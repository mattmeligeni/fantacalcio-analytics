"""Genera gli artefatti del listino: output/listino.csv e output/listino.html.

L'HTML ha tre sezioni (Parte 3, Fase 1): le maggiori occasioni (prezzo
consigliato molto sopra l'FVM, storico solido), le maggiori trappole (storico
solido, mercato sopra la proiezione), e i profili a bassa informazione a parte.

Ogni riga porta un MOTIVO in italiano. Non e' un abbellimento: se non si riesce
a scriverlo, il modello sta producendo un numero che nessuno puo' verificare
(Parte 3). Il motivo usa solo segnali calcolati (presenze, rigori, regressione).
"""
from __future__ import annotations

import html
import pathlib

import pandas as pd

from rules import LEGA, LeagueRules
from value.dati import con_imbattibilita
from value.listino import costruisci_listino

OUT = pathlib.Path("output")


def _punti_ultima_stagione() -> dict[int, float]:
    """Punti realizzati (imbattibilita' inclusa) nell'ultima stagione, per Id:
    serve come segnale di regressione nel motivo."""
    m = con_imbattibilita()
    ultima = sorted(m.stagione.unique())[-1]
    g = m[m.stagione == ultima]
    return dict(zip(g.Id, g.punti_imb))


def motivo(row, punti_ultima: float | None) -> str:
    if row.senza_storico:
        return "nessuno storico in Serie A: prezzo dal prior di ruolo (bassa informazione)"
    if row.bassa_info:
        return "pochissime presenze storiche: valutazione a bassa informazione"
    parti = []
    if row.rigori_attesi >= 2:
        parti.append("rigorista titolare")
    if row.cambio_club_rig:
        parti.append("rigorista che ha cambiato squadra: status a rischio")
    if row.pv_proj >= 30 and row.ruolo in ("D", "C"):
        parti.append("titolare molto affidabile")
    if punti_ultima is not None and punti_ultima - row.punti_proj > 25:
        parti.append("reduce da un'annata sopra la sua media, attesa in regressione")
    testa = ("il mercato lo sottoprezza rispetto alla proiezione"
             if row.diff_vs_fvm > 0
             else "il mercato lo paga sopra la proiezione")
    return testa + ("; " + ", ".join(parti) if parti else "")


def costruisci_report(lega: LeagueRules = LEGA,
                      giornata_corrente: int = 0) -> pd.DataFrame:
    lis = costruisci_listino(lega, giornata_corrente)
    pu = _punti_ultima_stagione()
    codmap = None  # il listino non porta il Cod: rimappo per Nome+ruolo dal panel
    # associa punti ultima stagione tramite un merge robusto su (Nome, ruolo)
    m = con_imbattibilita()
    ultima = sorted(m.stagione.unique())[-1]
    gu = m[m.stagione == ultima][["Nome", "R", "punti_imb"]].rename(
        columns={"R": "ruolo", "punti_imb": "punti_ultima"})
    lis = lis.merge(gu, on=["Nome", "ruolo"], how="left")
    lis["motivo"] = [motivo(r, r.punti_ultima if pd.notna(r.punti_ultima) else None)
                     for r in lis.itertuples()]
    return lis


COLONNE_OUT = ["Nome", "ruolo", "squadra", "pv_proj", "fm_proj", "punti_proj",
               "prezzo", "quotazione", "fvm_riscalato", "diff_vs_fvm",
               "rigori_attesi", "motivo"]
ETICHETTE = {
    "Nome": "Giocatore", "ruolo": "R", "squadra": "Squadra",
    "pv_proj": "Presenze", "fm_proj": "Fantamedia", "punti_proj": "Punti",
    "prezzo": "Prezzo cons.", "quotazione": "Quot. uff.",
    "fvm_riscalato": "FVM/2 risc.", "diff_vs_fvm": "Differenza",
    "rigori_attesi": "Rigori", "motivo": "Perche'",
}


def _tabella_html(df: pd.DataFrame) -> str:
    d = df[COLONNE_OUT].copy()
    for c in ["pv_proj", "fm_proj", "punti_proj", "fvm_riscalato",
              "diff_vs_fvm", "rigori_attesi"]:
        d[c] = d[c].round(1)
    righe = []
    for _, r in d.iterrows():
        celle = "".join(f"<td>{html.escape(str(r[c]))}</td>" for c in COLONNE_OUT)
        righe.append(f"<tr>{celle}</tr>")
    intest = "".join(f"<th>{ETICHETTE[c]}</th>" for c in COLONNE_OUT)
    return f"<table><thead><tr>{intest}</tr></thead><tbody>{''.join(righe)}</tbody></table>"


def scrivi_artefatti(lega: LeagueRules = LEGA, giornata_corrente: int = 0) -> None:
    OUT.mkdir(exist_ok=True)
    lis = costruisci_report(lega, giornata_corrente)
    lis.to_csv(OUT / "listino.csv", index=False)

    solide = lis[~lis.bassa_info]
    occasioni = solide.head(30)
    trappole = solide.tail(30).sort_values("diff_vs_fvm")
    bassa = lis[lis.bassa_info].sort_values("punti_proj", ascending=False).head(40)

    q = lis.groupby("ruolo").apply(
        lambda g: (g.prezzo - 1).clip(lower=0).sum(), include_groups=False)
    q = (q / q.sum() * 100).reindex(["P", "D", "C", "A"]).round(1)
    riga_quota = " · ".join(f"{r} {q[r]}%" for r in ["P", "D", "C", "A"])

    stile = """
    body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:2rem;color:#1a1a1a;background:#fff}
    h1{font-size:1.5rem} h2{margin-top:2.2rem;border-bottom:2px solid #ddd;padding-bottom:.3rem}
    p.nota{color:#555;max-width:60rem}
    table{border-collapse:collapse;width:100%;font-size:.86rem;margin-top:.6rem}
    th,td{padding:.35rem .5rem;border-bottom:1px solid #eee;text-align:right}
    th:first-child,td:first-child,th:nth-child(3),td:nth-child(3),td:last-child,th:last-child{text-align:left}
    td:last-child{color:#444;max-width:26rem}
    tbody tr:hover{background:#f6f8fa}
    .occ td:nth-child(10){color:#0a7d28;font-weight:600}
    .tra td:nth-child(10){color:#c0392b;font-weight:600}
    """
    corpo = f"""
    <h1>Listino d'asta 2026-27 — v2</h1>
    <p class="nota"><b>Cos'e':</b> il prezzo che conviene pagare per ogni giocatore,
    ricavato proiettando separatamente fantamedia e presenze (non i punti dell'anno
    scorso), scomponendo la fantamedia in voto, gioco su azione, rigori e malus, e
    confrontando con il valore di mercato ufficiale (FVM) riportato alla stessa scala.
    <b>Differenza</b> positiva = il mercato lo sottoprezza (occasione); negativa = lo
    sovrapprezza (trappola). Quota crediti per ruolo: {riga_quota}.</p>
    <p class="nota"><b>Come leggere il prezzo:</b> e' il valore relativo, cioe' quanto
    vale un giocatore rispetto al livello che ottieni gratis nel suo ruolo. I prezzi
    dei primissimi nomi sono alti perche' concentrano il valore del ruolo: sono un
    tetto massimo di quanto vale, non quanto devi spendere davvero. Quanto puoi
    permetterti data la rosa gia' fatta lo calcola il modulo d'asta, non questo
    listino.</p>

    <h2>Le 30 maggiori occasioni (storico solido)</h2>
    <p class="nota">Prezzo consigliato molto sopra l'FVM. Sono i giocatori su cui il
    mercato sbaglia in tuo favore.</p>
    <div class="occ">{_tabella_html(occasioni)}</div>

    <h2>Le 30 maggiori trappole (storico solido)</h2>
    <p class="nota">Il mercato li paga sopra la proiezione. Storico abbondante: non e'
    incertezza, e' disaccordo col mercato. Il verdetto finale spetta al backtest.</p>
    <div class="tra">{_tabella_html(trappole)}</div>

    <h2>Profili a bassa informazione (a parte)</h2>
    <p class="nota">Neopromossi, acquisti esteri, o pochissime presenze storiche:
    ricevono una stima media <b>per costruzione</b>, quindi appaiono vicini all'FVM.
    Non sono ne' occasioni ne' trappole: sono ammissioni di ignoranza, da valutare
    con notizie fresche sulla titolarita'.</p>
    {_tabella_html(bassa)}
    """
    doc = f"<!doctype html><html lang=it><head><meta charset=utf-8>" \
          f"<title>Listino d'asta 2026-27</title><style>{stile}</style></head>" \
          f"<body>{corpo}</body></html>"
    (OUT / "listino.html").write_text(doc, encoding="utf-8")
    print(f"scritti: {OUT/'listino.csv'} ({len(lis)} righe) e {OUT/'listino.html'}")
    print(f"occasioni {len(occasioni)} · trappole {len(trappole)} · bassa info {int(lis.bassa_info.sum())}")


if __name__ == "__main__":
    scrivi_artefatti()
