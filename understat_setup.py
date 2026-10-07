"""
Understat setup — senza parquet, con controllo dell'ambiente.

AMBIENTE RICHIESTO: Python 3.10+ (soccerdata >= 1.9 dichiara >=3.10,<3.15).
Con la 3.9 pip installa silenziosamente una versione vecchia della libreria.

    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -U pip
    pip install soccerdata pandas numpy

Uso:
    python understat_setup.py --step 0     # controllo ambiente, FALLO PER PRIMO
    python understat_setup.py --step 1     # scarica Understat
    python understat_setup.py --step 2     # mappa dei nomi squadra
    python understat_setup.py --step 3     # unione e validazione
    python understat_setup.py --step 4     # calibrazione Understat vs Opta
    python understat_setup.py --step 1b    # opzionale: i tiri
"""
import argparse
import pathlib
import sys

RAW = pathlib.Path("data/raw")
PANEL = pathlib.Path("data/panel")

LEAGUE = "ITA-Serie A"
SEASONS = ["2021", "2122", "2223", "2324", "2425", "2526"]

FBREF_COMPLETO = RAW / "Fbref_SenzaxG.csv"   # tutte le stagioni, senza xG
FBREF_OPTA = RAW / "Fbref_xG.csv"            # incompleto, ma con xG Opta


# --------------------------------------------------------------------------- #
# PASSO 0 — controllo dell'ambiente
# --------------------------------------------------------------------------- #
def step0_preflight() -> None:
    
    ok = True
    v = sys.version_info
    print(f"python      {v.major}.{v.minor}.{v.micro}   ({sys.executable})")
    if (v.major, v.minor) < (3, 10):
        print("  ERRORE: soccerdata >= 1.9 richiede Python 3.10+.")
        ok = False
    if ".venv" not in sys.executable and "virtualenv" not in sys.executable:
        print("  ATTENZIONE: non sembri dentro un ambiente virtuale. "
              "Su macOS i pacchetti --user danno conflitti binari.")

    for mod in ["pandas", "numpy", "soccerdata"]:
        try:
            m = __import__(mod)
            print(f"{mod:11s} {getattr(m, '__version__', '?')}")
        except Exception as e:  # noqa: BLE001
            print(f"{mod:11s} NON IMPORTABILE ({type(e).__name__}: {e})")
            ok = False

    for p in [FBREF_COMPLETO, FBREF_OPTA]:
        print(f"{'file':11s} {p}  {'ok' if p.exists() else 'MANCANTE'}")

    print("\n" + ("ambiente a posto, procedi con --step 1"
                  if ok else "sistema i problemi sopra prima di procedere"))
    if not ok:
        sys.exit(1)


# --------------------------------------------------------------------------- #
# PASSO 1 — scarico da Understat
# --------------------------------------------------------------------------- #
def step1_download() -> None:
    import soccerdata as sd

    PANEL.mkdir(parents=True, exist_ok=True)
    us = sd.Understat(leagues=LEAGUE, seasons=SEASONS)

    print("stagioni che soccerdata riconosce:")
    print(us.read_seasons().to_string())

    sched = us.read_schedule().reset_index()
    sched.to_csv(PANEL / "understat_schedule.csv", index=False)
    print(f"\nschedule salvato: {sched.shape}")
    print(sched.columns.tolist())
    print(sched.head(3).to_string())

    for nome, fn in [("team_match", us.read_team_match_stats),
                     ("player_season", us.read_player_season_stats)]:
        try:
            df = fn().reset_index()
            df.to_csv(PANEL / f"understat_{nome}.csv", index=False)
            print(f"\n{nome}: {df.shape}\n{df.columns.tolist()}")
        except Exception as e:  # noqa: BLE001
            print(f"\n{nome} non riuscito ({type(e).__name__}: {e}); "
                  "non è bloccante, lo schedule basta")


def step1b_shots() -> None:
    """Opzionale: i tiri, ~65k righe. Danno npxG corretto e xG giocatore-partita."""
    import soccerdata as sd

    PANEL.mkdir(parents=True, exist_ok=True)
    us = sd.Understat(leagues=LEAGUE, seasons=SEASONS)
    shots = us.read_shot_events().reset_index()
    shots.to_csv(PANEL / "understat_shots.csv", index=False)
    print(f"shots: {shots.shape}\n{shots.columns.tolist()}")
    print(shots.situation.value_counts().to_string())


# --------------------------------------------------------------------------- #
# Stagioni: le due fonti usano codifiche DIVERSE che si assomigliano.
#   FBref (tuo scraping nuovo):  '2020-2021'   -> anno iniziale 2020
#   FBref (vecchio file):         2020          -> anno iniziale 2020
#   soccerdata/Understat:        '2021'         -> anno iniziale 2020  (codice YYnn)
# La stringa '2021' significa cose diverse nelle due fonti: mai una funzione sola.
# --------------------------------------------------------------------------- #
def stagione_fbref(x) -> int:
    s = str(x).strip()
    if "-" in s:
        return int(s.split("-")[0])
    if len(s) == 4 and s.isdigit():
        return int(s)
    raise ValueError(f"stagione FBref non riconosciuta: {x!r}")


def stagione_understat(x) -> int:
    s = str(x).strip()
    if "-" in s:
        return int(s.split("-")[0])
    if len(s) == 4 and s.isdigit():
        return 2000 + int(s[:2])       # '2021' -> 2020
    raise ValueError(f"stagione Understat non riconosciuta: {x!r}")


def _diagnostica_stagioni(fb, us) -> None:
    a = sorted(fb.stagione.unique())
    b = sorted(us.stagione.unique())
    print(f"stagioni FBref     : {a}")
    print(f"stagioni Understat : {b}")
    comuni = sorted(set(a) & set(b))
    print(f"in comune          : {comuni}")
    if len(comuni) < min(len(a), len(b)):
        print("  ATTENZIONE: le stagioni non si sovrappongono del tutto. "
              "Controlla la codifica prima di fidarti del merge.")


# --------------------------------------------------------------------------- #
# PASSO 2 — mappa canonica dei nomi squadra
# --------------------------------------------------------------------------- #
def step2_team_map() -> None:
    import pandas as pd
    fb = pd.read_csv(FBREF_COMPLETO)
    us = pd.read_csv(PANEL / "understat_schedule.csv")

    fb_names = sorted(set(fb.team.dropna()) | set(fb.opponent.dropna()))
    us_names = sorted(set(us.home_team.dropna()) | set(us.away_team.dropna()))

    print(f"nomi FBref ({len(fb_names)}):\n  {fb_names}\n")
    print(f"nomi Understat ({len(us_names)}):\n  {us_names}\n")

    solo_fb = [n for n in fb_names if n not in us_names]
    solo_us = [n for n in us_names if n not in fb_names]
    print("presenti solo in FBref, da mappare a mano:")
    for n in solo_fb:
        print(f'    "{n}": "",')
    print(f"\ncandidati dal lato Understat:\n    {solo_us}")
    print("\nIncolla le corrispondenze in TEAM_MAP e rilancia --step 3.")


# Compilare dopo --step 2. Chiave = nome FBref, valore = nome Understat.
TEAM_MAP: dict = {
    "Hellas Verona": "Verona",
    "Internazionale": "Inter",
    "Milan": "AC Milan",
    "Parma": "Parma Calcio 1913",
}


# --------------------------------------------------------------------------- #
# PASSO 3 — unione e validazione
# --------------------------------------------------------------------------- #
def step3_join():
    import pandas as pd

    fb = pd.read_csv(FBREF_COMPLETO)
    us = pd.read_csv(PANEL / "understat_schedule.csv")

    fb = fb[fb.venue == "Home"].copy()
    fb = fb[fb["round"].str.contains("Matchweek", na=False)]   # via lo spareggio 2023
    fb["home"] = fb.team.replace(TEAM_MAP)
    fb["away"] = fb.opponent.replace(TEAM_MAP)
    fb["giornata"] = fb["round"].str.extract(r"(\d+)").astype(int)
    fb["stagione"] = fb.season.map(stagione_fbref)

    us["stagione"] = us.season.map(stagione_understat)
    us = us.rename(columns={"home_team": "home", "away_team": "away"})
    _diagnostica_stagioni(fb, us)

    # fallisce subito se TEAM_MAP e' incompleta, invece di perdere partite in silenzio
    noti = set(us.home) | set(us.away)
    orfani = sorted((set(fb.home) | set(fb.away)) - noti)
    if orfani:
        raise SystemExit(
            "TEAM_MAP incompleta. Nomi FBref senza corrispondenza in Understat:\n"
            + "\n".join(f'    "{n}": "",' for n in orfani)
            + f"\n\ncandidati liberi lato Understat: {sorted(noti - (set(fb.home) | set(fb.away)))}"
        )

    m = fb.merge(
        us[["stagione", "home", "away", "home_goals", "away_goals",
            "home_xg", "away_xg", "date"]],
        on=["stagione", "home", "away"],
        how="outer", indicator=True, suffixes=("", "_us"),
    )
    print("esito del merge:")
    print(m._merge.value_counts().to_string())

    both = m[m._merge == "both"].copy()

    # Partite in cui il risultato OMOLOGATO differisce da quello sul campo.
    # FBref riporta l'omologato, Understat il campo. Per il fantacalcio conta
    # il campo: i voti e i bonus/malus restano quelli della gara giocata.
    # Il pannello adotta quindi il risultato di Understat.
    ECCEZIONI_TAVOLINO = {
        (2020, "Verona", "Roma"),   # 0-0 sul campo, 3-0 a tavolino (caso Diawara)
    }
    tav = both.apply(
        lambda r: (r.stagione, r.home, r.away) in ECCEZIONI_TAVOLINO, axis=1)
    if tav.any():
        print(f"\n{int(tav.sum())} partita/e con risultato a tavolino: "
              "si adotta il risultato sul campo")
        both.loc[tav, ["gf", "ga"]] = both.loc[tav, ["home_goals", "away_goals"]].values

    ok = (both.gf == both.home_goals) & (both.ga == both.away_goals)
    print(f"\nVALIDAZIONE: punteggi coincidenti {ok.sum()}/{len(both)} "
          f"({ok.mean() * 100:.2f}%)")
    if not ok.all():
        print(both[~ok][["stagione", "giornata", "home", "away",
                         "gf", "ga", "home_goals", "away_goals"]].to_string())
    if (m._merge != "both").any():
        print("\npartite non agganciate (nomi da mappare):")
        print(m[m._merge != "both"][["stagione", "home", "away", "_merge"]]
              .head(30).to_string())

    out = both.drop(columns=["_merge", "home_goals", "away_goals"])
    out["fonte_xg"] = "understat"
    attese = fb.stagione.nunique() * 380
    if len(out) != attese:
        print(f"\nATTENZIONE: {len(out)} partite invece delle {attese} attese "
              f"({fb.stagione.nunique()} stagioni x 380)")
    out.to_csv(PANEL / "partite.csv", index=False)
    print(f"\nsalvato data/panel/partite.csv {out.shape}")
    return out


# --------------------------------------------------------------------------- #
# PASSO 4 — calibrazione Understat contro Opta
# --------------------------------------------------------------------------- #
def step4_calibrate() -> None:
    import numpy as np
    import pandas as pd

    if not FBREF_OPTA.exists():
        sys.exit(f"manca {FBREF_OPTA}")

    opta = pd.read_csv(FBREF_OPTA)
    opta = opta[(opta.venue == "Home") & opta.xg.notna()].copy()
    opta["home"] = opta.team.replace(TEAM_MAP)
    opta["away"] = opta.opponent.replace(TEAM_MAP)
    opta["stagione"] = opta.season.map(stagione_fbref)

    us = pd.read_csv(PANEL / "partite.csv")
    j = opta.merge(us[["stagione", "home", "away", "home_xg", "away_xg"]],
                   on=["stagione", "home", "away"], how="inner")
    print(f"partite sovrapposte: {len(j)}")

    for lato, o, u in [("casa", "xg", "home_xg"), ("trasferta", "xga", "away_xg")]:
        x, y = j[o].values, j[u].values
        b, a = np.polyfit(x, y, 1)
        r = np.corrcoef(x, y)[0, 1]
        rmse = float(np.sqrt(((y - x) ** 2).mean()))
        print(f"  {lato:10s} understat = {a:+.3f} + {b:.3f}·opta   "
              f"r={r:.3f}  rmse={rmse:.3f}  "
              f"media opta={x.mean():.2f} understat={y.mean():.2f}")

    print("\nPendenza vicina a 1 e intercetta vicina a 0: i due provider misurano")
    print("la stessa cosa. Altrimenti riscalare per stagione.")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--step", required=True,
                   choices=["0", "1", "1b", "2", "3", "4"])
    a = p.parse_args()
    {"0": step0_preflight, "1": step1_download, "1b": step1b_shots,
     "2": step2_team_map, "3": step3_join, "4": step4_calibrate}[a.step]()
    