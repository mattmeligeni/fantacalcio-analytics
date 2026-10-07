"""L'artefatto del listino si genera e ha le tre sezioni con il motivo."""
import pathlib

import pandas as pd
import pytest

DATI = pathlib.Path("data/raw/Statistiche Fantacalcio")
pytestmark = pytest.mark.skipif(not DATI.exists(), reason="dati non disponibili")


def test_report_si_genera_con_motivo(tmp_path, monkeypatch):
    import value.report as rep
    monkeypatch.setattr(rep, "OUT", tmp_path)
    rep.scrivi_artefatti()
    csv = tmp_path / "listino.csv"
    htm = tmp_path / "listino.html"
    assert csv.exists() and htm.exists()
    lis = pd.read_csv(csv)
    assert "motivo" in lis.columns
    assert lis.motivo.notna().all() and (lis.motivo.str.len() > 0).all()
    # ogni occasione con storico ha un motivo che non e' quello di bassa info
    occ = lis[~lis.bassa_info]
    assert not occ.motivo.str.contains("bassa informazione").any()
    testo = htm.read_text(encoding="utf-8")
    assert "occasioni" in testo and "trappole" in testo and "bassa informazione" in testo
