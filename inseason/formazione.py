"""Gestione settimanale: formazione consigliata e svincoli. Logica pura.

Formazione. Per ogni giocatore della rosa: punti attesi nella prossima giornata
= probabilita' di prendere voto × fantamedia proiettata (rigori inclusi). Si
sceglie il modulo ammesso (rules/config.py) che massimizza la somma degli
undici; la panchina si ordina DENTRO il ruolo (ordine di sostituzione hybrid:
prima si cerca il pari ruolo, docs/METODO.md §3), quindi conta l'ordine per
ruolo, non quello globale.

La probabilita' viene dal modello di disponibilita' (frazione di giornate con
voto attesa da qui a fine stagione). Per la singola giornata l'app mostra
accanto i minuti delle ultime partite (Understat): l'informazione che decide i
casi dubbi, insieme alle notizie su infortuni e squalifiche, che il modello non
vede. Un giocatore segnato come indisponibile ha probabilita' 0.

Svincoli. Per ruolo, i giocatori liberi con valore per presenza piu' alto del
tuo peggiore dello stesso ruolo: chi prendere e chi lasciare.
"""
from __future__ import annotations

import pandas as pd

from rules import LEGA, LeagueRules

RUOLI = ("P", "D", "C", "A")


def punti_attesi(rosa: pd.DataFrame, indisponibili: set[int] = frozenset()) -> pd.Series:
    """p_voto × fantamedia per la prossima giornata (0 se indisponibile)."""
    p = rosa.p_voto.where(~rosa.Id.isin(indisponibili), 0.0).fillna(0)
    return p * rosa.fm_proj.fillna(rosa.fm_base)


def formazione(rosa: pd.DataFrame, indisponibili: set[int] = frozenset(),
               lega: LeagueRules = LEGA) -> dict:
    """Modulo, titolari e panchina ordinata per ruolo.

    `rosa`: Id, Nome, ruolo, p_voto, fm_proj (o fm_base).
    """
    r = rosa.assign(attesi=punti_attesi(rosa, indisponibili)).sort_values(
        "attesi", ascending=False)
    per_ruolo = {k: r[r.ruolo == k] for k in RUOLI}
    if per_ruolo["P"].empty:
        raise ValueError("nessun portiere in rosa")
    migliore = None
    for d, c, a in lega.moduli:
        if len(per_ruolo["D"]) < d or len(per_ruolo["C"]) < c or len(per_ruolo["A"]) < a:
            continue
        tot = (per_ruolo["P"].attesi.iloc[0] + per_ruolo["D"].attesi.iloc[:d].sum()
               + per_ruolo["C"].attesi.iloc[:c].sum() + per_ruolo["A"].attesi.iloc[:a].sum())
        if migliore is None or tot > migliore[0]:
            migliore = (tot, (d, c, a))
    if migliore is None:
        raise ValueError("la rosa non copre nessun modulo ammesso")
    tot, (d, c, a) = migliore
    n = {"P": 1, "D": d, "C": c, "A": a}
    titolari = pd.concat([per_ruolo[k].iloc[:n[k]] for k in RUOLI])
    panchina = pd.concat([per_ruolo[k].iloc[n[k]:] for k in RUOLI])
    return dict(modulo=f"{d}-{c}-{a}", punti_attesi=round(float(tot), 1),
                titolari=titolari, panchina=panchina)


def svincoli(rosa: pd.DataFrame, liberi: pd.DataFrame, per_ruolo: int = 5,
             min_valore: float = 1.0, min_punti: float = 15.0) -> pd.DataFrame:
    """Per ruolo, i liberi che migliorano davvero sul peggiore della rosa.

    Si confronta il valore (presenze × vantaggio per partita). Fra riserve a
    valore zero, che contano solo come copertura della panchina, si confrontano
    i punti attesi. Soglie: +`min_valore` di valore o +`min_punti` punti.
    Entrambi i frame con: Id, Nome, ruolo, squadra, valore, punti_proj.
    """
    righe = []
    for k in RUOLI:
        mie = rosa[rosa.ruolo == k]
        if mie.empty:
            continue
        peggiore = mie.sort_values(["valore", "punti_proj"]).iloc[0]
        cand = liberi[liberi.ruolo == k].copy()
        cand["g_valore"] = cand.valore - peggiore.valore
        cand["g_punti"] = cand.punti_proj - peggiore.punti_proj
        meglio = cand[(cand.g_valore >= min_valore)
                      | ((cand.valore <= 0) & (peggiore.valore <= 0) & (cand.g_punti >= min_punti))]
        for _, l in meglio.sort_values(["g_valore", "g_punti"], ascending=False).head(per_ruolo).iterrows():
            righe.append(dict(ruolo=k, prendi=l.Nome, squadra=l.squadra,
                              valore_prendi=round(l.valore, 1), lascia=peggiore.Nome,
                              valore_lascia=round(peggiore.valore, 1),
                              guadagno_valore=round(l.g_valore, 1),
                              guadagno_punti=round(l.g_punti, 1)))
    return pd.DataFrame(righe, columns=["ruolo", "prendi", "squadra", "valore_prendi", "lascia",
                                        "valore_lascia", "guadagno_valore", "guadagno_punti"])
