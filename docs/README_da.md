# TerraMow til Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · **Dansk** · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Dette er en Home Assistant-integration til TerraMow robotplæneklippere.

### Funktioner

**Styring**
- Plæneklipperentitet: start, pause og retur til ladestationen
- Zoneklipning: zonevalgsentitet og tjenesten `terramow.start_select_region`
- **Redigering af tidsplan** — tjenesterne `terramow.add_schedule` / `terramow.delete_schedule` skriver ugentlige klippevinduer til klipperen og verificerer dem ved tilbagelæsning. *Bemærk:* den nuværende butiksfirmware accepterer endnu ikke skrivning af tidsplan via lokal MQTT (producentens app bruger Bluetooth/sky) — brug indtil da **planen for vejrafhængig klipning** til planlægning på HA-siden
- **Interaktivt kortkort** — vektorkort over plænen med panorering og zoom til dashboards: robottens position i realtid (farvet efter aktivitet, med følgetilstand), knapper til start / pause / station direkte på kortet, brikker for batteri / fremdrift / resterende tid, skyggelægning af det klippede areal med fremdrift pr. zone, klippespor, basestation, zoner med tryk-for-at-klippe, forbudte zoner og virtuelle vægge, aktive fejl markeret dér hvor de opstod, samt et **Wi-Fi-varmekort** over plænen; en **visningsknap** skifter mellem Begge / Spor / Areal / Wi-Fi. Temabevidst, registrerer sig selv, med et grænsefladeredigeringsværktøj (`custom:terramow-map-card`)
- Knap til kantklipning
- Indstillinger fra Home Assistant: klippehøjde, hastighed, baneafstand, knivhastighed, kantklipningsafstand, hovedretningstilstand og -vinkler, grundig hjørneklipning, kantklipningstilstand til højt græs
- Vedligeholdelse: nulstillingsknapper til tællerne for knivskiven og basestationen

**Overvågning**
- Kortkamera i realtid med klippespor, robotposition og basestation (plus et rent kamera med kun kort til dashboards, opløsning kan konfigureres i indstillingerne)
- Batteri: niveau, opladningsstatus, temperaturstatus, oplader tilsluttet, tændknap
- Fremdrift: areal for den aktuelle session, fremdrift (%), varighed og jobtype; samlet klippetid, antal job og klippet areal
- Status: mission / undermission / missionsstatus, driftstilstand, strømtilstand, årsag til retur til stationen, regnregistrering, problemindikator, indikatorer for datagemning og datakonvertering
- **Fejlsensor** — den aktive fejl som læsbar tekst (fx *Klipperen sidder fast*, *Klipperen er løftet* eller *OK*), så en notifikation eller en taleassistent kan sige, hvad der er galt, uden at behandle en attribut med en skabelon
- Sensor for igangværende job (fastholder den aktive mission også ved huller i tilstedeværelsessignalet) og en sensor for klipperens Wi-Fi-signalstyrke
- Kort: status, areal, flag for registreret / kan bygges / sikkerhedskopiering i gang
- Tidsplan: sensor for næste planlagte start og en **kalender over klippetidsplanen**, som kun kan læses (den næste klipning vises på kalenderkortet)
- Entitet til firmwareopdatering, firmwareversion på enhedssiden og sensor for versionskompatibilitet
- Alle entiteter opdateres øjeblikkeligt ved udsendelser fra enheden — ingen pollingforsinkelse

**Avanceret diagnostik** (datapunkter fremskaffet ved reverse engineering — mest i entitetskategorien *Diagnostik*, mange slået fra som standard; se [noterne om uofficielle datapunkter](en/developers/data_point_unofficial.md))
- Fejl og hændelser: antal aktive fejl (med den rå fejlliste som attribut) og kode for seneste hændelse. Kendte fejlkoder oversættes til læsbar tekst via et katalog opbygget af fællesskabet (`error_codes.py`), som også afkoder klipperens nyeste fejlkode (dp_115)
- Mobilnet / 4G: modem aktiveret, signalstyrke (RSRP / RSRQ), forbindelsestype og en aflæsning af *tving mobilnet*
- Miljø: solopgang / solnedgang som enheden rapporterer, dagslysstatus, dugfjernende varme, belysning og en advarsel om ekstremt vejr (med valgfri info-URL)
- Sikkerhed og avancerede indstillinger: status for niveauforskels- og hældningsregistrering, tærskelværdi for regnsensoren, automatisk fortsættelse efter regn og forsinkelsen herfor, samt en aflæsning af *tving én basestation*
- Driftstilstande: strenge for bevægelses- / kort- / klippetilstand
- Kortlægning og fremdrift: vejledningsflag til manuel kortlægning (genplacering / overtagelse nødvendig, grænse lukket) og en procentsats for fremdriften i kortgemningen

**Hændelser og automatiseringer**
- **Hændelsesentitet for klipperen** — udløser en separat hændelse ved hver væsentlig overgang (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), hver med de rå missionsfelter, så automatiseringer reagerer på *begivenheder* uden at polle aktivitetsstatussen
- Automatiseringsplaner, der importeres med ét klik (se nedenfor)

**Bekvemmeligheder i integrationen**
- Automatisk opdagelse via Zeroconf/mDNS
- Rekonfigurationsflow (skift vært/IP uden at tilføje igen) og genautentificeringsflow
- **Reparationssager** — handlingsrettede dashboardkort for inkompatibel firmware og for forfalden vedligeholdelse af kniv / basestation
- Download af diagnostik til lettere fejlrapporter
- Oversat til 33 sprog (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Bekræftede kommandoer** — zoneklipning venter på enhedens dp_119-bekræftelse og rapporterer afvisninger i stedet for stille at "lykkes"
- Lokal push-kommunikation via MQTT — ingen sky nødvendig

### Understøttede entiteter

| Platform | Entiteter |
| --- | --- |
| Plæneklipper | Styring til start / pause / station med aktivitet i realtid |
| Kamera | Kort med spor, robot og basestation; ren variant med kun kort |
| Sensor | Batteriniveau, batteristatus, batteriets temperaturstatus, kortstatus, kortareal, klippehøjde, klippehastighed, driftstilstand, position, samlet klippetid / job / klippet areal, areal / fremdrift / varighed / jobtype for den aktuelle session, igangværende job, fejl, resterende tid for kniv og basestation, næste planlagte start, versionskompatibilitet, status for hovedretning, strømtilstand, årsag til retur til stationen, mission, undermission, missionsstatus. *Diagnostik:* aktive fejl, seneste hændelse, Wi-Fi-signal, mobilnet RSRP / RSRQ / type, solopgang, solnedgang, bevægelses- / kort- / klippetilstand, tærskelværdi for regnsensoren, forsinkelse for fortsættelse efter regn, fremdrift i kortgemning |
| Binær sensor | Oplader, navigation lokaliseret, firmwareopdatering i gang, tændknap, problem, regn registreret, kort registreret / kan bygges / sikkerhedskopiering i gang, gemmer data, datakonvertering i gang. *Diagnostik:* mobilnet aktiveret, dugfjernende varme, belysning, dagslys, ekstremt vejr, niveauforskels- / hældningsregistrering, automatisk fortsættelse efter regn, tving én basestation, tving mobilnet, manuel kortlægning genplacering / overtagelse / grænse lukket, statusflag 134 (uafkodet) |
| Valg | Zonevalg, klippehastighed, knivhastighed, hovedretningstilstand, kantklipningstilstand til højt græs |
| Tal | Klippehøjde, kantklipningsafstand, baneafstand, vinkel for enkeltretning, interval for automatisk vinkelrotation, vinkel for første / anden retning |
| Kontakt | Grundig hjørneklipning |
| Knap | Kantklipning, nulstil knivtimer, nulstil basestationstimer |
| Opdatering | Firmwareversion |
| Hændelse | Klipperhændelse (klipning startet / sat på pause / vender tilbage / ved stationen / fuldført / fejl) |
| Kalender | Klippetidsplan (næste planlagte klipning) |

### Installation

[![Åbn din Home Assistant-instans og åbn et repository i Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Metode 1: HACS (anbefalet)
1. Sørg for, at [HACS](https://hacs.xyz/) er installeret
2. Brug knappen ovenfor for at tilføje integrationen til HACS
3. Åbn HACS, søg efter "TerraMow" og vælg integrationen
4. Installer den og genstart Home Assistant

#### Metode 2: Manuel installation
1. Kopier mappen `custom_components/terramow` til mappen `/config/custom_components` i din Home Assistant
2. Genstart Home Assistant
3. Gå til Indstillinger → Enheder og tjenester → Tilføj integration
4. Søg efter "TerraMow" og følg konfigurationstrinnene

### Konfiguration

Enheder på det lokale netværk opdages automatisk via Zeroconf — godkend den fundne enhed og indtast MQTT-adgangskoden. Til manuel opsætning kræves følgende parametre:

- **Vært**: IP-adresse eller værtsnavn for TerraMow-enheden
- **Adgangskode**: MQTT-adgangskode til autentificering

**Ændring af indstillinger senere**
- *Rekonfigurer* (Indstillinger → Enheder og tjenester → TerraMow → Rekonfigurer): skift vært/IP eller adgangskode på stedet, fx efter at klipperen har fået en ny DHCP-adresse — integrationen behøver ikke fjernes og tilføjes igen.
- *Indstillinger* (Konfigurer):
  - **Kortets outputopløsning** — højere er skarpere, men koster mere båndbredde og processorkraft pr. gengivelse.
  - **Korttema** — `light` eller `dark`.
  - **Vis klippet areal** — skyggelægger det allerede klippede område under sporlinjen.
  - **Behandl alle afsluttede job som 100 % færdige** — noget firmware afslutter et job uden at sende et færdiggørelsessignal, så sessionens fremdrift kommer aldrig op på 100 %, selv om plænen er færdig (den læses som "afbrudt"). Slå dette til for at behandle alle afsluttede job som færdige, ligesom producentens app; lad det være slået fra for at bevare tællerens ærlige værdi. *Standard: fra.*
- Hvis enhedens adgangskode ændres, starter Home Assistant automatisk et *genautentificeringsflow*.

### Krav

- Home Assistant 2024.6.0 eller nyere (CI validerer mod den aktuelle HA Core-udgivelse)
- TerraMow-firmware version 6.6.0 eller nyere
- TerraMow-appen version 1.6.0 eller nyere
- Kort i realtid og klippespor kræver firmwarens HA-modulversion 3; på version 2 (fx S800) fungerer alt andet, og sensoren for versionskompatibilitet rapporterer det

### Understøttede enheder

Denne integration fungerer med TerraMow robotplæneklippere, der tilbyder den lokale MQTT/HTTP-grænseflade — altså enhver model med den påkrævede firmware. Den bruges med TerraMows S-serie, herunder **S800** (som rapporterer firmwarens HA-modulversion 2) og nyere enheder med version 3. Enhver TerraMow-klipper med firmware 6.6.0+ og app 1.6.0+ bør fungere; sensoren for versionskompatibilitet og en reparationssag viser, om firmwaren på en bestemt enhed er for gammel til en given funktion.

### Tjenester

#### `terramow.start_select_region`

Starter klipning for en liste af valgte delområder.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Opretter eller fjerner et ugentligt klippevindue i klipperen. Hver skrivning
bekræftes mod enheden (dp_119-bekræftelse plus en tilbagelæsning af tidsplanen).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` tager vinduets `item_id` (vises som kalenderhændelsens uid og
returneres, når et vindue tilføjes).

> **Bemærk:** den nuværende butiksfirmware accepterer endnu ikke skrivning af
> tidsplan via lokal MQTT (producentens app bruger Bluetooth/sky). Brug indtil da
> **planen for vejrafhængig klipning** til planlægning på HA-siden.

### Interaktivt kortkort

Integrationen leverer sit eget Lovelace-kort — registreres automatisk, ingen manuel ressource og ingen separat installation af HACS-frontend:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Det tegner plænen som vektorer (skarpt ved al zoom, følger dit HA-tema): zoner, forbudte zoner, virtuelle vægge, klippesporet, basestationen og robottens position i realtid. Træk for at panorere, rul eller knib for at zoome, dobbelttryk for at tilpasse igen. **Tryk på en eller flere zoner** og tryk på knappen, der kommer frem, for at klippe præcis disse zoner (`terramow.start_select_region` under motorhjelmen).

En **visningsknap** skifter, hvad kortet lægger oven på plænen:

| Tilstand | Viser |
| --- | --- |
| **Begge** | det klippede areal *og* klippesporet (standard, når arealet er slået til) |
| **Spor** | kun sporet for det aktuelle og det forrige job |
| **Areal** | kun skyggelægningen af det klippede areal, med fremdrift pr. zone |
| **Wi-Fi** | et **Wi-Fi-varmekort** over plænen, målt af klipperen selv mens den klipper (grøn = stærk). Huller mellem klippebaner interpoleres fra nærliggende målinger; jord, klipperen aldrig har kørt over, står tom |

Den valgte tilstand huskes pr. entitet i browseren. Indstillinger og detaljer: se [dashboardvejledningen](en/dashboard.md#interactive-map-card) (på engelsk). Kortdata i realtid kræver firmwarens HA-modulversion 3 (samme som kortkameraet). Kortet findes også i dashboardets kortvælger som **TerraMow Map Card**, med et fuldt grænsefladeredigeringsværktøj — ingen YAML nødvendig.

### Dashboardeksempel

En færdig Lovelace-visning (kort i realtid, styring, fremdriftsmåler, statusoverblik) plus notifikationsautomatiseringer: se [dashboardvejledningen](en/dashboard.md) (på engelsk).

### Automatiseringsplaner

Planer, der importeres med ét klik, til de mest almindelige notifikationer — hver spørger kun om den relevante TerraMow-entitet og en notifikationshandling:

- **Vejrafhængig klipning** — starter klipningen efter din tidsplan og springer den automatisk over, når regn registreres eller forudsiges
  [![Importer plan](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Problemnotifikation** — når klipperen rapporterer en fejl
  [![Importer plan](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Vendte tilbage på grund af regn** — når klipperen kører til stationen på grund af regn
  [![Importer plan](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Klipning færdig** — når et klippejob afsluttes
  [![Importer plan](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Brug af hændelsesentiteten direkte** — klipperens hændelsesentitet er den mest fleksible udløser. Attributten `event_type` er en af `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, og entiteten bærer de rå felter `mission`, `sub_mission`, `state`, `back_to_station_reason` og `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow er færdig med at klippe 🌱"
```

### Reparationssager

Integrationen opretter handlingsrettede reparationssager i Home Assistant (Indstillinger → Enheder og tjenester → Reparationer) i stedet for at skjule problemer i sensorer:

- **Firmware inkompatibel / opdatering påkrævet** — firmwaren er for gammel til integrationen (eller til en bestemt funktion). Udledes af kontrollen af versionskompatibilitet; forsvinder, når en kompatibel firmware melder sig.
- **Knivvedligeholdelse forfalden** — knivskiven har nået sit anbefalede serviceinterval på 240 timer. Rens eller udskift knivene og tryk på knappen *Nulstil knivtimer* for at rydde sagen.
- **Vedligeholdelse af basestationen forfalden** — basestationen har nået sit anbefalede serviceinterval på 30 dage. Rens den og tryk på knappen *Nulstil basestationstimer* for at rydde sagen.

### Diagnostik og fejlfinding

- **Download af diagnostik**: Indstillinger → Enheder og tjenester → TerraMow → trepunktsmenuen → *Download diagnostik* laver et renset JSON-øjebliksbillede (enhedens status, firmwarekompatibilitet, rå datapunktcacher) — vedhæft det i fejlrapporter.
- **Opdagelse af funktioner, der ikke understøttes**: klipperen udsender flere datapunkter end dokumenteret. Den første nyttelast for hvert ukendt datapunkt logges én gang på INFO-niveau; slå fejlfindingslogning til for integrationen `terramow` for at optage dem alle. Finder du et datapunkt til en manglende funktion (fx løftealarm, tidsplankontakt, fejlkoder), så del det i en sag.

### Sådan opdateres data

TerraMow er en **local push**-integration. Klipperen kører en MQTT-broker på enheden; Home Assistant forbinder direkte til den over det lokale netværk (uden sky) og abonnerer på enhedens datapunktemner, så entiteternes status opdateres i samme øjeblik, som klipperen melder en ændring, og ikke efter et pollinginterval. Større nyttelaster (kortet, sporet i realtid) annonceres via MQTT og hentes efter behov via lokal HTTP. Hvis klipperen sover eller er uden for netværket, forsøges forbindelsen igen med eksponentiel forsinkelse, og plæneklipperentiteten viser det mistede forbindelse som sin `error`-aktivitet.

**Kommandoer fejler højlydt, ikke stille.** Når du sender en kommando — `dock`, `start_mowing`, `pause`, kantklipning, zoneklipning eller en indstillingsændring — udsendes den med MQTT QoS 1 (en kort genoprettelse af forbindelsen buffrer den altså i stedet for at kassere den). Hvis klipperen er offline eller uden forbindelse, hvis brokeren afviser udsendelsen, eller hvis en kommando kommer hurtigere, end enheden kan modtage den, **fejler tjenestekaldet med en fejl** i stedet for stille at melde succes. En automatisering, der kalder `lawn_mower.dock`, mens klipperen er uden forbindelse, ser dermed fejlen (og kan prøve igen eller sende en notifikation) i stedet for at tro, at klipperen er på vej tilbage, når den aldrig fik kommandoen.

### Kendte begrænsninger

- **Ingen sky- / fjernadgang** — Home Assistant skal være på samme lokale netværk som klipperen; der er ingen reserveløsning via skyen.
- **Firmwareafhængige funktioner** — kortet i realtid og klippesporvisningen kræver HA-modulversion 3; på version 2 (fx S800) fungerer alt andet, og kompatibilitetssensoren / reparationssagen melder om begrænsningen.
- **Firmwareopdateringer** foretages via TerraMow-appen, ikke fra Home Assistant; firmwarens `update`-entitet er kun informativ.
- **Positionssensoren og det rene kortkamera er slået fra som standard** (positionssensoren opdateres med cirka 2 Hz); slå dem til i entitetsindstillingerne, hvis du har brug for dem.
- **Mange entiteter til avanceret diagnostik er slået fra som standard** og grupperet under kategorien *Diagnostik* (mobilnet, solopgang/solnedgang, driftstilstande, flag for manuel kortlægning osv.); de kommer fra datapunkter fremskaffet ved reverse engineering, så slå kun dem til, du har brug for. Se [noterne om uofficielle datapunkter](en/developers/data_point_unofficial.md).
- Nogle datapunkter i enheden er udokumenterede; ukendte logges én gang for at hjælpe med at opdage manglende funktioner.

### Anvendelsesmuligheder

- **Regnbevidste notifikationer** — få en push, når klipperen vender tilbage til stationen på grund af regn (se planerne ovenfor).
- **Fejlalarmer** — bliv underrettet i samme øjeblik, klipperen melder et problem (sidder fast, løftet, blokeret).
- **Zoneklipning fra automatiseringer** — kald `terramow.start_select_region` for at klippe bestemte delområder efter en tidsplan eller fra en dashboardknap.
- **Vedligeholdelsespåmindelser** — sensorerne for resterende tid for kniv / basestation og nulstillingsknapperne gør det muligt at automatisere vedligeholdelsespåmindelser.
- **Kort i realtid på et dashboard** — vis kortkameraet med robottens position og klippesporet (se dashboardvejledningen).

### Sprog

Integrationen er oversat til: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Opgraderingsnoter

- **v0.5.0**: entiteternes statusværdier blev ændret fra store til små bogstaver (fx `MISSION_IDLE` → `mission_idle`) for at opfylde Home Assistants oversættelseskrav. Automatiseringer eller skabeloner, der sammenligner rå statusstrenge, kræver en engangsjustering; viste navne er uændrede.

### Support

Åbn en sag på [GitHub](https://github.com/it-rec/TerraMowHA/issues) for at få support.

### Information til udviklere

For udviklere, der vil forstå eller udvide denne integration (udviklerdokumentationen er på engelsk):

- [Bidragsvejledning](../CONTRIBUTING.md) — opsætning, kvalitetskrav (100 % dækning, `mypy --strict`, oversættelser), PR- og udgivelsesproces
- [Arkitektur](ARCHITECTURE.md) — integrationens indre dele: hubbens livscyklus, udførelsesmodel, datapunktkatalog, kort-/sporpipeline
- [Udviklervejledning](en/developers.md) — enhedens MQTT/HTTP-protokol, som den sendes over nettet
- [Hvad denne fork tilføjer i forhold til upstream](UPSTREAM_DELTA.md)

Sådan kører du testene lokalt:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Licens

Dette projekt er licenseret under GNU General Public License v3.0 — se filen [LICENSE](../LICENSE) for detaljer.
