# TerraMow for Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · **Norsk (bokmål)** · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Dette er en Home Assistant-integrasjon for TerraMow robotgressklippere.

### Funksjoner

**Styring**
- Gressklipper-entitet: start, pause og dokking
- Soneklipping: entitet for sonevalg og tjenesten `terramow.start_select_region`
- Knapp for kantklipping
- Innstillinger fra Home Assistant: klippehøyde, hastighet, sporavstand, knivhastighet, kantklippingsavstand, hovedretningsmodus og -vinkler, grundig hjørneklipping, kantklippingsmodus for høyt gress
- Vedlikehold: tilbakestillingsknapper for tellerne for knivskiven og basestasjonen

**Overvåking**
- Live kartkamera med klipperute, robotens posisjon og basestasjon (pluss et rent kamera med bare kartet for dashbord, oppløsningen kan konfigureres via alternativene)
- Batteri: nivå, ladestatus, temperaturstatus, lader tilkoblet, strømbryter
- Arbeidsfremdrift: areal for gjeldende økt, fremdrift (%), varighet og jobbtype; total klippetid, antall jobber og klippet areal
- Status: oppdrag / deloppdrag / oppdragsstatus, driftsmodus, strømmodus, årsak til retur til stasjonen, regndeteksjon, problemindikator, indikatorer for datalagring og datakonvertering
- Kart: status, areal, flagg for oppdaget / kan bygges / sikkerhetskopieres
- Tidsplan: neste planlagte start
- Entitet for fastvareoppdatering, fastvareversjon på enhetssiden og sensor for versjonskompatibilitet
- Alle entiteter oppdateres umiddelbart ved push fra enheten — ingen polling-forsinkelse

**Praktiske integrasjonsfunksjoner**
- Automatisk oppdagelse via Zeroconf/mDNS
- Rekonfigurasjonsflyt (endre vert/IP uten å legge til på nytt) og reautentiseringsflyt
- Nedlasting av diagnostikk for enkle feilrapporter
- Oversatt til 33 språk (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- MQTT-basert lokal push-kommunikasjon — ingen sky kreves

### Støttede entiteter

| Plattform | Entiteter |
| --- | --- |
| Gressklipper | Styring av start / pause / dokking med live aktivitet |
| Kamera | Kart med rute, robot og basestasjon; ren variant med bare kartet |
| Sensor | Batterinivå, batteristatus, batteritemperaturstatus, kartstatus, kartareal, klippehøyde, klippehastighet, driftsmodus, posisjon, total klippetid / antall jobber / klippet areal, areal / fremdrift / varighet / jobbtype for gjeldende økt, gjenværende tid for kniv og basestasjon, neste planlagte start, versjonskompatibilitet, hovedretningsstatus, strømmodus, årsak til retur til stasjonen, oppdrag, deloppdrag, oppdragsstatus |
| Binærsensor | Lading, navigasjon lokalisert, fastvareoppgradering pågår, strømbryter, problem, regn oppdaget, kart oppdaget / kan bygges / sikkerhetskopieres, lagrer data, datakonvertering pågår |
| Valg | Sonevalg, klippehastighet, knivhastighet, hovedretningsmodus, kantklippingsmodus for høyt gress |
| Tall | Klippehøyde, kantklippingsavstand, sporavstand, vinkel for én retning, intervall for automatisk vinkelrotasjon, vinkel for første / andre retning |
| Bryter | Grundig hjørneklipping |
| Knapp | Kantklipping, tilbakestill knivtimer, tilbakestill basestasjonstimer |
| Oppdatering | Fastvareversjon |

### Installasjon

#### Metode 1: HACS (anbefalt)
1. Sørg for at [HACS](https://hacs.xyz/) er installert
2. Bruk knappen ovenfor for å legge til i HACS
3. Gå til HACS → Integrasjoner → + → Søk etter "TerraMow"
4. Installer og start Home Assistant på nytt

#### Metode 2: Manuell installasjon
1. Kopier mappen `custom_components/terramow` til Home Assistant-mappen `/config/custom_components`
2. Start Home Assistant på nytt
3. Gå til Innstillinger → Enheter og tjenester → Legg til integrasjon
4. Søk etter "TerraMow" og følg konfigurasjonstrinnene

### Konfigurasjon

Enheter på det lokale nettverket oppdages automatisk via Zeroconf — godta den oppdagede enheten og skriv inn MQTT-passordet. For manuelt oppsett kreves følgende parametere:

- **Vert**: IP-adresse eller vertsnavn for TerraMow-enheten
- **Passord**: MQTT-passord for autentisering

**Endre innstillinger senere**
- *Rekonfigurer* (Innstillinger → Enheter og tjenester → TerraMow → Rekonfigurer): endre vert/IP eller passord direkte, f.eks. etter at gressklipperen har fått en ny DHCP-adresse — du trenger ikke å fjerne integrasjonen og legge den til på nytt.
- *Alternativer* (Konfigurer): angi kartkameraets utdataoppløsning. Høyere verdier gir et skarpere dashbordbilde på bekostning av båndbredde og CPU per rendering.
- Hvis enhetens passord endres, starter Home Assistant automatisk en *reautentiserings*-flyt.

### Krav

- Home Assistant 2023.9.3 eller nyere (testet med 2025.1.1)
- TerraMow fastvareversjon 6.6.0 eller nyere
- TerraMow APP versjon 1.6.0 eller nyere
- Live kart og klipperute krever fastvare med HA-modul versjon 3; på versjon 2 (f.eks. S800) fungerer alt annet, og sensoren for versjonskompatibilitet rapporterer det

### Tjenester

#### `terramow.start_select_region`

Start klipping for en liste over valgte delområder.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

### Diagnostikk og feilsøking

- **Nedlasting av diagnostikk**: Innstillinger → Enheter og tjenester → TerraMow → menyen med tre prikker → *Last ned diagnostikk* genererer et anonymisert JSON-øyeblikksbilde (enhetsstatus, fastvarekompatibilitet, cacher med rå datapunkter) — legg det gjerne ved feilrapporter.
- **Oppdage funksjoner som ikke støttes**: gressklipperen publiserer flere datapunkter enn det som er dokumentert. Den første payloaden for hvert ukjent datapunkt logges én gang på INFO-nivå; aktiver feilsøkingslogging for `terramow`-integrasjonen for å registrere alle. Hvis du finner et datapunkt for en manglende funksjon (f.eks. løftealarm, tidsplanbryter, feilkoder), del det gjerne i et issue.

### Språk

Integrasjonen er oversatt til: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Oppgraderingsnotater

- **v0.5.0**: entitetenes tilstandsverdier ble endret fra store til små bokstaver (f.eks. `MISSION_IDLE` → `mission_idle`) for å oppfylle Home Assistants oversettelseskrav. Automatiseringer eller maler som sammenligner rå tilstandsstrenger, trenger en engangsoppdatering; viste navn er uendret.

### Støtte

Opprett et issue på [GitHub](https://github.com/TerraMow/TerraMowHA/issues) for å få støtte.

### Utviklerinformasjon

Utviklere som er interessert i å forstå eller utvide denne integrasjonen, henvises til [utviklerguiden](en/developers.md).

Slik kjører du testpakken lokalt:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Lisens

Dette prosjektet er lisensiert under GNU General Public License v3.0 — se filen [LICENSE](../LICENSE) for detaljer.
