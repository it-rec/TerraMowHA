# TerraMow Home Assistantille

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · **Suomi** · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Tämä on Home Assistant -integraatio TerraMow-robottiruohonleikkureille.

### Ominaisuudet

**Ohjaus**
- Ruohonleikkurientiteetti: käynnistys, tauko ja telakointi
- Vyöhykeleikkuu: vyöhykkeen valintaentiteetti ja `terramow.start_select_region`-palvelu
- **Schedule editing** — `terramow.add_schedule` / `terramow.delete_schedule` services write weekly mowing slots to the mower, confirmed against the device (acknowledgement + read-back); the calendar reflects changes immediately
- **Interactive map card** — pan/zoom vector lawn map for dashboards: live robot position (activity-tinted, with follow mode), on-card start / pause / dock controls, battery & job-progress chips, optional mowed-coverage shading, mowing path, base station, zones with tap-to-mow selection, forbidden areas and virtual walls; theme-aware, self-registering, with a UI editor (`custom:terramow-map-card`)
- Reunaleikkuupainike
- Asetukset Home Assistantista: leikkuukorkeus, nopeus, leikkuuväli, terän nopeus, reunaleikkuun etäisyys, pääsuuntatila ja -kulmat, perusteellinen kulmien leikkuu, korkean ruohon reunaleikkuutila
- Huolto: nollauspainikkeet terälautasen ja tukiaseman laskureille

**Valvonta**
- Reaaliaikainen karttakamera, jossa näkyvät leikkuureitti, robotin sijainti ja tukiasema (lisäksi pelkän kartan näyttävä kamera kojelautoja varten, resoluutio määritettävissä asetuksista)
- Akku: varaustaso, lataustila, lämpötilatila, laturi kytketty, virtakytkin
- Työn edistyminen: nykyisen istunnon pinta-ala, edistyminen (%), kesto ja työn tyyppi; kokonaisleikkuuaika, töiden määrä ja leikattu pinta-ala
- Tila: tehtävä / alitehtävä / tehtävän tila, toimintatila, virtatila, tukiasemalle paluun syy, sateen tunnistus, ongelmailmaisin, tietojen tallennuksen ja tietojen muunnoksen ilmaisimet
- Kartta: tila, pinta-ala, liput havaittu / rakennettavissa / varmuuskopioidaan
- Aikataulu: seuraava ajastettu käynnistys
- Laiteohjelmiston päivitysentiteetti, laiteohjelmistoversio laitesivulla ja versioyhteensopivuusanturi
- Kaikki entiteetit päivittyvät välittömästi laitteen push-viesteistä — ei kyselyviivettä

**Integraation käyttömukavuus**
- Automaattinen löytäminen Zeroconf/mDNS:n kautta
- Uudelleenmääritysprosessi (isännän/IP:n vaihto ilman uudelleenlisäystä) ja uudelleentodennusprosessi
- Diagnostiikan lataus helppoja virheraportteja varten
- Käännetty 33 kielelle (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- MQTT-pohjainen paikallinen push-viestintä — pilveä ei tarvita

### Tuetut entiteetit

| Alusta | Entiteetit |
| --- | --- |
| Ruohonleikkuri | Käynnistys / tauko / telakointi -ohjaus reaaliaikaisella toimintatiedolla |
| Kamera | Kartta, jossa reitti, robotti ja tukiasema; pelkän kartan näyttävä variantti |
| Anturi | Akun varaustaso, akun tila, akun lämpötilatila, kartan tila, kartan pinta-ala, leikkuukorkeus, leikkuunopeus, toimintatila, sijainti, kokonaisleikkuuaika / töiden määrä / leikattu pinta-ala, nykyisen istunnon pinta-ala / edistyminen / kesto / työn tyyppi, terän ja tukiaseman jäljellä oleva aika, seuraava ajastettu käynnistys, versioyhteensopivuus, pääsuunnan tila, virtatila, tukiasemalle paluun syy, tehtävä, alitehtävä, tehtävän tila |
| Binäärianturi | Lataus, navigointi paikannettu, laiteohjelmiston päivitys käynnissä, virtakytkin, ongelma, sade havaittu, kartta havaittu / rakennettavissa / varmuuskopioidaan, tietojen tallennus, tietojen muunnos käynnissä |
| Valinta | Vyöhykkeen valinta, leikkuunopeus, terän nopeus, pääsuuntatila, korkean ruohon reunaleikkuutila |
| Numero | Leikkuukorkeus, reunaleikkuun etäisyys, leikkuuväli, yhden suunnan kulma, automaattisen kierron kulmaväli, ensimmäisen / toisen suunnan kulma |
| Kytkin | Perusteellinen kulmien leikkuu |
| Painike | Reunaleikkuu, terän ajastimen nollaus, tukiaseman ajastimen nollaus |
| Päivitys | Laiteohjelmistoversio |

### Asennus

#### Tapa 1: HACS (suositeltu)
1. Varmista, että [HACS](https://hacs.xyz/) on asennettu
2. Käytä yllä olevaa painiketta lisätäksesi repositorion HACS:iin
3. Siirry kohtaan HACS → Integraatiot → + → hae "TerraMow"
4. Asenna ja käynnistä Home Assistant uudelleen

#### Tapa 2: Manuaalinen asennus
1. Kopioi `custom_components/terramow`-kansio Home Assistantin `/config/custom_components`-kansioon
2. Käynnistä Home Assistant uudelleen
3. Siirry kohtaan Asetukset → Laitteet ja palvelut → Lisää integraatio
4. Hae "TerraMow" ja seuraa määritysvaiheita

### Määritys

Paikallisverkon laitteet löydetään automaattisesti Zeroconfin kautta — hyväksy löydetty laite ja syötä MQTT-salasana. Manuaalista määritystä varten tarvitaan seuraavat parametrit:

- **Isäntä**: TerraMow-laitteen IP-osoite tai isäntänimi
- **Salasana**: MQTT-salasana todennusta varten

**Asetusten muuttaminen myöhemmin**
- *Uudelleenmääritys* (Asetukset → Laitteet ja palvelut → TerraMow → Määritä uudelleen): vaihda isäntä/IP tai salasana suoraan, esim. kun leikkuri on saanut uuden DHCP-osoitteen — integraatiota ei tarvitse poistaa ja lisätä uudelleen.
- *Valinnat* (Määritä): aseta karttakameran lähtöresoluutio. Suuremmat arvot antavat terävämmän kuvan kojelaudalle kaistanleveyden ja renderöintikohtaisen CPU-kuorman kustannuksella.
- Jos laitteen salasana vaihtuu, Home Assistant käynnistää automaattisesti *uudelleentodennusprosessin*.

### Vaatimukset

- Home Assistant 2024.6.0 tai uudempi (testattu versiolla 2025.1.1)
- TerraMow-laiteohjelmiston versio 6.6.0 tai uudempi
- TerraMow APP -versio 1.6.0 tai uudempi
- Reaaliaikainen kartta ja leikkuureitti vaativat laiteohjelmiston HA-moduulin version 3; versiolla 2 (esim. S800) kaikki muu toimii, ja versioyhteensopivuusanturi ilmoittaa asiasta

### Palvelut

#### `terramow.start_select_region`

Käynnistää leikkuun valittujen alialueiden luettelolle.

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

### Diagnostiikka ja vianetsintä

- **Diagnostiikan lataus**: Asetukset → Laitteet ja palvelut → TerraMow → kolmen pisteen valikko → *Lataa diagnostiikka* tuottaa anonymisoidun JSON-tilannekuvan (laitteen tila, laiteohjelmiston yhteensopivuus, raakadatapisteiden välimuistit) — liitä se virheraportteihin.
- **Tukemattomien ominaisuuksien löytäminen**: leikkuri julkaisee enemmän datapisteitä kuin on dokumentoitu. Jokaisen tuntemattoman datapisteen ensimmäinen sisältö kirjataan kerran INFO-tasolla; ota virheenkorjauslokitus käyttöön `terramow`-integraatiolle tallentaaksesi ne kaikki. Jos löydät datapisteen puuttuvalle ominaisuudelle (esim. nostohälytys, aikataulukytkin, virhekoodit), jaa se issuessa.

### Kielet

Integraatio on käännetty seuraaville kielille: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Päivityshuomautukset

- **v0.5.0**: entiteettien tila-arvot muuttuivat isoista kirjaimista pieniksi (esim. `MISSION_IDLE` → `mission_idle`) Home Assistantin käännösvaatimusten täyttämiseksi. Raakoja tilamerkkijonoja vertailevat automaatiot tai mallipohjat vaativat kertaluonteisen päivityksen; näytettävät nimet eivät muutu.

### Tuki

Avaa issue [GitHubissa](https://github.com/it-rec/TerraMowHA/issues) saadaksesi tukea.

### Tietoa kehittäjille

Kehittäjät, jotka haluavat ymmärtää tätä integraatiota tai laajentaa sitä, löytävät lisätietoja [kehittäjän oppaasta](en/developers.md).

Testien ajaminen paikallisesti:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Lisenssi

Tämä projekti on lisensoitu GNU General Public License v3.0 -lisenssillä — katso lisätiedot [LICENSE](../LICENSE)-tiedostosta.
