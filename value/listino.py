"""Il listino: dalla proiezione al prezzo consigliato, confrontato con l'FVM.

Flusso (docs/METODO.md §7 "Dal valore al prezzo"):
  listone -> proiezione base a due stadi (fantamedia scomposta × presenze) +
  punti attesi dai rigori (per status) -> valore sopra il rimpiazzo (troncato a
  zero) -> ripartizione dei contendibili + 1 di pavimento -> confronto con l'FVM.

Il calcolo del valore e' dietro una **funzione sostituibile** (`funzione_valore`,
default additivo): vincolo di docs/METODO.md §7.1. Se si attivano i modificatori si
passa qui a un valore marginale-simulato senza toccare il resto.

Distinzioni che l'output tiene esplicite (Parte 2.4):
  - **bassa informazione**: giocatori senza storico (prior di ruolo) o con
    pochissime presenze pesate. Escono vicini alla media PER COSTRUZIONE, quindi
    NON sono trappole nel senso utile: vanno a parte, marcati.
  - **trappole vere**: storico abbondante il cui prezzo di mercato eccede la
    proiezione. Quelle sono segnale.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from rules import LEGA, LeagueRules
from ingest.componenti import carica_componenti
from value.budget import quote_ruolo
from value.dati import carica_listone, carica_statistiche
from value.proiezione import ParametriRuolo, parametri_ruolo, prior_di_ruolo, proietta
from value.rigoristi import proietta_rigori
from value.rimpiazzo import valore_sopra_rimpiazzo

FunzioneValore = Callable[[pd.DataFrame, LeagueRules], pd.Series]

# soglia di presenze pesate sotto la quale la valutazione e' a bassa informazione
SOGLIA_BASSA_INFO = 5.0


def _proietta_listone(lega: LeagueRules, giornata_corrente: int,
                      par: ParametriRuolo, proj: pd.DataFrame,
                      rigori: pd.DataFrame) -> pd.DataFrame:
    """Aggancia a ogni riga del listone la proiezione base + i rigori, o il prior
    di ruolo se manca lo storico. Squadra e ruolo vengono dal listone 2026-27."""
    lst = carica_listone()
    pj = proj.set_index(["Id", "R"])
    rig = rigori.set_index("Id")
    id_con_storico = set(proj.Id)
    righe = []
    for _, r in lst.iterrows():
        cod = int(r.Cod) if pd.notna(r.Cod) else None
        base = dict(Cod=cod, Nome=r.Nome, ruolo=r.ruolo, squadra=r.squadra,
                    quotazione=r.quotazione, fvm_meta=r.fvm_meta)
        if cod is not None and (cod, r.ruolo) in pj.index:
            p = pj.loc[(cod, r.ruolo)]
            base.update(fm_base=float(p.fm_base), pv_proj=float(p.pv_proj),
                        punti_base=float(p.punti_base), n_eff=float(p.n_eff),
                        senza_storico=False, cambio_ruolo=False)
        else:
            pr = prior_di_ruolo(r.ruolo, lega, giornata_corrente, par)
            base.update(**pr, senza_storico=True, cambio_ruolo=(cod in id_con_storico))
        # componente rigori (0 se non e' un rigorista o manca lo storico)
        if cod is not None and cod in rig.index:
            base["rigore_punti"] = float(rig.loc[cod, "rigore_punti"])
            base["rigori_attesi"] = float(rig.loc[cod, "rigori_attesi"])
            base["cambio_club_rig"] = bool(rig.loc[cod, "cambio_club"])
        else:
            base["rigore_punti"] = 0.0
            base["rigori_attesi"] = 0.0
            base["cambio_club_rig"] = False
        righe.append(base)
    return pd.DataFrame(righe)


def costruisci_listino(lega: LeagueRules = LEGA, giornata_corrente: int = 0,
                       funzione_valore: FunzioneValore = valore_sopra_rimpiazzo
                       ) -> pd.DataFrame:
    """Il listino completo, ordinato per differenza prezzo−FVM/2 decrescente."""
    m = carica_componenti()
    stat = carica_statistiche()
    par = parametri_ruolo(m)
    proj = proietta(lega, giornata_corrente, m=m, par=par)

    lst = carica_listone()
    squadra_2026 = {int(c): s for c, s in zip(lst.Cod, lst.squadra) if pd.notna(c)}
    rigori = proietta_rigori(lega, giornata_corrente, stat=stat,
                             squadra_2026=squadra_2026)

    L = _proietta_listone(lega, giornata_corrente, par, proj, rigori)

    # punti proiettati = base (fantamedia scomposta × presenze) + rigori
    L["punti_proj"] = (L.punti_base + L.rigore_punti).round(2)
    L["fm_proj"] = (L.punti_proj / L.pv_proj.replace(0, pd.NA)).round(3)

    # valore sopra il rimpiazzo (funzione sostituibile, §7.1)
    L = L.rename(columns={"ruolo": "R"})
    L["vor"] = funzione_valore(L, lega)
    L = L.rename(columns={"R": "ruolo"})

    # Prezzo: la quota per ruolo viene dalla strategia (§6.3, value/budget), la
    # ripartizione DENTRO il ruolo dalla proiezione (VOR). Cosi' il listino e la
    # ripartizione del budget non si contraddicono (Parte 2.3): l'allocazione fra
    # ruoli e' quella misurata sui punti realizzati, non quella (piu' difensiva)
    # che la compressione della proiezione produrrebbe da sola.
    contendibili = lega.crediti_contendibili
    quote = quote_ruolo(lega)
    L["prezzo"] = 1.0
    for r, budget_r in quote.items():
        mask = L.ruolo == r
        vor_r = L.loc[mask, "vor"].sum()
        crediti_r = budget_r * contendibili
        if vor_r > 0:
            L.loc[mask, "prezzo"] = (L.loc[mask, "vor"] / vor_r * crediti_r + 1)
    L["prezzo"] = L.prezzo.round().astype(int)

    # confronto con l'FVM riscalato allo stesso monte (isola il disaccordo
    # relativo col mercato, non lo scarto di scala fra i due sistemi)
    fattore = L.prezzo.sum() / L.fvm_meta.sum() if L.fvm_meta.sum() > 0 else 1.0
    L["fvm_riscalato"] = (L.fvm_meta * fattore).round(1)
    L["diff_vs_fvm"] = (L.prezzo - L.fvm_riscalato).round(1)

    # bassa informazione: prior, oppure pochissime presenze pesate (Parte 2.4)
    L["bassa_info"] = L.senza_storico | (L.n_eff < SOGLIA_BASSA_INFO)

    cols = ["Nome", "ruolo", "squadra", "pv_proj", "fm_proj", "punti_proj",
            "rigori_attesi", "rigore_punti", "vor", "prezzo", "quotazione",
            "fvm_meta", "fvm_riscalato", "diff_vs_fvm", "bassa_info",
            "senza_storico", "cambio_ruolo", "cambio_club_rig", "n_eff"]
    return (L[cols].sort_values("diff_vs_fvm", ascending=False)
            .reset_index(drop=True))


def quote_per_ruolo(listino: pd.DataFrame) -> pd.DataFrame:
    """Quota del prezzo consigliato per ruolo, da confrontare con §6.3."""
    q = listino.groupby("ruolo").prezzo.sum()
    return (q / q.sum() * 100).reindex(["P", "D", "C", "A"]).round(1)


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 25)
    lis = costruisci_listino()
    print(f"listino: {len(lis)} giocatori | bassa info: {int(lis.bassa_info.sum())} "
          f"| senza storico: {int(lis.senza_storico.sum())}")
    print("\nquota prezzo per ruolo (%):")
    print(quote_per_ruolo(lis).to_string())
    solide = lis[~lis.bassa_info]
    print("\n=== 15 maggiori OCCASIONI (storico solido) ===")
    print(solide.head(15)[["Nome", "ruolo", "squadra", "punti_proj", "prezzo",
          "fvm_riscalato", "diff_vs_fvm", "rigori_attesi"]].round(1).to_string(index=False))
    print("\n=== 10 maggiori TRAPPOLE (storico solido) ===")
    print(solide.tail(10)[["Nome", "ruolo", "squadra", "punti_proj", "prezzo",
          "fvm_riscalato", "diff_vs_fvm", "rigori_attesi"]].round(1).to_string(index=False))
