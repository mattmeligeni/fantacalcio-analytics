"""Gerarchia dei rigoristi per squadra e stagione, con conversione individuale
contratta verso la media di lega.

Il rigore e' uno degli eventi piu' prevedibili del gioco e pesa molto: +3 se
segnato, -3 se sbagliato (docs/DATI.md §2). Chi li batte lo si sa in anticipo, e
la conversione individuale regredisce forte verso la media di lega, quindi va
contratta: pochi calci non dicono se uno converte al 90% o al 60%.

Semantica certa (verificata, era la domanda aperta §11.2): nelle Statistiche
`Rc` = rigori calciati, `R+` = segnati, `R-` = sbagliati, con `Rc = R+ + R-`.
Nei voti per giornata gli stessi eventi sono `Rf` (segnati) e `Rs` (sbagliati).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from rules import LEGA, LeagueRules
from value.dati import carica_statistiche

# --- coefficienti MISURATI (non piu' scelti a occhio) --------------------- #
# La conversione individuale quasi non persiste (corr 0,14, pendenza 0,12 su
# n=28): va contratta FORTE verso la media di lega. La contrazione precedente
# (pseudo-conteggio k=5) dava troppo peso al dato individuale.
PERSISTENZA_CONVERSIONE = 0.12
# Volume dei rigori: Rc_n = 0,28 + 0,45·Rc (per chi ne ha calciato almeno uno).
RC_INTERCETTA = 0.28
RC_PENDENZA = 0.45
# Cambio di club: un rigorista che RESTA fa in media 2,59 rigori l'anno dopo,
# uno che CAMBIA 0,76. Chi cambia club perde lo status: fattore 0,76/2,59.
FATTORE_CAMBIO_CLUB = 0.76 / 2.59
EMIVITA_STAGIONI = 2.0
GIORNATE_STAGIONE_STORICA = 38


def conversione_lega(stat: pd.DataFrame | None = None) -> float:
    """Conversione media di lega, pooled sulle 6 stagioni (~0,79)."""
    if stat is None:
        stat = carica_statistiche()
    return float(stat["R+"].sum() / stat["Rc"].sum())


def _contrai(segnati: float, calciati: float, p0: float,
             pendenza: float = PERSISTENZA_CONVERSIONE) -> float:
    """Conversione contratta verso il prior di lega con la pendenza misurata:
    conv_proj = media_lega + pendenza·(conv_individuale − media_lega). Con
    pendenza 0,12 il dato individuale sposta pochissimo il prior, come dev'essere
    per una variabile che non persiste."""
    calc = np.asarray(calciati, dtype=float)
    conv_ind = np.divide(segnati, calc, out=np.full_like(calc, p0), where=calc > 0)
    return p0 + pendenza * (conv_ind - p0)


def valore_atteso_rigore(conversione: float) -> float:
    """Punti attesi per rigore calciato: +3 se segnato, -3 se sbagliato."""
    return (2.0 * conversione - 1.0) * 3.0


def rigoristi_carriera(stat: pd.DataFrame | None = None) -> pd.DataFrame:
    """Un rigorista per riga, aggregato sulle stagioni disponibili.

    Colonne: Id, Nome, R, calciati, segnati, conv_grezza, conv_contratta,
    valore_per_rigore. Ordinato per calciati decrescente.
    """
    if stat is None:
        stat = carica_statistiche()
    p0 = conversione_lega(stat)
    g = (stat[stat.Rc > 0]
         .groupby(["Id", "Nome", "R"], as_index=False)
         .agg(calciati=("Rc", "sum"), segnati=("R+", "sum"),
              stagioni=("stagione", "nunique")))
    g["conv_grezza"] = g.segnati / g.calciati
    g["conv_contratta"] = _contrai(g.segnati, g.calciati, p0)
    g["valore_per_rigore"] = g.conv_contratta.map(valore_atteso_rigore)
    return g.sort_values("calciati", ascending=False).reset_index(drop=True)


def gerarchia_per_squadra(stat: pd.DataFrame | None = None,
                          stagione: str | None = None) -> pd.DataFrame:
    """Chi batte i rigori in ogni squadra, per stagione.

    Per ogni (stagione, squadra) ordina i giocatori per rigori calciati e ne
    calcola la quota sui rigori di squadra. Il rigorista designato e' il primo;
    `quota` dice quanto e' netta la gerarchia (1,0 = rigorista unico).
    """
    if stat is None:
        stat = carica_statistiche()
    p0 = conversione_lega(stat)
    df = stat[stat.Rc > 0].copy()
    if stagione is not None:
        df = df[df.stagione == stagione]
    df["tot_sq"] = df.groupby(["stagione", "Squadra"]).Rc.transform("sum")
    df["quota"] = df.Rc / df.tot_sq
    df["conv_contratta"] = _contrai(df["R+"], df.Rc, p0)
    df["rango"] = (df.groupby(["stagione", "Squadra"]).Rc
                   .rank(ascending=False, method="first").astype(int))
    cols = ["stagione", "Squadra", "rango", "Nome", "R", "Rc", "R+", "R-",
            "quota", "conv_contratta"]
    return (df[cols].sort_values(["stagione", "Squadra", "rango"])
            .reset_index(drop=True))


def _peso_stagione(stagione: str, ordinate: list[str]) -> float:
    eta = len(ordinate) - ordinate.index(stagione)
    return 0.5 ** ((eta - 1) / EMIVITA_STAGIONI)


def _norm_squadra(s) -> str:
    return str(s).strip().lower().replace("hellas ", "").replace("ac ", "")


def proietta_rigori(lega: LeagueRules = LEGA, giornata_corrente: int = 0,
                    stat: pd.DataFrame | None = None,
                    squadra_2026: dict[int, str] | None = None) -> pd.DataFrame:
    """Punti attesi dai rigori per giocatore, sull'orizzonte residuo.

    La variabile che conta e' lo STATUS di rigorista, non la precisione della
    conversione (2.2): un rigorista da 5 penalty vale ~9 punti in piu' di un non
    rigorista, mentre convertire a 0,88 invece che 0,79 vale ~1,5 punti. Quindi:
      - volume atteso di rigori dalla persistenza misurata (Rc_n = 0,28 + 0,45·Rc
        pesato per decadimento), azzerato per chi non ne ha mai calciati;
      - fattore di cambio club: chi cambia squadra perde lo status designato;
      - conversione contratta FORTE verso la media di lega (pendenza 0,12).

    `squadra_2026` mappa Id -> squadra del listone: se manca o differisce
    dall'ultima squadra storica, si applica il fattore di cambio club.
    """
    if stat is None:
        stat = carica_statistiche()
    p0 = conversione_lega(stat)
    orizzonte = lega.giornate_residue(giornata_corrente)
    stag = sorted(stat.stagione.unique())
    st = stat.copy()
    st["w"] = st.stagione.map(lambda s: _peso_stagione(s, stag))

    righe = []
    for Id, g in st.groupby("Id"):
        rc_hist = float(np.average(g.Rc, weights=g.w))
        if rc_hist <= 0:
            continue                                   # mai un rigorista: 0 punti
        seg = float(g["R+"].sum())
        cal = float(g.Rc.sum())
        conv = _contrai(seg, cal, p0)
        rigori_attesi = RC_INTERCETTA + RC_PENDENZA * rc_hist

        ultima = g.sort_values("stagione").iloc[-1].Squadra
        sq26 = (squadra_2026 or {}).get(Id)
        cambia = sq26 is not None and _norm_squadra(sq26) != _norm_squadra(ultima)
        if cambia:
            rigori_attesi *= FATTORE_CAMBIO_CLUB

        rigori_attesi *= orizzonte / GIORNATE_STAGIONE_STORICA
        righe.append(dict(
            Id=Id, rigori_attesi=round(rigori_attesi, 2),
            conv_proj=round(float(conv), 3),
            rigore_punti=round(rigori_attesi * valore_atteso_rigore(float(conv)), 2),
            cambio_club=bool(cambia)))
    return pd.DataFrame(righe)


if __name__ == "__main__":
    stat = carica_statistiche()
    print(f"conversione di lega (pooled 6 stagioni): {conversione_lega(stat):.3f}\n")
    print("=== Top 15 rigoristi per volume (6 stagioni) ===")
    r = rigoristi_carriera(stat)
    print(r.head(15).round(3).to_string(index=False))
    print("\n=== Punti attesi dai rigori 2026-27 (top 12) ===")
    pr = proietta_rigori(stat=stat).merge(
        r[["Id", "Nome"]], on="Id", how="left")
    print(pr.nlargest(12, "rigore_punti").round(2).to_string(index=False))
