# Metodo

Documento di progetto: obiettivi, scelte modellistiche, risultati validati e lezioni imparate. Gli schemi esatti
dei file e le trappole di parsing sono in [`DATI.md`](DATI.md).

**Stato: raccolta dati chiusa e validata. `rules/` e `value/` (listino v2)
scritti e validati.** Motore di regolamento puro, punteggio squadra con
modificatori predisposti, parser voti; fantamedia scomposta e proiettata a due
stadi con contrazione unica calibrata, rigori proiettati per status, imbattibilità
misurata, coerenza col budget §6.3. Artefatti in `output/listino.{csv,html}`.
Suite verde (52 test). Prossimo passo: **`auction/`**, il modulo a ritorno più
alto, da avere pronto prima dell'asta. Installazione: `pip install -e .`.

---

## 1. Obiettivo

Sistema di supporto decisionale per una **lega privata di fantacalcio Serie A**.
Obiettivo unico e misurabile: massimizzare la probabilità di vincere il
campionato di lega, con il grosso del valore concentrato nell'**asta**.

È la mia **prima partecipazione** a una lega di fantacalcio: background tecnico
solido (Python, ML, scraping), nessuna esperienza del gioco. Per questo il codice
è esplicito sulle regole di dominio e non dà per scontata alcuna conoscenza
fantacalcistica implicita. In fondo al documento c'è un glossario.

**Questo non è principalmente un progetto di machine learning.** Circa quattro
quinti del vantaggio ottenibile nascono da aritmetica deterministica e
ottimizzazione vincolata: motore di regolamento, contabilità dei budget
avversari, ripartizione dei crediti, selezione di rosa sotto vincolo. Il quinto
restante è modellistica, e anche lì la statistica classica pesa più
dell'apprendimento automatico. Chi riprende il lavoro partendo dal modello
predittivo sta ottimizzando il pezzo che rende meno.

### Aspettative realistiche

In una lega da 8 squadre, eseguire bene l'asta e prezzare correttamente il
proprio regolamento porta grossolanamente da 1 probabilità su 8 a **circa 1 su
3 o 1 su 4**. Miglioramento sostanziale, e resta più probabile perdere.

Nessun modello prevede chi segnerà domenica. Il vantaggio è di **prezzatura
relativa**, non di previsione.

Criterio di successo, economico e non statistico:

> Le mie quotazioni avrebbero ordinato i giocatori meglio dell'FVM ufficiale
> rispetto ai punti effettivamente prodotti?

Si misura con correlazione di rango su split temporale rigoroso, e con aste
simulate contro 7 avversari che offrono ai prezzi pubblici. Se il sistema non
batte l'FVM in quel confronto, non c'è vantaggio: c'è un progetto interessante.

### Confine etico

Modelli, fogli di calcolo e tracker di budget **non sono barare**: sono giocare
meglio allo stesso gioco con le stesse informazioni pubbliche. La linea la
superano solo la collusione occulta e gli account multipli.

---

## 2. Parametri della lega

| parametro | valore |
|---|---|
| modalità | Classic |
| squadre | **8** |
| crediti per squadra | 500 |
| rosa | 25: 3 P, 8 D, 8 C, 6 A |
| fonte voti | redazione Fantacalcio.it (NON il voto statistico) |
| bonus/malus | tabella standard |
| bonus portiere imbattuto | **attivo, +1** |
| modificatori | **nessuno** |
| soglie gol | 66 punti prima rete, poi una ogni 6 |
| sostituzioni | 5, ordine **hybrid**: prima si tenta il pari ruolo, solo se impossibile si valutano soluzioni con cambio modulo |
| ammonito senza voto | viene sostituito |
| fonte assist | Fantacalcio.it |
| prima giornata conteggiata | **3ª** |
| mercato di riparazione | previsto, **crediti ancora da definire: tenerli parametrici** |
| scambi | ammessi |
| momento dell'asta | **a stagione avviata, 2ª o 3ª giornata** |

Il regolamento va codificato in `rules/config.py` come oggetto dichiarativo, mai
sparso nel codice.

### Aritmetica derivata
- Monte crediti di lega: 8 × 500 = **4000**
- Slot: 8 × 25 = **200**, pavimento di 1 credito ciascuno
- **Crediti contendibili: 3800**, cioè ~475 a squadra sopra il pavimento

---

## 3. L'asta a stagione avviata: il fatto strategico centrale

L'asta cade dopo 1-2 giornate già giocate.

**Cosa dà:** la titolarità reale osservata. Le gerarchie dichiarate in estate
saranno già smentite in diverse squadre, e il mercato reale sarà chiuso o quasi.

**Cosa non dà:** informazione sul rendimento. Su 1-2 partite i bonus sono rumore
quasi puro.

Regola operativa, da implementare esplicitamente:

> **Usa le prime giornate per aggiornare la disponibilità, quasi per nulla per
> aggiornare il rendimento.**

La stanza farà l'opposto: sovrapagherà chi ha segnato una doppietta alla prima.
Quell'asimmetria è il principale arbitraggio disponibile.

Corollario: il conteggio della lega parte dalla **3ª giornata**, quindi si
proietta su **36 giornate**, non su 38. Le prime due non producono punti per
nessuno: servono solo come osservazione della titolarità.


### Nota sull'ordine hybrid e il terzo portiere

Le sostituzioni tentano **prima un pari ruolo**; solo se non esiste una soluzione
valida si passa a valutare cambi di modulo. Conseguenze operative da codificare
in `rules/giornata.py`:

- La panchina va composta per **copertura di ruolo**, non solo per qualità: un
  attaccante in più in panchina non salva un difensore senza voto se esiste
  ancora un difensore disponibile.
- Il **terzo portiere vale praticamente zero** e va preso a 1 credito: entra solo
  se i primi due sono entrambi senza voto nella stessa giornata, evento raro.
- L'ordine di panchina conta **dentro il ruolo**, non fra ruoli diversi. Il
  modulo di ottimizzazione della formazione deve quindi ordinare per ruolo.

---

## 4. Dati: stato attuale

Raccolta **chiusa**. Schemi completi e trappole in [`DATI.md`](DATI.md).

### `data/raw/` — originali, mai modificati

| file | contenuto |
|---|---|
| voti per giornata (consolidato) | giocatore × giornata × squadra, 6 stagioni |
| `Statistiche_..._<stagione>.xlsx` ×6 | aggregati stagionali per giocatore, **verità di riferimento** |
| `Fbref_SenzaxG.csv` | 2280 partite: gol, tiri, possesso, modulo, arbitro, spettatori |
| `Fbref_xG.csv` | vecchio file con xG Opta, incompleto. **Solo archivio storico** |
| `Listone_20_08_26.xlsx` | 526 giocatori, quotazioni base 500, FVM base 1000 |
| calendario 2026-27 | 38 giornate |

### `data/panel/` — generati da `understat_setup.py`

| file | ruolo |
|---|---|
| **`partite.csv`** | **il file chiave**: 2280 gare, xG Understat, validato al 100% |
| `understat_player_season.csv` | giocatore × stagione, 6 stagioni, con minuti e npxG |
| `understat_team_match.csv` | squadra × partita, statistiche più ricche |
| `understat_schedule.csv` | intermedio, rigenerabile |
| `understat_shots.csv` | tiri, ~65k righe (scaricato con `--step 1b`) |

### Perché si scartano 2018-19 e 2019-20
Regime a **tre sostituzioni** invece di cinque: cambia la distribuzione dei
minuti dei subentranti e quindi la frequenza dei senza voto, che è la variabile
obiettivo del modello di disponibilità. Restano sei stagioni omogenee.

Il 2020-21 si giocò quasi tutto a porte chiuse: la colonna `attendance` vuota
del file FBref fornisce gratis l'indicatore, da usare come controllo nel modello
del fattore campo.

---

## 5. La vicenda delle fonti xG, e cosa insegna

**Gennaio 2026: FBref perde i dati Opta.** Il fornitore ha revocato l'accesso e
imposto la cancellazione. Non torneranno. Il file ri-scaricato non ha più `xg`,
`xga`, `dist`, `pk`; restano `sh`, `sot`, `poss`, `formation`, `referee`,
`attendance`.

Non era un buco in una stagione, era la fine della sorgente: senza cambio di
fonte lo stesso problema si sarebbe ripresentato a settembre, con l'asta di
mezzo.

**Decisione: Understat come provider unico dell'xG**, su tutte e sei le stagioni
e in avanti, via la libreria `soccerdata`. FBref resta solo per il contesto
partita.

### La regola generale
> La **coerenza dentro una serie** conta; la comparabilità fra serie no.

Una giuntura di provider a metà dello storico verrebbe letta dal modello come un
cambiamento reale del calcio, quando è solo un cambio di misuratore.

### Calibrazione misurata, Understat contro Opta (1950 partite sovrapposte)

| | relazione | r | rmse |
|---|---|---|---|
| casa | understat = +0,002 + 1,090 · opta | 0,934 | 0,345 |
| trasferta | understat = +0,019 + 1,057 · opta | 0,941 | 0,294 |

Medie: casa 1,38 Opta contro 1,51 Understat; trasferta 1,20 contro 1,29.

**Lettura:** correlazione altissima per due modelli indipendenti su singola
partita, nessuna distorsione additiva, ma **Understat produce xG più alti del
7-9%**. Bias di scala stabile, non rumore.

Conseguenze per uso:
- **Coefficienti della letteratura: utilizzabili tali e quali.** Persistenza
  degli xG ~0,6 e della sovraperformance ~0,12 sono correlazioni, invarianti per
  trasformazione affine con intercetta nulla.
- **Confronti fra giocatori: nessun problema**, purché si usino misure centrate
  sulla media di ruolo anziché valori assoluti.
- **Portieri: problema reale.** Con 1,51 gol attesi una Poisson dà il 22% di
  imbattibilità; con 1,38 dà il 25%. Errore relativo del 13% su una quantità che
  in questa lega vale punti veri.

### La correzione, che è anche la regola generale
**Non usare mai l'xG grezzo come tasso di gol atteso: ancoralo ai gol realmente
segnati.** Riscalare per stagione in modo che il totale di lega degli xG eguagli
il totale dei gol segnati, oppure includere un parametro di scala nel modello di
squadra. Così la domanda su quale provider abbia ragione diventa irrilevante,
perché ci si calibra sull'osservabile invece che sulle unità di misura altrui.

Immunizza anche dal prossimo cambio di fonte.

### Sull'RMSE
0,345 su una media di 1,4 non è piccolo, e circa un terzo è il bias sistematico;
il resto è disaccordo genuino partita per partita. **Una singola gara in cui i
due provider differiscono di 0,3 di xG non significa nulla.** Non guardare mai
l'xG di una singola giornata.

---

## 6. Risultati già ottenuti e validati

Tutti i numeri sotto sono calcolati **sui file reali del progetto**.

### 6.1 Motore di regolamento: formula validata

```
Fm = Mv + (3·Gf − Gs + 3·Rp + Ass − 0,5·Amm − Esp − 2·Au − 3·R−) / Pv
```

Verificata sulle 6 stagioni, 3319 righe con presenze: **errore medio 0,0062**,
puro arrotondamento a due decimali.

**`Gf` include già i gol su rigore.** Non sommare un secondo bonus per i rigori
segnati: si sovrastimerebbero proprio i rigoristi. `Rc` (calciati) vale −1, `R+`
(segnati) +1, `R−` (sbagliati) −2: in netto un rigore segnato fa +3, uno
sbagliato −3. `Rc = R+ + R−` verificato esattamente.

**Anomalia residua diagnosticata:** 213 righe su 3319 (6,4%), scarto **sempre
positivo** e sempre multiplo di 0,5 punti stagionali. Causa: `Amm` conta anche i
cartellini presi in partite chiuse con `6*`, che la redazione non applica alla
fantamedia perché in quella giornata il voto non esiste. **`Amm` del file
stagionale ≠ `Amm` che entra nella fantamedia.** Nel motore per giornata il
problema non si pone; non calibrare mai nulla sugli aggregati senza questa
correzione.

### 6.2 Livelli di rimpiazzo (mediana su 6 stagioni, 8 squadre)

Il "rimpiazzo" è il miglior giocatore che resta libero dopo l'asta, ottenibile a
1 credito. Il valore reale di un acquisto è quanto rende **in più**.

| ruolo | rimpiazzo (punti stagionali) | escursione |
|---|---|---|
| P | **173** | 161 – 177 |
| D | **194** | 188 – 200 |
| C | **210** | 207 – 216 |
| A | **205** | 192 – 219 |

Escursione di 10-15 punti su valori intorno a 200: **costanti strutturali**, non
serve ristimarle ogni anno.

### 6.3 Ripartizione del budget

| ruolo | quota contendibili | crediti a squadra | % budget |
|---|---|---|---|
| P | 5,0% | **27** | 5% |
| D | 24,8% | **126** | 25% |
| C | 28,4% | **143** | 29% |
| A | 41,9% | **205** | 41% |

Correzione **misurata** (non più stimata): le Statistiche non conteggiano
l'imbattibilità, attiva in questa lega. Ricostruita dai voti per giornata
(portiere con `Gs = 0` e voto reale = imbattuto), su 6 stagioni e portieri con
`Pv ≥ 20`: **clean sheet mediana 8, media 8,9, massimo 21**, 0,28 per presenza;
quartili 6 / 8 / 12. Aggiungendo +1 punto a clean sheet:

| ruolo | quota (misurata con imbattibilità) | crediti a squadra | % budget |
|---|---|---|---|
| P | 5,4% | 29 | 6% |
| D | 24,5% | 125 | 25% |
| C | 28,4% | 143 | 29% |
| A | 41,6% | 204 | 41% |

La quota portieri sale da 5,0% a **5,4%** (6% arrotondato), esattamente dove la
stima Poisson la collocava. Il motivo per cui si muove così poco: **anche il
portiere di rimpiazzo prende clean sheet**, quindi il rimpiazzo P sale da 173 a
**183** e gran parte del bonus si annulla nel calcolo del valore sopra il
rimpiazzo. **Non cambia la strategia, la conferma.** Implementato in
`value/dati.py` (`clean_sheet_portieri`, `con_imbattibilita`): il listino usa i
punti con imbattibilità per i portieri.

### 6.4 Persistenza anno su anno, **dentro il ruolo**

1311 coppie giocatore-stagione con ≥10 presenze in entrambe le annate.

| ruolo | n | presenze | media voto | tasso bonus | fantamedia | punti totali | pendenza |
|---|---|---|---|---|---|---|---|
| P | 79 | 0,194 | 0,289 | 0,534 | 0,450 | 0,192 | 0,442 |
| D | 499 | 0,332 | 0,436 | 0,413 | 0,485 | 0,360 | 0,495 |
| C | 485 | 0,355 | 0,388 | 0,507 | 0,476 | 0,409 | 0,453 |
| A | 248 | 0,242 | 0,484 | 0,525 | 0,517 | 0,298 | 0,544 |

**Avvertenza metodologica.** Sulle stesse coppie, le correlazioni aggregate su
tutti i ruoli davano 0,724 sulla fantamedia e 0,823 sul tasso di bonus: valori
gonfiati dalla composizione, perché i portieri vivono su un altro livello di
media voto e di malus e la loro sola presenza crea correlazione apparente
(paradosso di Simpson). **Nel codice usare sempre le correlazioni per ruolo.**

**Il risultato più importante dell'analisi:** i **punti totali** di stagione,
cioè esattamente il numero su cui la stanza prezzerà i giocatori, sono la
grandezza **meno persistente** di tutte (0,19–0,41). La fantamedia persiste il
doppio. La componente che distrugge la prevedibilità è la disponibilità
(presenze: 0,19–0,36).

Da qui discendono l'architettura a due stadi, la centralità dell'asta a stagione
avviata, e il fatto che il mercato prezzi male perché si ancora al numero meno
persistente disponibile.

### 6.5 Regola di contrazione

Pendenze 0,44 P / 0,50 D / 0,45 C / 0,54 A. Regola applicabile anche a mente:

> Fantamedia dell'anno scorso, misura di quanto sta sopra la media del ruolo,
> **dimezza quella distanza**.

Chi ha chiuso a 7,0 in un ruolo con media 5,4 vale circa 6,2.

Implementazione: contrazione empirico bayesiana con peso proporzionale alle
presenze, verso la media di ruolo; modello gerarchico completo per neopromossi e
giovani. Ponderare le stagioni con decadimento esponenziale, dimezzamento
intorno alle due stagioni.

### 6.6 Altri risultati

- **Gol per presenza (persistenza):** A 0,509 · C 0,447 · D 0,323. Assist per
  presenza 0,39–0,42 in tutti i ruoli. I gol dei difensori sono largamente
  rumore.
- **Portieri, gol subiti per presenza: r = 0,561**, la correlazione più alta del
  pannello. Non è merito del portiere, è forza difensiva della squadra. Media
  1,28 gol subiti a partita, dev. 0,34. **Il portiere si sceglie guardando la
  difesa davanti a lui e si compra a poco.**
- **Spezzoni** (presenze totali meno presenze con voto), mediana/massimo:
  A 2/14 · C 2/14 · D 1/10 · P 0/1. La coda è il rischio di rotazione che il
  mercato non prezza.
- **Minuti mediani per presenza:** A 41 · C 54 · D 68 · P 90.
- **Il 17-18% dei giocatori a listino non prende mai voto** in una stagione, con
  stabilità notevole su sei stagioni (16,7% – 18,6%).
- **Sovraperformance rispetto agli xG:** in letteratura la persistenza anno su
  anno si ferma intorno a 0,12, mentre la capacità di generare occasioni
  persiste intorno a 0,6. Chi ha segnato molto più del suo xG sarà sovrapprezzato
  e regredirà; chi ha creato molto senza convertire è sottoprezzato e non
  regredirà nella stessa misura. Corollario metodologico: una variabile che si è
  costretti a contrarre quasi a zero non merita misurazione più precisa, motivo
  per cui l'xG per giocatore-partita non era sulla strada critica.

### 6.7 Struttura del pool e strategia

Listone 2026-27: 526 giocatori (68 P, 186 D, 181 C, 91 A), 18 fuori lista da
escludere.

Con 8 squadre vengono posseduti 24 P, 64 D, 64 C, 48 A: il **35% dei portieri,
34% dei difensori, 35% dei centrocampisti e 53% degli attaccanti**. Restano
liberi oltre 300 giocatori.

**Concentrare, non diversificare.** Con un serbatoio così profondo e un mercato
di riparazione, un errore d'asta costa poco: si rimpiazza a gennaio. Il rischio
al ribasso è tamponato, quindi conviene accettare volatilità e concentrare i
crediti sui pochi giocatori con il divario più ampio rispetto al rimpiazzo.

**Difensori: riempire al minimo.** Senza modificatore difesa valgono solo per
voto e bonus, e il 65° difensore è ancora un titolare di metà classifica. Unica
eccezione: chi batte i piazzati o calcia rigori, che non sono difensori ma
centrocampisti mascherati.

**Maledizione del vincitore attenuata.** Il massimo di 8 stime è meno estremo del
massimo di 12: lo sconto sulle offerte può essere più leggero che in una lega
affollata. Resta valida la regola di scontare di più i profili su cui l'incertezza
è maggiore (neopromosse, giovani, reduci da stagioni anomale).

### 6.8 Scomposizione della fantamedia e proiezione (listino v2)

La fantamedia aggrega componenti con persistenze molto diverse, quindi un
fattore di contrazione unico è giusto in media e sbagliato ovunque. Scomposta
(dai voti per giornata, dove `Amm` è corretto e `Gf` è già al netto dei rigori;
ricomposizione **esatta**), misurata dentro il ruolo su coppie consecutive:

| componente | P | D | C | A |
|---|---|---|---|---|
| voto base | 0,28 | 0,45 | 0,39 | 0,52 |
| gioco su azione (gol non rigore + assist) | — | 0,38 | 0,43 | 0,49 |
| malus (cartellini, autogol) | 0,11 | 0,19 | 0,37 | 0,27 |
| portiere (gol subiti, parati, imbattibilità) | 0,54 | — | — | — |

Letture che cambiano le decisioni: il **portiere persiste 0,54**, più
dell'aggregato 0,44, quindi il valore del portiere va regredito **meno**; il
**malus persiste** (0,19–0,37), non è rumore; il gioco su azione persiste come
il voto. La componente **rigori non si proietta per persistenza** (rumore per
presenza) ma per status, vedi sotto. Implementato in `value/proiezione.py`, che
proietta ogni componente e ricompone.

**Errore evitato — doppia contrazione.** Applicare lo shrink empirico-bayesiano
*e* poi la pendenza di persistenza contrae due volte la stessa affidabilità e
schiaccia i giocatori con storico lungo (Calhanoglu proiettato troppo basso). La
pendenza a una stagione **è** l'affidabilità di una stagione (`slope = n/(n+K)`):
si ricava K da lì e si contrae **una volta sola**, con l'affidabilità che cresce
con le presenze pesate. Chi ha sei stagioni stabili regredisce poco, chi ne ha
una tanto. Principio generale: mai contrarre due volte la stessa cosa.

**Rigoristi: prevedere lo status, non la precisione** (`value/rigoristi.py`).
Misurato: la conversione individuale **non persiste** (pendenza 0,12), quindi va
contratta forte verso la media di lega (0,789); il **volume** persiste
(`Rc_succ = 0,28 + 0,45·Rc`); **cambiare club azzera lo status** (un rigorista
che resta fa 2,59 rigori l'anno dopo, uno che cambia 0,76 → fattore 0,29). Il
punto: essere il rigorista vale ~9 punti stagione, convertire meglio ~1,5. Il
modello proietta *chi li calcia* e li somma alla fantamedia scomposta.

**Coerenza listino ↔ budget (§6.3).** La quota crediti per ruolo la fissa la
strategia §6.3 (misurata sui punti realizzati), non la proiezione, che
compressa drifta verso i difensori. Il listino alloca **fra** i ruoli con la
quota §6.3 e **dentro** il ruolo con il valore sopra il rimpiazzo proiettato:
la ripartizione contendibili del listino coincide con §6.3 a 0,1 punti %.

**Disaccordo residuo col mercato, onesto.** Dopo la scomposizione Calhanoglu
resta sotto il suo prezzo di mercato: proietta ~19° centrocampista per punti
(output d'azione da metà classifica), mentre il mercato lo paga da top-5. Non è
un difetto del metodo: è un disaccordo genuino, che il backtest (fase 5)
arbitrerà. Specularmente il modello ama Barella (FVM basso, proiezione alta).

### 6.9 Imbattibilità: controllo esterno

La somma dei clean sheet dei portieri (dai voti) è entro il **2,5–4,6%** sopra i
clean sheet reali di squadra in `partite.csv` (partite con gol subiti = 0), su
tutte le stagioni. Lo scarto è positivo e piccolo, spiegato: una gara con il
portiere titolare sostituito dà due imbattibilità ma una sola per la squadra. Il
massimo, 21 clean sheet (Provedel, Lazio 2022-23), è la miglior difesa reale di
quella stagione, non un artefatto.

---

## 7. Architettura

```
fanta/
├── data/raw/          originali, MAI modificati, con data di scarico
├── data/panel/        csv consolidati
├── ingest/            parser + anagrafica di riconciliazione (congelata)
├── rules/             regolamento + fantavoto + giornata          [PURO]
├── models/            disponibilità, voto base, eventi, squadre, shrinkage
├── simulate/          Monte Carlo su giornate residue, con correlazioni
├── value/             rimpiazzo, listino, rosa ottimale
├── auction/           stato d'asta, inflazione, interfaccia Streamlit
├── inseason/          formazione, capitano, panchina, svincoli
└── backtest/          split temporale, aste simulate contro FVM
```

**Stack:** Python 3.12 in venv. pandas (tutto in memoria: ~100k righe
giocatore-partita, ~4k giocatore-stagione, nessun database), statsmodels,
LightGBM, scikit-learn, PuLP o OR-Tools, Streamlit, `soccerdata` per lo scraping.
CSV su disco per i pannelli: niente parquet, evita dipendenze compilate e resta
ispezionabile a occhio.

**Vincolo non negoziabile:** `rules/` non deve dipendere da `models/`. Il motore
di regolamento è puro, deterministico e testabile in isolamento. È l'unico modulo
in cui un errore resta silenzioso e contamina tutto il resto.

### 7.1 Modificatori: predisposti ora, e perché rompono il valore additivo

Questa lega **non** ha modificatori. L'interfaccia però è già in codice
(`rules/giornata.py`: protocollo `Modificatore` con firma
`applica(formazione, punti_base) -> float`; `LEGA.modificatori: tuple = ()`;
applicazione in sequenza nel punteggio squadra, no-op con tupla vuota, coperto
da test). Il retrofit successivo sarebbe costoso per una ragione non ovvia, che
va capita **prima** di attivarli.

I modificatori non agiscono sul fantavoto del singolo, agiscono sul punteggio
della **formazione**: il modificatore difesa legge la media di portiere + i
**quattro migliori** difensori; quello modulo confronta l'assetto con il 4-4-2.
Stanno quindi in `giornata.py`, non in `fantavoto.py`.

Conseguenza: **con i modificatori attivi il valore di un giocatore smette di
essere additivo.** Il valore di un difensore dipende da *quali altri difensori
possiedi*, perché il modificatore legge i migliori quattro: il quinto difensore
buono aggiunge poco, lo stesso giocatore che colma un buco vale moltissimo.
Questo **rompe l'impianto del valore sopra il rimpiazzo**, che assume
separabilità. Se un giorno si attivano, il listino deve passare da **somma di
valori individuali** a **contributo marginale simulato** — calcolato per
differenza, con e senza il giocatore, su una rosa di riferimento — e va
**ricalcolato durante l'asta a ogni acquisto**. Ordine di grandezza: col
modificatore difesa la quota crediti dei difensori passerebbe grosso modo dal
**25% a oltre il 35%**, a scapito degli attaccanti.

Vincolo che ne discende, già rispettato: **`value/listino.py` espone il calcolo
del valore dietro una funzione sostituibile**, non inline. Oggi additivo, domani
marginale-simulato cambiando quella sola funzione. Non anticipare la seconda
implementazione, ma non renderla impossibile.

### Scelte modellistiche

- **Boosting (LightGBM) solo per la disponibilità.** Campione ~100k righe
  giocatore-partita, obiettivo binario "prende voto sì/no", interazioni non
  lineari (minuti recenti, giorni dall'ultima gara, impegni di coppa, concorrenti
  nel ruolo). Da **calibrare** con regressione isotonica: serve una probabilità
  affidabile per la simulazione. Metriche log loss e Brier, **mai** accuratezza.
- **Niente boosting sul rendimento.** ~3k righe giocatore-stagione, correlazioni
  0,4–0,5: segnale debole e campione piccolo sono le condizioni in cui gli alberi
  sovradattano. Voto base con effetti misti e contrazione; eventi bonus con
  Poisson o binomiale negativa con offset sui minuti, perché sono conteggi.
- **Niente random forest.** Dove gli alberi aiutano il boosting le batte, dove non
  aiutano le batte un lineare regolarizzato.
- **Niente reti neurali.** Né scala né struttura le giustificano.
- **Modello di squadra stile Dixon-Coles su xG** (non sui gol, troppo rumorosi),
  con il riscalamento del §5. Alimenta gol subiti e imbattibilità dei portieri.
- **LLM solo periferici**: trasformare notizie su infortuni e conferenze stampa
  in indicatori strutturati. Accessorio.

### Simulazione
Monte Carlo su giornate residue, ~10.000 iterazioni: disponibilità → minuti →
eventi → motore di regolamento. La sottigliezza sono le **correlazioni**: due
difensori della stessa squadra prendono l'imbattibilità insieme, i gol di
compagni di reparto competono. Si induce con una variabile latente a livello di
partita-squadra o una copula gaussiana sui residui. L'output è una
**distribuzione**, non un numero.

### Dal valore al prezzo
Rimpiazzo per ruolo sulla domanda di titolari → valore sopra il rimpiazzo,
troncato a zero → ripartizione dei 3800 contendibili in proporzione, più 1
credito di pavimento → rosa ottimale come zaino a vincoli multipli.

Limite noto: massimizzare i punti attesi non è massimizzare la probabilità di
vincere, perché il premio è concentrato sul primo posto. Raffinamento: ricottura
simulata sulla probabilità di vittoria contro rose avversarie simulate.

Disponibilità a pagare durante l'asta: **per differenza**. Si risolve
l'ottimizzazione con quel giocatore a prezzo *p* e senza; la variazione
dell'obiettivo è il massimo reale.

### Perché `auction/` rende più di tutto il resto
Non contiene una riga di ML. In ogni istante l'offerta massima di ogni avversario
è deterministica:

```
offerta_massima = crediti_residui − (slot_ancora_da_riempire − 1)
```

Un avversario con 40 crediti e 15 posti vuoti può offrire al massimo 26. Chi
tiene aggiornato quel numero per tutti e sette sa quando può alzare in sicurezza
e quando sta rilanciando contro un muro. Nessun altro fa questi conti in tempo
reale.

Il modulo traccia anche il **fattore di inflazione** (pagato / atteso): se la
stanza paga i primi nomi il 20% sopra le stime, tutti i rimanenti costeranno meno
e i valori vanno riscalati in corsa.

Requisiti pratici: inserimento rapidissimo delle assegnazioni, tabella sempre
visibile dei 7 avversari con crediti, slot per ruolo e offerta massima, lista dei
migliori disponibili riprezzati, indicatore di inflazione, **funzionamento
offline**, **salvataggio dello stato a ogni operazione**.

### Gestione settimanale
Margine piccolo: quasi sempre si schierano i propri undici migliori. La regola
utile viene dalla teoria dei tornei: **contro un avversario più forte aumentare
la varianza** della formazione, contro uno più debole ridurla. Vale anche
rispetto alla classifica generale quando si è indietro a poche giornate dalla
fine.

---

## 8. Ordine di costruzione

Pensato per essere **interrompibile**.

1. ~~**`rules/`** con suite di test che rigioca giornate storiche note~~ **FATTO**
   (`rules/config.py` regolamento dichiarativo + modificatori predisposti §7.1,
   `rules/fantavoto.py` motore puro, `rules/giornata.py` punteggio squadra,
   `ingest/voti.py` parser, `tests/` sulle 6 stagioni)
2. **`ingest/`** + pannello unificato + anagrafica congelata *(parser voti fatto;
   resta il pannello unificato e l'anagrafica xG. `Cod.` verificata come chiave
   di join sicura, §6.7)*
3. ~~**`value/rimpiazzo.py`** e **`value/listino.py`** (listino v2)~~ **FATTO**
   (`value/dati.py` pannelli + imbattibilità misurata, `ingest/componenti.py`
   pannello componenti in cache, `value/proiezione.py` due stadi con fantamedia
   **scomposta** e contrazione **unica** calibrata, `value/rimpiazzo.py` su
   domanda titolari, `value/rigoristi.py` proiezione dei rigori per **status**,
   `value/budget.py` quota §6.3, `value/listino.py` valore sostituibile e coerenza
   di ruolo, `value/report.py` → `output/listino.csv` e `output/listino.html`).
   Vedi §6.8-6.9. Disaccordi col mercato lasciati espliciti per il backtest.
4. **`auction/`** — massimo ritorno sull'investimento (**prossimo passo**)
5. **`models/`** e **`simulate/`**
6. **`backtest/`** per ultimo

Se il tempo finisce: tagliare `models/` e `simulate/`, tenere rimpiazzi, listino
e assistente d'asta. Si perde forse un quarto del vantaggio.

### Test di accettazione

| test | criterio |
|---|---|
| motore di regolamento | rigioca giornate storiche, punteggio esatto al centesimo |
| identità gol di squadra | `gf = Σ Gf + Σ Au avversari` su tutte le giornate |
| identità portieri | `Σ Gs portiere = ga squadra` |
| identità rigori | `Σ Rf = pk`, `Σ Rs = pkatt − pk` (solo dove `pk` esiste) |
| aggregazione voti | coincide con le Statistiche su `Pv`, `Gf`, `Gs`, `Rp`, `Ass`, `Esp`, `Au`, `Mv`, `Fm` |
| anagrafica | ≥97% aggancio univoco sui giocatori con `Pv ≥ 20` |
| calibrazione disponibilità | Brier e log loss su split temporale |
| valore economico | correlazione di rango contro FVM sui punti realizzati |

---

## 9. Cose ancora da fare sui dati

Piccole, tutte rinviabili.

1. **Controllo di scala dell'xG**, due righe: sommare `home_xg`, `away_xg`, `gf`,
   `ga` su `partite.csv` e ricavare il fattore di riscalamento verso i gol reali.
   È la correzione più importante per i portieri e quindi per l'imbattibilità.
2. **Ricalcolare l'imbattibilità** dai voti per giornata e correggere la quota
   crediti dei portieri (§6.3).
3. ~~Verificare `understat_player_season.csv`~~ — **fatto: contiene `npg` e
   `npxG`.** L'approssimazione con il fattore 0,76 esce dal progetto: usare
   direttamente le colonne al netto dei rigori.

---

## 10. Lezioni imparate

**Rimpiazzo sugli slot di rosa invece che sui titolari.** Il primo tentativo
definiva il rimpiazzo come l'ultimo slot occupato in lega (24° portiere con 8×3).
Risultato: 24% dei crediti ai portieri e il miglior portiere prezzato 66 crediti.
Causa: si possiedono 3 portieri ma se ne schiera **uno**, e il 24° portiere per
punti totali è già un secondo di club che gioca 11 partite. **Il rimpiazzo si
calcola sulla domanda di titolari** (~1 P, 3,5 D, 3,5 C, 3 A per squadra).

**Media invece di mediana tra le stagioni.** Nel 2025-26 la quota portieri
risultava 8,8%, nelle altre cinque tra 4,1% e 5,8%.

**Correlazioni aggregate invece che per ruolo.** Vedi §6.4.

**Normalizzazione Unicode ingenua.** La `ø` non si decompone con NFKD: vedi
[`DATI.md`](DATI.md).

**Join che falliscono in silenzio.** Un merge riuscito al 72% senza sollevare
errori è il modo canonico in cui muoiono i progetti di dati. Ogni join deve
avere un criterio di validazione indipendente e fallire rumorosamente. Vedi il
caso dei nomi squadra in [`DATI.md`](DATI.md).

**Formati che si assomigliano e significano cose diverse.** La stringa `'2021'`
è la stagione 2020-21 per soccerdata e la stagione 2021-22 per FBref. Mai una
funzione di conversione unica per fonti diverse.

---

## 11. Domande aperte

1. **Crediti del mercato di riparazione** e rimborso sugli svincoli. Non ancora
   noti: tenuti **parametrici** in `LeagueRules` (`crediti_riparazione`,
   `rimborso_svincolo`) con default esplicito; cambiarli lì e rifare il listino
   basta. Incidono sulla propensione al rischio in asta: più crediti di
   riparazione significano errori più economici e quindi più concentrazione.
2. ~~**`Rf`/`Rs` nel file voti per giornata**~~ — **risolto** con identità esatte
   sulle 6 stagioni. `Rf` = gol su **rigore** ed è esattamente `R+`; `Rs` =
   rigori sbagliati ed è esattamente `R−`. **Trappola importante:** nel file voti
   per giornata la colonna `Gf` conta i **soli gol su azione** (rigori esclusi),
   mentre nel file Statistiche stagionale `Gf` **include** i rigori. Il totale
   gol per giornata è quindi `Gf + Rf`. Chi somma solo `Gf` sottostima ogni
   rigorista del ~9-13% (verificato: gol totali di lega tornano solo con `Gf+Rf`).
   Codificato in `rules/fantavoto.py` e coperto da `tests/test_aggregazione.py`.
3. ~~**Colonna `Under`** del listone~~ — **risolto: è l'età** (numeri 18-40), non
   un flag. Usata come `eta` in `value/dati.carica_listone`.

---

## 12. Glossario

**Voto** — voto in pagella, da 4 a 8 circa.
**Fantavoto** — voto più bonus meno malus.
**Bonus/malus standard di questa lega** — gol +3 · assist +1 · rigore parato +3 ·
rigore sbagliato −3 · ammonizione −0,5 · espulsione −1 · autogol −2 · gol subito
dal portiere −1 · **imbattibilità +1**.
**Senza voto (`6*`)** — è sceso in campo ma non ha giocato abbastanza per una
valutazione. Ai fini del gioco **conta come assenza**: viene sostituito.
**Pv** — presenze con voto. Diverso da `apps`, che conta anche gli spezzoni.
**Mv / Fm** — media voto e fantamedia sulle presenze con voto.
**Punti totali** — fantamedia × presenze. È ciò che finisce in classifica, ed è
la grandezza meno prevedibile.
**Soglie gol** — i punti di giornata diventano reti a scaglioni: 66 la prima, poi
una ogni 6.
**Listone** — elenco ufficiale degli acquistabili con ruolo e quotazione.
**FVM** — valore teorico d'asta su base 1000, da dividere per due. Calibrato su
un fantacalcio generico: la differenza con le regole locali è il margine.
**Rimpiazzo** — il miglior giocatore libero dopo l'asta, ottenibile a 1 credito.
Il livello che si ottiene gratis.
**Valore sopra il rimpiazzo** — quanto un giocatore rende in più del suo
rimpiazzo. L'unica cosa che si sta davvero comprando.
**Contrazione** — dimezzare la distanza dalla media di ruolo, perché parte del
rendimento è fortuna e la fortuna non si ripete.
**Persistenza** — quanto una grandezza si ripete da un anno all'altro.
**xG / xA** — gol e assist attesi in base alla qualità delle occasioni.
**npxG** — xG al netto dei rigori.
**Maledizione del vincitore** — in un'asta a valore comune vince tipicamente chi
ha sovrastimato di più. Rimedio: offrire meno della propria valutazione, tanto
più quanto si è incerti.
**Prezzo ombra dei crediti** — quanto vale il credito marginale date le caselle
da riempire. Cambia continuamente durante l'asta.
**Fattore di inflazione** — quanto la stanza sta pagando sopra o sotto le stime.
**Modello a due stadi** — *giocherà e prenderà voto?* (classificazione) e *se
gioca, quanto rende?* (regressione).
**Calibrazione** — un modello è calibrato se tra i casi a cui assegna 0,7 circa
il 70% si verifica. Una probabilità mal calibrata avvelena la simulazione.
**Zaino a vincoli multipli** — scegliere la rosa migliore rispettando budget e
slot per ruolo. Programmazione lineare intera.
**Paradosso di Simpson** — una correlazione su gruppi mescolati può differire
molto da quella dentro ciascun gruppo.
