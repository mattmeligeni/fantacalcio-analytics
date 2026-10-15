"""Pannelli unificati (ingest/panel.py) e fonti (ingest/fonti.py).

Il pannello giocatore × giornata deve riprodurre il motore di regolamento
riga per riga; quello giocatore × stagione deve contenere i tesserati senza
presenze, che la versione precedente perdeva.
"""
import pathlib

import numpy as np
import pytest

from rules import Prestazione, fantavoto

DATI = pathlib.Path("data/raw/Voti")
pytestmark = pytest.mark.skipif(not DATI.exists(), reason="dati non disponibili")


@pytest.fixture(scope="module")
def giornate():
    from ingest.panel import carica_giornate
    return carica_giornate()


@pytest.fixture(scope="module")
def stagioni(giornate):
    from ingest.panel import pannello_stagioni
    return pannello_stagioni(giornate)


def test_fantavoto_del_pannello_coincide_col_motore(giornate):
    campione = giornate.sample(3000, random_state=0)
    for r in campione.itertuples():
        p = Prestazione(ruolo=r.ruolo, voto=None if np.isnan(r.voto) else r.voto,
                        gf=r.gf, gs=r.gs, rp=r.rp, rf=r.rf, rs=r.rs, au=r.au,
                        amm=r.amm, esp=r.esp, ass=r.ass)
        atteso = fantavoto(p)
        assert (np.isnan(r.fv) if atteso is None else abs(atteso - r.fv) < 1e-9)


def test_senza_voto_non_produce_bonus(giornate):
    sv = giornate[giornate.voto.isna()]
    assert sv[["c_azione", "c_rigore", "c_malus", "c_port", "fv"]].isna().all().all()


def test_presenze_coincidono_con_le_statistiche(stagioni):
    from ingest.fonti import carica_statistiche
    st = carica_statistiche()
    m = stagioni.merge(st[["stagione", "Id", "Pv"]], on=["stagione", "Id"])
    # residui noti e classificati in tests/test_aggregazione.py (pattern A e B)
    assert (m.pv == m.Pv).mean() > 0.99


def test_tesserati_senza_presenze_inclusi(stagioni):
    zeri = stagioni.groupby("stagione").pv.apply(lambda s: (s == 0).mean())
    # ~17-19% per stagione (docs/DATI.md §2): non devono sparire
    assert zeri.between(0.15, 0.22).all()


def test_nomi_squadra_riconciliati():
    from ingest.fonti import carica_partite, carica_statistiche, verifica_nomi_squadra
    verifica_nomi_squadra(carica_partite(), carica_statistiche())


def test_listone_canonico():
    from ingest.fonti import carica_listone
    lst = carica_listone()
    assert len(lst) == 509 and lst.Id.is_unique
    assert lst.ruolo.value_counts().to_dict().keys() <= {"P", "D", "C", "A"}
