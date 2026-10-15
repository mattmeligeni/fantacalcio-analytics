"""Caricatori delle fonti grezze diverse dai voti per giornata: Statistiche
stagionali, listone, partite (xG Understat). Una funzione per fonte, colonne
canoniche in uscita, controllo esplicito delle colonne attese in ingresso.

Nomi squadra: lo schema canonico del progetto sono i nomi di Fantacalcio.it
(voti, Statistiche e listone coincidono gia', verificato). Le altre fonti si
mappano su quelli con una tabella esplicita e un controllo che fallisce se resta
un nome non mappato (docs/DATI.md §5 e §9: un join riuscito al 72% senza errori
e' il modo canonico in cui muoiono i progetti di dati).
"""
from __future__ import annotations

import glob
import pathlib
import re

import pandas as pd

RAW = pathlib.Path("data/raw")
PANEL = pathlib.Path("data/panel")
STAT_DIR = RAW / "Statistiche Fantacalcio"


def listone_recente(raw: pathlib.Path = RAW) -> pathlib.Path:
    """Il listone piu' recente in data/raw/ (Listone_GG_MM_AA.xlsx)."""
    def data(f):
        m = re.search(r"(\d{2})_(\d{2})_(\d{2})", f.stem)
        return (int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else (0, 0, 0)
    files = list(raw.glob("Listone_*.xlsx")) + list(raw.glob("Quotazioni_*.xlsx"))
    if not files:
        raise FileNotFoundError(f"nessun listone in {raw}")
    return max(files, key=data)


LISTONE = None       # di default il piu' recente: vedi listone_recente()
PARTITE = PANEL / "partite.csv"

STAT_NUM = ["Pv", "Mv", "Fm", "Gf", "Gs", "Rp", "Rc", "R+", "R-",
            "Ass", "Amm", "Esp", "Au"]

# Understat -> Fantacalcio. Solo i nomi che differiscono; gli altri coincidono.
SQUADRE_UNDERSTAT = {"AC Milan": "Milan", "Parma Calcio 1913": "Parma"}


def stagione_da_anno(anno: int) -> str:
    """Anno di inizio (convenzione di partite.csv) -> '2020-21'."""
    return f"{anno}-{(anno + 1) % 100:02d}"


# --------------------------------------------------------------------------- #
# Statistiche stagionali (verita' di riferimento per le presenze, Pv=0 inclusi)
# --------------------------------------------------------------------------- #
def carica_statistiche(cartella: str = str(STAT_DIR)) -> pd.DataFrame:
    """Pannello giocatore × stagione dal foglio `Tutti` (header sulla 2ª riga).

    Contiene anche i tesserati con `Pv = 0` (~17% per stagione): non sono
    spazzatura, sono il denominatore del rischio di rotazione (docs/DATI.md §2).
    `Squadra` e' il club di FINE stagione: chi si trasferisce a gennaio compare
    una volta sola, con il club d'arrivo.
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
        d["stagione"] = re.search(r"(\d{4}_\d{2})", f).group(1).replace("_", "-")
        parti.append(d)
    df = pd.concat(parti, ignore_index=True)
    if df.duplicated(["stagione", "Id"]).any():
        raise ValueError("Statistiche: (stagione, Id) non univoco")
    df["Pv"] = df.Pv.fillna(0).astype(int)
    return df


# --------------------------------------------------------------------------- #
# Listone — universo acquistabile della stagione d'asta
# --------------------------------------------------------------------------- #
def carica_listone(path: str | None = None,
                   escludi_fuori_lista: bool = True) -> pd.DataFrame:
    """Listone di preparazione. Intestazione sulla PRIMA riga (docs/DATI.md §8).

    Colonne canoniche: Id, Nome, ruolo, squadra, eta, fvm1000, quotazione,
    fvm_meta (FVM riportato a base 500). `PGv/MV/FM` sono a zero nel listone di
    preparazione e non si usano.
    """
    path = str(path or listone_recente())
    d = pd.read_excel(path, header=0)
    attese = ["#", "Nome", "Fuori lista", "Sq.", "Under", "R.",
              "FVM/1000", "QUOT."]
    mancanti = [c for c in attese if c not in d.columns]
    if mancanti:
        raise ValueError(f"{path}: colonne mancanti {mancanti}")
    if escludi_fuori_lista:
        d = d[d["Fuori lista"].isna()].copy()
    out = pd.DataFrame({
        "Id": pd.to_numeric(d["#"], errors="raise").astype(int),
        "Nome": d["Nome"].astype(str).str.strip(),
        "ruolo": d["R."].astype(str).str.strip(),
        "squadra": d["Sq."].astype(str).str.strip(),
        "eta": pd.to_numeric(d["Under"], errors="coerce"),
        "fvm1000": pd.to_numeric(d["FVM/1000"], errors="coerce"),
        "quotazione": pd.to_numeric(d["QUOT."], errors="coerce"),
    })
    if out.Id.duplicated().any():
        raise ValueError(f"{path}: codici duplicati nel listone")
    if not set(out.ruolo) <= {"P", "D", "C", "A"}:
        raise ValueError(f"{path}: ruoli inattesi {set(out.ruolo)}")
    out["fvm_meta"] = out.fvm1000 / 2.0     # FVM/1000 -> base 500
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Partite con xG Understat (generato da understat_setup.py, validato al 100%)
# --------------------------------------------------------------------------- #
def carica_partite(path: str = str(PARTITE)) -> pd.DataFrame:
    """Una riga per partita: stagione ('2020-21'), giornata, casa, ospite (nomi
    Fantacalcio), gol e xG Understat di casa e ospite.

    `partite.csv` ha una riga per partita vista dalla squadra di casa
    (`venue == Home`): `gf`/`ga` sono quindi i gol di casa/ospite.
    """
    p = pd.read_csv(path)
    attese = ["venue", "stagione", "giornata", "home", "away", "gf", "ga",
              "home_xg", "away_xg"]
    mancanti = [c for c in attese if c not in p.columns]
    if mancanti:
        raise ValueError(f"{path}: colonne mancanti {mancanti}")
    if not (p.venue == "Home").all():
        raise ValueError(f"{path}: attesa una riga per partita (venue == Home)")
    out = pd.DataFrame({
        "stagione": p.stagione.astype(int).map(stagione_da_anno),
        "giornata": p.giornata.astype(int),
        "casa": p.home.replace(SQUADRE_UNDERSTAT),
        "ospite": p.away.replace(SQUADRE_UNDERSTAT),
        "gol_casa": p.gf.astype(int),
        "gol_ospite": p.ga.astype(int),
        "xg_casa": p.home_xg.astype(float),
        "xg_ospite": p.away_xg.astype(float),
    })
    return out


def verifica_nomi_squadra(partite: pd.DataFrame, statistiche: pd.DataFrame) -> None:
    """Ogni (stagione, squadra) delle partite deve esistere nelle Statistiche e
    viceversa. Fallisce rumorosamente se la mappa dei nomi e' incompleta."""
    a = set(zip(partite.stagione, partite.casa)) | set(zip(partite.stagione, partite.ospite))
    b = set(zip(statistiche.stagione, statistiche.Squadra))
    if a != b:
        raise ValueError("nomi squadra non riconciliati fra partite e Statistiche: "
                         f"solo partite {sorted(a - b)[:5]}, solo Statistiche {sorted(b - a)[:5]}")
