# TerraMow dla Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="Logo TerraMow" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · **Polski** · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

To jest integracja Home Assistant dla robotów koszących TerraMow.

### Funkcje

**Sterowanie**
- Encja kosiarki: start, pauza i powrót do stacji
- Koszenie strefowe: encja wyboru strefy oraz usługa `terramow.start_select_region`
- **Edycja harmonogramu** — usługi `terramow.add_schedule` / `terramow.delete_schedule` zapisują cotygodniowe okna koszenia w kosiarce i weryfikują je przez odczyt zwrotny. *Uwaga:* obecne oprogramowanie sprzedażne nie przyjmuje jeszcze zapisu harmonogramu przez lokalne MQTT (aplikacja producenta korzysta z Bluetooth/chmury) — do czasu wsparcia w firmware użyj **blueprintu koszenia zależnego od pogody** do planowania po stronie HA
- **Interaktywna karta mapy** — wektorowa mapa trawnika z przesuwaniem i powiększaniem dla paneli: pozycja robota na żywo (barwiona zgodnie z aktywnością, z trybem podążania), przyciski start / pauza / stacja bezpośrednio na karcie, plakietki akumulatora / postępu / pozostałego czasu, cieniowanie skoszonej powierzchni z postępem dla każdej strefy, ścieżka koszenia, stacja bazowa, strefy z wyborem przez dotknięcie do koszenia, strefy zakazane i wirtualne ściany, aktywne usterki oznaczone w miejscu wystąpienia oraz **mapa cieplna Wi-Fi** trawnika; **przycisk widoku** przełącza Oba / Ścieżka / Powierzchnia / Wi-Fi. Zgodna z motywami, rejestruje się sama, z edytorem graficznym (`custom:terramow-map-card`)
- Przycisk koszenia krawędzi
- Ustawienia z Home Assistant: wysokość koszenia, prędkość, odstęp pasów, prędkość noża, odległość cięcia krawędzi, tryb i kąty kierunku głównego, dokładne koszenie narożników, tryb koszenia krawędzi dla wysokiej trawy
- Konserwacja: przyciski zerowania liczników tarczy nożowej i stacji bazowej

**Monitorowanie**
- Kamera mapy na żywo ze ścieżką koszenia, pozycją robota i stacją bazową (plus czysta kamera „tylko mapa” dla paneli, rozdzielczość konfigurowalna w opcjach)
- Akumulator: poziom, stan ładowania, stan temperatury, ładowarka podłączona, wyłącznik zasilania
- Postęp: powierzchnia bieżącej sesji, postęp (%), czas trwania i typ zadania; łączny czas koszenia, liczba zadań i skoszona powierzchnia
- Stan: misja / podmisja / stan misji, tryb pracy, tryb zasilania, powód powrotu do stacji, wykrywanie deszczu, wskaźnik problemu, wskaźniki zapisu i konwersji danych
- **Czujnik usterki** — aktywna usterka jako czytelny tekst (np. *Kosiarka zablokowana*, *Kosiarka podniesiona* albo *OK*), aby powiadomienie lub asystent głosowy mógł powiedzieć, co jest nie tak, bez przetwarzania atrybutu szablonem
- Czujnik trwającego zadania (utrzymuje aktywną misję również podczas przerw w sygnale obecności) oraz czujnik siły sygnału Wi-Fi po stronie kosiarki
- Mapa: stan, powierzchnia, flagi wykryta / możliwa do zbudowania / kopia zapasowa w toku
- Harmonogram: czujnik najbliższego zaplanowanego startu oraz **kalendarz harmonogramu koszenia** tylko do odczytu (najbliższe koszenie pojawia się na karcie kalendarza)
- Encja aktualizacji oprogramowania, wersja oprogramowania na stronie urządzenia oraz czujnik zgodności wersji
- Wszystkie encje aktualizują się natychmiast po wysyłce z urządzenia — bez opóźnienia odpytywania

**Zaawansowana diagnostyka** (punkty danych odtworzone metodą inżynierii odwrotnej — w większości w kategorii encji *Diagnostyka*, wiele domyślnie wyłączonych; zobacz [notatki o nieoficjalnych punktach danych](en/developers/data_point_unofficial.md))
- Błędy i zdarzenia: liczba aktywnych błędów (z surową listą błędów jako atrybutem) oraz kod ostatniego zdarzenia. Znane kody błędów są tłumaczone na czytelny tekst dzięki katalogowi tworzonemu przez społeczność (`error_codes.py`), który dekoduje również najnowszy kod błędu kosiarki (dp_115)
- Sieć komórkowa / 4G: modem włączony, siła sygnału (RSRP / RSRQ), typ połączenia oraz odczyt *wymuś sieć komórkową*
- Środowisko: wschód / zachód słońca raportowane przez urządzenie, stan światła dziennego, ogrzewanie przeciwmgielne, oświetlenie oraz ostrzeżenie o ekstremalnej pogodzie (z opcjonalnym adresem URL z informacjami)
- Bezpieczeństwo i ustawienia zaawansowane: stan wykrywania uskoków i nachylenia, próg czujnika deszczu, automatyczne wznowienie po deszczu i jego opóźnienie oraz odczyt *wymuś jedną stację bazową*
- Tryby pracy: ciągi znaków trybów ruchu / mapy / koszenia
- Mapowanie i postęp: flagi wskazówek dla mapowania ręcznego (potrzebne przepozycjonowanie / przejęcie, granica zamknięta) oraz procent postępu zapisu mapy

**Zdarzenia i automatyzacja**
- **Encja zdarzeń kosiarki** — wywołuje osobne zdarzenie przy każdym istotnym przejściu (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), każde z surowymi polami misji, dzięki czemu automatyzacje reagują na *zdarzenia* bez odpytywania stanu aktywności
- Blueprinty automatyzacji do importu jednym kliknięciem (zobacz poniżej)

**Udogodnienia integracji**
- Automatyczne wykrywanie przez Zeroconf/mDNS
- Przepływ rekonfiguracji (zmiana hosta/IP bez ponownego dodawania) i przepływ ponownego uwierzytelnienia
- **Zgłoszenia naprawy** — konkretne karty w panelu dla niezgodnego oprogramowania oraz zaległej konserwacji noża / stacji bazowej
- Pobieranie diagnostyki dla łatwiejszego zgłaszania błędów
- Przetłumaczona na 33 języki (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Potwierdzone polecenia** — koszenie strefowe czeka na potwierdzenie dp_119 z urządzenia i raportuje odrzucenia, zamiast po cichu „kończyć się sukcesem”
- Lokalna komunikacja push oparta na MQTT — chmura nie jest potrzebna

### Obsługiwane encje

| Platforma | Encje |
| --- | --- |
| Kosiarka | Sterowanie start / pauza / stacja z aktywnością na żywo |
| Kamera | Mapa ze ścieżką, robotem i stacją bazową; czysty wariant „tylko mapa” |
| Czujnik | Poziom akumulatora, stan akumulatora, stan temperatury akumulatora, stan mapy, powierzchnia mapy, wysokość koszenia, prędkość koszenia, tryb pracy, pozycja, łączny czas koszenia / zadania / skoszona powierzchnia, powierzchnia / postęp / czas trwania / typ zadania bieżącej sesji, trwające zadanie, usterka, pozostały czas noża i stacji bazowej, najbliższy zaplanowany start, zgodność wersji, stan kierunku głównego, tryb zasilania, powód powrotu do stacji, misja, podmisja, stan misji. *Diagnostyka:* aktywne błędy, ostatnie zdarzenie, sygnał Wi-Fi, komórkowy RSRP / RSRQ / typ, wschód słońca, zachód słońca, tryby ruchu / mapy / koszenia, próg czujnika deszczu, opóźnienie wznowienia po deszczu, postęp zapisu mapy |
| Czujnik binarny | Ładowanie, nawigacja zlokalizowana, aktualizacja oprogramowania w toku, wyłącznik zasilania, problem, wykryto deszcz, mapa wykryta / możliwa do zbudowania / kopia zapasowa w toku, zapis danych, konwersja danych w toku. *Diagnostyka:* sieć komórkowa włączona, ogrzewanie przeciwmgielne, oświetlenie, światło dzienne, ekstremalna pogoda, wykrywanie uskoków / nachylenia, automatyczne wznowienie po deszczu, wymuś jedną stację bazową, wymuś sieć komórkową, mapowanie ręczne przepozycjonowanie / przejęcie / granica zamknięta, flaga stanu 134 (nierozszyfrowana) |
| Wybór | Wybór strefy, prędkość koszenia, prędkość noża, tryb kierunku głównego, tryb koszenia krawędzi dla wysokiej trawy |
| Liczba | Wysokość koszenia, odległość cięcia krawędzi, odstęp pasów, kąt dla jednego kierunku, interwał automatycznego obrotu kąta, kąt pierwszego / drugiego kierunku |
| Przełącznik | Dokładne koszenie narożników |
| Przycisk | Koszenie krawędzi, zeruj licznik noża, zeruj licznik stacji bazowej |
| Aktualizacja | Wersja oprogramowania |
| Zdarzenie | Zdarzenie kosiarki (koszenie rozpoczęte / pauza / powrót / w stacji / zakończone / błąd) |
| Kalendarz | Harmonogram koszenia (najbliższe zaplanowane koszenie) |

### Instalacja

[![Otwórz swoją instancję Home Assistant i otwórz repozytorium w Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Metoda 1: HACS (zalecana)
1. Upewnij się, że [HACS](https://hacs.xyz/) jest zainstalowany
2. Użyj przycisku powyżej, aby dodać integrację do HACS
3. Otwórz HACS, wyszukaj „TerraMow” i wybierz integrację
4. Zainstaluj ją i uruchom ponownie Home Assistant

#### Metoda 2: Instalacja ręczna
1. Skopiuj katalog `custom_components/terramow` do katalogu `/config/custom_components` swojego Home Assistant
2. Uruchom ponownie Home Assistant
3. Przejdź do Ustawienia → Urządzenia i usługi → Dodaj integrację
4. Wyszukaj „TerraMow” i wykonaj kroki konfiguracji

### Konfiguracja

Urządzenia w sieci lokalnej są wykrywane automatycznie przez Zeroconf — zaakceptuj wykryte urządzenie i wpisz hasło MQTT. Do konfiguracji ręcznej potrzebne są następujące parametry:

- **Host**: adres IP lub nazwa hosta urządzenia TerraMow
- **Hasło**: hasło MQTT do uwierzytelnienia

**Późniejsza zmiana ustawień**
- *Rekonfiguracja* (Ustawienia → Urządzenia i usługi → TerraMow → Rekonfiguruj): zmień host/IP lub hasło na miejscu, np. po tym jak kosiarka otrzymała nowy adres DHCP — nie trzeba usuwać i ponownie dodawać integracji.
- *Opcje* (Konfiguruj):
  - **Rozdzielczość wyjściowa mapy** — wyższa jest ostrzejsza, ale kosztuje więcej pasma i CPU na każde renderowanie.
  - **Motyw mapy** — `light` lub `dark`.
  - **Pokaż skoszoną powierzchnię** — cieniuje już skoszony obszar pod linią ścieżki.
  - **Traktuj każde zakończone zadanie jako ukończone w 100 %** — niektóre wersje oprogramowania kończą zadanie bez sygnału ukończenia, więc postęp sesji nigdy nie osiąga 100 %, mimo że trawnik jest skoszony (odczytywane jako „przerwane”). Włącz tę opcję, aby traktować każde zakończone zadanie jako ukończone, tak jak robi to aplikacja producenta; zostaw wyłączoną, aby zachować uczciwą wartość licznika. *Domyślnie: wyłączone.*
- Jeśli hasło urządzenia się zmieni, Home Assistant automatycznie uruchomi przepływ *ponownego uwierzytelnienia*.

### Wymagania

- Home Assistant 2024.6.0 lub nowszy (CI weryfikuje integrację względem bieżącego wydania HA Core)
- Oprogramowanie TerraMow w wersji 6.6.0 lub nowszej
- Aplikacja TerraMow w wersji 1.6.0 lub nowszej
- Mapa na żywo i ścieżka koszenia wymagają wersji 3 modułu HA w oprogramowaniu; przy wersji 2 (np. S800) wszystko pozostałe działa, a czujnik zgodności wersji to zgłasza

### Obsługiwane urządzenia

Ta integracja działa z robotami koszącymi TerraMow, które udostępniają lokalny interfejs MQTT/HTTP — czyli z każdym modelem z wymaganym oprogramowaniem. Jest używana z serią S TerraMow, w tym z **S800** (który raportuje wersję 2 modułu HA) oraz z nowszymi egzemplarzami w wersji 3. Każda kosiarka TerraMow z oprogramowaniem 6.6.0+ i aplikacją 1.6.0+ powinna działać; czujnik zgodności wersji i zgłoszenie naprawy informują, czy oprogramowanie danego egzemplarza jest zbyt stare dla konkretnej funkcji.

### Usługi

#### `terramow.start_select_region`

Rozpoczyna koszenie listy wybranych podobszarów.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Tworzy lub usuwa cotygodniowe okno koszenia w kosiarce. Każdy zapis jest
potwierdzany przez urządzenie (potwierdzenie dp_119 oraz odczyt zwrotny
harmonogramu).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` przyjmuje `item_id` okna (wyświetlane jako uid zdarzenia
kalendarza i zwracane przy dodaniu okna).

> **Uwaga:** obecne oprogramowanie sprzedażne nie przyjmuje jeszcze zapisu
> harmonogramu przez lokalne MQTT (aplikacja producenta korzysta z
> Bluetooth/chmury). Do czasu wsparcia w firmware użyj **blueprintu koszenia
> zależnego od pogody** do planowania po stronie HA.

### Interaktywna karta mapy

Integracja dostarcza własną kartę Lovelace — rejestrowaną automatycznie, bez ręcznego dodawania zasobu ani osobnej instalacji frontendu HACS:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Rysuje trawnik wektorowo (ostro przy każdym powiększeniu, zgodnie z motywem HA): strefy, strefy zakazane, wirtualne ściany, ścieżkę koszenia, stację bazową i pozycję robota na żywo. Przeciągnij, aby przesunąć, kółko lub uszczypnięcie, aby powiększyć, dwukrotne dotknięcie, aby dopasować ponownie. **Dotknij jednej lub kilku stref** i naciśnij pojawiający się przycisk, aby skosić dokładnie te strefy (pod spodem `terramow.start_select_region`).

**Przycisk widoku** przełącza to, co karta nakłada na trawnik:

| Tryb | Pokazuje |
| --- | --- |
| **Oba** | skoszoną powierzchnię *i* ścieżkę koszenia (domyślnie, gdy powierzchnia jest włączona) |
| **Ścieżka** | tylko ścieżkę bieżącego i poprzedniego zadania |
| **Powierzchnia** | tylko cieniowanie skoszonej powierzchni, z postępem dla każdej strefy |
| **Wi-Fi** | **mapę cieplną Wi-Fi** trawnika, mierzoną przez samą kosiarkę podczas koszenia (zielony = mocny). Luki między przejazdami są interpolowane z sąsiednich pomiarów; grunt, po którym kosiarka nigdy nie jechała, pozostaje pusty |

Wybrany tryb jest zapamiętywany dla każdej encji w przeglądarce. Opcje i szczegóły: zobacz [przewodnik po panelach](en/dashboard.md#interactive-map-card) (w języku angielskim). Dane mapy na żywo wymagają wersji 3 modułu HA (tak jak kamera mapy). Karta jest też dostępna w wyborze kart panelu jako **TerraMow Map Card**, z pełnym edytorem graficznym — bez YAML.

### Przykładowy panel

Gotowy widok Lovelace (mapa na żywo, sterowanie, wskaźnik postępu, przegląd stanu) oraz automatyzacje powiadomień: zobacz [przewodnik po panelach](en/dashboard.md) (w języku angielskim).

### Blueprinty automatyzacji

Blueprinty do importu jednym kliknięciem dla najczęstszych powiadomień — każdy pyta tylko o odpowiednią encję TerraMow i akcję powiadomienia:

- **Koszenie zależne od pogody** — rozpoczyna koszenie zgodnie z Twoim harmonogramem, automatycznie pomijane, gdy wykryto lub przewidziano deszcz
  [![Importuj blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Powiadomienie o problemie** — gdy kosiarka zgłasza usterkę
  [![Importuj blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Powrót z powodu deszczu** — gdy kosiarka wraca do stacji z powodu deszczu
  [![Importuj blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Koszenie zakończone** — gdy zadanie koszenia się kończy
  [![Importuj blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Bezpośrednie użycie encji zdarzeń** — encja zdarzeń kosiarki jest najbardziej elastycznym wyzwalaczem. Jej atrybut `event_type` przyjmuje jedną z wartości `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error` i przenosi surowe pola `mission`, `sub_mission`, `state`, `back_to_station_reason` oraz `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow zakończył koszenie 🌱"
```

### Zgłoszenia naprawy

Integracja tworzy konkretne zgłoszenia naprawy w Home Assistant (Ustawienia → Urządzenia i usługi → Naprawy), zamiast ukrywać problemy w czujnikach:

- **Niezgodne oprogramowanie / wymagana aktualizacja** — oprogramowanie jest zbyt stare dla integracji (lub dla konkretnej funkcji). Wynika ze sprawdzenia zgodności wersji; znika, gdy zgłosi się zgodne oprogramowanie.
- **Wymagana konserwacja noża** — tarcza nożowa osiągnęła zalecany interwał serwisowy 240 godzin. Wyczyść lub wymień noże i naciśnij przycisk *Zeruj licznik noża*, aby usunąć zgłoszenie.
- **Wymagana konserwacja stacji bazowej** — stacja bazowa osiągnęła zalecany interwał serwisowy 30 dni. Wyczyść ją i naciśnij przycisk *Zeruj licznik stacji bazowej*, aby usunąć zgłoszenie.

### Diagnostyka i rozwiązywanie problemów

- **Pobieranie diagnostyki**: Ustawienia → Urządzenia i usługi → TerraMow → menu z trzema kropkami → *Pobierz diagnostykę* tworzy oczyszczony zrzut JSON (stan urządzenia, zgodność oprogramowania, surowe pamięci punktów danych) — dołącz go do zgłoszeń błędów.
- **Odkrywanie nieobsługiwanych funkcji**: kosiarka publikuje więcej punktów danych, niż jest udokumentowane. Pierwszy pakiet każdego nieznanego punktu danych jest raz zapisywany na poziomie INFO; włącz logowanie debugowania dla integracji `terramow`, aby zapisać je wszystkie. Jeśli znajdziesz punkt danych dla brakującej funkcji (np. alarm podniesienia, przełącznik harmonogramu, kody błędów), podziel się nim w zgłoszeniu.

### Jak aktualizowane są dane

TerraMow to integracja typu **local push**. Kosiarka udostępnia broker MQTT na urządzeniu; Home Assistant łączy się z nim bezpośrednio przez sieć lokalną (bez chmury) i subskrybuje tematy punktów danych urządzenia, więc stany encji aktualizują się w chwili, gdy kosiarka zgłasza zmianę, a nie w interwale odpytywania. Większe pakiety (mapa, ścieżka na żywo) są ogłaszane przez MQTT i pobierane na żądanie przez lokalne HTTP. Jeśli kosiarka jest uśpiona lub poza siecią, połączenie jest ponawiane z wykładniczym opóźnieniem, a encja kosiarki pokazuje utratę połączenia jako aktywność `error`.

**Polecenia zawodzą głośno, nie po cichu.** Gdy wysyłasz polecenie — `dock`, `start_mowing`, `pause`, koszenie krawędzi, koszenie strefowe lub dowolną zmianę ustawień — jest ono publikowane z MQTT QoS 1 (krótkie ponowne połączenie buforuje je, zamiast odrzucić). Jeśli kosiarka jest offline lub nieosiągalna, broker odrzuci publikację, albo polecenie przyjdzie szybciej, niż urządzenie potrafi je przyjąć, wywołanie usługi **kończy się błędem**, zamiast po cichu raportować sukces. Dzięki temu automatyzacja wywołująca `lawn_mower.dock`, gdy kosiarka jest nieosiągalna, widzi niepowodzenie (i może ponowić próbę lub powiadomić), zamiast wierzyć, że kosiarka wraca, choć nigdy nie otrzymała polecenia.

### Znane ograniczenia

- **Brak dostępu przez chmurę / zdalnie** — Home Assistant musi być w tej samej sieci lokalnej co kosiarka; nie ma wariantu awaryjnego przez chmurę.
- **Funkcje zależne od oprogramowania** — mapa na żywo i widok ścieżki koszenia wymagają wersji 3 modułu HA; przy wersji 2 (np. S800) wszystko pozostałe działa, a czujnik zgodności / zgłoszenie naprawy informuje o ograniczeniu.
- **Aktualizacje oprogramowania** wykonuje się w aplikacji TerraMow, nie z Home Assistant; encja `update` oprogramowania jest wyłącznie informacyjna.
- **Czujnik pozycji i czysta kamera mapy są domyślnie wyłączone** (czujnik pozycji aktualizuje się z częstotliwością około 2 Hz); włącz je w ustawieniach encji, jeśli są potrzebne.
- **Wiele encji zaawansowanej diagnostyki jest domyślnie wyłączonych** i zgrupowanych w kategorii *Diagnostyka* (sieć komórkowa, wschód/zachód słońca, tryby pracy, flagi mapowania ręcznego itd.); pochodzą z punktów danych odtworzonych metodą inżynierii odwrotnej, więc włącz tylko te, których potrzebujesz. Zobacz [notatki o nieoficjalnych punktach danych](en/developers/data_point_unofficial.md).
- Niektóre punkty danych urządzenia nie są udokumentowane; nieznane są raz zapisywane w logu, aby pomóc w odkrywaniu brakujących funkcji.

### Przykłady zastosowań

- **Powiadomienia związane z deszczem** — otrzymaj powiadomienie, gdy kosiarka wraca do stacji z powodu deszczu (zobacz blueprinty powyżej).
- **Alerty usterek** — otrzymaj powiadomienie w chwili, gdy kosiarka zgłasza problem (zablokowana, podniesiona, zatrzymana przez przeszkodę).
- **Koszenie strefowe z automatyzacji** — wywołaj `terramow.start_select_region`, aby skosić wybrane podobszary według harmonogramu lub przyciskiem w panelu.
- **Przypomnienia o konserwacji** — czujniki pozostałego czasu noża / stacji bazowej oraz przyciski zerowania pozwalają zautomatyzować przypomnienia o konserwacji.
- **Mapa na żywo w panelu** — pokaż kamerę mapy z pozycją robota i ścieżką koszenia (zobacz przewodnik po panelach).

### Języki

Integracja jest przetłumaczona na: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Uwagi dotyczące aktualizacji

- **v0.5.0**: wartości stanów encji zmieniono z wielkich na małe litery (np. `MISSION_IDLE` → `mission_idle`), aby spełnić wymagania tłumaczeń Home Assistant. Automatyzacje lub szablony porównujące surowe ciągi stanów wymagają jednorazowej korekty; wyświetlane nazwy pozostają bez zmian.

### Wsparcie

Aby uzyskać pomoc, otwórz zgłoszenie na [GitHubie](https://github.com/it-rec/TerraMowHA/issues).

### Informacje dla programistów

Dla programistów, którzy chcą zrozumieć lub rozszerzyć tę integrację (dokumentacja dla programistów jest w języku angielskim):

- [Przewodnik dla współtwórców](../CONTRIBUTING.md) — konfiguracja, wymagania jakościowe (100 % pokrycia, `mypy --strict`, tłumaczenia), proces PR i wydań
- [Architektura](ARCHITECTURE.md) — wewnętrzna budowa: cykl życia huba, model wykonania, katalog punktów danych, potok mapy/ścieżki
- [Przewodnik programisty](en/developers.md) — protokół MQTT/HTTP urządzenia „na łączu”
- [Co ten fork dodaje względem upstreamu](UPSTREAM_DELTA.md)

Aby uruchomić testy lokalnie:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Licencja

Ten projekt jest licencjonowany na warunkach GNU General Public License v3.0 — szczegóły w pliku [LICENSE](../LICENSE).
