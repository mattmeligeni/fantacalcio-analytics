"""L'artefatto del listino si genera, ha le sezioni e un motivo per ogni riga."""
import pathlib

import pandas as pd
import pytest

DATI = pathlib.Path("data/raw/Statistiche Fantacalcio")
pytestmark = pytest.mark.skipif(not DATI.exists(), reason="dati non disponibili")


@pytest.fixture(scope="module")
def artefatti(tmp_path_factory):
    import value.report as rep
    out = tmp_path_factory.mktemp("out")
    vecchio = rep.OUT
    rep.OUT = out
    try:
        rep.scrivi_artefatti()
    finally:
        rep.OUT = vecchio
    return out


def test_report_si_genera_con_motivo(artefatti):
    lis = pd.read_csv(artefatti / "listino.csv")
    assert lis.motivo.notna().all() and (lis.motivo.str.len() > 0).all()
    testo = (artefatti / "listino.html").read_text(encoding="utf-8")
    for sezione in ("occasioni", "trappole", "Gerarchie contese", "bassa informazione"):
        assert sezione in testo


def test_monte_crediti_e_quote(artefatti):
    from rules import LEGA
    lis = pd.read_csv(artefatti / "listino.csv")
    rose = sum(lis[lis.ruolo == r].prezzo.nlargest(s * LEGA.squadre).sum()
               for r, s in LEGA.rosa.slot.items())
    assert abs(rose - LEGA.monte_crediti) <= 25       # arrotondamento all'intero
    assert lis.prezzo.min() >= 1
    # chi e' arrivato dopo il listone non ha FVM: in coda, senza differenza
    assert lis.diff_vs_fvm.dropna().is_monotonic_decreasing


def test_un_solo_tasso_crediti(artefatti):
    lis = pd.read_csv(artefatti / "listino.csv")
    m = lis.valore > 1
    tasso = (lis.prezzo[m] - 1) / lis.valore[m]
    assert tasso.max() / tasso.min() < 1.2            # solo arrotondamento
