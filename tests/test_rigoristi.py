"""Gerarchia rigoristi e conversione contratta (value/rigoristi.py)."""
import pathlib

import pytest

from value.rigoristi import (
    conversione_lega,
    rigoristi_carriera,
    valore_atteso_rigore,
)

DATI = pathlib.Path("data/raw/Statistiche Fantacalcio")
pytestmark = pytest.mark.skipif(not DATI.exists(), reason="dati non disponibili")


def test_valore_atteso_rigore():
    # a conversione di lega ~0,79 un rigore vale ~1,7 punti attesi
    assert valore_atteso_rigore(1.0) == 3.0
    assert valore_atteso_rigore(0.5) == 0.0
    assert abs(valore_atteso_rigore(0.789) - 1.734) < 0.01


def test_conversione_lega_plausibile():
    p = conversione_lega()
    assert 0.74 < p < 0.82        # ~76-79%, coerente con la letteratura


def test_contrazione_verso_la_media():
    r = rigoristi_carriera()
    p0 = conversione_lega()
    # la conversione contratta e' sempre fra quella grezza e il prior di lega
    tra = ((r.conv_contratta - r.conv_grezza) * (p0 - r.conv_grezza) >= -1e-9)
    assert tra.all()
    # i pochi calci vengono contratti piu' dei molti
    pochi = r[r.calciati <= 3]
    molti = r[r.calciati >= 15]
    spinta_pochi = (pochi.conv_contratta - pochi.conv_grezza).abs().mean()
    spinta_molti = (molti.conv_contratta - molti.conv_grezza).abs().mean()
    assert spinta_pochi > spinta_molti


def test_identita_rigori():
    from value.dati import carica_statistiche
    s = carica_statistiche()
    assert (s.Rc == s["R+"] + s["R-"]).all()


def test_conversione_contratta_forte():
    """Parte 2.2: la conversione va contratta FORTE verso la media di lega
    (persistenza misurata 0,12), non a occhio. Un top rigorista al 0,90 deve
    proiettare vicino alla media di lega, non a 0,88."""
    from value.rigoristi import proietta_rigori, conversione_lega, rigoristi_carriera
    p0 = conversione_lega()
    pr = proietta_rigori().merge(rigoristi_carriera()[["Id", "Nome"]], on="Id")
    ber = pr[pr.Nome.str.startswith("Berardi")].iloc[0]
    assert abs(ber.conv_proj - p0) < 0.03      # tirato quasi alla media di lega


def test_non_rigoristi_zero_punti():
    from value.rigoristi import proietta_rigori
    from value.dati import carica_statistiche
    s = carica_statistiche()
    pr = proietta_rigori(stat=s)
    mai = set(s.groupby("Id").Rc.sum().loc[lambda x: x == 0].index)
    assert pr[pr.Id.isin(mai)].empty     # chi non ha mai calciato non ha proiezione rigori


def test_cambio_club_abbatte_i_rigori():
    """Un rigorista che cambia club perde lo status: rigore_punti crollano."""
    from value.rigoristi import proietta_rigori
    from value.dati import carica_statistiche
    s = carica_statistiche()
    # prendo un rigorista noto e ne simulo il cambio club
    tak = s.groupby("Id").Rc.sum().idxmax()
    resta = proietta_rigori(stat=s, squadra_2026={})     # nessun cambio noto
    ultima = s[s.Id == tak].sort_values("stagione").iloc[-1].Squadra
    cambia = proietta_rigori(stat=s, squadra_2026={tak: "SquadraNuovaX"})
    r0 = resta[resta.Id == tak].rigore_punti.iloc[0]
    r1 = cambia[cambia.Id == tak].rigore_punti.iloc[0]
    assert r1 < r0 * 0.5
