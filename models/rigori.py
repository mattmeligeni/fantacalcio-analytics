"""Rigoristi: si prevede lo STATUS (chi li calcia), non la precisione.

Misurato (docs/METODO.md §6.8): la conversione individuale non persiste
(pendenza 0,12) e va contratta forte verso la media di lega; essere il
rigorista vale ~9 punti a stagione, convertire meglio ~1,5. Qui lo status si
misura in modo piu' fine della versione precedente, dai voti per giornata:

    quota = rigori calciati dal giocatore
            / rigori calciati dalla sua squadra NELLE PARTITE IN CUI ERA IN CAMPO

pesati per decadimento delle stagioni, contratti verso zero con uno pseudo-
conteggio (un rigore su un rigore non fa un rigorista). Lo status maturato in
un ALTRO club vale solo una frazione (lo si perde cambiando squadra: chi resta
fa in media 2,59 rigori l'anno dopo, chi cambia 0,76). Le prime giornate
osservate prima dell'asta entrano con peso pieno: chi ha calciato un rigore
alla 1ª con il nuovo club e' un segnale vero di status.

Rigori attesi = rigori a partita della squadra × quota × presenze proiettate.
In una squadra le quote si normalizzano in modo che la somma pesata per la
disponibilita' non superi 1 (un solo rigorista per rigore).

Fuori campione (aste 2022-23 → 2025-26) la correlazione fra rigori previsti e
calciati sale da 0,50 (volume storico + fattore di cambio club) a ~0,62.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.istantanea import Istantanea
from models.rendimento import pesi_stagione
from rules import LEGA, LeagueRules

PSEUDO_RIGORI = 1.5          # contrazione verso "non rigorista", in rigori di squadra
PESO_ALTRO_CLUB = 0.15       # frazione di status che si porta in un club nuovo
PERSISTENZA_CONVERSIONE = 0.12


def conversione_lega(giornate: pd.DataFrame) -> float:
    """Conversione media di lega (gol su rigore / rigori calciati)."""
    return float(giornate.rf.sum() / (giornate.rf.sum() + giornate.rs.sum()))


def valore_rigore(conversione, lega: LeagueRules = LEGA):
    """Punti attesi per rigore calciato: +3 se segnato, −3 se sbagliato (pesi
    da `lega.bonus`, nessuna costante qui)."""
    b = lega.bonus
    return conversione * b.gol_fatto + (1 - conversione) * b.rigore_sbagliato


def quote_rigoristi(ist: Istantanea, pseudo: float = PSEUDO_RIGORI,
                    peso_altro: float = PESO_ALTRO_CLUB) -> pd.DataFrame:
    """Quota di status per ogni Id dell'universo, piu' la conversione contratta."""
    G = pd.concat([ist.giornate_storiche, ist.osservate], ignore_index=True)
    G = G.assign(rc=G.rf + G.rs)
    rig_partita = G.groupby(["stagione", "giornata", "squadra"]).rc.sum().rename("rc_sq")
    G = G.join(rig_partita, on=["stagione", "giornata", "squadra"])
    G = G[G.voto.notna() & G.Id.isin(ist.universo.Id)]

    w = pesi_stagione(list(ist.storico.stagione.unique()))
    w[ist.stagione] = 1.0                     # giornate osservate: peso pieno
    G = G.assign(w=G.stagione.map(w))
    club_ora = ist.universo.set_index("Id").squadra
    stesso = G.squadra.values == G.Id.map(club_ora).values

    out = pd.DataFrame(index=ist.universo.Id)
    for nome, m in (("club", stesso), ("altro", ~stesso)):
        x = G[m]
        out[f"rc_{nome}"] = (x.w * x.rc).groupby(x.Id).sum()
        out[f"sq_{nome}"] = (x.w * x.rc_sq).groupby(x.Id).sum()
    out = out.fillna(0.0)
    # stagione in corso nota solo come aggregato (Statistiche): i rigori della
    # squadra "con lui in campo" si approssimano con quelli di tutta la squadra
    # × la sua quota di presenze. Peso pieno, come le giornate osservate.
    if ist.osservate.empty and ist.osservato is not None and len(ist.osservato):
        o = ist.osservato.set_index("Id")
        g0 = max(ist.giornata_asta, 1)
        rc_sq = o.groupby("squadra").rc.sum()
        stesso_o = o.squadra.reindex(out.index) == club_ora.reindex(out.index)
        rc_o = o.rc.reindex(out.index).fillna(0)
        sq_o = (o.squadra.map(rc_sq) * o.pv / g0).reindex(out.index).fillna(0)
        out.loc[stesso_o, "rc_club"] += rc_o[stesso_o]
        out.loc[stesso_o, "sq_club"] += sq_o[stesso_o]
    out["quota"] = ((out.rc_club + peso_altro * out.rc_altro)
                    / (out.sq_club + peso_altro * out.sq_altro + pseudo))

    p0 = conversione_lega(G)
    seg = G.groupby("Id").rf.sum().reindex(out.index).fillna(0)
    cal = G.groupby("Id").rc.sum().reindex(out.index).fillna(0)
    ind = np.where(cal > 0, seg / cal.replace(0, np.nan), p0)
    out["conversione"] = p0 + PERSISTENZA_CONVERSIONE * (ind - p0)
    out["calciati_storici"] = cal
    return out


def proietta_rigori(ist: Istantanea, p_proj: pd.Series, rig_squadra: pd.Series,
                    n_giornate: int, lega: LeagueRules = LEGA) -> pd.DataFrame:
    """Rigori attesi e punti attesi dai rigori sulle giornate conteggiate.

    `p_proj`: probabilita' di prendere voto per giornata (Id); `rig_squadra`:
    rigori a favore a partita proiettati per squadra.
    """
    q = quote_rigoristi(ist)
    U = ist.universo.set_index("Id")
    d = q.join(U[["squadra"]])
    d["p"] = p_proj.reindex(d.index).fillna(0.0)
    # un solo rigorista per rigore: se la somma delle quote pesate per la
    # disponibilita' supera 1 nella squadra, si riscalano
    carico = (d.quota * d.p).groupby(d.squadra).transform("sum")
    d["quota"] = d.quota / np.maximum(carico, 1.0)
    d["rigori_attesi"] = d.squadra.map(rig_squadra) * d.quota * d.p * n_giornate
    d["punti_rigori"] = d.rigori_attesi * valore_rigore(d.conversione, lega)
    return d[["quota", "conversione", "calciati_storici", "rigori_attesi", "punti_rigori"]]
