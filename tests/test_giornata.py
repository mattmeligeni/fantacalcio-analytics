"""Punteggio squadra e predisposizione ai modificatori (rules/giornata.py)."""
import dataclasses

from rules import LEGA, Lineup, Prestazione, punteggio_base, punteggio_squadra
from rules.giornata import Modificatore


def _formazione_442() -> Lineup:
    p = [Prestazione(ruolo="P", voto=6.0, gs=0)]                    # 6 + 1 imb = 7
    d = [Prestazione(ruolo="D", voto=6.0) for _ in range(4)]       # 24
    c = [Prestazione(ruolo="C", voto=6.0) for _ in range(4)]       # 24
    a = [Prestazione(ruolo="A", voto=7.0, gf=1) for _ in range(2)] # 2*10 = 20
    return Lineup(titolari=tuple(p + d + c + a))


def test_modulo_e_conteggio_ruoli():
    f = _formazione_442()
    assert f.modulo() == (4, 4, 2)
    assert len(f.per_ruolo("P")) == 1


def test_punteggio_base_somma_i_fantavoti():
    f = _formazione_442()
    # 7 (portiere imbattuto) + 24 + 24 + 20 = 75
    assert punteggio_base(f) == 75.0


def test_nessun_modificatore_e_no_op():
    """Con LEGA.modificatori == () il punteggio squadra == punteggio base."""
    f = _formazione_442()
    assert LEGA.modificatori == ()
    assert punteggio_squadra(f) == punteggio_base(f)


def test_modificatori_applicati_in_sequenza():
    """Verifica il meccanismo di aggancio con modificatori fittizi, senza
    introdurne di concreti in LEGA: si costruisce una lega ad hoc."""
    class Aggiunge:
        def __init__(self, q): self.q = q
        def applica(self, formazione: Lineup, punti_base: float) -> float:
            return punti_base + self.q

    m1, m2 = Aggiunge(10), Aggiunge(5)
    assert isinstance(m1, Modificatore)          # rispetta il protocollo
    lega = dataclasses.replace(LEGA, modificatori=(m1, m2))
    f = _formazione_442()
    # base 75, poi +10, poi +5 = 90; e in sequenza, non commutato per caso
    assert punteggio_squadra(f, lega) == 90.0


def test_modificatore_legge_la_formazione():
    """Un modificatore puo' dipendere dall'assetto (come la difesa reale)."""
    class BonusSeQuattroDifensori:
        def applica(self, formazione: Lineup, punti_base: float) -> float:
            return punti_base + (3.0 if formazione.modulo()[0] >= 4 else 0.0)

    lega = dataclasses.replace(LEGA, modificatori=(BonusSeQuattroDifensori(),))
    assert punteggio_squadra(_formazione_442(), lega) == 78.0
