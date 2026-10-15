"""Previsioni e prezzi della versione v2 (commit bd4016e) sulle aste del backtest.

Serve solo al confronto v2 → v3 (backtest/confronto.py). Il codice v2 non vive
piu' nel working tree: lo si estrae da git in una cartella temporanea e lo si
esegue CON LE SUE FUNZIONI ORIGINALI, sugli stessi universi d'asta (giocatori,
ruoli, club) del backtest v3, addestrandolo solo sulle stagioni precedenti a
ogni asta. Cosi' il confronto e' alla pari e riproducibile:

    python -m backtest.v2_legacy      # scrive output/backtest/previsioni_v2.csv
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

COMMIT_V2 = "bd4016e"
OUT = pathlib.Path("output/backtest")

_SCRIPT = r'''
import sys, pandas as pd
sys.path.insert(0, ".")
from rules import LEGA
from ingest.componenti import carica_componenti
from value.dati import carica_statistiche, con_imbattibilita
from value.proiezione import parametri_ruolo, proietta, prior_di_ruolo
from value.rigoristi import proietta_rigori
from value.rimpiazzo import valore_sopra_rimpiazzo
from value.budget import quote_ruolo
U = pd.read_csv(sys.argv[1])
m_all = carica_componenti(); stat_all = carica_statistiche(); ci_all = con_imbattibilita(stat_all)
out = []
for t, u in U.groupby("stagione"):
    m = m_all[m_all.stagione < t]; stat = stat_all[stat_all.stagione < t]
    par = parametri_ruolo(m); proj = proietta(LEGA, 0, m=m, par=par).set_index(["Id", "R"])
    rig = proietta_rigori(LEGA, 0, stat=stat,
                          squadra_2026={int(i): s for i, s in zip(u.Id, u.squadra)}).set_index("Id")
    rows = []
    for _, r in u.iterrows():
        d = dict(stagione=t, Id=r.Id, R=r.ruolo)
        if (r.Id, r.ruolo) in proj.index:
            p = proj.loc[(r.Id, r.ruolo)]; d.update(pv_proj=p.pv_proj, punti_base=p.punti_base)
        else:
            pr = prior_di_ruolo(r.ruolo, LEGA, 0, par); d.update(pv_proj=pr["pv_proj"], punti_base=pr["punti_base"])
        d["rig"] = float(rig.rigore_punti.get(r.Id, 0.0))
        d["rigori_attesi"] = float(rig.rigori_attesi.get(r.Id, 0.0))
        rows.append(d)
    L = pd.DataFrame(rows); L["punti_proj"] = L.punti_base + L.rig
    L["vor"] = valore_sopra_rimpiazzo(L, LEGA)
    q = quote_ruolo(LEGA, m=ci_all[ci_all.stagione < t]); L["prezzo"] = 1.0
    for r, b in q.items():
        msk = L.R == r; v = L.loc[msk, "vor"].sum()
        if v > 0:
            L.loc[msk, "prezzo"] = L.loc[msk, "vor"] / v * b * LEGA.crediti_contendibili + 1
    out.append(L)
pd.concat(out).rename(columns={"R": "ruolo"}).to_csv(sys.argv[2], index=False)
'''


def genera(universi: "pd.DataFrame", destinazione: pathlib.Path = OUT / "previsioni_v2.csv",
           python: str = sys.executable) -> pathlib.Path:
    """Esegue la v2 sugli universi (colonne stagione, Id, ruolo, squadra)."""
    radice = pathlib.Path.cwd()
    destinazione = destinazione.resolve()
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        archivio = subprocess.run(["git", "archive", COMMIT_V2], cwd=radice,
                                  check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tmp)], input=archivio, check=True)
        # i dati sono locali e fuori da git: la v2 li legge per percorso relativo.
        # Il suo pannello componenti va in una copia, per non toccare data/panel/.
        (tmp / "data").mkdir()
        (tmp / "data" / "raw").symlink_to(radice / "data" / "raw")
        (tmp / "data" / "panel").mkdir()
        partite = radice / "data" / "panel" / "partite.csv"
        if partite.exists():
            (tmp / "data" / "panel" / "partite.csv").symlink_to(partite)
        universi[["stagione", "Id", "ruolo", "squadra"]].to_csv(tmp / "universi.csv", index=False)
        (tmp / "esegui_v2.py").write_text(_SCRIPT)
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        subprocess.run([python, "esegui_v2.py", "universi.csv", str(destinazione)],
                       cwd=tmp, check=True, env=env)
    return destinazione


if __name__ == "__main__":
    import pandas as pd
    from backtest.storico import proiezioni_storiche
    df = proiezioni_storiche()
    print(f"scritto {genera(df)}")
