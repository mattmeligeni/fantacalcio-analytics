"""L'istantanea d'asta non deve mai vedere il futuro: e' la garanzia su cui
poggia tutto il backtest (models/istantanea.py)."""
import pathlib

import pytest

DATI = pathlib.Path("data/raw/Voti")
pytestmark = pytest.mark.skipif(not DATI.exists(), reason="dati non disponibili")


@pytest.fixture(scope="module")
def dati():
    from ingest.fonti import carica_partite
    from ingest.panel import carica_giornate, pannello_stagioni
    g = carica_giornate()
    return g, pannello_stagioni(g), carica_partite()


@pytest.mark.parametrize("stagione", ["2022-23", "2025-26"])
def test_nessuna_sbirciata(dati, stagione):
    from models.istantanea import da_storico
    ist = da_storico(stagione, 2, *dati)
    assert (ist.storico.stagione < stagione).all()
    assert (ist.giornate_storiche.stagione < stagione).all()
    assert (ist.partite.stagione < stagione).all()
    assert (ist.osservate.stagione == stagione).all()
    assert ist.osservate.giornata.max() <= 2


def test_universo_e_club_della_stagione(dati):
    from models.istantanea import da_storico
    g = dati[0]
    ist = da_storico("2024-25", 2, *dati)
    squadre = set(g[g.stagione == "2024-25"].squadra)
    assert set(ist.universo.squadra) <= squadre and len(squadre) == 20
    assert ist.universo.Id.is_unique


def test_arrivi_di_gennaio_esclusi(dati):
    from models.istantanea import da_storico
    g, S, _ = dati
    ist = da_storico("2024-25", 2, *dati)
    cur = S[S.stagione == "2024-25"]
    ieri = set(S[S.stagione == "2023-24"].Id)
    gennaio = cur[(cur.prima_giornata >= 20) & ~cur.Id.isin(ieri)].Id
    assert len(gennaio) > 0
    assert not ist.universo.Id.isin(gennaio).any()


def test_senza_giornate_osservate(dati):
    from models.istantanea import da_storico
    ist = da_storico("2024-25", 0, *dati)
    assert ist.osservate.empty
