"""Proiezione a due stadi del rendimento, dal quale nasce il valore.

Punto centrale (docs/METODO.md §6.4): NON si proiettano i punti dell'anno scorso. Si
proiettano separatamente la **fantamedia** e le **presenze**, poi si moltiplica.

E c'e' un secondo livello di separazione (docs/METODO.md §6.5bis): la fantamedia stessa
aggrega componenti con persistenze molto diverse, quindi un fattore unico e' giusto
in media e sbagliato ovunque. Si scompone in voto base, bonus su azione, malus e
componente portiere, ognuna contratta con la sua pendenza MISURATA (persistenze
tipiche: voto 0,28-0,52 · azione 0,38-0,49 · malus 0,11-0,37 · portiere 0,54).
La quinta componente, i rigori, non si proietta per persistenza (rumore per
presenza) ma per STATUS di rigorista in value/rigoristi.py, e si somma a valle.

Ingredienti: pannello componenti da ingest/componenti (fantamedia con
imbattibilita' per i portieri), stagioni con decadimento esponenziale
(dimezzamento ~2 stagioni), shrink empirico-bayesiano per i pochi dati.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from rules import LEGA, LeagueRules
from ingest.componenti import carica_componenti

RUOLI = ("P", "D", "C", "A")
GIORNATE_STAGIONE_STORICA = 38

# Componenti della fantamedia contratte per persistenza. I rigori (c_rigore) NON
# sono qui: li proietta value/rigoristi.py per status, non per persistenza.
COMPONENTI_FM = ("c_voto", "c_azione", "c_malus", "c_port")

EMIVITA_STAGIONI = 2.0       # dimezzamento del peso delle stagioni (~2 stagioni)


def _k_da_pendenza(slope: float, campione_tipico: float) -> float:
    """Peso del prior (in unita' di campione) coerente con la persistenza a una
    stagione. La pendenza anno-su-anno misurata E' l'affidabilita' di una
    stagione: slope = n/(n+K). Da qui K = n·(1−slope)/slope. Usare la pendenza
    come UNICA contrazione, non in aggiunta allo shrink empirico-bayesiano: erano
    due stime della stessa affidabilita' e applicarle entrambe sovra-contrae i
    giocatori con storico lungo (principio: mai contrarre due volte la stessa
    cosa). Cosi' chi ha sei stagioni stabili regredisce poco, chi ne ha una tanto.
    """
    s = min(max(slope, 0.05), 0.95)
    return campione_tipico * (1.0 - s) / s


@dataclass(frozen=True)
class ParametriRuolo:
    comp_media: dict[str, dict[str, float]]     # [componente][ruolo] media
    comp_pendenza: dict[str, dict[str, float]]  # [componente][ruolo] persistenza
    pv_media: dict[str, float]
    pendenza_pv: dict[str, float]


def _ols_pendenza(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, float); y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 5 or x[ok].std() < 1e-9:
        return 0.5
    return float(np.polyfit(x[ok], y[ok], 1)[0])


def parametri_ruolo(m: pd.DataFrame, min_pv: int = 10) -> ParametriRuolo:
    """Medie e pendenze per ruolo e per componente, misurate dai dati."""
    comp_media = {c: {} for c in COMPONENTI_FM}
    pv_media = {}
    for r in RUOLI:
        g = m[(m.ruolo == r) & (m.Pv >= 15)]
        for c in COMPONENTI_FM:
            comp_media[c][r] = float(np.average(g[c], weights=g.Pv))
        pv_media[r] = float(g.Pv.mean())

    ord_ = sorted(m.stagione.unique())
    coppie = []
    for a, b in zip(ord_, ord_[1:]):
        x = m[m.stagione == a].set_index("Id")
        y = m[m.stagione == b].set_index("Id")
        j = x.join(y, rsuffix="_n", how="inner")
        coppie.append(j[(j.Pv >= min_pv) & (j.Pv_n >= min_pv)])
    P = pd.concat(coppie)
    comp_pend = {c: {} for c in COMPONENTI_FM}
    pendenza_pv = {}
    for r in RUOLI:
        s = P[P.ruolo == r]
        for c in COMPONENTI_FM:
            comp_pend[c][r] = _ols_pendenza(s[c].values, s[f"{c}_n"].values)
        pendenza_pv[r] = _ols_pendenza(s.Pv.values, s.Pv_n.values)
    return ParametriRuolo(comp_media, comp_pend, pv_media, pendenza_pv)


def _peso_stagione(stagione: str, ordinate: list[str]) -> float:
    eta = len(ordinate) - ordinate.index(stagione)      # 1 = piu' recente
    return 0.5 ** ((eta - 1) / EMIVITA_STAGIONI)


def proietta(lega: LeagueRules = LEGA, giornata_corrente: int = 0,
             m: pd.DataFrame | None = None,
             par: ParametriRuolo | None = None) -> pd.DataFrame:
    """Proiezione BASE per giocatore con storico (senza la componente rigori,
    aggiunta a valle dal modello dei rigoristi). Una riga per (Id, ruolo).

    Colonne: Id, Nome, R (=ruolo), fm_base (per presenza, senza rigori),
    pv_proj, punti_base, n_eff. L'orizzonte viene da lega.giornate_residue.
    """
    if m is None:
        m = carica_componenti()
    if par is None:
        par = parametri_ruolo(m)
    stag = sorted(m.stagione.unique())
    m = m.copy()
    m["w"] = m.stagione.map(lambda s: _peso_stagione(s, stag))
    orizzonte = lega.giornate_residue(giornata_corrente)

    righe = []
    for (Id, R), g in m.groupby(["Id", "ruolo"]):
        g = g[g.Pv > 0]
        if g.empty:
            continue
        w = g.w.values
        wp = w * g.Pv.values
        n_eff = float(wp.sum())           # presenze pesate: affidabilita' della fm
        n_stag = float(w.sum())           # stagioni pesate: affidabilita' delle presenze

        # stadio 1 — fantamedia per componente: UNICA contrazione EB verso la
        # media di ruolo, con prior calibrato sulla persistenza della componente.
        # Piu' presenze pesate (n_eff) -> meno contrazione. Niente doppio shrink.
        fm_base = 0.0
        for c in COMPONENTI_FM:
            media = par.comp_media[c][R]
            K = _k_da_pendenza(par.comp_pendenza[c][R], par.pv_media[R])
            hist = float(np.average(g[c], weights=wp))
            r = n_eff / (n_eff + K)
            fm_base += media + r * (hist - media)

        # stadio 2 — presenze: EB del tasso di disponibilita' verso la media di
        # ruolo, affidabilita' in NUMERO DI STAGIONI (una stagione = un'osservazione
        # del tasso), prior calibrato sulla persistenza delle presenze.
        pv_hist38 = float(np.average(g.Pv, weights=w))
        K_pv = _k_da_pendenza(par.pendenza_pv[R], 1.0)     # in unita' di stagione
        r_pv = n_stag / (n_stag + K_pv)
        pv_proj38 = par.pv_media[R] + r_pv * (pv_hist38 - par.pv_media[R])
        pv_proj38 = float(np.clip(pv_proj38, 0, GIORNATE_STAGIONE_STORICA))
        pv_proj = pv_proj38 * orizzonte / GIORNATE_STAGIONE_STORICA

        righe.append(dict(
            Id=Id, Nome=g.Nome.iloc[-1], R=R,
            fm_base=round(fm_base, 3), pv_proj=round(pv_proj, 2),
            punti_base=round(fm_base * pv_proj, 2), n_eff=round(n_eff, 1)))
    return pd.DataFrame(righe)


def prior_di_ruolo(ruolo: str, lega: LeagueRules = LEGA,
                   giornata_corrente: int = 0,
                   par: ParametriRuolo | None = None) -> dict:
    """Proiezione per un giocatore SENZA storico Serie A: media di ruolo (somma
    delle componenti medie, rigori esclusi), presenze scontate. Mai esclusione:
    si segnala e si prezza col prior. Marcato `bassa_informazione`."""
    if par is None:
        par = parametri_ruolo(carica_componenti())
    orizzonte = lega.giornate_residue(giornata_corrente)
    fm = sum(par.comp_media[c][ruolo] for c in COMPONENTI_FM)
    pv38 = par.pv_media[ruolo] * 0.75          # sconto: profilo ignoto, non titolare certo
    pv = pv38 * orizzonte / GIORNATE_STAGIONE_STORICA
    return dict(fm_base=round(fm, 3), pv_proj=round(pv, 2),
                punti_base=round(fm * pv, 2), n_eff=0.0)
