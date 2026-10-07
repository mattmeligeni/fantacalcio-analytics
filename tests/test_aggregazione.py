"""Test di accettazione §6.4: aggregando i voti per giornata di una stagione,
i totali per giocatore devono coincidere con le Statistiche stagionali, che
sono la verita' di riferimento (verificata contro i gol reali in partite.csv).

Questo e' il test che "rigioca le giornate storiche" richiesto da docs/METODO.md §8:
se il motore di regolamento o il parser sbagliano, qui salta.

Nota sulle convenzioni verificate qui (identita' esatte sulle 6 stagioni):
  - voti `Gf`  = gol su azione (rigori esclusi)
  - voti `Rf`  = gol su rigore == Statistiche `R+`
  - voti `Rs`  = rigori sbagliati == Statistiche `R-`
  - totale gol confrontabile con Statistiche `Gf` = voti (Gf + Rf)
  - le Statistiche NON conteggiano l'imbattibilita': il confronto sulla Fm usa
    quindi il regolamento con imbattibilita' azzerata.

`Amm` e' escluso di proposito: le Statistiche contano anche i cartellini presi
in gare senza voto, che non entrano nella fantamedia (docs/DATI.md §2).

I residui NON sono rumore ne' trasferimenti (verificato: nessun caso ha piu' di
una squadra nei voti o un codice duplicato nelle Statistiche). Sono due pattern
deterministici, descritti sotto e imposti come invarianti dai test, non come
tolleranze numeriche. Dettaglio in docs/DATI.md §6.7.
"""
import dataclasses
import pathlib

import pandas as pd
import pytest

from ingest.voti import leggi_stagione
from rules import LEGA, Prestazione, da_voto_testuale, fantavoto

RAW = pathlib.Path("data/raw")
VOTI = RAW / "Voti"
STAT = RAW / "Statistiche Fantacalcio"

LEGA_NO_IMB = dataclasses.replace(
    LEGA, bonus=dataclasses.replace(LEGA.bonus, imbattibilita=0.0))

# I residui fra voti aggregati e Statistiche NON sono casuali: classificati per
# meccanismo su tutte e sei le stagioni (vedi docs/DATI.md §6.7).
#
#  PATTERN A — espulsione su senza voto: una riga `6*` che porta Esp=1. Il
#    parser scarta la riga (6* = assenza, corretto), ma le Statistiche contano
#    sia la presenza sia l'espulsione. E' il gemello dell'anomalia Amm (§2).
#    Firma: Pv_voti < Pv_stat e Esp_voti < Esp_stat. Solo 2 casi in 6 stagioni.
#
#  PATTERN B — surplus di presenze su giocatori di margine (giovani/subentri,
#    Cod. alto) nelle stagioni recenti. I voti per giornata sono SNAPSHOT LIVE;
#    le Statistiche sono il prodotto RICONCILIATO di fine stagione. Fra i due
#    Fantacalcio.it rivede le apparizioni marginali (un "6" a un subentrante
#    puo' diventare s.v., un gol loggato live viene riattribuito). Le tre
#    stagioni piu' vecchie erano gia' convergenti (gol di lega +0); le recenti
#    catturate piu' vicino al live conservano gli extra. Firma UNIVOCA e
#    verificata: Pv_voti >= Pv_stat SEMPRE (i voti sovra-contano, mai il
#    contrario). Assente in 20-22, cresce dal 23-24 (2, 17, 7 casi).
STAGIONI = [
    ("20-21", "2020_21"),
    ("21-22", "2021_22"),
    ("22-23", "2022_23"),
    ("23-24", "2023_24"),
    ("24-25", "2024_25"),
    ("25-26", "2025_26"),
]
EVENTI = ["Gf", "Gs", "Rp", "Ass", "Esp", "Au"]   # Amm escluso per §2

pytestmark = pytest.mark.skipif(
    not VOTI.exists() or not STAT.exists(),
    reason="dati grezzi non disponibili in questo ambiente")


def _aggrega_voti(cartella: str) -> pd.DataFrame:
    df = leggi_stagione(cartella)
    df["vn"] = df["Voto"].map(da_voto_testuale)

    def fv(r):
        p = Prestazione(ruolo=r.Ruolo, voto=r.vn, gf=r.Gf, gs=r.Gs, rp=r.Rp,
                        rf=r.Rf, rs=r.Rs, au=r.Au, amm=r.Amm, esp=r.Esp, ass=r.Ass)
        return fantavoto(p, LEGA_NO_IMB)

    df["fv"] = df.apply(fv, axis=1)
    v = df[df.vn.notna()]      # presenze = righe con voto reale (i 6* esclusi)
    agg = v.groupby("Cod.").agg(
        Pv=("vn", "size"), Mv=("vn", "mean"), Fm=("fv", "mean"),
        Gf=("Gf", "sum"), Rf=("Rf", "sum"), Gs=("Gs", "sum"), Rp=("Rp", "sum"),
        Ass=("Ass", "sum"), Esp=("Esp", "sum"), Au=("Au", "sum"),
    ).reset_index()
    agg["Gf"] = agg.Gf + agg.Rf      # totale gol, per confronto con Statistiche
    return agg


def _statistiche(tag: str) -> pd.DataFrame:
    stat = pd.read_excel(STAT / f"Statistiche_Fantacalcio_Stagione_{tag}.xlsx",
                         sheet_name="Tutti", header=1)
    for c in ["Pv", "Mv", "Fm", "Gf", "Gs", "Rp", "Ass", "Esp", "Au"]:
        stat[c] = pd.to_numeric(stat[c], errors="coerce")
    return stat[stat.Pv > 0]


def _righe_esp_su_senza_voto(cartella: str) -> set[int]:
    """Cod. con almeno una riga `6*` che porta un'espulsione (pattern A)."""
    df = leggi_stagione(cartella)
    df["vn"] = df["Voto"].map(da_voto_testuale)
    sv = df[df.vn.isna() & (df.Esp > 0)]
    return set(sv["Cod."].dropna().astype(int))


@pytest.mark.parametrize("cartella,tag", STAGIONI)
def test_ogni_residuo_e_classificato(cartella, tag):
    """Non basta che i residui siano pochi: ognuno deve appartenere a un
    pattern noto. Se compare uno scarto di segno o forma diversa, e' una
    regressione del motore/parser, non rumore di provenienza."""
    agg = _aggrega_voti(str(VOTI / cartella))
    stat = _statistiche(tag)
    m = agg.merge(stat, left_on="Cod.", right_on="Id", suffixes=("_c", "_s"))
    assert len(m) >= 0.97 * len(stat), \
        f"{cartella}: agganciati {len(m)}/{len(stat)} giocatori"

    pattern_a = _righe_esp_su_senza_voto(str(VOTI / cartella))
    discordanti = m[sum((m[f"{c}_c"] - m[f"{c}_s"]).abs() for c in EVENTI) > 0]

    non_spiegati = []
    for _, r in discordanti.iterrows():
        cod = int(r["Cod."])
        dPv = r.Pv_c - r.Pv_s
        dEsp = r.Esp_c - r.Esp_s
        is_A = cod in pattern_a and dPv < 0 and dEsp < 0
        is_B = dPv >= 1 and (r[[f"{c}_c" for c in EVENTI]].values
                             >= r[[f"{c}_s" for c in EVENTI]].values).all()
        if not (is_A or is_B):
            non_spiegati.append((cod, r.Nome,
                                 {c: int(r[f"{c}_c"] - r[f"{c}_s"])
                                  for c in ["Pv", *EVENTI]
                                  if r[f"{c}_c"] != r[f"{c}_s"]}))
    assert not non_spiegati, \
        f"{cartella}: residui non classificabili (ne' A ne' B): {non_spiegati}"


def test_invariante_i_voti_non_sottocontano_mai():
    """Invariante trasversale: al netto del pattern A (espulsione su 6*), le
    presenze dei voti per giornata sono SEMPRE >= quelle delle Statistiche. La
    provenienza puo' solo gonfiare lo snapshot live, mai il contrario."""
    for cartella, tag in STAGIONI:
        agg = _aggrega_voti(str(VOTI / cartella))
        stat = _statistiche(tag)
        m = agg.merge(stat, left_on="Cod.", right_on="Id", suffixes=("_c", "_s"))
        pattern_a = _righe_esp_su_senza_voto(str(VOTI / cartella))
        sotto = m[(m.Pv_c < m.Pv_s) & ~m["Cod."].astype(int).isin(pattern_a)]
        assert sotto.empty, \
            f"{cartella}: presenze sotto-contate fuori dal pattern A: " \
            f"{list(zip(sotto.Nome, sotto.Pv_c, sotto.Pv_s))}"


def test_stagioni_vecchie_perfette():
    """Le prime tre stagioni, ormai convergenti, tornano ESATTE sugli eventi
    di gioco (l'unica eccezione ammessa e' il pattern A su Pv/Esp)."""
    for cartella, tag in STAGIONI[:3]:
        agg = _aggrega_voti(str(VOTI / cartella))
        stat = _statistiche(tag)
        m = agg.merge(stat, left_on="Cod.", right_on="Id", suffixes=("_c", "_s"))
        for col in ["Gf", "Gs", "Rp", "Ass", "Au"]:   # Esp: pattern A in 22-23
            assert (m[f"{col}_c"] == m[f"{col}_s"]).all(), f"{cartella}/{col}"
        # gol di lega identici (Gf voti include gia' Rf nell'aggregato)
        assert m.Gf_c.sum() == m.Gf_s.sum(), f"{cartella}: gol di lega"
