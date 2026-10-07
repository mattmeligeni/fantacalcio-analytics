"""Quota strategica di crediti per ruolo (docs/METODO.md §6.3), misurata dai dati.

E' la decisione portante di "quanto spendere per ruolo": si calcola sui livelli
di rimpiazzo REALIZZATI (punti storici, imbattibilita' inclusa), come somma del
valore sopra il rimpiazzo per ruolo, mediana sulle stagioni. Il listino usa
questa quota per l'allocazione FRA i ruoli; la proiezione decide chi comprare
DENTRO ogni ruolo. Tenere separate le due cose evita che la compressione della
proiezione (che regredisce piu' gli attaccanti dei difensori) sposti da sola
l'allocazione strategica.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from rules import LEGA, LeagueRules
from value.dati import con_imbattibilita

RUOLI = ("P", "D", "C", "A")


def quote_ruolo(lega: LeagueRules = LEGA,
                m: pd.DataFrame | None = None) -> dict[str, float]:
    """Quota dei crediti contendibili per ruolo (somma 1), mediana sulle stagioni.

    Metodo di §6.3: per ogni stagione e ruolo, rimpiazzo = k-esimo per punti con
    k = titolari×squadre; VOR_totale = Σ(punti − rimpiazzo)+; quota = share del
    VOR fra i ruoli. Si prende la mediana fra le stagioni (piu' robusta della
    media alle annate anomale, errore gia' commesso in §10).
    """
    if m is None:
        m = con_imbattibilita()
    per_stag = []
    for st, g in m.groupby("stagione"):
        vor = {}
        for r in RUOLI:
            k = round(lega.titolari_per_ruolo[r] * lega.squadre)
            sub = g[g.R == r].sort_values("punti_imb", ascending=False).reset_index(drop=True)
            repl = sub.loc[k - 1, "punti_imb"]
            vor[r] = float((sub.punti_imb - repl).clip(lower=0).sum())
        tot = sum(vor.values())
        per_stag.append({r: vor[r] / tot for r in RUOLI})
    med = pd.DataFrame(per_stag).median()
    med = med / med.sum()
    return {r: float(med[r]) for r in RUOLI}


if __name__ == "__main__":
    q = quote_ruolo()
    print("quota strategica crediti per ruolo (§6.3):")
    for r in RUOLI:
        print(f"  {r}: {q[r]*100:.1f}%")
