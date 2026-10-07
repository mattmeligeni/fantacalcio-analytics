"""Livelli di rimpiazzo per ruolo: il valore che si ottiene gratis.

Il rimpiazzo e' il miglior giocatore libero dopo l'asta, ottenibile a 1 credito.
Si calcola sulla **domanda di titolari** (`LEGA.titolari_per_ruolo`), NON sugli
slot di rosa: si possiedono 3 portieri ma se ne schiera 1. Calcolarlo sugli slot
e' l'errore gia' commesso una volta (docs/METODO.md §10): dava il 24% dei crediti ai
portieri.

Qui il rimpiazzo si calcola sui **punti proiettati** dell'universo acquistabile
(il listone), non sui punti storici: e' il livello che rimarra' libero data la
domanda della lega.
"""
from __future__ import annotations

import pandas as pd

from rules import LEGA, LeagueRules

RUOLI = ("P", "D", "C", "A")


def rango_rimpiazzo(ruolo: str, lega: LeagueRules = LEGA) -> int:
    """k-esimo giocatore per ruolo che segna il livello di rimpiazzo.

    k = titolari_per_ruolo × squadre (arrotondato). Con 8 squadre: P 8, D 28,
    C 28, A 24. Il (k+1)-esimo e oltre restano tipicamente liberi.
    """
    return round(lega.titolari_per_ruolo[ruolo] * lega.squadre)


def livelli_rimpiazzo(proiezioni: pd.DataFrame,
                      lega: LeagueRules = LEGA) -> dict[str, float]:
    """Punti proiettati del giocatore di rimpiazzo, per ruolo.

    `proiezioni` deve avere colonne `R` e `punti_proj` e coprire l'universo
    acquistabile (listone proiettato). Se un ruolo ha meno di k candidati, il
    rimpiazzo e' l'ultimo disponibile (caso di guardia, non atteso col listone).
    """
    liv = {}
    for r in RUOLI:
        sub = (proiezioni[proiezioni.R == r]
               .sort_values("punti_proj", ascending=False)
               .reset_index(drop=True))
        k = rango_rimpiazzo(r, lega)
        idx = min(k, len(sub)) - 1
        liv[r] = float(sub.loc[idx, "punti_proj"]) if idx >= 0 else 0.0
    return liv


def valore_sopra_rimpiazzo(proiezioni: pd.DataFrame,
                           lega: LeagueRules = LEGA) -> pd.Series:
    """VOR = max(0, punti_proj − rimpiazzo del ruolo). Troncato a zero: sotto il
    rimpiazzo il giocatore vale il pavimento, non un valore negativo."""
    liv = livelli_rimpiazzo(proiezioni, lega)
    vor = proiezioni.punti_proj - proiezioni.R.map(liv)
    return vor.clip(lower=0.0)
