"""Anagrafica Understat ↔ Fantacalcio: da (giocatore, squadra) Understat al
codice Id di Fantacalcio.it.

Strategia (docs/DATI.md §5): normalizzazione con sostituzioni esplicite
(la `ø` non si decompone con NFKD), cognome Fantacalcio senza le iniziali
puntate ("Martinez L." -> martinez + iniziale l), aggancio per intersezione di
token DENTRO la stessa squadra, disambiguazione con l'iniziale. Ogni giocatore
Understat aggancia al massimo un Id e viceversa.

Validazione indipendente, che fallisce rumorosamente: fra i giocatori
Fantacalcio con almeno `soglia_pv` presenze deve agganciarsi almeno il
`copertura_minima` (un join riuscito al 72% senza errori e' il modo canonico in
cui muoiono i progetti di dati).
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

from ingest.fonti import SQUADRE_UNDERSTAT

EXTRA = str.maketrans({
    "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
    "ß": "ss", "æ": "ae", "Æ": "Ae", "ð": "d", "þ": "th", "ı": "i",
})


def normalizza(s: str) -> str:
    s = str(s).translate(EXTRA)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z. ]", " ", s.lower().replace("-", " ").replace("'", ""))


def _token_fanta(nome: str) -> tuple[set[str], str]:
    """'Milinkovic-Savic V.' -> ({'milinkovic','savic'}, 'v')."""
    parti = normalizza(nome).split()
    iniz = "".join(p.rstrip(".") for p in parti if p.endswith("."))
    cogn = {p for p in parti if not p.endswith(".") and len(p) > 1}
    return cogn, iniz


def aggancia(fanta: pd.DataFrame, understat: pd.DataFrame) -> pd.DataFrame:
    """`fanta`: Id, Nome, squadra. `understat`: player_id, player, team.
    Ritorna player_id -> Id con il criterio usato."""
    # un giocatore trasferito compare con piu' squadre: si tengono tutte
    us = understat[["player_id", "player", "team"]].drop_duplicates(["player_id", "team"]).copy()
    us["squadra"] = us.team.replace(SQUADRE_UNDERSTAT)
    us["tok"] = us.player.map(lambda s: set(normalizza(s).split()))
    us["unito"] = us.player.map(lambda s: normalizza(s).replace(" ", "").replace(".", ""))
    us["nome1"] = us.player.map(lambda s: normalizza(s).split()[0] if s else "")
    righe, presi = [], set()
    for f in fanta.itertuples():
        cogn, iniz = _token_fanta(f.Nome)
        if not cogn:
            continue
        unito = "".join(sorted(cogn, key=normalizza(f.Nome).find))
        # 1) token del cognome contenuti nel nome Understat; 2) cognome attaccato
        #    ("Delprato" ~ "Del Prato"); sempre dentro la stessa squadra
        stessa = us[us.squadra == f.squadra]
        cand = stessa[stessa.tok.map(lambda t: cogn <= t)]
        if cand.empty:
            cand = stessa[stessa.unito.str.contains(unito, regex=False)]
        if cand.empty:
            # 3) un token in comune, ma solo se nella squadra e' l'unico
            #    ("Floriani Mussolini" ~ "Romano Floriani")
            cand = stessa[stessa.tok.map(lambda t: bool(cogn & t))]
            if cand.player_id.nunique() > 1:
                cand = cand.iloc[0:0]
        if cand.player_id.nunique() > 1 and iniz:
            cand = cand[cand.nome1.str.startswith(iniz)]
        cand = cand.drop_duplicates("player_id")
        if len(cand) == 1 and int(cand.player_id.iloc[0]) not in presi:
            pid = int(cand.player_id.iloc[0])
            presi.add(pid)
            righe.append(dict(Id=int(f.Id), player_id=pid, player=cand.player.iloc[0]))
    return pd.DataFrame(righe, columns=["Id", "player_id", "player"])


def valida(mappa: pd.DataFrame, fanta: pd.DataFrame, soglia_pv: int = 3,
           copertura_minima: float = 0.95) -> float:
    rilevanti = fanta[fanta.pv >= soglia_pv]
    cop = float(rilevanti.Id.isin(mappa.Id).mean()) if len(rilevanti) else 1.0
    if cop < copertura_minima:
        mancano = rilevanti[~rilevanti.Id.isin(mappa.Id)].Nome.head(15).tolist()
        raise ValueError(f"anagrafica Understat: copertura {cop:.1%} < {copertura_minima:.0%} "
                         f"sui giocatori con >= {soglia_pv} presenze; es. mancanti {mancano}")
    return cop


def minuti_recenti(minuti: pd.DataFrame, mappa: pd.DataFrame, ultime: int = 3) -> pd.DataFrame:
    """Per Id: minuti nelle ultime `ultime` partite della sua squadra (0 se non
    e' sceso in campo) e se e' partito titolare l'ultima volta."""
    minuti = minuti.assign(date=minuti.game.str[:10])     # "2026-08-22 Casa-Ospite"
    m = minuti.merge(mappa[["player_id", "Id"]], on="player_id", how="inner")
    partite = (minuti[["team", "game", "date"]].drop_duplicates()
               .sort_values("date").groupby("team").tail(ultime))
    g = partite.merge(m[["team", "game", "Id", "minutes", "position"]],
                      on=["team", "game"], how="left")
    agg = m.sort_values("date").groupby("Id").agg(team=("team", "last"))
    righe = []
    for Id, team in agg.team.items():
        pp = partite[partite.team == team].sort_values("date")
        mins = [int(g[(g.game == gm) & (g.Id == Id)].minutes.sum()) for gm in pp.game]
        ultima_pos = g[(g.game == pp.game.iloc[-1]) & (g.Id == Id)].position
        righe.append(dict(Id=Id, minuti_recenti=mins,
                          titolare_ultima=bool(len(ultima_pos)) and str(ultima_pos.iloc[0]) != "Sub"))
    return pd.DataFrame(righe).set_index("Id") if righe else pd.DataFrame(
        columns=["minuti_recenti", "titolare_ultima"])
