# TerraMow voor Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow-logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · **Nederlands** · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Dit is een Home Assistant-integratie voor TerraMow-robotmaaiers.

### Functies

**Besturing**
- Grasmaaier-entiteit: starten, pauzeren en naar het dockstation
- Zone-maaien: zonekeuze-entiteit en de service `terramow.start_select_region`
- **Schema bewerken** — de services `terramow.add_schedule` / `terramow.delete_schedule` schrijven wekelijkse maaivensters naar de maaier en verifiëren ze door terug te lezen. *Let op:* de huidige winkelfirmware accepteert schemawijzigingen via lokale MQTT nog niet (de app van de fabrikant gebruikt Bluetooth/cloud) — gebruik tot die tijd de **blueprint voor weersafhankelijk maaien** voor planning aan de HA-kant
- **Interactieve kaartkaart** — vectorkaart van het gazon met pannen/zoomen voor dashboards: live robotpositie (getint op activiteit, met volgmodus), bediening voor starten / pauzeren / docken op de kaart zelf, chips voor accu / voortgang / resterende tijd, arcering van het gemaaide oppervlak met voortgang per zone, maaipad, basisstation, zones met tikken-om-te-maaien, verboden zones en virtuele wanden, actieve storingen op hun plek gemarkeerd, en een **wifi-heatmap** van het gazon; een **weergaveknop** wisselt tussen Beide / Pad / Oppervlak / Wifi. Thema-bewust, registreert zichzelf, met een UI-editor (`custom:terramow-map-card`)
- Knop voor kantenmaaien
- Instellingen vanuit Home Assistant: maaihoogte, snelheid, baanafstand, mesbladsnelheid, kantsnijafstand, hoofdrichtingsmodus en -hoeken, grondig hoeken maaien, kantenmaaimodus voor hoog gras
- Onderhoud: resetknoppen voor de tellers van de messchijf en het basisstation

**Monitoring**
- Live kaartcamera met maaipad, robotpositie en basisstation (plus een schone kaart-only camera voor dashboards, resolutie instelbaar via de opties)
- Accu: niveau, laadstatus, temperatuurstatus, lader aangesloten, aan/uit-schakelaar
- Voortgang: oppervlak van de huidige sessie, voortgang (%), duur en taaktype; totale maaitijd, aantal taken en gemaaid oppervlak
- Status: missie / submissie / missiestatus, bedrijfsmodus, energiemodus, reden voor terugkeer naar station, regendetectie, probleemindicator, indicatoren voor gegevens opslaan en gegevensconversie
- **Storingssensor** — de actieve storing als leesbare tekst (bijv. *Maaier vastgelopen*, *Maaier opgetild* of *OK*), zodat een melding of spraakassistent kan zeggen wat er mis is zonder een attribuut via een template uit te lezen
- Sensor voor de lopende taak (houdt de actieve missie vast over onderbrekingen in de heartbeat) en een sensor voor de wifi-signaalsterkte van de maaier
- Kaart: status, oppervlak, vlaggen voor gedetecteerd / bouwbaar / back-up bezig
- Schema: sensor voor de volgende geplande start en een alleen-lezen **maaischema-agenda** (de volgende maaibeurt verschijnt op de agendakaart)
- Firmware-update-entiteit, firmwareversie op de apparaatpagina en een sensor voor versiecompatibiliteit
- Alle entiteiten werken direct bij op pushes van het apparaat — geen pollingvertraging

**Geavanceerde diagnostiek** (gereverse-engineerde datapunten — meestal in de entiteitscategorie *Diagnostisch*, veel standaard uitgeschakeld; zie de [notities over onofficiële datapunten](en/developers/data_point_unofficial.md))
- Fouten & gebeurtenissen: aantal actieve fouten (met de ruwe foutenlijst als attribuut) en de code van de laatste gebeurtenis. Bekende foutcodes worden via een door de community samengestelde catalogus (`error_codes.py`) omgezet naar leesbare tekst; die decodeert ook de laatste foutcode van de maaier (dp_115)
- Mobiel / 4G: modem ingeschakeld, signaalsterkte (RSRP / RSRQ), verbindingstype en een uitlezing van *mobiel netwerk forceren*
- Omgeving: door het apparaat gemelde zonsopkomst / zonsondergang, daglichtstatus, antibeslagverwarming, verlichting en een extreem-weerwaarschuwing (met optionele info-URL)
- Veiligheid & geavanceerde instellingen: status van klif- en hellingdetectie, drempel van de regensensor, automatisch hervatten na regen en de vertraging daarvan, en een uitlezing van *één basisstation forceren*
- Bedrijfsmodi: tekenreeksen voor beweeg- / kaart- / maaimodus
- Kartering & voortgang: hulpvlaggen voor handmatig karteren (herpositionering / overname nodig, grens gesloten) en een percentage voor de voortgang van het opslaan van de kaart

**Gebeurtenissen & automatisering**
- **Maaier-gebeurtenisentiteit** — vuurt bij elke noemenswaardige overgang een losse gebeurtenis af (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), elk met de ruwe missievelden, zodat automatiseringen op *gebeurtenissen* reageren zonder de activiteitsstatus te pollen
- Automatiserings-blueprints om met één klik te importeren (zie hieronder)

**Gebruiksgemak van de integratie**
- Automatische detectie via Zeroconf/mDNS
- Herconfiguratie-flow (host/IP wijzigen zonder opnieuw toevoegen) en herauthenticatie-flow
- **Reparatiemeldingen** — bruikbare dashboardkaarten voor incompatibele firmware en voor verlopen onderhoud van mes / basisstation
- Diagnostiek-download voor eenvoudige bugrapporten
- Vertaald in 33 talen (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Bevestigde opdrachten** — zone-maaien wacht op de dp_119-bevestiging van het apparaat en meldt afwijzingen in plaats van stil te "slagen"
- Lokale push-communicatie via MQTT — geen cloud nodig

### Ondersteunde entiteiten

| Platform | Entiteiten |
| --- | --- |
| Grasmaaier | Besturing voor starten / pauzeren / docken met live activiteit |
| Camera | Kaart met pad, robot en basisstation; schone kaart-only variant |
| Sensor | Accuniveau, accustatus, accutemperatuurstatus, kaartstatus, kaartoppervlak, maaihoogte, maaisnelheid, bedrijfsmodus, positie, totale maaitijd / taken / gemaaid oppervlak, oppervlak / voortgang / duur / taaktype van de huidige sessie, lopende taak, storing, resterende tijd voor mes en basisstation, volgende geplande start, versiecompatibiliteit, hoofdrichtingsstatus, energiemodus, reden voor terugkeer naar station, missie, submissie, missiestatus. *Diagnostisch:* actieve fouten, laatste gebeurtenis, wifi-signaal, mobiel RSRP / RSRQ / type, zonsopkomst, zonsondergang, beweeg- / kaart- / maaimodus, drempel van de regensensor, vertraging voor hervatten na regen, voortgang kaart opslaan |
| Binaire sensor | Aan het laden, navigatie gelokaliseerd, firmware wordt bijgewerkt, aan/uit-schakelaar, probleem, regen gedetecteerd, kaart gedetecteerd / bouwbaar / back-up bezig, gegevens opslaan, gegevensconversie bezig. *Diagnostisch:* mobiel ingeschakeld, antibeslagverwarming, verlichting, daglicht, extreem weer, klif- / hellingdetectie, automatisch hervatten na regen, één basisstation forceren, mobiel netwerk forceren, handmatig karteren herpositionering / overname / grens gesloten, statusvlag 134 (niet gedecodeerd) |
| Keuzelijst | Zonekeuze, maaisnelheid, mesbladsnelheid, hoofdrichtingsmodus, kantenmaaimodus voor hoog gras |
| Getal | Maaihoogte, kantsnijafstand, baanafstand, hoek voor enkele richting, interval voor automatisch draaien van de hoek, hoek van de eerste / tweede richting |
| Schakelaar | Grondig hoeken maaien |
| Knop | Kantenmaaien, mestimer resetten, basisstationtimer resetten |
| Update | Firmwareversie |
| Gebeurtenis | Maaier-gebeurtenis (maaien gestart / gepauzeerd / terugkerend / gedockt / voltooid / fout) |
| Agenda | Maaischema (volgende geplande maaibeurt) |

### Installatie

[![Open je Home Assistant-instantie en open een repository in de Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Methode 1: HACS (aanbevolen)
1. Zorg dat [HACS](https://hacs.xyz/) is geïnstalleerd
2. Gebruik de knop hierboven om de integratie aan HACS toe te voegen
3. Open HACS, zoek naar "TerraMow" en selecteer de integratie
4. Installeer en start Home Assistant opnieuw op

#### Methode 2: Handmatige installatie
1. Kopieer de map `custom_components/terramow` naar de map `/config/custom_components` van je Home Assistant
2. Start Home Assistant opnieuw op
3. Ga naar Instellingen → Apparaten & diensten → Integratie toevoegen
4. Zoek naar "TerraMow" en volg de configuratiestappen

### Configuratie

Apparaten in het lokale netwerk worden automatisch gedetecteerd via Zeroconf — accepteer het gevonden apparaat en voer het MQTT-wachtwoord in. Voor handmatige installatie zijn de volgende parameters nodig:

- **Host**: IP-adres of hostnaam van het TerraMow-apparaat
- **Wachtwoord**: MQTT-wachtwoord voor authenticatie

**Instellingen later wijzigen**
- *Herconfigureren* (Instellingen → Apparaten & diensten → TerraMow → Herconfigureren): wijzig host/IP of wachtwoord ter plekke, bijv. nadat de maaier een nieuw DHCP-adres heeft gekregen — de integratie hoeft niet verwijderd en opnieuw toegevoegd te worden.
- *Opties* (Configureren):
  - **Uitvoerresolutie van de kaart** — hoger is scherper, maar kost meer bandbreedte en CPU per render.
  - **Kaartthema** — `light` of `dark`.
  - **Gemaaid oppervlak weergeven** — arceert het al gemaaide gebied onder de padlijn.
  - **Elke afgeronde taak als 100 % voltooid behandelen** — sommige firmware beëindigt een afgeronde taak zonder voltooiingssignaal, waardoor de sessievoortgang nooit op 100 % springt terwijl het gazon wel klaar is (het leest als "afgebroken"). Zet dit aan om elke afgeronde taak als voltooid te behandelen, net als de app van de fabrikant; laat het uit om de eerlijke tellerwaarde te houden. *Standaard: uit.*
- Als het wachtwoord van het apparaat wijzigt, start Home Assistant automatisch een *herauthenticatie*-flow.

### Vereisten

- Home Assistant 2024.6.0 of nieuwer (de CI valideert tegen de huidige HA Core-release)
- TerraMow-firmwareversie 6.6.0 of nieuwer
- TerraMow-APP-versie 1.6.0 of nieuwer
- Live kaart en maaipad vereisen firmware HA-moduleversie 3; op versie 2 (bijv. S800) werkt al het andere, en de sensor voor versiecompatibiliteit meldt dat

### Ondersteunde apparaten

Deze integratie werkt met TerraMow-robotmaaiers die de lokale MQTT/HTTP-interface aanbieden — dus elk model met de vereiste firmware. Ze wordt gebruikt met de TerraMow S-serie, waaronder de **S800** (die firmware HA-moduleversie 2 meldt) en nieuwere exemplaren met versie 3. Elke TerraMow-maaier met firmware 6.6.0+ en app 1.6.0+ zou moeten werken; de sensor voor versiecompatibiliteit en een reparatiemelding geven aan of de firmware van een specifiek exemplaar te oud is voor een bepaalde functie.

### Services

#### `terramow.start_select_region`

Start het maaien voor een lijst met geselecteerde subgebieden.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Schrijf of verwijder een wekelijks maaivenster op de maaier. Elke schrijfactie
wordt bevestigd tegen het apparaat (dp_119-bevestiging plus het teruglezen van
het schema).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` verwacht de `item_id` van het venster (wordt weergegeven als
de uid van de agendagebeurtenis en teruggegeven wanneer een venster wordt
toegevoegd).

> **Let op:** de huidige winkelfirmware accepteert schemawijzigingen via lokale
> MQTT nog niet (de app van de fabrikant gebruikt Bluetooth/cloud). Gebruik tot
> die tijd de **blueprint voor weersafhankelijk maaien** voor planning aan de
> HA-kant.

### Interactieve kaartkaart

De integratie levert haar eigen Lovelace-kaart mee — automatisch geregistreerd, geen handmatige resource of aparte HACS-frontend-installatie nodig:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

De kaart tekent het gazon als vectoren (scherp bij elke zoom, volgt je HA-thema): zones, verboden zones, virtuele wanden, het maaipad, het basisstation en de live positie van de robot. Slepen om te pannen, scrollen of knijpen om te zoomen, dubbeltikken om opnieuw in te passen. **Tik op een of meer zones** en druk op de knop die verschijnt om precies die zones te maaien (achter de schermen `terramow.start_select_region`).

Een **weergaveknop** wisselt wat de kaart over het gazon legt:

| Modus | Toont |
| --- | --- |
| **Beide** | gemaaid oppervlak *en* het maaipad (standaard als de oppervlakweergave aan staat) |
| **Pad** | alleen het pad van de huidige en de vorige taak |
| **Oppervlak** | alleen de arcering van het gemaaide oppervlak, met voortgang per zone |
| **Wifi** | een **wifi-heatmap** van het gazon, door de maaier zelf gemeten tijdens het maaien (groen = sterk). Gaten tussen maaibanen worden geïnterpoleerd uit naburige metingen; grond waar de maaier nooit is geweest blijft leeg |

De gekozen modus wordt per entiteit in de browser onthouden. Opties en details: zie de [dashboardgids](en/dashboard.md#interactive-map-card) (Engels). Live kaartgegevens vereisen firmware HA-moduleversie 3 (net als de kaartcamera). De kaart is ook beschikbaar in de kaartkiezer van het dashboard als **TerraMow Map Card**, met een volledige UI-editor — geen YAML nodig.

### Dashboardvoorbeeld

Een kant-en-klare Lovelace-weergave (live kaart, bediening, voortgangsmeter, statusoverzicht) plus meldingsautomatiseringen: zie de [dashboardgids](en/dashboard.md) (Engels).

### Automatiserings-blueprints

Met één klik importeerbare blueprints voor de meest voorkomende meldingen — elk vraagt alleen om de betreffende TerraMow-entiteit en een meldingsactie:

- **Weersafhankelijk maaien** — start het maaien volgens je schema en sla het automatisch over als regen wordt gedetecteerd of voorspeld
  [![Blueprint importeren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Probleemmelding** — wanneer de maaier een storing meldt
  [![Blueprint importeren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Teruggekeerd door regen** — wanneer de maaier door regen naar het dock gaat
  [![Blueprint importeren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Maaien voltooid** — wanneer een maaitaak afgerond is
  [![Blueprint importeren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**De gebeurtenisentiteit direct gebruiken** — de maaier-gebeurtenisentiteit is de meest flexibele trigger. Het attribuut `event_type` is een van `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, en de entiteit draagt de ruwe velden `mission`, `sub_mission`, `state`, `back_to_station_reason` en `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow is klaar met maaien 🌱"
```

### Reparatiemeldingen

De integratie maakt bruikbare Home Assistant-reparatiemeldingen aan (Instellingen → Apparaten & diensten → Reparaties) in plaats van problemen in sensoren te verstoppen:

- **Firmware incompatibel / update vereist** — de firmware is te oud voor de integratie (of voor een specifieke functie). Afgeleid uit de versiecompatibiliteitscontrole; verdwijnt zodra een compatibele firmware zich meldt.
- **Onderhoud mes vereist** — de messchijf heeft het aanbevolen serviceinterval van 240 uur bereikt. Maak de messen schoon of vervang ze en druk op de knop *Mestimer resetten* om de melding te wissen.
- **Onderhoud basisstation vereist** — het basisstation heeft het aanbevolen serviceinterval van 30 dagen bereikt. Maak het schoon en druk op de knop *Basisstationtimer resetten* om de melding te wissen.

### Diagnostiek & probleemoplossing

- **Diagnostiek downloaden**: Instellingen → Apparaten & diensten → TerraMow → menu met drie puntjes → *Diagnostiek downloaden* maakt een geschoonde JSON-momentopname (apparaatstatus, firmwarecompatibiliteit, ruwe datapunt-caches) — voeg die toe aan bugrapporten.
- **Niet-ondersteunde functies ontdekken**: de maaier publiceert meer datapunten dan er gedocumenteerd zijn. De eerste payload van elk onbekend datapunt wordt eenmalig op INFO-niveau gelogd; schakel debug-logging in voor de `terramow`-integratie om ze allemaal vast te leggen. Vind je een datapunt voor een ontbrekende functie (bijv. optil-alarm, schemaschakelaar, foutcodes), deel het dan in een issue.

### Hoe gegevens worden bijgewerkt

TerraMow is een **local push**-integratie. De maaier draait een MQTT-broker op het apparaat; Home Assistant verbindt daar direct mee via het LAN (geen cloud) en abonneert zich op de datapunt-topics van het apparaat, zodat entiteitsstatussen bijwerken op het moment dat de maaier een wijziging meldt, in plaats van op een polling-interval. Grotere payloads (de kaart, het live pad) worden via MQTT aangekondigd en op aanvraag via lokale HTTP opgehaald. Als de maaier in slaapstand is of niet in het netwerk zit, wordt de verbinding opnieuw geprobeerd met exponentiële backoff, en toont de grasmaaier-entiteit het verbindingsverlies als activiteit `error`.

**Opdrachten falen hoorbaar, niet stil.** Wanneer je een opdracht verstuurt — `dock`, `start_mowing`, `pause`, kantenmaaien, zone-maaien of een instellingswijziging — wordt die gepubliceerd met MQTT QoS 1 (een korte herverbinding buffert de opdracht dus in plaats van hem te laten vallen). Als de maaier offline of onbereikbaar is, de broker de publicatie afwijst, of een opdracht sneller komt dan het apparaat hem kan verwerken, **faalt de serviceaanroep met een fout** in plaats van stil succes te melden. Een automatisering die `lawn_mower.dock` aanroept terwijl de maaier onbereikbaar is, ziet dus het falen (en kan het opnieuw proberen of een melding sturen) in plaats van te denken dat de maaier op de terugweg is terwijl hij de opdracht nooit ontving.

### Bekende beperkingen

- **Geen cloud / toegang op afstand** — Home Assistant moet in hetzelfde LAN als de maaier zitten; er is geen cloud-terugvaloptie.
- **Firmware-afhankelijke functies** — de live kaart en de maaipadweergave vereisen firmware HA-moduleversie 3; op versie 2 (bijv. de S800) werkt al het andere, en de compatibiliteitssensor / reparatiemelding rapporteert de beperking.
- **Firmware-updates** gebeuren via de TerraMow-app, niet vanuit Home Assistant; de firmware-`update`-entiteit is alleen informatief.
- **De positiesensor en de schone kaartcamera zijn standaard uitgeschakeld** (de positiesensor werkt bij met ongeveer 2 Hz); schakel ze in via de entiteitsinstellingen als je ze nodig hebt.
- **Veel entiteiten voor geavanceerde diagnostiek zijn standaard uitgeschakeld** en gegroepeerd onder de categorie *Diagnostisch* (mobiel, zonsopkomst/zonsondergang, bedrijfsmodi, vlaggen voor handmatig karteren, enz.); ze komen uit gereverse-engineerde datapunten, dus schakel alleen in wat je nodig hebt. Zie de [notities over onofficiële datapunten](en/developers/data_point_unofficial.md).
- Sommige datapunten van het apparaat zijn niet gedocumenteerd; onbekende worden eenmalig gelogd om ontbrekende functies te helpen ontdekken.

### Toepassingen

- **Regenbewuste meldingen** — krijg een pushbericht wanneer de maaier door regen naar het dockstation terugkeert (zie de blueprints hierboven).
- **Storingsalarmen** — word gewaarschuwd op het moment dat de maaier een probleem meldt (vastgelopen, opgetild, geblokkeerd).
- **Zone-maaien uit automatiseringen** — roep `terramow.start_select_region` aan om specifieke subgebieden volgens schema of via een dashboardknop te maaien.
- **Onderhoudsherinneringen** — de sensoren voor resterende tijd van mes / basisstation en de resetknoppen maken geautomatiseerde onderhoudsherinneringen mogelijk.
- **Live kaart op een dashboard** — toon de kaartcamera met de robotpositie en het maaipad (zie de dashboardgids).

### Talen

De integratie is vertaald in: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Upgrade-opmerkingen

- **v0.5.0**: statuswaarden van entiteiten zijn van hoofdletters naar kleine letters gewijzigd (bijv. `MISSION_IDLE` → `mission_idle`) om aan de vertaalvereisten van Home Assistant te voldoen. Automatiseringen of templates die ruwe statusstrings vergelijken hebben een eenmalige aanpassing nodig; weergegeven namen blijven ongewijzigd.

### Ondersteuning

Open voor ondersteuning een issue op [GitHub](https://github.com/it-rec/TerraMowHA/issues).

### Informatie voor ontwikkelaars

Voor ontwikkelaars die deze integratie willen begrijpen of uitbreiden (de ontwikkelaarsdocumentatie is in het Engels):

- [Bijdragegids](../CONTRIBUTING.md) — opzet, kwaliteitseisen (100 % dekking, `mypy --strict`, vertalingen), PR- en releaseproces
- [Architectuur](ARCHITECTURE.md) — de interne werking: hub-levenscyclus, uitvoeringsmodel, datapunt-catalogus, kaart-/padpijplijn
- [Ontwikkelaarsgids](en/developers.md) — het MQTT/HTTP-apparaatprotocol op de lijn
- [Wat deze fork toevoegt ten opzichte van upstream](UPSTREAM_DELTA.md)

De testsuite lokaal uitvoeren:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Licentie

Dit project is gelicentieerd onder de GNU General Public License v3.0 — zie het bestand [LICENSE](../LICENSE) voor details.
