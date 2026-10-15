"""Stagione in corso (ingest/corrente.py) e anagrafica Understat."""
import pathlib

import pandas as pd
import pytest

from ingest.anagrafica import aggancia, normalizza
from ingest.corrente import osservato_da_statistiche


def test_statistiche_gol_rigori_separati():
    stat = pd.DataFrame([dict(Id=1, R="A", Nome="X", Squadra="Roma", Pv=5, Mv=6.5, Fm=8.0,
                              Gf=4, Gs=0, Rp=0, Rc=2, **{"R+": 1, "R-": 1}, Ass=2, Amm=1,
                              Esp=0, Au=0)])
    o = osservato_da_statistiche(stat).iloc[0]
    assert o.gf == 3                                   # Gf include i rigori: 4 − 1
    assert o.c_azione == 3 * 3 + 2
    assert o.c_rigore == 3 * 1 - 3 * 1
    assert o.c_malus == -0.5
    assert o.voto_s == 32.5


def test_normalizzazione_lettere_speciali():
    assert normalizza("Højlund") == "hojlund"
    assert normalizza("Milinkovic-Savic V.") == "milinkovic savic v."


def test_aggancio_con_iniziale_e_cognome_attaccato():
    fanta = pd.DataFrame([dict(Id=1, Nome="Martinez L.", squadra="Inter"),
                          dict(Id=2, Nome="Martinez Jo.", squadra="Inter"),
                          dict(Id=3, Nome="Delprato", squadra="Parma")])
    us = pd.DataFrame([dict(player_id=10, player="Lautaro Martínez", team="Inter"),
                       dict(player_id=11, player="Josep Martínez", team="Inter"),
                       dict(player_id=12, player="Enrico Del Prato", team="Parma Calcio 1913")])
    m = aggancia(fanta, us).set_index("Id").player_id.to_dict()
    assert m == {1: 10, 2: 11, 3: 12}


CORRENTE = pathlib.Path("data/raw/Stagione in corso")


@pytest.mark.skipif(not CORRENTE.exists(), reason="stagione in corso non importata")
def test_anagrafica_reale_copertura():
    from ingest import anagrafica as an
    from ingest.corrente import carica_stagione_in_corso
    c = carica_stagione_in_corso()
    if c is None or c.minuti is None:
        pytest.skip("Understat in corso non scaricato")
    assert an.valida(an.aggancia(c.osservato, c.minuti), c.osservato) >= 0.95
