# Metodo

Documento di progetto: obiettivi, scelte modellistiche, risultati validati e lezioni imparate. Gli schemi esatti
dei file e le trappole di parsing sono in [`DATI.md`](DATI.md).

**Stato (ottobre 2026): v3. Raccolta dati chiusa e validata; `rules/`, `models/`,
`simulate/`, `value/` e `backtest/` scritti e validati su split temporale.**
Pannello unificato con i tesserati a zero presenze, istantanea d'asta che non
vede il futuro, disponibilità con le prime giornate osservate, rendimento con
una sola contrazione calibrata fuori campione, portieri dalla difesa della
squadra (xG ancorato ai gol), rigoristi per quota di status, valore per presenza
sopra il panchinaro tipo, prezzi a tasso unico con monte esatto. Il backtest
2022-23 → 2025-26 batte la v2 e la baseline su punti e su valore realizzato
(§6.12). Artefatti in `output/listino.{csv,html}` e `output/backtest/`. Suite
verde (71 test). Prossimo passo: **`auction/`**. Installazione: `pip install -e .`.
**Il listino va rigenerato il giorno dell'asta** con i voti delle giornate già
giocate in `data/raw/Voti/26-27/`: è il guadagno più grande misurato (§6.10).

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

> **Revisione v3 — la quota per ruolo non è una costante strutturale.** Misurata
> come *valore marginale realizzato* per una squadra con panchina (§6.11, rose
> rigiocate con i fantavoti veri), la quota dei centrocampisti vale 46%, 3%, 51%,
> 27% nelle quattro stagioni 2022-23 → 2025-26, e cambia di decine di punti a
> seconda di come la stanza compone le rose. Le mediane qui sopra davano una
> falsa precisione e la v2 le **imponeva** al listino: un punto di portiere
> costava il 78% più di uno di difensore. Dalla v3 la quota è un **risultato**
> (tasso crediti/valore unico per tutti i ruoli): sul listino 2026-27 esce
> P 10,0% · D 26,1% · C 29,9% · A 33,9%, vicina alla media realizzata nel
> backtest con le rose del mercato (8,5 · 25,9 · 31,3 · 34,3).

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

> **Revisione v3 — la persistenza delle presenze qui sopra è sottostimata.**
> Le coppie sono filtrate a ≥10 presenze in *entrambe* le stagioni: si escludono
> proprio i casi in cui la disponibilità cambia (troncamento), e la pendenza
> crolla. Su tutte le coppie di tesserati, zeri inclusi, la pendenza delle
> presenze è **P 0,75 · D 0,50 · C 0,54 · A 0,48** (contro 0,22-0,37 usate dalla
> v2). La conclusione strategica resta (i punti totali sono rumorosi, il mercato
> si ancora a loro), ma la v2 contraeva le presenze di tutti verso "titolare":
> portieri proiettati a 25 presenze contro 10 reali, dispersione schiacciata da
> 12 a 3,5. Vedi §6.10.

### 6.5 Regola di contrazione

Pendenze 0,44 P / 0,50 D / 0,45 C / 0,54 A. Regola applicabile anche a mente:

> Fantamedia dell'anno scorso, misura di quanto sta sopra la media del ruolo,
> **dimezza quella distanza**.

Chi ha chiuso a 7,0 in un ruolo con media 5,4 vale circa 6,2.

Implementazione: contrazione empirico bayesiana con peso proporzionale alle
presenze, verso la media di ruolo; modello gerarchico completo per neopromossi e
giovani. Ponderare le stagioni con decadimento esponenziale, dimezzamento
intorno alle due stagioni.

> **Revisione v3.** La costante K della contrazione si sceglie per minimo
> errore di previsione sulle aste storiche di addestramento (per ruolo e
> famiglia), non da una pendenza troncata; i valori risultano vicini ai vecchi
> (20-80 presenze pesate). La media di ruolo verso cui si contrae è quella di
> **tutti** i giocatori pesata per presenze, non dei soli titolari (≥15
> presenze): il prior dei titolari gonfiava le riserve. Per i bonus degli
> attaccanti conviene una media che cresce con la disponibilità proiettata
> (chi gioca di più segna di più a partita); per il voto di D e C no (+6-10%
> di errore). Implementato in `models/rendimento.py`.

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

**Coerenza listino ↔ budget (§6.3).** *Superata nella v3, era un errore:*
imporre la quota §6.3 a una proiezione compressa dava a ogni ruolo un tasso
crediti/punto diverso (P 6,3 · D 3,6 · C 4,3 · A 4,5). Vedi la revisione in §6.3
e §6.11. Testo originale: la quota crediti per ruolo la fissa la
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

### 6.10 Disponibilità: le prime giornate valgono più dell'anno prima (v3)

Obiettivo: frazione delle giornate conteggiate (3ª-38ª) in cui il giocatore
prende voto. Misurato su "aste storiche" ricostruite (`models/istantanea.py`:
universo dei tesserati, club all'asta, solo dati anteriori all'asta):

- le **presenze nelle prime 2 giornate** correlano 0,55-0,73 con quelle del
  resto della stagione; le presenze dell'anno prima 0,36-0,67. È la regola §3
  ("usa le prime giornate per la disponibilità") misurata: la v2 non la usava;
- logistica frazionaria per ruolo con ridge (`models/disponibilita.py`):
  correlazione con le presenze reali **0,59-0,77** fuori campione (v2:
  0,32-0,57), errore medio 5,8-8,0 presenze (v2: 9,9-16,5);
- un **boosting** (HistGradientBoosting) sugli stessi dati fa peggio
  (0,56-0,70): a livello giocatore-stagione il campione è piccolo e la
  relazione quasi lineare nel logit. Resta il logistico, senza dipendenze;
- **concorrenza nel reparto** e **normalizzazione per squadra** non migliorano
  la previsione: l'informazione è già nelle presenze recenti e osservate. Resta
  solo un **tetto** in porta (la somma delle disponibilità dei portieri di una
  squadra non supera quella storica: uno solo gioca);
- **senza giornate osservate** (listino d'estate) la correlazione scende a
  0,38-0,74 e i cambi di gerarchia estivi sono invisibili (Vicario arrivato da
  titolare alla Juventus è per il modello un esordiente). Il listino li
  segnala confrontando la gerarchia del modello con quella dell'FVM; si
  risolvono rigenerando il listino dopo le prime giornate.

Portieri: la componente portiere (gol subiti, imbattibilità, rigori parati) si
proietta dalla **difesa della squadra**, non dal portiere (`models/squadre.py`):
xG concessi l'anno prima riscalati ai gol della stagione (fattore da 1,02 nel
2020-21 a 0,87 nel 2025-26: l'xG grezzo avrebbe introdotto una deriva, §5),
neopromosse con la media storica delle neopromosse (−1,34 a partita contro
−0,86). Errore fuori campione 0,12 contro 0,135 dei gol subiti e 0,19 della media.

Rigoristi (`models/rigori.py`): quota dei rigori della squadra calciati dal
giocatore **nelle partite in cui era in campo**, contratta verso zero (1,5
rigori di pseudo-conteggio), status maturato in un altro club al 15%; rigori
attesi = rigori di squadra a partita × quota × presenze. Correlazione coi
rigori calciati 0,53 (v2: 0,50), calibrata (pendenza 0,96). Il modello assegna
circa metà dei rigori totali: l'altra metà la calciano rigoristi nuovi, che
nessuno può anticipare; ridistribuirla peggiora l'errore.

### 6.11 Il valore: presenze × vantaggio per partita, non punti totali (v3)

Con una panchina, una giornata saltata non costa i punti del titolare ma la
differenza col compagno che entra. Simulando la formazione settimanale di una
lega di 8 rose (`simulate/lega.py`: modulo migliore fra i sette del Classic
fra chi prende voto), il valore marginale di D, C e A correla **0,93-0,98** con
"presenze × vantaggio per partita sul rimpiazzo" e solo **0,64-0,75** con i
punti totali sopra il rimpiazzo usati dalla v2. La v2 premiava chi gioca tanto
anche se mediocre.

Funzione di default (`value/valore.py`):

    valore = presenze proiettate × (fantamedia proiettata − fantamedia del panchinaro tipo)

con il panchinaro tipo = media dei giocatori fra il rango 1,5k e 2,5k per punti
proiettati (k = domanda di titolari). Prezzo = 1 + tasso × valore, **tasso
unico** per tutti i ruoli, 3800 contendibili ripartiti sui 200 giocatori che
riempiono le rose: la somma dei prezzi delle rose è esattamente 4000 (la v2
dava il credito di pavimento a tutti i 509, somma 4314).

La simulazione resta come funzione alternativa (`valore_simulato`, il punto di
aggancio §7.1 per i modificatori), ma **non** è il default: il valore dei
portieri dipende da quanti titolari in porta restano svincolati (24 posti in
rosa per 20 titolari), e a seconda dell'ipotesi la simulazione dà ai portieri
dal 13% al 25% del valore, contro l'8,5% realizzato. La formula per presenza è
la più robusta al contesto (§6.12).

### 6.12 Backtest v2 → v3 (aste 2022-23 → 2025-26)

`python -m backtest.confronto` rigioca quattro aste: per ognuna i modelli si
addestrano solo sulle aste precedenti, la v2 si estrae da git (`bd4016e`) e gira
con le sue funzioni originali sugli stessi universi. Medie sulle quattro
stagioni, dentro il ruolo, P · D · C · A.

| metrica (punti dalla 3ª giornata) | ingenuo (punti anno prima) | v2 | v3 senza giornate | v3 con 2 giornate |
|---|---|---|---|---|
| Spearman, tutti | .64 · .39 · .41 · .31 | .60 · .39 · .43 · .34 | .66 · .43 · .45 · .39 | **.69 · .60 · .61 · .62** |
| Spearman fra i rilevanti | .47 · .10 · .14 · .24 | .33 · .03 · .13 · .24 | .51 · .10 · .12 · .30 | **.58 · .27 · .28 · .54** |
| distorsione (punti) | −9 · −17 · −22 · −17 | +70 · +30 · +33 · +50 | −5 · 0 · +1 · +1 | **−3 · 0 · 0 · +3** |
| calibrazione (1 = giusta) | .74 · .39 · .41 · .33 | 2,41 · 1,30 · 1,38 · 1,16 | 1,17 · .96 · .93 · .73 | **.98 · 1,00 · .96 · .86** |
| errore medio (punti) | 29 · 61 · 63 · 75 | 86 · 60 · 64 · 78 | 35 · 54 · 57 · 64 | **31 · 47 · 51 · 55** |
| correlazione presenze | — | .57 · .38 · .43 · .32 | .74 · .43 · .46 · .38 | **.77 · .59 · .60 · .59** |

"Rilevanti" = unione dei primi 3k per punti reali e per ciascun modello: lo
stesso insieme per tutti.

Valore economico: correlazione (Pearson, tutti i ruoli insieme) fra valore
previsto e valore marginale **realizzato** rigiocando la stagione con i
fantavoti veri, in tre contesti di rose:

| candidato | rose dal mercato (punti anno prima) | lega efficiente (proiezioni v3) | rose dai prezzi v2 |
|---|---|---|---|
| v2 | 0,355 | 0,312 | 0,249 |
| v3 senza giornate | 0,394 | 0,377 | 0,295 |
| v3 con 2 giornate | **0,428** | **0,433** | **0,360** |

La v3 vince in tutti i contesti. Sullo Spearman il margine è più piccolo
(0,28-0,31 contro 0,24-0,28): il valore realizzato di una singola stagione è
molto rumoroso, soprattutto per i difensori.

Limiti dichiarati: la formazione simulata sa chi giocherà (il limite di 5
sostituzioni non è simulato); l'universo storico è ricostruito dai tesserati
della stagione meno gli arrivi di gennaio; l'FVM storico non esiste, quindi il
confronto col mercato vero si potrà fare solo da questa stagione in avanti.

---

## 7. Architettura

```
fanta/
├── data/raw/          originali, MAI modificati, con data di scarico
├── data/panel/        csv consolidati
├── ingest/            parser voti, fonti, pannelli unificati (giornata, stagione)
├── rules/             regolamento + fantavoto + giornata + moduli  [PURO]
├── models/            istantanea d'asta, disponibilità, rendimento, squadre, rigori
├── simulate/          lega simulata: draft, formazione settimanale, valore marginale
├── value/             valore, prezzi, listino, report
├── auction/           stato d'asta, inflazione, interfaccia Streamlit   [da fare]
├── inseason/          formazione, capitano, panchina, svincoli          [da fare]
└── backtest/          split temporale, metriche su punti e valore, confronto v2
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

- **Disponibilità: logistica, non boosting (misurato, §6.10).** L'idea iniziale
  era LightGBM su ~100k righe giocatore-partita. A livello giocatore-stagione
  (l'unità che serve al listino) un boosting fa peggio della logistica
  frazionaria con ridge. Un modello per partita (minuti recenti, giorni di
  riposo, coppe) resta un'estensione possibile per `inseason/`.
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
Panchinaro tipo per ruolo (ranghi 1,5k-2,5k sulla domanda di titolari) →
valore = presenze × vantaggio per partita, troncato a zero → 3800 contendibili
ripartiti in proporzione sui 200 delle rose con un tasso unico, più 1 credito
di pavimento (§6.11) → rosa ottimale come zaino a vincoli multipli (da fare).

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
2. ~~**`ingest/`** + pannello unificato~~ **FATTO (v3)** (`ingest/panel.py`
   giocatore × giornata e × stagione con i tesserati a zero presenze,
   `ingest/fonti.py` Statistiche, listone, partite con nomi riconciliati).
   *Resta l'anagrafica xG giocatore (Understat ↔ Fantacalcio) congelata.*
3. ~~**`value/`** listino~~ **RIFATTO (v3)**: `value/valore.py` valore per presenza
   e prezzi a tasso unico, `value/listino.py`, `value/report.py`. Vedi §6.11.
4. **`auction/`** — massimo ritorno sull'investimento (**prossimo passo**)
5. ~~**`models/`** e **`simulate/`**~~ **FATTO (v3)**: `models/istantanea.py`,
   `disponibilita.py`, `rendimento.py`, `squadre.py`, `rigori.py`,
   `proiezione.py`; `simulate/lega.py` (formazione e valore marginale).
   *Resta la simulazione stagionale con correlazioni fra compagni.*
6. ~~**`backtest/`**~~ **FATTO (v3)**: `backtest/storico.py` (punti),
   `backtest/economico.py` (valore realizzato), `backtest/confronto.py`
   (v2 → v3, §6.12), `backtest/v2_legacy.py` (la v2 rieseguita da git).

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
| calibrazione disponibilità | correlazione con le presenze reali su split temporale (`tests/test_backtest.py`) |
| proiezione | batte "punti dell'anno scorso" in ogni ruolo, distorsione < 8 punti, calibrazione 0,75-1,25 |
| istantanea d'asta | nessun dato posteriore all'asta (`tests/test_istantanea.py`) |
| prezzi | monte esatto 4000 sulle rose, tasso crediti/valore unico |
| valore economico | correlazione col valore marginale realizzato (`backtest/economico.py`); contro l'FVM appena esisterà uno storico di FVM |

---

## 9. Cose ancora da fare sui dati

Piccole, tutte rinviabili.

1. ~~**Controllo di scala dell'xG**~~ — **fatto (v3)**, `models/squadre.py`: fattore
   per stagione da 1,02 a 0,87. Testo originale: due righe: sommare `home_xg`, `away_xg`, `gf`,
   `ga` su `partite.csv` e ricavare il fattore di riscalamento verso i gol reali.
   È la correzione più importante per i portieri e quindi per l'imbattibilità.
2. ~~**Ricalcolare l'imbattibilità**~~ — **fatto** (§6.3, §6.9): dai voti per giornata e correggere la quota
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

**Stimare una persistenza su un campione troncato.** Filtrare le coppie a
≥10 presenze in entrambe le stagioni esclude chi smette di giocare e fa crollare
la pendenza delle presenze (0,22 invece di 0,75 per i portieri). Il modello v2
ne usciva convinto che tutti fossero titolari (§6.4). Le stagioni a zero
presenze sono dati, non rumore: tenerle.

**Contrarre verso la media dei titolari.** Il prior "giocatori con ≥15
presenze" è più alto della media vera: gonfia proprio le riserve, che sono
la maggioranza del listone.

**Valutare sui punti totali in una lega con panchina.** Le giornate saltate le
copre la panchina: il valore è presenze × vantaggio per partita (§6.11).

**Imporre una quota per ruolo misurata a posteriori.** Contiene la fortuna e
oscilla da una stagione all'altra (§6.3, revisione): fissarla come vincolo dà a
ogni ruolo un prezzo diverso per lo stesso punto. Deve essere un risultato.

**Controlli contabili che nessuno guarda.** La somma dei prezzi della v2 era
4314 su un monte di 4000, e i portieri di una squadra sommavano fino a 100
presenze su 36. Erano test facili da scrivere e non c'erano: ora ci sono.

**Validare la proiezione solo con identità contabili.** I 52 test della v2
erano verdi su un modello che non batteva "punti dell'anno scorso". Un test di
accettazione deve misurare la previsione fuori campione (`tests/test_backtest.py`).

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
   un flag. Usata come `eta` in `ingest/fonti.carica_listone`.

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
