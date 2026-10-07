"""Punteggio della FORMAZIONE per giornata: somma dei fantavoti piu' i
modificatori. Puro e deterministico come il resto di `rules/`.

Perche' i modificatori stanno qui e non in `fantavoto.py`: non agiscono sul
fantavoto del singolo, agiscono sul punteggio della formazione. Il modificatore
difesa legge la media di portiere + i quattro migliori difensori; quello modulo
confronta l'assetto schierato con il 4-4-2. Sono quindi funzioni della `Lineup`,
non della singola `Prestazione`.

Questa lega NON ha modificatori (`LEGA.modificatori == ()`), quindi il punteggio
squadra e' la pura somma dei fantavoti. L'interfaccia esiste comunque adesso
perche' il retrofit successivo sarebbe costoso (vedi docs/METODO.md §7.1): con tupla
vuota tutto qui e' un no-op verificato da test.

NOTA: la logica di sostituzione hybrid (docs/METODO.md §3) e la composizione della
panchina vivranno in `inseason/`, che sceglie CHI schierare. Qui si assume la
formazione gia' decisa: si calcola solo il suo punteggio.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .config import LEGA, LeagueRules
from .fantavoto import Prestazione, fantavoto


@dataclass(frozen=True)
class Lineup:
    """Gli undici schierati di una squadra in una giornata, gia' decisi.

    Contiene le prestazioni dei titolari che hanno preso voto. La logica di
    sostituzione (subentri per i senza voto) e' a monte, in `inseason/`: qui
    arriva la formazione effettiva che ha totalizzato punti.
    """
    titolari: tuple[Prestazione, ...]

    def per_ruolo(self, ruolo: str) -> list[Prestazione]:
        return [p for p in self.titolari if p.ruolo == ruolo]

    def modulo(self) -> tuple[int, int, int]:
        """Assetto (D, C, A). Il portiere e' implicito."""
        return (len(self.per_ruolo("D")),
                len(self.per_ruolo("C")),
                len(self.per_ruolo("A")))


@runtime_checkable
class Modificatore(Protocol):
    """Un modificatore corregge il punteggio squadra leggendo la formazione.

    Firma unica: dato l'assetto e il punteggio corrente restituisce il nuovo
    punteggio. Si applicano in sequenza (l'output di uno e' l'input del
    successivo), quindi ognuno deve poter partire da un punteggio gia' corretto
    da quelli prima. Nessun modificatore concreto e' definito in questa lega.
    """
    def applica(self, formazione: Lineup, punti_base: float) -> float: ...


def punteggio_base(formazione: Lineup, lega: LeagueRules = LEGA) -> float:
    """Somma dei fantavoti degli undici schierati, senza modificatori."""
    return round(sum(fv for p in formazione.titolari
                     if (fv := fantavoto(p, lega)) is not None), 2)


def punteggio_squadra(formazione: Lineup, lega: LeagueRules = LEGA) -> float:
    """Punteggio finale: base, poi i modificatori in sequenza.

    Con `lega.modificatori == ()` (questa lega) equivale a `punteggio_base`:
    l'identita' e' verificata da test. E' il punto di aggancio per la difesa e
    il modulo, se un giorno si attivano.
    """
    punti = punteggio_base(formazione, lega)
    for mod in lega.modificatori:
        punti = mod.applica(formazione, punti)
    return round(punti, 2)
