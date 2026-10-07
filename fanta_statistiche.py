"""
Fantacalcio: caricamento e analisi dei file Statistiche stagionali di Fantacalcio.it.

Lega di riferimento: Classic, 8 squadre, 500 crediti, rosa 3-8-8-6,
bonus/malus standard con imbattibilita' portiere attiva, nessun modificatore.

Uso:
    python fanta_statistiche.py /percorso/cartella_con_gli_xlsx
"""
import sys, re, glob, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

NUM = ["Pv", "Mv", "Fm", "Gf", "Gs", "Rp", "Rc", "R+", "R-", "Ass", "Amm", "Esp", "Au"]

# 8 squadre; domanda di TITOLARI, non di slot in rosa (vedi nota nel README)
N_SQUADRE = 8
TITOLARI = {"P": 1.0, "D": 3.5, "C": 3.5, "A": 3.0}
SLOT_ROSA = {"P": 3, "D": 8, "C": 8, "A": 6}
CREDITI = 500


# --------------------------------------------------------------------------- #
# caricamento
# --------------------------------------------------------------------------- #
def carica_stagione(path: str) -> pd.DataFrame:
    d = pd.read_excel(path, sheet_name="Tutti", header=1)
    for c in NUM:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["stagione"] = re.search(r"(\d{4}_\d{2})", path).group(1).replace("_", "-")
    d["punti"] = d.Fm * d.Pv
    # tabella standard SENZA imbattibilita' (il file non la include)
    d["bonus_netti"] = (
        3 * d.Gf - d.Gs + 3 * d.Rp + d.Ass
        - 0.5 * d.Amm - d.Esp - 2 * d.Au - 3 * d["R-"]
    )
    d["tasso_bonus"] = d.bonus_netti / d.Pv.replace(0, np.nan)
    return d


def carica_tutte(cartella: str) -> pd.DataFrame:
    files = sorted(glob.glob(f"{cartella}/Statistiche_*.xlsx"))
    if not files:
        raise FileNotFoundError(f"nessun file Statistiche_*.xlsx in {cartella}")
    return pd.concat([carica_stagione(f) for f in files], ignore_index=True)


# --------------------------------------------------------------------------- #
# validazione del motore di regolamento
# --------------------------------------------------------------------------- #
def valida_formula(df: pd.DataFrame) -> pd.DataFrame:
    """Fm = Mv + bonus_netti / Pv.

    Gli scarti residui sono SEMPRE positivi e multipli di 0.5 punti stagionali:
    la colonna Amm conta anche i cartellini presi in partite senza voto, che la
    redazione non applica alla fantamedia. Nel motore per giornata il problema
    non si pone, perche' il malus si applica solo alle righe con voto reale.
    """
    v = df[df.Pv > 0].copy()
    v["fm_calc"] = v.Mv + v.bonus_netti / v.Pv
    v["scarto"] = v.Fm - v.fm_calc
    v["scarto_punti"] = v.scarto * v.Pv
    return v


# --------------------------------------------------------------------------- #
# livelli di rimpiazzo e listino
# --------------------------------------------------------------------------- #
def livelli_rimpiazzo(df: pd.DataFrame, n_squadre: int = N_SQUADRE) -> pd.DataFrame:
    out = []
    for st, g in df.groupby("stagione"):
        for r, per_squadra in TITOLARI.items():
            k = round(per_squadra * n_squadre)
            sub = g[g.R == r].sort_values("punti", ascending=False).reset_index(drop=True)
            repl = sub.loc[k - 1, "punti"]
            out.append(dict(
                stagione=st, ruolo=r, rango=k, rimpiazzo=repl,
                top=sub.punti.max(),
                vor_totale=(sub.punti - repl).clip(lower=0).sum(),
            ))
    R = pd.DataFrame(out)
    R["quota"] = R.groupby("stagione").vor_totale.transform(lambda s: s / s.sum())
    return R


def budget_per_ruolo(R: pd.DataFrame, n_squadre: int = N_SQUADRE) -> pd.DataFrame:
    """Mediana sulle stagioni: piu' robusta della media alle annate anomale."""
    slot_totali = sum(SLOT_ROSA.values()) * n_squadre
    contendibili = CREDITI * n_squadre - slot_totali
    med = R.groupby("ruolo").quota.median()
    med = med / med.sum()
    rows = []
    for r in ["P", "D", "C", "A"]:
        pavimento = SLOT_ROSA[r] * n_squadre
        tot = med[r] * contendibili + pavimento
        rows.append(dict(ruolo=r, quota_pct=round(med[r] * 100, 1),
                         crediti_squadra=round(tot / n_squadre),
                         pct_budget=round(tot / n_squadre / CREDITI * 100)))
    return pd.DataFrame(rows)


def listino(df: pd.DataFrame, stagione: str, n_squadre: int = N_SQUADRE) -> pd.DataFrame:
    """Prezzo implicito su base storica. NON e' una proiezione: serve a leggere
    la forma delle curve, non a decidere gli acquisti."""
    g = df[df.stagione == stagione]
    contendibili = CREDITI * n_squadre - sum(SLOT_ROSA.values()) * n_squadre
    parti = []
    for r, per_squadra in TITOLARI.items():
        k = round(per_squadra * n_squadre)
        sub = g[g.R == r].sort_values("punti", ascending=False).reset_index(drop=True)
        sub["vor"] = (sub.punti - sub.loc[k - 1, "punti"]).clip(lower=0)
        parti.append(sub)
    allp = pd.concat(parti)
    allp["prezzo"] = (allp.vor / allp.vor.sum() * contendibili + 1).round()
    return allp.sort_values("prezzo", ascending=False)


# --------------------------------------------------------------------------- #
# persistenza anno su anno
# --------------------------------------------------------------------------- #
def coppie_consecutive(df: pd.DataFrame, min_pv: int = 10) -> pd.DataFrame:
    ord_ = sorted(df.stagione.unique())
    parti = []
    for a, b in zip(ord_, ord_[1:]):
        x = df[df.stagione == a].set_index("Id")
        y = df[df.stagione == b].set_index("Id")
        j = x.join(y, rsuffix="_n", how="inner")
        parti.append(j[(j.Pv >= min_pv) & (j.Pv_n >= min_pv)])
    return pd.concat(parti)


def persistenza(P: pd.DataFrame) -> pd.DataFrame:
    """Correlazioni DENTRO il ruolo. Le correlazioni aggregate sono gonfiate
    dalla composizione per ruolo (i portieri stanno su un altro livello di Mv
    e di bonus): usare sempre queste, non quelle pooled."""
    rows = []
    for r in ["P", "D", "C", "A"]:
        s = P[P.R == r]
        rows.append(dict(
            ruolo=r, n=len(s),
            Pv=s.Pv.corr(s.Pv_n), Mv=s.Mv.corr(s.Mv_n),
            tasso_bonus=s.tasso_bonus.corr(s.tasso_bonus_n),
            Fm=s.Fm.corr(s.Fm_n), punti=s.punti.corr(s.punti_n),
            pendenza=np.polyfit(s.Fm, s.Fm_n, 1)[0],
        ))
    return pd.DataFrame(rows).round(3)


def contrai(valore: float, ruolo: str, pendenza: dict, media_ruolo: dict) -> float:
    """Stima contratta verso la media di ruolo con il fattore empirico."""
    b = pendenza[ruolo]
    return media_ruolo[ruolo] + b * (valore - media_ruolo[ruolo])


# --------------------------------------------------------------------------- #
def main(cartella: str) -> None:
    df = carica_tutte(cartella)
    print(f"caricate {df.stagione.nunique()} stagioni, {len(df)} righe\n")

    v = valida_formula(df)
    an = v[v.scarto.abs() > 0.011]
    print("VALIDAZIONE")
    print(f"  errore medio {v.scarto.abs().mean():.4f} | anomale {len(an)}/{len(v)} "
          f"({len(an)/len(v)*100:.1f}%) | tutte positive: {bool((an.scarto > 0).all())}")

    R = livelli_rimpiazzo(df)
    print("\nLIVELLI DI RIMPIAZZO (punti stagionali, mediana)")
    print(R.groupby("ruolo").rimpiazzo.median().reindex(["P", "D", "C", "A"]).round(0).to_string())

    print("\nBUDGET PER RUOLO")
    print(budget_per_ruolo(R).to_string(index=False))

    P = coppie_consecutive(df)
    print(f"\nPERSISTENZA DENTRO IL RUOLO ({len(P)} coppie)")
    print(persistenza(P).to_string(index=False))

    df.to_parquet("statistiche_unificate.parquet")
    print("\npannello salvato in statistiche_unificate.parquet")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
