"""Stato della lega durante l'asta e durante la stagione. Logica pura.

Tiene le rose delle 8 squadre e i crediti, e risponde in ogni istante a:
  - quanto puo' offrire al massimo ogni squadra (deterministico):
        offerta_massima = crediti_residui − (slot_ancora_da_riempire − 1)
  - quanto la stanza sta pagando rispetto al listino (fattore di inflazione);
  - quanto valgono ADESSO i giocatori rimasti: i crediti ancora spendibili sopra
    il pavimento si ripartiscono sul valore rimasto, quindi se i primi nomi sono
    stati strapagati i successivi costeranno meno (e viceversa).

Lo stato si salva su disco a ogni operazione (scrittura atomica: file
temporaneo + rename), cosi' un crash a meta' asta non perde nulla. Nessuna
dipendenza da Streamlit: l'interfaccia e' in app/.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime

import pandas as pd

from rules import LEGA, LeagueRules

RUOLI = ("P", "D", "C", "A")


@dataclass
class Movimento:
    Id: int
    Nome: str
    ruolo: str
    squadra: str          # fantasquadra
    prezzo: int
    tipo: str = "asta"    # asta | mercato | cessione
    quando: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class StatoLega:
    squadre: list[str]
    mia: str
    crediti_iniziali: int = LEGA.crediti_per_squadra
    movimenti: list[Movimento] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # rose e crediti
    # ------------------------------------------------------------------ #
    def rose(self) -> pd.DataFrame:
        """Giocatori attualmente in rosa (acquisti meno cessioni)."""
        righe = {}
        for m in self.movimenti:
            if m.tipo == "cessione":
                righe.pop(m.Id, None)
            else:
                righe[m.Id] = m
        cols = ["Id", "Nome", "ruolo", "squadra", "prezzo"]
        if not righe:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame([asdict(m) for m in righe.values()])[cols]

    def proprietario(self, Id: int) -> str | None:
        r = self.rose()
        hit = r[r.Id == Id]
        return None if hit.empty else str(hit.squadra.iloc[0])

    def riepilogo(self, lega: LeagueRules = LEGA) -> pd.DataFrame:
        """Per squadra: crediti residui, slot liberi per ruolo, offerta massima."""
        r = self.rose()
        righe = []
        for sq in self.squadre:
            spesi = sum(m.prezzo for m in self.movimenti
                        if m.squadra == sq and m.tipo != "cessione")
            rimborsi = sum(m.prezzo for m in self.movimenti
                           if m.squadra == sq and m.tipo == "cessione")
            crediti = self.crediti_iniziali - spesi + rimborsi
            mia_r = r[r.squadra == sq]
            liberi = {ruolo: lega.rosa.slot[ruolo] - int((mia_r.ruolo == ruolo).sum())
                      for ruolo in RUOLI}
            vuoti = sum(liberi.values())
            righe.append(dict(squadra=sq, crediti=crediti, slot_liberi=vuoti,
                              **{f"liberi_{k}": v for k, v in liberi.items()},
                              offerta_massima=lega.offerta_massima(crediti, vuoti) if vuoti else 0))
        return pd.DataFrame(righe).set_index("squadra")

    # ------------------------------------------------------------------ #
    # operazioni (validate: falliscono con un messaggio chiaro)
    # ------------------------------------------------------------------ #
    def acquista(self, Id: int, Nome: str, ruolo: str, squadra: str, prezzo: int,
                 tipo: str = "asta", lega: LeagueRules = LEGA) -> Movimento:
        if squadra not in self.squadre:
            raise ValueError(f"squadra sconosciuta: {squadra}")
        if ruolo not in RUOLI:
            raise ValueError(f"ruolo non valido: {ruolo}")
        if prezzo < 1:
            raise ValueError("il prezzo minimo e' 1 credito")
        if (prop := self.proprietario(Id)) is not None:
            raise ValueError(f"{Nome} e' gia' di {prop}")
        rie = self.riepilogo(lega).loc[squadra]
        if rie[f"liberi_{ruolo}"] <= 0:
            raise ValueError(f"{squadra} ha gia' tutti i {lega.rosa.slot[ruolo]} slot di ruolo {ruolo}")
        if prezzo > rie.offerta_massima:
            raise ValueError(f"{squadra} puo' offrire al massimo {rie.offerta_massima} "
                             f"(crediti {rie.crediti}, slot liberi {rie.slot_liberi})")
        m = Movimento(int(Id), Nome, ruolo, squadra, int(prezzo), tipo)
        self.movimenti.append(m)
        return m

    def cedi(self, Id: int, lega: LeagueRules = LEGA) -> Movimento:
        """Svincolo: il giocatore torna libero, si rimborsa la quota di lega."""
        r = self.rose()
        hit = r[r.Id == Id]
        if hit.empty:
            raise ValueError("giocatore non in rosa")
        h = hit.iloc[0]
        rimborso = int(round(h.prezzo * lega.rimborso_svincolo))
        m = Movimento(int(Id), h.Nome, h.ruolo, h.squadra, rimborso, "cessione")
        self.movimenti.append(m)
        return m

    def annulla_ultimo(self) -> Movimento | None:
        return self.movimenti.pop() if self.movimenti else None

    # ------------------------------------------------------------------ #
    # inflazione e prezzi in corsa
    # ------------------------------------------------------------------ #
    def inflazione(self, listino: pd.DataFrame) -> float:
        """Pagato / prezzo di listino, sui giocatori comprati all'asta."""
        r = self.rose().merge(listino[["Id", "prezzo"]].rename(columns={"prezzo": "listino"}),
                              on="Id", how="left")
        if r.empty or r.listino.sum() == 0:
            return 1.0
        return float(r.prezzo.sum() / r.listino.fillna(1).sum())

    def prezzi_correnti(self, listino: pd.DataFrame, lega: LeagueRules = LEGA) -> pd.DataFrame:
        """Listino dei giocatori ancora liberi, riprezzato con i crediti rimasti.

        Crediti spendibili sopra il pavimento = Σ crediti − Σ slot liberi. Si
        ripartiscono in proporzione al valore (prezzo − 1) dei migliori rimasti
        che riempiono gli slot liberi di ogni ruolo. Il risultato e' il prezzo
        "giusto" ora; l'offerta massima di ognuno dice chi puo' arrivarci.
        """
        rie = self.riepilogo(lega)
        presi = set(self.rose().Id)
        liberi = listino[~listino.Id.isin(presi)].copy()
        spendibili = float(rie.crediti.sum() - rie.slot_liberi.sum())
        quota = []
        for r in RUOLI:
            n = int(rie[f"liberi_{r}"].sum())
            quota.append(liberi[liberi.ruolo == r].nlargest(n, "prezzo"))
        valore = float(pd.concat(quota).prezzo.sub(1).clip(lower=0).sum()) if quota else 0.0
        fattore = spendibili / valore if valore > 0 else 1.0
        liberi["prezzo_ora"] = (1 + (liberi.prezzo - 1).clip(lower=0) * fattore).round().astype(int)
        liberi.attrs["fattore"] = fattore
        return liberi.sort_values("prezzo_ora", ascending=False)


# --------------------------------------------------------------------------- #
# persistenza
# --------------------------------------------------------------------------- #
def salva(stato: StatoLega, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dati = dict(squadre=stato.squadre, mia=stato.mia,
                crediti_iniziali=stato.crediti_iniziali,
                movimenti=[asdict(m) for m in stato.movimenti])
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def carica(path: pathlib.Path) -> StatoLega | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    return StatoLega(squadre=d["squadre"], mia=d["mia"],
                     crediti_iniziali=d.get("crediti_iniziali", LEGA.crediti_per_squadra),
                     movimenti=[Movimento(**m) for m in d.get("movimenti", [])])
