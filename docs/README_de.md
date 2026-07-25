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
- **Schedule editing** — `terramow.add_schedule` / `terramow.delete_schedule` services write weekly mowing slots to the mower with read-back verification. *Note:* current retail firmware does not yet accept schedule writes over local MQTT (the vendor app uses Bluetooth/cloud) — until firmware adds it, use the **weather-adaptive mowing blueprint** for HA-side scheduling
- **Interactive map card** — pan/zoom vector lawn map for dashboards: live robot position (activity-tinted, with follow mode), on-card start / pause / dock controls, battery & job-progress chips, optional mowed-coverage shading, mowing path, base station, zones with tap-to-mow selection, forbidden areas and virtual walls; theme-aware, self-registering, with a UI editor (`custom:terramow-map-card`)
- Taste für Kantenschnitt
- Einstellungen aus Home Assistant: Mähhöhe, Geschwindigkeit, Bahnabstand, Messerdrehzahl, Kantenschnittabstand, Hauptrichtungsmodus und -winkel, gründliches Eckenmähen, Kantenschnittmodus für hohes Gras
- Wartung: Reset-Tasten für die Zähler von Messerteller und Basisstation

**Überwachung**
- Live-Kartenkamera mit Mähpfad, Roboterposition und Basisstation (plus eine reine Kartenkamera für Dashboards, Auflösung über die Optionen konfigurierbar)
- Akku: Ladestand, Ladezustand, Temperaturzustand, Ladegerät verbunden, Netzschalter
- Auftragsfortschritt: Fläche der aktuellen Sitzung, Fortschritt (%), Dauer und Auftragstyp; Gesamtmähzeit, Auftragsanzahl und gemähte Fläche
- Status: Mission / Untermission / Missionszustand, Betriebsmodus, Leistungsmodus, Grund für die Rückkehr zur Station, Regenerkennung, Problemanzeige, Anzeigen für Datenspeicherung und Datenkonvertierung
- **Saison-Heatmap** — eine Kartenansicht (`Saison`), die einfärbt, wie viele *abgeschlossene Zyklen* jede Rasenstelle erreicht haben. Ein Streifen, den der Mäher jeden zweiten Lauf auslässt, sieht in einem einzelnen Zyklus unauffällig aus und wird erst durch das Stapeln sichtbar; blass heißt selten erreicht. Jeder Zyklus zählt pro Zelle einmal, egal wie oft er durchgefahren ist, bleibt über Neustarts erhalten und wird beim Kartenwechsel zurückgesetzt
- Karte: Status, Fläche, Flags für erkannt / erstellbar / Sicherung läuft
- Zeitplan: nächster geplanter Start
- Firmware-Update-Entität, Firmware-Version auf der Geräteseite und Sensor für die Versionskompatibilität
- Alle Entitäten werden bei Geräte-Pushes sofort aktualisiert — keine Polling-Verzögerung

**Komfortfunktionen der Integration**
- Automatische Erkennung über Zeroconf/mDNS
- Rekonfigurations-Flow (Host/IP ändern ohne erneutes Hinzufügen) und Reauthentifizierungs-Flow
- Diagnose-Download für einfache Fehlerberichte
- In 33 Sprachen übersetzt (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- Lokale Push-Kommunikation auf MQTT-Basis — keine Cloud erforderlich

### Unterstützte Entitäten

| Plattform | Entitäten |
| --- | --- |
| Rasenmäher | Steuerung für Starten / Pausieren / Andocken mit Live-Aktivität |
| Kamera | Karte mit Pfad, Roboter und Basisstation; reine Kartenvariante |
| Sensor | Akkustand, Akkuzustand, Akkutemperaturzustand, Kartenstatus, Kartenfläche, Mähhöhe, Mähgeschwindigkeit, Betriebsmodus, Position, Gesamtmähzeit / Aufträge / gemähte Fläche, Fläche / Fortschritt / Dauer / Auftragstyp der aktuellen Sitzung, verbleibende Zeit für Messer und Basisstation, nächster geplanter Start, Versionskompatibilität, Hauptrichtungsstatus, Leistungsmodus, Grund für die Rückkehr zur Station, Mission, Untermission, Missionszustand |
| Binärsensor | Wird geladen, Navigation lokalisiert, Firmware-Aktualisierung läuft, Netzschalter, Problem, Regen erkannt, Karte erkannt / erstellbar / Sicherung läuft, Daten werden gespeichert, Datenkonvertierung läuft |
| Auswahl | Zonenauswahl, Mähgeschwindigkeit, Messerdrehzahl, Hauptrichtungsmodus, Kantenschnittmodus für hohes Gras |
| Zahl | Mähhöhe, Kantenschnittabstand, Bahnabstand, Winkel für Einzelrichtung, Intervall für automatische Winkeldrehung, Winkel der ersten / zweiten Richtung |
| Schalter | Gründliches Eckenmähen |
| Taste | Kantenschnitt, Messer-Timer zurücksetzen, Basisstations-Timer zurücksetzen |
| Update | Firmware-Version |

### Installation

#### Methode 1: HACS (empfohlen)
1. Stellen Sie sicher, dass [HACS](https://hacs.xyz/) installiert ist
2. Verwenden Sie die Schaltfläche oben, um die Integration zu HACS hinzuzufügen
3. Gehen Sie zu HACS → Integrationen → + → Suchen Sie nach „TerraMow“
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
- *Optionen* (Konfigurieren): Ausgabeauflösung der Kartenkamera festlegen. Höhere Werte liefern ein schärferes Dashboard-Bild, kosten aber mehr Bandbreite und CPU pro Rendering.
- Wenn sich das Gerätepasswort ändert, startet Home Assistant automatisch einen *Reauthentifizierungs*-Flow.

### Anforderungen

- Home Assistant 2024.6.0 oder neuer (getestet mit 2025.1.1)
- TerraMow-Firmware-Version 6.6.0 oder neuer
- TerraMow-APP-Version 1.6.0 oder neuer
- Live-Karte und Mähpfad erfordern die Firmware-HA-Modul-Version 3; auf Version 2 (z. B. S800) funktioniert alles andere, und der Sensor für die Versionskompatibilität meldet dies

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

### Interactive map card

The integration ships its own Lovelace card — auto-registered, no manual resource or HACS frontend install needed:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

It renders the lawn as vectors (crisp at any zoom, follows your HA theme): zones, forbidden areas, virtual walls, the mowing path, the base station and the robot's live position. Drag to pan, scroll or pinch to zoom, double-tap to re-fit. **Tap one or more zones** and press the button that appears to mow exactly those zones (`terramow.start_select_region` under the hood). Options and details: see the [dashboard guide](en/dashboard.md#interactive-map-card). Live map data requires firmware HA module version 3 (same as the map camera). The card is also available in the dashboard card picker as **TerraMow Map Card**, with a full UI editor — no YAML needed.

### Diagnose & Fehlerbehebung

- **Diagnose-Download**: Einstellungen → Geräte & Dienste → TerraMow → Drei-Punkte-Menü → *Diagnose herunterladen* erzeugt einen bereinigten JSON-Schnappschuss (Gerätezustand, Firmware-Kompatibilität, Rohdatenpunkt-Caches) — bitte fügen Sie ihn Fehlerberichten bei.
- **Nicht unterstützte Funktionen entdecken**: Der Mäher veröffentlicht mehr Datenpunkte, als dokumentiert sind. Die erste Nutzlast jedes unbekannten Datenpunkts wird einmalig auf INFO-Ebene protokolliert; aktivieren Sie das Debug-Logging für die `terramow`-Integration, um alle aufzuzeichnen. Wenn Sie einen Datenpunkt für eine fehlende Funktion finden (z. B. Hebealarm, Zeitplanschalter, Fehlercodes), teilen Sie ihn bitte in einem Issue mit.

### Sprachen

Die Integration ist übersetzt in: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Hinweise zum Upgrade

- **v0.5.0**: Die Zustandswerte der Entitäten wurden von Groß- auf Kleinschreibung umgestellt (z. B. `MISSION_IDLE` → `mission_idle`), um die Übersetzungsanforderungen von Home Assistant zu erfüllen. Automatisierungen oder Templates, die rohe Zustandszeichenketten vergleichen, benötigen eine einmalige Anpassung; die angezeigten Namen bleiben unverändert.

### Support

Öffnen Sie für Unterstützung ein Issue auf [GitHub](https://github.com/it-rec/TerraMowHA/issues).

### Informationen für Entwickler

Entwickler, die diese Integration verstehen oder erweitern möchten, finden weitere Informationen im [Entwicklerhandbuch](en/developers.md).

So führen Sie die Testsuite lokal aus:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Lizenz

Dieses Projekt ist unter der GNU General Public License v3.0 lizenziert — Details finden Sie in der Datei [LICENSE](../LICENSE).
