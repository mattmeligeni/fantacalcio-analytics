"""Parser dei file Voti Fantacalcio.it (giocatore × giornata).

Gestisce tutte le trappole di docs/DATI.md §1:
  - tre fogli, si usa SOLO `Fantacalcio` (la redazione agganciata alla lega);
  - organizzazione a blocchi per squadra (riga col solo nome squadra, poi
    intestazione, poi i giocatori): il parser mantiene lo stato della squadra;
  - righe `ALL` (allenatori) da scartare;
  - `Voto` e' testo: contiene sia `6.5` sia `6*` (senza voto);
  - solo chi e' sceso in campo compare nel file.

Il parser fallisce rumorosamente se le colonne attese non ci sono (convenzione
docs/DATI.md §9). Scrive niente: restituisce DataFrame in memoria.
"""
from __future__ import annotations

import glob
import pathlib
import re

import pandas as pd

# Intestazione attesa del blocco giocatori (docs/DATI.md §1).
COLONNE = ["Cod.", "Ruolo", "Nome", "Voto",
           "Gf", "Gs", "Rp", "Rs", "Rf", "Au", "Amm", "Esp", "Ass"]
NUMERICHE = ["Gf", "Gs", "Rp", "Rs", "Rf", "Au", "Amm", "Esp", "Ass"]
RUOLI_VALIDI = {"P", "D", "C", "A"}


def _stagione_da_nome(path: str) -> str:
    m = re.search(r"Stagione_(\d{4})_(\d{2})", path)
    if not m:
        raise ValueError(f"stagione non riconosciuta nel nome file: {path}")
    return f"{m.group(1)}-{m.group(2)}"


def _giornata_da_nome(path: str) -> int:
    m = re.search(r"Giornata_(\d+)", path)
    if not m:
        raise ValueError(f"giornata non riconosciuta nel nome file: {path}")
    return int(m.group(1))


def leggi_giornata(path: str) -> pd.DataFrame:
    """Un file .xlsx di una giornata -> righe tidy (una per giocatore sceso).

    Colonne di uscita: stagione, giornata, squadra, Cod., Ruolo, Nome, Voto (str
    grezza), e le colonne evento numeriche. La conversione di `Voto` in float o
    None e' lasciata al motore (`rules.da_voto_testuale`) per non perdere la
    distinzione fra `6*` e voto reale.
    """
    raw = pd.read_excel(path, sheet_name="Fantacalcio", header=None, dtype=str)

    squadra: str | None = None
    header_visto = False
    righe: list[dict] = []

    for _, r in raw.iterrows():
        cella0 = (r[0] or "").strip() if isinstance(r[0], str) else (
            "" if pd.isna(r[0]) else str(r[0]).strip())
        # intestazione del blocco: prima colonna == "Cod."
        if cella0 == "Cod.":
            header_visto = True
            continue
        # riga col solo nome squadra: prima colonna piena, resto vuoto
        resto_vuoto = all(pd.isna(r[c]) for c in range(1, raw.shape[1]))
        if cella0 and resto_vuoto:
            # salta le righe di intestazione/copyright in cima al foglio
            if header_visto or _sembra_squadra(cella0):
                squadra = cella0
            continue
        if not cella0:
            continue
        ruolo = (r[1] or "").strip() if isinstance(r[1], str) else ""
        if ruolo not in RUOLI_VALIDI:      # scarta ALL (allenatori) e rumore
            continue
        righe.append({
            "squadra": squadra,
            "Cod.": cella0,
            "Ruolo": ruolo,
            "Nome": (r[2] or "").strip() if isinstance(r[2], str) else r[2],
            "Voto": r[3],
            **{c: r[COLONNE.index(c)] for c in NUMERICHE},
        })

    if not righe:
        raise ValueError(f"nessuna riga giocatore estratta da {path} "
                         "(struttura del foglio cambiata?)")

    df = pd.DataFrame(righe)
    for c in NUMERICHE:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["Cod."] = pd.to_numeric(df["Cod."], errors="coerce").astype("Int64")
    df["stagione"] = _stagione_da_nome(path)
    df["giornata"] = _giornata_da_nome(path)
    if df["squadra"].isna().any():
        raise ValueError(f"righe senza squadra in {path}: stato squadra perso")
    return df


def _sembra_squadra(s: str) -> bool:
    """Euristica difensiva: una riga di squadra e' testo breve senza cifre."""
    return len(s) <= 30 and not any(ch.isdigit() for ch in s) and \
        "fantacalcio" not in s.lower() and "www." not in s.lower()


def leggi_stagione(cartella: str) -> pd.DataFrame:
    """Tutte le giornate di una cartella stagione, concatenate e ordinate."""
    files = sorted(glob.glob(str(pathlib.Path(cartella) / "*.xlsx")),
                   key=_giornata_da_nome)
    if not files:
        raise FileNotFoundError(f"nessun .xlsx in {cartella}")
    df = pd.concat([leggi_giornata(f) for f in files], ignore_index=True)
    return df.sort_values(["giornata", "squadra", "Ruolo"]).reset_index(drop=True)
