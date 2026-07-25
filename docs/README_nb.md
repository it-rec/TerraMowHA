# TerraMow for Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · **Norsk (bokmål)** · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Dette er en Home Assistant-integrasjon for TerraMow robotgressklippere.

### Funksjoner

**Styring**
- Gressklipperentitet: start, pause og retur til ladestasjonen
- Soneklipping: soneutvalgsentitet og tjenesten `terramow.start_select_region`
- **Redigering av tidsplan** — tjenestene `terramow.add_schedule` / `terramow.delete_schedule` skriver ukentlige klippevinduer til klipperen og verifiserer dem ved tilbakelesing. *Merk:* dagens butikkfastvare godtar ennå ikke skriving av tidsplan over lokal MQTT (produsentens app bruker Bluetooth/sky) — bruk til da **oppskriften for væravhengig klipping** for planlegging på HA-siden
- **Interaktivt kartkort** — vektorkart over plenen med panorering og zoom for dashbord: robotens posisjon i sanntid (farget etter aktivitet, med følgemodus), knapper for start / pause / stasjon rett på kortet, brikker for batteri / framdrift / gjenstående tid, skyggelegging av klippet areal med framdrift per sone, klippespor, basestasjon, soner med trykkvalg for klipping, forbudte soner og virtuelle vegger, aktive feil markert der de oppsto, samt et **Wi-Fi-varmekart** over plenen; en **visningsknapp** veksler mellom Begge / Spor / Areal / Wi-Fi. Temabevisst, registrerer seg selv, med et grensesnittredigeringsverktøy (`custom:terramow-map-card`)
- Knapp for kantklipping
- Innstillinger fra Home Assistant: klippehøyde, hastighet, baneavstand, knivhastighet, kantklippeavstand, hovedretningsmodus og -vinkler, grundig hjørneklipping, kantklippemodus for høyt gress
- Vedlikehold: nullstillingsknapper for tellerne til knivskiven og basestasjonen

**Overvåking**
- Kartkamera i sanntid med klippespor, robotposisjon og basestasjon (pluss et rent kamera med bare kart for dashbord, oppløsning konfigurerbar i alternativene)
- Batteri: nivå, ladestatus, temperaturstatus, lader tilkoblet, strømbryter
- Framdrift: areal for gjeldende økt, framdrift (%), varighet og jobbtype; total klippetid, antall jobber og klippet areal
- Status: oppdrag / underoppdrag / oppdragsstatus, driftsmodus, strømmodus, årsak til retur til stasjonen, regnregistrering, problemindikator, indikatorer for datalagring og datakonvertering
- **Feilsensor** — den aktive feilen som lesbar tekst (f.eks. *Klipperen har satt seg fast*, *Klipperen er løftet* eller *OK*), slik at et varsel eller en taleassistent kan si hva som er galt uten å behandle et attributt med en mal
- Sensor for pågående jobb (holder det aktive oppdraget også ved brudd i nærværssignalet) og en sensor for klipperens Wi-Fi-signalstyrke
- Kart: status, areal, flagg for oppdaget / byggbart / sikkerhetskopiering pågår
- Tidsplan: sensor for neste planlagte start og en **kalender for klippetidsplanen** som bare kan leses (neste klipping vises på kalenderkortet)
- Entitet for fastvareoppdatering, fastvareversjon på enhetssiden og sensor for versjonskompatibilitet
- Alle entiteter oppdateres umiddelbart ved utsendinger fra enheten — ingen pollingforsinkelse

**Avansert diagnostikk** (datapunkter framskaffet ved omvendt utvikling — for det meste i entitetskategorien *Diagnostikk*, mange avslått som standard; se [notatene om uoffisielle datapunkter](en/developers/data_point_unofficial.md))
- Feil og hendelser: antall aktive feil (med den rå feillisten som attributt) og kode for siste hendelse. Kjente feilkoder oversettes til lesbar tekst via en katalog bygget av fellesskapet (`error_codes.py`), som også dekoder klipperens nyeste feilkode (dp_115)
- Mobilnett / 4G: modem aktivert, signalstyrke (RSRP / RSRQ), tilkoblingstype og en avlesning av *tving mobilnett*
- Miljø: soloppgang / solnedgang som enheten rapporterer, dagslysstatus, dugghindrende varme, belysning og et varsel om ekstremvær (med valgfri info-URL)
- Sikkerhet og avanserte innstillinger: status for nivåforskjells- og helningsregistrering, terskelverdi for regnsensoren, automatisk fortsettelse etter regn og forsinkelsen for dette, samt en avlesning av *tving én basestasjon*
- Driftsmoduser: strenger for bevegelses- / kart- / klippemodus
- Kartlegging og framdrift: veiledningsflagg for manuell kartlegging (reposisjonering / overtakelse nødvendig, grense lukket) og en prosentsats for framdriften i kartlagringen

**Hendelser og automasjoner**
- **Hendelsesentitet for klipperen** — utløser en egen hendelse ved hver betydelige overgang (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), hver med de rå oppdragsfeltene, slik at automasjoner reagerer på *hendelser* uten å polle aktivitetsstatusen
- Automasjonsoppskrifter som importeres med ett klikk (se nedenfor)

**Bekvemmeligheter i integrasjonen**
- Automatisk oppdagelse via Zeroconf/mDNS
- Rekonfigureringsflyt (bytt vert/IP uten å legge til på nytt) og reautentiseringsflyt
- **Reparasjonssaker** — handlingsrettede dashbordkort for inkompatibel fastvare og for forfalt vedlikehold av kniv / basestasjon
- Nedlasting av diagnostikk for enklere feilrapporter
- Oversatt til 33 språk (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Bekreftede kommandoer** — soneklipping venter på enhetens dp_119-bekreftelse og rapporterer avvisninger i stedet for å "lykkes" stille
- Lokal push-kommunikasjon over MQTT — ingen sky nødvendig

### Støttede entiteter

| Plattform | Entiteter |
| --- | --- |
| Gressklipper | Styring for start / pause / stasjon med aktivitet i sanntid |
| Kamera | Kart med spor, robot og basestasjon; ren variant med bare kart |
| Sensor | Batterinivå, batteristatus, batteriets temperaturstatus, kartstatus, kartareal, klippehøyde, klippehastighet, driftsmodus, posisjon, total klippetid / jobber / klippet areal, areal / framdrift / varighet / jobbtype for gjeldende økt, pågående jobb, feil, gjenstående tid for kniv og basestasjon, neste planlagte start, versjonskompatibilitet, status for hovedretning, strømmodus, årsak til retur til stasjonen, oppdrag, underoppdrag, oppdragsstatus. *Diagnostikk:* aktive feil, siste hendelse, Wi-Fi-signal, mobilnett RSRP / RSRQ / type, soloppgang, solnedgang, bevegelses- / kart- / klippemodus, terskelverdi for regnsensoren, forsinkelse for fortsettelse etter regn, framdrift i kartlagring |
| Binær sensor | Lader, navigasjon lokalisert, fastvareoppdatering pågår, strømbryter, problem, regn registrert, kart oppdaget / byggbart / sikkerhetskopiering pågår, lagrer data, datakonvertering pågår. *Diagnostikk:* mobilnett aktivert, dugghindrende varme, belysning, dagslys, ekstremvær, nivåforskjells- / helningsregistrering, automatisk fortsettelse etter regn, tving én basestasjon, tving mobilnett, manuell kartlegging reposisjonering / overtakelse / grense lukket, statusflagg 134 (udekodet) |
| Valg | Sonevalg, klippehastighet, knivhastighet, hovedretningsmodus, kantklippemodus for høyt gress |
| Tall | Klippehøyde, kantklippeavstand, baneavstand, vinkel for enkeltretning, intervall for automatisk vinkelrotasjon, vinkel for første / andre retning |
| Bryter | Grundig hjørneklipping |
| Knapp | Kantklipping, nullstill knivtimer, nullstill basestasjonstimer |
| Oppdatering | Fastvareversjon |
| Hendelse | Klipperhendelse (klipping startet / satt på pause / returnerer / ved stasjonen / fullført / feil) |
| Kalender | Klippetidsplan (neste planlagte klipping) |

### Installasjon

[![Åpne din Home Assistant-instans og åpne et repositorium i Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Metode 1: HACS (anbefalt)
1. Sørg for at [HACS](https://hacs.xyz/) er installert
2. Bruk knappen over for å legge integrasjonen til HACS
3. Åpne HACS, søk etter «TerraMow» og velg integrasjonen
4. Installer den og start Home Assistant på nytt

#### Metode 2: Manuell installasjon
1. Kopier mappen `custom_components/terramow` til mappen `/config/custom_components` i din Home Assistant
2. Start Home Assistant på nytt
3. Gå til Innstillinger → Enheter og tjenester → Legg til integrasjon
4. Søk etter «TerraMow» og følg konfigurasjonstrinnene

### Konfigurasjon

Enheter i det lokale nettverket oppdages automatisk via Zeroconf — godta den oppdagede enheten og skriv inn MQTT-passordet. For manuell oppsett kreves følgende parametere:

- **Vert**: IP-adresse eller vertsnavn for TerraMow-enheten
- **Passord**: MQTT-passord for autentisering

**Endre innstillinger senere**
- *Rekonfigurer* (Innstillinger → Enheter og tjenester → TerraMow → Rekonfigurer): bytt vert/IP eller passord på stedet, f.eks. etter at klipperen har fått en ny DHCP-adresse — integrasjonen behøver ikke fjernes og legges til igjen.
- *Alternativer* (Konfigurer):
  - **Kartets utdataoppløsning** — høyere er skarpere, men koster mer båndbredde og prosessorkraft per gjengivelse.
  - **Karttema** — `light` eller `dark`.
  - **Vis klippet areal** — skyggelegger det allerede klippede området under sporlinjen.
  - **Behandle enhver fullført jobb som 100 % ferdig** — noe fastvare avslutter en jobb uten å sende et fullføringssignal, så øktens framdrift kommer aldri til 100 % selv om plenen er ferdig (den leses som «avbrutt»). Slå på dette for å behandle enhver fullført jobb som ferdig, slik produsentens app gjør; la det stå av for å beholde tellerens ærlige verdi. *Standard: av.*
- Hvis enhetens passord endres, starter Home Assistant automatisk en *reautentiseringsflyt*.

### Krav

- Home Assistant 2024.6.0 eller nyere (CI validerer mot gjeldende HA Core-utgivelse)
- TerraMow-fastvare versjon 6.6.0 eller nyere
- TerraMow-appen versjon 1.6.0 eller nyere
- Kart i sanntid og klippespor krever fastvarens HA-modulversjon 3; på versjon 2 (f.eks. S800) fungerer alt annet, og sensoren for versjonskompatibilitet rapporterer det

### Støttede enheter

Denne integrasjonen fungerer med TerraMow robotgressklippere som tilbyr det lokale MQTT/HTTP-grensesnittet — altså enhver modell med den nødvendige fastvaren. Den brukes med TerraMows S-serie, inkludert **S800** (som rapporterer fastvarens HA-modulversjon 2) og nyere enheter med versjon 3. Enhver TerraMow-klipper med fastvare 6.6.0+ og app 1.6.0+ bør fungere; sensoren for versjonskompatibilitet og en reparasjonssak viser om fastvaren på en bestemt enhet er for gammel for en gitt funksjon.

### Tjenester

#### `terramow.start_select_region`

Starter klipping for en liste med valgte delområder.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Oppretter eller fjerner et ukentlig klippevindu i klipperen. Hver skriving
bekreftes mot enheten (dp_119-bekreftelse pluss en tilbakelesing av tidsplanen).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` tar vinduets `item_id` (vises som kalenderhendelsens uid og
returneres når et vindu legges til).

> **Merk:** dagens butikkfastvare godtar ennå ikke skriving av tidsplan over
> lokal MQTT (produsentens app bruker Bluetooth/sky). Bruk til da **oppskriften
> for væravhengig klipping** for planlegging på HA-siden.

### Interaktivt kartkort

Integrasjonen leverer sitt eget Lovelace-kort — registreres automatisk, ingen manuell ressurs og ingen separat installasjon av HACS-frontend:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Det tegner plenen som vektorer (skarpt ved all zoom, følger ditt HA-tema): soner, forbudte soner, virtuelle vegger, klippesporet, basestasjonen og robotens posisjon i sanntid. Dra for å panorere, rull eller knip for å zoome, dobbelttrykk for å tilpasse på nytt. **Trykk på én eller flere soner** og trykk på knappen som vises for å klippe nøyaktig disse sonene (`terramow.start_select_region` under panseret).

En **visningsknapp** veksler hva kortet legger over plenen:

| Modus | Viser |
| --- | --- |
| **Begge** | det klippede arealet *og* klippesporet (standard når arealet er slått på) |
| **Spor** | bare sporet for gjeldende og forrige jobb |
| **Areal** | bare skyggeleggingen av det klippede arealet, med framdrift per sone |
| **Wi-Fi** | et **Wi-Fi-varmekart** over plenen, målt av klipperen selv mens den klipper (grønt = sterkt). Hull mellom klippedrag interpoleres fra nærliggende målinger; grunn klipperen aldri har kjørt over, blir stående tom |

Den valgte modusen huskes per entitet i nettleseren. Alternativer og detaljer: se [dashbordveiledningen](en/dashboard.md#interactive-map-card) (på engelsk). Kartdata i sanntid krever fastvarens HA-modulversjon 3 (samme som kartkameraet). Kortet finnes også i dashbordets kortvelger som **TerraMow Map Card**, med et fullstendig grensesnittredigeringsverktøy — ingen YAML nødvendig.

### Dashbordeksempel

En ferdig Lovelace-visning (kart i sanntid, styring, framdriftsmåler, statusoversikt) pluss varselautomasjoner: se [dashbordveiledningen](en/dashboard.md) (på engelsk).

### Automasjonsoppskrifter

Oppskrifter som importeres med ett klikk for de vanligste varslene — hver spør bare etter den aktuelle TerraMow-entiteten og en varselhandling:

- **Væravhengig klipping** — starter klippingen etter tidsplanen din og hopper automatisk over den når regn registreres eller varsles
  [![Importer oppskrift](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Problemvarsel** — når klipperen rapporterer en feil
  [![Importer oppskrift](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Returnerte på grunn av regn** — når klipperen går til stasjonen på grunn av regn
  [![Importer oppskrift](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Klipping ferdig** — når en klippejobb avsluttes
  [![Importer oppskrift](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Bruke hendelsesentiteten direkte** — klipperens hendelsesentitet er den mest fleksible utløseren. Attributtet `event_type` er én av `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, og entiteten bærer de rå feltene `mission`, `sub_mission`, `state`, `back_to_station_reason` og `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow er ferdig med klippingen 🌱"
```

### Reparasjonssaker

Integrasjonen oppretter handlingsrettede reparasjonssaker i Home Assistant (Innstillinger → Enheter og tjenester → Reparasjoner) i stedet for å skjule problemer i sensorer:

- **Fastvare inkompatibel / oppdatering påkrevd** — fastvaren er for gammel for integrasjonen (eller for en bestemt funksjon). Utledes fra kontrollen av versjonskompatibilitet; forsvinner når en kompatibel fastvare melder seg.
- **Knivvedlikehold forfalt** — knivskiven har nådd sitt anbefalte serviceintervall på 240 timer. Rengjør eller bytt knivene og trykk på knappen *Nullstill knivtimer* for å fjerne saken.
- **Vedlikehold av basestasjonen forfalt** — basestasjonen har nådd sitt anbefalte serviceintervall på 30 dager. Rengjør den og trykk på knappen *Nullstill basestasjonstimer* for å fjerne saken.

### Diagnostikk og feilsøking

- **Nedlasting av diagnostikk**: Innstillinger → Enheter og tjenester → TerraMow → trepunktsmenyen → *Last ned diagnostikk* lager et renset JSON-øyeblikksbilde (enhetens status, fastvarekompatibilitet, rå datapunktcacher) — legg det ved feilrapporter.
- **Oppdage funksjoner som ikke støttes**: klipperen publiserer flere datapunkter enn det som er dokumentert. Den første nyttelasten for hvert ukjente datapunkt logges én gang på INFO-nivå; slå på feilsøkingslogging for integrasjonen `terramow` for å ta opp alle. Finner du et datapunkt for en manglende funksjon (f.eks. løftealarm, tidsplanbryter, feilkoder), del det i en sak.

### Slik oppdateres data

TerraMow er en **local push**-integrasjon. Klipperen kjører en MQTT-megler på enheten; Home Assistant kobler seg direkte til den over det lokale nettverket (uten sky) og abonnerer på enhetens datapunktemner, så entitetenes status oppdateres i samme øyeblikk som klipperen melder en endring, og ikke etter et pollingintervall. Større nyttelaster (kartet, sporet i sanntid) annonseres over MQTT og hentes ved behov over lokal HTTP. Hvis klipperen sover eller er utenfor nettverket, gjøres nye tilkoblingsforsøk med eksponentiell forsinkelse, og gressklipperentiteten viser tapt forbindelse som sin `error`-aktivitet.

**Kommandoer feiler høylytt, ikke stille.** Når du sender en kommando — `dock`, `start_mowing`, `pause`, kantklipping, soneklipping eller en innstillingsendring — publiseres den med MQTT QoS 1 (en kort gjenoppkobling bufrer den altså i stedet for å forkaste den). Hvis klipperen er offline eller uten forbindelse, hvis megleren avviser publiseringen, eller hvis en kommando kommer raskere enn enheten kan ta imot den, **feiler tjenestekallet med en feil** i stedet for å melde stille suksess. En automasjon som kaller `lawn_mower.dock` mens klipperen er uten forbindelse, ser dermed feilen (og kan prøve igjen eller varsle) i stedet for å tro at klipperen er på vei tilbake når den aldri fikk kommandoen.

### Kjente begrensninger

- **Ingen sky- / fjerntilgang** — Home Assistant må være i samme lokale nettverk som klipperen; det finnes ingen reserveløsning via skyen.
- **Fastvareavhengige funksjoner** — kartet i sanntid og klippesporvisningen krever HA-modulversjon 3; på versjon 2 (f.eks. S800) fungerer alt annet, og kompatibilitetssensoren / reparasjonssaken melder om begrensningen.
- **Fastvareoppdateringer** gjøres via TerraMow-appen, ikke fra Home Assistant; fastvarens `update`-entitet er bare informativ.
- **Posisjonssensoren og det rene kartkameraet er avslått som standard** (posisjonssensoren oppdateres med cirka 2 Hz); slå dem på i entitetsinnstillingene hvis du trenger dem.
- **Mange entiteter for avansert diagnostikk er avslått som standard** og gruppert under kategorien *Diagnostikk* (mobilnett, soloppgang/solnedgang, driftsmoduser, flagg for manuell kartlegging osv.); de kommer fra datapunkter framskaffet ved omvendt utvikling, så slå bare på dem du trenger. Se [notatene om uoffisielle datapunkter](en/developers/data_point_unofficial.md).
- Noen datapunkter i enheten er udokumenterte; ukjente logges én gang for å hjelpe til med å oppdage manglende funksjoner.

### Bruksområder

- **Regnbevisste varsler** — få et push-varsel når klipperen returnerer til stasjonen på grunn av regn (se oppskriftene over).
- **Feilvarsler** — bli varslet i samme øyeblikk som klipperen melder et problem (fastkjørt, løftet, blokkert).
- **Soneklipping fra automasjoner** — kall `terramow.start_select_region` for å klippe bestemte delområder etter en tidsplan eller fra en dashbordknapp.
- **Vedlikeholdspåminnelser** — sensorene for gjenstående tid for kniv / basestasjon og nullstillingsknappene gjør det mulig å automatisere vedlikeholdspåminnelser.
- **Kart i sanntid på et dashbord** — vis kartkameraet med robotens posisjon og klippesporet (se dashbordveiledningen).

### Språk

Integrasjonen er oversatt til: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Oppgraderingsmerknader

- **v0.5.0**: entitetenes statusverdier endret seg fra store til små bokstaver (f.eks. `MISSION_IDLE` → `mission_idle`) for å oppfylle Home Assistants oversettelseskrav. Automasjoner eller maler som sammenligner rå statusstrenger, trenger en engangsjustering; viste navn er uendret.

### Støtte

Åpne en sak på [GitHub](https://github.com/it-rec/TerraMowHA/issues) for støtte.

### Informasjon for utviklere

For utviklere som vil forstå eller utvide denne integrasjonen (utviklerdokumentasjonen er på engelsk):

- [Bidragsveiledning](../CONTRIBUTING.md) — oppsett, kvalitetskrav (100 % dekning, `mypy --strict`, oversettelser), PR- og utgivelsesprosess
- [Arkitektur](ARCHITECTURE.md) — integrasjonens indre deler: hubbens livsløp, utføringsmodell, datapunktkatalog, kart-/sporpipeline
- [Utviklerveiledning](en/developers.md) — enhetens MQTT/HTTP-protokoll slik den går over nettet
- [Hva denne forken legger til sammenlignet med upstream](UPSTREAM_DELTA.md)

Slik kjører du testene lokalt:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Lisens

Dette prosjektet er lisensiert under GNU General Public License v3.0 — se filen [LICENSE](../LICENSE) for detaljer.
