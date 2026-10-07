# DATI.md

Allegato tecnico a [`METODO.md`](METODO.md): schemi esatti di ogni file, trappole di parsing,
identità di validazione. Tutto verificato sui file reali del progetto.

**Regola generale: i file grezzi non si modificano mai.** Vivono in `data/raw/`
con la data di scarico nel nome. I parser leggono da lì e scrivono in
`data/panel/`. Se un parser ha un bug si ripassa dai grezzi, non dalla fonte.
Questa regola ha già salvato il progetto una volta: l'xG Opta di FBref è oggi
irriproducibile ed esiste solo perché il vecchio file non era stato sovrascritto.

---

## 1. Voti Fantacalcio.it — giocatore × giornata

File tipo: `Voti_Fantacalcio_Stagione_2025_26_Giornata_1.xlsx`

**Tre fogli**: `Fantacalcio`, `Statistico`, `Italia`. Sono tre fonti voti diverse.
**Usare esclusivamente `Fantacalcio`**, la redazione a cui è agganciata la lega.
Mescolarle introduce un errore sistematico che nessuna regolarizzazione rimuove.

Organizzazione **a blocchi per squadra**: una riga con il solo nome squadra, poi
l'intestazione, poi i giocatori. Il parser deve mantenere lo stato della squadra
corrente.

**Colonne:** `Cod.` · `Ruolo` · `Nome` · `Voto` · `Gf` · `Gs` · `Rp` · `Rs` ·
`Rf` · `Au` · `Amm` · `Esp` · `Ass`

`Cod.` **coincide con la colonna `#` del listone** (verificato): la
riconciliazione anagrafica fra voti e listone è gratuita.

**Convenzione gol (verificata con identità esatte sulle 6 stagioni, vedi §6.6).**
Qui `Gf` conta i **soli gol su azione**, rigori **esclusi**; i gol su rigore
stanno in `Rf` e `Rs` sono i rigori sbagliati. Questo è l'**opposto** delle
Statistiche stagionali (§2), dove `Gf` include i rigori. Mappatura verificata
riga per riga: `Rf` (voti) ≡ `R+` (Statistiche), `Rs` (voti) ≡ `R−`. Il totale
gol di una prestazione è quindi **`Gf + Rf`**. Sommare solo `Gf` sottostima ogni
rigorista del ~9-13%. Codificato in `rules/fantavoto.py` (`Prestazione`).

### Trappole

1. **Righe `ALL`** — 20 per giornata, sono gli allenatori. Scartare.
2. **Marcatore `6*`** — è il senza voto. Nella giornata 1 del 2025-26 compare 33
   volte su 314 giocatori; due di quelle righe portano un'ammonizione, il che
   conferma la semantica e si aggancia alla regola di lega "ammonito senza voto
   viene sostituito". **Le righe con asterisco NON contano come presenza.**
   Trattarle come un 6 pieno gonfia le medie di tutti i subentranti.
3. **`Voto` è testo**, non numero: contiene sia `6.5` sia `6*`.
4. **Solo chi è sceso in campo compare nel file** — 314 giocatori nella giornata
   1, circa 15,7 per squadra. Chi è rimasto in panchina o era infortunato non c'è.

   Conseguenza: per costruire il pannello della disponibilità bisogna
   **ricostruire la rosa di ogni squadra per stagione** come unione dei giocatori
   comparsi almeno una volta, e trattare l'assenza dalla giornata come mancata
   partecipazione. Si perde la distinzione fra infortunato e panchinaro
   inutilizzato: limite reale ma non bloccante, perché ai fini del fantacalcio i
   due casi producono lo stesso risultato. Caso non recuperabile: un giocatore
   trasferito a gennaio che non gioca mai resta invisibile.
5. **Non esiste una colonna fantavoto.** Va ricostruito; per validarlo vedi §6.
6. **Recuperi e rinvii**: conservare la data reale della partita, non solo il
   numero di giornata. Un turno giocato mesi dopo cade in un contesto di forma
   diverso e sfalsa ogni media mobile costruita sull'ordine delle giornate.

---

## 2. Statistiche stagionali — giocatore × stagione

Sei file, dal 2020-21 al 2025-26. Cinque fogli, gli ultimi quattro sono la stessa
tabella filtrata per ruolo: **usare solo `Tutti`**. Intestazione sulla **seconda
riga** (`header=1`).

**Colonne:** `Id` · `R` · `Rm` · `Nome` · `Squadra` · `Pv` · `Mv` · `Fm` · `Gf` ·
`Gs` · `Rp` · `Rc` · `R+` · `R-` · `Ass` · `Amm` · `Esp` · `Au`

Schema identico in tutte e sei (verificato). Righe: 678 / 675 / 672 / 664 / 679 /
663.

### Semantica decodificata per minimi quadrati

Coefficienti stimati regredendo `(Fm − Mv) · Pv` sugli eventi:

| colonna | significato | peso stimato |
|---|---|---|
| `Gf` | gol fatti, **rigori inclusi** | +3,000 |
| `Gs` | gol subiti | −1,000 |
| `Rp` | rigori parati | +2,980 |
| `Rc` | rigori calciati | −1,009 |
| `R+` | rigori segnati | +1,005 |
| `R-` | rigori sbagliati | −2,014 |
| `Ass` | assist | +1,003 |
| `Amm` | ammonizioni | −0,493 |
| `Esp` | espulsioni | −1,020 |
| `Au` | autogol | −2,035 |

`Rc = R+ + R−` verificato esattamente su tutte le righe.

Composizione: un rigore segnato produce +3 dal gol (già in `Gf`), poi −1 da `Rc`
e +1 da `R+`, quindi **+3** netti. Uno sbagliato produce −1 da `Rc` e −2 da `R−`,
quindi **−3**. Il triangolo esiste per leggibilità, non aggiunge punti.

### Formula equivalente

```
Fm = Mv + (3·Gf − Gs + 3·Rp + Ass − 0,5·Amm − Esp − 2·Au − 3·R−) / Pv
```

Errore medio sulle 6 stagioni: **0,0062**.

### Anomalia residua: 213 righe su 3319 (6,4%)

Scarto **sempre positivo**, sempre multiplo di 0,5 punti stagionali, crescente
col numero di ammonizioni.

**Causa:** `Amm` conta anche i cartellini presi in partite chiuse con `6*`, che
la redazione non applica alla fantamedia perché in quella giornata il voto non
esiste.

**Conseguenza:** `Amm` del file stagionale **non è** l'`Amm` che entra nella
fantamedia. Nel motore per giornata il problema non si pone. Non calibrare mai
nulla sugli aggregati stagionali senza questa correzione: introdurrebbe una
distorsione silenziosa sui giocatori più falloso.

### Nota
Il file **non conteggia l'imbattibilità del portiere**, attiva in questa lega. La
`Fm` letta qui sottostima i portieri. Ricostruirla dai file per giornata: portiere
con `Gs = 0` e voto reale = imbattuto.

### Pannello componenti (per la proiezione)
Per scomporre la fantamedia in parti con persistenze diverse (voto, gioco su
azione, rigori, malus, portiere) NON si usano le Statistiche: la loro colonna
`Amm` include i cartellini nelle gare senza voto (anomalia sopra), quindi la
ricomposizione sbaglia di multipli di 0,5. Si usano i **voti per giornata**, dove
`Amm` è corretto (solo presenze con voto) e `Gf` è già al netto dei rigori: la
ricomposizione è esatta. Generato da `ingest/componenti.py` in
`data/panel/componenti_stagione.csv` (rigenerabile), con controllo indipendente
all'ingresso (somma componenti = fantamedia). Persistenze misurate in docs/METODO.md §6.8.

### Altro
- 116 righe con `Pv = 0` nel 2025-26 (17,5%). **Non sono spazzatura:** misurano
  quanti tesserati non prendono mai voto, cioè il denominatore del rischio di
  rotazione. Stabile su sei stagioni: 16,7% – 18,6%.
- 663 giocatori contro i 526 del listone corrente, perché include chi ha lasciato
  la Serie A.

---

## 3. Partite FBref — squadra × partita

File: `Fbref_SenzaxG.csv` (completo, 6 stagioni) e `Fbref_xG.csv` (vecchio,
incompleto, **solo archivio storico dell'xG Opta**).

**Colonne rimaste dopo la perdita dei dati Opta:** `date` · `time` · `comp` ·
`round` · `day` · `venue` · `result` · `gf` · `ga` · `opponent` · `poss` ·
`attendance` · `captain` · `formation` · `opp formation` · `referee` ·
`match report` · `notes` · `sh` · `sot` · `fk` · `season` · `team`

**Perse:** `xg`, `xga`, `dist`, `pk`, `pkatt`.

Una riga **per squadra per partita**: ogni incontro compare due volte.

### Trappole

1. **`season` ha due formati diversi fra i due file**: `2020` nel vecchio,
   `'2020-2021'` nel nuovo. E soprattutto la stringa `'2021'` significa la
   stagione **2021-22** per FBref e la stagione **2020-21** per soccerdata. Mai
   una funzione di conversione unica: vedi `stagione_fbref` e
   `stagione_understat` in `understat_setup.py`.
2. **`round` vale `Matchweek N`**: convertire in intero.
3. **Due righe `Relegation tie-breaker`** nel 2022-23 (Spezia – Hellas Verona,
   2023-06-11): non è una giornata, **eliminare**. È la ragione per cui quella
   stagione ha 762 righe invece di 760.
4. **`attendance` vuota per 688 righe**, quasi tutte del 2020-21: fornisce
   **gratis l'indicatore delle partite a porte chiuse**, indispensabile per non
   far collassare la stima del fattore campo.
5. **FBref usa due nomi per la stessa squadra**: compaiono sia `Inter` sia
   `Internazionale`. È la causa più insidiosa di join che sembrano funzionare:
   metà delle partite dell'Inter si sarebbe agganciata e l'altra no, senza alcun
   errore. Entrambi vanno mappati.

---

## 4. Understat via `soccerdata`

Libreria `soccerdata` (Python **3.10+**; con la 3.9 pip installa silenziosamente
una versione vecchia). Lega `"ITA-Serie A"`, stagioni `["2021", "2122", "2223",
"2324", "2425", "2526"]`.

| metodo | output |
|---|---|
| `read_schedule()` | una riga per partita con **`home_xg`, `away_xg`**, gol, data. È il minimo indispensabile |
| `read_team_match_stats()` | statistiche squadra × partita più ricche |
| `read_player_season_stats()` | giocatore × stagione, **con minuti**; verificare se include `npg` e `npxG` |
| `read_shot_events()` | tiri, ~65k righe su sei stagioni: npxG esatto, xG giocatore-partita, rigori |

La libreria mette in cache le pagine grezze da sola: la seconda esecuzione è
quasi istantanea.

`read_player_season_stats()` **sostituisce i vecchi CSV xG per giocatore**: copre
sei stagioni invece di una, viene dalla stessa fonte del pannello partite, e se
contiene `npxG` rende superflua la stima dei gol attesi su azione con il fattore
0,76.

### Nota sui vecchi CSV xG per giocatore (ora rimossi)
Erano un export per stagione con `apps`, `min`, `goals`, `a`, `xG`, `xA`, `xG90`,
`xA90`. Il dato più prezioso non era l'xG ma i **minuti**, e in particolare la
differenza `apps − Pv`, cioè gli spezzoni giocati senza prendere voto. Se il file
Understat espone `apps` e `min`, quella misura resta disponibile.

---

## 5. Normalizzazione dei nomi

### Squadre — mappa canonica (verificata sulle 6 stagioni)

```python
TEAM_MAP = {                       # FBref -> Understat
    "Hellas Verona":  "Verona",
    "Internazionale": "Inter",
    "Milan":          "AC Milan",
    "Parma":          "Parma Calcio 1913",
}
```

Dopo la mappatura i due insiemi coincidono: 29 nomi per parte.

### Giocatori — la `ø` non si decompone con NFKD

È la causa della maggior parte dei fallimenti silenziosi. Servono sostituzioni
**esplicite** prima della normalizzazione Unicode:

```python
EXTRA = str.maketrans({
    'ø':'o', 'Ø':'O', 'đ':'d', 'Đ':'D', 'ł':'l', 'Ł':'L',
    'ß':'ss', 'æ':'ae', 'Æ':'Ae', 'ð':'d', 'þ':'th', 'ı':'i',
})
```

Casi reali verificati:

| Fantacalcio.it | fonte xG | causa |
|---|---|---|
| Ostigard | Leo Østigard | `ø` |
| Hojlund | Rasmus Højlund | `ø` |
| Sorensen O. | Oliver Sørensen | `ø` |
| N'Dicka | Evan Ndicka | apostrofo |
| Delprato | Enrico Del Prato | cognome separato |
| Malinovskyi | Ruslan Malinovskiy | traslitterazione |
| Kalulu | Pierre Kalulu Kyatengwa | secondo cognome |

Copertura misurata dell'aggancio con le correzioni: **97% sui titolari, 98%
complessivo**, 533 agganci univoci su 547 giocatori con almeno una presenza.

### Strategia di aggancio
1. Normalizzazione con le sostituzioni esplicite sopra
2. Rimozione del suffisso iniziale stile Fantacalcio.it (`Martinez L.` →
   `Martinez`)
3. Aggancio per **intersezione di token**, non uguaglianza di stringa
4. Disambiguazione dei candidati multipli tramite la **squadra** (24 casi
   ambigui con `Pv ≥ 25` risolti così)
5. Revisione manuale del residuo e **congelamento** della tabella

---

## 6. Identità di validazione

Test di accettazione del progetto, da eseguire su tutte le giornate come
controllo automatico.

### 6.1 Gol di squadra (verificata su tutte e 20 le squadre della giornata 1)

```
gf_squadra = Σ Gf dei suoi giocatori + Σ Au dei giocatori avversari
```

Il caso apparentemente anomalo del Pisa (0 gol dai propri giocatori ma 1 nel
tabellino) si spiega con l'autogol dell'Atalanta, e conferma la formula.

### 6.2 Portieri
```
Σ Gs del portiere = ga della squadra
```

### 6.3 Rigori — scioglie l'ambiguità su `Rf`/`Rs`
```
Σ Rf = pk        Σ Rs = pkatt − pk
```
Eseguibile solo sulle stagioni in cui `pk` esiste (il file FBref nuovo l'ha
persa). Test declassato da primario a opzionale: la stessa verifica si ottiene
in modo più fine da `Rc`, `R+`, `R−` delle Statistiche.

### 6.4 Aggregazione voti contro Statistiche
Aggregando i voti per giornata di una stagione, devono coincidere riga per riga:
`Pv`, `Gf`, `Gs`, `Rp`, `Ass`, `Esp`, `Au`, e di conseguenza `Mv` e `Fm`.

Diagnosi per tipo di scarto:
- **`Pv` non torna** → gestione errata dei `6*`
- **`Gf` non torna** → parser che legge male le colonne
- **`Fm` non torna a parità del resto** → errore nel motore di regolamento
- **`Amm` non torna** → atteso, vedi §2

### 6.5 Join FBref ↔ Understat
Chiave: **`(stagione, squadra_casa, squadra_ospite)`**, non la data. In un girone
all'italiana ogni coppia ordinata ricorre esattamente una volta per stagione:
chiave naturale, immune al formato della data, al fuso orario, ai rinvii e alla
numerazione delle giornate.

Prima del merge: ridurre FBref a una riga per partita (`venue == "Home"`) e
togliere lo spareggio 2023.

**Validazione:** i punteggi delle due fonti devono coincidere. Se coincidono al
100%, il join è provato: la probabilità che due partite sbagliate condividano
stagione, squadre e punteggio esatto è nulla. Risultato ottenuto: **2280 partite
agganciate, 2280 punteggi coincidenti**.

### 6.6 Convenzione gol voti↔Statistiche (verificata, era la domanda §11.2)
Aggregando i voti per giornata di una stagione:
```
Σ Rf (voti) = Σ R+ (Statistiche)          # rigori segnati
Σ Rs (voti) = Σ R− (Statistiche)          # rigori sbagliati
Σ (Gf + Rf) (voti) = Σ Gf (Statistiche)   # totale gol, rigori inclusi
```
Esatte su tutte e sei le stagioni. Il totale gol di lega torna con i gol reali
di `partite.csv` solo usando `Gf + Rf`, non `Gf` da solo (che è ~9-13% più basso
perché conta i soli gol su azione). Coperto da `tests/test_aggregazione.py`.

### 6.7 Residui voti↔Statistiche: due pattern, non rumore

Aggregando i voti per giornata contro le Statistiche (§6.4), 20-21 e 21-22
tornano a zero; le altre hanno pochi residui. Non sono trasferimenti (verificato:
ogni caso ha una sola squadra nei voti e codice unico nelle Statistiche). Sono
due meccanismi deterministici, imposti come invarianti in `tests/`.

**Pattern A — espulsione su senza voto.** Una riga `6*` che porta `Esp=1`. Il
parser scarta la riga (`6*` = assenza, corretto), ma le Statistiche contano sia
la presenza sia l'espulsione. E' il gemello dell'anomalia `Amm` di §2. Firma:
`Pv_voti < Pv_stat` e `Esp_voti < Esp_stat`. Solo **2 casi in 6 stagioni**
(Paredes 22-23, Henry 23-24).

**Pattern B — surplus di presenze su giocatori di margine, stagioni recenti.**
I voti per giornata sono **snapshot live**; le Statistiche sono il prodotto
**riconciliato di fine stagione**. Fra i due, Fantacalcio.it rivede le
apparizioni marginali di giovani/subentri (un `6` a un subentrante diventa s.v.,
un gol loggato live viene riattribuito). Firma **univoca e verificata**:
`Pv_voti >= Pv_stat` sempre — i voti sovra-contano, mai il contrario. Assente in
20-22, cresce dal 23-24 (2, 17, 7 casi): le stagioni vecchie erano gia'
convergenti (gol di lega +0), le recenti catturate piu' vicino al live
conservano gli extra. Impatto trascurabile (≈24 giocatori di margine su ~3300,
scarto Fm da arrotondamento) e **sempre a favore dei voti**: le Statistiche
restano la verita' di riferimento per la prezzatura.

**Riassegnazione di codice o ritardo di riconciliazione? Verificato: ritardo.**
Per tutti e 24 i casi B si e' cercato nelle Statistiche della stessa stagione
per **nome normalizzato** invece che per `Cod.`, per vedere se le presenze
mancanti finissero sotto un secondo codice. Esito netto: **0 su 24 hanno un
secondo codice; tutti e 24 hanno codice unico** con `Pv` piu' bassa. Le presenze
mancanti non sono attribuite ad alcun codice: sono state ritirate/riclassificate
s.v. nel prodotto finale. Non e' riassegnazione di codice.

**Conseguenza operativa (importante per il join).** `Cod.` **e' una chiave di
join sicura anche per i codici alti recenti**: un giocatore non viene spezzato su
due codici fra voti e Statistiche. Non serve un join per nome a valle. Se il
controllo avesse dato riassegnazione, la chiave giocatore non sarebbe stata
`Cod.` da sola e uno giovane esploso a novembre si sarebbe visto lo storico
dimezzato: verificato che non accade. Per il resto: rendimento dalle Statistiche
(verita'), serie temporale dai voti per giornata, sapendo che su giovani/subentri
delle ultime due stagioni i voti possono contenere 1-2 presenze poi ritirate.
Impatto sul prezzo indistinguibile da zero: sono giocatori con 1-2 presenze che
nel listino ricevono comunque il prior di ruolo per storico insufficiente. Il
bilancio gol di lega (`Σ Gf+Rf` voti vs `Σ Gf` Statistiche) e' il controllo
rapido: +0 = fonti convergenti, positivo = snapshot live con extra da riconciliare.

---

## 7. Eccezione: risultati a tavolino

**Verona – Roma, 19 settembre 2020, 1ª giornata.** Finì 0-0 sul campo; il giudice
sportivo inflisse alla Roma la sconfitta per 3-0 a tavolino per aver schierato
Amadou Diawara, iscritto per errore nella lista Under 22 nonostante avesse
compiuto 23 anni. Ricorso respinto in appello e dal Collegio di Garanzia del CONI.

FBref registra il risultato **omologato** (3-0), Understat quello **sul campo**
(0-0). Entrambi corretti, convenzioni diverse.

**Il pannello adotta il risultato sul campo.** Al fantacalcio la sconfitta a
tavolino non cambiò nulla: i voti restarono quelli, bonus e malus si riferirono
allo 0-0, e al portiere della Roma non fu assegnato alcun malus. Tenere il 3-0
avrebbe rotto l'identità §6.1, dove quella partita è uno 0-0 con imbattibilità
per entrambi i portieri.

L'eccezione è codificata in `ECCEZIONI_TAVOLINO` in `understat_setup.py`, con
messaggio a schermo: la validazione torna al 100% senza mascherare nulla.

Curiosità che chiude il cerchio: è la stessa partita per cui, nel vecchio file
Opta, mancava il valore di `xg`.

---

## 8. Listone 2026-27

File tipo: `Listone_20_08_26.xlsx`. **Intestazione sulla PRIMA riga (`header=0`)**
nel file corrente — NON sulla seconda: `pd.read_excel(header=1)` prende un
giocatore come intestazione. `value/dati.carica_listone` legge con `header=0`.

**Colonne:** `#` · `Nome` · `Fuori lista` · `Sq.` · `Under` · `R.` · `R.MANTRA` ·
`PGv` · `MV` · `FM` · `FVM/1000` · `QUOT.` (+ `FantaSquadra` e `Costo`, vuote,
da compilare dopo l'asta)

- **526 giocatori**, 20 squadre, codici univoci. `#` = `Cod.` dei voti.
- Composizione: **68 P, 186 D, 181 C, 91 A**.
- `QUOT.` su **base 500**, coerente con la lega. `FVM/1000` su base 1000: **da
  dividere per due**.
- **`PGv`, `MV`, `FM` sono a zero** nel listone di preparazione: si popolano a
  stagione avviata. Non usarlo come sorgente di validazione — usare le
  Statistiche.
- **18 giocatori marcati fuori lista** con asterisco (colonna `Fuori lista`):
  `value/dati.carica_listone(escludi_fuori_lista=True)` li toglie → 509 in lista.
- `Under` **è l'età** (numeri 18-40 circa), non un flag: confermato, usato come
  `eta` in `carica_listone`.

---

## 9. Ambiente e convenzioni

**Python 3.12 in venv dedicato dentro la cartella del progetto.** Il Python di
sistema di macOS (3.9, CommandLineTools) con pacchetti installati `--user`
produce sia versioni sbagliate delle librerie sia conflitti binari
(`ValueError: numpy.dtype size changed`).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install soccerdata pandas numpy
```

**Niente parquet.** I file sono piccoli e il CSV evita dipendenze compilate ed è
ispezionabile a occhio quando qualcosa non torna.

**`understat_setup.py --step 0`** esegue un preflight: versione di Python,
percorso dell'eseguibile, versioni dei pacchetti, presenza dei file. Farlo per
primo.

### Convenzioni non negoziabili
- **Ogni snapshot grezzo si conserva con la data e non si sovrascrive mai.**
- **I parser falliscono rumorosamente**: controllo esplicito delle colonne attese
  all'ingresso, con errore che dice quale manca.
- **I nomi del provider stanno dietro uno schema canonico**: il resto del codice
  vede `xg_squadra`, `xg_concessi`, `assist`, mai `xg`, `xga`, `a`. Se cambia la
  fonte si tocca un file solo.
- **Colonna `fonte_xg` nel pannello**, per non dover indovinare fra un anno.
- **Ogni join ha un criterio di validazione indipendente** e fallisce
  rumorosamente. Un merge riuscito al 72% senza errori è il modo canonico in cui
  muoiono i progetti di dati.
- **L'anagrafica dei nomi si costruisce una volta e si congela.**
- **Il regolamento sta solo in `rules/config.py`.**
- **Indicatori di regime obbligatori** nei modelli: sostituzioni disponibili e
  partite a porte chiuse.
