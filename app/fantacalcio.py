"""Applicazione: listino, asta dal vivo, mercato e gestione settimanale.

    streamlit run app/fantacalcio.py

Funziona offline una volta importati i dati (la rete serve solo per scaricare
Understat). Lo stato della lega (rose, crediti, movimenti) e' in
data/app/lega.json e si salva a ogni operazione. Tutta la logica sta in
auction/, inseason/, value/: qui c'e' solo l'interfaccia.
"""
from __future__ import annotations

import pathlib
import sys

RADICE = pathlib.Path(__file__).resolve().parents[1]
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

import os  # noqa: E402
from datetime import datetime  # noqa: E402

os.chdir(RADICE)            # i percorsi dei dati sono relativi alla radice

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from auction import stato as sa  # noqa: E402
from inseason.formazione import formazione, svincoli  # noqa: E402
from rules import LEGA  # noqa: E402

STATO = pathlib.Path("data/app/lega.json")
LISTINO = pathlib.Path("output/listino.csv")
NOMI_RUOLO = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}
FORMATI = {
    "attesi": st.column_config.NumberColumn("Punti attesi", format="%.1f"),
    "p_voto": st.column_config.NumberColumn("Prob. voto", format="%.2f"),
    "fm_proj": st.column_config.NumberColumn("Fantamedia", format="%.2f"),
    "pv_proj": st.column_config.NumberColumn("Presenze", format="%.1f"),
    "prezzo": st.column_config.NumberColumn("Prezzo", format="%d"),
    "prezzo_ora": st.column_config.NumberColumn("Prezzo ora", format="%d"),
    "fvm_riscalato": st.column_config.NumberColumn("FVM risc.", format="%.0f"),
    "minuti_recenti": st.column_config.ListColumn("Minuti ultime 3"),
    "titolare_ultima": st.column_config.CheckboxColumn("Titolare l'ultima"),
    "motivo": st.column_config.TextColumn("Perché", width="large"),
}

st.set_page_config(page_title="Fantacalcio", page_icon="⚽", layout="wide")


# --------------------------------------------------------------------------- #
# dati
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def leggi_listino(mtime: float) -> pd.DataFrame:
    return pd.read_csv(LISTINO, keep_default_na=True).fillna({"gerarchia": "", "motivo": ""})


@st.cache_data(show_spinner=False)
def minuti_recenti(mtime: float) -> pd.DataFrame:
    try:
        from ingest import anagrafica as an
        from ingest.corrente import carica_stagione_in_corso
        c = carica_stagione_in_corso()
        if c is None or c.minuti is None:
            return pd.DataFrame()
        mappa = an.aggancia(c.osservato, c.minuti)
        return an.minuti_recenti(c.minuti, mappa)
    except Exception as e:  # noqa: BLE001  (informazione accessoria: non blocca l'app)
        st.warning(f"minuti Understat non disponibili: {e}")
        return pd.DataFrame()


def listino() -> pd.DataFrame | None:
    if not LISTINO.exists():
        return None
    return leggi_listino(LISTINO.stat().st_mtime)


def ricalcola():
    from value.report import scrivi_artefatti
    with st.spinner("Addestro i modelli sulle stagioni passate e ricalcolo il listino (~1 minuto)…"):
        scrivi_artefatti()
    leggi_listino.clear()
    minuti_recenti.clear()


def stato() -> sa.StatoLega | None:
    if "stato" not in st.session_state:
        st.session_state.stato = sa.carica(STATO)
    return st.session_state.stato


def salva(s: sa.StatoLega):
    sa.salva(s, STATO)
    st.session_state.stato = s


def etichetta(r) -> str:
    return f"{r.Nome} ({r.ruolo}, {r.squadra}) · {int(r.prezzo)} cr"


# --------------------------------------------------------------------------- #
# pagine
# --------------------------------------------------------------------------- #
def _data(iso: str) -> str:
    """'2026-10-15' -> '15/10/2026'."""
    a, m, g = iso.split("-")
    return f"{g}/{m}/{a}"


def pagina_dati():
    from ingest import importa
    st.header("Dati")
    try:
        stag = importa.stagione_corrente()
    except FileNotFoundError:
        st.error("Nessun listone in data/raw/: scarica il listone da Fantacalcio.it e importalo.")
        stag = None
    c1, c2, c3 = st.columns(3)
    c1.metric("Stagione", stag or "—")
    f = importa.statistiche_correnti(stag) if stag else None
    c2.metric("Statistiche in corso", _data(f.name.split("__")[-1].removesuffix(".xlsx")) if f else "nessuna")
    u = importa.understat_corrente(stag) if stag else None
    c3.metric("Understat", _data(u.name) if u else "nessuno")

    st.subheader("Aggiorna")
    st.write("1. Scarica da Fantacalcio.it le **Statistiche** della stagione (e se vuoi i "
             "**voti per giornata** e il **listone**) nella cartella Download.")
    cartella = st.text_input("Cartella dei file scaricati", str(importa.DOWNLOAD))
    if st.button("Importa i file Fantacalcio"):
        for riga in importa.importa_download(pathlib.Path(cartella).expanduser()):
            st.write(riga)
    st.write("2. Scarica le partite e i minuti della stagione da Understat (serve la rete).")
    if st.button("Scarica Understat"):
        try:
            with st.spinner("Scarico da Understat…"):
                for riga in importa.scarica_understat(stag):
                    st.write(riga)
        except Exception as e:  # noqa: BLE001
            st.error(f"Download non riuscito: {e}")
    st.write("3. Ricalcola il listino con tutto cio' che si sa adesso.")
    if st.button("Ricalcola il listino", type="primary"):
        ricalcola()
        st.success("Listino aggiornato.")
    lis = listino()
    if lis is not None:
        quando = datetime.fromtimestamp(LISTINO.stat().st_mtime)
        st.caption(f"Listino attuale: {len(lis)} giocatori, aggiornato il {quando:%d/%m/%Y %H:%M}.")


def pagina_listino():
    st.header("Listino")
    lis = listino()
    if lis is None:
        st.info("Nessun listino: vai su Dati e premi «Ricalcola il listino».")
        return
    s = stato()
    presi = set(s.rose().Id) if s else set()
    c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
    ruoli = c1.multiselect("Ruolo", list(NOMI_RUOLO), default=list(NOMI_RUOLO))
    squadre = c2.multiselect("Squadra", sorted(lis.squadra.unique()))
    cerca = c3.text_input("Cerca")
    solo_liberi = c4.checkbox("Solo liberi", value=bool(presi))
    d = lis[lis.ruolo.isin(ruoli)]
    if squadre:
        d = d[d.squadra.isin(squadre)]
    if cerca:
        d = d[d.Nome.str.contains(cerca, case=False)]
    if solo_liberi:
        d = d[~d.Id.isin(presi)]
    cols = ["Nome", "ruolo", "squadra", "prezzo", "fvm_riscalato", "diff_vs_fvm", "pv_proj",
            "fm_proj", "rigori_attesi", "punti_proj", "valore", "motivo"]
    st.dataframe(
        d.sort_values("prezzo", ascending=False)[cols], hide_index=True, use_container_width=True,
        column_config={
            "prezzo": st.column_config.NumberColumn("Prezzo", format="%d"),
            "fvm_riscalato": st.column_config.NumberColumn("FVM risc.", format="%.0f"),
            "diff_vs_fvm": st.column_config.NumberColumn("Diff.", format="%+.0f"),
            "pv_proj": st.column_config.NumberColumn("Presenze", format="%.1f"),
            "fm_proj": st.column_config.NumberColumn("Fantamedia", format="%.2f"),
            "rigori_attesi": st.column_config.NumberColumn("Rigori", format="%.1f"),
            "punti_proj": st.column_config.NumberColumn("Punti", format="%.0f"),
            "valore": st.column_config.NumberColumn("Valore", format="%.1f"),
            "motivo": st.column_config.TextColumn("Perché", width="large"),
        })
    q = lis.groupby("ruolo").apply(lambda x: (x.prezzo - 1).clip(lower=0).sum(), include_groups=False)
    st.caption("Quota crediti per ruolo: " + " · ".join(
        f"{r} {q[r] / q.sum() * 100:.0f}%" for r in ["P", "D", "C", "A"]))


def configura_lega():
    st.subheader("Configura la lega")
    with st.form("config"):
        nomi = st.text_area("Nomi delle squadre, uno per riga",
                            "\n".join(f"Squadra {i + 1}" for i in range(LEGA.squadre)))
        lista = [n.strip() for n in nomi.splitlines() if n.strip()]
        mia = st.text_input("La mia squadra (uno dei nomi sopra)", lista[0] if lista else "")
        crediti = st.number_input("Crediti per squadra", 1, 5000, LEGA.crediti_per_squadra)
        if st.form_submit_button("Crea"):
            if len(lista) != LEGA.squadre:
                st.error(f"Servono {LEGA.squadre} squadre (rules/config.py).")
            elif mia not in lista:
                st.error("La mia squadra deve essere uno dei nomi.")
            else:
                salva(sa.StatoLega(squadre=lista, mia=mia, crediti_iniziali=int(crediti)))
                st.rerun()


def pagina_asta():
    st.header("Asta e mercato")
    lis = listino()
    s = stato()
    if lis is None:
        st.info("Prima calcola il listino (pagina Dati).")
        return
    if s is None:
        configura_lega()
        return
    correnti = s.prezzi_correnti(lis)
    rie = s.riepilogo()
    c1, c2, c3 = st.columns(3)
    c1.metric("Inflazione (pagato / listino)", f"{s.inflazione(lis):.2f}")
    c2.metric("Fattore sui prezzi rimasti", f"{correnti.attrs.get('fattore', 1):.2f}")
    c3.metric("Giocatori assegnati", len(s.rose()))

    with st.form("assegna", clear_on_submit=True):
        a1, a2, a3, a4 = st.columns([3, 2, 1, 1])
        opzioni = correnti.reset_index(drop=True)
        scelto = a1.selectbox("Giocatore", range(len(opzioni)),
                              format_func=lambda i: f"{etichetta(opzioni.iloc[i])} → ora {int(opzioni.prezzo_ora.iloc[i])}",
                              index=None, placeholder="cerca per nome…")
        squadra = a2.selectbox("Squadra", s.squadre, index=s.squadre.index(s.mia))
        prezzo = a3.number_input("Prezzo", 1, 1000, 1)
        tipo = a4.selectbox("Tipo", ["asta", "mercato"])
        if st.form_submit_button("Assegna", type="primary") and scelto is not None:
            r = opzioni.iloc[scelto]
            try:
                s.acquista(int(r.Id), r.Nome, r.ruolo, squadra, int(prezzo), tipo)
                salva(s)
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    b1, b2 = st.columns([1, 3])
    if b1.button("Annulla l'ultima operazione") and s.annulla_ultimo():
        salva(s)
        st.rerun()

    st.subheader("Squadre")
    st.dataframe(rie.rename(columns={"slot_liberi": "slot liberi", "liberi_P": "P", "liberi_D": "D",
                                     "liberi_C": "C", "liberi_A": "A",
                                     "offerta_massima": "offerta max"}), use_container_width=True)

    st.subheader("Migliori disponibili, prezzo di adesso")
    tabs = st.tabs([NOMI_RUOLO[r] for r in NOMI_RUOLO])
    for t, r in zip(tabs, NOMI_RUOLO):
        with t:
            st.dataframe(correnti[correnti.ruolo == r].head(25)[
                ["Nome", "squadra", "prezzo_ora", "prezzo", "fvm_riscalato", "pv_proj", "fm_proj", "motivo"]],
                hide_index=True, use_container_width=True, column_config=FORMATI)

    st.subheader("Rose")
    rose = s.rose()
    sq = st.selectbox("Squadra da vedere", s.squadre, index=s.squadre.index(s.mia))
    mia = rose[rose.squadra == sq].merge(lis[["Id", "squadra", "prezzo"]].rename(
        columns={"squadra": "club", "prezzo": "listino"}), on="Id", how="left")
    st.dataframe(mia.sort_values(["ruolo", "prezzo"], ascending=[True, False]),
                 hide_index=True, use_container_width=True)
    if not mia.empty:
        c = st.selectbox("Svincola / cedi", range(len(mia)), index=None,
                         format_func=lambda i: f"{mia.Nome.iloc[i]} ({mia.ruolo.iloc[i]})")
        if c is not None and st.button("Conferma svincolo"):
            s.cedi(int(mia.Id.iloc[c]))
            salva(s)
            st.rerun()


def pagina_squadra():
    st.header("La mia squadra")
    lis = listino()
    s = stato()
    if lis is None or s is None:
        st.info("Servono il listino (Dati) e la lega configurata (Asta e mercato).")
        return
    rosa = s.rose()
    rosa = rosa[rosa.squadra == s.mia][["Id"]].merge(lis, on="Id", how="left")
    if rosa.empty:
        st.info("La tua rosa e' vuota: assegna i giocatori nella pagina Asta e mercato.")
        return
    mr = minuti_recenti(LISTINO.stat().st_mtime)
    if not mr.empty:
        rosa = rosa.join(mr, on="Id")
    indisp = st.multiselect("Indisponibili questa giornata (infortuni, squalifiche, notizie)",
                            rosa.Id.tolist(), format_func=lambda i: rosa.set_index("Id").Nome[i])
    try:
        f = formazione(rosa, set(indisp))
    except ValueError as e:
        st.error(str(e))
        return
    c1, c2 = st.columns(2)
    c1.metric("Modulo consigliato", f["modulo"])
    c2.metric("Punti attesi", f["punti_attesi"])
    cols = [c for c in ["Nome", "ruolo", "squadra", "attesi", "p_voto", "fm_proj",
                        "minuti_recenti", "titolare_ultima"] if c in f["titolari"].columns]
    st.subheader("Titolari")
    st.dataframe(f["titolari"][cols], hide_index=True, use_container_width=True, column_config=FORMATI)
    st.subheader("Panchina (ordine per ruolo)")
    st.dataframe(f["panchina"][cols], hide_index=True, use_container_width=True, column_config=FORMATI)

    st.subheader("Svincoli consigliati")
    occupati = set(s.rose().Id)
    liberi = lis[~lis.Id.isin(occupati)]
    sv = svincoli(rosa, liberi)
    if sv.empty:
        st.write("Nessun libero vale piu' dei tuoi peggiori.")
    else:
        st.dataframe(sv, hide_index=True, use_container_width=True)


PAGINE = {"Dati": pagina_dati, "Listino": pagina_listino,
          "Asta e mercato": pagina_asta, "La mia squadra": pagina_squadra}
scelta = st.sidebar.radio("Fantacalcio", list(PAGINE))
PAGINE[scelta]()
