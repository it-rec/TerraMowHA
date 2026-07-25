# TerraMow för Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · **Svenska** · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Detta är en Home Assistant-integration för TerraMow robotgräsklippare.

### Funktioner

**Styrning**
- Gräsklipparentitet: starta, pausa och åka till laddstationen
- Zonklippning: zonvalsentitet och tjänsten `terramow.start_select_region`
- **Redigering av schema** — tjänsterna `terramow.add_schedule` / `terramow.delete_schedule` skriver veckovisa klippfönster till klipparen och verifierar dem genom återläsning. *Observera:* nuvarande butiksfirmware accepterar ännu inte schemaskrivningar via lokal MQTT (tillverkarens app använder Bluetooth/moln) — använd tills dess **ritningen för väderanpassad klippning** för schemaläggning på HA-sidan
- **Interaktivt kartkort** — vektorkarta över gräsmattan med panorering och zoom för instrumentpaneler: robotens position i realtid (färgad efter aktivitet, med följläge), knappar för start / paus / station direkt på kortet, brickor för batteri / förlopp / återstående tid, skuggning av den klippta ytan med förlopp per zon, klippspår, basstation, zoner med tryckval för klippning, förbjudna zoner och virtuella väggar, aktiva fel markerade där de uppstod, samt en **Wi-Fi-värmekarta** över gräsmattan; en **vyknapp** växlar mellan Båda / Spår / Yta / Wi-Fi. Temamedvetet, registrerar sig självt, med ett gränssnittsredigeringsverktyg (`custom:terramow-map-card`)
- Knapp för kantklippning
- Inställningar från Home Assistant: klipphöjd, hastighet, banavstånd, knivhastighet, kantklippningsavstånd, huvudriktningsläge och -vinklar, noggrann hörnklippning, kantklippningsläge för högt gräs
- Underhåll: återställningsknappar för knivskivans och basstationens räknare

**Övervakning**
- Kartkamera i realtid med klippspår, robotposition och basstation (plus en ren kamera med endast karta för instrumentpaneler, upplösning konfigurerbar i alternativen)
- Batteri: nivå, laddningsstatus, temperaturstatus, laddare ansluten, strömbrytare
- Förlopp: yta för aktuell session, förlopp (%), varaktighet och jobbtyp; total klipptid, antal jobb och klippt yta
- Status: uppdrag / deluppdrag / uppdragsstatus, driftläge, strömläge, orsak till återgång till stationen, regndetektering, problemindikator, indikatorer för datalagring och datakonvertering
- **Felsensor** — det aktiva felet som läsbar text (t.ex. *Klipparen har fastnat*, *Klipparen har lyfts* eller *OK*), så att en avisering eller röstassistent kan säga vad som är fel utan att bearbeta ett attribut med en mall
- Sensor för pågående jobb (behåller det aktiva uppdraget även vid avbrott i närvarosignalen) och en sensor för klipparens Wi-Fi-signalstyrka
- Karta: status, yta, flaggor för upptäckt / byggbar / säkerhetskopiering pågår
- Schema: sensor för nästa schemalagda start och en **kalender för klippschemat** som endast går att läsa (nästa klippning visas på kalenderkortet)
- Entitet för firmwareuppdatering, firmwareversion på enhetssidan och sensor för versionskompatibilitet
- Alla entiteter uppdateras direkt vid utskick från enheten — ingen pollningsfördröjning

**Avancerad diagnostik** (datapunkter framtagna genom reverse engineering — mestadels i entitetskategorin *Diagnostik*, många avstängda som standard; se [anteckningarna om inofficiella datapunkter](en/developers/data_point_unofficial.md))
- Fel och händelser: antal aktiva fel (med den råa fellistan som attribut) och kod för senaste händelse. Kända felkoder översätts till läsbar text via en katalog som byggs av communityn (`error_codes.py`), som även avkodar klipparens senaste felkod (dp_115)
- Mobilnät / 4G: modem aktiverat, signalstyrka (RSRP / RSRQ), anslutningstyp och en avläsning av *tvinga mobilnät*
- Miljö: soluppgång / solnedgång som enheten rapporterar, dagsljusstatus, imskyddsvärme, belysning och en varning för extremt väder (med valfri info-URL)
- Säkerhet och avancerade inställningar: status för nivåskillnads- och lutningsdetektering, tröskelvärde för regnsensorn, automatisk fortsättning efter regn och dess fördröjning, samt en avläsning av *tvinga en enda basstation*
- Driftlägen: strängar för rörelse- / kart- / klippläge
- Kartläggning och förlopp: vägledningsflaggor för manuell kartläggning (ompositionering / övertagande behövs, gräns stängd) och en procentsats för kartsparandets förlopp

**Händelser och automationer**
- **Händelseentitet för klipparen** — utlöser en separat händelse vid varje betydande övergång (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), var och en med de råa uppdragsfälten, så att automationer reagerar på *skeenden* utan att polla aktivitetsstatusen
- Automationsritningar som importeras med ett klick (se nedan)

**Bekvämligheter i integrationen**
- Automatisk upptäckt via Zeroconf/mDNS
- Omkonfigureringsflöde (byt värd/IP utan att lägga till på nytt) och återautentiseringsflöde
- **Reparationsärenden** — åtgärdbara kort i instrumentpanelen för inkompatibel firmware och för förfallet underhåll av kniv / basstation
- Nedladdning av diagnostik för enklare felrapporter
- Översatt till 33 språk (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Bekräftade kommandon** — zonklippning väntar på enhetens dp_119-bekräftelse och rapporterar avslag i stället för att tyst "lyckas"
- Lokal push-kommunikation via MQTT — inget moln behövs

### Stödda entiteter

| Plattform | Entiteter |
| --- | --- |
| Gräsklippare | Styrning för start / paus / station med aktivitet i realtid |
| Kamera | Karta med spår, robot och basstation; ren variant med endast karta |
| Sensor | Batterinivå, batteristatus, batteriets temperaturstatus, kartstatus, kartyta, klipphöjd, klipphastighet, driftläge, position, total klipptid / jobb / klippt yta, yta / förlopp / varaktighet / jobbtyp för aktuell session, pågående jobb, fel, återstående tid för kniv och basstation, nästa schemalagda start, versionskompatibilitet, status för huvudriktning, strömläge, orsak till återgång till stationen, uppdrag, deluppdrag, uppdragsstatus. *Diagnostik:* aktiva fel, senaste händelse, Wi-Fi-signal, mobilnät RSRP / RSRQ / typ, soluppgång, solnedgång, rörelse- / kart- / klippläge, tröskelvärde för regnsensorn, fördröjning för fortsättning efter regn, kartsparandets förlopp |
| Binär sensor | Laddar, navigering lokaliserad, firmwareuppdatering pågår, strömbrytare, problem, regn upptäckt, karta upptäckt / byggbar / säkerhetskopiering pågår, sparar data, datakonvertering pågår. *Diagnostik:* mobilnät aktiverat, imskyddsvärme, belysning, dagsljus, extremt väder, nivåskillnads- / lutningsdetektering, automatisk fortsättning efter regn, tvinga en enda basstation, tvinga mobilnät, manuell kartläggning ompositionering / övertagande / gräns stängd, statusflagga 134 (oavkodad) |
| Val | Zonval, klipphastighet, knivhastighet, huvudriktningsläge, kantklippningsläge för högt gräs |
| Tal | Klipphöjd, kantklippningsavstånd, banavstånd, vinkel för enkelriktning, intervall för automatisk vinkelrotation, vinkel för första / andra riktningen |
| Strömbrytare | Noggrann hörnklippning |
| Knapp | Kantklippning, återställ knivtimer, återställ basstationstimer |
| Uppdatering | Firmwareversion |
| Händelse | Klipparhändelse (klippning startad / pausad / återvänder / vid stationen / slutförd / fel) |
| Kalender | Klippschema (nästa schemalagda klippning) |

### Installation

[![Öppna din Home Assistant-instans och öppna ett arkiv i Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Metod 1: HACS (rekommenderas)
1. Kontrollera att [HACS](https://hacs.xyz/) är installerat
2. Använd knappen ovan för att lägga till integrationen i HACS
3. Öppna HACS, sök efter "TerraMow" och välj integrationen
4. Installera den och starta om Home Assistant

#### Metod 2: Manuell installation
1. Kopiera mappen `custom_components/terramow` till mappen `/config/custom_components` i din Home Assistant
2. Starta om Home Assistant
3. Gå till Inställningar → Enheter och tjänster → Lägg till integration
4. Sök efter "TerraMow" och följ konfigurationsstegen

### Konfiguration

Enheter i det lokala nätverket upptäcks automatiskt via Zeroconf — godkänn den upptäckta enheten och ange MQTT-lösenordet. För manuell installation krävs följande parametrar:

- **Värd**: IP-adress eller värdnamn för TerraMow-enheten
- **Lösenord**: MQTT-lösenord för autentisering

**Ändra inställningar senare**
- *Omkonfigurera* (Inställningar → Enheter och tjänster → TerraMow → Omkonfigurera): byt värd/IP eller lösenord på plats, t.ex. efter att klipparen fått en ny DHCP-adress — integrationen behöver inte tas bort och läggas till igen.
- *Alternativ* (Konfigurera):
  - **Kartans utmatningsupplösning** — högre är skarpare men kostar mer bandbredd och processorkraft per rendering.
  - **Karttema** — `light` eller `dark`.
  - **Visa klippt yta** — skuggar den redan klippta ytan under spårlinjen.
  - **Behandla varje avslutat jobb som 100 % klart** — viss firmware avslutar ett jobb utan att skicka någon slutsignal, så sessionens förlopp når aldrig 100 % även om gräsmattan är klar (det läses som "avbrutet"). Slå på detta för att behandla varje avslutat jobb som klart, precis som tillverkarens app; lämna av för att behålla räknarens ärliga värde. *Standard: av.*
- Om enhetens lösenord ändras startar Home Assistant automatiskt ett *återautentiseringsflöde*.

### Krav

- Home Assistant 2024.6.0 eller senare (CI validerar mot den aktuella HA Core-utgåvan)
- TerraMow-firmware version 6.6.0 eller senare
- TerraMow-appen version 1.6.0 eller senare
- Karta i realtid och klippspår kräver firmwarens HA-modulversion 3; på version 2 (t.ex. S800) fungerar allt annat, och sensorn för versionskompatibilitet rapporterar det

### Stödda enheter

Denna integration fungerar med TerraMow robotgräsklippare som exponerar det lokala MQTT/HTTP-gränssnittet — alltså vilken modell som helst med den firmware som krävs. Den används med TerraMows S-serie, inklusive **S800** (som rapporterar firmwarens HA-modulversion 2) och nyare enheter med version 3. Vilken TerraMow-klippare som helst med firmware 6.6.0+ och app 1.6.0+ bör fungera; sensorn för versionskompatibilitet och ett reparationsärende visar om en specifik enhets firmware är för gammal för en viss funktion.

### Tjänster

#### `terramow.start_select_region`

Startar klippning för en lista med valda delområden.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Skapar eller tar bort ett veckovis klippfönster i klipparen. Varje skrivning
bekräftas mot enheten (dp_119-bekräftelse samt en återläsning av schemat).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` tar fönstrets `item_id` (visas som kalenderhändelsens uid och
returneras när ett fönster läggs till).

> **Observera:** nuvarande butiksfirmware accepterar ännu inte schemaskrivningar
> via lokal MQTT (tillverkarens app använder Bluetooth/moln). Använd tills dess
> **ritningen för väderanpassad klippning** för schemaläggning på HA-sidan.

### Interaktivt kartkort

Integrationen levererar sitt eget Lovelace-kort — registreras automatiskt, ingen manuell resurs och ingen separat installation av HACS-frontend:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Det ritar gräsmattan som vektorer (skarpt vid all zoom, följer ditt HA-tema): zoner, förbjudna zoner, virtuella väggar, klippspåret, basstationen och robotens position i realtid. Dra för att panorera, rulla eller nyp för att zooma, dubbeltryck för att anpassa igen. **Tryck på en eller flera zoner** och tryck på knappen som visas för att klippa exakt dessa zoner (`terramow.start_select_region` under huven).

En **vyknapp** växlar vad kortet lägger över gräsmattan:

| Läge | Visar |
| --- | --- |
| **Båda** | den klippta ytan *och* klippspåret (standard när ytan är påslagen) |
| **Spår** | endast spåret för det aktuella och det föregående jobbet |
| **Yta** | endast skuggningen av den klippta ytan, med förlopp per zon |
| **Wi-Fi** | en **Wi-Fi-värmekarta** över gräsmattan, mätt av klipparen själv medan den klipper (grönt = starkt). Luckor mellan klippdrag interpoleras från intilliggande mätningar; mark som klipparen aldrig har körts över lämnas tom |

Det valda läget sparas per entitet i webbläsaren. Alternativ och detaljer: se [instrumentpanelsguiden](en/dashboard.md#interactive-map-card) (på engelska). Kartdata i realtid kräver firmwarens HA-modulversion 3 (samma som kartkameran). Kortet finns även i instrumentpanelens kortväljare som **TerraMow Map Card**, med ett fullständigt gränssnittsredigeringsverktyg — ingen YAML behövs.

### Exempel på instrumentpanel

En färdig Lovelace-vy (karta i realtid, styrning, förloppsmätare, statusöversikt) plus aviseringsautomationer: se [instrumentpanelsguiden](en/dashboard.md) (på engelska).

### Automationsritningar

Ritningar som importeras med ett klick för de vanligaste aviseringarna — var och en frågar bara efter den aktuella TerraMow-entiteten och en aviseringsåtgärd:

- **Väderanpassad klippning** — startar klippningen enligt ditt schema och hoppar automatiskt över den när regn upptäcks eller förutspås
  [![Importera ritning](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Problemavisering** — när klipparen rapporterar ett fel
  [![Importera ritning](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Återvände på grund av regn** — när klipparen åker till stationen på grund av regn
  [![Importera ritning](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Klippning klar** — när ett klippjobb avslutas
  [![Importera ritning](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Använda händelseentiteten direkt** — klipparens händelseentitet är den mest flexibla utlösaren. Attributet `event_type` är ett av `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, och entiteten bär de råa fälten `mission`, `sub_mission`, `state`, `back_to_station_reason` och `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow är klar med klippningen 🌱"
```

### Reparationsärenden

Integrationen skapar åtgärdbara reparationsärenden i Home Assistant (Inställningar → Enheter och tjänster → Reparationer) i stället för att gömma problem i sensorer:

- **Firmware inkompatibel / uppdatering krävs** — firmwaren är för gammal för integrationen (eller för en specifik funktion). Härleds från kontrollen av versionskompatibilitet; försvinner när en kompatibel firmware anmäler sig.
- **Knivunderhåll förfallet** — knivskivan har nått sitt rekommenderade serviceintervall på 240 timmar. Rengör eller byt knivarna och tryck på knappen *Återställ knivtimer* för att rensa ärendet.
- **Underhåll av basstationen förfallet** — basstationen har nått sitt rekommenderade serviceintervall på 30 dagar. Rengör den och tryck på knappen *Återställ basstationstimer* för att rensa ärendet.

### Diagnostik och felsökning

- **Nedladdning av diagnostik**: Inställningar → Enheter och tjänster → TerraMow → trepunktsmenyn → *Ladda ner diagnostik* skapar en rensad JSON-ögonblicksbild (enhetens status, firmwarekompatibilitet, råa datapunktscachar) — bifoga den i felrapporter.
- **Upptäcka funktioner som inte stöds**: klipparen publicerar fler datapunkter än vad som är dokumenterat. Den första nyttolasten för varje okänd datapunkt loggas en gång på INFO-nivå; aktivera felsökningsloggning för integrationen `terramow` för att spela in dem alla. Om du hittar en datapunkt för en saknad funktion (t.ex. lyftlarm, schemabrytare, felkoder), dela den i ett ärende.

### Så uppdateras data

TerraMow är en **local push**-integration. Klipparen kör en MQTT-broker på enheten; Home Assistant ansluter direkt till den över det lokala nätverket (utan moln) och prenumererar på enhetens datapunktsämnen, så entiteternas status uppdateras i samma stund som klipparen rapporterar en ändring, inte enligt ett pollningsintervall. Större nyttolaster (kartan, spåret i realtid) annonseras via MQTT och hämtas på begäran via lokal HTTP. Om klipparen sover eller är utanför nätverket görs nya anslutningsförsök med exponentiell fördröjning, och gräsklipparentiteten visar det förlorade anslutningen som sin `error`-aktivitet.

**Kommandon misslyckas högljutt, inte tyst.** När du skickar ett kommando — `dock`, `start_mowing`, `pause`, kantklippning, zonklippning eller någon inställningsändring — publiceras det med MQTT QoS 1 (en kort återanslutning buffrar det alltså i stället för att tappa det). Om klipparen är offline eller onåbar, om brokern avvisar publiceringen, eller om ett kommando kommer snabbare än enheten kan ta emot det, **misslyckas tjänsteanropet med ett fel** i stället för att tyst rapportera framgång. En automation som anropar `lawn_mower.dock` medan klipparen är onåbar ser därmed misslyckandet (och kan försöka igen eller avisera) i stället för att tro att klipparen är på väg tillbaka när den aldrig fick kommandot.

### Kända begränsningar

- **Ingen moln- / fjärråtkomst** — Home Assistant måste finnas i samma lokala nätverk som klipparen; det finns ingen reservväg via molnet.
- **Firmwareberoende funktioner** — kartan i realtid och klippspårsvyn kräver HA-modulversion 3; på version 2 (t.ex. S800) fungerar allt annat, och kompatibilitetssensorn / reparationsärendet rapporterar begränsningen.
- **Firmwareuppdateringar** görs via TerraMow-appen, inte från Home Assistant; firmwarens `update`-entitet är endast informativ.
- **Positionssensorn och den rena kartkameran är avstängda som standard** (positionssensorn uppdateras med cirka 2 Hz); aktivera dem i entitetsinställningarna om du behöver dem.
- **Många entiteter för avancerad diagnostik är avstängda som standard** och grupperade under kategorin *Diagnostik* (mobilnät, soluppgång/solnedgång, driftlägen, flaggor för manuell kartläggning m.m.); de kommer från datapunkter framtagna genom reverse engineering, så aktivera bara dem du behöver. Se [anteckningarna om inofficiella datapunkter](en/developers/data_point_unofficial.md).
- Vissa datapunkter i enheten är odokumenterade; okända loggas en gång för att hjälpa till att upptäcka saknade funktioner.

### Användningsfall

- **Regnmedvetna aviseringar** — få en push när klipparen återvänder till sin station på grund av regn (se ritningarna ovan).
- **Fellarm** — bli aviserad i samma stund som klipparen rapporterar ett problem (fastnat, lyft, blockerad).
- **Zonklippning från automationer** — anropa `terramow.start_select_region` för att klippa specifika delområden enligt ett schema eller från en knapp i instrumentpanelen.
- **Underhållspåminnelser** — sensorerna för återstående tid för kniv / basstation och återställningsknapparna gör det möjligt att automatisera underhållspåminnelser.
- **Karta i realtid i en instrumentpanel** — visa kartkameran med robotens position och klippspåret (se instrumentpanelsguiden).

### Språk

Integrationen är översatt till: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Uppgraderingsanteckningar

- **v0.5.0**: entiteternas statusvärden ändrades från versaler till gemener (t.ex. `MISSION_IDLE` → `mission_idle`) för att uppfylla Home Assistants översättningskrav. Automationer eller mallar som jämför råa statussträngar behöver en engångsjustering; visade namn är oförändrade.

### Support

Öppna ett ärende på [GitHub](https://github.com/it-rec/TerraMowHA/issues) för support.

### Information för utvecklare

För utvecklare som vill förstå eller utöka denna integration (utvecklardokumentationen är på engelska):

- [Bidragsguide](../CONTRIBUTING.md) — uppsättning, kvalitetskrav (100 % täckning, `mypy --strict`, översättningar), PR- och släppprocess
- [Arkitektur](ARCHITECTURE.md) — integrationens inre delar: hubbens livscykel, exekveringsmodell, datapunktskatalog, kart-/spårpipeline
- [Utvecklarguide](en/developers.md) — enhetens MQTT/HTTP-protokoll så som det går över nätet
- [Vad denna fork lägger till jämfört med upstream](UPSTREAM_DELTA.md)

Så kör du testsviten lokalt:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Licens

Detta projekt är licensierat under GNU General Public License v3.0 — se filen [LICENSE](../LICENSE) för detaljer.
