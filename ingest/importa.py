"""Import dei file scaricati da Fantacalcio.it e da Understat (soccerdata).

Regola del progetto: i grezzi non si modificano e non si sovrascrivono mai.
Ogni import COPIA i file in data/raw/ con la data di scarico nel nome, cosi'
ogni snapshot resta ricostruibile.

Dove finiscono:
  - stagioni CONCLUSE: `Statistiche_Fantacalcio_Stagione_AAAA_AA.xlsx` in
    data/raw/Statistiche Fantacalcio/ (letto da ingest/fonti.carica_statistiche);
  - stagione IN CORSO: le Statistiche cambiano ogni settimana, quindi vanno in
    data/raw/Stagione in corso/ con la data (`..._AAAA_AA__2026-10-15.xlsx`);
    si usa sempre lo snapshot piu' recente;
  - voti per giornata `Voti_Fantacalcio_Stagione_AAAA_AA_Giornata_N.xlsx` in
    data/raw/Voti/AA-AA/ (letti da ingest/voti.py);
  - listone `Listone_*.xlsx` / `Quotazioni_*.xlsx` in data/raw/;
  - Understat della stagione in corso in data/raw/Understat/AAAA-AA/<data>/.

Una stagione e' "in corso" se e' quella del listone piu' recente.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import shutil

RAW = pathlib.Path("data/raw")
STAT_DIR = RAW / "Statistiche Fantacalcio"
CORRENTE_DIR = RAW / "Stagione in corso"
VOTI_DIR = RAW / "Voti"
UNDERSTAT_DIR = RAW / "Understat"
DOWNLOAD = pathlib.Path.home() / "Downloads"

RE_STAT = re.compile(r"Statistiche_Fantacalcio_Stagione_(\d{4})_(\d{2})\.xlsx$")
RE_VOTI = re.compile(r"Voti_Fantacalcio_Stagione_(\d{4})_(\d{2})_Giornata_(\d+)\.xlsx$")
RE_LISTONE = re.compile(r"(Listone|Quotazioni)_.*\.xlsx$", re.I)


def stagione_corrente(raw: pathlib.Path = RAW) -> str:
    """Stagione in corso: quella del listone piu' recente ('2026-27').

    Il nome del listone porta la data (Listone_20_08_26 = 20 agosto 2026):
    una stagione inizia d'estate, quindi l'anno della data e' l'anno d'inizio.
    """
    listoni = sorted(raw.glob("Listone_*.xlsx")) + sorted(raw.glob("Quotazioni_*.xlsx"))
    if not listoni:
        raise FileNotFoundError("nessun listone in data/raw/")
    anni = []
    for f in listoni:
        m = re.search(r"(\d{2})_(\d{2})_(\d{2})", f.stem)
        if m:
            g, mese, a = (int(x) for x in m.groups())
            anni.append(2000 + a if mese >= 7 else 2000 + a - 1)
    a = max(anni)
    return f"{a}-{(a + 1) % 100:02d}"


def _copia(src: pathlib.Path, dst: pathlib.Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return f"gia' presente: {dst}"
    shutil.copy2(src, dst)
    return f"importato: {src.name} -> {dst}"


def importa_download(cartella: pathlib.Path = DOWNLOAD, oggi: dt.date | None = None) -> list[str]:
    """Copia in data/raw/ i file Fantacalcio trovati in `cartella`. Ritorna il log."""
    oggi = oggi or dt.date.today()
    corrente = stagione_corrente()
    log = []
    for f in sorted(cartella.glob("*.xlsx")):
        if m := RE_STAT.search(f.name):
            stag = f"{m.group(1)}-{m.group(2)}"
            if stag == corrente:
                dst = CORRENTE_DIR / f"{f.stem}__{oggi.isoformat()}.xlsx"
            else:
                dst = STAT_DIR / f.name
            log.append(_copia(f, dst))
        elif m := RE_VOTI.search(f.name):
            cart = VOTI_DIR / f"{m.group(1)[2:]}-{m.group(2)}"
            log.append(_copia(f, cart / f.name))
        elif RE_LISTONE.search(f.name):
            log.append(_copia(f, RAW / f.name))
    return log or [f"nessun file Fantacalcio in {cartella}"]


def statistiche_correnti(stagione: str | None = None) -> pathlib.Path | None:
    """Snapshot piu' recente delle Statistiche della stagione in corso."""
    stagione = stagione or stagione_corrente()
    tag = stagione.replace("-", "_")
    files = sorted(CORRENTE_DIR.glob(f"Statistiche_Fantacalcio_Stagione_{tag}__*.xlsx"))
    return files[-1] if files else None


# --------------------------------------------------------------------------- #
# Understat via soccerdata
# --------------------------------------------------------------------------- #
def codice_understat(stagione: str) -> str:
    """'2026-27' -> '2627' (convenzione soccerdata: MAI riusarla per FBref)."""
    return stagione[2:4] + stagione[5:7]


def scarica_understat(stagione: str | None = None, oggi: dt.date | None = None) -> list[str]:
    """Scarica da Understat la stagione in corso: calendario, partite di
    squadra, giocatore × stagione e giocatore × partita. Richiede rete."""
    import soccerdata as sd                    # dipendenza pesante: import locale
    stagione = stagione or stagione_corrente()
    oggi = oggi or dt.date.today()
    dest = UNDERSTAT_DIR / stagione / oggi.isoformat()
    dest.mkdir(parents=True, exist_ok=True)
    us = sd.Understat(leagues="ITA-Serie A", seasons=[codice_understat(stagione)],
                      no_cache=True)
    log = []
    for nome, fn in [("schedule", us.read_schedule),
                     ("team_match", us.read_team_match_stats),
                     ("player_season", us.read_player_season_stats),
                     ("player_match", us.read_player_match_stats)]:
        df = fn().reset_index()
        df.to_csv(dest / f"{nome}.csv", index=False)
        log.append(f"Understat {stagione} {nome}: {len(df)} righe -> {dest / (nome + '.csv')}")
    return log


def understat_corrente(stagione: str | None = None) -> pathlib.Path | None:
    """Cartella dello scarico Understat piu' recente della stagione."""
    stagione = stagione or stagione_corrente()
    cartelle = sorted(p for p in (UNDERSTAT_DIR / stagione).glob("*") if p.is_dir())
    return cartelle[-1] if cartelle else None


if __name__ == "__main__":
    for riga in importa_download():
        print(riga)
    for riga in scarica_understat():
        print(riga)
