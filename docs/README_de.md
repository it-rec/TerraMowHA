# TerraMow für Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · **Deutsch** · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Dies ist eine Home-Assistant-Integration für TerraMow-Mähroboter.

### Funktionen

**Steuerung**
- Rasenmäher-Entität: Starten, Pausieren und Andocken
- Zonenmähen: Zonenauswahl-Entität und der Dienst `terramow.start_select_region`
- **Zeitplan bearbeiten** — die Dienste `terramow.add_schedule` / `terramow.delete_schedule` schreiben wöchentliche Mähfenster auf den Mäher und verifizieren sie durch Rücklesen. *Hinweis:* Die aktuelle Seriennummern-Firmware akzeptiert Zeitplan-Schreibvorgänge über lokales MQTT noch nicht (die Hersteller-App nutzt Bluetooth/Cloud) — bis die Firmware das unterstützt, verwenden Sie das **Blueprint für wetterabhängiges Mähen** für die Planung auf HA-Seite
- **Interaktive Kartenkarte** — Vektorkarte des Rasens mit Verschieben/Zoomen für Dashboards: Live-Roboterposition (nach Aktivität eingefärbt, mit Folgemodus), Bedienelemente für Starten / Pausieren / Andocken direkt auf der Karte, Chips für Akku / Auftragsfortschritt / Restzeit, Schattierung der gemähten Fläche mit Fortschritt pro Zone, Mähpfad, Basisstation, Zonen mit Antippen-zum-Mähen, Sperrzonen und virtuelle Wände, aktive Störungen an ihrem Ort markiert sowie eine **WLAN-Heatmap** des Rasens; eine **Ansichtsschaltfläche** wechselt zwischen Beides / Weg / Fläche / WLAN. Theme-fähig, selbstregistrierend, mit UI-Editor (`custom:terramow-map-card`)
- Taste für Kantenschnitt
- Einstellungen aus Home Assistant: Mähhöhe, Geschwindigkeit, Bahnabstand, Messerdrehzahl, Kantenschnittabstand, Hauptrichtungsmodus und -winkel, gründliches Eckenmähen, Kantenschnittmodus für hohes Gras
- **Schreibbare erweiterte Einstellungen** (dp_150, *standardmäßig deaktiviert*) — Schalter für Klippenerkennung, Hangerkennung und Auto-Fortsetzen nach Regen sowie Zahlenwerte für Regensensor-Schwelle und Fortsetzungs-Verzögerung. Das Schreibformat ist undokumentiert, deshalb wird jede Änderung gegen die Rückmeldung des Mähers geprüft und **schlägt sichtbar fehl**, wenn die Firmware sie ignoriert; die schreibgeschützten Diagnose-Sensoren bleiben in jedem Fall erhalten
- Wartung: Reset-Tasten für die Zähler von Messerteller und Basisstation

**Überwachung**
- Live-Kartenkamera mit Mähpfad, Roboterposition und Basisstation (plus eine reine Kartenkamera für Dashboards, Auflösung über die Optionen konfigurierbar)
- Akku: Ladestand, Ladezustand, Temperaturzustand, Ladegerät verbunden, Netzschalter
- Auftragsfortschritt: Fläche der aktuellen Sitzung, Fortschritt (%), Dauer und Auftragstyp; Gesamtmähzeit, Auftragsanzahl und gemähte Fläche
- Status: Mission / Untermission / Missionszustand, Betriebsmodus, Leistungsmodus, Grund für die Rückkehr zur Station, Regenerkennung, Problemanzeige, Anzeigen für Datenspeicherung und Datenkonvertierung
- **Störungssensor** — die aktive Störung als lesbarer Text (z. B. *Mäher steckengeblieben*, *Mäher angehoben* oder *OK*), sodass eine Benachrichtigung oder ein Sprachassistent das Problem benennen kann, ohne ein Attribut per Template auszuwerten
- Sensor für den laufenden Auftrag (hält die aktive Mission auch über Lücken im Heartbeat hinweg) und ein Sensor für die WLAN-Signalstärke des Mähers
- Karte: Status, Fläche, Flags für erkannt / erstellbar / Sicherung läuft
- Zeitplan: Sensor für den nächsten geplanten Start und ein schreibgeschützter **Mähzeitplan-Kalender** (der nächste Mähvorgang erscheint auf der Kalenderkarte)
- Firmware-Update-Entität, Firmware-Version auf der Geräteseite und Sensor für die Versionskompatibilität
- Alle Entitäten werden bei Geräte-Pushes sofort aktualisiert — keine Polling-Verzögerung

**Erweiterte Diagnose** (rückentwickelte Datenpunkte — überwiegend in der Entitätskategorie *Diagnose*, viele standardmäßig deaktiviert; siehe die [Notizen zu unoffiziellen Datenpunkten](en/developers/data_point_unofficial.md))
- Fehler & Ereignisse: Anzahl aktiver Fehler (mit der Rohfehlerliste als Attribut) und Code des letzten Ereignisses. Bekannte Fehlercodes werden über einen von der Community zusammengetragenen Katalog (`error_codes.py`) in lesbaren Text übersetzt, der auch den neuesten Fehlercode des Mähers (dp_115) dekodiert
- Mobilfunk / 4G: Modem aktiviert, Signalstärke (RSRP / RSRQ), Verbindungstyp und eine Anzeige für *Mobilfunknetz erzwingen*
- Umgebung: vom Gerät gemeldeter Sonnenauf- / -untergang, Tageslichtzustand, Beschlagheizung, Beleuchtung und eine Extremwetterwarnung (mit optionaler Info-URL)
- Sicherheit & erweiterte Einstellungen: Zustand der Absturz- und Neigungserkennung, Schwellwert des Regensensors, automatische Fortsetzung nach Regen und Verzögerung dafür sowie eine Anzeige für *einzelne Basisstation erzwingen*
- Betriebsmodi: Zeichenketten für Bewegungs- / Karten- / Mähmodus
- Kartierung & Fortschritt: Hinweisflags für die manuelle Kartierung (Neupositionierung / Übernahme erforderlich, Grenze geschlossen) und ein Prozentwert für den Kartenspeicher-Fortschritt

**Ereignisse & Automatisierung**
- **Mäher-Ereignis-Entität** — löst bei jedem nennenswerten Übergang ein einzelnes Ereignis aus (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), jeweils mit den Roh-Missionsfeldern, sodass Automatisierungen auf *Vorgänge* reagieren, ohne den Aktivitätszustand abzufragen
- Automatisierungs-Blueprints zum Import mit einem Klick (siehe unten)

**Komfortfunktionen der Integration**
- Automatische Erkennung über Zeroconf/mDNS
- Rekonfigurations-Flow (Host/IP ändern ohne erneutes Hinzufügen) und Reauthentifizierungs-Flow
- **Reparaturhinweise** — handlungsorientierte Dashboard-Karten für inkompatible Firmware und für fällige Wartung von Messer / Basisstation
- Diagnose-Download für einfache Fehlerberichte
- In 33 Sprachen übersetzt (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Bestätigte Befehle** — das Zonenmähen wartet auf die dp_119-Bestätigung des Geräts und meldet Ablehnungen, anstatt stillschweigend „Erfolg“ zu melden
- Lokale Push-Kommunikation auf MQTT-Basis — keine Cloud erforderlich

### Unterstützte Entitäten

| Plattform | Entitäten |
| --- | --- |
| Rasenmäher | Steuerung für Starten / Pausieren / Andocken mit Live-Aktivität |
| Kamera | Karte mit Pfad, Roboter und Basisstation; reine Kartenvariante |
| Sensor | Akkustand, Akkuzustand, Akkutemperaturzustand, Kartenstatus, Kartenfläche, Mähhöhe, Mähgeschwindigkeit, Betriebsmodus, Position, Gesamtmähzeit / Aufträge / gemähte Fläche, Fläche / Fortschritt / Dauer / Auftragstyp der aktuellen Sitzung, laufender Auftrag, Störung, verbleibende Zeit für Messer und Basisstation, nächster geplanter Start, Versionskompatibilität, Hauptrichtungsstatus, Leistungsmodus, Grund für die Rückkehr zur Station, Mission, Untermission, Missionszustand. *Diagnose:* aktive Fehler, letztes Ereignis, WLAN-Signal, Mobilfunk RSRP / RSRQ / Typ, Sonnenaufgang, Sonnenuntergang, Bewegungs- / Karten- / Mähmodus, Schwellwert des Regensensors, Verzögerung der Fortsetzung nach Regen, Kartenspeicher-Fortschritt |
| Binärsensor | Wird geladen, Navigation lokalisiert, Firmware-Aktualisierung läuft, Netzschalter, Problem, Regen erkannt, Karte erkannt / erstellbar / Sicherung läuft, Daten werden gespeichert, Datenkonvertierung läuft. *Diagnose:* Mobilfunk aktiviert, Beschlagheizung, Beleuchtung, Tageslicht, Extremwetter, Absturz- / Neigungserkennung, automatische Fortsetzung nach Regen, einzelne Basisstation erzwingen, Mobilfunknetz erzwingen, manuelle Kartierung Neupositionierung / Übernahme / Grenze geschlossen, Zustandsflag 134 (nicht dekodiert) |
| Auswahl | Zonenauswahl, Mähgeschwindigkeit, Messerdrehzahl, Hauptrichtungsmodus, Kantenschnittmodus für hohes Gras |
| Zahl | Mähhöhe, Kantenschnittabstand, Bahnabstand, Winkel für Einzelrichtung, Intervall für automatische Winkeldrehung, Winkel der ersten / zweiten Richtung. *Konfiguration, standardmäßig aus:* Regensensor-Schwelle, Fortsetzungs-Verzögerung nach Regen |
| Schalter | Gründliches Eckenmähen. *Konfiguration, standardmäßig aus:* Klippenerkennung, Hangerkennung, Auto-Fortsetzen nach Regen |
| Taste | Kantenschnitt, Messer-Timer zurücksetzen, Basisstations-Timer zurücksetzen |
| Update | Firmware-Version |
| Ereignis | Mäher-Ereignis (Mähen gestartet / pausiert / Rückkehr / angedockt / abgeschlossen / Fehler) |
| Kalender | Mähzeitplan (nächster geplanter Mähvorgang) |

### Installation

[![Öffnen Sie Ihre Home-Assistant-Instanz und öffnen Sie ein Repository im Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Methode 1: HACS (empfohlen)
1. Stellen Sie sicher, dass [HACS](https://hacs.xyz/) installiert ist
2. Verwenden Sie die Schaltfläche oben, um die Integration zu HACS hinzuzufügen
3. Öffnen Sie HACS, suchen Sie nach „TerraMow“ und wählen Sie die Integration aus
4. Installieren Sie die Integration und starten Sie Home Assistant neu

#### Methode 2: Manuelle Installation
1. Kopieren Sie den Ordner `custom_components/terramow` in den Ordner `/config/custom_components` Ihres Home Assistant
2. Starten Sie Home Assistant neu
3. Gehen Sie zu Einstellungen → Geräte & Dienste → Integration hinzufügen
4. Suchen Sie nach „TerraMow“ und folgen Sie den Konfigurationsschritten

### Konfiguration

Geräte im lokalen Netzwerk werden automatisch über Zeroconf erkannt — akzeptieren Sie das erkannte Gerät und geben Sie das MQTT-Passwort ein. Für die manuelle Einrichtung sind die folgenden Parameter erforderlich:

- **Host**: IP-Adresse oder Hostname des TerraMow-Geräts
- **Passwort**: MQTT-Passwort für die Authentifizierung

**Einstellungen später ändern**
- *Rekonfigurieren* (Einstellungen → Geräte & Dienste → TerraMow → Rekonfigurieren): Host/IP oder Passwort direkt ändern, z. B. nachdem der Mäher eine neue DHCP-Adresse erhalten hat — die Integration muss nicht entfernt und neu hinzugefügt werden.
- *Optionen* (Konfigurieren):
  - **Ausgabeauflösung der Karte** — höhere Werte sind schärfer, kosten aber mehr Bandbreite und CPU pro Rendering.
  - **Karten-Theme** — `light` oder `dark`.
  - **Gemähte Fläche anzeigen** — schattiert die bereits gemähte Fläche unter der Pfadlinie.
  - **Jeden beendeten Auftrag als 100 % abgeschlossen werten** — manche Firmware beendet einen fertigen Auftrag ohne Abschlusssignal, sodass der Sitzungsfortschritt nie auf 100 % springt, obwohl der Rasen fertig ist (er wird als „abgebrochen“ gelesen). Aktivieren Sie diese Option, um jeden beendeten Auftrag als abgeschlossen zu behandeln — wie die Hersteller-App; lassen Sie sie aus, um den ehrlichen Zählerwert zu behalten. *Standard: aus.*
- Wenn sich das Gerätepasswort ändert, startet Home Assistant automatisch einen *Reauthentifizierungs*-Flow.

### Anforderungen

- Home Assistant 2024.6.0 oder neuer (die CI prüft gegen die aktuelle HA-Core-Version)
- TerraMow-Firmware-Version 6.6.0 oder neuer
- TerraMow-APP-Version 1.6.0 oder neuer
- Live-Karte und Mähpfad erfordern die Firmware-HA-Modul-Version 3; auf Version 2 (z. B. S800) funktioniert alles andere, und der Sensor für die Versionskompatibilität meldet dies

### Unterstützte Geräte

Diese Integration funktioniert mit TerraMow-Mährobotern, die die lokale MQTT/HTTP-Schnittstelle bereitstellen — also mit jedem Modell auf der erforderlichen Firmware. Sie wird mit der TerraMow-S-Serie eingesetzt, einschließlich des **S800** (der die Firmware-HA-Modul-Version 2 meldet) und neuerer Geräte mit Version 3. Jeder TerraMow-Mäher mit Firmware 6.6.0+ und App 1.6.0+ sollte funktionieren; der Sensor für die Versionskompatibilität und ein Reparaturhinweis zeigen an, wenn die Firmware eines Geräts für eine bestimmte Funktion zu alt ist.

### Dienste

#### `terramow.start_select_region`

Startet das Mähen für eine Liste ausgewählter Teilbereiche.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Legt ein wöchentliches Mähfenster auf dem Mäher an oder entfernt es. Jeder
Schreibvorgang wird gegen das Gerät bestätigt (dp_119-Quittung plus Rücklesen
des Zeitplans).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` erwartet die `item_id` des Fensters (wird als UID des
Kalenderereignisses angezeigt und beim Anlegen eines Fensters zurückgegeben).

> **Hinweis:** Die aktuelle Seriennummern-Firmware akzeptiert Zeitplan-Schreibvorgänge
> über lokales MQTT noch nicht (die Hersteller-App nutzt Bluetooth/Cloud). Bis die
> Firmware das unterstützt, verwenden Sie das **Blueprint für wetterabhängiges Mähen**
> für die Planung auf HA-Seite.

### Interaktive Kartenkarte

Die Integration bringt ihre eigene Lovelace-Karte mit — automatisch registriert, ohne manuelle Ressource oder separate HACS-Frontend-Installation:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Sie stellt den Rasen als Vektoren dar (scharf bei jedem Zoom, folgt Ihrem HA-Theme): Zonen, Sperrzonen, virtuelle Wände, den Mähpfad, die Basisstation und die Live-Position des Roboters. Ziehen zum Verschieben, Scrollen oder Zwei-Finger-Zoom zum Zoomen, Doppeltippen zum erneuten Einpassen. **Tippen Sie eine oder mehrere Zonen an** und drücken Sie die erscheinende Schaltfläche, um genau diese Zonen zu mähen (im Hintergrund `terramow.start_select_region`).

Eine **Ansichtsschaltfläche** wechselt, was die Karte über den Rasen legt:

| Modus | Zeigt |
| --- | --- |
| **Beides** | gemähte Fläche *und* Mähpfad (Standard, wenn die Flächenanzeige aktiv ist) |
| **Weg** | nur den Pfad des aktuellen und des vorherigen Auftrags |
| **Fläche** | nur die Schattierung der gemähten Fläche, mit Fortschritt pro Zone |
| **WLAN** | eine **WLAN-Heatmap** des Rasens, vom Mäher während des Mähens erfasst (grün = stark). Lücken zwischen Mähbahnen werden aus benachbarten Messwerten interpoliert; nie befahrener Boden bleibt leer |

Der gewählte Modus wird pro Entität im Browser gespeichert. Optionen und Details: siehe den [Dashboard-Leitfaden](en/dashboard.md#interactive-map-card) (englisch). Live-Kartendaten erfordern die Firmware-HA-Modul-Version 3 (wie bei der Kartenkamera). Die Karte steht auch in der Kartenauswahl des Dashboards als **TerraMow Map Card** bereit, mit vollständigem UI-Editor — kein YAML erforderlich.

### Dashboard-Beispiel

Eine fertige Lovelace-Ansicht (Live-Karte, Bedienelemente, Fortschrittsanzeige, Statusübersicht) plus Benachrichtigungs-Automatisierungen: siehe den [Dashboard-Leitfaden](en/dashboard.md) (englisch).

### Automatisierungs-Blueprints

Mit einem Klick importierbare Blueprints für die häufigsten Benachrichtigungen — jedes fragt nur nach der passenden TerraMow-Entität und einer Benachrichtigungsaktion:

- **Wetterabhängiges Mähen** — startet das Mähen nach Ihrem Zeitplan und überspringt es automatisch, wenn Regen erkannt oder vorhergesagt wird
  [![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Problem-Benachrichtigung** — wenn der Mäher eine Störung meldet
  [![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Wegen Regen zurückgekehrt** — wenn der Mäher wegen Regen andockt
  [![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Mähen abgeschlossen** — wenn ein Mähauftrag fertig ist
  [![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Die Ereignis-Entität direkt verwenden** — die Mäher-Ereignis-Entität ist der flexibelste Auslöser. Ihr Attribut `event_type` ist eines von `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, und sie trägt die Rohfelder `mission`, `sub_mission`, `state`, `back_to_station_reason` und `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow hat das Mähen beendet 🌱"
```

### Reparaturhinweise

Die Integration erzeugt handlungsorientierte Home-Assistant-Reparaturhinweise (Einstellungen → Geräte & Dienste → Reparaturen), anstatt Probleme in Sensoren zu verstecken:

- **Firmware inkompatibel / Update erforderlich** — die Firmware ist für die Integration (oder eine bestimmte Funktion) zu alt. Abgeleitet aus der Versionskompatibilitätsprüfung; verschwindet, sobald sich eine kompatible Firmware meldet.
- **Messerwartung fällig** — der Messerteller hat sein empfohlenes Wartungsintervall von 240 Stunden erreicht. Reinigen/ersetzen Sie die Messer und drücken Sie die Taste *Messer-Timer zurücksetzen*, um den Hinweis zu löschen.
- **Wartung der Basisstation fällig** — die Basisstation hat ihr empfohlenes Wartungsintervall von 30 Tagen erreicht. Reinigen Sie sie und drücken Sie die Taste *Basisstations-Timer zurücksetzen*, um den Hinweis zu löschen.

### Diagnose & Fehlerbehebung

- **Diagnose-Download**: Einstellungen → Geräte & Dienste → TerraMow → Drei-Punkte-Menü → *Diagnose herunterladen* erzeugt einen bereinigten JSON-Schnappschuss (Gerätezustand, Firmware-Kompatibilität, Rohdatenpunkt-Caches) — bitte fügen Sie ihn Fehlerberichten bei.
- **Nicht unterstützte Funktionen entdecken**: Der Mäher veröffentlicht mehr Datenpunkte, als dokumentiert sind. Die erste Nutzlast jedes unbekannten Datenpunkts wird einmalig auf INFO-Ebene protokolliert; aktivieren Sie das Debug-Logging für die `terramow`-Integration, um alle aufzuzeichnen. Wenn Sie einen Datenpunkt für eine fehlende Funktion finden (z. B. Hebealarm, Zeitplanschalter, Fehlercodes), teilen Sie ihn bitte in einem Issue mit.

### Wie Daten aktualisiert werden

TerraMow ist eine **Local-Push**-Integration. Der Mäher betreibt einen MQTT-Broker auf dem Gerät; Home Assistant verbindet sich direkt über das LAN damit (keine Cloud) und abonniert die Datenpunkt-Topics des Geräts. Entitätszustände aktualisieren sich daher in dem Moment, in dem der Mäher eine Änderung meldet, und nicht in einem Abfrageintervall. Größere Nutzlasten (die Karte, der Live-Pfad) werden über MQTT angekündigt und bei Bedarf über lokales HTTP geladen. Ist der Mäher im Ruhezustand oder nicht im Netz, wird die Verbindung mit exponentiellem Backoff erneut versucht, und die Rasenmäher-Entität zeigt den Verbindungsverlust als Aktivität `error` an.

**Befehle scheitern laut, nicht stillschweigend.** Wenn Sie einen Befehl senden — `dock`, `start_mowing`, `pause`, Kantenschnitt, Zonenmähen oder eine Einstellungsänderung — wird er mit MQTT QoS 1 veröffentlicht (eine kurze Neuverbindung puffert ihn also, statt ihn zu verwerfen). Ist der Mäher offline/nicht erreichbar, lehnt der Broker die Veröffentlichung ab, oder kommt ein Befehl schneller, als das Gerät ihn annehmen kann, **schlägt der Dienstaufruf mit einem Fehler fehl**, statt stillschweigend Erfolg zu melden. Eine Automatisierung, die `lawn_mower.dock` aufruft, während der Mäher nicht erreichbar ist, sieht damit den Fehlschlag (und kann es erneut versuchen oder benachrichtigen), statt zu glauben, der Mäher sei auf dem Rückweg, obwohl er den Befehl nie erhalten hat.

### Bekannte Einschränkungen

- **Kein Cloud- / Fernzugriff** — Home Assistant muss sich im selben LAN wie der Mäher befinden; es gibt keinen Cloud-Rückfall.
- **Firmware-abhängige Funktionen** — Live-Karte und Mähpfad-Ansicht erfordern die Firmware-HA-Modul-Version 3; auf Version 2 (z. B. dem S800) funktioniert alles andere, und der Kompatibilitätssensor / Reparaturhinweis meldet die Einschränkung.
- **Firmware-Updates** werden über die TerraMow-App durchgeführt, nicht aus Home Assistant; die Firmware-`update`-Entität ist nur informativ.
- **Der Positionssensor und die reine Kartenkamera sind standardmäßig deaktiviert** (der Positionssensor aktualisiert sich mit etwa 2 Hz); aktivieren Sie sie bei Bedarf in den Entitätseinstellungen.
- **Viele Entitäten der erweiterten Diagnose sind standardmäßig deaktiviert** und in der Kategorie *Diagnose* gruppiert (Mobilfunk, Sonnenauf-/-untergang, Betriebsmodi, Flags der manuellen Kartierung usw.); sie stammen aus rückentwickelten Datenpunkten — aktivieren Sie daher nur, was Sie brauchen. Siehe die [Notizen zu unoffiziellen Datenpunkten](en/developers/data_point_unofficial.md).
- Einige Datenpunkte des Geräts sind undokumentiert; unbekannte werden einmalig protokolliert, um fehlende Funktionen zu entdecken.

### Anwendungsfälle

- **Regenabhängige Benachrichtigungen** — erhalten Sie eine Push-Nachricht, wenn der Mäher wegen Regen zu seiner Station zurückkehrt (siehe die Blueprints oben).
- **Störungsalarme** — werden Sie in dem Moment benachrichtigt, in dem der Mäher ein Problem meldet (steckengeblieben, angehoben, blockiert).
- **Zonenmähen aus Automatisierungen** — rufen Sie `terramow.start_select_region` auf, um bestimmte Teilbereiche nach Zeitplan oder per Dashboard-Schaltfläche zu mähen.
- **Wartungserinnerungen** — die Sensoren für die verbleibende Zeit von Messer / Basisstation und die Reset-Tasten erlauben automatisierte Wartungserinnerungen.
- **Live-Karte auf einem Dashboard** — zeigen Sie die Kartenkamera mit Roboterposition und Mähpfad (siehe den Dashboard-Leitfaden).

### Sprachen

Die Integration ist übersetzt in: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Hinweise zum Upgrade

- **v0.5.0**: Die Zustandswerte der Entitäten wurden von Groß- auf Kleinschreibung umgestellt (z. B. `MISSION_IDLE` → `mission_idle`), um die Übersetzungsanforderungen von Home Assistant zu erfüllen. Automatisierungen oder Templates, die rohe Zustandszeichenketten vergleichen, benötigen eine einmalige Anpassung; die angezeigten Namen bleiben unverändert.

### Support

Öffnen Sie für Unterstützung ein Issue auf [GitHub](https://github.com/it-rec/TerraMowHA/issues).

### Informationen für Entwickler

Für Entwickler, die diese Integration verstehen oder erweitern möchten (die Entwicklerdokumentation ist auf Englisch):

- [Beitragsleitfaden](../CONTRIBUTING.md) — Einrichtung, Qualitätsanforderungen (100 % Testabdeckung, `mypy --strict`, Übersetzungen), PR- und Release-Prozess
- [Architektur](ARCHITECTURE.md) — Interna der Integration: Hub-Lebenszyklus, Ausführungsmodell, Datenpunkt-Katalog, Karten-/Pfad-Pipeline
- [Entwicklerhandbuch](en/developers.md) — das MQTT/HTTP-Geräteprotokoll auf dem Draht
- [Was dieser Fork gegenüber Upstream ergänzt](UPSTREAM_DELTA.md)

So führen Sie die Testsuite lokal aus:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Lizenz

Dieses Projekt ist unter der GNU General Public License v3.0 lizenziert — Details finden Sie in der Datei [LICENSE](../LICENSE).
