# TerraMow dla Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="Logo TerraMow" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · **Polski** · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

To jest integracja Home Assistant dla robotów koszących TerraMow.

### Funkcje

**Sterowanie**
- Encja kosiarki: uruchamianie, wstrzymywanie i powrót do stacji dokującej
- Koszenie stref: encja wyboru strefy oraz usługa `terramow.start_select_region`
- **Schedule editing** — `terramow.add_schedule` / `terramow.delete_schedule` services write weekly mowing slots to the mower, confirmed against the device (acknowledgement + read-back); the calendar reflects changes immediately
- **Interactive map card** — pan/zoom vector lawn map for dashboards: live robot position (activity-tinted, with follow mode), on-card start / pause / dock controls, battery & job-progress chips, optional mowed-coverage shading, mowing path, base station, zones with tap-to-mow selection, forbidden areas and virtual walls; theme-aware, self-registering, with a UI editor (`custom:terramow-map-card`)
- Przycisk koszenia krawędzi
- Ustawienia z poziomu Home Assistant: wysokość koszenia, prędkość, rozstaw torów, prędkość ostrzy, odległość koszenia krawędzi, tryb i kąty kierunku głównego, dokładne koszenie narożników, tryb koszenia krawędzi w wysokiej trawie
- Konserwacja: przyciski resetowania liczników tarczy ostrzy i stacji bazowej

**Monitorowanie**
- Kamera z mapą na żywo pokazująca trasę koszenia, pozycję robota i stację bazową (plus przejrzysta kamera z samą mapą do paneli, rozdzielczość konfigurowalna w opcjach)
- Akumulator: poziom, stan ładowania, stan temperatury, podłączona ładowarka, przełącznik zasilania
- Postęp pracy: powierzchnia bieżącej sesji, postęp (%), czas trwania i typ zadania; łączny czas koszenia, liczba zadań i skoszona powierzchnia
- Status: misja / podmisja / stan misji, tryb pracy, tryb zasilania, powód powrotu do stacji, wykrywanie deszczu, wskaźnik problemu, wskaźniki zapisywania danych i konwersji danych
- Mapa: status, powierzchnia, flagi wykryta / możliwa do zbudowania / trwa tworzenie kopii zapasowej
- Harmonogram: następny zaplanowany start
- Encja aktualizacji oprogramowania układowego, wersja oprogramowania układowego na stronie urządzenia oraz czujnik zgodności wersji
- Wszystkie encje aktualizują się natychmiast po powiadomieniach push z urządzenia — bez opóźnień wynikających z odpytywania

**Wygoda korzystania z integracji**
- Automatyczne wykrywanie przez Zeroconf/mDNS
- Przepływ rekonfiguracji (zmiana hosta/IP bez ponownego dodawania) oraz przepływ ponownego uwierzytelniania
- Pobieranie diagnostyki ułatwiające zgłaszanie błędów
- Przetłumaczona na 33 języków (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- Lokalna komunikacja push oparta na MQTT — chmura nie jest wymagana

### Obsługiwane encje

| Platforma | Encje |
| --- | --- |
| Kosiarka | Sterowanie start / pauza / powrót do stacji z aktywnością na żywo |
| Kamera | Mapa z trasą, robotem i stacją bazową; przejrzysty wariant z samą mapą |
| Czujnik | Poziom akumulatora, stan akumulatora, stan temperatury akumulatora, status mapy, powierzchnia mapy, wysokość koszenia, prędkość koszenia, tryb pracy, pozycja, łączny czas koszenia / zadania / skoszona powierzchnia, powierzchnia / postęp / czas trwania / typ zadania bieżącej sesji, pozostały czas ostrzy i stacji bazowej, następny zaplanowany start, zgodność wersji, status kierunku głównego, tryb zasilania, powód powrotu do stacji, misja, podmisja, stan misji |
| Czujnik binarny | Ładowanie, nawigacja zlokalizowana, trwa aktualizacja oprogramowania układowego, przełącznik zasilania, problem, wykryto deszcz, mapa wykryta / możliwa do zbudowania / trwa tworzenie kopii zapasowej, zapisywanie danych, trwa konwersja danych |
| Wybór | Wybór strefy, prędkość koszenia, prędkość ostrzy, tryb kierunku głównego, tryb koszenia krawędzi w wysokiej trawie |
| Liczba | Wysokość koszenia, odległość koszenia krawędzi, rozstaw torów koszenia, kąt pojedynczego kierunku, interwał automatycznej zmiany kąta, kąt pierwszego / drugiego kierunku |
| Przełącznik | Dokładne koszenie narożników |
| Przycisk | Koszenie krawędzi, resetowanie licznika ostrzy, resetowanie licznika stacji bazowej |
| Aktualizacja | Wersja oprogramowania układowego |

### Instalacja

#### Metoda 1: HACS (zalecana)
1. Upewnij się, że [HACS](https://hacs.xyz/) jest zainstalowany
2. Użyj przycisku powyżej, aby dodać integrację do HACS
3. Przejdź do HACS → Integracje → + → Wyszukaj "TerraMow"
4. Zainstaluj i uruchom ponownie Home Assistant

#### Metoda 2: Instalacja ręczna
1. Skopiuj folder `custom_components/terramow` do folderu `/config/custom_components` swojego Home Assistant
2. Uruchom ponownie Home Assistant
3. Przejdź do Ustawienia → Urządzenia i usługi → Dodaj integrację
4. Wyszukaj "TerraMow" i postępuj zgodnie z krokami konfiguracji

### Konfiguracja

Urządzenia w sieci lokalnej są wykrywane automatycznie przez Zeroconf — zaakceptuj wykryte urządzenie i wprowadź hasło MQTT. Do konfiguracji ręcznej wymagane są następujące parametry:

- **Host**: adres IP lub nazwa hosta urządzenia TerraMow
- **Hasło**: hasło MQTT do uwierzytelniania

**Późniejsza zmiana ustawień**
- *Rekonfiguracja* (Ustawienia → Urządzenia i usługi → TerraMow → Rekonfiguruj): zmień hosta/IP lub hasło bezpośrednio, np. po tym, jak kosiarka otrzymała nowy adres DHCP — nie trzeba usuwać i ponownie dodawać integracji.
- *Opcje* (Konfiguruj): ustaw rozdzielczość wyjściową kamery z mapą. Wyższe wartości dają ostrzejszy obraz na panelu kosztem większego zużycia pasma i CPU na każde renderowanie.
- Jeśli hasło urządzenia się zmieni, Home Assistant automatycznie uruchamia przepływ *ponownego uwierzytelniania*.

### Wymagania

- Home Assistant 2024.6.0 lub nowszy (testowano z 2025.1.1)
- Oprogramowanie układowe TerraMow w wersji 6.6.0 lub nowszej
- Aplikacja TerraMow (APP) w wersji 1.6.0 lub nowszej
- Mapa na żywo i trasa koszenia wymagają wersji 3 modułu HA oprogramowania układowego; w wersji 2 (np. S800) wszystko pozostałe działa, a czujnik zgodności wersji to zgłasza

### Usługi

#### `terramow.start_select_region`

Rozpoczyna koszenie dla listy wybranych podregionów.

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

### Diagnostyka i rozwiązywanie problemów

- **Pobieranie diagnostyki**: Ustawienia → Urządzenia i usługi → TerraMow → menu z trzema kropkami → *Pobierz diagnostykę* generuje zanonimizowany zrzut JSON (stan urządzenia, zgodność oprogramowania układowego, pamięci podręczne surowych punktów danych) — prosimy o dołączanie go do zgłoszeń błędów.
- **Odkrywanie nieobsługiwanych funkcji**: kosiarka publikuje więcej punktów danych, niż jest udokumentowanych. Pierwszy ładunek każdego nieznanego punktu danych jest logowany jednorazowo na poziomie INFO; włącz logowanie debugowania dla integracji `terramow`, aby rejestrować je wszystkie. Jeśli znajdziesz punkt danych dla brakującej funkcji (np. alarm podniesienia, przełącznik harmonogramu, kody błędów), podziel się nim w zgłoszeniu (issue).

### Języki

Integracja jest przetłumaczona na: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Uwagi dotyczące aktualizacji

- **v0.5.0**: wartości stanów encji zmieniono z wielkich na małe litery (np. `MISSION_IDLE` → `mission_idle`), aby spełnić wymagania Home Assistant dotyczące tłumaczeń. Automatyzacje lub szablony porównujące surowe ciągi stanów wymagają jednorazowej aktualizacji; wyświetlane nazwy pozostają bez zmian.

### Wsparcie

Aby uzyskać pomoc, otwórz zgłoszenie (issue) na [GitHub](https://github.com/it-rec/TerraMowHA/issues).

### Informacje dla programistów

Programiści zainteresowani zrozumieniem lub rozszerzeniem tej integracji mogą zapoznać się z [Przewodnikiem programisty](en/developers.md).

Aby uruchomić zestaw testów lokalnie:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Licencja

Ten projekt jest objęty licencją GNU General Public License v3.0 — szczegóły znajdują się w pliku [LICENSE](../LICENSE).
