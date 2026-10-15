"""Grandezze di SQUADRA proiettate: difesa (per i portieri) e rigori a partita.

Portieri. La componente portiere del fantavoto (−1 a gol subito, +3 a rigore
parato, +1 di imbattibilita') e' quasi tutta forza difensiva della squadra, non
merito del portiere (docs/METODO.md §6.6: gol subiti per presenza r = 0,56,
"il portiere si sceglie guardando la difesa davanti a lui"). Qui si proietta
direttamente la componente portiere per partita di ogni squadra dagli xG
concessi la stagione prima:

    port_squadra(t) = a + b · xGA_per_partita(t−1)        [squadre gia' in A]
    port_squadra(t) = media delle neopromosse storiche    [neopromosse]

L'xG Understat NON si usa grezzo: per ogni stagione si riscala in modo che il
totale di lega eguagli i gol segnati (docs/METODO.md §5). Il fattore non e'
costante (1,02 nel 2020-21, 0,87 nel 2025-26): usare l'xG grezzo avrebbe
introdotto una deriva proprio sulla grandezza dei portieri. Misurato fuori
campione, l'xGA riscalato prevede la componente portiere meglio dei gol subiti
e molto meglio della media (errore 0,12 contro 0,135 e 0,19).

Stagione in corso. Le partite gia' giocate (Understat, o lo storico nel
backtest) aggiornano la stima della difesa con un peso proporzionale alle
partite: port = (k·prior + n·port_osservato) / (k + n), con k stimato fuori
campione sulle stagioni passate tagliate alla stessa giornata.

Rigori. I rigori a favore di una squadra persistono poco (pendenza 0,32 fra
stagioni consecutive): si contraggono forte verso la media di lega (~0,16 a
partita), con la pendenza stimata sulle stagioni di addestramento.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from models.istantanea import Istantanea, _stagione_precedente


def tabella_squadre(partite: pd.DataFrame) -> pd.DataFrame:
    """Squadra × stagione: gol e xG (riscalato ai gol della stagione) a partita."""
    L = pd.concat([
        partite.assign(squadra=partite.casa, gf=partite.gol_casa, ga=partite.gol_ospite,
                       xgf=partite.xg_casa, xga=partite.xg_ospite),
        partite.assign(squadra=partite.ospite, gf=partite.gol_ospite, ga=partite.gol_casa,
                       xgf=partite.xg_ospite, xga=partite.xg_casa),
    ])
    scala = L.groupby("stagione").apply(lambda d: d.ga.sum() / d.xga.sum(),
                                        include_groups=False)
    L["xga_r"] = L.xga * L.stagione.map(scala)
    L["xgf_r"] = L.xgf * L.stagione.map(scala)
    T = L.groupby(["stagione", "squadra"]).agg(
        gf=("gf", "mean"), ga=("ga", "mean"),
        xgf=("xgf_r", "mean"), xga=("xga_r", "mean"), partite=("ga", "size"))
    return T.reset_index()


def componente_portiere_squadra(giornate: pd.DataFrame) -> pd.DataFrame:
    """Componente portiere realizzata per partita di portiere, squadra × stagione."""
    gk = giornate[(giornate.ruolo == "P") & giornate.voto.notna()]
    return (gk.groupby(["stagione", "squadra"]).c_port.mean()
              .rename("port").reset_index())


def rigori_squadra(giornate: pd.DataFrame) -> pd.DataFrame:
    """Rigori calciati a favore per partita, squadra × stagione."""
    rc = (giornate.assign(rc=giornate.rf + giornate.rs)
          .groupby(["stagione", "squadra"]).agg(rc=("rc", "sum"),
                                                g=("giornata", "nunique")))
    return (rc.rc / rc.g).rename("rig_pp").reset_index()


@dataclass(frozen=True)
class ModelloSquadre:
    a_port: float
    b_port: float
    port_neopromosse: float
    rig_media: float
    rig_pendenza: float
    k_osservate: float = 1e9          # peso del prior in partite (inf = ignora)

    def port_osservato(self, partite: pd.DataFrame | None) -> pd.DataFrame:
        """Componente portiere implicita nelle partite gia' giocate, per squadra."""
        if partite is None or partite.empty:
            return pd.DataFrame(columns=["port", "n"])
        T = tabella_squadre(partite)
        return pd.DataFrame({"squadra": T.squadra, "port": self.a_port + self.b_port * T.xga,
                             "n": T.partite}).set_index("squadra")

    def prevedi(self, ist: Istantanea) -> pd.DataFrame:
        """Per ogni squadra dell'asta: componente portiere e rigori a partita."""
        prec = _stagione_precedente(ist.stagione)
        T = tabella_squadre(ist.partite)
        T1 = T[T.stagione == prec].set_index("squadra")
        R = rigori_squadra(ist.giornate_storiche)
        R1 = R[R.stagione == prec].set_index("squadra")
        oss = self.port_osservato(ist.partite_osservate)
        righe = []
        for sq in ist.squadre:
            neo = sq not in T1.index
            port = (self.port_neopromosse if neo
                    else self.a_port + self.b_port * float(T1.loc[sq, "xga"]))
            if sq in oss.index:
                n = float(oss.loc[sq, "n"])
                port = (self.k_osservate * port + n * float(oss.loc[sq, "port"])) / (self.k_osservate + n)
            rig1 = R1.rig_pp.get(sq, np.nan)
            rig = self.rig_media + (0.0 if np.isnan(rig1)
                                    else self.rig_pendenza * (rig1 - self.rig_media))
            righe.append(dict(squadra=sq, neopromossa=neo, port_pp=port, rig_pp=rig,
                              xga_prec=np.nan if neo else float(T1.loc[sq, "xga"])))
        return pd.DataFrame(righe).set_index("squadra")


def addestra(ist: Istantanea) -> ModelloSquadre:
    """Stima sulle transizioni fra stagioni consecutive dello storico dell'asta
    (solo stagioni passate rispetto all'asta)."""
    T = tabella_squadre(ist.partite)
    port = componente_portiere_squadra(ist.giornate_storiche)
    rig = rigori_squadra(ist.giornate_storiche)
    stagioni = sorted(T.stagione.unique())
    x, y, neo, r0, r1 = [], [], [], [], []
    for s0, s1 in zip(stagioni, stagioni[1:]):
        prima = T[T.stagione == s0].set_index("squadra")
        dopo = port[port.stagione == s1].set_index("squadra")
        rp = rig[rig.stagione == s0].set_index("squadra")
        rd = rig[rig.stagione == s1].set_index("squadra")
        for sq in dopo.index:
            if sq in prima.index:
                x.append(prima.loc[sq, "xga"])
                y.append(dopo.loc[sq, "port"])
            else:
                neo.append(dopo.loc[sq, "port"])
            if sq in rp.index:
                r0.append(rp.loc[sq, "rig_pp"])
                r1.append(rd.loc[sq, "rig_pp"])
    if len(x) < 10:
        raise ValueError("storico insufficiente per il modello di squadra")
    b, a = np.polyfit(x, y, 1)
    rig_media = float(rig.rig_pp.mean())
    pend = float(np.polyfit(np.array(r0) - rig_media, np.array(r1) - rig_media, 1)[0])
    m = ModelloSquadre(
        a_port=float(a), b_port=float(b),
        port_neopromosse=float(np.mean(neo)) if neo else float(np.mean(y)),
        rig_media=rig_media, rig_pendenza=float(np.clip(pend, 0.0, 1.0)))
    if ist.giornata_asta <= 0:
        return m
    return _stima_k_osservate(m, ist)


GRIGLIA_K_OSS = (2.0, 4.0, 6.0, 10.0, 15.0, 20.0, 30.0, 50.0, 1e9)


def _stima_k_osservate(m: ModelloSquadre, ist: Istantanea) -> ModelloSquadre:
    """Peso delle partite gia' giocate: per ogni stagione passata si taglia alla
    giornata dell'asta, si fonde e si confronta col resto della stagione."""
    from dataclasses import replace
    g0 = ist.giornata_asta
    T = tabella_squadre(ist.partite)
    G = ist.giornate_storiche
    stagioni = sorted(T.stagione.unique())
    righe = []
    for s0, s1 in zip(stagioni, stagioni[1:]):
        prima = T[T.stagione == s0].set_index("squadra")
        oss = m.port_osservato(ist.partite[(ist.partite.stagione == s1)
                                           & (ist.partite.giornata <= g0)])
        dopo = componente_portiere_squadra(G[(G.stagione == s1) & (G.giornata > g0)]).set_index("squadra")
        for sq in dopo.index:
            prior = (m.a_port + m.b_port * prima.loc[sq, "xga"]) if sq in prima.index else m.port_neopromosse
            if sq in oss.index:
                righe.append((prior, oss.loc[sq, "port"], oss.loc[sq, "n"], dopo.loc[sq, "port"]))
    if not righe:
        return m
    d = np.array(righe, dtype=float)
    err = {k: float(np.mean(((k * d[:, 0] + d[:, 2] * d[:, 1]) / (k + d[:, 2]) - d[:, 3]) ** 2))
           for k in GRIGLIA_K_OSS}
    return replace(m, k_osservate=min(err, key=err.get))
