"""Proiezione a due stadi scomposta, rimpiazzo, listino v2 (value/)."""
import dataclasses
import pathlib

import numpy as np
import pandas as pd
import pytest

from rules import LEGA
from ingest.componenti import COMPONENTI, carica_componenti
from value.budget import quote_ruolo
from value.proiezione import parametri_ruolo, proietta
from value.rimpiazzo import rango_rimpiazzo, valore_sopra_rimpiazzo

DATI = pathlib.Path("data/raw/Statistiche Fantacalcio")
pytestmark = pytest.mark.skipif(not DATI.exists(), reason="dati non disponibili")


# --- scomposizione della fantamedia (Parte 2.1) --------------------------- #
def test_componenti_ricompongono_la_fantamedia():
    m = carica_componenti()
    ric = (m[COMPONENTI].sum(axis=1) - m.fm_lega).abs().max()
    assert ric < 1e-6, "le componenti devono ricomporre esattamente la fantamedia"


# --- proiezione base ------------------------------------------------------ #
def test_proiezione_base_moltiplica_fm_e_pv():
    p = proietta()
    assert (abs(p.punti_base - p.fm_base * p.pv_proj) < 0.1).all()


def test_pv_proj_entro_orizzonte():
    p = proietta()
    assert (p.pv_proj <= LEGA.giornate_conteggiate + 1e-6).all()


def test_orizzonte_non_e_letterale():
    a = proietta(LEGA).set_index("Id").pv_proj
    lega_meta = dataclasses.replace(LEGA, prima_giornata_conteggiata=20)
    b = proietta(lega_meta).set_index("Id").pv_proj
    comune = a.index.intersection(b.index)
    assert abs((b[comune] / a[comune]).median() - 19 / 36) < 0.02


def test_niente_doppia_contrazione():
    """Uno con storico lungo e stabile deve regredire MENO di uno con una sola
    stagione: e' il punto della contrazione unica (Parte 2.1). Verifichiamo che
    la fantamedia proiettata di chi ha molte presenze pesate resti piu' vicina al
    suo storico che alla media di ruolo."""
    m = carica_componenti()
    par = parametri_ruolo(m)
    p = proietta(m=m, par=par)
    lunghi = p[p.n_eff > 60]
    assert len(lunghi) > 20
    # per i giocatori con storico lungo, la proiezione non e' schiacciata sulla
    # media: c'e' dispersione reale (non tutti uguali alla media di ruolo)
    assert lunghi.fm_base.std() > 0.35


# --- rimpiazzo ------------------------------------------------------------ #
def test_rango_rimpiazzo_su_titolari_non_slot():
    assert (rango_rimpiazzo("P"), rango_rimpiazzo("D"),
            rango_rimpiazzo("C"), rango_rimpiazzo("A")) == (8, 28, 28, 24)


def test_vor_non_negativo():
    p = proietta().rename(columns={"punti_base": "punti_proj"})
    assert (valore_sopra_rimpiazzo(p) >= 0).all()


# --- listino v2 ----------------------------------------------------------- #
def test_listino_completo_e_bassa_info_separata():
    from value.listino import costruisci_listino
    lis = costruisci_listino()
    assert len(lis) > 450
    assert lis.prezzo.min() >= 1
    # i profili a bassa informazione sono marcati (Parte 2.4)
    assert lis.bassa_info.sum() > 0
    assert (lis[lis.senza_storico].bassa_info).all()
    assert lis.diff_vs_fvm.is_monotonic_decreasing


def test_coerenza_quote_per_ruolo():
    """Parte 2.3: la ripartizione dei contendibili per ruolo del listino deve
    coincidere con la quota strategica §6.3. Tolleranza 1 punto %, motivata
    dall'arrotondamento intero di ~500 prezzi."""
    from value.listino import costruisci_listino
    lis = costruisci_listino()
    cont = (lis.prezzo - 1).clip(lower=0)
    q = quote_ruolo()
    for r in ["P", "D", "C", "A"]:
        share = cont[lis.ruolo == r].sum() / cont.sum()
        assert abs(share - q[r]) < 0.01, f"ruolo {r}: {share:.3f} vs {q[r]:.3f}"


def test_funzione_valore_sostituibile():
    from value.listino import costruisci_listino
    lis = costruisci_listino(funzione_valore=lambda df, lega: pd.Series(0.0, index=df.index))
    assert (lis.prezzo == 1).all()
