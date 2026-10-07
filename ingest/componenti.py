"""Pannello giocatore × stagione scomposto in componenti del fantavoto.

Perche' dai voti per giornata e non dalle Statistiche: la fantamedia va scomposta
in parti con persistenze diverse e contratte separatamente (docs/METODO.md §6.5bis).
Le Statistiche non lo permettono in modo esatto perche' la colonna `Amm` conta
anche i cartellini presi in gare senza voto (anomalia §2): la ricomposizione
sbaglia di multipli di 0,5. I voti per giornata danno l'`Amm` corretto (solo
sulle presenze con voto) e un `Gf` gia' al netto dei rigori, quindi la
scomposizione ricompone la fantamedia in modo esatto.

Le cinque componenti (per presenza), la cui somma e' la fantamedia di lega
(imbattibilita' inclusa per i portieri):
  c_voto   = Mv
  c_azione = (3·gol_su_azione + assist) / Pv
  c_rigore = (3·rigori_segnati − 3·rigori_sbagliati) / Pv
  c_malus  = (−0,5·amm − esp − 2·autogol) / Pv
  c_port   = (−gol_subiti + 3·rigori_parati + imbattibilita') / Pv   [solo P]

Il pannello viene messo in cache in data/panel/, rigenerabile.
"""
from __future__ import annotations

import glob
import pathlib

import numpy as np
import pandas as pd

from ingest.voti import leggi_stagione
from rules import da_voto_testuale

PANEL = pathlib.Path("data/panel")
CACHE = PANEL / "componenti_stagione.csv"
VOTI_DIR = pathlib.Path("data/raw/Voti")

COMPONENTI = ["c_voto", "c_azione", "c_rigore", "c_malus", "c_port"]


def _aggrega(voti_root: str) -> pd.DataFrame:
    parti = []
    for c in sorted(p for p in glob.glob(f"{voti_root}/*")
                    if pathlib.Path(p).is_dir()):
        df = leggi_stagione(c)
        df["vn"] = df["Voto"].map(da_voto_testuale)
        v = df[df.vn.notna()].copy()
        v["cs"] = ((v.Ruolo == "P") & (v.Gs == 0)).astype(int)
        g = v.groupby(["Cod.", "stagione"]).agg(
            ruolo=("Ruolo", lambda s: s.mode().iloc[0]),
            squadra=("squadra", lambda s: s.mode().iloc[0]),
            Nome=("Nome", lambda s: s.mode().iloc[0]),
            Pv=("vn", "size"), Mv=("vn", "mean"),
            gf=("Gf", "sum"), rf=("Rf", "sum"), rs=("Rs", "sum"),
            ass=("Ass", "sum"), amm=("Amm", "sum"), esp=("Esp", "sum"),
            au=("Au", "sum"), gs=("Gs", "sum"), rp=("Rp", "sum"),
            cs=("cs", "sum"),
        ).reset_index()
        parti.append(g)
    m = pd.concat(parti, ignore_index=True)
    Pv = m.Pv
    m["c_voto"] = m.Mv
    m["c_azione"] = (3 * m.gf + m.ass) / Pv
    m["c_rigore"] = (3 * m.rf - 3 * m.rs) / Pv
    m["c_malus"] = (-0.5 * m.amm - m.esp - 2 * m.au) / Pv
    m["c_port"] = np.where(m.ruolo == "P", (-m.gs + 3 * m.rp + m.cs) / Pv, 0.0)
    m["fm_lega"] = m[COMPONENTI].sum(axis=1)
    return m.rename(columns={"Cod.": "Id"})


def carica_componenti(rigenera: bool = False) -> pd.DataFrame:
    """Pannello componenti, dalla cache se c'e' e non si chiede la rigenerazione.

    Controllo indipendente all'ingresso (principio: ogni numero ha un controllo):
    la somma delle componenti deve ricomporre la fantamedia di lega a meno
    dell'arrotondamento. Se non torna, la cache e' corrotta e va rigenerata.
    """
    if CACHE.exists() and not rigenera:
        m = pd.read_csv(CACHE)
        if abs((m[COMPONENTI].sum(axis=1) - m.fm_lega)).max() < 1e-6:
            return m
    m = _aggrega(str(VOTI_DIR))
    PANEL.mkdir(parents=True, exist_ok=True)
    m.to_csv(CACHE, index=False)
    return m


if __name__ == "__main__":
    m = carica_componenti(rigenera=True)
    print(f"pannello componenti: {len(m)} giocatore-stagione, {m.stagione.nunique()} stagioni")
    ric = (m[COMPONENTI].sum(axis=1) - m.fm_lega).abs().max()
    print(f"controllo ricomposizione (max scarto vs fm_lega): {ric:.2e}")
    print("\nmedia componenti per ruolo (Pv>=15):")
    g = m[m.Pv >= 15]
    print(g.groupby("ruolo")[COMPONENTI].mean().round(2).to_string())
