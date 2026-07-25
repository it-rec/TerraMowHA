# TerraMow per Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="Logo TerraMow" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · **Italiano** · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Questa è un'integrazione di Home Assistant per i robot tagliaerba TerraMow.

### Funzionalità

**Controllo**
- Entità tagliaerba: avvio, pausa e rientro alla base
- Taglio per zone: entità di selezione zona e servizio `terramow.start_select_region`
- **Modifica della pianificazione** — i servizi `terramow.add_schedule` / `terramow.delete_schedule` scrivono fasce di taglio settimanali sul robot e le verificano rileggendole. *Nota:* il firmware commerciale attuale non accetta ancora scritture della pianificazione via MQTT locale (l'app del produttore usa Bluetooth/cloud) — nel frattempo usa il **blueprint per il taglio adattato al meteo** per pianificare lato HA
- **Scheda mappa interattiva** — mappa vettoriale del prato con panoramica e zoom per le dashboard: posizione del robot in tempo reale (colorata in base all'attività, con modalità inseguimento), comandi avvio / pausa / base direttamente sulla scheda, indicatori di batteria / avanzamento / tempo rimanente, ombreggiatura della superficie tagliata con avanzamento per zona, percorso di taglio, stazione base, zone con selezione a tocco per il taglio, zone vietate e muri virtuali, guasti attivi segnalati nel punto in cui si sono verificati, e una **mappa di calore Wi-Fi** del prato; un **pulsante di vista** alterna Entrambi / Percorso / Superficie / Wi-Fi. Compatibile con i temi, si registra da sola, con editor grafico (`custom:terramow-map-card`)
- Pulsante per il taglio dei bordi
- Impostazioni da Home Assistant: altezza di taglio, velocità, distanza tra le passate, velocità della lama, distanza di taglio dei bordi, modalità e angoli della direzione principale, taglio accurato degli angoli, modalità taglio bordi per erba alta
- Manutenzione: pulsanti di azzeramento per i contatori del disco lame e della stazione base

**Monitoraggio**
- Telecamera mappa in tempo reale con percorso di taglio, posizione del robot e stazione base (più una telecamera «sola mappa» pulita per le dashboard, con risoluzione configurabile nelle opzioni)
- Batteria: livello, stato di carica, stato della temperatura, caricatore collegato, interruttore di alimentazione
- Avanzamento: superficie della sessione corrente, avanzamento (%), durata e tipo di lavoro; tempo di taglio totale, numero di lavori e superficie tagliata
- Stato: missione / sottomissione / stato della missione, modalità operativa, modalità di alimentazione, motivo del rientro alla base, rilevamento pioggia, indicatore di problema, indicatori di salvataggio e conversione dei dati
- **Sensore di guasto** — il guasto attivo come testo leggibile (ad es. *Robot bloccato*, *Robot sollevato* oppure *OK*), così una notifica o un assistente vocale può dire cosa non va senza elaborare un attributo con un template
- Sensore del lavoro in corso (mantiene la missione attiva anche in caso di interruzioni del segnale di presenza) e un sensore della potenza del segnale Wi-Fi del robot
- Mappa: stato, superficie, flag rilevata / costruibile / backup in corso
- Pianificazione: sensore del prossimo avvio programmato e un **calendario della pianificazione di taglio** in sola lettura (il prossimo taglio compare sulla scheda calendario)
- Entità di aggiornamento del firmware, versione del firmware nella pagina del dispositivo e sensore di compatibilità di versione
- Tutte le entità si aggiornano immediatamente agli invii del dispositivo — nessun ritardo di polling

**Diagnostica avanzata** (punti dati ricavati per reverse engineering — in gran parte nella categoria entità *Diagnostica*, molti disattivati per impostazione predefinita; vedi le [note sui punti dati non ufficiali](en/developers/data_point_unofficial.md))
- Errori ed eventi: numero di errori attivi (con l'elenco errori grezzo come attributo) e codice dell'ultimo evento. I codici di errore noti vengono tradotti in testo leggibile tramite un catalogo alimentato dalla comunità (`error_codes.py`), che decodifica anche l'ultimo codice di errore del robot (dp_115)
- Cellulare / 4G: modem attivo, potenza del segnale (RSRP / RSRQ), tipo di connessione e una lettura *forza rete cellulare*
- Ambiente: alba / tramonto riportati dal dispositivo, stato di luce diurna, riscaldamento antiappannamento, illuminazione e avviso di meteo estremo (con URL informativo opzionale)
- Sicurezza e impostazioni avanzate: stato del rilevamento di dislivelli e di pendenza, soglia del sensore di pioggia, ripresa automatica dopo la pioggia e relativo ritardo, e una lettura *forza stazione base singola*
- Modalità operative: stringhe delle modalità movimento / mappa / taglio
- Mappatura e avanzamento: flag di guida per la mappatura manuale (riposizionamento / intervento necessari, perimetro chiuso) e una percentuale di avanzamento del salvataggio della mappa

**Eventi e automazioni**
- **Entità evento del robot** — genera un evento distinto a ogni transizione significativa (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), ognuno con i campi grezzi della missione, così le automazioni reagiscono agli *accadimenti* senza interrogare lo stato di attività
- Blueprint di automazione importabili con un clic (vedi sotto)

**Comodità dell'integrazione**
- Rilevamento automatico tramite Zeroconf/mDNS
- Flusso di riconfigurazione (cambio di host/IP senza reinstallare) e flusso di riautenticazione
- **Segnalazioni di riparazione** — schede della dashboard utilizzabili per firmware incompatibile e per la manutenzione dovuta della lama / della stazione base
- Download della diagnostica per semplificare le segnalazioni di bug
- Tradotta in 33 lingue (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Comandi confermati** — il taglio per zone attende la conferma dp_119 del dispositivo e segnala i rifiuti invece di «riuscire» in silenzio
- Comunicazione locale push basata su MQTT — nessun cloud richiesto

### Entità supportate

| Piattaforma | Entità |
| --- | --- |
| Tagliaerba | Comando avvio / pausa / base con attività in tempo reale |
| Telecamera | Mappa con percorso, robot e stazione base; variante pulita «sola mappa» |
| Sensore | Livello batteria, stato batteria, stato temperatura batteria, stato mappa, superficie mappa, altezza di taglio, velocità di taglio, modalità operativa, posizione, tempo di taglio / lavori / superficie tagliata totali, superficie / avanzamento / durata / tipo di lavoro della sessione corrente, lavoro in corso, guasto, tempo residuo per lama e stazione base, prossimo avvio programmato, compatibilità di versione, stato della direzione principale, modalità di alimentazione, motivo del rientro alla base, missione, sottomissione, stato della missione. *Diagnostica:* errori attivi, ultimo evento, segnale Wi-Fi, cellulare RSRP / RSRQ / tipo, alba, tramonto, modalità movimento / mappa / taglio, soglia del sensore di pioggia, ritardo di ripresa dopo la pioggia, avanzamento salvataggio mappa |
| Sensore binario | In carica, navigazione localizzata, aggiornamento firmware in corso, interruttore di alimentazione, problema, pioggia rilevata, mappa rilevata / costruibile / backup in corso, salvataggio dati, conversione dati in corso. *Diagnostica:* cellulare attivo, riscaldamento antiappannamento, illuminazione, luce diurna, meteo estremo, rilevamento dislivelli / pendenza, ripresa automatica dopo la pioggia, forza stazione base singola, forza rete cellulare, mappatura manuale riposizionamento / intervento / perimetro chiuso, flag di stato 134 (non decodificato) |
| Selezione | Selezione zona, velocità di taglio, velocità della lama, modalità direzione principale, modalità taglio bordi per erba alta |
| Numero | Altezza di taglio, distanza di taglio dei bordi, distanza tra le passate, angolo per direzione singola, intervallo di rotazione automatica dell'angolo, angolo della prima / seconda direzione |
| Interruttore | Taglio accurato degli angoli |
| Pulsante | Taglio dei bordi, azzera timer lama, azzera timer stazione base |
| Aggiornamento | Versione del firmware |
| Evento | Evento del robot (taglio avviato / in pausa / rientro / alla base / completato / errore) |
| Calendario | Pianificazione di taglio (prossimo taglio programmato) |

### Installazione

[![Apri la tua istanza di Home Assistant e apri un repository nell'Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Metodo 1: HACS (consigliato)
1. Assicurati che [HACS](https://hacs.xyz/) sia installato
2. Usa il pulsante qui sopra per aggiungere l'integrazione a HACS
3. Apri HACS, cerca «TerraMow» e seleziona l'integrazione
4. Installala e riavvia Home Assistant

#### Metodo 2: Installazione manuale
1. Copia la cartella `custom_components/terramow` nella cartella `/config/custom_components` del tuo Home Assistant
2. Riavvia Home Assistant
3. Vai su Impostazioni → Dispositivi e servizi → Aggiungi integrazione
4. Cerca «TerraMow» e segui i passaggi di configurazione

### Configurazione

I dispositivi sulla rete locale vengono rilevati automaticamente tramite Zeroconf — accetta il dispositivo rilevato e inserisci la password MQTT. Per la configurazione manuale sono necessari i seguenti parametri:

- **Host**: indirizzo IP o nome host del dispositivo TerraMow
- **Password**: password MQTT per l'autenticazione

**Modificare le impostazioni in seguito**
- *Riconfigura* (Impostazioni → Dispositivi e servizi → TerraMow → Riconfigura): cambia host/IP o password sul posto, ad es. dopo che il robot ha ricevuto un nuovo indirizzo DHCP — non serve rimuovere e riaggiungere l'integrazione.
- *Opzioni* (Configura):
  - **Risoluzione di uscita della mappa** — più alta è più nitida, ma costa più banda e CPU per ogni rendering.
  - **Tema della mappa** — `light` o `dark`.
  - **Mostra la superficie tagliata** — ombreggia l'area già tagliata sotto la linea del percorso.
  - **Considera ogni lavoro terminato come completato al 100 %** — alcuni firmware terminano un lavoro senza emettere un segnale di completamento, così l'avanzamento della sessione non arriva mai al 100 % anche se il prato è finito (risulta «interrotto»). Attiva questa opzione per considerare completato qualsiasi lavoro terminato, come fa l'app del produttore; lasciala disattivata per conservare il valore onesto del contatore. *Predefinito: disattivato.*
- Se la password del dispositivo cambia, Home Assistant avvia automaticamente un flusso di *riautenticazione*.

### Requisiti

- Home Assistant 2024.6.0 o successivo (la CI verifica sull'attuale versione di HA Core)
- Firmware TerraMow versione 6.6.0 o successiva
- App TerraMow versione 1.6.0 o successiva
- La mappa in tempo reale e il percorso di taglio richiedono la versione 3 del modulo HA del firmware; con la versione 2 (ad es. S800) tutto il resto funziona, e il sensore di compatibilità di versione lo segnala

### Dispositivi supportati

Questa integrazione funziona con i robot tagliaerba TerraMow che espongono l'interfaccia MQTT/HTTP locale — cioè qualsiasi modello con il firmware richiesto. Viene usata con la serie S di TerraMow, incluso l'**S800** (che riporta la versione 2 del modulo HA del firmware) e unità più recenti con la versione 3. Qualsiasi robot TerraMow con firmware 6.6.0+ e app 1.6.0+ dovrebbe funzionare; il sensore di compatibilità di versione e una segnalazione di riparazione indicano se il firmware di una specifica unità è troppo vecchio per una data funzionalità.

### Servizi

#### `terramow.start_select_region`

Avvia il taglio per un elenco di sotto-regioni selezionate.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Crea o rimuove una fascia di taglio settimanale sul robot. Ogni scrittura viene
confermata dal dispositivo (conferma dp_119 più una rilettura della
pianificazione).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` richiede l'`item_id` della fascia (mostrato come uid
dell'evento di calendario e restituito quando una fascia viene aggiunta).

> **Nota:** il firmware commerciale attuale non accetta ancora scritture della
> pianificazione via MQTT locale (l'app del produttore usa Bluetooth/cloud). Nel
> frattempo usa il **blueprint per il taglio adattato al meteo** per pianificare
> lato HA.

### Scheda mappa interattiva

L'integrazione include la propria scheda Lovelace — registrata automaticamente, senza risorse manuali né installazione separata del frontend HACS:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Disegna il prato come vettori (nitido a ogni livello di zoom, segue il tuo tema HA): zone, zone vietate, muri virtuali, il percorso di taglio, la stazione base e la posizione del robot in tempo reale. Trascina per spostare, rotella o pizzico per lo zoom, doppio tocco per riadattare. **Tocca una o più zone** e premi il pulsante che appare per tagliare esattamente quelle zone (`terramow.start_select_region` dietro le quinte).

Un **pulsante di vista** alterna ciò che la scheda sovrappone al prato:

| Modalità | Mostra |
| --- | --- |
| **Entrambi** | la superficie tagliata *e* il percorso di taglio (predefinito quando la superficie è attiva) |
| **Percorso** | solo il percorso del lavoro corrente e di quello precedente |
| **Superficie** | solo l'ombreggiatura della superficie tagliata, con avanzamento per zona |
| **Wi-Fi** | una **mappa di calore Wi-Fi** del prato, misurata dal robot stesso durante il taglio (verde = forte). I vuoti tra le passate vengono interpolati dalle misure vicine; il terreno mai percorso resta vuoto |

La modalità scelta viene ricordata per entità nel browser. Opzioni e dettagli: vedi la [guida alle dashboard](en/dashboard.md#interactive-map-card) (in inglese). I dati della mappa in tempo reale richiedono la versione 3 del modulo HA del firmware (come la telecamera mappa). La scheda è disponibile anche nel selettore di schede della dashboard come **TerraMow Map Card**, con editor grafico completo — nessun YAML necessario.

### Esempio di dashboard

Una vista Lovelace pronta all'uso (mappa in tempo reale, comandi, indicatore di avanzamento, riepilogo di stato) più automazioni di notifica: vedi la [guida alle dashboard](en/dashboard.md) (in inglese).

### Blueprint di automazione

Blueprint importabili con un clic per le notifiche più comuni — ognuno chiede solo l'entità TerraMow interessata e un'azione di notifica:

- **Taglio adattato al meteo** — avvia il taglio secondo la tua pianificazione, saltandolo automaticamente se viene rilevata o prevista pioggia
  [![Importa blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Notifica di problema** — quando il robot segnala un guasto
  [![Importa blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Rientro per pioggia** — quando il robot rientra alla base a causa della pioggia
  [![Importa blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Taglio completato** — quando un lavoro di taglio si conclude
  [![Importa blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Usare direttamente l'entità evento** — l'entità evento del robot è il trigger più flessibile. Il suo attributo `event_type` è uno tra `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, e porta i campi grezzi `mission`, `sub_mission`, `state`, `back_to_station_reason` e `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow ha finito di tagliare 🌱"
```

### Segnalazioni di riparazione

L'integrazione crea segnalazioni di riparazione utilizzabili in Home Assistant (Impostazioni → Dispositivi e servizi → Riparazioni) invece di nascondere i problemi nei sensori:

- **Firmware incompatibile / aggiornamento necessario** — il firmware è troppo vecchio per l'integrazione (o per una funzionalità specifica). Deriva dal controllo di compatibilità di versione; scompare quando si annuncia un firmware compatibile.
- **Manutenzione della lama dovuta** — il disco lame ha raggiunto l'intervallo di manutenzione consigliato di 240 ore. Pulisci o sostituisci le lame e premi il pulsante *Azzera timer lama* per cancellarla.
- **Manutenzione della stazione base dovuta** — la stazione base ha raggiunto l'intervallo di manutenzione consigliato di 30 giorni. Puliscila e premi il pulsante *Azzera timer stazione base* per cancellarla.

### Diagnostica e risoluzione dei problemi

- **Download della diagnostica**: Impostazioni → Dispositivi e servizi → TerraMow → menu a tre punti → *Scarica diagnostica* genera un'istantanea JSON depurata (stato del dispositivo, compatibilità del firmware, cache grezze dei punti dati) — allegala alle segnalazioni di bug.
- **Scoprire funzionalità non supportate**: il robot pubblica più punti dati di quanti siano documentati. Il primo payload di ogni punto dati sconosciuto viene registrato una volta a livello INFO; attiva il logging di debug per l'integrazione `terramow` per registrarli tutti. Se trovi un punto dati per una funzionalità mancante (ad es. allarme di sollevamento, interruttore della pianificazione, codici di errore), condividilo in una issue.

### Come vengono aggiornati i dati

TerraMow è un'integrazione **local push**. Il robot esegue un broker MQTT a bordo; Home Assistant si collega direttamente tramite la rete locale (senza cloud) e si iscrive ai topic dei punti dati del dispositivo, così gli stati delle entità si aggiornano nell'istante in cui il robot segnala un cambiamento, e non secondo un intervallo di polling. I payload più grandi (la mappa, il percorso in tempo reale) vengono annunciati via MQTT e scaricati su richiesta via HTTP locale. Se il robot è in standby o fuori rete, la connessione viene ritentata con attesa esponenziale, e l'entità tagliaerba espone la perdita di connessione come attività `error`.

**I comandi falliscono in modo evidente, non silenzioso.** Quando invii un comando — `dock`, `start_mowing`, `pause`, taglio dei bordi, taglio per zone o qualsiasi modifica di impostazione — viene pubblicato con MQTT QoS 1 (una breve riconnessione lo mette quindi in buffer invece di scartarlo). Se il robot è offline o non raggiungibile, se il broker rifiuta la pubblicazione, oppure se un comando arriva più rapidamente di quanto il dispositivo possa accettarlo, la chiamata al servizio **fallisce con un errore** invece di segnalare un successo silenzioso. Così un'automazione che chiama `lawn_mower.dock` mentre il robot non è raggiungibile vede il fallimento (e può ritentare o notificare) invece di credere che il robot stia rientrando quando non ha mai ricevuto il comando.

### Limitazioni note

- **Nessun accesso cloud / remoto** — Home Assistant deve trovarsi sulla stessa rete locale del robot; non esiste un ripiego via cloud.
- **Funzionalità legate al firmware** — la mappa in tempo reale e la vista del percorso di taglio richiedono la versione 3 del modulo HA; con la versione 2 (ad es. l'S800) tutto il resto funziona, e il sensore di compatibilità / la segnalazione di riparazione riporta la limitazione.
- **Gli aggiornamenti del firmware** si effettuano tramite l'app TerraMow, non da Home Assistant; l'entità `update` del firmware è solo informativa.
- **Il sensore di posizione e la telecamera mappa pulita sono disattivati per impostazione predefinita** (il sensore di posizione si aggiorna a circa 2 Hz); attivali dalle impostazioni dell'entità se ti servono.
- **Molte entità di diagnostica avanzata sono disattivate per impostazione predefinita** e raggruppate nella categoria *Diagnostica* (cellulare, alba/tramonto, modalità operative, flag di mappatura manuale, ecc.); provengono da punti dati ricavati per reverse engineering, quindi attiva solo quelli che ti servono. Vedi le [note sui punti dati non ufficiali](en/developers/data_point_unofficial.md).
- Alcuni punti dati del dispositivo non sono documentati; quelli sconosciuti vengono registrati una volta per aiutare a scoprire funzionalità mancanti.

### Casi d'uso

- **Notifiche legate alla pioggia** — ricevi una notifica quando il robot rientra alla base a causa della pioggia (vedi i blueprint sopra).
- **Avvisi di guasto** — vieni avvisato nel momento in cui il robot segnala un problema (bloccato, sollevato, ostacolato).
- **Taglio per zone dalle automazioni** — chiama `terramow.start_select_region` per tagliare sotto-regioni specifiche secondo una pianificazione o da un pulsante della dashboard.
- **Promemoria di manutenzione** — i sensori del tempo residuo di lama / stazione base e i pulsanti di azzeramento permettono di automatizzare i promemoria di manutenzione.
- **Mappa in tempo reale su una dashboard** — mostra la telecamera mappa con la posizione del robot e il percorso di taglio (vedi la guida alle dashboard).

### Lingue

L'integrazione è tradotta in: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Note sull'aggiornamento

- **v0.5.0**: i valori di stato delle entità sono passati da maiuscolo a minuscolo (ad es. `MISSION_IDLE` → `mission_idle`) per rispettare i requisiti di traduzione di Home Assistant. Automazioni o template che confrontano stringhe di stato grezze richiedono un adeguamento una volta sola; i nomi visualizzati non cambiano.

### Supporto

Apri una issue su [GitHub](https://github.com/it-rec/TerraMowHA/issues) per ricevere assistenza.

### Informazioni per gli sviluppatori

Per gli sviluppatori interessati a capire o estendere questa integrazione (la documentazione per sviluppatori è in inglese):

- [Guida al contributo](../CONTRIBUTING.md) — configurazione, requisiti di qualità (100 % di copertura, `mypy --strict`, traduzioni), processo di PR e di rilascio
- [Architettura](ARCHITECTURE.md) — il funzionamento interno: ciclo di vita dell'hub, modello di esecuzione, catalogo dei punti dati, pipeline mappa/percorso
- [Guida per sviluppatori](en/developers.md) — il protocollo MQTT/HTTP del dispositivo così come viaggia in rete
- [Cosa aggiunge questo fork rispetto all'upstream](UPSTREAM_DELTA.md)

Per eseguire la suite di test in locale:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Licenza

Questo progetto è concesso in licenza secondo la GNU General Public License v3.0 — vedi il file [LICENSE](../LICENSE) per i dettagli.
