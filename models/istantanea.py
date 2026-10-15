"""L'istantanea d'asta: tutto e solo cio' che si sa il giorno dell'asta.

E' il contratto unico fra dati e modelli. Ogni modello riceve un'`Istantanea` e
non vede altro, quindi lo stesso codice serve:
  - per il listino vero (`per_asta`: listone 2026-27 + tutto lo storico);
  - per il backtest (`da_storico`: si rimette l'orologio all'asta di una stagione
    passata e si nasconde tutto cio' che e' venuto dopo).

La lega fa l'asta a stagione avviata (docs/METODO.md §3): le prime giornate sono
OSSERVATE e servono ad aggiornare la disponibilita' (chi gioca davvero, con che
club), quasi per nulla il rendimento. `giornata_asta` e' l'ultima giornata
giocata prima dell'asta; i punti contano dalla giornata successiva o dalla prima
conteggiata se e' piu' avanti.

Garanzia anti-sbirciata: `storico` e `giornate_storiche` contengono solo stagioni
precedenti; `osservate` solo le giornate <= giornata_asta della stagione d'asta.
Il test tests/test_istantanea.py lo impone.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ingest.fonti import carica_partite
from ingest.panel import aggrega_voti, carica_giornate, pannello_stagioni

# Una stagione storica ha 38 giornate. Le giornate del girone di ritorno partono
# dalla 20ª: chi compare per la prima volta da li' in poi e non era in Serie A
# l'anno prima e' un arrivo di gennaio, che all'asta d'estate non esisteva.
GIORNATE_STAGIONE = 38
PRIMA_DEL_RITORNO = 20


@dataclass(frozen=True)
class Istantanea:
    stagione: str                     # stagione d'asta, es. "2025-26"
    giornata_asta: int                # ultima giornata giocata prima dell'asta
    universo: pd.DataFrame            # Id, Nome, ruolo, squadra (+ fvm_meta, quotazione)
    storico: pd.DataFrame             # pannello_stagioni, solo stagioni < stagione
    giornate_storiche: pd.DataFrame   # pannello giornate, solo stagioni < stagione
    osservate: pd.DataFrame           # giornate della stagione d'asta <= giornata_asta
    partite: pd.DataFrame             # partite delle stagioni < stagione
    # stagione in corso gia' aggregata (Statistiche) quando mancano i voti per
    # giornata; e partite gia' giocate della stagione d'asta (gol e xG)
    osservato: pd.DataFrame | None = None
    partite_osservate: pd.DataFrame | None = None

    def aggregato_osservato(self) -> pd.DataFrame:
        """Somme per Id delle giornate gia' giocate (formato aggrega_voti),
        dai voti per giornata se ci sono, altrimenti dall'aggregato."""
        if self.osservato is not None:
            return self.osservato
        if len(self.osservate):
            return aggrega_voti(self.osservate)
        return pd.DataFrame(
            columns=["stagione", "Id", "pv", "sv", "voto_s", "c_azione", "c_rigore",
                     "c_malus", "c_port", "gf", "rf", "rs", "rc", "gs", "cs"])

    @property
    def squadre(self) -> list[str]:
        return sorted(self.universo.squadra.unique())

    @property
    def stagioni_storiche(self) -> list[str]:
        return sorted(self.storico.stagione.unique())


def _stagione_precedente(stagione: str) -> str:
    a = int(stagione[:4]) - 1
    return f"{a}-{(a + 1) % 100:02d}"


def da_storico(stagione: str, giornata_asta: int = 2,
               giornate: pd.DataFrame | None = None,
               stagioni: pd.DataFrame | None = None,
               partite: pd.DataFrame | None = None) -> Istantanea:
    """Ricostruisce l'asta di una stagione passata, per il backtest.

    Universo: i tesserati della stagione (Statistiche + voti), meno gli arrivi
    di gennaio dall'estero o dalla B (prima apparizione dalla 20ª giornata e
    nessuna riga nella stagione precedente). Club all'asta: quello con cui
    compare per la prima volta nel girone d'andata; per chi si e' mosso a
    gennaio senza aver giocato prima, il club di fine stagione precedente; per
    chi non ha mai giocato, il club delle Statistiche.

    Limite dichiarato: un tesserato che non gioca mai e cambia squadra a
    gennaio resta col club d'arrivo. Riguarda pochi giocatori a zero presenze,
    identico per tutti i modelli confrontati.
    """
    if giornate is None:
        giornate = carica_giornate()
    if stagioni is None:
        stagioni = pannello_stagioni(giornate)
    if partite is None:
        partite = carica_partite()
    prec = _stagione_precedente(stagione)
    cur = stagioni[stagioni.stagione == stagione].copy()
    if cur.empty:
        raise ValueError(f"stagione {stagione} assente dal pannello")
    ieri = stagioni[stagioni.stagione == prec].set_index("Id")

    # le 20 squadre della stagione: quelle con cui i giocatori scendono in campo
    squadre = set(cur.squadra_inizio.dropna())
    club_ieri = cur.Id.map(ieri.squadra)
    # arrivo di gennaio = prima apparizione nel ritorno e, d'estate, fuori dalla
    # Serie A (assente l'anno prima, o in un club poi retrocesso)
    tardivo = cur.prima_giornata >= PRIMA_DEL_RITORNO
    gennaio = tardivo & ~club_ieri.isin(squadre)
    cur = cur[~gennaio].copy()
    club_ieri = club_ieri[~gennaio]

    club = cur.squadra_inizio.where(cur.prima_giornata < PRIMA_DEL_RITORNO)
    club = club.fillna(club_ieri.where(cur.prima_giornata >= PRIMA_DEL_RITORNO))
    cur["squadra"] = club.fillna(cur.squadra)
    if not set(cur.squadra) <= squadre:
        raise ValueError(f"{stagione}: club fuori dalla Serie A nell'universo "
                         f"{sorted(set(cur.squadra) - squadre)}")

    universo = cur[["Id", "Nome", "ruolo", "squadra"]].reset_index(drop=True)
    return Istantanea(
        stagione=stagione,
        giornata_asta=giornata_asta,
        universo=universo,
        storico=stagioni[stagioni.stagione < stagione].reset_index(drop=True),
        giornate_storiche=giornate[giornate.stagione < stagione].reset_index(drop=True),
        osservate=giornate[(giornate.stagione == stagione)
                           & (giornate.giornata <= giornata_asta)].reset_index(drop=True),
        partite=partite[partite.stagione < stagione].reset_index(drop=True),
        partite_osservate=partite[(partite.stagione == stagione)
                                  & (partite.giornata <= giornata_asta)].reset_index(drop=True),
    )


def per_asta(listone: pd.DataFrame, stagione: str, giornata_asta: int = 2,
             giornate: pd.DataFrame | None = None,
             stagioni: pd.DataFrame | None = None,
             partite: pd.DataFrame | None = None,
             osservato: pd.DataFrame | None = None,
             partite_osservate: pd.DataFrame | None = None) -> Istantanea:
    """L'asta vera (o il mercato in corso): universo dal listone, storico
    completo, e quanto gia' giocato della stagione: voti per giornata se sono in
    data/raw/Voti/, altrimenti l'aggregato `osservato` (ingest/corrente.py), e
    le partite gia' giocate (Understat)."""
    if giornate is None:
        giornate = carica_giornate()
    if stagioni is None:
        stagioni = pannello_stagioni(giornate)
    if partite is None:
        partite = carica_partite()
    cols = [c for c in ["Id", "Nome", "ruolo", "squadra", "fvm_meta", "quotazione", "eta"]
            if c in listone.columns]
    return Istantanea(
        stagione=stagione,
        giornata_asta=giornata_asta,
        universo=listone[cols].reset_index(drop=True),
        storico=stagioni[stagioni.stagione < stagione].reset_index(drop=True),
        giornate_storiche=giornate[giornate.stagione < stagione].reset_index(drop=True),
        osservate=giornate[(giornate.stagione == stagione)
                           & (giornate.giornata <= giornata_asta)].reset_index(drop=True),
        partite=partite[partite.stagione < stagione].reset_index(drop=True),
        osservato=osservato,
        partite_osservate=partite_osservate,
    )
