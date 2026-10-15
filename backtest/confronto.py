"""Confronto completo v2 → v3 sulle aste 2022-23 → 2025-26.

    python -m backtest.confronto

Scrive in output/backtest/:
  - previsioni.csv        una riga per (stagione, giocatore): previsioni v3 con
                          e senza giornate osservate, v2, baseline, realizzato;
  - metriche_punti.csv    metriche sui punti (storico.riassunto);
  - metriche_valore.csv   correlazione col valore marginale realizzato;
  - quote_ruolo.csv       quota del valore per ruolo, prevista e realizzata;
  - confronto.html        il report visivo (backtest/report.py).

La v2 si rigenera da git con backtest/v2_legacy.py se manca il suo file.
"""
from __future__ import annotations

import pathlib

import pandas as pd

from backtest import economico, storico, v2_legacy

OUT = pathlib.Path("output/backtest")


def esegui(rigenera_v2: bool = False) -> dict[str, pd.DataFrame]:
    OUT.mkdir(parents=True, exist_ok=True)
    dati = storico._carica()
    g = dati[0]
    con = storico.proiezioni_storiche(giornata_asta=2, dati=dati)
    senza = storico.proiezioni_storiche(giornata_asta=0, dati=dati)

    file_v2 = OUT / "previsioni_v2.csv"
    if rigenera_v2 or not file_v2.exists():
        v2_legacy.genera(con, file_v2)
    v2 = pd.read_csv(file_v2).rename(columns={
        "punti_proj": "v2_punti", "pv_proj": "v2_pv",
        "rigori_attesi": "v2_rigori", "prezzo": "v2_prezzo"})
    df = (con.merge(senza[["stagione", "Id", "punti_proj", "pv_proj", "fm_base", "p_voto"]]
                    .rename(columns={"punti_proj": "g0_punti", "pv_proj": "g0_pv",
                                     "fm_base": "g0_fm_base", "p_voto": "g0_p_voto"}),
                    on=["stagione", "Id"], how="left")
             .merge(v2[["stagione", "Id", "v2_punti", "v2_pv", "v2_rigori", "v2_prezzo"]],
                    on=["stagione", "Id"], how="left"))
    if df.v2_punti.isna().any():
        raise ValueError("universi v2 e v3 non allineati")

    modelli = {
        "v3 (2 giornate osservate)": ("punti_proj", "pv_proj"),
        "v3 (nessuna giornata)": ("g0_punti", "g0_pv"),
        "v2": ("v2_punti", "v2_pv"),
        "ingenuo (punti anno prima)": ("ingenua", None),
    }
    punti = storico.riassunto(df, modelli)

    # valore: stessa funzione del listino, sulle proiezioni di ciascuna variante
    df = economico.valori_previsti(df)
    g0 = df[["stagione", "ruolo", "g0_pv", "g0_punti", "g0_fm_base"]].rename(
        columns={"g0_pv": "pv_proj", "g0_punti": "punti_proj", "g0_fm_base": "fm_base"})
    df["v3_valore_g0"] = (g0.groupby("stagione", group_keys=False)
                            .apply(lambda d: economico.valore_per_presenza(d)))
    df = economico.valori_realizzati(df, g, {**economico.CONTESTI,
                                             "mercato: prezzi v2": "v2_prezzo"})
    candidati = {
        "v3 (2 giornate osservate)": "v3_valore",
        "v3 (nessuna giornata)": "v3_valore_g0",
        "v3 punti totali (formula v2)": "v3_punti_totali",
        "v2": "v2_prezzo",
        "ingenuo (punti anno prima)": "ingenua",
    }
    contesti = {**economico.CONTESTI, "mercato: prezzi v2": "v2_prezzo"}
    valore = economico.confronto(df, candidati, contesti)
    quote = economico.quote_ruolo(df.assign(v2_val=df.v2_prezzo - 1), {
        "realizzato (mercato: punti anno prima)": "real::mercato: punti anno prima",
        "realizzato (lega efficiente)": "real::lega efficiente: proiezioni v3",
        "v3": "v3_valore", "v2": "v2_val"})
    stagionali = economico.quote_per_stagione(df, "real::mercato: punti anno prima")

    df.to_csv(OUT / "previsioni.csv", index=False)
    punti.to_csv(OUT / "metriche_punti.csv")
    valore.to_csv(OUT / "metriche_valore.csv")
    quote.to_csv(OUT / "quote_ruolo.csv")
    stagionali.to_csv(OUT / "quote_realizzate_per_stagione.csv")
    return dict(previsioni=df, punti=punti, valore=valore, quote=quote,
                quote_stagionali=stagionali)


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    r = esegui()
    from backtest import report
    print(f"report: {report.scrivi()}")
    print(r["punti"].to_string())
    print(r["valore"].to_string())
    print(r["quote"].to_string())
    print(r["quote_stagionali"].to_string())
