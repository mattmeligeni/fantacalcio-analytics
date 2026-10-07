"""Caricamento dei pannelli per la valutazione: Statistiche stagionali (verita'
di rendimento), imbattibilita' dei portieri ricostruita dai voti per giornata,
e listone 2026-27 (universo degli acquistabili).

Niente parquet, tutto in memoria. I loader falliscono rumorosamente se le colonne
attese non ci sono (convenzione docs/DATI.md §9).
"""
from __future__ import annotations

import glob
import pathlib
import re

import numpy as np
import pandas as pd

RAW = pathlib.Path("data/raw")
STAT_DIR = RAW / "Statistiche Fantacalcio"
VOTI_DIR = RAW / "Voti"
LISTONE = RAW / "Listone_20_08_26.xlsx"

STAT_NUM = ["Pv", "Mv", "Fm", "Gf", "Gs", "Rp", "Rc", "R+", "R-",
            "Ass", "Amm", "Esp", "Au"]


# --------------------------------------------------------------------------- #
# Statistiche stagionali per giocatore
# --------------------------------------------------------------------------- #
def _stagione_da_nome(path: str) -> str:
    return re.search(r"(\d{4}_\d{2})", path).group(1).replace("_", "-")


def carica_statistiche(cartella: str = str(STAT_DIR)) -> pd.DataFrame:
    """Pannello giocatore × stagione dalle Statistiche (foglio `Tutti`).

    `punti` = Fm × Pv, i punti totali di stagione SENZA imbattibilita' (le
    Statistiche non la conteggiano, docs/DATI.md §2). Per i punti con
    imbattibilita' vedi `con_imbattibilita`.
    """
    files = sorted(glob.glob(f"{cartella}/Statistiche_*.xlsx"))
    if not files:
        raise FileNotFoundError(f"nessun Statistiche_*.xlsx in {cartella}")
    parti = []
    for f in files:
        d = pd.read_excel(f, sheet_name="Tutti", header=1)
        mancanti = [c for c in ["Id", "R", "Nome", "Squadra", *STAT_NUM]
                    if c not in d.columns]
        if mancanti:
            raise ValueError(f"{f}: colonne mancanti {mancanti}")
        for c in STAT_NUM:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d["stagione"] = _stagione_da_nome(f)
        parti.append(d)
    df = pd.concat(parti, ignore_index=True)
    df["punti"] = df.Fm * df.Pv
    return df


# --------------------------------------------------------------------------- #
# Imbattibilita' dei portieri, ricostruita dai voti per giornata
# --------------------------------------------------------------------------- #
def clean_sheet_portieri() -> pd.DataFrame:
    """Clean sheet per (Id, stagione): giornate con ruolo P, voto reale e
    Gs == 0. E' il conteggio dell'imbattibilita' attiva in questa lega, che le
    Statistiche NON includono (docs/DATI.md §2, docs/METODO.md §6.3).

    Deriva dal pannello componenti gia' in cache (colonna `cs`), che aggrega i
    voti per giornata una volta sola: evita di riparsare tutti gli .xlsx a ogni
    chiamata.
    """
    from ingest.componenti import carica_componenti
    m = carica_componenti()
    p = m[m.ruolo == "P"]
    return (p[["Id", "stagione", "cs", "Pv"]]
            .rename(columns={"Id": "Cod.", "cs": "clean_sheet", "Pv": "pv_voti"})
            .reset_index(drop=True))


def con_imbattibilita(stat: pd.DataFrame | None = None,
                      cs: pd.DataFrame | None = None) -> pd.DataFrame:
    """Aggiunge ai punti dei portieri i punti di imbattibilita' (+1 per clean
    sheet). Restituisce lo stesso pannello con la colonna `punti_imb`.

    Per i non-portieri `punti_imb == punti`. Il merge e' su (Id, stagione) con
    la chiave `Cod.` dei voti, che coincide con `Id` (docs/DATI.md §1).
    """
    if stat is None:
        stat = carica_statistiche()
    if cs is None:
        cs = clean_sheet_portieri()
    m = stat.merge(cs.rename(columns={"Cod.": "Id"})[["Id", "stagione",
                   "clean_sheet"]], on=["Id", "stagione"], how="left")
    m["clean_sheet"] = m.clean_sheet.fillna(0).astype(int)
    # l'imbattibilita' vale +1 punto a giornata, solo per i portieri
    m["punti_imb"] = m.punti + np.where(m.R == "P", m.clean_sheet, 0)
    return m


# --------------------------------------------------------------------------- #
# Listone 2026-27 — universo acquistabile
# --------------------------------------------------------------------------- #
def carica_listone(path: str = str(LISTONE), escludi_fuori_lista: bool = True) -> pd.DataFrame:
    """Listone di preparazione. Intestazione sulla PRIMA riga (header=0): nel
    file corrente NON e' sulla seconda come annota DATI §8, va letto cosi'.

    Restituisce colonne canoniche: Cod, Nome, ruolo, squadra, eta, fvm1000,
    quotazione. `PGv/MV/FM` sono a zero (listino di preparazione), non usarle.
    """
    d = pd.read_excel(path, header=0)
    attese = ["#", "Nome", "Fuori lista", "Sq.", "Under", "R.",
              "FVM/1000", "QUOT."]
    mancanti = [c for c in attese if c not in d.columns]
    if mancanti:
        raise ValueError(f"{path}: colonne mancanti {mancanti}")
    if escludi_fuori_lista:
        d = d[d["Fuori lista"].isna()].copy()
    out = pd.DataFrame({
        "Cod": pd.to_numeric(d["#"], errors="coerce").astype("Int64"),
        "Nome": d["Nome"].astype(str).str.strip(),
        "ruolo": d["R."].astype(str).str.strip(),
        "squadra": d["Sq."].astype(str).str.strip(),
        "eta": pd.to_numeric(d["Under"], errors="coerce"),
        "fvm1000": pd.to_numeric(d["FVM/1000"], errors="coerce"),
        "quotazione": pd.to_numeric(d["QUOT."], errors="coerce"),
    })
    out["fvm_meta"] = out.fvm1000 / 2.0     # FVM/1000 -> base 500 (dividere per 2)
    return out.reset_index(drop=True)
