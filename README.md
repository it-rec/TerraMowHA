# TerraMow for Home Assistant

<div align="center">
  <p>
    <a href="https://github.com/it-rec/TerraMowHA/actions/workflows/validate.yml"><img src="https://github.com/it-rec/TerraMowHA/actions/workflows/validate.yml/badge.svg" alt="Validate"/></a>
    <a href="https://github.com/it-rec/TerraMowHA/actions/workflows/release.yml"><img src="https://github.com/it-rec/TerraMowHA/actions/workflows/release.yml/badge.svg" alt="Release"/></a>
    <a href="https://codecov.io/gh/it-rec/TerraMowHA"><img src="https://codecov.io/gh/it-rec/TerraMowHA/branch/main/graph/badge.svg" alt="Coverage"/></a>
  </p>
  <img src="docs/images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 **English** · [Dansk](docs/README_da.md) · [Deutsch](docs/README_de.md) · [Español](docs/README_es.md) · [Français](docs/README_fr.md) · [Italiano](docs/README_it.md) · [Nederlands](docs/README_nl.md) · [Norsk (bokmål)](docs/README_nb.md) · [Polski](docs/README_pl.md) · [Português](docs/README_pt.md) · [Suomi](docs/README_fi.md) · [Svenska](docs/README_sv.md) · [Čeština](docs/README_cs.md) · [中文](docs/README_zh.md)

---

This is a Home Assistant integration for TerraMow robotic lawn mowers.

### Features

**Control**
- Lawn mower entity: start, pause and dock
- Zone mowing: zone select entity and `terramow.start_select_region` service
- **Schedule editing** — `terramow.add_schedule` / `terramow.delete_schedule` services write weekly mowing slots to the mower with read-back verification. *Note:* current retail firmware does not yet accept schedule writes over local MQTT (the vendor app uses Bluetooth/cloud) — until firmware adds it, use the **weather-adaptive mowing blueprint** for HA-side scheduling
- **Interactive map card** — pan/zoom vector lawn map for dashboards: live robot position (activity-tinted, with follow mode), on-card start / pause / dock controls, battery / job-progress / ETA chips, mowed-coverage shading with per-zone progress, mowing path, base station, zones with tap-to-mow selection, forbidden areas and virtual walls, active faults pinned on the map, and a **Wi-Fi heatmap** of the lawn; a **view-mode button** cycles Both / Path / Area / Wi-Fi, and a **maintenance button** holds the blade / base-station counters with their reset buttons and warns in colour when one runs out. Theme-aware, self-registering, with a UI editor (`custom:terramow-map-card`)
- Edge trim mowing button
- Settings from Home Assistant: mowing height, speed, spacing, blade speed, edge cutting distance, main direction mode and angles, thorough corner cutting, high-grass edge trim mode
- Maintenance: reset buttons for the blade disk and base station counters
- **Maintenance todo list** — a `todo` entity that lists exactly the chores the device's own counters report as due (blade disc, base station) and resets the matching counter when you tick one off. Empty when there is nothing to do

**Monitoring**
- Live map camera with mowing path, robot pose and base station (plus a clean map-only camera for dashboards, resolution configurable via options)
- **Mow report image** — a frozen picture of the *last finished* session: the lawn with that session's mow track shaded in, plus a ribbon carrying its own numbers (area, duration, how it ended). Attach it to a "mowing finished" notification — a live camera frame taken minutes later already shows an empty map, because the device clears its path and counters at session end
- Battery: level, charging state, temperature state, charger connected, power switch
- Job progress: current session area, progress (%), duration and job type; lifetime mowing time, job count and mowed area
- Status: mission / sub-mission / mission state, operation mode, power mode, back-to-station reason, rain detection, problem indicator, saving-data and data-conversion indicators
- **Fault sensor** — the active fault as readable text (e.g. *Mower stuck*, *Mower lifted*, or *OK*), so a notification or voice assistant can say what is wrong without templating an attribute
- Active-job sensor (the running mission, held across mid-session heartbeat gaps) and a mower-side Wi-Fi signal sensor
- **Season heatmap** — a map-card view (`Season`) shading how many *finished cycles* have reached each patch of lawn. A strip the mower skips every second run looks fine in any single cycle and only shows up once the cycles are stacked; pale means rarely reached. Each cycle counts once per cell however often it drove through, persists across restarts and resets with the map
- Map: status, area, detected / buildable / backing-up flags
- **Per-zone "last mowed"** — one timestamp sensor per map zone, stamped with the last time the mower was reported *inside* that zone, with the running cycle's coverage as an attribute. Makes "the terrace hasn't been mowed in ten days" an automation trigger instead of something you notice by eye
- Schedule: next-scheduled-start sensor and a read-only **mowing-schedule calendar** (the next mow appears on the calendar card)
- **Service forecasts** — two timestamp sensors projecting when the blade and base-station counters will reach their service interval. The rate is *measured* from the device's own readings, not assumed, so the sensors stay `unknown` until there is at least a day of observation and the counter has actually moved
- Firmware update entity, firmware version on the device page, and version compatibility sensor
- All entities update instantly on device pushes — no polling delay

**Problem hotspots**
- The mower reports *that* a fault happened, never *where*. Pairing each new dp_116 error code with the pose the mower reported at that moment builds a map of the spots that actually cause trouble — the tree root, the soft patch, the gap it wedges itself into. Repeat faults at one spot merge into a single marker carrying the count, so the repetition is the thing you see. Shown as a map-card layer (`show_hotspots`), persisted across restarts and cleared when the map changes

**Advanced diagnostics** (reverse-engineered data points — mostly in the *Diagnostic* entity category, many disabled by default; see [unofficial data-point notes](docs/en/developers/data_point_unofficial.md))
- Errors & events: active-error count (with the raw error list as an attribute) and last-event code. Known error codes are resolved to readable text through a community-sourced catalog (`error_codes.py`), which also decodes the mower's latest-error code (dp_115)
- Cellular / 4G: modem enabled, signal strength (RSRP / RSRQ), connection type, and a *force cellular network* readout
- Environment: device-reported sunrise / sunset, daylight state, defogger heating, illumination light, and an extreme-weather warning (with an optional info URL)
- Safety & advanced settings: cliff-detection and slope-detection state, rain-sensor threshold, after-rain auto-resume and resume-delay, and a *force single base station* readout
- Operating modes: movement / map / mowing mode strings
- Mapping & progress: manual-mapping guidance flags (relocation / takeover needed, boundary closed) and a map-save progress percentage

**Events & automation**
- **Mower event entity** — fires a discrete event on every notable transition (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), each carrying the raw mission fields, so automations react to *happenings* without polling activity state
- One-click automation blueprints (see below)
- **Assist voice control for zones** — an intent that resolves a spoken zone name against the mower's own map and starts a selective mow ("mow the front lawn"). Matching forgives case, punctuation and accents, but never guesses: an unknown or ambiguous name is answered with the list of zones instead. Copy the ready-made sentences from [`docs/custom_sentences/`](docs/custom_sentences) into your `config/custom_sentences/<language>/` folder

**Integration quality of life**
- Zeroconf/mDNS auto-discovery
- Reconfigure flow (change host/IP without re-adding) and reauth flow
- **Mower on the Home Assistant map** — set the base station's real coordinates and the compass bearing of the map's top edge in the options, and a `device_tracker` projects the mower's live pose onto GPS coordinates: zone triggers, proximity and "the mower left the property" all work. Throttled (1 m / 10 s) so a 2 Hz pose stream doesn't flood the recorder; no tracker is created until the anchor is set
- **Repair issues** — actionable dashboard cards for incompatible firmware and for due blade / base-station maintenance
- Diagnostics download for easy bug reports
- Translated into 33 languages (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Confirmed commands** — zone mowing waits for the device's dp_119 acknowledgement and reports rejections instead of silently "succeeding"
- MQTT based local push communication — no cloud required

### Supported entities

| Platform | Entities |
| --- | --- |
| Lawn mower | Start / pause / dock control with live activity |
| Camera | Map with path, robot and base station; clean map-only variant |
| Image | Mow report of the last finished session (area / duration / outcome as attributes) |
| Sensor | Battery level, battery state, battery temperature state, map status, map area, mow height, mow speed, operation mode, pose, total mowing time / jobs / mowed area, current session area / progress / duration / job type, per-zone last-mowed timestamps, active job, fault, remaining blade & base station time, blade / base-station service forecasts, next scheduled start, version compatibility, main direction status, power mode, back-to-station reason, mission, sub-mission, mission state. *Diagnostic:* active errors, last event, Wi-Fi signal, cellular RSRP / RSRQ / type, sunrise, sunset, movement / map / mowing mode, rain-sensor threshold, after-rain resume delay, map save progress |
| Binary sensor | Charging, navigation located, firmware upgrading, power switch, problem, rain detected, map detected / buildable / backing up, saving data, data conversion in progress. *Diagnostic:* cellular enabled, defogger heating, illumination, daylight, extreme weather, cliff / slope detection, after-rain auto-resume, force single base station, force cellular network, manual-mapping relocation / takeover / boundary-closed, state flag 134 (undecoded) |
| Select | Zone select, mow speed, blade speed, main direction mode, high-grass edge trim mode |
| Number | Mowing height, edge cutting distance, mowing spacing, single direction angle, auto-rotate angle interval, first / second direction angle |
| Switch | Thorough corner cutting |
| Button | Edge trim, reset blade timer, reset base station timer |
| Update | Firmware version |
| Event | Mower event (mowing started / paused / returning / docked / completed / error) |
| Calendar | Mowing schedule (next scheduled mow) |
| Todo | Maintenance list (blade disc, base station) — completing an item resets its counter |
| Device tracker | Mower position as GPS coordinates (only with a configured anchor) |

### Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Method 1: HACS (Recommended)
1. Make sure [HACS](https://hacs.xyz/) is installed
2. Use the button above to add to HACS
3. Open HACS, search for "TerraMow" and select it
4. Install and restart Home Assistant

#### Method 2: Manual Installation
1. Copy the `custom_components/terramow` folder to your Home Assistant `/config/custom_components` folder
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration
4. Search for "TerraMow" and follow the configuration steps

### Configuration

Devices on the local network are discovered automatically via Zeroconf — accept the discovered device and enter the MQTT password. For manual setup the following parameters are required:

- **Host**: IP address or hostname of the TerraMow device
- **Password**: MQTT password for authentication

**Changing settings later**
- *Reconfigure* (Settings → Devices & Services → TerraMow → Reconfigure): change the host/IP or password in place, e.g. after the mower received a new DHCP address — no need to remove and re-add the integration.
- *Options* (Configure):
  - **Map output resolution** — higher is sharper but costs more bandwidth and CPU per render.
  - **Map theme** — `light` or `dark`.
  - **Show mowed coverage** — shade the already-mowed area beneath the path line.
  - **Treat every finished job as 100 % complete** — some firmware ends a finished job without emitting a completion signal, so the session progress never snaps to 100 % even though the lawn is done (it reads as "aborted"). Turn this on to treat any finished job as complete, matching the vendor app; leave it off to keep the honest counter value. *Default: off.*
  - **GPS anchor** — the base station's latitude/longitude plus the compass bearing the top of the rendered map points to. With both coordinates set, a `device_tracker` entity projecting the live pose onto GPS appears; leave them empty and none is created.
- If the device password changes, Home Assistant automatically starts a *reauthentication* flow.

### Requirements

- Home Assistant 2024.6.0 or later (CI validates against the current HA Core release)
- TerraMow firmware version 6.6.0 or later
- TerraMow APP version 1.6.0 or later
- Live map and mowing path require firmware HA module version 3; on version 2 (e.g. S800) everything else works and the version compatibility sensor reports it

### Supported devices

This integration works with TerraMow robotic lawn mowers that expose the local MQTT/HTTP interface — i.e. any model on the required firmware. It has been used with the TerraMow S-series, including the **S800** (which reports firmware HA module version 2) and newer units on version 3. Any TerraMow mower on firmware 6.6.0+ and app 1.6.0+ should work; the version-compatibility sensor and a repair issue tell you if a specific unit's firmware is too old for a given feature.

### Services

#### `terramow.start_select_region`

Start mowing for a list of selected sub-regions.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Write or remove a weekly mowing slot on the mower. Each write is confirmed
against the device (dp_119 acknowledgement plus a schedule read-back).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` takes the `item_id` of the slot (shown as the calendar
event's uid and returned when a slot is added).

> **Note:** current retail firmware does not yet accept schedule writes over
> local MQTT (the vendor app uses Bluetooth/cloud). Until firmware adds it, use
> the **weather-adaptive mowing blueprint** for HA-side scheduling.

### Interactive map card

The integration ships its own Lovelace card — auto-registered, no manual resource or HACS frontend install needed:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

It renders the lawn as vectors (crisp at any zoom, follows your HA theme): zones, forbidden areas, virtual walls, the mowing path, the base station and the robot's live position. Drag to pan, scroll or pinch to zoom, double-tap to re-fit. **Tap one or more zones** and press the button that appears to mow exactly those zones (`terramow.start_select_region` under the hood).

A **view-mode button** cycles what the card overlays on the lawn:

| Mode | Shows |
| --- | --- |
| **Both** | mowed coverage *and* the mowing path (default when coverage is on) |
| **Path** | the current and previous job's path only |
| **Area** | the mowed-coverage shading only, with per-zone progress |
| **Wi-Fi** | a **Wi-Fi heatmap** of the lawn, sampled by the mower as it mows (green = strong). Gaps between mow passes are interpolated from neighbouring samples; ground the mower never covered stays blank |

**Session replay**: press the replay button and the card scrubs through the track the mower actually drove this session — the mowed area filling in as it goes — with play/pause and a slider. It replays data the card already has, so it costs no extra traffic, and it deliberately excludes the previous session's history path: replaying *this* mow must not sweep in the last one.

The chosen mode is remembered per entity in the browser. Options and details: see the [dashboard guide](docs/en/dashboard.md#interactive-map-card). Live map data requires firmware HA module version 3 (same as the map camera). The card is also available in the dashboard card picker as **TerraMow Map Card**, with a full UI editor — no YAML needed.

### Dashboard example

A ready-made Lovelace view (live map, controls, progress gauge, status glance) plus notification automations: see the [dashboard guide](docs/en/dashboard.md).

### Automation blueprints

One-click importable blueprints for the most common notifications — each just asks for the relevant TerraMow entity and a notification action:

- **Weather-adaptive mowing** — start mowing on your schedule, skipped automatically when rain is detected or forecast
  [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Problem notification** — when the mower reports a fault
  [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Returned because of rain** — when the mower docks due to rain
  [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Mowing finished** — when a mowing job completes
  [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

- **Growth-adaptive mowing** — mow when the grass has actually grown — accumulates growing degree days from your weather entity and starts a mow once enough have built up
  [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fgrowth_adaptive_mowing.yaml)
- **Quiet hours** — dock the mower when quiet hours begin and resume afterwards, but only the job the window actually interrupted
  [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fquiet_hours.yaml)
- **Pause while someone is in the garden** — pause on a gate contact, motion or person entity and resume once the garden has been clear for a while
  [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fpresence_pause.yaml)

**Using the event entity directly** — the mower event entity is the most flexible trigger. Its `event_type` attribute is one of `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, and it carries the raw `mission`, `sub_mission`, `state`, `back_to_station_reason` and `has_error` fields:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow finished mowing 🌱"
```

### Repair issues

The integration raises actionable Home Assistant repair issues (Settings → Devices & Services → Repairs) instead of hiding problems in sensors:

- **Firmware incompatible / update required** — the firmware is too old for the integration (or a specific feature). Derived from the version-compatibility check; clears when a compatible firmware reports in.
- **Blade maintenance due** — the blade disc has run for its recommended 240-hour service interval. Clean/replace the blades and press the *Reset Blade Timer* button to clear it.
- **Base station maintenance due** — the base station has run for its recommended 30-day service interval. Clean it and press the *Reset Base Station Timer* button to clear it.

### Diagnostics & troubleshooting

- **Diagnostics download**: Settings → Devices & Services → TerraMow → three-dot menu → *Download diagnostics* produces a redacted JSON snapshot (device state, firmware compatibility, raw data point caches) — please attach it to bug reports.
- **Discovering unsupported features**: the mower publishes more data points than are documented. The first payload of every unknown data point is logged once at INFO level; enable debug logging for the `terramow` integration to record all of them. If you find a data point for a missing feature (e.g. lift alarm, schedule switch, error codes), please share it in an issue.

### How data updates work

TerraMow is a **local push** integration. The mower runs an on-device MQTT broker; Home Assistant connects to it directly over the LAN (no cloud) and subscribes to the device's data-point topics, so entity states update the instant the mower reports a change rather than on a polling interval. Larger payloads (the map, the live path) are announced over MQTT and fetched on demand over local HTTP. If the mower is asleep or off the network the connection is retried with exponential backoff, and the lawn-mower entity surfaces the connection loss as its `error` activity.

**Commands fail loudly, not silently.** When you send a command — `dock`, `start_mowing`, `pause`, edge trim, zone mowing, or any setting change — it is published at MQTT QoS 1 (so a brief reconnect buffers it instead of dropping it). If the mower is offline/unreachable, the broker rejects the publish, or a command arrives faster than the device can accept it, the service call **fails with an error** instead of silently reporting success. This means an automation that calls `lawn_mower.dock` while the mower is unreachable now sees the failure (and can retry or notify) rather than believing the mower is on its way back when it never received the command.

### Known limitations

- **No cloud / remote access** — Home Assistant must be on the same LAN as the mower; there is no cloud fallback.
- **Firmware-gated features** — the live map and mowing-path view require firmware HA module version 3; on version 2 (e.g. the S800) everything else works and the compatibility sensor / repair issue reports the limitation.
- **Firmware updates** are performed through the TerraMow app, not from Home Assistant; the firmware `update` entity is informational only.
- **The pose sensor and the clean-mode map camera are disabled by default** (the pose sensor updates at ~2 Hz); enable them from the entity settings if you need them.
- **Many advanced-diagnostic entities are disabled by default** and grouped under the *Diagnostic* category (cellular, sunrise/sunset, operating modes, manual-mapping flags, etc.); they come from reverse-engineered data points, so enable only the ones you need. See the [unofficial data-point notes](docs/en/developers/data_point_unofficial.md).
- Some device data points are undocumented; unknown ones are logged once to help discover missing features.

### Use cases

- **Rain-aware notifications** — get a push when the mower returns to its dock because of rain (see the blueprints above).
- **Fault alerts** — be notified the moment the mower reports a problem (stuck, lifted, blocked).
- **Zone mowing from automations** — call `terramow.start_select_region` to mow specific sub-regions on a schedule or from a dashboard button.
- **Maintenance reminders** — the remaining blade / base-station time sensors and the reset buttons let you automate maintenance reminders.
- **Live map on a dashboard** — show the map camera with the robot position and mowing path (see the dashboard guide).

### Languages

The integration is translated into: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Upgrade notes

- **v0.5.0**: entity state values changed from uppercase to lowercase (e.g. `MISSION_IDLE` → `mission_idle`) to comply with Home Assistant translation requirements. Automations or templates comparing raw state strings need a one-time update; displayed names are unchanged.

### Support

Open an issue on [GitHub](https://github.com/it-rec/TerraMowHA/issues) for support.

### Developer Information

For developers interested in understanding or extending this integration:

- [Contributing guide](CONTRIBUTING.md) — setup, quality gates (100% coverage, `mypy --strict`, translations), PR and release process
- [Architecture](docs/ARCHITECTURE.md) — integration internals: hub lifecycle, execution model, data-point catalog, map/path pipeline
- [Developer guide](docs/en/developers.md) — the on-the-wire MQTT/HTTP device protocol
- [What this fork adds over upstream](docs/UPSTREAM_DELTA.md)

To run the test suite locally:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
