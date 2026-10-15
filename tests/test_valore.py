"""Dal valore al prezzo (value/valore.py): monte esatto, tasso unico, funzione
sostituibile. Casi sintetici: niente dati."""
import numpy as np
import pandas as pd

from rules import LEGA
from value.valore import (livelli_rimpiazzo, prezzi, rango_titolari,
                          valore_per_presenza, valore_punti_totali)


def _proiezioni(seme=0):
    rng = np.random.default_rng(seme)
    righe = []
    for r, n in {"P": 60, "D": 180, "C": 180, "A": 90}.items():
        p = rng.uniform(0.05, 0.95, n)
        fm = rng.normal({"P": 5.3, "D": 6.0, "C": 6.2, "A": 6.5}[r], 0.4, n)
        righe.append(pd.DataFrame(dict(ruolo=r, p_voto=p, pv_proj=36 * p,
                                       fm_base=fm, punti_proj=36 * p * fm)))
    return pd.concat(righe, ignore_index=True)


def test_rango_su_titolari_non_slot():
    assert [rango_titolari(r) for r in "PDCA"] == [8, 28, 28, 24]


def test_monte_esatto_sulle_rose():
    d = _proiezioni()
    v = valore_per_presenza(d)
    pr = prezzi(d, v)
    tot = sum(pr[d.ruolo == r].nlargest(s * LEGA.squadre).sum()
              for r, s in LEGA.rosa.slot.items())
    assert abs(tot - LEGA.monte_crediti) < 1e-6
    assert (pr >= 1).all()


def test_un_solo_tasso_per_tutti_i_ruoli():
    d = _proiezioni()
    v = valore_per_presenza(d)
    pr = prezzi(d, v)
    tasso = ((pr - 1) / v)[v > 0]
    assert tasso.max() - tasso.min() < 1e-9


def test_valore_per_presenza_non_premia_chi_gioca_tanto_da_riserva():
    d = _proiezioni()
    liv = livelli_rimpiazzo(d)
    # un titolare fisso che rende esattamente come il panchinaro tipo vale 0
    riga = pd.DataFrame(dict(ruolo=["D"], p_voto=[0.95], pv_proj=[34.2],
                             fm_base=[liv.fm_rimpiazzo["D"]],
                             punti_proj=[34.2 * liv.fm_rimpiazzo["D"]]))
    d2 = pd.concat([d, riga], ignore_index=True)
    assert valore_per_presenza(d2).iloc[-1] < 0.5
    # con la vecchia definizione sui punti totali avrebbe valore pieno
    assert valore_punti_totali(d2).iloc[-1] > 0


def test_funzione_sostituibile():
    import value.valore as vv
    assert hasattr(vv, "FunzioneValore")          # firma pubblica (§7.1)
    d = _proiezioni()
    zero = pd.Series(0.0, index=d.index)
    assert (prezzi(d, zero) == 1).all()
