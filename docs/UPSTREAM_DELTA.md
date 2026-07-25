# What this fork adds over upstream

This document tracks the differences between `it-rec/TerraMowHA` and the
upstream project [`TerraMow/TerraMowHA`](https://github.com/TerraMow/TerraMowHA).
Keep it up to date when landing changes that diverge from upstream.

At the time of writing, upstream's latest tag is **v0.3.0**; this fork is on the
**v1.x** line. The fork is a strict superset — every upstream capability is
retained — plus the additions below.

**Last synced with upstream:** commit `045d789` (2026-06-18, upstream `main`).
All upstream commits after v0.3.0 are already covered by the fork:

| Upstream commit | Where the fork has it |
|---|---|
| `b7af54a` Rotate the robot and base image | Rotated robot/station rendering in `map_render.py` (pose `theta`/`yaw`). |
| `5b9daf8` Show mowing path live without reload (#55) | Generalized backward-seq session reset in `hub.py` `_async_handle_meta`, applied to all meta channels (path, history path, map). |
| `045d789` Stop MQTT reconnect loop spam / thread leak | Superseded by the async MQTT stack in `hub.py` / `const.py`: exponential backoff, throttled logging, connection task cancelled and awaited on unload. |

## New platforms & entities

| Platform | What it adds |
|---|---|
| **Event** (`event.py`) | A mower event entity firing `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, each with the raw mission fields as attributes. Lets automations react to transitions without polling. |
| **Calendar** (`calendar.py`) | A read-only mowing-schedule calendar: the full weekly schedule when dp_122 is available, otherwise the dp_138 next scheduled mow, with active/upcoming/next-day and past-midnight handling. |
| Camera | A second, default-disabled *clean* map-only camera for dashboards, plus a configurable output resolution. |
| **Image** (`image.py`) | A mow-report image: the last finished session frozen as a PNG (its mow track plus a ribbon with area, duration and outcome), rendered once per session so it still shows that session after the device has reset its counters. |
| Sensor | A default-disabled pose sensor, a **Wi-Fi signal** sensor (dp_109, mower-side strength in percent), and a session-level **Active Job** sensor that reports the running mission across mid-session heartbeat gaps. |

## New user-facing capabilities

- **Interactive map card** (`map_card.py` + `frontend/terramow-map-card.js`):
  an auto-registered Lovelace card rendering the map as vectors over a
  `terramow/map/subscribe` WebSocket feed — pan/zoom, live robot marker,
  theme-aware, with tap-to-mow zone selection driving
  `terramow.start_select_region`. It has grown a full on-card control set:
  status chips, a mowed-coverage overlay (true stripe spacing) and follow
  mode, per-zone stripe-direction indicators, long-press for a zone's mow
  settings, trapped / maintenance / passage markers, a layer legend,
  camera-parity badges, a stale-map chip, two-finger rotate with a compass
  reset, keyboard zone cycling, and a card editor with rotation presets and a
  "use current rotation" capture.
- **Repair issues** (`issues.py`): actionable dashboard cards for
  incompatible/too-old firmware (from dp_127) and for due blade (240 h) /
  base-station (30 day) maintenance (from dp_126 / dp_125), which clear
  themselves once resolved.
- **Diagnostics** (`diagnostics.py`): a redacted JSON snapshot for bug reports.
- **`terramow.start_select_region` service** with translated exceptions — a
  **confirmed write**: it waits for the device's dp_119 command
  acknowledgement and raises on rejection (rejected fire-and-forget commands
  are logged; the last ack ships in diagnostics).
- **Writable mowing schedule**: `terramow.add_schedule` / `terramow.delete_schedule`
  services (dp_122 `ADD`/`DELETE`) with per-firmware payload negotiation —
  every write is judged by its dp_119 ack and verified against a fresh `GET`.
- **Reauthentication** and **reconfigure** flows, **Zeroconf/mDNS discovery**
  (`_mqtt._tcp.local.`, `terramow*`), and an **options flow** (map resolution,
  theme, mowed-coverage shading).
- **Firmware update entity** and version-compatibility sensor.
- **Automation blueprints** and a **dashboard guide**.
- **Full localization** across 33 languages.

## Architecture & quality

- **Typed config-entry runtime data**: per-entry state lives in the typed
  `entry.runtime_data` (`TerraMowConfigEntry = ConfigEntry[TerraMowBasicData]`)
  instead of `hass.data`.
- **Strict typing**: the whole package passes `mypy --strict`; both runtime
  dependencies ship `py.typed`.
- **Home Assistant Quality Scale: Platinum** — `quality_scale.yaml` (all
  Bronze→Platinum rules done/exempt), `icons.json` icon translations, exception
  translations, disabled-by-default entities where appropriate.
- **100% line + branch test coverage**, enforced in CI
  (`--cov-fail-under=100`), starting from no test suite upstream.
- **Async-native hub**: the paho worker thread has been replaced by an
  `aiomqtt` asyncio task (cancelled and awaited cleanly on unload), with MQTT
  auto-reconnect using exponential backoff and throttled logging; map/path HTTP
  fetch runs over Home Assistant's shared aiohttp session with ETag caching,
  sequence guards, retry/backoff and pending-meta requeue.
- **Device-identifier migration** (`TerraMowLanwMower` → `TerraMowLawnMower`) and
  **S800 support** (older firmware HA-module version 2 works without nagging).
- **CI/CD**: `validate.yml` (tests+coverage, mypy strict, ruff, hassfest, HACS)
  and `release.yml` (builds `terramow.zip`, publishes the GitHub release).

## Release history (fork)

- **v0.6.0** — upstream ports (#68/#80/#81) and community issue fixes.
- **v0.8.2 / v0.8.3** — full package typing + mypy gate.
- **v0.8.4** — Gold quality scale.
- **v0.8.5** — Platinum (strict typing, injected websession, `py.typed`).
- **v0.8.6** — `hass.data` → `entry.runtime_data` migration.
- **v0.8.7** — event entity, mowing-schedule calendar, maintenance repair
  issues, all localized across 33 languages.
- **v1.0.0** — documentation completeness, clean-up and the first stable release.
- **v1.15.0** — interactive Lovelace map card: live vector map with
  tap-to-mow zones and an auto-registered Lovelace resource.
- **v1.16.x** — map card v1.1 (on-card controls, status chips, coverage,
  follow mode); dp_119 decode for confirmed commands and dp_122 schedule-write
  capture; release notes generated from commit messages.
- **v1.17.x** — command-ack and schedule captures exported in diagnostics;
  app-direction capture widened to all data points.
- **v1.18.x** — writable mowing schedule (`add_schedule` / `delete_schedule`)
  with per-firmware format negotiation, full-broker discovery and numeric-verb
  probing.
- **v1.19.x** — weather-adaptive mowing blueprint; map card registered as a
  `js` Lovelace resource (#140); stale "Saving Map" / "Running" display decayed
  to idle (#142).
- **v1.21.x** — select-region command sent with the device's outbound field
  names; event entity's map-save fields decayed to idle (#142).
- **v1.22.0** — async-native hub: the paho worker thread replaced by an
  `aiomqtt` task (#148); map card correctness, performance and accessibility
  pass.
- **v1.23.0** — trapped / maintenance / passage markers on the map card.
- **v1.24.0** — per-zone mowing-stripe direction on the map card.
- **v1.25.0** — long-press a zone for its mow settings on the map card.
- **v1.26.0** — dp_109 surfaced as a Wi-Fi signal sensor.
- **v1.27.0** — map card true-spacing coverage, camera-parity badges and legend.
- **v1.28.0** — map card stale-map chip and layer-count debug section.
- **v1.29.0** — map card two-finger rotate and compass reset.
- **v1.30.0** — session-level Active Job sensor (follow-up to #142).
- **v1.31.0** — map card keyboard zone cycling.
- **v1.32.0** — card editor rotation presets and "use current rotation" capture.
