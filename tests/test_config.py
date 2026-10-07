"""Regolamento dichiarativo (rules/config.py): orizzonte di proiezione e
domanda di titolari non devono piu' essere parametri nascosti nel codice."""
import pathlib

import pandas as pd
import pytest

from rules import LEGA

CALENDARIO = pathlib.Path("data/raw/calendario_serie-a-it_2026-27.csv")


def test_giornate_totali_validate_contro_calendario():
    """`giornate_totali` va validato contro il calendario, non assunto."""
    if not CALENDARIO.exists():
        pytest.skip("calendario non disponibile")
    cal = pd.read_csv(CALENDARIO)
    assert int(cal.matchday.max()) == LEGA.giornate_totali
    # 380 partite = 38 giornate x 10 (20 squadre): giornate complete
    assert cal.groupby("matchday").size().eq(10).all()


def test_orizzonte_pieno():
    # conteggio dalla 3a su 38 -> 36 giornate a punti
    assert LEGA.giornate_residue(0) == 36
    assert LEGA.giornate_conteggiate == 36


def test_orizzonte_a_stagione_avviata():
    # l'asta cade alla 2a-3a: dopo la 2a giornata restano dalla 3a alla 38a = 36
    assert LEGA.giornate_residue(2) == 36
    # dalla 3a in poi ogni giornata giocata ne toglie una
    assert LEGA.giornate_residue(3) == 35
    # riparazione di gennaio (dopo la 19a): dalla 20a alla 38a
    assert LEGA.giornate_residue(19) == 19
    # a fine stagione mai negativo
    assert LEGA.giornate_residue(38) == 0
    assert LEGA.giornate_residue(50) == 0


def test_orizzonte_lega_da_prima_giornata():
    import dataclasses
    lega = dataclasses.replace(LEGA, prima_giornata_conteggiata=1)
    assert lega.giornate_residue(0) == 38


def test_titolari_per_ruolo_esposti():
    t = LEGA.titolari_per_ruolo
    assert t == {"P": 1.0, "D": 3.5, "C": 3.5, "A": 3.0}
    # somma coerente con un 11 titolare (1 + 3.5 + 3.5 + 3 = 11)
    assert sum(t.values()) == 11.0


def test_aritmetica_contendibili():
    assert LEGA.monte_crediti == 4000
    assert LEGA.slot_totali_lega == 200
    assert LEGA.crediti_contendibili == 3800
