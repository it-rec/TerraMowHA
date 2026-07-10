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
- Taglio a zone: entità di selezione zona e servizio `terramow.start_select_region`
- **Schedule editing** — `terramow.add_schedule` / `terramow.delete_schedule` services write weekly mowing slots to the mower, confirmed against the device (acknowledgement + read-back); the calendar reflects changes immediately
- **Interactive map card** — pan/zoom vector lawn map for dashboards: live robot position (activity-tinted, with follow mode), on-card start / pause / dock controls, battery & job-progress chips, optional mowed-coverage shading, mowing path, base station, zones with tap-to-mow selection, forbidden areas and virtual walls; theme-aware, self-registering, with a UI editor (`custom:terramow-map-card`)
- Pulsante per il taglio dei bordi
- Impostazioni da Home Assistant: altezza di taglio, velocità, spaziatura, velocità delle lame, distanza di taglio dei bordi, modalità e angoli della direzione principale, taglio accurato degli angoli, modalità taglio bordi con erba alta
- Manutenzione: pulsanti di azzeramento per i contatori del disco lame e della stazione base

**Monitoraggio**
- Telecamera con mappa in tempo reale con percorso di taglio, posizione del robot e stazione base (più una telecamera con la sola mappa, pulita, per i dashboard, con risoluzione configurabile tramite le opzioni)
- Batteria: livello, stato di carica, stato della temperatura, caricabatterie collegato, interruttore di alimentazione
- Avanzamento del lavoro: area della sessione corrente, avanzamento (%), durata e tipo di lavoro; tempo di taglio totale, numero di lavori e area tagliata
- Stato: missione / sottomissione / stato della missione, modalità operativa, modalità di alimentazione, motivo del rientro alla stazione, rilevamento pioggia, indicatore di problemi, indicatori di salvataggio dati e conversione dati
- Mappa: stato, area, indicatori rilevata / costruibile / backup in corso
- Pianificazione: prossimo avvio pianificato
- Entità di aggiornamento firmware, versione del firmware nella pagina del dispositivo e sensore di compatibilità delle versioni
- Tutte le entità si aggiornano istantaneamente ai push del dispositivo — nessun ritardo da polling

**Comodità dell'integrazione**
- Rilevamento automatico tramite Zeroconf/mDNS
- Flusso di riconfigurazione (cambio di host/IP senza dover riaggiungere l'integrazione) e flusso di riautenticazione
- Download della diagnostica per segnalazioni di bug semplici
- Tradotta in 33 lingue (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- Comunicazione locale di tipo push basata su MQTT — nessun cloud richiesto

### Entità supportate

| Piattaforma | Entità |
| --- | --- |
| Tagliaerba | Controllo avvio / pausa / rientro alla base con attività in tempo reale |
| Telecamera | Mappa con percorso, robot e stazione base; variante pulita con la sola mappa |
| Sensore | Livello della batteria, stato della batteria, stato della temperatura della batteria, stato della mappa, area della mappa, altezza di taglio, velocità di taglio, modalità operativa, posizione, tempo di taglio totale / lavori / area tagliata, area / avanzamento / durata / tipo di lavoro della sessione corrente, tempo rimanente di lame e stazione base, prossimo avvio pianificato, compatibilità delle versioni, stato della direzione principale, modalità di alimentazione, motivo del rientro alla stazione, missione, sottomissione, stato della missione |
| Sensore binario | In carica, navigazione localizzata, aggiornamento firmware in corso, interruttore di alimentazione, problema, pioggia rilevata, mappa rilevata / costruibile / backup in corso, salvataggio dati, conversione dati in corso |
| Selezione | Selezione zona, velocità di taglio, velocità delle lame, modalità direzione principale, modalità taglio bordi con erba alta |
| Numero | Altezza di taglio, distanza di taglio dei bordi, spaziatura di taglio, angolo a direzione singola, intervallo dell'angolo di rotazione automatica, angolo della prima / seconda direzione |
| Interruttore | Taglio accurato degli angoli |
| Pulsante | Taglio dei bordi, azzera il timer delle lame, azzera il timer della stazione base |
| Aggiornamento | Versione del firmware |

### Installazione

#### Metodo 1: HACS (consigliato)
1. Assicurarsi che [HACS](https://hacs.xyz/) sia installato
2. Usare il pulsante qui sopra per aggiungere l'integrazione a HACS
3. Andare in HACS → Integrazioni → + → Cercare "TerraMow"
4. Installare e riavviare Home Assistant

#### Metodo 2: Installazione manuale
1. Copiare la cartella `custom_components/terramow` nella cartella `/config/custom_components` del proprio Home Assistant
2. Riavviare Home Assistant
3. Andare in Impostazioni → Dispositivi e servizi → Aggiungi integrazione
4. Cercare "TerraMow" e seguire i passaggi di configurazione

### Configurazione

I dispositivi sulla rete locale vengono rilevati automaticamente tramite Zeroconf — accettare il dispositivo rilevato e inserire la password MQTT. Per la configurazione manuale sono richiesti i seguenti parametri:

- **Host**: indirizzo IP o nome host del dispositivo TerraMow
- **Password**: password MQTT per l'autenticazione

**Modificare le impostazioni in seguito**
- *Riconfigura* (Impostazioni → Dispositivi e servizi → TerraMow → Riconfigura): cambiare host/IP o password direttamente, ad esempio dopo che il tagliaerba ha ricevuto un nuovo indirizzo DHCP — non è necessario rimuovere e riaggiungere l'integrazione.
- *Opzioni* (Configura): impostare la risoluzione di uscita della telecamera della mappa. Valori più alti offrono un'immagine più nitida nel dashboard al costo di maggiore banda e CPU per ogni rendering.
- Se la password del dispositivo cambia, Home Assistant avvia automaticamente un flusso di *riautenticazione*.

### Requisiti

- Home Assistant 2024.6.0 o successivo (testato con 2025.1.1)
- Firmware TerraMow versione 6.6.0 o successiva
- APP TerraMow versione 1.6.0 o successiva
- La mappa in tempo reale e il percorso di taglio richiedono la versione 3 del modulo HA del firmware; con la versione 2 (ad es. S800) tutto il resto funziona e il sensore di compatibilità delle versioni lo segnala

### Servizi

#### `terramow.start_select_region`

Avvia il taglio per un elenco di sottoregioni selezionate.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

### Interactive map card

The integration ships its own Lovelace card — auto-registered, no manual resource or HACS frontend install needed:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

It renders the lawn as vectors (crisp at any zoom, follows your HA theme): zones, forbidden areas, virtual walls, the mowing path, the base station and the robot's live position. Drag to pan, scroll or pinch to zoom, double-tap to re-fit. **Tap one or more zones** and press the button that appears to mow exactly those zones (`terramow.start_select_region` under the hood). Options and details: see the [dashboard guide](en/dashboard.md#interactive-map-card). Live map data requires firmware HA module version 3 (same as the map camera). The card is also available in the dashboard card picker as **TerraMow Map Card**, with a full UI editor — no YAML needed.

### Diagnostica e risoluzione dei problemi

- **Download della diagnostica**: Impostazioni → Dispositivi e servizi → TerraMow → menu a tre puntini → *Scarica diagnostica* genera uno snapshot JSON con i dati sensibili oscurati (stato del dispositivo, compatibilità del firmware, cache dei punti dati grezzi) — si prega di allegarlo alle segnalazioni di bug.
- **Scoprire funzionalità non supportate**: il tagliaerba pubblica più punti dati di quelli documentati. Il primo payload di ogni punto dati sconosciuto viene registrato una sola volta a livello INFO; abilitare il log di debug per l'integrazione `terramow` per registrarli tutti. Se si trova un punto dati relativo a una funzionalità mancante (ad es. allarme di sollevamento, interruttore della pianificazione, codici di errore), si prega di condividerlo in una issue.

### Lingue

L'integrazione è tradotta in: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Note di aggiornamento

- **v0.5.0**: i valori di stato delle entità sono passati dalle maiuscole alle minuscole (ad es. `MISSION_IDLE` → `mission_idle`) per rispettare i requisiti di traduzione di Home Assistant. Le automazioni o i template che confrontano stringhe di stato grezze richiedono un aggiornamento una tantum; i nomi visualizzati restano invariati.

### Supporto

Aprire una issue su [GitHub](https://github.com/it-rec/TerraMowHA/issues) per ricevere supporto.

### Informazioni per gli sviluppatori

Gli sviluppatori interessati a comprendere o estendere questa integrazione possono consultare la [Guida per gli sviluppatori](en/developers.md).

Per eseguire la suite di test in locale:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Licenza

Questo progetto è concesso in licenza secondo i termini della GNU General Public License v3.0 — per i dettagli vedere il file [LICENSE](../LICENSE).
