"""La stagione in corso: cosa si e' gia' visto, nel formato che usano i modelli.

Due fonti, entrambe opzionali:
  - Fantacalcio.it: se ci sono i voti per giornata (data/raw/Voti/AA-AA/) si
    usano quelli; altrimenti lo snapshot piu' recente delle Statistiche
    (data/raw/Stagione in corso/), che e' un aggregato: si ricostruiscono le
    stesse somme per giocatore che `ingest.panel.aggrega_voti` produce dai voti.
  - Understat: partite giocate (gol e xG di squadra) e minuti per giocatore.

Limiti dell'aggregato (dichiarati): non conta gli ingressi senza voto (`6*`) e
non dice quali portieri sono rimasti imbattuti; i modelli non ne dipendono (la
componente portiere viene dalla difesa di squadra).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ingest import importa
from ingest.fonti import SQUADRE_UNDERSTAT
from ingest.panel import FAMIGLIE, aggrega_voti
from rules import LEGA, LeagueRules


@dataclass(frozen=True)
class StagioneInCorso:
    stagione: str
    giornata: int                    # ultima giornata giocata
    osservato: pd.DataFrame          # somme per Id (formato aggrega_voti) + squadra, ruolo
    partite: pd.DataFrame            # formato ingest.fonti.carica_partite, giocate
    minuti: pd.DataFrame | None      # Understat giocatore × partita (minuti)
    fonte: str


def osservato_da_statistiche(stat: pd.DataFrame, lega: LeagueRules = LEGA) -> pd.DataFrame:
    """Statistiche (foglio Tutti) della stagione in corso -> somme per Id.

    Convenzione verificata (docs/DATI.md §2): `Gf` delle Statistiche INCLUDE i
    rigori, `R+`/`R-` sono i rigori segnati/sbagliati; quindi gol su azione =
    Gf − R+. `Amm` puo' contare cartellini in gare senza voto (scarto di
    multipli di 0,5 sul malus: trascurabile su poche giornate).
    """
    b = lega.bonus
    s = stat.copy()
    pv = s.Pv.fillna(0)
    gf_az = (s.Gf - s["R+"]).clip(lower=0)
    out = pd.DataFrame({
        "Id": s.Id.astype(int), "ruolo": s.R, "squadra": s.Squadra, "Nome": s.Nome,
        "pv": pv.astype(int), "sv": 0,
        "voto_s": (s.Mv * pv).fillna(0),
        "c_azione": b.gol_fatto * gf_az + b.assist * s.Ass,
        "c_rigore": b.gol_fatto * s["R+"] + b.rigore_sbagliato * s["R-"],
        "c_malus": b.ammonizione * s.Amm + b.espulsione * s.Esp + b.autogol * s.Au,
        "c_port": b.gol_subito * s.Gs + b.rigore_parato * s.Rp,
        "gf": gf_az, "rf": s["R+"], "rs": s["R-"], "rc": s.Rc, "gs": s.Gs, "cs": 0,
    })
    return out.fillna(0)


def partite_understat(team_match: pd.DataFrame, stagione: str) -> pd.DataFrame:
    """Understat partite di squadra -> formato carica_partite, solo giocate.

    La giornata si ricava dall'ordine delle partite di ogni squadra (Understat
    non la riporta): per squadra la n-esima partita giocata e' la giornata n.
    Approssimazione esatta senza recuperi; con un recupero sfalsa di una
    giornata solo la squadra coinvolta.
    """
    t = team_match.dropna(subset=["home_goals"]).sort_values("date")
    out = pd.DataFrame({
        "stagione": stagione,
        "casa": t.home_team.replace(SQUADRE_UNDERSTAT),
        "ospite": t.away_team.replace(SQUADRE_UNDERSTAT),
        "gol_casa": t.home_goals.astype(int), "gol_ospite": t.away_goals.astype(int),
        "xg_casa": t.home_xg.astype(float), "xg_ospite": t.away_xg.astype(float),
        "data": t.date,
    })
    n = pd.concat([out.casa, out.ospite]).value_counts()
    out["giornata"] = (out.groupby("casa").cumcount() + 1).clip(upper=int(n.max()))
    return out.reset_index(drop=True)


def carica_stagione_in_corso(giornate: pd.DataFrame | None = None,
                             lega: LeagueRules = LEGA) -> StagioneInCorso | None:
    """Tutto cio' che si sa della stagione in corso, o None se non c'e' nulla."""
    stagione = importa.stagione_corrente()
    us_dir = importa.understat_corrente(stagione)
    partite = pd.DataFrame()
    minuti = None
    if us_dir is not None:
        partite = partite_understat(pd.read_csv(us_dir / "team_match.csv"), stagione)
        pm = us_dir / "player_match.csv"
        minuti = pd.read_csv(pm) if pm.exists() else None

    voti = None if giornate is None else giornate[giornate.stagione == stagione]
    if voti is not None and len(voti):
        oss = aggrega_voti(voti)
        info = voti.sort_values("giornata").groupby("Id")[["squadra", "ruolo", "Nome"]].last()
        oss = oss.join(info, on="Id")
        giornata = int(voti.giornata.max())
        fonte = "voti per giornata Fantacalcio.it"
    else:
        f = importa.statistiche_correnti(stagione)
        if f is None:
            return None
        stat = _leggi_statistiche(f)
        oss = osservato_da_statistiche(stat, lega)
        giornata = int(oss.pv.max())
        if len(partite):
            giornata = max(giornata, int(round(len(partite) * 2 / oss.squadra.nunique())))
        fonte = f"Statistiche Fantacalcio.it ({f.name})"
    for c in ["pv", "sv", "voto_s", *FAMIGLIE, "gf", "rf", "rs", "rc", "gs", "cs"]:
        if c not in oss.columns:
            oss[c] = 0
    return StagioneInCorso(stagione, giornata, oss.reset_index(drop=True),
                           partite, minuti, fonte)


def _leggi_statistiche(path) -> pd.DataFrame:
    from ingest.fonti import STAT_NUM
    d = pd.read_excel(path, sheet_name="Tutti", header=1)
    mancanti = [c for c in ["Id", "R", "Nome", "Squadra", *STAT_NUM] if c not in d.columns]
    if mancanti:
        raise ValueError(f"{path}: colonne mancanti {mancanti}")
    for c in STAT_NUM:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    return d
