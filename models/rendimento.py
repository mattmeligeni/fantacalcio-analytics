"""Stadio 2 — rendimento per presenza: quanto vale una giornata con voto.

La fantamedia si scompone in famiglie con persistenze diverse (docs/METODO.md
§6.8) e ognuna si contrae verso una media di ruolo con un'UNICA contrazione
empirico-bayesiana (mai due volte la stessa affidabilita'):

    stima = media + n / (n + K) · (storico − media)

con `n` = presenze con voto pesate per decadimento (dimezzamento 2 stagioni) e
`storico` la media per presenza pesata allo stesso modo. Le prime giornate
osservate prima dell'asta entrano come i dati piu' recenti (peso 1): pesano per
quello che sono, due presenze, quindi quasi nulla, come vuole la regola §3.

Cosa cambia rispetto alla versione precedente, tutto misurato fuori campione:
  - **K stimato per minimo errore di previsione** sulle aste storiche di
    addestramento, per ruolo e famiglia, non ricavato da una pendenza calcolata
    solo su chi aveva >=10 presenze (troncamento). I valori risultano vicini ai
    vecchi (20-80 presenze pesate): il rendimento per presenza NON era il
    problema principale del vecchio modello.
  - **media di ruolo su tutti i giocatori** pesata per presenze, non solo su chi
    ne ha >=15: il vecchio prior dei titolari gonfiava le riserve.
  - per ogni ruolo e famiglia si sceglie (sull'errore di addestramento) se la
    media dipende dalla disponibilita' proiettata (`media_p`): conviene per i
    bonus degli attaccanti (chi gioca di piu' segna di piu' a partita), non per
    il voto di difensori e centrocampisti, dove peggiora l'errore del 6-10%.
  - la famiglia **portiere** (gol subiti, rigori parati, imbattibilita') non si
    stima dal portiere ma dalla difesa della sua squadra: models/squadre.py.
  - i **rigori** non sono qui: models/rigori.py, per status.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from models.istantanea import GIORNATE_STAGIONE, Istantanea

RUOLI = ("P", "D", "C", "A")
EMIVITA_STAGIONI = 2.0
# famiglia -> colonna somma nel pannello stagioni
FAMIGLIE = {"voto": "voto_s", "azione": "c_azione", "malus": "c_malus", "port": "c_port"}
GRIGLIA_K = (2.0, 5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 1e9)
VARIANTI = ("costante", "media_p")


def pesi_stagione(stagioni: list[str], emivita: float = EMIVITA_STAGIONI) -> dict[str, float]:
    """Peso di ogni stagione storica: 1 la piu' recente, dimezzato ogni `emivita`."""
    ordinate = sorted(stagioni)
    return {s: 0.5 ** ((len(ordinate) - 1 - i) / emivita) for i, s in enumerate(ordinate)}


def storico_pesato(ist: Istantanea, emivita: float = EMIVITA_STAGIONI) -> pd.DataFrame:
    """Per ogni Id dell'universo: n (presenze pesate), quota storica di presenze
    e media per presenza di ogni famiglia. Le giornate osservate entrano con
    peso 1, come la stagione piu' recente."""
    H = ist.storico[ist.storico.Id.isin(ist.universo.Id)]
    w = pesi_stagione(list(ist.storico.stagione.unique()), emivita)
    A = H.assign(w=H.stagione.map(w), slot=float(GIORNATE_STAGIONE))
    o = ist.aggregato_osservato()
    if len(o):
        o = o[o.Id.isin(ist.universo.Id)]
        A = pd.concat([A, o.assign(w=1.0, slot=float(ist.giornata_asta))],
                      ignore_index=True)
    A["wpv"] = A.w * A.pv
    A["wslot"] = A.w * A.slot
    for f, c in FAMIGLIE.items():
        A[f"s_{f}"] = A.w * A[c]
    T = A.groupby("Id")[["wpv", "wslot", *[f"s_{f}" for f in FAMIGLIE]]].sum()
    T = T.reindex(ist.universo.Id).fillna(0.0)
    out = pd.DataFrame(index=T.index)
    out["n"] = T.wpv
    out["quota_storica"] = (T.wpv / T.wslot.replace(0, np.nan)).fillna(0.0)
    for f in FAMIGLIE:
        out[f"x_{f}"] = (T[f"s_{f}"] / T.wpv.replace(0, np.nan))
    return out


@dataclass(frozen=True)
class Prior:
    """Media di ruolo per famiglia: a + b·p (b = 0 nella variante costante)."""
    a: float
    b: float

    def __call__(self, p):
        return self.a + self.b * p


def _stima_prior(storico: pd.DataFrame, ruolo: str, famiglia: str) -> tuple[Prior, Prior]:
    """Prior costante (media pesata per presenze di TUTTI i giocatori del ruolo)
    e prior lineare nella quota di presenze stagionale."""
    d = storico[(storico.ruolo == ruolo) & (storico.pv > 0)]
    y = (d[FAMIGLIE[famiglia]] / d.pv).values
    x = (d.pv / GIORNATE_STAGIONE).values
    w = d.pv.values.astype(float)
    costante = Prior(float(np.average(y, weights=w)), 0.0)
    X = np.c_[np.ones(len(d)), x] * np.sqrt(w)[:, None]
    a, b = np.linalg.lstsq(X, y * np.sqrt(w), rcond=None)[0]
    return costante, Prior(float(a), float(b))


@dataclass(frozen=True)
class ModelloRendimento:
    # (ruolo, famiglia) -> (prior scelto, K, variante)
    parametri: dict[tuple[str, str], tuple[Prior, float, str]]

    def prevedi(self, ist: Istantanea, p_proj: pd.Series) -> pd.DataFrame:
        """Rendimento per presenza proiettato, per famiglia (indice Id).

        `p_proj` e' la disponibilita' proiettata (serve alla variante `media_p`
        e a dare a chi non ha storico una media coerente con quanto giochera').
        """
        S = storico_pesato(ist)
        ruolo = ist.universo.set_index("Id").ruolo
        out = pd.DataFrame(index=S.index)
        p = p_proj.reindex(S.index).fillna(0.0)
        for f in FAMIGLIE:
            col = pd.Series(np.nan, index=S.index)
            for r in RUOLI:
                m = (ruolo.reindex(S.index) == r).values
                if not m.any():
                    continue
                prior, K, _ = self.parametri[(r, f)]
                mu = prior(p[m])
                lam = S.n[m] / (S.n[m] + K)
                col[m] = mu + lam * (S[f"x_{f}"][m].fillna(0.0) - mu)
            out[f] = col
        # la famiglia portiere esiste solo per i portieri (per loro la sostituisce
        # comunque la difesa di squadra in models/proiezione.py)
        out.loc[ruolo.reindex(out.index) != "P", "port"] = 0.0
        out["n_eff"] = S.n
        return out

    def tabella(self) -> pd.DataFrame:
        righe = [dict(ruolo=r, famiglia=f, variante=v, K=K, a=pr.a, b=pr.b)
                 for (r, f), (pr, K, v) in self.parametri.items()]
        return pd.DataFrame(righe)


def addestra(addestramento: list[tuple[Istantanea, pd.Series, pd.DataFrame]],
             storico_prior: pd.DataFrame) -> ModelloRendimento:
    """Sceglie prior e K per (ruolo, famiglia) minimizzando l'errore quadratico,
    pesato per presenze realizzate, sulle aste storiche di addestramento.

    Ogni elemento: (istantanea, disponibilita' proiettata, realizzato) dove
    `realizzato` ha per Id le presenze `pv` e le somme di famiglia sulle giornate
    conteggiate di quella stagione. `storico_prior` e' il pannello stagioni da
    cui stimare le medie di ruolo: lo storico dell'asta DA PREVEDERE, che
    contiene solo stagioni passate.
    """
    if not addestramento:
        raise ValueError("serve almeno un'asta storica per addestrare")
    blocchi = []
    for ist, p, real in addestramento:
        S = storico_pesato(ist)
        d = S.join(ist.universo.set_index("Id").ruolo)
        d["p"] = p.reindex(d.index).fillna(0.0)
        d["pv_real"] = real.pv.reindex(d.index).fillna(0)
        for f, c in FAMIGLIE.items():
            d[f"y_{f}"] = real[c].reindex(d.index) / real.pv.reindex(d.index).replace(0, np.nan)
        blocchi.append(d[d.pv_real > 0])
    D = pd.concat(blocchi)

    parametri = {}
    for r in RUOLI:
        for f in FAMIGLIE:
            costante, lineare = _stima_prior(storico_prior, r, f)
            d = D[D.ruolo == r]
            migliore = None
            for variante, prior in (("costante", costante), ("media_p", lineare)):
                mu = prior(d.p)
                for K in GRIGLIA_K:
                    lam = d.n / (d.n + K)
                    stima = mu + lam * (d[f"x_{f}"].fillna(0.0) - mu)
                    err = float(np.average((stima - d[f"y_{f}"]) ** 2, weights=d.pv_real))
                    if migliore is None or err < migliore[0] - 1e-12:
                        migliore = (err, prior, K, variante)
            parametri[(r, f)] = migliore[1:]
    return ModelloRendimento(parametri)
