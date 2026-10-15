"""Backtest economico: il listino anticipa quanto vale davvero un giocatore?

Le metriche di backtest/storico.py misurano i PUNTI. Ma in asta si compra
valore, cioe' quanto un giocatore aggiunge ai punti della sua squadra, panchina
compresa. Qui lo si misura sui dati veri:

  1. si costruiscono 8 rose plausibili (draft a serpentina con i vincoli di
     slot) secondo un "contesto": come la stanza ordina i giocatori;
  2. si rigioca la stagione giornata per giornata con i fantavoti VERI
     (simulate/lega.settimane_reali): ogni settimana si schiera il modulo
     migliore fra chi ha preso voto;
  3. il valore REALIZZATO di un giocatore e' quanto migliora in media una di
     quelle rose rispetto al miglior svincolato del suo ruolo.

Poi si correla il valore previsto (o il prezzo) con quello realizzato, su tutti
i ruoli insieme: premia sia l'ordine dentro il ruolo sia la scala fra ruoli,
cioe' la ripartizione del budget. Il contesto conta (chi resta svincolato cambia
il valore di tutti), quindi si prova con piu' contesti: un modello e' buono se
vince in tutti.

Lezione emersa (docs/METODO.md §6.11): la quota realizzata per ruolo oscilla
moltissimo fra stagioni e contesti (il centrocampo vale il 46%, 3%, 51%, 27% del
valore nelle quattro stagioni): la "quota strategica per ruolo" della versione
precedente non era una costante strutturale e imporla era un errore.
"""
from __future__ import annotations

import pandas as pd

from simulate import lega as sl
from value.valore import valore_per_presenza, valore_punti_totali

CONTESTI = {
    "mercato: punti anno prima": "ingenua",
    "lega efficiente: proiezioni v3": "punti_proj",
}


def valori_realizzati(df: pd.DataFrame, giornate: pd.DataFrame,
                      contesti: dict[str, str] = CONTESTI,
                      da_giornata: int = 3) -> pd.DataFrame:
    """Aggiunge una colonna `real::<contesto>` per contesto, stagione per stagione."""
    parti = []
    for t, d in df.groupby("stagione"):
        d = d.reset_index(drop=True).copy()
        s = sl.settimane_reali(giornate, t, d, da_giornata)
        ruolo = d.ruolo.values
        for nome, col in contesti.items():
            v = d[col].fillna(0).values
            rose = sl.draft(v, ruolo)
            fa = sl.rimpiazzi(v, ruolo, rose)
            d[f"real::{nome}"] = sl.valore_marginale(s, rose, fa)
        parti.append(d)
    return pd.concat(parti, ignore_index=True)


def valori_previsti(df: pd.DataFrame) -> pd.DataFrame:
    """Valori della v3 per stagione (stessa funzione del listino) e alternative."""
    parti = []
    for _, d in df.groupby("stagione"):
        d = d.copy()
        d["v3_valore"] = valore_per_presenza(d)
        d["v3_punti_totali"] = valore_punti_totali(d)
        parti.append(d)
    return pd.concat(parti)


def confronto(df: pd.DataFrame, candidati: dict[str, str],
              contesti: dict[str, str] = CONTESTI) -> pd.DataFrame:
    """Correlazione (Pearson e Spearman, tutti i ruoli insieme) fra ogni
    candidato e il valore realizzato, media sulle stagioni, per contesto."""
    righe = []
    for t, d in df.groupby("stagione"):
        for nc, cc in candidati.items():
            for nx in contesti:
                y = d[f"real::{nx}"]
                righe.append(dict(stagione=t, candidato=nc, contesto=nx,
                                  pearson=d[cc].corr(y),
                                  spearman=d[cc].corr(y, method="spearman")))
    return (pd.DataFrame(righe).groupby(["candidato", "contesto"])
            [["pearson", "spearman"]].mean().round(3))


def quote_ruolo(df: pd.DataFrame, colonne: dict[str, str]) -> pd.DataFrame:
    """Quota del valore positivo per ruolo (%), per ogni colonna."""
    out = {}
    for nome, c in colonne.items():
        q = df.groupby("ruolo")[c].apply(lambda x: x.clip(lower=0).sum())
        out[nome] = q / q.sum() * 100
    return pd.DataFrame(out).T.reindex(columns=["P", "D", "C", "A"]).round(1)


def quote_per_stagione(df: pd.DataFrame, colonna: str) -> pd.DataFrame:
    q = (df.groupby(["stagione", "ruolo"])[colonna]
           .apply(lambda x: x.clip(lower=0).sum()).unstack())
    return (q.div(q.sum(axis=1), axis=0) * 100).reindex(columns=["P", "D", "C", "A"]).round(1)
