"""Formazione consigliata e svincoli (inseason/formazione.py)."""
import pandas as pd

from inseason.formazione import formazione, svincoli


def _rosa():
    righe, i = [], 0
    for r, n, fm in [("P", 3, 5.5), ("D", 8, 6.0), ("C", 8, 6.2), ("A", 6, 6.8)]:
        for k in range(n):
            i += 1
            righe.append(dict(Id=i, Nome=f"{r}{k}", ruolo=r, squadra="X", p_voto=0.9 - 0.1 * k,
                              fm_proj=fm, fm_base=fm, valore=10 - k, punti_proj=150 - 10 * k))
    return pd.DataFrame(righe)


def test_formazione_completa_con_modulo_ammesso():
    from rules import LEGA
    f = formazione(_rosa())
    d, c, a = (int(x) for x in f["modulo"].split("-"))
    assert (d, c, a) in LEGA.moduli
    assert len(f["titolari"]) == 11 and len(f["panchina"]) == 14


def test_indisponibile_va_in_panchina():
    r = _rosa()
    stella = r[r.ruolo == "A"].Id.iloc[0]
    f = formazione(r, {stella})
    assert stella not in set(f["titolari"].Id)


def test_panchina_ordinata_dentro_il_ruolo():
    f = formazione(_rosa())
    for _, g in f["panchina"].groupby("ruolo", sort=False):
        assert g.attesi.is_monotonic_decreasing


def test_svincoli_solo_guadagni_veri():
    r = _rosa()
    liberi = pd.DataFrame([
        dict(Id=100, Nome="buono", ruolo="D", squadra="Y", valore=5.0, punti_proj=140),
        dict(Id=101, Nome="inutile", ruolo="D", squadra="Y", valore=3.4, punti_proj=60),
    ])
    sv = svincoli(r, liberi)
    assert list(sv.prendi) == ["buono"]                 # peggiore D vale 3: +2 si', +0.4 no
