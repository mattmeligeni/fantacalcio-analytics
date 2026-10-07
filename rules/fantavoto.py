"""Motore di regolamento PURO: dal voto in pagella + eventi al fantavoto.

Questo e' l'unico modulo in cui un errore resta silenzioso e contamina tutto il
resto (docs/METODO.md §7). E' deterministico, senza dipendenze da `models/`, e
testabile in isolamento. Non legge file: opera su strutture gia' parse.

Formula validata sulle 6 stagioni (docs/METODO.md §6.1, errore medio 0,0062):

    Fm = Mv + (3·Gf − Gs + 3·Rp + Ass − 0,5·Amm − Esp − 2·Au − 3·R−) / Pv

Qui la applichiamo per singola giornata-giocatore (denominatore 1), piu' il
bonus di imbattibilita' +1 attivo in questa lega (non presente nei file
Statistiche, va aggiunto dal motore).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .config import LEGA, LeagueRules

# Marcatore del "senza voto": e' sceso in campo ma non ha giocato abbastanza.
# Ai fini del gioco conta come ASSENZA e viene sostituito (docs/METODO.md §12,
# docs/DATI.md §1). La colonna Voto e' testo e contiene sia "6.5" sia "6*".
SENZA_VOTO = "6*"


@dataclass(frozen=True)
class Prestazione:
    """Riga giocatore × giornata, gia' normalizzata dai grezzi.

    `voto` e' None quando il giocatore e' senza voto (`6*`): in quel caso non
    produce fantavoto e la riga non conta come presenza.

    ATTENZIONE alla semantica dei gol, verificata con identita' esatte sulle 6
    stagioni (voti per giornata vs Statistiche stagionali, vedi test):
      - `gf` = gol SU AZIONE, rigori ESCLUSI  (colonna `Gf` del file voti)
      - `rf` = gol SU RIGORE                  (colonna `Rf`; == `R+` stagionale)
    Il totale di gol e' quindi `gf + rf`. Nel file Statistiche stagionale, al
    contrario, la colonna `Gf` include gia' i rigori: sono due convenzioni
    diverse (docs/DATI.md §2 vs §11.2). Il motore conta il gol una volta sola,
    su `gf + rf`.
    """
    ruolo: str
    voto: float | None
    gf: int = 0          # gol su AZIONE, rigori esclusi (colonna Gf voti)
    gs: int = 0          # gol subiti (portiere)
    rp: int = 0          # rigori parati
    rf: int = 0          # gol su rigore (colonna Rf voti; == R+ stagionale)
    rs: int = 0          # rigori sbagliati (colonna Rs voti; == R- stagionale)
    au: int = 0          # autogol
    amm: int = 0         # ammonizioni
    esp: int = 0         # espulsioni
    ass: int = 0         # assist

    @property
    def ha_voto(self) -> bool:
        return self.voto is not None


def da_voto_testuale(v) -> float | None:
    """Interpreta la colonna `Voto` testuale: numero -> float, `6*` -> None."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() == "nan":
        return None
    if "*" in s:                 # senza voto: 6*, e talvolta altri con asterisco
        return None
    return float(s.replace(",", "."))


def bonus_netti(p: Prestazione, lega: LeagueRules = LEGA) -> float:
    """Somma di bonus/malus della prestazione, imbattibilita' INCLUSA.

    Non include il voto in pagella: e' il termine `(Fm − Mv)` per la giornata.
    """
    b = lega.bonus
    tot = (
        b.gol_fatto * (p.gf + p.rf)      # gol su azione + gol su rigore
        + b.gol_subito * p.gs
        + b.rigore_parato * p.rp
        + b.rigore_sbagliato * p.rs      # rigori SBAGLIATI (rf sono i segnati)
        + b.assist * p.ass
        + b.ammonizione * p.amm
        + b.espulsione * p.esp
        + b.autogol * p.au
    )
    if imbattibile(p):
        tot += b.imbattibilita
    return tot


def imbattibile(p: Prestazione) -> bool:
    """Portiere imbattuto: ruolo P, ha voto reale, nessun gol subito.

    Va valutato solo su chi ha effettivamente giocato: un portiere senza voto
    non prende l'imbattibilita' (docs/METODO.md §6.3, docs/DATI.md §2 nota).
    """
    return p.ruolo == "P" and p.ha_voto and p.gs == 0


def fantavoto(p: Prestazione, lega: LeagueRules = LEGA) -> float | None:
    """Fantavoto della singola giornata, o None se il giocatore e' senza voto."""
    if not p.ha_voto:
        return None
    return round(p.voto + bonus_netti(p, lega), 2)


# --------------------------------------------------------------------------- #
# Soglie gol: dal punteggio totale di giornata di una squadra alle reti segnate.
# 66 la prima rete, poi una ogni 6 (docs/METODO.md §2).
# --------------------------------------------------------------------------- #
def reti_da_punti(punti: float, lega: LeagueRules = LEGA) -> int:
    """Numero di gol prodotti da un totale di fantapunti di squadra."""
    s = lega.soglie
    if punti < s.prima:
        return 0
    return 1 + int(math.floor((punti - s.prima) / s.passo))


def somma_fantavoti(prestazioni: list[Prestazione], lega: LeagueRules = LEGA) -> float:
    """Totale di fantapunti degli undici schierati (chi ha voto)."""
    return round(sum(fv for p in prestazioni
                     if (fv := fantavoto(p, lega)) is not None), 2)
