# TerraMow Home Assistantille

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · **Suomi** · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Tämä on Home Assistant -integraatio TerraMow-robottiruohonleikkureille.

### Ominaisuudet

**Ohjaus**
- Ruohonleikkuriolio: käynnistys, tauko ja paluu asemalle
- Vyöhykeleikkuu: vyöhykevalintaolio ja palvelu `terramow.start_select_region`
- **Aikataulun muokkaus** — palvelut `terramow.add_schedule` / `terramow.delete_schedule` kirjoittavat viikoittaisia leikkuuaikoja leikkuriin ja varmistavat ne takaisinluvulla. *Huomio:* nykyinen myyntilaiteohjelmisto ei vielä hyväksy aikataulun kirjoitusta paikallisen MQTT:n kautta (valmistajan sovellus käyttää Bluetoothia/pilveä) — kunnes laiteohjelmisto tukee sitä, käytä HA-puolen ajastukseen **sään mukaan sopeutuvan leikkuun blueprintiä**
- **Interaktiivinen karttakortti** — vektorimuotoinen nurmikkokartta panoroinnilla ja zoomilla koontinäyttöihin: robotin sijainti reaaliaikaisesti (väritettynä toiminnan mukaan, seurantatilalla), käynnistys- / tauko- / asemapainikkeet suoraan kortilla, akun / edistymisen / jäljellä olevan ajan merkit, leikatun alueen varjostus vyöhykekohtaisella edistymisellä, leikkuureitti, tukiasema, vyöhykkeet napautusvalinnalla leikkuuta varten, kieltoalueet ja virtuaaliseinät, aktiiviset viat merkittynä esiintymispaikkaansa sekä nurmikon **Wi-Fi-lämpökartta**; **näkymäpainike** vaihtaa Molemmat / Reitti / Alue / Wi-Fi. Teemat huomioiva, itsensä rekisteröivä, käyttöliittymämuokkaimella (`custom:terramow-map-card`)
- Reunaleikkuupainike
- Asetukset Home Assistantista: leikkuukorkeus, nopeus, kaistaväli, terän nopeus, reunaleikkuuetäisyys, pääsuunnan tila ja kulmat, huolellinen kulmien leikkuu, korkean ruohon reunaleikkuutila
- Huolto: nollauspainikkeet terälevyn ja tukiaseman laskureille

**Seuranta**
- Reaaliaikainen karttakamera leikkuureitillä, robotin sijainnilla ja tukiasemalla (lisäksi pelkistetty vain kartan näyttävä kamera koontinäyttöihin, tarkkuus säädettävissä asetuksista)
- Akku: varaustaso, lataustila, lämpötilatila, laturi kytketty, virtakytkin
- Edistyminen: nykyisen istunnon pinta-ala, edistyminen (%), kesto ja työn tyyppi; kokonaisleikkuuaika, töiden lukumäärä ja leikattu pinta-ala
- Tila: tehtävä / alitehtävä / tehtävän tila, toimintatila, virransyöttötila, asemalle paluun syy, sateen tunnistus, ongelmailmaisin, tiedon tallennuksen ja muunnoksen ilmaisimet
- **Vikatunnistin** — aktiivinen vika luettavana tekstinä (esim. *Leikkuri jumissa*, *Leikkuri nostettu* tai *OK*), jotta ilmoitus tai puheavustaja voi kertoa, mikä on vialla, ilman attribuutin käsittelyä mallipohjalla
- Käynnissä olevan työn tunnistin (säilyttää aktiivisen tehtävän myös sykeviestien katkoksissa) ja leikkurin Wi-Fi-signaalin voimakkuuden tunnistin
- Kartta: tila, pinta-ala, liput havaittu / rakennettavissa / varmuuskopiointi käynnissä
- Aikataulu: seuraavan ajastetun käynnistyksen tunnistin ja vain luettava **leikkuuaikataulun kalenteri** (seuraava leikkuu näkyy kalenterikortilla)
- Laiteohjelmiston päivitysolio, laiteohjelmiston versio laitesivulla ja versioyhteensopivuuden tunnistin
- Kaikki oliot päivittyvät välittömästi laitteen lähetyksistä — ei kyselyviivettä

**Edistynyt diagnostiikka** (takaisinmallinnetut datapisteet — pääosin *Diagnostiikka*-oliokategoriassa, monet oletuksena pois käytöstä; katso [muistiinpanot epävirallisista datapisteistä](en/developers/data_point_unofficial.md))
- Virheet ja tapahtumat: aktiivisten virheiden määrä (raaka virhelista attribuuttina) ja viimeisen tapahtuman koodi. Tunnetut virhekoodit käännetään luettavaksi tekstiksi yhteisön kokoamalla luettelolla (`error_codes.py`), joka myös purkaa leikkurin uusimman virhekoodin (dp_115)
- Mobiiliverkko / 4G: modeemi käytössä, signaalin voimakkuus (RSRP / RSRQ), yhteystyyppi ja lukema *pakota mobiiliverkko*
- Ympäristö: laitteen ilmoittama auringonnousu / -lasku, päivänvalon tila, huurteenpoiston lämmitys, valaistus ja äärimmäisen sään varoitus (valinnaisella info-URL:lla)
- Turvallisuus ja edistyneet asetukset: pudotus- ja kaltevuustunnistuksen tila, sadeanturin kynnysarvo, automaattinen jatkaminen sateen jälkeen ja sen viive sekä lukema *pakota yksi tukiasema*
- Toimintatilat: liikkumis- / kartta- / leikkuutilan merkkijonot
- Kartoitus ja edistyminen: manuaalisen kartoituksen ohjeliput (uudelleensijoitus / haltuunotto tarvitaan, raja suljettu) ja kartan tallennuksen edistymisprosentti

**Tapahtumat ja automaatiot**
- **Leikkurin tapahtumaolio** — luo erillisen tapahtuman jokaisessa merkittävässä siirtymässä (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), kukin raakoine tehtäväkenttineen, joten automaatiot reagoivat *tapahtumiin* ilman toimintatilan kyselyä
- Yhdellä napsautuksella tuotavat automaatioblueprintit (katso alta)

**Integraation käyttömukavuus**
- Automaattinen löytäminen Zeroconfin/mDNS:n kautta
- Uudelleenmääritysvirta (isännän/IP:n vaihto ilman uudelleenlisäystä) ja uudelleentodennusvirta
- **Korjausilmoitukset** — toimintaan ohjaavat koontinäyttökortit yhteensopimattomasta laiteohjelmistosta sekä erääntyneestä terän / tukiaseman huollosta
- Diagnostiikan lataus vikailmoitusten helpottamiseksi
- Käännetty 33 kielelle (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Vahvistetut komennot** — vyöhykeleikkuu odottaa laitteen dp_119-kuittausta ja ilmoittaa hylkäyksistä sen sijaan, että "onnistuisi" hiljaisesti
- Paikallinen push-tiedonsiirto MQTT:llä — pilveä ei tarvita

### Tuetut oliot

| Alusta | Oliot |
| --- | --- |
| Ruohonleikkuri | Käynnistys- / tauko- / asemaohjaus reaaliaikaisella toiminnalla |
| Kamera | Kartta reitillä, robotilla ja tukiasemalla; pelkistetty vain kartan variantti |
| Tunnistin | Akun varaustaso, akun tila, akun lämpötilatila, kartan tila, kartan pinta-ala, leikkuukorkeus, leikkuunopeus, toimintatila, sijainti, kokonaisleikkuuaika / työt / leikattu pinta-ala, nykyisen istunnon pinta-ala / edistyminen / kesto / työn tyyppi, käynnissä oleva työ, vika, terän ja tukiaseman jäljellä oleva aika, seuraava ajastettu käynnistys, versioyhteensopivuus, pääsuunnan tila, virransyöttötila, asemalle paluun syy, tehtävä, alitehtävä, tehtävän tila. *Diagnostiikka:* aktiiviset virheet, viimeinen tapahtuma, Wi-Fi-signaali, mobiiliverkon RSRP / RSRQ / tyyppi, auringonnousu, auringonlasku, liikkumis- / kartta- / leikkuutila, sadeanturin kynnysarvo, sateen jälkeisen jatkamisen viive, kartan tallennuksen edistyminen |
| Binääritunnistin | Lataa, navigointi paikannettu, laiteohjelmiston päivitys käynnissä, virtakytkin, ongelma, sade havaittu, kartta havaittu / rakennettavissa / varmuuskopiointi käynnissä, tallentaa tietoja, tiedon muunnos käynnissä. *Diagnostiikka:* mobiiliverkko käytössä, huurteenpoiston lämmitys, valaistus, päivänvalo, äärimmäinen sää, pudotus- / kaltevuustunnistus, automaattinen jatkaminen sateen jälkeen, pakota yksi tukiasema, pakota mobiiliverkko, manuaalinen kartoitus uudelleensijoitus / haltuunotto / raja suljettu, tilalippu 134 (purkamaton) |
| Valinta | Vyöhykevalinta, leikkuunopeus, terän nopeus, pääsuunnan tila, korkean ruohon reunaleikkuutila |
| Numero | Leikkuukorkeus, reunaleikkuuetäisyys, kaistaväli, yhden suunnan kulma, kulman automaattisen kierron väli, ensimmäisen / toisen suunnan kulma |
| Kytkin | Huolellinen kulmien leikkuu |
| Painike | Reunaleikkuu, nollaa terän ajastin, nollaa tukiaseman ajastin |
| Päivitys | Laiteohjelmiston versio |
| Tapahtuma | Leikkurin tapahtuma (leikkuu aloitettu / tauolla / palaa / asemalla / valmis / virhe) |
| Kalenteri | Leikkuuaikataulu (seuraava ajastettu leikkuu) |

### Asennus

[![Avaa Home Assistant -instanssisi ja avaa arkisto Home Assistant Community Storessa.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Tapa 1: HACS (suositeltu)
1. Varmista, että [HACS](https://hacs.xyz/) on asennettu
2. Käytä yllä olevaa painiketta lisätäksesi integraation HACSiin
3. Avaa HACS, etsi "TerraMow" ja valitse integraatio
4. Asenna se ja käynnistä Home Assistant uudelleen

#### Tapa 2: Manuaalinen asennus
1. Kopioi kansio `custom_components/terramow` Home Assistantin kansioon `/config/custom_components`
2. Käynnistä Home Assistant uudelleen
3. Siirry kohtaan Asetukset → Laitteet ja palvelut → Lisää integraatio
4. Etsi "TerraMow" ja seuraa määritysvaiheita

### Määritykset

Paikallisverkon laitteet löydetään automaattisesti Zeroconfin kautta — hyväksy löydetty laite ja syötä MQTT-salasana. Manuaaliseen käyttöönottoon tarvitaan seuraavat parametrit:

- **Isäntä**: TerraMow-laitteen IP-osoite tai isäntänimi
- **Salasana**: MQTT-salasana todennukseen

**Asetusten muuttaminen myöhemmin**
- *Määritä uudelleen* (Asetukset → Laitteet ja palvelut → TerraMow → Määritä uudelleen): vaihda isäntä/IP tai salasana paikan päällä, esim. kun leikkuri on saanut uuden DHCP-osoitteen — integraatiota ei tarvitse poistaa ja lisätä uudelleen.
- *Asetukset* (Määritä):
  - **Kartan ulostulotarkkuus** — suurempi on terävämpi, mutta kuluttaa enemmän kaistanleveyttä ja suoritintehoa jokaisessa hahmonnuksessa.
  - **Kartan teema** — `light` tai `dark`.
  - **Näytä leikattu alue** — varjostaa jo leikatun alueen reittiviivan alle.
  - **Käsittele jokainen päättynyt työ 100 % valmiina** — jotkin laiteohjelmistot päättävät työn ilman valmistumissignaalia, joten istunnon edistyminen ei koskaan hyppää 100 %:iin vaikka nurmikko on valmis (se näkyy "keskeytettynä"). Ota tämä käyttöön, jos haluat jokaisen päättyneen työn näkyvän valmiina, kuten valmistajan sovelluksessa; jätä pois käytöstä säilyttääksesi laskurin rehellisen arvon. *Oletus: pois käytöstä.*
- Jos laitteen salasana muuttuu, Home Assistant käynnistää automaattisesti *uudelleentodennus*virran.

### Vaatimukset

- Home Assistant 2024.6.0 tai uudempi (CI tarkistaa integraation nykyistä HA Core -julkaisua vasten)
- TerraMow-laiteohjelmisto versio 6.6.0 tai uudempi
- TerraMow-sovellus versio 1.6.0 tai uudempi
- Reaaliaikainen kartta ja leikkuureitti vaativat laiteohjelmiston HA-moduulin version 3; versiossa 2 (esim. S800) kaikki muu toimii, ja versioyhteensopivuuden tunnistin ilmoittaa siitä

### Tuetut laitteet

Tämä integraatio toimii TerraMow-robottiruohonleikkureiden kanssa, jotka tarjoavat paikallisen MQTT/HTTP-rajapinnan — eli minkä tahansa mallin kanssa, jossa on vaadittu laiteohjelmisto. Sitä käytetään TerraMowin S-sarjan kanssa, mukaan lukien **S800** (joka ilmoittaa laiteohjelmiston HA-moduulin version 2) ja uudemmat yksiköt versiolla 3. Minkä tahansa TerraMow-leikkurin, jossa on laiteohjelmisto 6.6.0+ ja sovellus 1.6.0+, pitäisi toimia; versioyhteensopivuuden tunnistin ja korjausilmoitus kertovat, jos tietyn yksikön laiteohjelmisto on liian vanha tiettyyn ominaisuuteen.

### Palvelut

#### `terramow.start_select_region`

Käynnistää leikkuun valituille alialueille.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Luo tai poistaa viikoittaisen leikkuuajan leikkurissa. Jokainen kirjoitus
varmistetaan laitteelta (dp_119-kuittaus sekä aikataulun takaisinluku).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` ottaa ajan `item_id`-arvon (näkyy kalenteritapahtuman
uid-tunnisteena ja palautetaan ajan lisäyksessä).

> **Huomio:** nykyinen myyntilaiteohjelmisto ei vielä hyväksy aikataulun
> kirjoitusta paikallisen MQTT:n kautta (valmistajan sovellus käyttää
> Bluetoothia/pilveä). Kunnes laiteohjelmisto tukee sitä, käytä HA-puolen
> ajastukseen **sään mukaan sopeutuvan leikkuun blueprintiä**.

### Interaktiivinen karttakortti

Integraatio sisältää oman Lovelace-korttinsa — rekisteröidään automaattisesti, ei manuaalista resurssia eikä erillistä HACS-frontendin asennusta:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Se piirtää nurmikon vektoreina (terävä kaikilla zoomitasoilla, seuraa HA-teemaasi): vyöhykkeet, kieltoalueet, virtuaaliseinät, leikkuureitin, tukiaseman ja robotin reaaliaikaisen sijainnin. Vedä panoroidaksesi, rullaa tai nipistä zoomatakseesi, kaksoisnapauta sovittaaksesi uudelleen. **Napauta yhtä tai useampaa vyöhykettä** ja paina ilmestyvää painiketta leikataksesi juuri nämä vyöhykkeet (taustalla `terramow.start_select_region`).

**Näkymäpainike** vaihtaa, mitä kortti piirtää nurmikon päälle:

| Tila | Näyttää |
| --- | --- |
| **Molemmat** | leikatun alueen *ja* leikkuureitin (oletus, kun aluenäyttö on käytössä) |
| **Reitti** | vain nykyisen ja edellisen työn reitin |
| **Alue** | vain leikatun alueen varjostuksen, vyöhykekohtaisella edistymisellä |
| **Wi-Fi** | nurmikon **Wi-Fi-lämpökartan**, jonka leikkuri mittaa itse leikatessaan (vihreä = vahva). Ajolinjojen väliset aukot interpoloidaan naapurimittauksista; maa, jolla leikkuri ei ole koskaan käynyt, jää tyhjäksi |

Valittu tila muistetaan oliokohtaisesti selaimessa. Asetukset ja yksityiskohdat: katso [koontinäyttöopas](en/dashboard.md#interactive-map-card) (englanniksi). Reaaliaikainen karttadata vaatii laiteohjelmiston HA-moduulin version 3 (kuten karttakamera). Kortti löytyy myös koontinäytön korttivalitsimesta nimellä **TerraMow Map Card**, täydellä käyttöliittymämuokkaimella — YAML:ää ei tarvita.

### Koontinäyttöesimerkki

Valmis Lovelace-näkymä (reaaliaikainen kartta, ohjaimet, edistymismittari, tilakatsaus) sekä ilmoitusautomaatiot: katso [koontinäyttöopas](en/dashboard.md) (englanniksi).

### Automaatioblueprintit

Yhdellä napsautuksella tuotavat blueprintit yleisimpiin ilmoituksiin — kukin kysyy vain asianmukaisen TerraMow-olion ja ilmoitustoiminnon:

- **Sään mukaan sopeutuva leikkuu** — käynnistää leikkuun aikataulusi mukaan ja ohittaa sen automaattisesti, kun sade havaitaan tai sitä ennustetaan
  [![Tuo blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Ongelmailmoitus** — kun leikkuri ilmoittaa viasta
  [![Tuo blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Palasi sateen vuoksi** — kun leikkuri palaa asemalle sateen takia
  [![Tuo blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Leikkuu valmis** — kun leikkuutyö päättyy
  [![Tuo blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Tapahtumaolion suora käyttö** — leikkurin tapahtumaolio on joustavin liipaisin. Sen `event_type`-attribuutti on yksi arvoista `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, ja se kantaa raakoja kenttiä `mission`, `sub_mission`, `state`, `back_to_station_reason` ja `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow sai leikkuun valmiiksi 🌱"
```

### Korjausilmoitukset

Integraatio luo toimintaan ohjaavia Home Assistantin korjausilmoituksia (Asetukset → Laitteet ja palvelut → Korjaukset) sen sijaan, että piilottaisi ongelmat tunnistimiin:

- **Laiteohjelmisto yhteensopimaton / päivitys vaaditaan** — laiteohjelmisto on liian vanha integraatiolle (tai tietylle ominaisuudelle). Perustuu versioyhteensopivuuden tarkistukseen; poistuu, kun yhteensopiva laiteohjelmisto ilmoittautuu.
- **Terän huolto erääntynyt** — terälevy on saavuttanut suositellun 240 tunnin huoltovälin. Puhdista tai vaihda terät ja paina painiketta *Nollaa terän ajastin* poistaaksesi ilmoituksen.
- **Tukiaseman huolto erääntynyt** — tukiasema on saavuttanut suositellun 30 päivän huoltovälin. Puhdista se ja paina painiketta *Nollaa tukiaseman ajastin* poistaaksesi ilmoituksen.

### Diagnostiikka ja vianetsintä

- **Diagnostiikan lataus**: Asetukset → Laitteet ja palvelut → TerraMow → kolmen pisteen valikko → *Lataa diagnostiikka* tuottaa siivotun JSON-tilannevedoksen (laitteen tila, laiteohjelmiston yhteensopivuus, raa'at datapistevälimuistit) — liitä se vikailmoituksiin.
- **Tukemattomien ominaisuuksien löytäminen**: leikkuri julkaisee enemmän datapisteitä kuin on dokumentoitu. Jokaisen tuntemattoman datapisteen ensimmäinen sisältö kirjataan kertaalleen INFO-tasolla; ota `terramow`-integraatiolle käyttöön debug-lokitus tallentaaksesi ne kaikki. Jos löydät datapisteen puuttuvalle ominaisuudelle (esim. nostohälytys, aikataulukytkin, virhekoodit), jaa se issuessa.

### Miten tiedot päivittyvät

TerraMow on **local push** -integraatio. Leikkuri ylläpitää MQTT-välittäjää laitteessa; Home Assistant yhdistää siihen suoraan paikallisverkon yli (ei pilveä) ja tilaa laitteen datapisteaiheet, joten olioiden tilat päivittyvät sillä hetkellä, kun leikkuri ilmoittaa muutoksesta, eikä kyselyvälin mukaan. Suuremmat sisällöt (kartta, reaaliaikainen reitti) ilmoitetaan MQTT:n kautta ja haetaan tarvittaessa paikallisella HTTP:llä. Jos leikkuri on lepotilassa tai poissa verkosta, yhteyttä yritetään uudelleen eksponentiaalisella viiveellä, ja ruohonleikkuriolio näyttää yhteyden katkeamisen `error`-toimintanaan.

**Komennot epäonnistuvat äänekkäästi, eivät hiljaa.** Kun lähetät komennon — `dock`, `start_mowing`, `pause`, reunaleikkuu, vyöhykeleikkuu tai mikä tahansa asetusmuutos — se julkaistaan MQTT QoS 1:llä (lyhyt uudelleenyhdistys puskuroi sen sen sijaan, että pudottaisi sen). Jos leikkuri on offline tai tavoittamattomissa, välittäjä hylkää julkaisun tai komento saapuu nopeammin kuin laite pystyy sen hyväksymään, palvelukutsu **epäonnistuu virheellä** sen sijaan, että ilmoittaisi hiljaisesti onnistumisesta. Näin automaatio, joka kutsuu `lawn_mower.dock` leikkurin ollessa tavoittamattomissa, näkee epäonnistumisen (ja voi yrittää uudelleen tai ilmoittaa) eikä usko leikkurin olevan paluumatkalla, kun se ei koskaan saanut komentoa.

### Tunnetut rajoitukset

- **Ei pilvi- / etäkäyttöä** — Home Assistantin on oltava samassa paikallisverkossa kuin leikkuri; pilvivarayhteyttä ei ole.
- **Laiteohjelmistosta riippuvat ominaisuudet** — reaaliaikainen kartta ja leikkuureittinäkymä vaativat HA-moduulin version 3; versiossa 2 (esim. S800) kaikki muu toimii, ja yhteensopivuustunnistin / korjausilmoitus kertoo rajoituksesta.
- **Laiteohjelmiston päivitykset** tehdään TerraMow-sovelluksella, ei Home Assistantista; laiteohjelmiston `update`-olio on vain informatiivinen.
- **Sijaintitunnistin ja pelkistetty karttakamera ovat oletuksena pois käytöstä** (sijaintitunnistin päivittyy noin 2 Hz:n tahtiin); ota ne käyttöön olioasetuksista, jos tarvitset niitä.
- **Monet edistyneen diagnostiikan oliot ovat oletuksena pois käytöstä** ja ryhmitelty *Diagnostiikka*-kategoriaan (mobiiliverkko, auringonnousu/-lasku, toimintatilat, manuaalisen kartoituksen liput jne.); ne perustuvat takaisinmallinnettuihin datapisteisiin, joten ota käyttöön vain tarvitsemasi. Katso [muistiinpanot epävirallisista datapisteistä](en/developers/data_point_unofficial.md).
- Jotkin laitteen datapisteet ovat dokumentoimattomia; tuntemattomat kirjataan kertaalleen, jotta puuttuvia ominaisuuksia voidaan löytää.

### Käyttötapaukset

- **Sateeseen reagoivat ilmoitukset** — saat push-viestin, kun leikkuri palaa asemalleen sateen vuoksi (katso blueprintit yllä).
- **Vikahälytykset** — saat ilmoituksen heti, kun leikkuri ilmoittaa ongelmasta (jumissa, nostettu, tukossa).
- **Vyöhykeleikkuu automaatioista** — kutsu `terramow.start_select_region` leikatakseesi tiettyjä alialueita aikataulun mukaan tai koontinäytön painikkeella.
- **Huoltomuistutukset** — terän / tukiaseman jäljellä olevan ajan tunnistimet ja nollauspainikkeet mahdollistavat automatisoidut huoltomuistutukset.
- **Reaaliaikainen kartta koontinäytöllä** — näytä karttakamera robotin sijainnilla ja leikkuureitillä (katso koontinäyttöopas).

### Kielet

Integraatio on käännetty kielille: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Päivitysohjeet

- **v0.5.0**: olioiden tila-arvot muuttuivat isoista kirjaimista pieniksi (esim. `MISSION_IDLE` → `mission_idle`) Home Assistantin käännösvaatimusten vuoksi. Automaatiot tai mallipohjat, jotka vertaavat raakoja tilamerkkijonoja, tarvitsevat kertaluonteisen päivityksen; näytetyt nimet eivät muutu.

### Tuki

Avaa tukea varten issue [GitHubissa](https://github.com/it-rec/TerraMowHA/issues).

### Tietoa kehittäjille

Kehittäjille, jotka haluavat ymmärtää tai laajentaa tätä integraatiota (kehittäjädokumentaatio on englanniksi):

- [Osallistumisopas](../CONTRIBUTING.md) — käyttöönotto, laatuvaatimukset (100 % kattavuus, `mypy --strict`, käännökset), PR- ja julkaisuprosessi
- [Arkkitehtuuri](ARCHITECTURE.md) — integraation sisäinen rakenne: hubin elinkaari, suoritusmalli, datapisteluettelo, kartta-/reittiputki
- [Kehittäjäopas](en/developers.md) — laitteen MQTT/HTTP-protokolla sellaisena kuin se kulkee verkossa
- [Mitä tämä fork lisää upstreamiin](UPSTREAM_DELTA.md)

Testien suorittaminen paikallisesti:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Lisenssi

Tämä projekti on lisensoitu GNU General Public License v3.0 -lisenssillä — katso yksityiskohdat tiedostosta [LICENSE](../LICENSE).
