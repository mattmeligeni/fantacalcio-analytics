"""Stato della lega (auction/stato.py): vincoli d'asta, offerta massima,
inflazione, persistenza. Casi sintetici, niente dati."""
import pandas as pd
import pytest

from auction.stato import StatoLega, carica, salva
from rules import LEGA

SQUADRE = [f"S{i}" for i in range(LEGA.squadre)]


def _listino():
    righe = []
    for r, n in {"P": 30, "D": 80, "C": 80, "A": 60}.items():
        for i in range(n):
            righe.append(dict(Id=len(righe) + 1, Nome=f"{r}{i}", ruolo=r, prezzo=max(1, 60 - i)))
    return pd.DataFrame(righe)


def test_offerta_massima_e_slot():
    s = StatoLega(SQUADRE, "S0")
    s.acquista(1, "P0", "P", "S0", 100)
    rie = s.riepilogo().loc["S0"]
    assert rie.crediti == 400 and rie.slot_liberi == 24
    assert rie.offerta_massima == 400 - (24 - 1)


def test_vincoli_rifiutati():
    s = StatoLega(SQUADRE, "S0")
    s.acquista(1, "P0", "P", "S0", 1)
    with pytest.raises(ValueError, match="gia' di S0"):
        s.acquista(1, "P0", "P", "S1", 5)
    s.acquista(2, "P1", "P", "S0", 1)
    s.acquista(3, "P2", "P", "S0", 1)
    with pytest.raises(ValueError, match="slot"):
        s.acquista(4, "P3", "P", "S0", 1)
    with pytest.raises(ValueError, match="al massimo"):
        s.acquista(5, "D0", "D", "S1", 500)


def test_cessione_rimborsa_e_libera():
    s = StatoLega(SQUADRE, "S0")
    s.acquista(10, "D0", "D", "S0", 30)
    s.cedi(10)
    assert s.proprietario(10) is None
    assert s.riepilogo().loc["S0"].crediti == 500 - 30 + round(30 * LEGA.rimborso_svincolo)


def test_annulla_ultimo():
    s = StatoLega(SQUADRE, "S0")
    s.acquista(10, "D0", "D", "S0", 30)
    assert s.annulla_ultimo().Id == 10 and s.rose().empty


def test_prezzi_correnti_seguono_i_crediti_rimasti():
    lis = _listino()
    s = StatoLega(SQUADRE, "S0")
    neutro = s.prezzi_correnti(lis).attrs["fattore"]
    # la stanza strapaga il primo: restano meno crediti, i rimasti costano meno
    s.acquista(1, "P0", "P", "S1", 300)
    assert s.prezzi_correnti(lis).attrs["fattore"] < neutro
    assert s.inflazione(lis) > 1


def test_salvataggio_roundtrip(tmp_path):
    s = StatoLega(SQUADRE, "S3")
    s.acquista(7, "P6", "P", "S3", 12, tipo="mercato")
    f = tmp_path / "lega.json"
    salva(s, f)
    t = carica(f)
    assert t.mia == "S3" and t.rose().equals(s.rose())
