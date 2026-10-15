"""Pannelli unificati su cui lavorano modelli e backtest.

Due livelli, entrambi derivati dai grezzi e messi in cache in data/panel/:

1. **giocatore × giornata** (`carica_giornate`): una riga per ogni giocatore
   sceso in campo, con voto (NaN se `6*`), eventi, fantavoto calcolato dal
   motore di regolamento e le quattro famiglie di bonus (azione, rigore, malus,
   portiere). E' la serie temporale: serve a misurare la disponibilita' per
   tratti di stagione, a osservare le prime giornate prima dell'asta e a
   calcolare i punti realizzati sulle giornate che contano (dalla 3ª).

2. **giocatore × stagione** (`pannello_stagioni`): l'UNIONE dei tesserati delle
   Statistiche (che includono chi non ha mai preso voto, `Pv = 0`) e degli
   aggregati dei voti. Il pannello componenti della versione precedente nasceva
   solo dai voti, quindi le stagioni passate a zero presenze sparivano: per la
   disponibilita' era il buco piu' grave, perche' sono proprio i casi in cui un
   giocatore smette di giocare.

Convenzioni verificate (docs/DATI.md §1, §6.6): nei voti `Gf` = soli gol su
azione, `Rf` = gol su rigore, `Rs` = rigori sbagliati; `6*` = senza voto, conta
come assenza.
"""
from __future__ import annotations

import glob
import pathlib

import numpy as np
import pandas as pd

from ingest.fonti import carica_statistiche
from ingest.voti import leggi_stagione
from rules import LEGA, LeagueRules, componenti_bonus, da_voto_testuale

PANEL = pathlib.Path("data/panel")
CACHE_GIORNATE = PANEL / "voti_giornata.csv"
VOTI_DIR = pathlib.Path("data/raw/Voti")

EVENTI = ["gf", "gs", "rp", "rs", "rf", "au", "amm", "esp", "ass"]
FAMIGLIE = ["c_azione", "c_rigore", "c_malus", "c_port"]


# --------------------------------------------------------------------------- #
# giocatore × giornata
# --------------------------------------------------------------------------- #
def _costruisci_giornate(voti_root: pathlib.Path, lega: LeagueRules) -> pd.DataFrame:
    cartelle = sorted(p for p in glob.glob(f"{voti_root}/*") if pathlib.Path(p).is_dir())
    if not cartelle:
        raise FileNotFoundError(f"nessuna cartella stagione in {voti_root}")
    df = pd.concat([leggi_stagione(c) for c in cartelle], ignore_index=True)
    df = df.rename(columns={"Cod.": "Id", "Ruolo": "ruolo", "Gf": "gf", "Gs": "gs",
                            "Rp": "rp", "Rs": "rs", "Rf": "rf", "Au": "au",
                            "Amm": "amm", "Esp": "esp", "Ass": "ass"})
    if df.Id.isna().any():
        raise ValueError("righe voti senza codice giocatore")
    df["Id"] = df.Id.astype(int)
    df["sv"] = df.Voto.astype(str).str.contains(r"\*", regex=True)
    df["voto"] = df.Voto.map(da_voto_testuale).astype(float)
    df = df.drop(columns="Voto")
    return _aggiungi_fantavoto(df, lega)


def _aggiungi_fantavoto(df: pd.DataFrame, lega: LeagueRules) -> pd.DataFrame:
    c = componenti_bonus(df, lega)
    ha_voto = df.voto.notna()
    # bonus e malus valgono solo sulle presenze con voto: su un `6*` il
    # cartellino non entra nella fantamedia (docs/DATI.md §2)
    for fam in ("azione", "rigore", "malus", "port"):
        df[f"c_{fam}"] = np.where(ha_voto, c[fam], np.nan)
    df["cs"] = c["cs"].astype(int)
    df["fv"] = df.voto + df[FAMIGLIE].sum(axis=1, min_count=1)
    return df


def carica_giornate(rigenera: bool = False, lega: LeagueRules = LEGA) -> pd.DataFrame:
    """Pannello giocatore × giornata, dalla cache se valida.

    Controllo all'ingresso: il fantavoto in cache deve ricomporsi esattamente da
    voto + famiglie di bonus (stesso controllo della versione precedente sulle
    componenti stagionali, qui riga per riga).
    """
    if CACHE_GIORNATE.exists() and not rigenera:
        df = pd.read_csv(CACHE_GIORNATE)
        ric = (df.voto + df[FAMIGLIE].sum(axis=1, min_count=1) - df.fv).abs().max()
        if len(df) > 0 and ric < 1e-9:
            return df
    df = _costruisci_giornate(VOTI_DIR, lega)
    PANEL.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE_GIORNATE, index=False)
    return df


# --------------------------------------------------------------------------- #
# giocatore × stagione
# --------------------------------------------------------------------------- #
def aggrega_voti(g: pd.DataFrame) -> pd.DataFrame:
    """Aggregati per (stagione, Id) di un pezzo qualunque del pannello giornate.

    Somme e conteggi, mai medie: le medie si ricavano dividendo per `pv` a valle,
    cosi' due tratti di stagione si possono sommare senza errori di peso.
    """
    v = g.assign(pv=g.voto.notna().astype(int), sv=g.sv.astype(int),
                 rc=g.rf + g.rs)
    v["voto_s"] = v.voto.fillna(0.0)
    for c in FAMIGLIE:
        v[c] = v[c].fillna(0.0)
    agg = v.groupby(["stagione", "Id"]).agg(
        pv=("pv", "sum"), sv=("sv", "sum"), voto_s=("voto_s", "sum"),
        c_azione=("c_azione", "sum"), c_rigore=("c_rigore", "sum"),
        c_malus=("c_malus", "sum"), c_port=("c_port", "sum"),
        gf=("gf", "sum"), rf=("rf", "sum"), rs=("rs", "sum"), rc=("rc", "sum"),
        gs=("gs", "sum"), cs=("cs", "sum"),
    ).reset_index()
    return agg


def pannello_stagioni(giornate: pd.DataFrame | None = None,
                      stat: pd.DataFrame | None = None) -> pd.DataFrame:
    """Tesserati × stagione: Statistiche (anche Pv = 0) unite agli aggregati voti.

    Colonne: stagione, Id, Nome, ruolo, squadra (fine stagione), squadra_inizio
    (prima squadra con cui compare nei voti), pv/sv e somme di eventi e famiglie
    dai voti, pv_g2 (presenze con voto nel girone di ritorno, giornate 20-38).

    Le presenze `pv` vengono dai voti (coerenti con le componenti); le
    Statistiche servono a sapere CHI era tesserato anche senza presenze.
    I ~8 giocatori/stagione presenti nei voti ma non nelle Statistiche (presenze
    poi ritirate, docs/DATI.md §6.7) restano, col ruolo dei voti.
    """
    if giornate is None:
        giornate = carica_giornate()
    if stat is None:
        stat = carica_statistiche()
    agg = aggrega_voti(giornate)
    ritorno = (giornate[giornate.giornata >= 20]
               .assign(pv=lambda d: d.voto.notna().astype(int))
               .groupby(["stagione", "Id"]).pv.sum().rename("pv_g2"))
    prima = (giornate.sort_values("giornata")
             .groupby(["stagione", "Id"])
             .agg(squadra_inizio=("squadra", "first"), ruolo_voti=("ruolo", "first"),
                  nome_voti=("Nome", "first"), prima_giornata=("giornata", "first"),
                  squadra_fine_voti=("squadra", "last")))
    s = stat[["stagione", "Id", "Nome", "R", "Squadra"]].rename(
        columns={"R": "ruolo", "Squadra": "squadra"})
    m = (s.merge(agg, on=["stagione", "Id"], how="outer", indicator=True)
          .merge(prima.reset_index(), on=["stagione", "Id"], how="left")
          .merge(ritorno.reset_index(), on=["stagione", "Id"], how="left"))
    m["in_statistiche"] = m.pop("_merge") != "right_only"
    m["Nome"] = m.Nome.fillna(m.nome_voti)
    m["ruolo"] = m.ruolo.fillna(m.ruolo_voti)
    m["squadra"] = m.squadra.fillna(m.squadra_fine_voti)
    conti = ["pv", "sv", "voto_s", *FAMIGLIE, "gf", "rf", "rs", "rc", "gs", "cs", "pv_g2"]
    m[conti] = m[conti].fillna(0)
    for c in ["pv", "sv", "gf", "rf", "rs", "rc", "gs", "cs", "pv_g2"]:
        m[c] = m[c].astype(int)
    if m.duplicated(["stagione", "Id"]).any():
        raise ValueError("pannello stagioni: (stagione, Id) non univoco")
    if m.ruolo.isna().any() or not set(m.ruolo) <= {"P", "D", "C", "A"}:
        raise ValueError("pannello stagioni: ruoli mancanti o inattesi")
    return m.drop(columns=["nome_voti", "ruolo_voti", "squadra_fine_voti"])


def punti_realizzati(giornate: pd.DataFrame, stagione: str,
                     da_giornata: int, a_giornata: int = 38) -> pd.DataFrame:
    """Punti e presenze REALIZZATI in un intervallo di giornate di una stagione.

    E' la grandezza obiettivo del backtest: i punti che un giocatore avrebbe
    portato in classifica dalla prima giornata conteggiata in poi (imbattibilita'
    inclusa, motore di regolamento di lega).
    """
    g = giornate[(giornate.stagione == stagione)
                 & giornate.giornata.between(da_giornata, a_giornata)]
    r = (g.assign(pv=g.voto.notna().astype(int))
          .groupby("Id").agg(punti=("fv", "sum"), pv=("pv", "sum"),
                             rigore=("c_rigore", "sum")))
    return r.reset_index()
