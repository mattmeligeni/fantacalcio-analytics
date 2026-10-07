"""Parser dei file grezzi verso pannelli tidy in memoria.

Regola: i grezzi non si toccano mai; i parser falliscono rumorosamente se le
colonne attese non ci sono (docs/DATI.md §9).
"""
from .voti import leggi_giornata, leggi_stagione

__all__ = ["leggi_giornata", "leggi_stagione"]
