"""Stadio 1 — disponibilita': quante delle giornate che contano giochera' con voto.

Obiettivo: la frazione di giornate conteggiate (dalla 3ª alla 38ª) in cui il
giocatore prende voto. Modello: regressione logistica frazionaria per ruolo,
con penalita' ridge, stimata su "aste storiche" ricostruite con
`models.istantanea.da_storico` (una riga per tesserato e stagione).

Perche' cosi', misurato nel backtest (docs/METODO.md §6.10):
  - le prime giornate OSSERVATE prima dell'asta sono il predittore piu' forte di
    tutti (correlazione 0,55-0,73 con le presenze del resto della stagione,
    contro 0,36-0,67 delle presenze dell'anno prima). E' la regola §3 "usa le
    prime giornate per aggiornare la disponibilita'", ora implementata;
  - le stagioni a zero presenze entrano come zeri veri (pannello_stagioni), non
    spariscono;
  - un boosting (HistGradientBoosting) sugli stessi dati fa PEGGIO (correlazione
    0,56-0,70 contro 0,59-0,76): a livello giocatore-stagione il campione e'
    piccolo e la relazione quasi lineare nel logit. Niente dipendenze in piu';
  - la concorrenza nel reparto (disponibilita' dei compagni davanti) e la
    normalizzazione per squadra non migliorano la previsione fuori campione:
    l'informazione e' gia' nelle presenze recenti e osservate.

Il modello della versione precedente regrediva le presenze verso la media dei
TITOLARI con una pendenza stimata solo su chi aveva >=10 presenze in entrambe le
stagioni (troncamento): tutti risultavano titolari (portieri 25 presenze
proiettate contro 10 reali) e la dispersione veniva schiacciata da 12 a 3,5.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ingest.panel import punti_realizzati
from models.istantanea import GIORNATE_STAGIONE, Istantanea, _stagione_precedente
from rules import LEGA, LeagueRules

RUOLI = ("P", "D", "C", "A")
GIRONE = 19

CARATTERISTICHE = [
    "pv1",      # presenze con voto la stagione scorsa / 38 (0 se tesserato senza voto)
    "pv2",      # idem due stagioni fa
    "pv1_rit",  # presenze con voto nel girone di ritorno scorso / 19 (ruolo recente)
    "sv1",      # ingressi senza voto (6*) la stagione scorsa / 38: spezzoni
    "in1",      # era tesserato in Serie A la stagione scorsa
    "in2",      # ... e due stagioni fa
    "stesso_club",   # tesserato l'anno scorso con lo stesso club
    "cambio_club",   # tesserato l'anno scorso con un altro club di Serie A
    "neopromossa",   # il suo club non era in Serie A la stagione scorsa
    "voto_rel",      # media voto della stagione scorsa meno la media del ruolo
    "voto_noto",     # 1 se voto_rel e' definito (almeno una presenza con voto)
    "oss_voto",      # presenze con voto nelle giornate gia' giocate / giornate
    "oss_zero",      # 1 se non ha mai preso voto nelle giornate gia' giocate
]


def caratteristiche(ist: Istantanea) -> pd.DataFrame:
    """Matrice delle caratteristiche per l'universo dell'istantanea (indice Id)."""
    U = ist.universo[["Id", "ruolo", "squadra"]].copy()
    H = ist.storico
    s1 = _stagione_precedente(ist.stagione)
    s2 = _stagione_precedente(s1)
    h1 = H[H.stagione == s1].set_index("Id")
    h2 = H[H.stagione == s2].set_index("Id")

    U["in1"] = U.Id.isin(h1.index).astype(float)
    U["in2"] = U.Id.isin(h2.index).astype(float)
    U["pv1"] = U.Id.map(h1.pv).fillna(0) / GIORNATE_STAGIONE
    U["pv2"] = U.Id.map(h2.pv).fillna(0) / GIORNATE_STAGIONE
    U["pv1_rit"] = U.Id.map(h1.pv_g2).fillna(0) / GIRONE
    U["sv1"] = U.Id.map(h1.sv).fillna(0) / GIORNATE_STAGIONE
    club1 = U.Id.map(h1.squadra)
    U["stesso_club"] = ((club1 == U.squadra) & (U.in1 == 1)).astype(float)
    U["cambio_club"] = ((club1 != U.squadra) & (U.in1 == 1)).astype(float)
    U["neopromossa"] = (~U.squadra.isin(set(h1.squadra))).astype(float) if len(h1) else 0.0

    mv1 = U.Id.map(h1.voto_s / h1.pv.where(h1.pv > 0))
    media_ruolo = U.assign(mv1=mv1).groupby("ruolo").mv1.transform("mean")
    U["voto_noto"] = mv1.notna().astype(float)
    U["voto_rel"] = (mv1 - media_ruolo).fillna(0.0)

    # gli ingressi senza voto (6*) delle giornate osservate NON sono una
    # caratteristica: l'aggregato delle Statistiche non li riporta, e un modello
    # deve usare solo cio' che avra' anche il giorno in cui lo si usa
    g0 = max(ist.giornata_asta, 1)
    o = ist.aggregato_osservato()
    if len(o):
        U["oss_voto"] = U.Id.map(o.set_index("Id").pv).fillna(0) / g0
    else:
        U["oss_voto"] = 0.0
    # senza giornate osservate l'indicatore vale 1 per tutti: collineare con
    # l'intercetta, la penalita' ridge lo tiene a bada
    U["oss_zero"] = (U.oss_voto == 0).astype(float)
    return U.set_index("Id")[["ruolo", "squadra", *CARATTERISTICHE]]


def giornate_conteggiate(ist: Istantanea, lega: LeagueRules = LEGA) -> tuple[int, int]:
    """Prima e numero di giornate che producono punti dopo l'asta."""
    prima = max(lega.prima_giornata_conteggiata, ist.giornata_asta + 1)
    return prima, lega.giornate_totali - prima + 1


def etichette(ist: Istantanea, giornate: pd.DataFrame,
              lega: LeagueRules = LEGA) -> pd.Series:
    """Frazione REALIZZATA di giornate conteggiate con voto (solo backtest)."""
    prima, n = giornate_conteggiate(ist, lega)
    r = punti_realizzati(giornate, ist.stagione, prima).set_index("Id")
    return (ist.universo.Id.map(r.pv).fillna(0) / n).set_axis(ist.universo.Id)


# --------------------------------------------------------------------------- #
# Logistica frazionaria con ridge (IRLS), solo numpy
# --------------------------------------------------------------------------- #
def _logit_ridge(X: np.ndarray, y: np.ndarray, w: np.ndarray,
                 lam: float, iterazioni: int = 100) -> np.ndarray:
    """Massimizza Σ w·[y·log p + (1−y)·log(1−p)] − lam/2·|b|² (intercetta libera).

    `y` e' una frazione in [0,1] (presenze/giornate), `w` il numero di giornate:
    e' la verosimiglianza binomiale con y·w successi su w prove.
    """
    b = np.zeros(X.shape[1])
    pen = np.full(X.shape[1], lam)
    pen[0] = 0.0
    for _ in range(iterazioni):
        p = 1.0 / (1.0 + np.exp(-(X @ b)))
        grad = X.T @ (w * (y - p)) - pen * b
        hess = X.T @ (X * (w * p * (1 - p))[:, None]) + np.diag(pen)
        passo = np.linalg.solve(hess, grad)
        b += passo
        if np.abs(passo).max() < 1e-9:
            break
    return b


# Ruoli con un vincolo fisico di squadra: in porta gioca uno solo. Le
# probabilita' dei portieri di una squadra si ripartiscono la capienza storica
# (~0,98 portieri con voto a partita) in proporzione alle QUOTE p/(1−p): misurato
# sul backtest, l'errore sulle presenze dei portieri scende da 5,8-5,9 a
# 5,3-5,6 rispetto a un semplice tetto. Per gli altri ruoli vincoli di squadra
# non migliorano la previsione fuori campione.
RUOLI_CON_TETTO = ("P",)


@dataclass(frozen=True)
class ModelloDisponibilita:
    coefficienti: dict[str, np.ndarray]     # per ruolo: [intercetta, *CARATTERISTICHE]
    n_addestramento: dict[str, int]
    capienza: dict[str, float]              # giocatori con voto a partita, per squadra e ruolo

    def prevedi(self, ist: Istantanea,
                ruoli_con_tetto: tuple[str, ...] = RUOLI_CON_TETTO) -> pd.Series:
        """Probabilita' di prendere voto in una giornata conteggiata, per Id."""
        X = caratteristiche(ist)
        p = pd.Series(np.nan, index=X.index, dtype=float)
        for r in RUOLI:
            m = (X.ruolo == r).values
            if not m.any():
                continue
            Z = np.c_[np.ones(m.sum()), X.loc[m, CARATTERISTICHE].values]
            p[m] = 1.0 / (1.0 + np.exp(-(Z @ self.coefficienti[r])))
        for r in ruoli_con_tetto:
            m = X.ruolo == r
            quota = p[m] / (1.0 - p[m])
            p[m] = (quota / quota.groupby(X.squadra[m]).transform("sum")
                    * self.capienza[r]).clip(upper=0.99)
        return p

    def tabella_coefficienti(self) -> pd.DataFrame:
        return pd.DataFrame(self.coefficienti,
                            index=["intercetta", *CARATTERISTICHE]).round(3)


def addestra(addestramento: list[tuple[Istantanea, pd.Series]],
             lam: float = 1.0) -> ModelloDisponibilita:
    """Stima il modello su coppie (istantanea storica, etichette realizzate)."""
    if not addestramento:
        raise ValueError("serve almeno un'asta storica per addestrare")
    parti = []
    for ist, y in addestramento:
        X = caratteristiche(ist)
        X["y"] = y.reindex(X.index).values
        X["w"] = float(giornate_conteggiate(ist)[1])
        parti.append(X)
    D = pd.concat(parti, keys=range(len(parti)), names=["asta", "Id"]).reset_index()
    coef, n, cap = {}, {}, {}
    for r in RUOLI:
        d = D[D.ruolo == r]
        Z = np.c_[np.ones(len(d)), d[CARATTERISTICHE].values]
        coef[r] = _logit_ridge(Z, d.y.values, d.w.values, lam)
        n[r] = len(d)
        cap[r] = float(d.groupby(["asta", "squadra"]).y.sum().mean())
    return ModelloDisponibilita(coef, n, cap)
