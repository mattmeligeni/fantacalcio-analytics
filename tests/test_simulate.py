"""Motore della lega simulata (simulate/lega.py) su casi giocattolo calcolabili
a mano: formazione settimanale, moduli, draft, valore marginale."""
import numpy as np

from simulate.lega import Settimane, draft, punteggio_rosa, rimpiazzi, valore_marginale


def _sett(ruoli, disp, punti, atteso=None):
    disp = np.asarray(disp, bool)
    punti = np.asarray(punti, float)
    atteso = punti.mean(axis=0) if atteso is None else np.asarray(atteso, float)
    return Settimane(ids=np.arange(len(ruoli)), ruolo=np.array(ruoli), disponibile=disp,
                     punti=punti, atteso=atteso, scala=1.0, media=False)


def _rosa_base():
    # 1 P, 5 D, 5 C, 3 A: un 3-4-3 o 4-4-2 sempre coperto
    return ["P"] + ["D"] * 5 + ["C"] * 5 + ["A"] * 3


def test_formazione_prende_il_modulo_migliore():
    ruoli = _rosa_base()
    punti = np.array([[6.0] + [6.0] * 5 + [6.0] * 5 + [9.0, 9.0, 9.0]])
    s = _sett(ruoli, np.ones_like(punti), punti)
    # con tre attaccanti da 9 conviene il 3-4-3: 6 + 3·6 + 4·6 + 3·9
    assert punteggio_rosa(s, np.arange(len(ruoli))) == 6 + 18 + 24 + 27


def test_slot_scoperto_vale_zero():
    ruoli = ["P", "D", "D", "D", "C", "C", "C", "C", "A", "A", "A"]
    punti = np.full((1, 11), 6.0)
    disp = np.ones((1, 11), bool)
    disp[0, 0] = False                          # il portiere non gioca
    s = _sett(ruoli, disp, punti)
    assert punteggio_rosa(s, np.arange(11)) == 60.0


def test_la_panchina_copre_le_assenze():
    # quattro difensori schierati, uno da 7 salta una settimana su due: entra
    # il quinto (6) dalla panchina e la squadra perde solo 1 punto
    ruoli = ["P"] + ["D"] * 5 + ["C"] * 4 + ["A"] * 2
    W = 4
    punti = np.full((W, 12), 6.0)
    punti[:, 1:3] = 7.0
    disp = np.ones((W, 12), bool)
    disp[::2, 1] = False
    s = _sett(ruoli, disp, punti, atteso=[6, 7, 7, 6, 6, 6, 6, 6, 6, 6, 6, 6])
    tot = punteggio_rosa(s, np.arange(12))
    pieno = 6 + (7 + 7 + 6 + 6) + 4 * 6 + 2 * 6   # 4-4-2 con tutti
    assert tot == W * pieno - 2 * 1               # 2 settimane: 6 al posto di 7


def test_senza_riserve_lo_slot_resta_vuoto():
    # solo 4 difensori, 4 centrocampisti, 2 attaccanti: se un difensore manca
    # nessun modulo ammesso e' completo e uno slot vale 0 (si gioca in dieci)
    ruoli = ["P"] + ["D"] * 4 + ["C"] * 4 + ["A"] * 2
    punti = np.full((1, 11), 7.0)
    disp = np.ones((1, 11), bool)
    disp[0, 1] = False
    s = _sett(ruoli, disp, punti)
    assert punteggio_rosa(s, np.arange(11)) == 70.0


def test_draft_rispetta_gli_slot():
    from rules import LEGA
    rng = np.random.default_rng(0)
    ruoli = np.array(["P"] * 40 + ["D"] * 100 + ["C"] * 100 + ["A"] * 70)
    rose = draft(rng.random(len(ruoli)), ruoli)
    assert len(rose) == LEGA.squadre
    for r in rose:
        conta = {k: int((ruoli[r] == k).sum()) for k in "PDCA"}
        assert conta == LEGA.rosa.slot
    assert len(set(np.concatenate(rose))) == LEGA.squadre * 25


def test_valore_marginale_del_rimpiazzo_e_di_chi_non_gioca():
    rng = np.random.default_rng(1)
    ruoli = np.array(["P"] * 40 + ["D"] * 100 + ["C"] * 100 + ["A"] * 70)
    N, W = len(ruoli), 300
    p = rng.uniform(0.2, 0.95, N)
    fm = rng.normal(6.2, 0.4, N)
    fm[-1] = 0.0                                  # attaccante che non segna mai
    p[-1] = 0.0                                   # e non gioca mai
    disp = rng.random((W, N)) < p
    s = Settimane(ids=np.arange(N), ruolo=ruoli, disponibile=disp,
                  punti=np.broadcast_to(fm, (W, N)), atteso=fm, scala=36.0, media=True)
    val = fm * p
    rose = draft(val, ruoli)
    fa = rimpiazzi(val, ruoli, rose)
    v = valore_marginale(s, rose, fa)
    assert all(v[fa[r]] == 0.0 for r in "PDCA")
    assert abs(v[-1]) < 1e-9 or v[-1] <= 0
    assert v.max() > 0
