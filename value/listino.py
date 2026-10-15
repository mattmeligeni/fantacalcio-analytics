"""Il listino d'asta: proiezione → valore → prezzo, confrontato con l'FVM.

Flusso:
  1. istantanea d'asta (models/istantanea.per_asta): universo dal listone,
     storico completo, e le giornate della stagione d'asta gia' presenti in
     data/raw/Voti/ (le prime giornate osservate: §3);
  2. modello di proiezione addestrato sulle aste storiche ricostruite con le
     STESSE informazioni (stesso numero di giornate osservate), proiezione;
  3. valore per presenza sopra il panchinaro tipo (value/valore.py, funzione
     sostituibile §7.1);
  4. prezzo: un unico tasso crediti/valore, monte esatto di 4000 sulle rose;
  5. confronto con l'FVM riportato allo stesso monte sulle rose.

Cosa NON fa: dire quanto offrire in un dato momento dell'asta. Il prezzo e'
quanto vale il giocatore se tutti pagassero il giusto; quanto puoi spendere
date la rosa gia' fatta e i crediti degli avversari e' compito di `auction/`.

Rifare il listino dopo aver messo in data/raw/Voti/26-27/ i voti delle prime
giornate: il modello passa automaticamente a usare le presenze osservate, il
predittore di disponibilita' piu' forte di tutti.
"""
from __future__ import annotations

import pandas as pd

from ingest.fonti import carica_listone, carica_partite
from ingest.panel import carica_giornate, pannello_stagioni
from models import proiezione as pj
from models.istantanea import per_asta
from rules import LEGA, LeagueRules
from value.valore import (FunzioneValore, livelli_rimpiazzo, prezzi,
                          valore_per_presenza)

SOGLIA_BASSA_INFO = 5.0      # presenze pesate sotto cui la stima e' quasi solo prior


def giornate_osservate(giornate: pd.DataFrame, stagione: str) -> int:
    """Ultima giornata della stagione d'asta di cui ci sono i voti (0 se nessuna)."""
    g = giornate[giornate.stagione == stagione]
    return int(g.giornata.max()) if len(g) else 0


def riscala_fvm(listino: pd.DataFrame, lega: LeagueRules = LEGA) -> pd.Series:
    """FVM/2 riportato allo stesso monte dei prezzi: la somma sulle rose (i
    migliori per FVM nel rispetto degli slot) fa 4000. Isola il disaccordo
    RELATIVO col mercato dallo scarto di scala fra i due sistemi."""
    in_rosa = pd.Series(False, index=listino.index)
    for r, slot in lega.rosa.slot.items():
        m = listino.ruolo == r
        in_rosa[listino.fvm_meta[m].nlargest(slot * lega.squadre).index] = True
    fattore = lega.monte_crediti / listino.fvm_meta[in_rosa].sum()
    return listino.fvm_meta * fattore


# Titolari per squadra e ruolo usati per confrontare le gerarchie (4-4-2 medio).
TITOLARI_SQUADRA = {"P": 1, "D": 4, "C": 4, "A": 2}


def gerarchia_contesa(listino: pd.DataFrame) -> pd.Series:
    """Segnala chi il mercato (FVM) considera titolare e il modello no, o viceversa.

    Senza giornate osservate il modello non vede i cambi estivi di gerarchia
    (un portiere arrivato dall'estero da titolare e' per lui un esordiente),
    mentre l'FVM li incorpora. Non si corregge la stima con l'FVM (non c'e'
    storico di FVM su cui calibrarlo): si segnala, e si rifa' il listino dopo
    le prime giornate, che risolvono il dubbio meglio di qualunque fonte.
    """
    flag = pd.Series("", index=listino.index)
    for (sq, r), d in listino.groupby(["squadra", "ruolo"]):
        n = TITOLARI_SQUADRA[r]
        # in porta il titolare e' uno solo: basta che il mercato ne indichi un
        # altro; negli altri reparti serve uno scarto netto di gerarchia
        soglia = n if r == "P" else 2 * n
        rk_mkt = d.fvm_meta.rank(ascending=False, method="first")
        rk_mod = d.pv_proj.rank(ascending=False, method="first")
        per_mercato = d.index[(rk_mkt <= n) & (rk_mod > soglia)]
        per_modello = d.index[(rk_mod <= n) & (rk_mkt > soglia)]
        flag[per_mercato] = "titolare per il mercato, riserva per il modello"
        flag[per_modello] = "titolare per il modello, riserva per il mercato"
    return flag


def universo_corrente(listone: pd.DataFrame, corrente) -> pd.DataFrame:
    """A stagione avviata l'universo e' la rosa ATTUALE (Statistiche della
    stagione in corso: comprende gli acquisti arrivati dopo il listone e toglie
    chi e' partito), con FVM e quotazione presi dal listone dove ci sono."""
    if corrente is None:
        return listone
    u = corrente.osservato[["Id", "Nome", "ruolo", "squadra"]].drop_duplicates("Id")
    extra = [c for c in ["fvm_meta", "quotazione", "eta"] if c in listone.columns]
    return u.merge(listone[["Id", *extra]], on="Id", how="left")


def costruisci_listino(lega: LeagueRules = LEGA, stagione: str | None = None,
                       funzione_valore: FunzioneValore = valore_per_presenza,
                       giornata_asta: int | None = None,
                       dati=None) -> tuple[pd.DataFrame, dict]:
    """Il listino completo e un dizionario di informazioni sul calcolo.

    Senza argomenti usa la stagione del listone piu' recente e tutto cio' che
    si sa di quella stagione (ingest/corrente.py). `giornata_asta=0` forza il
    listino d'estate, senza nulla di osservato.
    """
    from ingest.corrente import carica_stagione_in_corso
    from ingest.importa import stagione_corrente
    stagione = stagione or stagione_corrente()
    if dati is None:
        g = carica_giornate()
        dati = (g, pannello_stagioni(g), carica_partite(), carica_listone())
    g, S, P, listone = dati
    corrente = carica_stagione_in_corso(g, lega) if giornata_asta != 0 else None
    if corrente is not None and corrente.stagione != stagione:
        corrente = None
    if giornata_asta is None:
        giornata_asta = corrente.giornata if corrente else giornate_osservate(g, stagione)
    voti_per_giornata = giornate_osservate(g, stagione) > 0
    ist = per_asta(universo_corrente(listone, corrente), stagione, giornata_asta, g, S, P,
                   osservato=None if (corrente is None or voti_per_giornata) else corrente.osservato,
                   partite_osservate=None if corrente is None else corrente.partite)
    modello = pj.addestra(ist, g, S, P, lega)
    L = pj.proietta(modello, ist, lega)

    L["valore"] = funzione_valore(L, lega).values
    L["prezzo"] = prezzi(L, L.valore, lega).round().astype(int)
    L["fvm_riscalato"] = riscala_fvm(L, lega).round(1)
    L["diff_vs_fvm"] = (L.prezzo - L.fvm_riscalato).round(1)
    L["bassa_info"] = L.senza_storico | (L.n_eff < SOGLIA_BASSA_INFO)
    L["gerarchia"] = gerarchia_contesa(L)

    info = dict(
        stagione=stagione,
        giornate_osservate=giornata_asta,
        fonte_osservate=corrente.fonte if corrente else "nessuna",
        giornate_conteggiate=pj.disponibilita.giornate_conteggiate(ist, lega)[1],
        aste_addestramento=modello.aste_addestramento,
        rimpiazzo=livelli_rimpiazzo(L, lega),
        squadre=modello.squadre.prevedi(ist),
        disponibilita=modello.disponibilita.tabella_coefficienti(),
        rendimento=modello.rendimento.tabella(),
    )
    colonne = ["Id", "Nome", "ruolo", "squadra", "eta", "p_voto", "pv_proj",
               "fm_voto", "fm_azione", "fm_malus", "fm_port", "fm_base",
               "rigori_attesi", "punti_rigori", "punti_proj", "fm_proj",
               "valore", "prezzo", "quotazione", "fvm_meta", "fvm_riscalato",
               "diff_vs_fvm", "bassa_info", "senza_storico", "cambio_club",
               "neopromossa", "gerarchia", "n_eff"]
    L = L[[c for c in colonne if c in L.columns]]
    return L.sort_values("diff_vs_fvm", ascending=False).reset_index(drop=True), info


def quote_per_ruolo(listino: pd.DataFrame) -> pd.Series:
    """Quota dei crediti contendibili per ruolo (prezzo − 1 sulle rose)."""
    q = listino.groupby("ruolo").apply(lambda d: (d.prezzo - 1).clip(lower=0).sum(),
                                       include_groups=False)
    return (q / q.sum() * 100).reindex(["P", "D", "C", "A"]).round(1)


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 30)
    lis, info = costruisci_listino()
    print(f"listino {info['stagione']}: {len(lis)} giocatori | giornate osservate "
          f"{info['giornate_osservate']} | conteggiate {info['giornate_conteggiate']}")
    print("quota crediti per ruolo (%):", quote_per_ruolo(lis).to_dict())
    print(lis.head(20)[["Nome", "ruolo", "squadra", "pv_proj", "fm_proj",
                        "punti_proj", "prezzo", "fvm_riscalato", "diff_vs_fvm"]].round(1))
