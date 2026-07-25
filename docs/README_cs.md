# TerraMow pro Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · **Čeština** · [中文](README_zh.md)

---

Toto je integrace pro Home Assistant určená pro robotické sekačky TerraMow.

### Funkce

**Ovládání**
- Entita sekačky: spuštění, pauza a návrat do stanice
- Sečení po zónách: entita výběru zóny a služba `terramow.start_select_region`
- **Úprava rozvrhu** — služby `terramow.add_schedule` / `terramow.delete_schedule` zapisují týdenní okna sečení do sekačky a ověřují je zpětným čtením. *Poznámka:* současný prodejní firmware zápis rozvrhu přes lokální MQTT zatím nepřijímá (aplikace výrobce používá Bluetooth/cloud) — dokud to firmware neumožní, použijte pro plánování na straně HA **blueprint sečení podle počasí**
- **Interaktivní karta mapy** — vektorová mapa trávníku s posunem a přiblížením pro panely: poloha robota v reálném čase (obarvená podle aktivity, s režimem sledování), ovládání spuštění / pauzy / návratu přímo na kartě, štítky baterie / průběhu / zbývajícího času, vyšrafování posečené plochy s průběhem po zónách, trasa sečení, základnová stanice, zóny s výběrem klepnutím pro sečení, zakázané zóny a virtuální stěny, aktivní závady vyznačené na místě výskytu a **teplotní mapa Wi-Fi** trávníku; **tlačítko zobrazení** přepíná Obojí / Trasa / Plocha / Wi-Fi. Respektuje motivy, registruje se sama a má editor rozhraní (`custom:terramow-map-card`)
- Tlačítko pro sečení okrajů
- Nastavení z Home Assistant: výška sečení, rychlost, rozestup pásů, otáčky nože, vzdálenost pro sečení okrajů, režim a úhly hlavního směru, důkladné sečení rohů, režim sečení okrajů pro vysokou trávu
- Údržba: tlačítka pro vynulování počitadel nožového disku a základnové stanice

**Monitorování**
- Živá kamera mapy s trasou sečení, polohou robota a základnovou stanicí (a navíc čistá kamera „pouze mapa“ pro panely, s rozlišením nastavitelným v možnostech)
- Baterie: úroveň, stav nabíjení, stav teploty, připojená nabíječka, vypínač
- Průběh: plocha aktuální session, průběh (%), doba trvání a typ úlohy; celková doba sečení, počet úloh a posečená plocha
- Stav: misie / podmisie / stav misie, provozní režim, režim napájení, důvod návratu do stanice, detekce dešťě, indikátor problému, indikátory ukládání a konverze dat
- **Senzor závady** — aktivní závada jako čitelný text (např. *Sekačka uvízla*, *Sekačka zvednuta* nebo *OK*), takže oznámení nebo hlasový asistent může říct, co se děje, bez zpracování atributu šablonou
- Senzor probíhající úlohy (drží aktivní misii i přes mezery v signálu přítomnosti) a senzor síly signálu Wi-Fi na straně sekačky
- Mapa: stav, plocha, příznaky detekována / lze vytvořit / probíhá záloha
- Rozvrh: senzor nejbližšího naplánovaného spuštění a **kalendář rozvrhu sečení** pouze pro čtení (nejbližší sečení se zobrazí na kartě kalendáře)
- Entita aktualizace firmwaru, verze firmwaru na stránce zařízení a senzor kompatibility verzí
- Všechny entity se aktualizují okamžitě při odeslání ze zařízení — bez prodlevy dotazování

**Rozšířená diagnostika** (datové body získané reverzním inženýrstvím — většinou v kategorii entit *Diagnostika*, mnohé ve výchozím stavu vypnuté; viz [poznámky k neoficiálním datovým bodům](en/developers/data_point_unofficial.md))
- Chyby a události: počet aktivních chyb (se surovým seznamem chyb jako atributem) a kód poslední události. Známé chybové kódy jsou přeloženy do čitelného textu pomocí katalogu spravovaného komunitou (`error_codes.py`), který také dekóduje nejnovější chybový kód sekačky (dp_115)
- Mobilní síť / 4G: modem zapnut, síla signálu (RSRP / RSRQ), typ připojení a odečet *vynutit mobilní síť*
- Prostředí: východ / západ slunce hlášený zařízením, stav denního světla, vyhřívání proti zamlžení, osvětlení a varování před extrémním počasím (s volitelnou informační URL)
- Bezpečnost a rozšířená nastavení: stav detekce hran a sklonu, prahová hodnota dešťového senzoru, automatické pokračování po dešti a jeho zpoždění, a odečet *vynutit jednu základnovou stanici*
- Provozní režimy: textové hodnoty režimů pohybu / mapy / sečení
- Mapování a průběh: příznaky pokynů pro ruční mapování (potřeba přesunutí / převzetí, hranice uzavřena) a procento průběhu ukládání mapy

**Události a automatizace**
- **Entita události sekačky** — při každém významném přechodu vyvolá samostatnou událost (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), každou se surovými poli misie, takže automatizace reagují na *děje* bez dotazování stavu aktivity
- Blueprinty automatizací importovatelné jedním kliknutím (viz níže)

**Vymoženosti integrace**
- Automatické zjištění přes Zeroconf/mDNS
- Rekonfigurační tok (změna hostitele/IP bez opětovného přidání) a tok opětovného ověření
- **Hlášení opravy** — konkrétní karty v panelu pro nekompatibilní firmware a pro dlužnou údržbu nože / základnové stanice
- Stažení diagnostiky pro snadné hlášení chyb
- Přeloženo do 33 jazyků (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Potvrzené příkazy** — sečení po zónách čeká na potvrzení dp_119 ze zařízení a hlásí odmítnutí, místo aby tiše „uspělo“
- Lokální push komunikace přes MQTT — cloud není potřeba

### Podporované entity

| Platforma | Entity |
| --- | --- |
| Sekačka | Ovládání spuštění / pauzy / návratu s živou aktivitou |
| Kamera | Mapa s trasou, robotem a základnovou stanicí; čistá varianta „pouze mapa“ |
| Senzor | Úroveň baterie, stav baterie, stav teploty baterie, stav mapy, plocha mapy, výška sečení, rychlost sečení, provozní režim, poloha, celková doba sečení / úlohy / posečená plocha, plocha / průběh / doba trvání / typ úlohy aktuální session, probíhající úloha, závada, zbývající čas nože a základnové stanice, nejbližší naplánované spuštění, kompatibilita verzí, stav hlavního směru, režim napájení, důvod návratu do stanice, misie, podmisie, stav misie. *Diagnostika:* aktivní chyby, poslední událost, signál Wi-Fi, mobilní RSRP / RSRQ / typ, východ slunce, západ slunce, režimy pohybu / mapy / sečení, prahová hodnota dešťového senzoru, zpoždění pokračování po dešti, průběh ukládání mapy |
| Binární senzor | Nabíjení, navigace lokalizována, probíhá aktualizace firmwaru, vypínač, problém, detekován déšť, mapa detekována / lze vytvořit / probíhá záloha, ukládání dat, probíhá konverze dat. *Diagnostika:* mobilní síť zapnuta, vyhřívání proti zamlžení, osvětlení, denní světlo, extrémní počasí, detekce hran / sklonu, automatické pokračování po dešti, vynutit jednu základnovou stanici, vynutit mobilní síť, ruční mapování přesunutí / převzetí / hranice uzavřena, stavový příznak 134 (nedekódovaný) |
| Výběr | Výběr zóny, rychlost sečení, otáčky nože, režim hlavního směru, režim sečení okrajů pro vysokou trávu |
| Číslo | Výška sečení, vzdálenost pro sečení okrajů, rozestup pásů, úhel pro jeden směr, interval automatického otáčení úhlu, úhel prvního / druhého směru |
| Přepínač | Důkladné sečení rohů |
| Tlačítko | Sečení okrajů, vynulovat časovač nože, vynulovat časovač základnové stanice |
| Aktualizace | Verze firmwaru |
| Událost | Událost sekačky (sečení spuštěno / pauza / návrat / ve stanici / dokončeno / chyba) |
| Kalendář | Rozvrh sečení (nejbližší naplánované sečení) |

### Instalace

[![Otevřete svou instanci Home Assistant a otevřete repozitář v Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Metoda 1: HACS (doporučeno)
1. Ujistěte se, že je nainstalován [HACS](https://hacs.xyz/)
2. Pomocí tlačítka výše přidejte integraci do HACS
3. Otevřete HACS, vyhledejte „TerraMow“ a vyberte integraci
4. Nainstalujte ji a restartujte Home Assistant

#### Metoda 2: Ruční instalace
1. Zkopírujte složku `custom_components/terramow` do složky `/config/custom_components` svého Home Assistant
2. Restartujte Home Assistant
3. Přejděte do Nastavení → Zařízení a služby → Přidat integraci
4. Vyhledejte „TerraMow“ a projděte kroky konfigurace

### Konfigurace

Zařízení v místní síti jsou zjištěna automaticky přes Zeroconf — přijměte nalezené zařízení a zadejte heslo MQTT. Pro ruční nastavení jsou potřeba tyto parametry:

- **Hostitel**: IP adresa nebo název hostitele zařízení TerraMow
- **Heslo**: heslo MQTT pro ověření

**Změna nastavení později**
- *Rekonfigurovat* (Nastavení → Zařízení a služby → TerraMow → Rekonfigurovat): změňte hostitele/IP nebo heslo na místě, např. poté co sekačka získala novou adresu DHCP — integraci není třeba odebírat a znovu přidávat.
- *Možnosti* (Konfigurovat):
  - **Výstupní rozlišení mapy** — vyšší je ostřejší, ale stojí více přenosového pásma a CPU při každém vykreslení.
  - **Motiv mapy** — `light` nebo `dark`.
  - **Zobrazit posečenou plochu** — vyšrafuje již posečenou oblast pod linií trasy.
  - **Považovat každou dokončenou úlohu za 100 % hotovou** — některé firmwary ukončí úlohu bez signálu dokončení, takže průběh session nikdy nevyskočí na 100 %, i když je trávník posečený (čte se jako „přerušeno“). Zapněte tuto možnost, aby byla každá dokončená úloha považována za hotovou, stejně jako v aplikaci výrobce; nechte ji vypnutou, chcete-li zachovat poctivou hodnotu počitadla. *Výchozí: vypnuto.*
- Pokud se změní heslo zařízení, Home Assistant automaticky spustí tok *opětovného ověření*.

### Požadavky

- Home Assistant 2024.6.0 nebo novější (CI ověřuje integraci proti aktuálnímu vydání HA Core)
- Firmware TerraMow verze 6.6.0 nebo novější
- Aplikace TerraMow verze 1.6.0 nebo novější
- Živá mapa a trasa sečení vyžadují verzi 3 modulu HA ve firmwaru; u verze 2 (např. S800) funguje vše ostatní a senzor kompatibility verzí to hlásí

### Podporovaná zařízení

Tato integrace funguje s robotickými sekačkami TerraMow, které poskytují lokální rozhraní MQTT/HTTP — tedy s jakýmkoli modelem s požadovaným firmwarem. Používá se se sérií S od TerraMow, včetně **S800** (který hlásí verzi 2 modulu HA) a novějších kusů s verzí 3. Jakákoli sekačka TerraMow s firmwarem 6.6.0+ a aplikací 1.6.0+ by měla fungovat; senzor kompatibility verzí a hlášení opravy oznámí, pokud je firmware konkrétního kusu příliš starý pro danou funkci.

### Služby

#### `terramow.start_select_region`

Spustí sečení pro seznam vybraných podoblastí.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Vytvoří nebo odebere týdenní okno sečení v sekačce. Každý zápis je potvrzen
zařízením (potvrzení dp_119 plus zpětné čtení rozvrhu).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` očekává `item_id` okna (zobrazuje se jako uid kalendářní
události a vrací se při přidání okna).

> **Poznámka:** současný prodejní firmware zápis rozvrhu přes lokální MQTT zatím
> nepřijímá (aplikace výrobce používá Bluetooth/cloud). Dokud to firmware
> neumožní, použijte pro plánování na straně HA **blueprint sečení podle
> počasí**.

### Interaktivní karta mapy

Integrace přináší vlastní kartu Lovelace — registrovanou automaticky, bez ručního přidávání zdroje či zvláštní instalace frontendu HACS:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Trávník vykresluje vektorově (ostře při každém přiblížení, podle vašeho motivu HA): zóny, zakázané zóny, virtuální stěny, trasu sečení, základnovou stanici a živou polohu robota. Tažením posunete, kolečkem nebo gestem přiblížíte, dvojitým klepnutím znovu přizpůsobíte. **Klepněte na jednu či více zón** a stiskněte zobrazené tlačítko, aby se posekaly právě tyto zóny (na pozadí `terramow.start_select_region`).

**Tlačítko zobrazení** přepíná, co karta vykresluje nad trávníkem:

| Režim | Zobrazuje |
| --- | --- |
| **Obojí** | posečenou plochu *i* trasu sečení (výchozí, když je plocha zapnutá) |
| **Trasa** | pouze trasu aktuální a předchozí úlohy |
| **Plocha** | pouze vyšrafování posečené plochy, s průběhem po zónách |
| **Wi-Fi** | **teplotní mapu Wi-Fi** trávníku, kterou sekačka měří sama během sečení (zelená = silný signál). Mezery mezi jízdami se interpolují ze sousedních měření; půda, kterou sekačka nikdy neprojela, zůstává prázdná |

Zvolený režim se pro každou entitu pamatuje v prohlížeči. Možnosti a podrobnosti: viz [průvodce panely](en/dashboard.md#interactive-map-card) (v angličtině). Živá data mapy vyžadují verzi 3 modulu HA (stejně jako kamera mapy). Karta je také dostupná ve výběru karet panelu jako **TerraMow Map Card**, s plnohodnotným editorem rozhraní — bez YAML.

### Ukázkový panel

Hotové zobrazení Lovelace (živá mapa, ovládání, ukazatel průběhu, přehled stavu) a automatizace oznámení: viz [průvodce panely](en/dashboard.md) (v angličtině).

### Blueprinty automatizací

Blueprinty importovatelné jedním kliknutím pro nejčastější oznámení — každý se ptá jen na příslušnou entitu TerraMow a akci oznámení:

- **Sečení podle počasí** — spustí sečení podle vašeho rozvrhu a automaticky jej vynechá, když je zjištěn nebo předpovězen déšť
  [![Importovat blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Oznámení o problému** — když sekačka hlásí závadu
  [![Importovat blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Návrat kvůli dešti** — když se sekačka vrací do stanice kvůli dešti
  [![Importovat blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Sečení dokončeno** — když úloha sečení skončí
  [![Importovat blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Přímé použití entity události** — entita události sekačky je nejpružnější spouštěč. Její atribut `event_type` má jednu z hodnot `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error` a nese surová pole `mission`, `sub_mission`, `state`, `back_to_station_reason` a `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow dokončil sečení 🌱"
```

### Hlášení opravy

Integrace vytváří konkrétní hlášení opravy v Home Assistant (Nastavení → Zařízení a služby → Opravy), místo aby problémy skrývala v senzorech:

- **Nekompatibilní firmware / vyžadována aktualizace** — firmware je pro integraci (nebo pro konkrétní funkci) příliš starý. Vychází z kontroly kompatibility verzí; zmizí, jakmile se ohlásí kompatibilní firmware.
- **Nutná údržba nože** — nožový disk dosáhl doporučeného servisního intervalu 240 hodin. Vyčistěte nebo vyměňte nože a stiskněte tlačítko *Vynulovat časovač nože*, čímž hlášení odstraníte.
- **Nutná údržba základnové stanice** — základnová stanice dosáhla doporučeného servisního intervalu 30 dnů. Vyčistěte ji a stiskněte tlačítko *Vynulovat časovač základnové stanice*, čímž hlášení odstraníte.

### Diagnostika a řešení problémů

- **Stažení diagnostiky**: Nastavení → Zařízení a služby → TerraMow → nabídka se třemi tečkami → *Stáhnout diagnostiku* vytvoří pročištěný snímek JSON (stav zařízení, kompatibilita firmwaru, surové cache datových bodů) — přiložte jej k hlášením chyb.
- **Objevování nepodporovaných funkcí**: sekačka publikuje více datových bodů, než je zdokumentováno. První obsah každého neznámého datového bodu se jednou zapíše na úrovni INFO; zapněte pro integraci `terramow` protokolování na úrovni debug, abyste zachytili všechny. Pokud najdete datový bod pro chybějící funkci (např. alarm zvednutí, přepínač rozvrhu, chybové kódy), podělte se o něj v hlášení.

### Jak se aktualizují data

TerraMow je integrace typu **local push**. Sekačka provozuje MQTT broker přímo v zařízení; Home Assistant se k němu připojuje přes místní síť (bez cloudu) a přihlašuje se k odběru témat datových bodů zařízení, takže stavy entit se aktualizují v okamžiku, kdy sekačka ohlásí změnu, a ne v intervalu dotazování. Větší obsahy (mapa, živá trasa) se ohlašují přes MQTT a stahují na vyžádání přes lokální HTTP. Pokud sekačka spí nebo není v síti, připojení se opakuje s exponenciálním odstupem a entita sekačky vyjadřuje ztrátu spojení jako aktivitu `error`.

**Příkazy selhávají nahlas, nikoli tiše.** Když odešlete příkaz — `dock`, `start_mowing`, `pause`, sečení okrajů, sečení po zónách nebo jakoukoli změnu nastavení — je publikován s MQTT QoS 1 (krátké znovupřipojení jej tedy uloží do bufferu, místo aby jej zahodilo). Je-li sekačka offline či nedostupná, odmítne-li broker publikaci, nebo přijde-li příkaz rychleji, než jej zařízení dokáže přijmout, volání služby **selže s chybou**, místo aby tiše hlásilo úspěch. Automatizace, která zavolá `lawn_mower.dock`, když je sekačka nedostupná, tak vidí selhání (a může opakovat pokus nebo poslat oznámení), místo aby věřila, že se sekačka vrací, když příkaz nikdy neobdržela.

### Známá omezení

- **Žádný cloudový / vzdálený přístup** — Home Assistant musí být ve stejné místní síti jako sekačka; cloudová záložní cesta neexistuje.
- **Funkce závislé na firmwaru** — živá mapa a zobrazení trasy sečení vyžadují verzi 3 modulu HA; u verze 2 (např. S800) funguje vše ostatní a senzor kompatibility / hlášení opravy toto omezení oznámí.
- **Aktualizace firmwaru** se provádějí v aplikaci TerraMow, nikoli z Home Assistant; entita `update` firmwaru je pouze informativní.
- **Senzor polohy a čistá kamera mapy jsou ve výchozím stavu vypnuté** (senzor polohy se aktualizuje asi 2× za sekundu); pokud je potřebujete, zapněte je v nastavení entity.
- **Mnoho entit rozšířené diagnostiky je ve výchozím stavu vypnutých** a seskupených v kategorii *Diagnostika* (mobilní síť, východ/západ slunce, provozní režimy, příznaky ručního mapování atd.); vycházejí z datových bodů získaných reverzním inženýrstvím, zapínejte tedy jen ty, které potřebujete. Viz [poznámky k neoficiálním datovým bodům](en/developers/data_point_unofficial.md).
- Některé datové body zařízení nejsou zdokumentovány; neznámé se jednou zapíší do protokolu, aby pomohly objevit chybějící funkce.

### Případy použití

- **Oznámení související s deštěm** — dostanete zprávu, když se sekačka vrací do stanice kvůli dešti (viz blueprinty výše).
- **Upozornění na závady** — dostanete oznámení v okamžiku, kdy sekačka hlásí problém (uvízla, byla zvednuta, je zablokovaná).
- **Sečení po zónách z automatizací** — zavolejte `terramow.start_select_region`, abyste posekali konkrétní podoblasti podle rozvrhu nebo tlačítkem v panelu.
- **Připomínky údržby** — senzory zbývajícího času nože / základnové stanice a tlačítka pro vynulování umožňují automatizovat připomínky údržby.
- **Živá mapa v panelu** — zobrazte kameru mapy s polohou robota a trasou sečení (viz průvodce panely).

### Jazyky

Integrace je přeložena do: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Poznámky k aktualizaci

- **v0.5.0**: hodnoty stavů entit se změnily z velkých na malá písmena (např. `MISSION_IDLE` → `mission_idle`), aby splnily požadavky Home Assistant na překlady. Automatizace nebo šablony porovnávající surové textové stavy vyžadují jednorázovou úpravu; zobrazované názvy se nemění.

### Podpora

Pro podporu otevřete hlášení na [GitHubu](https://github.com/it-rec/TerraMowHA/issues).

### Informace pro vývojáře

Pro vývojáře, kteří chtějí této integraci porozumět nebo ji rozšířit (dokumentace pro vývojáře je v angličtině):

- [Průvodce pro přispěvatele](../CONTRIBUTING.md) — nastavení, požadavky na kvalitu (100 % pokrytí, `mypy --strict`, překlady), proces PR a vydání
- [Architektura](ARCHITECTURE.md) — vnitřní stavba: životní cyklus hubu, model vykonávání, katalog datových bodů, pipeline mapy/trasy
- [Průvodce pro vývojáře](en/developers.md) — protokol MQTT/HTTP zařízení „na drátě“
- [Co tento fork přidává nad upstream](UPSTREAM_DELTA.md)

Spuštění testů lokálně:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Licence

Tento projekt je licencován pod GNU General Public License v3.0 — podrobnosti najdete v souboru [LICENSE](../LICENSE).
