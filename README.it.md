[English](README.md) | **Italiano**

# Fantacalcio Analytics

Supporto decisionale per una lega privata di fantacalcio Serie A: Classic,
8 squadre, 500 crediti, rosa 3-8-8-6, asta alla 2ª-3ª giornata. L'obiettivo è
prezzare i giocatori **meglio del valore di mercato ufficiale (FVM)** con le regole
della propria lega: il vantaggio è di prezzatura relativa, non di previsione.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Test](https://img.shields.io/badge/test-pytest-0A9EDC?logo=pytest&logoColor=white)
![Licenza](https://img.shields.io/badge/licenza-PolyForm%20Strict%201.0.0-lightgrey)

Il metodo completo (obiettivi, calibrazione delle fonti xG, risultati validati,
architettura, lezioni imparate) è in [`docs/METODO.md`](docs/METODO.md); gli schemi
dei file e le trappole di parsing in [`docs/DATI.md`](docs/DATI.md).

<p align="center"><img src="docs/img/listino.png" width="85%" alt="Listino d'asta generato"></p>

## Stato

Raccolta dati **chiusa e validata**: 6 stagioni (2020-21 → 2025-26), 2280 partite
con xG Understat, aggregati stagionali per giocatore, voti per giornata, listone
2026-27, calendario 2026-27.

**`rules/` e `value/` scritti e validati**: motore di regolamento puro, punteggio
squadra con modificatori predisposti, parser voti, imbattibilità dei portieri
misurata, gerarchia rigoristi, e listino con proiezione a due stadi (fantamedia
e presenze separate) confrontato con l'FVM. Suite di test verde sulle 6 stagioni.
Prossimo passo: **`auction/`**, il modulo a ritorno più alto, prima dell'asta.

## Ambiente

```bash
python3.12 -m venv .venv        # 3.10+ obbligatorio
source .venv/bin/activate
pip install -U pip
pip install -e .                # installa il progetto e le dipendenze
pip install pytest              # per la suite di test
```

`pip install -e .` (editable) mette `rules`, `ingest` e `value` sul path: da quel
momento `python value/listino.py`, `python -m value.listino` e i test funzionano
da qualunque cartella. `openpyxl` (dipendenza) serve per leggere gli `.xlsx`.

## Struttura del codice

| percorso | cosa contiene |
|---|---|
| `rules/config.py` | regolamento dichiarativo (`LEGA`), unico posto delle costanti; orizzonte `giornate_residue`, `titolari_per_ruolo`, `modificatori` predisposti |
| `rules/fantavoto.py` | motore puro: dal voto + eventi al fantavoto, imbattibilità, soglie gol |
| `rules/giornata.py` | punteggio squadra + protocollo `Modificatore` (no-op con tupla vuota) |
| `ingest/voti.py` | parser dei file Voti per giornata (gestisce blocchi squadra, `ALL`, `6*`) |
| `ingest/componenti.py` | pannello componenti della fantamedia (voto, azione, rigori, malus, portiere), in cache |
| `value/dati.py` | pannelli Statistiche/listone + imbattibilità portieri misurata |
| `value/proiezione.py` | proiezione a due stadi: fantamedia **scomposta** e presenze, contrazione unica calibrata |
| `value/rigoristi.py` | rigoristi: gerarchia + proiezione dei rigori per **status** (volume, conversione, cambio club) |
| `value/rimpiazzo.py` | livelli di rimpiazzo sulla domanda di titolari |
| `value/budget.py` | quota crediti strategica per ruolo (§6.3), misurata |
| `value/listino.py` | listino: valore→prezzo (funzione sostituibile), coerenza col budget, confronto FVM |
| `value/report.py` | genera `output/listino.csv` e `output/listino.html` con il motivo per riga |
| `tests/` | test unitari del motore + accettazione sulle 6 stagioni + invarianti del listino |

```bash
python -m pytest -q                 # esegue tutta la suite
python -m value.report              # genera output/listino.csv e output/listino.html
python -m value.listino             # stampa occasioni, trappole, quote per ruolo
python -m value.rigoristi           # gerarchia e proiezione dei rigoristi
```

## Script esistenti

| file | cosa fa |
|---|---|
| `understat_setup.py` | preflight, scarico Understat, mappa squadre, join con FBref, calibrazione vs Opta |
| `fanta_statistiche.py` | carica i 6 file Statistiche, valida la formula, calcola rimpiazzi, budget e persistenza |

```bash
python understat_setup.py --step 0     # controllo ambiente
python understat_setup.py --step 1     # scarico Understat  (1b per i tiri)
python understat_setup.py --step 2     # mappa nomi squadra
python understat_setup.py --step 3     # unione e validazione -> data/panel/partite.csv
python understat_setup.py --step 4     # calibrazione Understat vs Opta

python fanta_statistiche.py "data/raw/Statistiche Fantacalcio/"
```

## Dati

I dati non sono nel repository: voti e statistiche di Fantacalcio.it, xG di Understat e FBref sono di proprietà
delle rispettive fonti. `understat_setup.py` scarica i dati di Understat; gli altri file vanno messi in `data/raw/`
con i nomi descritti in [`docs/DATI.md`](docs/DATI.md). I test di accettazione sulle 6 stagioni richiedono questi
dati; i test del motore di regolamento no.

## Licenza

Codice consultabile con la [PolyForm Strict License 1.0.0](LICENSE): si può leggere ed eseguire per scopi non
commerciali; non si può modificare, ridistribuire né usare commercialmente senza permesso scritto.

---

<sub>© 2026 [Mattia Meligeni](https://mattiameligeni.com). Progetto non affiliato a Fantacalcio.it, Understat o FBref.</sub>
