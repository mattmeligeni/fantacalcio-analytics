"""Regolamento di lega come oggetto dichiarativo unico.

Vincolo di progetto (docs/METODO.md §7): il regolamento vive SOLO qui. Nessun altro
modulo deve avere costanti di regolamento sparse nel codice; tutti importano
`LEGA` (o costruiscono un proprio `LeagueRules` per esperimenti).

Parametri ancora ignoti (mercato di riparazione, rimborso svincoli) sono tenuti
espliciti e con default dichiarato, come richiesto da docs/METODO.md §11: cambiarli
qui e rifare il listino deve bastare.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Solo per l'annotazione: il protocollo vive in rules/giornata.py (i
    # modificatori agiscono sulla formazione, non sul fantavoto). Import sotto
    # TYPE_CHECKING per non creare un ciclo config <-> giornata; con
    # `from __future__ import annotations` l'annotazione resta una stringa.
    from .giornata import Modificatore


# --------------------------------------------------------------------------- #
# Pesi bonus/malus — la tabella standard di QUESTA lega.
# Riferimento: docs/METODO.md §12 (glossario) e la formula validata §6.1.
# I nomi delle chiavi seguono le colonne dei file Statistiche stagionali
# (`R+`, `R-` = rigori segnati/sbagliati); il parser per giornata mappa
# `Rf -> R+` e `Rs -> R-` (vedi ingest/voti.py e docs/DATI.md §11.2).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BonusMalus:
    gol_fatto: float = 3.0            # Gf, RIGORI INCLUSI (non sommare i rigori)
    gol_subito: float = -1.0         # Gs (portiere)
    rigore_parato: float = 3.0       # Rp
    rigore_sbagliato: float = -3.0   # R- / Rs, netto a giornata (vedi nota)
    assist: float = 1.0              # Ass
    ammonizione: float = -0.5        # Amm
    espulsione: float = -1.0         # Esp
    autogol: float = -2.0            # Au
    imbattibilita: float = 1.0       # +1 al portiere con Gs==0 e voto reale

    # Nota sul rigore: nei file Statistiche il triangolo Rc/R+/R- pesa
    # Rc=-1, R+=+1, R-=-2, per un netto di +3 (segnato) e -3 (sbagliato).
    # ATTENZIONE alla convenzione dei GOL, diversa fra le due fonti (verificata
    # con identita' esatte sulle 6 stagioni):
    #   - Statistiche stagionali: `Gf` INCLUDE i rigori segnati.
    #   - Voti per giornata:      `Gf` = solo gol su azione; i gol su rigore
    #                             stanno in `Rf` (== R+). Totale gol = Gf + Rf.
    # Il motore per giornata conta quindi +3 su (Gf + Rf) e -3 su ogni rigore
    # SBAGLIATO (Rs == R-). Vedi rules/fantavoto.py e i test di aggregazione.


# --------------------------------------------------------------------------- #
# Soglie gol: i punti di giornata diventano reti a scaglioni (docs/METODO.md §2/§12).
# 66 la prima rete, poi una ogni 6.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SoglieGol:
    prima: float = 66.0
    passo: float = 6.0


# --------------------------------------------------------------------------- #
# Composizione rosa e domanda di titolari.
# SLOT = caselle possedute; TITOLARI = quanti se ne schierano in media, la base
# corretta per il calcolo del rimpiazzo (docs/METODO.md §10, errore gia' commesso).
# --------------------------------------------------------------------------- #
RUOLI = ("P", "D", "C", "A")


@dataclass(frozen=True)
class Rosa:
    slot: dict[str, int] = field(
        default_factory=lambda: {"P": 3, "D": 8, "C": 8, "A": 6})
    titolari: dict[str, float] = field(
        default_factory=lambda: {"P": 1.0, "D": 3.5, "C": 3.5, "A": 3.0})

    @property
    def slot_totali(self) -> int:
        return sum(self.slot.values())


# --------------------------------------------------------------------------- #
# Sostituzioni: ordine "hybrid" (docs/METODO.md §3). Prima si tenta il pari ruolo;
# solo se non esiste soluzione valida si valuta il cambio di modulo.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Sostituzioni:
    max_sostituzioni: int = 5
    ordine: str = "hybrid"  # "pari_ruolo" | "hybrid" | "libero"
    ammonito_senza_voto_sostituito: bool = True


# --------------------------------------------------------------------------- #
# Parametri economici e di calendario.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LeagueRules:
    squadre: int = 8
    crediti_per_squadra: int = 500
    prima_giornata_conteggiata: int = 3     # il conteggio parte dalla 3a
    giornate_totali: int = 38
    fonte_voti: str = "Fantacalcio"          # NON lo Statistico
    fonte_assist: str = "Fantacalcio"

    bonus: BonusMalus = field(default_factory=BonusMalus)
    soglie: SoglieGol = field(default_factory=SoglieGol)
    rosa: Rosa = field(default_factory=Rosa)
    sostituzioni: Sostituzioni = field(default_factory=Sostituzioni)

    # Modificatori di formazione (difesa, modulo, ...). Vuoto in questa lega.
    # Agiscono sul punteggio squadra in rules/giornata.py, applicati in
    # sequenza; con tupla vuota sono un no-op. NON sono additivi sul singolo
    # giocatore: se un giorno si attivano leggere la nota in docs/METODO.md §7.1,
    # perche' rompono l'impianto del valore sopra il rimpiazzo.
    modificatori: tuple["Modificatore", ...] = ()

    # --- Parametri PARAMETRICI, ancora da definire (docs/METODO.md §11) ---------- #
    crediti_riparazione: int = 0             # default esplicito, da rivedere
    rimborso_svincolo: float = 1.0           # frazione del costo, da rivedere

    # ---- aritmetica derivata --------------------------------------------- #
    @property
    def monte_crediti(self) -> int:
        return self.squadre * self.crediti_per_squadra

    @property
    def slot_totali_lega(self) -> int:
        return self.squadre * self.rosa.slot_totali

    @property
    def crediti_contendibili(self) -> int:
        """Crediti sopra il pavimento di 1 per slot."""
        return self.monte_crediti - self.slot_totali_lega

    @property
    def titolari_per_ruolo(self) -> dict[str, float]:
        """Domanda media di titolari per ruolo (moduli medi del Classic).

        E' la base corretta per il livello di rimpiazzo: si schiera 1 P, non 3.
        Da qui dipendono tutti i rimpiazzi (docs/METODO.md §10, errore gia' commesso).
        Nessuna funzione di value/ deve riscrivere questi numeri a mano.
        """
        return self.rosa.titolari

    def giornate_residue(self, giornata_corrente: int = 0) -> int:
        """Giornate che producono ancora punti a partire da `giornata_corrente`.

        `giornata_corrente = 0` = prima dell'inizio: tutte le giornate
        conteggiate. Con conteggio dalla 3a su 38 totali da' 36. Chi gioca una
        lega che parte dalla 1a mette prima_giornata_conteggiata=1 e ottiene 38.
        Rifacendo il listino alla riparazione (giornata_corrente=19) si ottiene
        l'orizzonte corretto senza toccare codice. Mai negativo.
        """
        inizio = max(self.prima_giornata_conteggiata, giornata_corrente + 1)
        return max(0, self.giornate_totali - inizio + 1)

    @property
    def giornate_conteggiate(self) -> int:
        """Giornate che producono punti in classifica (orizzonte pieno)."""
        return self.giornate_residue(0)

    def offerta_massima(self, crediti_residui: int, slot_da_riempire: int) -> int:
        """Offerta massima deterministica di un avversario (docs/METODO.md §7).

        Deve tenere 1 credito per ogni slot ANCORA da riempire oltre a quello
        che si sta comprando.
        """
        return crediti_residui - (slot_da_riempire - 1)


# Istanza canonica della lega. Il resto del codice importa questa.
LEGA = LeagueRules()
