"""Simulazione della lega: rose, formazione settimanale, valore marginale.

Perche' esiste (docs/METODO.md §7.1, §6.11). Il valore di un giocatore NON e' la
somma dei suoi punti sopra un rimpiazzo: quando un titolare non prende voto
entra un compagno di rosa, quindi le giornate saltate costano molto meno di
quanto dica il conteggio dei punti totali. Il valore vero e' quanto il
giocatore aggiunge al punteggio della SQUADRA, con la formazione scelta ogni
settimana fra chi gioca, e si misura per differenza:

    valore(i) = punti_squadra(rosa con i) − punti_squadra(rosa con il rimpiazzo)

E' il "contributo marginale simulato" che §7.1 prevedeva per i modificatori;
serve gia' senza, per via della panchina. Simulato su una lega di 8 rose
plausibili si scopre per esempio che per D, C e A il valore segue quasi
esattamente presenze × vantaggio per partita sul rimpiazzo (correlazione
0,93-0,98), mentre i punti totali sopra il rimpiazzo ci arrivano solo a
0,64-0,75: il vecchio listino premiava chi gioca tanto anche se mediocre.

Due sorgenti di settimane, stesso motore:
  - `settimane_simulate`: disponibilita' estratte dalle probabilita' proiettate,
    punti = rendimento atteso (per il listino);
  - `settimane_reali`: chi ha preso voto davvero e con che fantavoto, giornata
    per giornata (per il backtest economico).

Semplificazioni dichiarate: la formazione e' scelta sapendo chi giochera'
(infortuni e squalifiche si sanno prima; i `6*` imprevisti li copre la
panchina, quasi sempre con un pari ruolo); il limite di 5 sostituzioni e
l'ordine di panchina non sono simulati; disponibilita' indipendenti fra
giocatori.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from rules import LEGA, LeagueRules

RUOLI = ("P", "D", "C", "A")


@dataclass(frozen=True)
class Settimane:
    """Matrici settimana × giocatore per un universo di giocatori."""
    ids: np.ndarray            # (N,) codici
    ruolo: np.ndarray          # (N,) ruoli
    disponibile: np.ndarray    # (W, N) bool: prende voto quella settimana
    punti: np.ndarray          # (W, N) fantavoto della settimana se gioca
    atteso: np.ndarray         # (N,) rendimento atteso: l'ordine con cui si schiera
    scala: float               # moltiplicatore per passare da media/somma a stagione
    media: bool                # True: punteggio = media sulle W settimane × scala

    def indice(self) -> dict[int, int]:
        return {int(i): k for k, i in enumerate(self.ids)}


def settimane_simulate(proiezioni: pd.DataFrame, n_giornate: int,
                       settimane: int = 2000, seme: int = 0) -> Settimane:
    """Disponibilita' ~ Bernoulli(p_voto), punti = rendimento atteso per presenza
    (rigori inclusi). Colonne richieste: Id, ruolo, p_voto, fm_tot."""
    rng = np.random.default_rng(seme)
    p = proiezioni.p_voto.fillna(0).values
    fm = proiezioni.fm_tot.fillna(0).values
    disp = rng.random((settimane, len(p))) < p[None, :]
    return Settimane(ids=proiezioni.Id.values, ruolo=proiezioni.ruolo.values,
                     disponibile=disp, punti=np.broadcast_to(fm, disp.shape),
                     atteso=fm, scala=float(n_giornate), media=True)


def settimane_reali(giornate: pd.DataFrame, stagione: str, giocatori: pd.DataFrame,
                    da_giornata: int, atteso: pd.Series | None = None) -> Settimane:
    """Le giornate vere di una stagione: chi ha preso voto e il suo fantavoto.

    `atteso` e' l'ordine con cui il manager schiera; di default la fantamedia
    realizzata nella stagione (un manager che conosce il valore dei suoi ma non
    il risultato della singola giornata): riferimento indipendente dai modelli.
    """
    g = giornate[(giornate.stagione == stagione) & (giornate.giornata >= da_giornata)
                 & giornate.voto.notna()]
    tab = g.pivot_table(index="giornata", columns="Id", values="fv", aggfunc="sum")
    tab = tab.reindex(columns=giocatori.Id.values)
    disp = tab.notna().values
    punti = tab.fillna(0.0).values
    if atteso is None:
        atteso = g.groupby("Id").fv.mean()
    att = giocatori.Id.map(atteso).fillna(0.0).values
    return Settimane(ids=giocatori.Id.values, ruolo=giocatori.ruolo.values,
                     disponibile=disp, punti=punti, atteso=att, scala=1.0, media=False)


# --------------------------------------------------------------------------- #
# Formazione settimanale e punteggio di una rosa
# --------------------------------------------------------------------------- #
_MAX_PER_RUOLO = {"P": 1, "D": 5, "C": 5, "A": 3}


def punteggio_rosa(s: Settimane, rosa: np.ndarray,
                   lega: LeagueRules = LEGA) -> float:
    """Punti stagionali di una rosa (indici in `s`), formazione ottima ogni
    settimana: per ruolo i migliori disponibili per rendimento atteso, poi il
    modulo che massimizza il punteggio ATTESO; si incassa il punteggio della
    settimana. Uno slot che non si riesce a coprire vale 0."""
    W = s.disponibile.shape[0]
    att_k, real_k = {}, {}
    for r in RUOLI:
        idx = rosa[s.ruolo[rosa] == r]
        idx = idx[np.argsort(-s.atteso[idx], kind="stable")]
        kmax = _MAX_PER_RUOLO[r]
        A = s.disponibile[:, idx]
        cnt = np.cumsum(A, axis=1)
        e = np.zeros((W, kmax + 1))
        v = np.zeros((W, kmax + 1))
        att = s.atteso[idx]
        pts = s.punti[:, idx]
        for k in range(1, kmax + 1):
            sel = A & (cnt <= k)
            e[:, k] = sel @ att
            v[:, k] = (sel * pts).sum(axis=1)
        att_k[r], real_k[r] = e, v
    migliore_att = np.full(W, -np.inf)
    incasso = np.zeros(W)
    for d, c, a in lega.moduli:
        e = att_k["P"][:, 1] + att_k["D"][:, d] + att_k["C"][:, c] + att_k["A"][:, a]
        v = real_k["P"][:, 1] + real_k["D"][:, d] + real_k["C"][:, c] + real_k["A"][:, a]
        meglio = e > migliore_att
        migliore_att = np.where(meglio, e, migliore_att)
        incasso = np.where(meglio, v, incasso)
    return float(incasso.mean() * s.scala if s.media else incasso.sum() * s.scala)


# --------------------------------------------------------------------------- #
# Rose: draft a serpentina per valore, con i vincoli di slot per ruolo
# --------------------------------------------------------------------------- #
def draft(valore: np.ndarray, ruolo: np.ndarray,
          lega: LeagueRules = LEGA) -> list[np.ndarray]:
    """Rose di una lega plausibile: a turno ogni squadra prende il giocatore di
    valore piu' alto fra quelli dei ruoli in cui ha ancora posto."""
    slot = lega.rosa.slot
    ordine = np.argsort(-valore, kind="stable")
    preso = np.zeros(len(valore), bool)
    rose = [[] for _ in range(lega.squadre)]
    posti = [dict(slot) for _ in range(lega.squadre)]
    giri = sum(slot.values())
    for giro in range(giri):
        turno = range(lega.squadre) if giro % 2 == 0 else range(lega.squadre - 1, -1, -1)
        for t in turno:
            for j in ordine:
                if not preso[j] and posti[t][ruolo[j]] > 0:
                    preso[j] = True
                    posti[t][ruolo[j]] -= 1
                    rose[t].append(j)
                    break
    return [np.array(r, dtype=int) for r in rose]


def rimpiazzi(valore: np.ndarray, ruolo: np.ndarray,
              rose: list[np.ndarray]) -> dict[str, int]:
    """Il miglior giocatore libero per ruolo: quello che si prende a 1 credito."""
    preso = np.zeros(len(valore), bool)
    for r in rose:
        preso[r] = True
    out = {}
    for r in RUOLI:
        liberi = np.where(~preso & (ruolo == r))[0]
        out[r] = int(liberi[np.argmax(valore[liberi])])
    return out


def valore_marginale(s: Settimane, rose: list[np.ndarray], fa: dict[str, int],
                     candidati: np.ndarray | None = None,
                     lega: LeagueRules = LEGA) -> np.ndarray:
    """Valore di ogni candidato per una squadra media della lega.

    Per ogni rosa T e candidato i del ruolo r: si toglie da T il giocatore w
    (i stesso se e' in T, altrimenti il meno prezioso del ruolo in T) e si
    confronta T−w+i con T−w+rimpiazzo. Media sulle rose. Per chi e' in rosa e'
    la definizione per differenza; per chi non lo e' risponde a "quanto
    migliorerebbe una squadra se lo prendesse al posto del suo peggiore".
    """
    N = len(s.ids)
    if candidati is None:
        candidati = np.arange(N)
    tot = np.zeros(N)
    for T in rose:
        base = punteggio_rosa(s, T, lega)
        # contributo di ogni membro rispetto al rimpiazzo del suo ruolo
        contributo = {}
        for j in T:
            senza = np.where(T == j, fa[s.ruolo[j]], T)
            contributo[j] = base - punteggio_rosa(s, senza, lega)
        peggiore, rif = {}, {}
        for r in RUOLI:
            membri = [j for j in T if s.ruolo[j] == r]
            w = min(membri, key=lambda j: contributo[j])
            peggiore[r] = w
            rif[r] = np.where(T == w, fa[r], T)          # T − w + rimpiazzo
        rif_punti = {r: punteggio_rosa(s, rif[r], lega) for r in RUOLI}
        in_T = set(T.tolist())
        for i in candidati:
            r = s.ruolo[i]
            if i in in_T:
                tot[i] += contributo[i]
            elif i == fa[r]:
                continue                                  # vale 0 per definizione
            else:
                con_i = np.where(rif[r] == fa[r], i, rif[r])
                tot[i] += punteggio_rosa(s, con_i, lega) - rif_punti[r]
    return tot / len(rose)
