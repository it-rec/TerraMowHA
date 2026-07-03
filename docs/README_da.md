# TerraMow til Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · **Dansk** · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Dette er en Home Assistant-integration til TerraMow robotplæneklippere.

### Funktioner

**Styring**
- Plæneklipper-entitet: start, pause og dock
- Zoneklipning: entitet til zonevalg og tjenesten `terramow.start_select_region`
- Knap til kantklipning
- Indstillinger fra Home Assistant: klippehøjde, hastighed, baneafstand, knivhastighed, kantklipningsafstand, hovedretningstilstand og -vinkler, grundig hjørneklipning, kantklipningstilstand til højt græs
- Vedligeholdelse: nulstillingsknapper til tællerne for knivskiven og basestationen

**Overvågning**
- Live-kortkamera med klipperute, robottens position og basestation (plus et rent kamera kun med kortet til dashboards, opløsningen kan konfigureres via indstillingerne)
- Batteri: niveau, opladningsstatus, temperaturstatus, oplader tilsluttet, tænd/sluk-kontakt
- Arbejdsfremskridt: areal for den aktuelle session, fremskridt (%), varighed og opgavetype; samlet klippetid, antal opgaver og klippet areal
- Status: mission / delmission / missionsstatus, driftstilstand, strømtilstand, årsag til returnering til stationen, regnregistrering, problemindikator, indikatorer for datalagring og datakonvertering
- Kort: status, areal, flag for registreret / kan opbygges / sikkerhedskopieres
- Tidsplan: næste planlagte start
- Firmwareopdaterings-entitet, firmwareversion på enhedssiden og sensor for versionskompatibilitet
- Alle entiteter opdateres øjeblikkeligt ved push fra enheden — ingen polling-forsinkelse

**Praktiske integrationsfunktioner**
- Automatisk registrering via Zeroconf/mDNS
- Rekonfigurationsflow (skift vært/IP uden at tilføje igen) og genautentificeringsflow
- Download af diagnostik til nemme fejlrapporter
- Oversat til 14 sprog (en, cs, da, de, es, fi, fr, it, nb, nl, pl, pt, sv, zh-Hans)
- Lokal push-kommunikation baseret på MQTT — ingen cloud påkrævet

### Understøttede entiteter

| Platform | Entiteter |
| --- | --- |
| Plæneklipper | Styring af start / pause / dock med live-aktivitet |
| Kamera | Kort med rute, robot og basestation; ren variant kun med kortet |
| Sensor | Batteriniveau, batteristatus, batteritemperaturstatus, kortstatus, kortareal, klippehøjde, klippehastighed, driftstilstand, position, samlet klippetid / antal opgaver / klippet areal, areal / fremskridt / varighed / opgavetype for den aktuelle session, resterende tid for kniv og basestation, næste planlagte start, versionskompatibilitet, hovedretningsstatus, strømtilstand, årsag til returnering til stationen, mission, delmission, missionsstatus |
| Binær sensor | Opladning, navigation lokaliseret, firmwareopgradering i gang, tænd/sluk-kontakt, problem, regn registreret, kort registreret / kan opbygges / sikkerhedskopieres, gemmer data, datakonvertering i gang |
| Valg | Zonevalg, klippehastighed, knivhastighed, hovedretningstilstand, kantklipningstilstand til højt græs |
| Tal | Klippehøjde, kantklipningsafstand, baneafstand, vinkel for enkelt retning, interval for automatisk vinkelrotation, vinkel for første / anden retning |
| Kontakt | Grundig hjørneklipning |
| Knap | Kantklipning, nulstil knivtimer, nulstil basestationstimer |
| Opdatering | Firmwareversion |

### Installation

#### Metode 1: HACS (anbefales)
1. Sørg for, at [HACS](https://hacs.xyz/) er installeret
2. Brug knappen ovenfor til at tilføje til HACS
3. Gå til HACS → Integrationer → + → Søg efter "TerraMow"
4. Installer og genstart Home Assistant

#### Metode 2: Manuel installation
1. Kopiér mappen `custom_components/terramow` til din Home Assistant-mappe `/config/custom_components`
2. Genstart Home Assistant
3. Gå til Indstillinger → Enheder og tjenester → Tilføj integration
4. Søg efter "TerraMow" og følg konfigurationstrinnene

### Konfiguration

Enheder på det lokale netværk registreres automatisk via Zeroconf — acceptér den fundne enhed og indtast MQTT-adgangskoden. Til manuel opsætning kræves følgende parametre:

- **Vært**: IP-adresse eller værtsnavn for TerraMow-enheden
- **Adgangskode**: MQTT-adgangskode til godkendelse

**Ændring af indstillinger senere**
- *Rekonfigurer* (Indstillinger → Enheder og tjenester → TerraMow → Rekonfigurer): skift vært/IP eller adgangskode direkte, f.eks. efter at plæneklipperen har fået en ny DHCP-adresse — det er ikke nødvendigt at fjerne integrationen og tilføje den igen.
- *Indstillinger* (Konfigurer): angiv kortkameraets outputopløsning. Højere værdier giver et skarpere dashboard-billede på bekostning af båndbredde og CPU pr. rendering.
- Hvis enhedens adgangskode ændres, starter Home Assistant automatisk et *genautentificerings*-flow.

### Krav

- Home Assistant 2023.9.3 eller nyere (testet med 2025.1.1)
- TerraMow firmwareversion 6.6.0 eller nyere
- TerraMow APP version 1.6.0 eller nyere
- Live-kort og klipperute kræver firmware med HA-modul version 3; på version 2 (f.eks. S800) fungerer alt andet, og sensoren for versionskompatibilitet rapporterer det

### Tjenester

#### `terramow.start_select_region`

Start klipning for en liste over valgte delområder.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

### Diagnostik og fejlfinding

- **Download af diagnostik**: Indstillinger → Enheder og tjenester → TerraMow → menuen med tre prikker → *Download diagnostik* genererer et anonymiseret JSON-øjebliksbillede (enhedsstatus, firmwarekompatibilitet, caches med rå datapunkter) — vedhæft det venligst til fejlrapporter.
- **Opdagelse af ikke-understøttede funktioner**: plæneklipperen udgiver flere datapunkter, end der er dokumenteret. Den første payload for hvert ukendt datapunkt logges én gang på INFO-niveau; aktivér debug-logning for `terramow`-integrationen for at registrere dem alle. Hvis du finder et datapunkt for en manglende funktion (f.eks. løftealarm, tidsplankontakt, fejlkoder), så del det gerne i et issue.

### Sprog

Integrationen er oversat til: Čeština, Dansk, Deutsch, English, Español, Français, Italiano, Nederlands, Norsk (bokmål), Polski, Português, Suomi, Svenska og 简体中文.

### Opgraderingsnoter

- **v0.5.0**: entiteternes tilstandsværdier blev ændret fra store til små bogstaver (f.eks. `MISSION_IDLE` → `mission_idle`) for at overholde Home Assistants oversættelseskrav. Automatiseringer eller skabeloner, der sammenligner rå tilstandsstrenge, kræver en engangsopdatering; de viste navne er uændrede.

### Support

Opret et issue på [GitHub](https://github.com/TerraMow/TerraMowHA/issues) for at få support.

### Udviklerinformation

Udviklere, der er interesserede i at forstå eller udvide denne integration, henvises til [udviklerguiden](en/developers.md).

Sådan køres testpakken lokalt:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Licens

Dette projekt er licenseret under GNU General Public License v3.0 — se filen [LICENSE](../LICENSE) for detaljer.
