"""Modelli di proiezione: invarianti strutturali sull'asta 2025-26 ricostruita.

Non verificano QUANTO sono buone le previsioni (lo fa tests/test_backtest.py),
ma che siano coerenti: probabilita' valide, portieri entro il tetto di squadra,
xG ancorato ai gol, quote rigoristi sensate, nessun valore mancante.
"""
import pathlib

import numpy as np
import pytest

DATI = pathlib.Path("data/raw/Voti")
pytestmark = pytest.mark.skipif(not DATI.exists(), reason="dati non disponibili")


@pytest.fixture(scope="module")
def ctx():
    from ingest.fonti import carica_partite
    from ingest.panel import carica_giornate, pannello_stagioni
    from models import proiezione as pj
    from models.istantanea import da_storico
    g = carica_giornate()
    S = pannello_stagioni(g)
    P = carica_partite()
    ist = da_storico("2025-26", 2, g, S, P)
    m = pj.addestra(ist, g, S, P)
    return ist, m, pj.proietta(m, ist)


def test_addestramento_solo_su_aste_passate(ctx):
    _, m, _ = ctx
    assert m.aste_addestramento == ("2021-22", "2022-23", "2023-24", "2024-25")


def test_proiezione_completa_e_finita(ctx):
    ist, _, out = ctx
    assert len(out) == len(ist.universo)
    cols = ["p_voto", "pv_proj", "fm_base", "punti_proj", "punti_rigori"]
    assert np.isfinite(out[cols].values).all()
    assert out.p_voto.between(0, 1).all()
    assert (out.pv_proj <= 36 + 1e-9).all()


def test_portieri_entro_il_tetto_di_squadra(ctx):
    _, m, out = ctx
    somma = out[out.ruolo == "P"].groupby("squadra").p_voto.sum()
    assert (somma <= m.disponibilita.capienza["P"] + 1e-9).all()


def test_le_giornate_osservate_contano(ctx):
    _, m, _ = ctx
    tab = m.disponibilita.tabella_coefficienti()
    assert (tab.loc["oss_voto"] > 0.5).all()


def test_xg_ancorato_ai_gol():
    from ingest.fonti import carica_partite
    from models.squadre import tabella_squadre
    T = tabella_squadre(carica_partite())
    tot = T.assign(g=T.ga * T.partite, x=T.xga * T.partite).groupby("stagione")[["g", "x"]].sum()
    assert np.allclose(tot.g, tot.x)


def test_difesa_migliore_componente_portiere_migliore(ctx):
    _, m, _ = ctx
    assert m.squadre.b_port < 0                    # piu' xG concessi, peggio il portiere
    assert m.squadre.port_neopromosse < m.squadre.a_port + m.squadre.b_port * 1.3


def test_quote_rigoristi(ctx):
    ist, _, out = ctx
    from models.rigori import quote_rigoristi
    q = quote_rigoristi(ist)
    assert q.quota.between(0, 1).all()
    assert (out.rigori_attesi >= 0).all()
    carico = out.assign(q=out.rigori_attesi).groupby("squadra").q.sum()
    assert (carico <= 0.25 * 36 + 1e-9).all()     # mai piu' rigori di quelli di squadra
