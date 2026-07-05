# TerraMow för Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · **Svenska** · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Detta är en Home Assistant-integration för TerraMow robotgräsklippare.

### Funktioner

**Styrning**
- Gräsklipparentitet: starta, pausa och docka
- Zonklippning: entitet för zonval och tjänsten `terramow.start_select_region`
- Knapp för kantklippning
- Inställningar från Home Assistant: klipphöjd, hastighet, spåravstånd, knivhastighet, kantklippningsavstånd, huvudriktningsläge och -vinklar, noggrann hörnklippning, kantklippningsläge för högt gräs
- Underhåll: återställningsknappar för räknarna för knivdisken och basstationen

**Övervakning**
- Livekartkamera med klippspår, robotens position och basstation (plus en ren kamera med enbart kartan för instrumentpaneler, upplösningen kan konfigureras via alternativen)
- Batteri: nivå, laddningsstatus, temperaturstatus, laddare ansluten, strömbrytare
- Arbetsförlopp: yta för aktuell session, förlopp (%), varaktighet och jobbtyp; total klipptid, antal jobb och klippt yta
- Status: uppdrag / deluppdrag / uppdragsstatus, driftläge, strömläge, orsak till återgång till stationen, regndetektering, problemindikator, indikatorer för datalagring och datakonvertering
- Karta: status, yta, flaggor för upptäckt / kan byggas / säkerhetskopieras
- Schema: nästa schemalagda start
- Entitet för firmwareuppdatering, firmwareversion på enhetssidan och sensor för versionskompatibilitet
- Alla entiteter uppdateras omedelbart vid push från enheten — ingen pollningsfördröjning

**Praktiska integrationsfunktioner**
- Automatisk upptäckt via Zeroconf/mDNS
- Omkonfigurationsflöde (byt värd/IP utan att lägga till på nytt) och omautentiseringsflöde
- Nedladdning av diagnostik för enkla felrapporter
- Översatt till 33 språk (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- MQTT-baserad lokal push-kommunikation — inget moln krävs

### Entiteter som stöds

| Plattform | Entiteter |
| --- | --- |
| Gräsklippare | Styrning av start / paus / dockning med liveaktivitet |
| Kamera | Karta med spår, robot och basstation; ren variant med enbart kartan |
| Sensor | Batterinivå, batteristatus, batteritemperaturstatus, kartstatus, kartyta, klipphöjd, klipphastighet, driftläge, position, total klipptid / antal jobb / klippt yta, yta / förlopp / varaktighet / jobbtyp för aktuell session, återstående tid för kniv och basstation, nästa schemalagda start, versionskompatibilitet, huvudriktningsstatus, strömläge, orsak till återgång till stationen, uppdrag, deluppdrag, uppdragsstatus |
| Binär sensor | Laddning, navigering lokaliserad, firmwareuppgradering pågår, strömbrytare, problem, regn upptäckt, karta upptäckt / kan byggas / säkerhetskopieras, sparar data, datakonvertering pågår |
| Val | Zonval, klipphastighet, knivhastighet, huvudriktningsläge, kantklippningsläge för högt gräs |
| Nummer | Klipphöjd, kantklippningsavstånd, spåravstånd, vinkel för en riktning, intervall för automatisk vinkelrotation, vinkel för första / andra riktningen |
| Strömbrytare | Noggrann hörnklippning |
| Knapp | Kantklippning, återställ knivtimern, återställ basstationstimern |
| Uppdatering | Firmwareversion |

### Installation

#### Metod 1: HACS (rekommenderas)
1. Se till att [HACS](https://hacs.xyz/) är installerat
2. Använd knappen ovan för att lägga till i HACS
3. Gå till HACS → Integrationer → + → Sök efter "TerraMow"
4. Installera och starta om Home Assistant

#### Metod 2: Manuell installation
1. Kopiera mappen `custom_components/terramow` till Home Assistant-mappen `/config/custom_components`
2. Starta om Home Assistant
3. Gå till Inställningar → Enheter och tjänster → Lägg till integration
4. Sök efter "TerraMow" och följ konfigurationsstegen

### Konfiguration

Enheter i det lokala nätverket upptäcks automatiskt via Zeroconf — acceptera den upptäckta enheten och ange MQTT-lösenordet. För manuell konfiguration krävs följande parametrar:

- **Värd**: IP-adress eller värdnamn för TerraMow-enheten
- **Lösenord**: MQTT-lösenord för autentisering

**Ändra inställningar senare**
- *Omkonfigurera* (Inställningar → Enheter och tjänster → TerraMow → Omkonfigurera): byt värd/IP eller lösenord direkt, t.ex. efter att gräsklipparen har fått en ny DHCP-adress — du behöver inte ta bort integrationen och lägga till den igen.
- *Alternativ* (Konfigurera): ställ in kartkamerans utdataupplösning. Högre värden ger en skarpare bild på instrumentpanelen på bekostnad av bandbredd och CPU per rendering.
- Om enhetens lösenord ändras startar Home Assistant automatiskt ett *omautentiserings*-flöde.

### Krav

- Home Assistant 2023.9.3 eller senare (testad med 2025.1.1)
- TerraMow firmwareversion 6.6.0 eller senare
- TerraMow APP version 1.6.0 eller senare
- Livekarta och klippspår kräver firmware med HA-modul version 3; på version 2 (t.ex. S800) fungerar allt annat och sensorn för versionskompatibilitet rapporterar det

### Tjänster

#### `terramow.start_select_region`

Starta klippning för en lista med valda delområden.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

### Diagnostik och felsökning

- **Nedladdning av diagnostik**: Inställningar → Enheter och tjänster → TerraMow → trepunktsmenyn → *Ladda ner diagnostik* skapar en anonymiserad JSON-ögonblicksbild (enhetsstatus, firmwarekompatibilitet, cacher med rådatapunkter) — bifoga den gärna i felrapporter.
- **Upptäcka funktioner som inte stöds**: gräsklipparen publicerar fler datapunkter än vad som är dokumenterat. Den första payloaden för varje okänd datapunkt loggas en gång på INFO-nivå; aktivera felsökningsloggning för `terramow`-integrationen för att registrera alla. Om du hittar en datapunkt för en saknad funktion (t.ex. lyftlarm, schemabrytare, felkoder), dela den gärna i ett issue.

### Språk

Integrationen är översatt till: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Uppgraderingsanteckningar

- **v0.5.0**: entiteternas tillståndsvärden ändrades från versaler till gemener (t.ex. `MISSION_IDLE` → `mission_idle`) för att uppfylla Home Assistants översättningskrav. Automationer eller mallar som jämför råa tillståndssträngar behöver en engångsuppdatering; de visade namnen är oförändrade.

### Support

Öppna ett issue på [GitHub](https://github.com/it-rec/TerraMowHA/issues) för att få support.

### Utvecklarinformation

Utvecklare som är intresserade av att förstå eller utöka denna integration hänvisas till [utvecklarguiden](en/developers.md).

Så här kör du testsviten lokalt:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Licens

Detta projekt är licensierat under GNU General Public License v3.0 — se filen [LICENSE](../LICENSE) för detaljer.
