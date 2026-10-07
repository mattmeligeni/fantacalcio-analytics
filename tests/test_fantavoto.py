"""Test unitari del motore di regolamento puro (rules/fantavoto.py).

Casi noti, deterministici, indipendenti dai dati. Verificano la formula,
la convenzione sui rigori (gol = gf + rf), l'imbattibilita' e il senza voto.
"""
import dataclasses

from rules import (
    LEGA,
    Prestazione,
    bonus_netti,
    da_voto_testuale,
    fantavoto,
    imbattibile,
    reti_da_punti,
)

LEGA_NO_IMB = dataclasses.replace(
    LEGA, bonus=dataclasses.replace(LEGA.bonus, imbattibilita=0.0))


# --- interpretazione del voto testuale ------------------------------------ #
def test_voto_testuale():
    assert da_voto_testuale("6.5") == 6.5
    assert da_voto_testuale("6,5") == 6.5      # virgola decimale
    assert da_voto_testuale("6*") is None      # senza voto
    assert da_voto_testuale("") is None
    assert da_voto_testuale(None) is None


# --- casi base ------------------------------------------------------------ #
def test_voto_secco_senza_eventi():
    p = Prestazione(ruolo="C", voto=6.0)
    assert fantavoto(p) == 6.0


def test_gol_su_azione():
    # attaccante voto 7 + 1 gol su azione = 10
    p = Prestazione(ruolo="A", voto=7.0, gf=1)
    assert fantavoto(p) == 10.0


def test_gol_su_rigore_vale_come_gol():
    # rigore segnato: gf=0, rf=1 -> comunque +3
    p = Prestazione(ruolo="A", voto=6.0, gf=0, rf=1)
    assert fantavoto(p) == 9.0


def test_rigore_sbagliato():
    # rigore sbagliato: -3 netti (Rs == R-)
    p = Prestazione(ruolo="A", voto=6.0, rs=1)
    assert fantavoto(p) == 3.0


def test_rigore_segnato_e_sbagliato_nella_stessa_gara():
    # uno segnato (+3) e uno sbagliato (-3) -> voto invariato
    p = Prestazione(ruolo="A", voto=6.5, rf=1, rs=1)
    assert fantavoto(p) == 6.5


def test_ammonizione_ed_espulsione():
    p = Prestazione(ruolo="D", voto=6.0, amm=1)
    assert fantavoto(p) == 5.5
    p = Prestazione(ruolo="D", voto=6.0, esp=1)
    assert fantavoto(p) == 5.0


def test_assist_e_autogol():
    assert fantavoto(Prestazione(ruolo="C", voto=6.0, ass=1)) == 7.0
    assert fantavoto(Prestazione(ruolo="D", voto=6.0, au=1)) == 4.0


# --- portiere e imbattibilita' -------------------------------------------- #
def test_imbattibilita_attiva():
    # portiere voto 6, 0 gol subiti -> +1 di imbattibilita'
    p = Prestazione(ruolo="P", voto=6.0, gs=0)
    assert imbattibile(p) is True
    assert fantavoto(p) == 7.0
    # senza il bonus (come le Statistiche stagionali)
    assert fantavoto(p, LEGA_NO_IMB) == 6.0


def test_portiere_battuto_no_imbattibilita():
    p = Prestazione(ruolo="P", voto=6.0, gs=2)
    assert imbattibile(p) is False
    assert fantavoto(p) == 4.0     # 6 - 2 gol subiti


def test_solo_il_portiere_prende_imbattibilita():
    # un difensore con gs=0 non e' "imbattibile": il campo gs vale solo per P
    d = Prestazione(ruolo="D", voto=6.0, gs=0)
    assert imbattibile(d) is False
    assert fantavoto(d) == 6.0


def test_rigore_parato():
    p = Prestazione(ruolo="P", voto=6.0, gs=0, rp=1)
    # 6 + 3 (rigore parato) + 1 (imbattibilita') = 10
    assert fantavoto(p) == 10.0


# --- senza voto ----------------------------------------------------------- #
def test_senza_voto_non_produce_fantavoto():
    p = Prestazione(ruolo="A", voto=None, gf=1)
    assert fantavoto(p) is None
    assert p.ha_voto is False


# --- bonus_netti separato dal voto ---------------------------------------- #
def test_bonus_netti_escludono_il_voto():
    p = Prestazione(ruolo="A", voto=7.0, gf=1, ass=1)
    assert bonus_netti(p) == 4.0   # 3 (gol) + 1 (assist)


# --- soglie gol ----------------------------------------------------------- #
def test_soglie_gol():
    assert reti_da_punti(65.9) == 0
    assert reti_da_punti(66.0) == 1
    assert reti_da_punti(71.9) == 1
    assert reti_da_punti(72.0) == 2     # 66 + 6
    assert reti_da_punti(78.0) == 3
    assert reti_da_punti(0.0) == 0
