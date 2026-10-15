"""Test di accettazione (docs/METODO.md §8): sulle aste ricostruite il modello
deve ordinare i giocatori meglio della baseline "punti dell'anno scorso", su cui
si ancora la stanza, ed essere calibrato (niente distorsione, dispersione giusta).

E' il test lento della suite (~1 minuto): rigioca due aste complete.
"""
import pathlib

import pytest

DATI = pathlib.Path("data/raw/Voti")
pytestmark = pytest.mark.skipif(not DATI.exists(), reason="dati non disponibili")


@pytest.fixture(scope="module")
def metriche():
    from backtest.storico import proiezioni_storiche, riassunto
    df = proiezioni_storiche(stagioni=("2024-25", "2025-26"))
    return riassunto(df, {"v3": ("punti_proj", "pv_proj"), "ingenuo": ("ingenua", None)})


def test_batte_la_baseline_in_ogni_ruolo(metriche):
    for r in "PDCA":
        assert metriche.loc[("v3", r), "spearman"] > metriche.loc[("ingenuo", r), "spearman"]


def test_calibrato(metriche):
    v3 = metriche.loc["v3"]
    assert v3.distorsione.abs().max() < 8          # punti, su ~100 di media
    assert v3.calibrazione.between(0.75, 1.25).all()


def test_presenze_previste_con_dispersione_reale(metriche):
    assert (metriche.loc["v3"].corr_presenze > 0.5).all()
