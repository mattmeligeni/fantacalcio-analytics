"""Dal rendimento proiettato al valore: quanto un giocatore aggiunge a una squadra.

Funzione di valore di default — VALORE PER PRESENZA (docs/METODO.md §6.11):

    valore = presenze proiettate × (fantamedia proiettata − fantamedia di rimpiazzo)

troncato a zero. La fantamedia di rimpiazzo del ruolo e' quella del
"panchinaro tipo" della lega: la media dei giocatori fra il rango 1,5·k e
2,5·k per punti proiettati (k = domanda di titolari: 8 P, 28 D, 28 C, 24 A).
Sono i giocatori che stanno nelle panchine delle otto rose e che entrano
quando un titolare non prende voto.

Perche' non i punti totali sopra il rimpiazzo, come nella versione precedente.
Con una panchina, una giornata saltata non costa i punti del titolare ma solo
la differenza col compagno che lo sostituisce. Simulando la formazione
settimanale di una lega di 8 rose (simulate/lega.py) il valore marginale di
D, C e A correla 0,93-0,98 con "presenze × vantaggio per partita" e solo
0,64-0,75 con i punti totali sopra il rimpiazzo. Il vecchio listino premiava
chi gioca tanto anche se mediocre.

Verifica economica (backtest/economico.py): rigiocando le stagioni 2022-23 →
2025-26 con i fantavoti veri, questa funzione anticipa il valore marginale
realizzato meglio del vecchio listino in ogni contesto di rose provato.

Funzioni alternative, stessa firma (vincolo §7.1: la funzione e' sostituibile):
  - `valore_punti_totali`: la vecchia definizione, tenuta per confronto;
  - `valore_simulato`: contributo marginale simulato nelle rose di una lega
    plausibile. E' quella da usare se un giorno si attivano i modificatori, che
    rendono il valore non additivo. Senza modificatori sovrastima i portieri
    (scarsita' di titolari in porta che dipende da chi resta svincolato) ed e'
    meno robusta al contesto: non e' il default.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from rules import LEGA, LeagueRules

RUOLI = ("P", "D", "C", "A")
FASCIA_RIMPIAZZO = (1.5, 2.5)        # in multipli della domanda di titolari k

FunzioneValore = Callable[[pd.DataFrame, LeagueRules], pd.Series]


def rango_titolari(ruolo: str, lega: LeagueRules = LEGA) -> int:
    """k = titolari schierati in media × squadre: P 8, D 28, C 28, A 24.

    Si usa la domanda di TITOLARI, non gli slot di rosa (docs/METODO.md §10)."""
    return round(lega.titolari_per_ruolo[ruolo] * lega.squadre)


def fantamedia_totale(proiezioni: pd.DataFrame) -> pd.Series:
    """Punti per presenza, rigori inclusi (i rigori si calciano giocando)."""
    pv = proiezioni.pv_proj.where(proiezioni.pv_proj > 0)
    return (proiezioni.punti_proj / pv).fillna(proiezioni.fm_base)


def livelli_rimpiazzo(proiezioni: pd.DataFrame, lega: LeagueRules = LEGA,
                      fascia: tuple[float, float] = FASCIA_RIMPIAZZO) -> pd.DataFrame:
    """Per ruolo: fantamedia del panchinaro tipo e punti del k-esimo titolare."""
    fm = fantamedia_totale(proiezioni)
    righe = []
    for r in RUOLI:
        k = rango_titolari(r, lega)
        ordine = proiezioni[proiezioni.ruolo == r].punti_proj.sort_values(ascending=False)
        lo, hi = int(fascia[0] * k), int(fascia[1] * k)
        banca = ordine.iloc[lo - 1:hi].index
        righe.append(dict(ruolo=r, k=k, fm_rimpiazzo=float(fm[banca].mean()),
                          punti_k=float(ordine.iloc[k - 1])))
    return pd.DataFrame(righe).set_index("ruolo")


def valore_per_presenza(proiezioni: pd.DataFrame, lega: LeagueRules = LEGA) -> pd.Series:
    """Default: presenze × vantaggio per partita sul panchinaro tipo, >= 0."""
    liv = livelli_rimpiazzo(proiezioni, lega)
    fm = fantamedia_totale(proiezioni)
    v = proiezioni.pv_proj * (fm - proiezioni.ruolo.map(liv.fm_rimpiazzo))
    return v.clip(lower=0.0)


def valore_punti_totali(proiezioni: pd.DataFrame, lega: LeagueRules = LEGA) -> pd.Series:
    """La definizione della versione precedente: punti − punti del k-esimo."""
    liv = livelli_rimpiazzo(proiezioni, lega)
    return (proiezioni.punti_proj - proiezioni.ruolo.map(liv.punti_k)).clip(lower=0.0)


def valore_simulato(proiezioni: pd.DataFrame, lega: LeagueRules = LEGA,
                    contesto: str = "fvm_meta", settimane: int = 1500,
                    seme: int = 0) -> pd.Series:
    """Contributo marginale simulato in una lega di rose costruite dal mercato.

    `contesto`: la colonna con cui la stanza ordina i giocatori per fare le rose
    (all'asta vera l'FVM; nel backtest i punti della stagione scorsa). Ogni
    giocatore vale quanto migliora in media una di quelle rose rispetto al
    miglior svincolato del suo ruolo. Tronca a zero.
    """
    from simulate import lega as sl            # import locale: modulo pesante
    d = proiezioni.reset_index(drop=True).assign(fm_tot=fantamedia_totale(proiezioni).values)
    ruolo = d.ruolo.values
    n = int(round(d.pv_proj.sum() / d.p_voto.sum())) if d.p_voto.sum() > 0 else 36
    s = sl.settimane_simulate(d, n, settimane=settimane, seme=seme)
    rose = sl.draft(d[contesto].fillna(0).values, ruolo, lega)
    fa = sl.rimpiazzi(d.punti_proj.values, ruolo, rose)
    v = sl.valore_marginale(s, rose, fa, lega=lega)
    return pd.Series(np.clip(v, 0, None), index=proiezioni.index)


def prezzi(proiezioni: pd.DataFrame, valore: pd.Series,
           lega: LeagueRules = LEGA) -> pd.Series:
    """Dal valore ai crediti, un unico tasso per tutti i ruoli.

    I 3800 crediti contendibili si ripartiscono in proporzione al valore fra i
    200 giocatori che riempiono le rose (i migliori per valore nel rispetto
    degli slot: 24 P, 64 D, 64 C, 48 A), piu' 1 credito di pavimento. Cosi' la
    somma dei prezzi delle rose e' esattamente il monte crediti (4000) e un
    punto di valore costa lo stesso in ogni ruolo. La versione precedente dava
    il pavimento a tutti i 509 del listone (somma 4314) e imponeva quote fisse
    per ruolo (un punto di portiere costava il 78% piu' di uno di difensore).
    """
    in_rosa = pd.Series(False, index=proiezioni.index)
    for r, slot in lega.rosa.slot.items():
        m = proiezioni.ruolo == r
        in_rosa[valore[m].nlargest(slot * lega.squadre).index] = True
    totale = valore[in_rosa].sum()
    tasso = lega.crediti_contendibili / totale if totale > 0 else 0.0
    return 1.0 + tasso * valore


def tasso_crediti(proiezioni: pd.DataFrame, valore: pd.Series,
                  lega: LeagueRules = LEGA) -> float:
    """Crediti per punto di valore (lo stesso per tutti i ruoli)."""
    p = prezzi(proiezioni, valore, lega)
    m = valore > 0
    return float(((p[m] - 1) / valore[m]).median()) if m.any() else 0.0
