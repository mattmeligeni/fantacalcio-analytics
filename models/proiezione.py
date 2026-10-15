"""Proiezione dei punti sulle giornate conteggiate: il pezzo che unisce i modelli.

    punti = presenze proiettate × rendimento per presenza + punti dai rigori

  - presenze: models/disponibilita.py (logistica sulle aste storiche, con le
    prime giornate osservate);
  - rendimento per presenza: models/rendimento.py (voto, azione, malus con una
    sola contrazione calibrata fuori campione) e models/squadre.py (componente
    portiere dalla difesa della squadra);
  - rigori: models/rigori.py (status di rigorista × rigori della squadra).

`addestra` stima tutto SOLO sulle aste storiche precedenti a quella da
prevedere: per il listino 2026-27 su tutte e cinque le aste ricostruibili
(2021-22 → 2025-26), nel backtest su quelle prima della stagione di prova. Lo
stesso codice, la stessa garanzia anti-sbirciata.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ingest.panel import aggrega_voti
from models import disponibilita, rendimento, squadre
from models.istantanea import Istantanea, _stagione_precedente, da_storico
from models.rigori import proietta_rigori
from rules import LEGA, LeagueRules


@dataclass(frozen=True)
class ModelloProiezione:
    disponibilita: disponibilita.ModelloDisponibilita
    rendimento: rendimento.ModelloRendimento
    squadre: squadre.ModelloSquadre
    aste_addestramento: tuple[str, ...]


def realizzato(ist: Istantanea, giornate: pd.DataFrame,
               lega: LeagueRules = LEGA) -> pd.DataFrame:
    """Somme realizzate sulle giornate conteggiate dell'asta (solo backtest):
    presenze, punti (fantavoti) e famiglie di bonus, per Id."""
    prima, _ = disponibilita.giornate_conteggiate(ist, lega)
    g = giornate[(giornate.stagione == ist.stagione) & (giornate.giornata >= prima)]
    a = aggrega_voti(g).set_index("Id")
    a["punti"] = g.groupby("Id").fv.sum()
    return a


def aste_di_addestramento(ist: Istantanea) -> list[str]:
    """Stagioni storiche ricostruibili come asta: serve la stagione precedente
    (per le caratteristiche) e devono essere tutte anteriori all'asta."""
    st = ist.stagioni_storiche
    return [s for s in st if _stagione_precedente(s) in st]


def addestra(ist: Istantanea, giornate: pd.DataFrame, stagioni: pd.DataFrame,
             partite: pd.DataFrame, lega: LeagueRules = LEGA) -> ModelloProiezione:
    # le aste storiche vedono solo dati anteriori all'asta da prevedere
    giornate = giornate[giornate.stagione < ist.stagione]
    stagioni = stagioni[stagioni.stagione < ist.stagione]
    partite = partite[partite.stagione < ist.stagione]
    aste = aste_di_addestramento(ist)
    if not aste:
        raise ValueError(f"nessuna asta storica utilizzabile prima di {ist.stagione}")
    storiche = [da_storico(s, ist.giornata_asta, giornate, stagioni, partite) for s in aste]

    m_disp = disponibilita.addestra(
        [(s, disponibilita.etichette(s, giornate, lega)) for s in storiche])
    m_rend = rendimento.addestra(
        [(s, m_disp.prevedi(s), realizzato(s, giornate, lega)) for s in storiche],
        storico_prior=ist.storico)
    m_sq = squadre.addestra(ist)
    return ModelloProiezione(m_disp, m_rend, m_sq, tuple(aste))


def proietta(modello: ModelloProiezione, ist: Istantanea,
             lega: LeagueRules = LEGA) -> pd.DataFrame:
    """Proiezione per ogni giocatore dell'universo dell'asta (una riga per Id)."""
    _, n = disponibilita.giornate_conteggiate(ist, lega)
    U = ist.universo.set_index("Id")
    p = modello.disponibilita.prevedi(ist)
    R = modello.rendimento.prevedi(ist, p)
    T = modello.squadre.prevedi(ist)
    rig = proietta_rigori(ist, p, T.rig_pp, n, lega)

    out = U.copy()
    out["p_voto"] = p
    out["pv_proj"] = p * n
    out["fm_voto"] = R.voto
    out["fm_azione"] = R.azione
    out["fm_malus"] = R.malus
    # portieri: la componente portiere e' quella della difesa della squadra
    out["fm_port"] = np.where(out.ruolo == "P", out.squadra.map(T.port_pp), 0.0)
    out["fm_base"] = out[["fm_voto", "fm_azione", "fm_malus", "fm_port"]].sum(axis=1)
    out["rigori_attesi"] = rig.rigori_attesi
    out["punti_rigori"] = rig.punti_rigori
    out["punti_proj"] = out.pv_proj * out.fm_base + out.punti_rigori
    out["fm_proj"] = out.punti_proj / out.pv_proj.where(out.pv_proj > 0)
    out["n_eff"] = R.n_eff

    prec = _stagione_precedente(ist.stagione)
    h1 = ist.storico[ist.storico.stagione == prec].set_index("Id")
    out["senza_storico"] = out.n_eff <= 0
    out["cambio_club"] = out.index.isin(h1.index) & (out.index.map(h1.squadra) != out.squadra)
    out["neopromossa"] = out.squadra.map(T.neopromossa).astype(bool)
    return out.reset_index()
