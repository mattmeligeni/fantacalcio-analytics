"""Motore di regolamento del fantacalcio: puro, deterministico, senza modelli.

Vincolo non negoziabile (docs/METODO.md §7): `rules/` non dipende da `models/`.
"""
from .config import LEGA, LeagueRules
from .fantavoto import (
    Prestazione,
    SENZA_VOTO,
    bonus_netti,
    componenti_bonus,
    da_voto_testuale,
    fantavoto,
    fantavoto_vettoriale,
    imbattibile,
    reti_da_punti,
    somma_fantavoti,
)
from .giornata import (
    Lineup,
    Modificatore,
    punteggio_base,
    punteggio_squadra,
)

__all__ = [
    "LEGA",
    "LeagueRules",
    "Prestazione",
    "SENZA_VOTO",
    "bonus_netti",
    "componenti_bonus",
    "da_voto_testuale",
    "fantavoto",
    "fantavoto_vettoriale",
    "imbattibile",
    "reti_da_punti",
    "somma_fantavoti",
    "Lineup",
    "Modificatore",
    "punteggio_base",
    "punteggio_squadra",
]
