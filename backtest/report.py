"""Report visivo del confronto v2 → v3: output/backtest/confronto.html.

    python -m backtest.report          # dopo python -m backtest.confronto

Legge solo i CSV scritti da backtest/confronto.py, quindi si rigenera sempre dai
dati. Grafici in SVG inline (nessuna dipendenza), con tabella sotto ogni grafico
e colori per entita' fissi: lo stesso modello ha lo stesso colore ovunque.
"""
from __future__ import annotations

import html
import pathlib

import numpy as np
import pandas as pd

from value.valore import prezzi, valore_per_presenza

OUT = pathlib.Path("output/backtest")
RUOLI = ["P", "D", "C", "A"]
NOMI_RUOLO = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}

# entita' -> slot di colore (ordine fisso, validato per CVD in chiaro e scuro)
SERIE = {
    "v3 (2 giornate osservate)": ("--s1", "v3 con 2 giornate osservate"),
    "v3 (nessuna giornata)": ("--s2", "v3 senza giornate osservate"),
    "v2": ("--s3", "v2 (versione precedente)"),
    "ingenuo (punti anno prima)": ("--s4", "punti dell'anno prima"),
}


def _fmt(v, dec=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:+.{dec}f}" if dec == 1 else f"{v:.{dec}f}"


def _barra(x, w, y0, y1):
    """Rettangolo con estremo dati arrotondato (4px) e base squadrata."""
    h = abs(y1 - y0)
    r = min(4.0, h / 2, w / 2)
    if y1 <= y0:          # cresce verso l'alto
        return (f"M{x:.1f},{y0:.1f} L{x:.1f},{y1 + r:.1f} Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f} "
                f"L{x + w - r:.1f},{y1:.1f} Q{x + w:.1f},{y1:.1f} {x + w:.1f},{y1 + r:.1f} "
                f"L{x + w:.1f},{y0:.1f} Z")
    return (f"M{x:.1f},{y0:.1f} L{x:.1f},{y1 - r:.1f} Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f} "
            f"L{x + w - r:.1f},{y1:.1f} Q{x + w:.1f},{y1:.1f} {x + w:.1f},{y1 - r:.1f} "
            f"L{x + w:.1f},{y0:.1f} Z")


def grafico_barre(tab: pd.DataFrame, titolo: str, sottotitolo: str, dec: int = 2,
                  etichette_gruppi: dict | None = None) -> str:
    """Barre raggruppate: righe di `tab` = gruppi sull'asse x, colonne = serie."""
    serie = [c for c in tab.columns if tab[c].notna().any()]
    W, H, sx, dx, su, giu = 680, 300, 52, 12, 16, 34
    vals = tab[serie].values.astype(float)
    lo = min(0.0, np.nanmin(vals))
    hi = max(0.0, np.nanmax(vals))
    passo = _passo((hi - lo) / 5 if hi > lo else 1)
    lo = np.floor(lo / passo) * passo
    hi = np.ceil(hi / passo) * passo
    y = lambda v: su + (hi - v) / (hi - lo) * (H - su - giu)    # noqa: E731
    gruppi = list(tab.index)
    banda = (W - sx - dx) / len(gruppi)
    bw = min(24.0, (banda * 0.7 - 2 * (len(serie) - 1)) / len(serie))
    parti = []
    t = lo
    while t <= hi + 1e-9:
        parti.append(f'<line x1="{sx}" x2="{W - dx}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="griglia"/>'
                     f'<text x="{sx - 8}" y="{y(t) + 4:.1f}" class="tick" text-anchor="end">'
                     f"{t:.{max(0, dec - 1) if passo < 1 else 0}f}</text>")
        t += passo
    parti.append(f'<line x1="{sx}" x2="{W - dx}" y1="{y(0):.1f}" y2="{y(0):.1f}" class="asse"/>')
    for i, g in enumerate(gruppi):
        larg = len(serie) * bw + 2 * (len(serie) - 1)
        x0 = sx + i * banda + (banda - larg) / 2
        for j, s in enumerate(serie):
            v = tab.loc[g, s]
            if pd.isna(v):
                continue
            x = x0 + j * (bw + 2)
            nome = SERIE[s][1]
            gruppo = (etichette_gruppi or {}).get(g, g)
            parti.append(f'<path d="{_barra(x, bw, y(0), y(v))}" fill="var({SERIE[s][0]})">'
                         f"<title>{html.escape(gruppo)} · {html.escape(nome)}: {v:.{dec}f}</title></path>")
        etichetta = (etichette_gruppi or {}).get(g, g)
        parti.append(f'<text x="{sx + (i + 0.5) * banda:.1f}" y="{H - 12}" class="gruppo" '
                     f'text-anchor="middle">{html.escape(etichetta)}</text>')
    legenda = "".join(f'<span class="voce"><i style="background:var({SERIE[s][0]})"></i>'
                      f"{html.escape(SERIE[s][1])}</span>" for s in serie)
    tabella = _tabella_html(tab[serie].rename(columns={s: SERIE[s][1] for s in serie})
                            .rename(index=etichette_gruppi or {}), dec)
    return (f'<figure><figcaption><b>{titolo}</b><br><span>{sottotitolo}</span></figcaption>'
            f'<div class="legenda">{legenda}</div>'
            f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(titolo)}">'
            f'{"".join(parti)}</svg>'
            f"<details><summary>Tabella</summary>{tabella}</details></figure>")


def _passo(x: float) -> float:
    e = 10 ** np.floor(np.log10(x))
    for m in (1, 2, 2.5, 5, 10):
        if m * e >= x:
            return m * e
    return 10 * e


def _tabella_html(df: pd.DataFrame, dec: int = 2) -> str:
    intest = "<th></th>" + "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    righe = []
    for i, r in df.iterrows():
        celle = "".join(f"<td>{'—' if pd.isna(v) else (f'{v:.{dec}f}' if isinstance(v, (float, np.floating)) else html.escape(str(v)))}</td>"
                        for v in r.values)
        righe.append(f"<tr><th>{html.escape(str(i))}</th>{celle}</tr>")
    return f'<div class="scroll"><table><thead><tr>{intest}</tr></thead><tbody>{"".join(righe)}</tbody></table></div>'


def _contabilita(prev: pd.DataFrame) -> pd.DataFrame:
    """Controlli di coerenza per stagione: monte crediti e portieri per squadra."""
    righe = []
    for t, d in prev.groupby("stagione"):
        d = d.copy()
        d["v3_prezzo"] = prezzi(d, valore_per_presenza(d))
        rose_v3 = sum(d[d.ruolo == r].v3_prezzo.nlargest(s * 8).sum()
                      for r, s in {"P": 3, "D": 8, "C": 8, "A": 6}.items())
        gk = d[d.ruolo == "P"].groupby("squadra")
        righe.append({
            "stagione": t,
            "somma prezzi v2 (monte 4000)": d.v2_prezzo.sum(),
            "somma prezzi rose v3": rose_v3,
            "presenze portieri max per squadra, v2 (max 36)": gk.v2_pv.sum().max(),
            "presenze portieri max per squadra, v3": gk.pv_proj.sum().max(),
            "presenze portieri max per squadra, reali": gk.pv_real.sum().max(),
        })
    return pd.DataFrame(righe).set_index("stagione").round(0)


STILE = """
.viz-root{color-scheme:light;--bg:#fcfcfb;--fg:#0b0b0b;--muto:#52514e;--riga:#e6e5e0;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100}
@media (prefers-color-scheme: dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;
--bg:#1a1a19;--fg:#ffffff;--muto:#c3c2b7;--riga:#2f2f2c;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--bg:#1a1a19;--fg:#ffffff;--muto:#c3c2b7;
--riga:#2f2f2c;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500}
body{margin:0;background:#fcfcfb}
@media (prefers-color-scheme: dark){body{background:#1a1a19}}
.viz-root{background:var(--bg);color:var(--fg);font-family:-apple-system,"Segoe UI",Roboto,sans-serif;
max-width:60rem;margin:0 auto;padding:2rem 16px;line-height:1.45}
h1{font-size:1.45rem;margin:0 0 .3rem} h2{font-size:1.1rem;margin:2.4rem 0 .4rem}
p{color:var(--muto);max-width:52rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:12px;margin:1.4rem 0}
.tile{border:1px solid var(--riga);border-radius:8px;padding:.8rem 1rem}
.tile .l{color:var(--muto);font-size:.85rem}.tile .v{font-size:1.8rem;font-weight:600}
.tile .d{color:var(--muto);font-size:.85rem}
figure{margin:1.6rem 0}figcaption span{color:var(--muto);font-size:.9rem}
.legenda{display:flex;flex-wrap:wrap;gap:.4rem 1rem;margin:.6rem 0;font-size:.85rem;color:var(--muto)}
.voce i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
svg{width:100%;height:auto;display:block}
.griglia{stroke:var(--riga);stroke-width:1}.asse{stroke:var(--muto);stroke-width:1}
.tick{fill:var(--muto);font-size:11px}.gruppo{fill:var(--fg);font-size:12px}
path:hover{opacity:.8}
details{margin-top:.4rem;font-size:.85rem}summary{cursor:pointer;color:var(--muto)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;font-size:.85rem;margin-top:.5rem;width:100%}
th,td{padding:.3rem .5rem;border-bottom:1px solid var(--riga);text-align:right;white-space:nowrap}
th:first-child{text-align:left}thead th{color:var(--muto);font-weight:500}
"""


def scrivi(out: pathlib.Path = OUT) -> pathlib.Path:
    punti = pd.read_csv(out / "metriche_punti.csv").set_index(["modello", "ruolo"])
    valore = pd.read_csv(out / "metriche_valore.csv").set_index(["candidato", "contesto"])
    quote = pd.read_csv(out / "quote_ruolo.csv", index_col=0)
    stagionali = pd.read_csv(out / "quote_realizzate_per_stagione.csv", index_col=0)
    prev = pd.read_csv(out / "previsioni.csv")

    def per_ruolo(metrica):
        t = punti[metrica].unstack("modello").reindex(RUOLI)
        return t[[s for s in SERIE if s in t.columns]]

    sp = per_ruolo("spearman")
    media = sp.mean()
    dist = per_ruolo("distorsione")
    pres = per_ruolo("corr_presenze")
    val = valore.pearson.unstack("candidato").reindex(
        ["mercato: punti anno prima", "lega efficiente: proiezioni v3", "mercato: prezzi v2"])
    val = val[[s for s in SERIE if s in val.columns]]
    v3, v2 = "v3 (2 giornate osservate)", "v2"

    tiles = [
        ("Ordine dei giocatori (Spearman medio)", f"{media[v3]:.2f}", f"v2: {media[v2]:.2f}"),
        ("Distorsione media dei punti", f"{dist[v3].mean():+.1f}", f"v2: {dist[v2].mean():+.1f} punti a giocatore"),
        ("Presenze: correlazione media", f"{pres[v3].mean():.2f}", f"v2: {pres[v2].mean():.2f}"),
        ("Valore realizzato (rose dal mercato)",
         f"{val.loc['mercato: punti anno prima', v3]:.2f}",
         f"v2: {val.loc['mercato: punti anno prima', v2]:.2f} (correlazione)"),
    ]
    tiles_html = "".join(f'<div class="tile"><div class="l">{l}</div><div class="v">{v}</div>'
                         f'<div class="d">{d}</div></div>' for l, v, d in tiles)
    contab = _contabilita(prev)

    corpo = f"""
<h1>Fantacalcio: v2 → v3, misurato</h1>
<p>Quattro aste rigiocate (2022-23 → 2025-26) con i soli dati disponibili il giorno
dell'asta. Ogni modello si addestra solo sulle stagioni precedenti; la v2 è estratta da git
(commit bd4016e) e gira con il suo codice originale sugli stessi giocatori. Si confronta con i
punti fatti davvero dalla 3ª giornata, fantavoto di lega e imbattibilità inclusi.</p>
<div class="tiles">{tiles_html}</div>

<h2>1. Chi farà più punti: l'ordine dei giocatori</h2>
{grafico_barre(sp, "Correlazione di rango fra punti previsti e reali", "Spearman, dentro il ruolo, media su 4 stagioni. Più alto è meglio.", 2, NOMI_RUOLO)}
{grafico_barre(per_ruolo("spearman_rilevanti"), "Lo stesso, solo fra i giocatori che contano in asta", "Unione dei primi 3k per punti reali e per ciascun modello (k = titolari richiesti dalla lega): stesso insieme per tutti.", 2, NOMI_RUOLO)}

<h2>2. Quanti punti: distorsione</h2>
{grafico_barre(dist, "Errore medio con segno sui punti di stagione", "Punti previsti meno reali, media per giocatore. Zero è giusto; la v2 sovrastimava tutti, i portieri di 70 punti.", 1, NOMI_RUOLO)}

<h2>3. Quante presenze</h2>
{grafico_barre(pres, "Correlazione fra presenze previste e reali", "Le prime due giornate osservate sono il predittore più forte; la v2 proiettava quasi tutti come titolari.", 2, NOMI_RUOLO)}

<h2>4. Quanto vale davvero: il test economico</h2>
<p>Le stagioni rigiocate giornata per giornata con i fantavoti veri, 8 rose e il modulo migliore
ogni settimana. Il valore realizzato di un giocatore è quanto ha migliorato la sua squadra
rispetto al miglior svincolato. Il contesto cambia chi resta svincolato, quindi si prova con tre
modi diversi di comporre le rose.</p>
{grafico_barre(val, "Correlazione fra valore previsto e valore realizzato", "Pearson, tutti i ruoli insieme (premia anche la giusta scala fra ruoli), media su 4 stagioni.", 2, {"mercato: punti anno prima": "rose dal mercato", "lega efficiente: proiezioni v3": "lega efficiente", "mercato: prezzi v2": "rose dai prezzi v2"})}

<h2>5. Quanto spendere per ruolo</h2>
<p>La v2 imponeva quote fisse per ruolo. Misurata sul valore realizzato, la quota oscilla moltissimo da
una stagione all'altra: non è una costante strutturale. Nella v3 è un risultato, con un solo tasso
crediti/valore per tutti i ruoli.</p>
{_tabella_html(quote, 1)}
<p>Quota realizzata per stagione (rose dal mercato), in %:</p>
{_tabella_html(stagionali, 1)}

<h2>6. Controlli contabili</h2>
<p>Errori che producevano numeri insensati nella v2: il monte crediti sforato e portieri della stessa
squadra con più presenze di quante partite esistano.</p>
{_tabella_html(contab, 0)}
"""
    doc = ("<!doctype html><html lang=it><head><meta charset=utf-8>"
           '<meta name="viewport" content="width=device-width,initial-scale=1">'
           f"<title>Confronto v2 v3</title><style>{STILE}</style></head>"
           f'<body><main class="viz-root">{corpo}</main></body></html>')
    dest = out / "confronto.html"
    dest.write_text(doc, encoding="utf-8")
    return dest


if __name__ == "__main__":
    print(f"scritto {scrivi()}")
