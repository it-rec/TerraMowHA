# TerraMow pro Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · **Čeština** · [中文](README_zh.md)

---

Toto je integrace pro Home Assistant určená pro robotické sekačky TerraMow.

### Funkce

**Ovládání**
- Entita sekačky: start, pauza a návrat do stanice
- Sečení zón: entita výběru zóny a služba `terramow.start_select_region`
- Tlačítko sečení okrajů
- Nastavení z Home Assistant: výška sečení, rychlost, rozestup, rychlost nožů, vzdálenost sečení okrajů, režim a úhly hlavního směru, důkladné sečení rohů, režim sečení okrajů ve vysoké trávě
- Údržba: tlačítka pro reset počítadel nožového disku a základnové stanice

**Monitorování**
- Kamera s živou mapou s trasou sečení, polohou robota a základnovou stanicí (plus čistá kamera pouze s mapou pro dashboardy, rozlišení lze nastavit v možnostech)
- Baterie: úroveň, stav nabíjení, stav teploty, připojená nabíječka, hlavní vypínač
- Průběh práce: plocha aktuální relace, průběh (%), doba trvání a typ práce; celkový čas sečení, počet prací a posečená plocha
- Stav: mise / dílčí mise / stav mise, provozní režim, režim napájení, důvod návratu do stanice, detekce deště, indikátor problému, indikátory ukládání dat a konverze dat
- Mapa: stav, plocha, příznaky detekována / lze sestavit / probíhá zálohování
- Plán: další naplánovaný start
- Entita aktualizace firmwaru, verze firmwaru na stránce zařízení a senzor kompatibility verzí
- Všechny entity se aktualizují okamžitě při push zprávách ze zařízení — žádné zpoždění způsobené dotazováním

**Pohodlí integrace**
- Automatické objevování přes Zeroconf/mDNS
- Proces rekonfigurace (změna hostitele/IP bez opětovného přidání) a proces opětovného ověření
- Stažení diagnostiky pro snadné hlášení chyb
- Přeloženo do 33 jazyků (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- Lokální push komunikace založená na MQTT — cloud není vyžadován

### Podporované entity

| Platforma | Entity |
| --- | --- |
| Sekačka | Ovládání start / pauza / návrat do stanice s aktivitou v reálném čase |
| Kamera | Mapa s trasou, robotem a základnovou stanicí; čistá varianta pouze s mapou |
| Senzor | Úroveň baterie, stav baterie, stav teploty baterie, stav mapy, plocha mapy, výška sečení, rychlost sečení, provozní režim, poloha, celkový čas sečení / počet prací / posečená plocha, plocha / průběh / doba trvání / typ práce aktuální relace, zbývající čas nožů a základnové stanice, další naplánovaný start, kompatibilita verzí, stav hlavního směru, režim napájení, důvod návratu do stanice, mise, dílčí mise, stav mise |
| Binární senzor | Nabíjení, navigace lokalizována, probíhá aktualizace firmwaru, hlavní vypínač, problém, detekován déšť, mapa detekována / lze sestavit / probíhá zálohování, ukládání dat, probíhá konverze dat |
| Výběr | Výběr zóny, rychlost sečení, rychlost nožů, režim hlavního směru, režim sečení okrajů ve vysoké trávě |
| Číslo | Výška sečení, vzdálenost sečení okrajů, rozestup sečení, úhel jednoho směru, interval automatického otáčení úhlu, úhel prvního / druhého směru |
| Přepínač | Důkladné sečení rohů |
| Tlačítko | Sečení okrajů, reset časovače nožů, reset časovače základnové stanice |
| Aktualizace | Verze firmwaru |

### Instalace

#### Metoda 1: HACS (doporučeno)
1. Ujistěte se, že je nainstalován [HACS](https://hacs.xyz/)
2. Pomocí tlačítka výše přidejte repozitář do HACS
3. Přejděte do HACS → Integrace → + → vyhledejte „TerraMow“
4. Nainstalujte a restartujte Home Assistant

#### Metoda 2: Ruční instalace
1. Zkopírujte složku `custom_components/terramow` do složky `/config/custom_components` vašeho Home Assistant
2. Restartujte Home Assistant
3. Přejděte do Nastavení → Zařízení a služby → Přidat integraci
4. Vyhledejte „TerraMow“ a postupujte podle kroků konfigurace

### Konfigurace

Zařízení v místní síti jsou automaticky objevena přes Zeroconf — přijměte objevené zařízení a zadejte heslo MQTT. Pro ruční nastavení jsou vyžadovány následující parametry:

- **Hostitel**: IP adresa nebo název hostitele zařízení TerraMow
- **Heslo**: heslo MQTT pro ověření

**Pozdější změna nastavení**
- *Rekonfigurace* (Nastavení → Zařízení a služby → TerraMow → Rekonfigurovat): změňte hostitele/IP nebo heslo přímo na místě, např. poté, co sekačka dostala novou adresu DHCP — integraci není třeba odebírat a znovu přidávat.
- *Možnosti* (Konfigurovat): nastavte výstupní rozlišení kamery s mapou. Vyšší hodnoty poskytují ostřejší obraz na dashboardu za cenu vyšší šířky pásma a zátěže CPU na jedno vykreslení.
- Pokud se heslo zařízení změní, Home Assistant automaticky spustí proces *opětovného ověření*.

### Požadavky

- Home Assistant 2023.9.3 nebo novější (testováno s 2025.1.1)
- Firmware TerraMow verze 6.6.0 nebo novější
- Aplikace TerraMow verze 1.6.0 nebo novější
- Živá mapa a trasa sečení vyžadují firmware s HA modulem verze 3; na verzi 2 (např. S800) funguje vše ostatní a senzor kompatibility verzí tuto skutečnost hlásí

### Služby

#### `terramow.start_select_region`

Spustí sečení pro seznam vybraných dílčích oblastí.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

### Diagnostika a řešení problémů

- **Stažení diagnostiky**: Nastavení → Zařízení a služby → TerraMow → nabídka se třemi tečkami → *Stáhnout diagnostiku* vytvoří anonymizovaný JSON snímek (stav zařízení, kompatibilita firmwaru, mezipaměti surových datových bodů) — připojte jej prosím k hlášením chyb.
- **Objevování nepodporovaných funkcí**: sekačka publikuje více datových bodů, než je zdokumentováno. První obsah každého neznámého datového bodu je jednou zaznamenán na úrovni INFO; zapněte ladicí protokolování pro integraci `terramow`, aby se zaznamenaly všechny. Pokud najdete datový bod pro chybějící funkci (např. alarm zvednutí, přepínač plánu, chybové kódy), sdílejte jej prosím v issue.

### Jazyky

Integrace je přeložena do těchto jazyků: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Poznámky k aktualizaci

- **v0.5.0**: hodnoty stavů entit se změnily z velkých na malá písmena (např. `MISSION_IDLE` → `mission_idle`), aby vyhovovaly požadavkům Home Assistant na překlady. Automatizace nebo šablony porovnávající surové stavové řetězce vyžadují jednorázovou aktualizaci; zobrazované názvy zůstávají beze změny.

### Podpora

Pro podporu otevřete issue na [GitHub](https://github.com/TerraMow/TerraMowHA/issues).

### Informace pro vývojáře

Vývojáři, kteří chtějí této integraci porozumět nebo ji rozšířit, naleznou informace v [příručce pro vývojáře](en/developers.md).

Spuštění sady testů lokálně:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Licence

Tento projekt je licencován pod licencí GNU General Public License v3.0 — podrobnosti naleznete v souboru [LICENSE](../LICENSE).
