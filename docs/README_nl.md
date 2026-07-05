# TerraMow voor Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow-logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · **Nederlands** · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Dit is een Home Assistant-integratie voor TerraMow-robotmaaiers.

### Functies

**Bediening**
- Grasmaaier-entiteit: starten, pauzeren en naar het dockingstation sturen
- Zonemaaien: zoneselectie-entiteit en de service `terramow.start_select_region`
- Knop voor het maaien van randen
- Instellingen vanuit Home Assistant: maaihoogte, snelheid, baanafstand, messnelheid, randmaaiafstand, hoofdrichtingsmodus en -hoeken, grondig hoekmaaien, randmaaimodus voor hoog gras
- Onderhoud: resetknoppen voor de tellers van de messchijf en het basisstation

**Bewaking**
- Livekaartcamera met maaipad, robotpositie en basisstation (plus een strakke camera met alleen de kaart voor dashboards, resolutie instelbaar via de opties)
- Accu: niveau, laadstatus, temperatuurstatus, lader aangesloten, aan/uit-schakelaar
- Taakvoortgang: oppervlakte van de huidige sessie, voortgang (%), duur en taaktype; totale maaitijd, aantal taken en gemaaide oppervlakte
- Status: missie / submissie / missiestatus, bedrijfsmodus, energiemodus, reden voor terugkeer naar het station, regendetectie, probleemindicator, indicatoren voor gegevens opslaan en gegevensconversie
- Kaart: status, oppervlakte, vlaggen voor gedetecteerd / opbouwbaar / back-up bezig
- Planning: volgende geplande start
- Firmware-update-entiteit, firmwareversie op de apparaatpagina en sensor voor versiecompatibiliteit
- Alle entiteiten worden direct bijgewerkt bij pushberichten van het apparaat — geen pollingvertraging

**Gebruiksgemak van de integratie**
- Automatische detectie via Zeroconf/mDNS
- Herconfiguratieflow (host/IP wijzigen zonder opnieuw toe te voegen) en herauthenticatieflow
- Diagnostiekdownload voor eenvoudige bugrapporten
- Vertaald in 33 talen (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- Lokale pushcommunicatie op basis van MQTT — geen cloud nodig

### Ondersteunde entiteiten

| Platform | Entiteiten |
| --- | --- |
| Grasmaaier | Bediening voor starten / pauzeren / docken met live-activiteit |
| Camera | Kaart met pad, robot en basisstation; strakke variant met alleen de kaart |
| Sensor | Accuniveau, accustatus, accutemperatuurstatus, kaartstatus, kaartoppervlakte, maaihoogte, maaisnelheid, bedrijfsmodus, positie, totale maaitijd / taken / gemaaide oppervlakte, oppervlakte / voortgang / duur / taaktype van de huidige sessie, resterende tijd van messen en basisstation, volgende geplande start, versiecompatibiliteit, status van de hoofdrichting, energiemodus, reden voor terugkeer naar het station, missie, submissie, missiestatus |
| Binaire sensor | Opladen, navigatie gelokaliseerd, firmware-upgrade bezig, aan/uit-schakelaar, probleem, regen gedetecteerd, kaart gedetecteerd / opbouwbaar / back-up bezig, gegevens opslaan, gegevensconversie bezig |
| Selectie | Zoneselectie, maaisnelheid, messnelheid, hoofdrichtingsmodus, randmaaimodus voor hoog gras |
| Getal | Maaihoogte, randmaaiafstand, maaibaanafstand, hoek voor enkele richting, interval voor automatisch roterende hoek, hoek van de eerste / tweede richting |
| Schakelaar | Grondig hoekmaaien |
| Knop | Randen maaien, mestimer resetten, basisstationtimer resetten |
| Update | Firmwareversie |

### Installatie

#### Methode 1: HACS (aanbevolen)
1. Zorg ervoor dat [HACS](https://hacs.xyz/) is geïnstalleerd
2. Gebruik de knop hierboven om de integratie aan HACS toe te voegen
3. Ga naar HACS → Integraties → + → Zoek naar "TerraMow"
4. Installeer en herstart Home Assistant

#### Methode 2: Handmatige installatie
1. Kopieer de map `custom_components/terramow` naar de map `/config/custom_components` van uw Home Assistant
2. Herstart Home Assistant
3. Ga naar Instellingen → Apparaten en diensten → Integratie toevoegen
4. Zoek naar "TerraMow" en volg de configuratiestappen

### Configuratie

Apparaten in het lokale netwerk worden automatisch gedetecteerd via Zeroconf — accepteer het gedetecteerde apparaat en voer het MQTT-wachtwoord in. Voor handmatige installatie zijn de volgende parameters vereist:

- **Host**: IP-adres of hostnaam van het TerraMow-apparaat
- **Wachtwoord**: MQTT-wachtwoord voor authenticatie

**Instellingen later wijzigen**
- *Herconfigureren* (Instellingen → Apparaten en diensten → TerraMow → Herconfigureren): wijzig de host/IP of het wachtwoord ter plekke, bijvoorbeeld nadat de maaier een nieuw DHCP-adres heeft gekregen — de integratie hoeft niet te worden verwijderd en opnieuw toegevoegd.
- *Opties* (Configureren): stel de uitvoerresolutie van de kaartcamera in. Hogere waarden geven een scherper dashboardbeeld, maar kosten meer bandbreedte en CPU per rendering.
- Als het wachtwoord van het apparaat verandert, start Home Assistant automatisch een *herauthenticatie*-flow.

### Vereisten

- Home Assistant 2023.9.3 of nieuwer (getest met 2025.1.1)
- TerraMow-firmwareversie 6.6.0 of nieuwer
- TerraMow-APP-versie 1.6.0 of nieuwer
- De livekaart en het maaipad vereisen firmware-HA-moduleversie 3; op versie 2 (bijv. S800) werkt al het overige en meldt de sensor voor versiecompatibiliteit dit

### Services

#### `terramow.start_select_region`

Start het maaien voor een lijst met geselecteerde subregio's.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

### Diagnostiek en probleemoplossing

- **Diagnostiekdownload**: Instellingen → Apparaten en diensten → TerraMow → menu met drie puntjes → *Diagnostische gegevens downloaden* levert een geanonimiseerde JSON-momentopname op (apparaatstatus, firmwarecompatibiliteit, caches met ruwe datapunten) — voeg deze alstublieft toe aan bugrapporten.
- **Niet-ondersteunde functies ontdekken**: de maaier publiceert meer datapunten dan er gedocumenteerd zijn. De eerste payload van elk onbekend datapunt wordt eenmalig gelogd op INFO-niveau; schakel debug-logging in voor de `terramow`-integratie om ze allemaal vast te leggen. Als u een datapunt vindt voor een ontbrekende functie (bijv. tilalarm, planningsschakelaar, foutcodes), deel het dan in een issue.

### Talen

De integratie is vertaald in: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Upgrade-opmerkingen

- **v0.5.0**: de statuswaarden van entiteiten zijn gewijzigd van hoofdletters naar kleine letters (bijv. `MISSION_IDLE` → `mission_idle`) om te voldoen aan de vertaalvereisten van Home Assistant. Automatiseringen of sjablonen die ruwe statusstrings vergelijken, hebben een eenmalige aanpassing nodig; de weergegeven namen blijven ongewijzigd.

### Ondersteuning

Open een issue op [GitHub](https://github.com/it-rec/TerraMowHA/issues) voor ondersteuning.

### Informatie voor ontwikkelaars

Ontwikkelaars die deze integratie willen begrijpen of uitbreiden, kunnen de [Ontwikkelaarshandleiding](en/developers.md) raadplegen.

Om de testsuite lokaal uit te voeren:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Licentie

Dit project is gelicentieerd onder de GNU General Public License v3.0 — zie het bestand [LICENSE](../LICENSE) voor details.
