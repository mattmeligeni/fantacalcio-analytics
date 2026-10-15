"""Backtest su split temporale rigoroso: si rigiocano le aste 2022-23 → 2025-26.

Per ogni stagione di prova:
  1. si ricostruisce l'istantanea d'asta (models.istantanea.da_storico):
     universo dei tesserati, club all'asta, prime `giornata_asta` giornate
     osservate, storico solo delle stagioni precedenti;
  2. si addestrano tutti i modelli SOLO sulle aste storiche precedenti;
  3. si proietta e si confronta con quanto realizzato sulle giornate che
     contano (dalla 3ª alla 38ª), fantavoto di lega e imbattibilita' inclusi.

Il 2021-22 non e' una stagione di prova: e' la prima asta ricostruibile (serve
la stagione precedente per le caratteristiche) e fa da addestramento.

Metriche, sempre DENTRO il ruolo (paradosso di Simpson, docs/METODO.md §6.4):
  - correlazione di rango (Spearman) fra punti previsti e realizzati, su tutto
    l'universo e sui giocatori che contano in asta (i primi per previsione);
  - errore assoluto medio su punti e presenze, distorsione media;
  - pendenza di calibrazione: regressione dei punti reali sui previsti (1 =
    dispersione giusta; < 1 = previsioni troppo disperse; > 1 = troppo schiacciate);
  - "cattura": punti reali dei primi k scelti dal modello sul totale dei primi k
    veri (k = domanda di titolari della lega: 8 P, 28 D, 28 C, 24 A).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ingest.fonti import carica_partite
from ingest.panel import carica_giornate, pannello_stagioni
from models import proiezione as pj
from models.istantanea import _stagione_precedente, da_storico
from rules import LEGA, LeagueRules

STAGIONI_PROVA = ("2022-23", "2023-24", "2024-25", "2025-26")
RUOLI = ("P", "D", "C", "A")


def baseline_ingenua(ist, giornate: pd.DataFrame, n_giornate: int) -> pd.Series:
    """Punti della stagione scorsa riportati all'orizzonte: il numero su cui si
    ancora la stanza (docs/METODO.md §6.4). 0 per chi non era in Serie A."""
    prec = _stagione_precedente(ist.stagione)
    g = giornate[giornate.stagione == prec]
    punti = g.groupby("Id").fv.sum() * n_giornate / 38
    return ist.universo.Id.map(punti).fillna(0.0).set_axis(ist.universo.Id)


def proiezioni_storiche(stagioni=STAGIONI_PROVA, giornata_asta: int = 2,
                        lega: LeagueRules = LEGA, dati=None) -> pd.DataFrame:
    """Proiezioni del modello e realizzato, una riga per (stagione, giocatore)."""
    g, S, P = dati if dati is not None else _carica()
    parti = []
    for t in stagioni:
        ist = da_storico(t, giornata_asta, g, S, P)
        m = pj.addestra(ist, g, S, P, lega)
        out = pj.proietta(m, ist, lega)
        real = pj.realizzato(ist, g, lega)
        _, n = pj.disponibilita.giornate_conteggiate(ist, lega)
        out["stagione"] = t
        out["punti_real"] = out.Id.map(real.punti).fillna(0.0)
        out["pv_real"] = out.Id.map(real.pv).fillna(0)
        out["rigori_real"] = out.Id.map(real.rc).fillna(0)
        out["ingenua"] = out.Id.map(baseline_ingenua(ist, g, n))
        parti.append(out)
    return pd.concat(parti, ignore_index=True)


def _carica():
    g = carica_giornate()
    return g, pannello_stagioni(g), carica_partite()


def rango_titolari(lega: LeagueRules = LEGA) -> dict[str, int]:
    return {r: round(lega.titolari_per_ruolo[r] * lega.squadre) for r in RUOLI}


def metriche(df: pd.DataFrame, modelli: dict[str, tuple[str, str | None]],
             reale: str = "punti_real", lega: LeagueRules = LEGA) -> pd.DataFrame:
    """Metriche per (stagione, ruolo, modello).

    `modelli`: nome -> (colonna punti previsti, colonna presenze previste o None).
    La correlazione "fra i rilevanti" si calcola su un insieme COMUNE a tutti i
    modelli confrontati: l'unione dei primi 3k per punti realizzati e dei primi
    3k per ciascun modello (k = domanda di titolari). Calcolarla sui primi di
    ogni modello separatamente premierebbe chi mette in cima giocatori molto
    diversi fra loro, non chi li ordina meglio.
    """
    k_tit = rango_titolari(lega)
    righe = []
    for (t, r), d in df.groupby(["stagione", "ruolo"]):
        k = k_tit[r]
        rilevanti = set(d.nlargest(3 * k, reale).index)
        for col, _ in modelli.values():
            rilevanti |= set(d.nlargest(3 * k, col).index)
        dr = d.loc[sorted(rilevanti)]
        migliori = d.nlargest(k, reale)[reale].sum()
        for nome, (col, pv) in modelli.items():
            x, y = d[col].values, d[reale].values
            riga = dict(
                stagione=t, ruolo=r, modello=nome,
                spearman=d[col].corr(d[reale], method="spearman"),
                spearman_rilevanti=dr[col].corr(dr[reale], method="spearman"),
                mae=np.abs(x - y).mean(),
                distorsione=(x - y).mean(),
                calibrazione=np.polyfit(x, y, 1)[0] if np.std(x) > 0 else np.nan,
                cattura=d.nlargest(k, col)[reale].sum() / migliori,
            )
            if pv is not None:
                riga["mae_presenze"] = np.abs(d[pv] - d.pv_real).mean()
                riga["corr_presenze"] = np.corrcoef(d[pv], d.pv_real)[0, 1]
            righe.append(riga)
    return pd.DataFrame(righe)


def riassunto(df: pd.DataFrame, modelli: dict[str, tuple[str, str | None]],
              lega: LeagueRules = LEGA) -> pd.DataFrame:
    """Tabella modello × ruolo con la media delle metriche sulle stagioni."""
    M = metriche(df, modelli, lega=lega)
    return M.groupby(["modello", "ruolo"]).mean(numeric_only=True).round(3)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    df = proiezioni_storiche()
    print(riassunto(df, {"nuovo": ("punti_proj", "pv_proj"),
                         "ingenuo": ("ingenua", None)}))
