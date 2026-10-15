"""Artefatti del listino: output/listino.csv e output/listino.html.

Ogni riga porta un MOTIVO in italiano costruito solo da segnali calcolati
(presenze proiettate, vantaggio per partita sul panchinaro tipo, rigori, difesa
della squadra, cambi di club e gerarchie). Se non si riesce a scriverlo, il
modello sta producendo un numero che nessuno puo' verificare.

Sezioni: occasioni e trappole con storico solido, gerarchie contese col
mercato, profili a bassa informazione (stima quasi tutta di prior: ammissioni di
ignoranza, non segnali).
"""
from __future__ import annotations

import html
import pathlib

import pandas as pd

from rules import LEGA, LeagueRules
from value.listino import costruisci_listino, quote_per_ruolo

OUT = pathlib.Path("output")


def motivo(r, fm_rimpiazzo: float) -> str:
    if r.senza_storico:
        return ("nessuno storico in Serie A: stima dalla media di ruolo e dalla "
                "squadra (bassa informazione)")
    parti = []
    if r.pv_proj >= 28:
        parti.append(f"titolare fisso ({r.pv_proj:.0f} presenze attese)")
    elif r.p_voto < 0.45:
        parti.append(f"presenze incerte ({r.pv_proj:.0f} attese)")
    vantaggio = r.fm_proj - fm_rimpiazzo if pd.notna(r.fm_proj) else 0.0
    if vantaggio > 0.1:
        parti.append(f"{vantaggio:+.2f} a partita sul panchinaro tipo")
    else:
        parti.append(f"{vantaggio:+.2f} a partita sul panchinaro tipo: rende come una "
                     "riserva, quindi vale poco anche se gioca sempre")
    if r.rigori_attesi >= 1.5:
        parti.append(f"rigorista ({r.rigori_attesi:.1f} rigori attesi)")
    if r.ruolo == "P":
        parti.append(f"difesa della squadra: {r.fm_port:+.2f} a partita fra gol subiti e imbattibilita'")
    if r.cambio_club:
        parti.append("ha cambiato squadra")
    if r.neopromossa:
        parti.append("squadra neopromossa")
    if r.gerarchia:
        parti.append(r.gerarchia)
    if r.bassa_info:
        parti.append("poche presenze storiche (bassa informazione)")
    if pd.isna(r.diff_vs_fvm):
        testa = "non nel listone (arrivato dopo): nessun FVM di confronto"
    elif r.diff_vs_fvm > 0:
        testa = "il mercato lo sottoprezza"
    else:
        testa = "il mercato lo paga piu' del suo valore"
    return testa + ("; " + "; ".join(parti) if parti else "")


def costruisci_report(lega: LeagueRules = LEGA, **kw) -> tuple[pd.DataFrame, dict]:
    lis, info = costruisci_listino(lega, **kw)
    rimp = info["rimpiazzo"].fm_rimpiazzo
    lis["motivo"] = [motivo(r, rimp[r.ruolo]) for r in lis.itertuples()]
    return lis, info


COLONNE_OUT = ["Nome", "ruolo", "squadra", "pv_proj", "fm_proj", "rigori_attesi",
               "punti_proj", "prezzo", "fvm_riscalato", "diff_vs_fvm", "motivo"]
ETICHETTE = {
    "Nome": "Giocatore", "ruolo": "R", "squadra": "Squadra",
    "pv_proj": "Presenze", "fm_proj": "Fantamedia", "rigori_attesi": "Rigori",
    "punti_proj": "Punti", "prezzo": "Prezzo", "fvm_riscalato": "FVM risc.",
    "diff_vs_fvm": "Differenza", "motivo": "Perché",
}


def _tabella(df: pd.DataFrame, classe: str = "") -> str:
    d = df[COLONNE_OUT].copy()
    for c in ["pv_proj", "fm_proj", "rigori_attesi", "punti_proj", "fvm_riscalato", "diff_vs_fvm"]:
        d[c] = d[c].astype(float).round(1)
    d["fm_proj"] = df.fm_proj.astype(float).round(2)
    righe = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(r[c]))}</td>" for c in COLONNE_OUT) + "</tr>"
        for _, r in d.iterrows())
    intest = "".join(f"<th>{ETICHETTE[c]}</th>" for c in COLONNE_OUT)
    return (f'<div class="scroll"><table class="{classe}"><thead><tr>{intest}</tr></thead>'
            f"<tbody>{righe}</tbody></table></div>")


STILE = """
:root{--bg:#fbfbfa;--fg:#1b1b1a;--muto:#5d5d58;--riga:#e7e6e1;--hover:#f1f0ec;--su:#0b6e2f;--giu:#b3261e;--accento:#2f5d8a}
@media (prefers-color-scheme: dark){:root{--bg:#161615;--fg:#ecebe6;--muto:#a3a29b;--riga:#2c2c2a;--hover:#22221f;--su:#5fc483;--giu:#f08a80;--accento:#8db4dc}}
body{font-family:-apple-system,"Segoe UI",Roboto,sans-serif;margin:0 auto;max-width:78rem;padding:2rem 1rem;background:var(--bg);color:var(--fg)}
h1{font-size:1.5rem;margin-bottom:.2rem} h2{margin-top:2.4rem;font-size:1.15rem;border-bottom:2px solid var(--riga);padding-bottom:.3rem}
p.nota{color:var(--muto);max-width:62rem;line-height:1.45}
.avviso{border-left:4px solid var(--giu);padding:.6rem .9rem;background:var(--hover);max-width:62rem}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.85rem;margin-top:.6rem}
th,td{padding:.35rem .5rem;border-bottom:1px solid var(--riga);text-align:right;white-space:nowrap}
th:nth-child(1),td:nth-child(1),th:nth-child(3),td:nth-child(3),th:last-child,td:last-child{text-align:left}
td:last-child{white-space:normal;color:var(--muto);min-width:22rem}
tbody tr:hover{background:var(--hover)}
.occ td:nth-child(10){color:var(--su);font-weight:600}
.tra td:nth-child(10){color:var(--giu);font-weight:600}
code{color:var(--accento)}
"""


def scrivi_artefatti(lega: LeagueRules = LEGA, **kw) -> pd.DataFrame:
    OUT.mkdir(exist_ok=True)
    lis, info = costruisci_report(lega, **kw)
    lis.to_csv(OUT / "listino.csv", index=False)

    # occasioni e trappole: storico solido e gerarchia non contesa col mercato
    solide = lis[~lis.bassa_info & (lis.gerarchia == "")]
    occasioni = solide.head(30)
    trappole = solide.tail(30).sort_values("diff_vs_fvm")
    contese = lis[lis.gerarchia != ""].sort_values("fvm_riscalato", ascending=False).head(40)
    bassa = lis[lis.bassa_info].sort_values("fvm_riscalato", ascending=False).head(40)

    q = quote_per_ruolo(lis)
    riga_quota = " · ".join(f"{r} {q[r]}%" for r in ["P", "D", "C", "A"])
    rimp = info["rimpiazzo"]
    riga_rimp = " · ".join(f"{r} {rimp.fm_rimpiazzo[r]:.2f}" for r in ["P", "D", "C", "A"])
    oss = info["giornate_osservate"]
    avviso = ("" if oss > 0 else
              '<p class="avviso"><b>Nessuna giornata della stagione osservata.</b> Le '
              "presenze vengono solo dallo storico: i cambi di gerarchia dell'estate "
              "(nuovi titolari, portieri arrivati dall'estero) sono invisibili, e nel "
              "backtest l'ordine dei giocatori migliora molto con le prime due giornate. "
              "Mettere i voti delle giornate giocate in <code>data/raw/Voti/26-27/</code> "
              "e rigenerare con <code>python -m value.report</code> prima dell'asta.</p>")

    corpo = f"""
<h1>Listino d'asta {info['stagione']} — v3</h1>
<p class="nota">Giornate osservate: <b>{oss}</b> · giornate che contano: {info['giornate_conteggiate']}
· modelli addestrati sulle aste {', '.join(info['aste_addestramento'])}.</p>
{avviso}
<p class="nota"><b>Come nasce il prezzo.</b> Presenze attese × vantaggio per partita sul
<i>panchinaro tipo</i> del ruolo (fantamedia di rimpiazzo: {riga_rimp}). Le giornate che un
titolare salta le copre la panchina, quindi giocare tanto vale poco se si rende come una riserva.
I 3800 crediti contendibili si dividono in proporzione al valore, con lo stesso tasso per ogni
ruolo: la quota per ruolo e' un risultato, non un vincolo ({riga_quota}). La somma dei prezzi
delle rose fa esattamente 4000.</p>
<p class="nota"><b>Come leggerlo.</b> Il prezzo e' quanto vale il giocatore se tutti pagassero
il giusto, non quanto offrire in un dato momento: quello dipende da rosa e crediti residui
(modulo d'asta). <b>Differenza</b> = prezzo − FVM riportato allo stesso monte: positiva,
il mercato lo sottoprezza; negativa, lo sovrapprezza.</p>

<h2>Le 30 maggiori occasioni (storico solido, gerarchia non contesa)</h2>
{_tabella(occasioni, "occ")}

<h2>Le 30 maggiori trappole (storico solido, gerarchia non contesa)</h2>
<p class="nota">Storico abbondante: non e' incertezza, e' disaccordo col mercato.</p>
{_tabella(trappole, "tra")}

<h2>Gerarchie contese col mercato</h2>
<p class="nota">Il mercato e il modello indicano titolari diversi nella stessa squadra. Di
solito il mercato sa del mercato estivo, il modello sa chi ha giocato davvero: le prime
giornate decidono. Da verificare con le notizie prima di offrire.</p>
{_tabella(contese)}

<h2>Profili a bassa informazione</h2>
<p class="nota">Esordienti in Serie A o pochissime presenze: la stima e' quasi tutta media di
ruolo e di squadra. Non sono occasioni ne' trappole: sono ammissioni di ignoranza.</p>
{_tabella(bassa)}
"""
    doc = (f"<!doctype html><html lang=it><head><meta charset=utf-8>"
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f"<title>Listino d'asta {info['stagione']}</title><style>{STILE}</style></head>"
           f"<body>{corpo}</body></html>")
    (OUT / "listino.html").write_text(doc, encoding="utf-8")
    print(f"scritti: {OUT / 'listino.csv'} ({len(lis)} righe) e {OUT / 'listino.html'}")
    print(f"quote per ruolo: {riga_quota} · giornate osservate {oss}")
    return lis


if __name__ == "__main__":
    scrivi_artefatti()
