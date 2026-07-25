# What this fork adds over upstream

This document tracks the differences between `it-rec/TerraMowHA` and the
upstream project [`TerraMow/TerraMowHA`](https://github.com/TerraMow/TerraMowHA).
Keep it up to date when landing changes that diverge from upstream.

At the time of writing, upstream's latest tag is **v0.3.0**; this fork is on the
**v1.x** line. The fork is a strict superset — every upstream capability is
retained — plus the additions below.

**Last synced with upstream:** commit `045d789` (2026-06-18, upstream `main`).
As of the v1.62.0 doc pass this sync check had not been repeated — re-verify
against upstream `main` before the next release. All upstream commits up to the
synced point are already covered by the fork:

| Upstream commit | Where the fork has it |
|---|---|
| `b7af54a` Rotate the robot and base image | Rotated robot/station rendering in `map_render.py` (pose `theta`/`yaw`). |
| `5b9daf8` Show mowing path live without reload (#55) | Generalized backward-seq session reset in `hub.py` `_async_handle_meta`, applied to all meta channels (path, history path, map). |
| `045d789` Stop MQTT reconnect loop spam / thread leak | Superseded by the async MQTT stack in `hub.py` / `const.py`: exponential backoff, throttled logging, connection task cancelled and awaited on unload. |

## New platforms & entities

| Platform | What it adds |
|---|---|
| **Event** (`event.py`) | A mower event entity firing `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, each with the raw mission fields as attributes. Lets automations react to transitions without polling. |
| **Todo** (`todo.py`) | A maintenance list generated from the blade / base-station counters: an item exists while the device reports the interval as reached, and completing it resets that counter on the mower. |
| **Calendar** (`calendar.py`) | A read-only mowing-schedule calendar: the full weekly schedule when dp_122 is available, otherwise the dp_138 next scheduled mow, with active/upcoming/next-day and past-midnight handling. |
| Camera | A second, default-disabled *clean* map-only camera for dashboards, plus a configurable output resolution. |
| Sensor | A default-disabled pose sensor, a **Wi-Fi signal** sensor (dp_109, mower-side strength in percent), a session-level **Active Job** sensor that reports the running mission across mid-session heartbeat gaps, and a **Fault** sensor carrying the active fault as readable text (dp_116/dp_115 resolved through the `error_codes.py` catalog). |

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
  reset, keyboard zone cycling, a session replay scrubber, and a card editor
  with rotation presets and a "use current rotation" capture. It also carries a
  **Wi-Fi heatmap** of the lawn (self-sampled from dp_109 as the mower drives,
  gap-filled between mow passes), a **view-mode button** cycling
  Both / Path / Area / Wi-Fi with the choice remembered per entity, per-zone
  progress shading from the cycle coverage, an ETA chip, and active faults
  pinned where they were reported.
- **Fault hotspots**: each new dp_116 error code is paired with the pose the
  mower reported at that moment and accumulated into a persisted, map-scoped
  set of problem spots (repeats merged with a count), drawn as a map-card
  layer — information neither the app nor the cloud offers.
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
- **Community-sourced error-code catalog** (`error_codes.py`): device fault
  codes are resolved to readable text for the Fault sensor and the card's fault
  pins, and the undocumented dp_115 latest-error code is decoded.
- **Reauthentication** and **reconfigure** flows, **Zeroconf/mDNS discovery**
  (`_mqtt._tcp.local.`, `terramow*`), and an **options flow** (map resolution,
  theme, mowed-coverage shading, and treating any finished job as 100 %
  complete for firmware that never emits a completion signal).
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
- **v1.42.0** — the event entity's `has_error` attribute mirrors the combined
  fault signal (#171).
- **v1.43.0** — unknown-dp changes persisted to a restart-proof JSONL log while
  debug logging is on.
- **v1.44.0** — the session's mowed path stays visible across a mid-session
  recharge dock.
- **v1.45.0** — session sensors snap to 100 % on completion and reset once the
  job is over (#204, #207).
- **v1.46.0** — archived session mow paths persisted across HA restarts;
  dp_103/104/120 acks and the dp_114 event-code mirror documented.
- **v1.47.0** — the active-job latch releases on a manual job end; ETA chip in
  the map HUD.
- **v1.48.0** — persistent cycle-level mowed coverage derived from the mow tracks.
- **v1.49.0** — map card per-zone progress shading from the cycle coverage.
- **v1.50.0** — lazy camera render and throttled zone coverage; the dp_103
  draw-region finding documented (no local draw-region mode).
- **v1.51.0** — smoother map pan/zoom and instant load on (re)subscribe.
- **v1.52.0** — community-sourced error-code catalog; dp_115 latest-error code
  decoded.
- **v1.53.0** — map card Wi-Fi heatmap and view-mode toggle with no-flicker
  mounts; mission status chip localized via entity translations; the mow path
  split into runs so no phantom diagonal bridges a transit.
- **v1.54.0** — coverage store slimmed (coarse simplify plus point cap).
- **v1.55.0** — path-extraction cache for the live map feed.
- **v1.56.0** — one scene build shared across a hub's feeds.
- **v1.57.0** — the camera's live-view static rebuild throttled, so streaming a
  mow stays cheap.
- **v1.58.0** — the dock and mower stand out against the mowed area on the card.
- **v1.59.0** — active faults shown on the map; error 909 catalogued.
- **v1.60.0** — **Fault** sensor carrying the active fault as readable text.
- **v1.61.0** — option to treat any finished job as 100 % complete.
- **v1.62.0** — missing and untranslated strings completed in all locales.

> Entries for v1.33.0–v1.41.0 are consolidated into the fork's squashed
> pre-v1.41 history and are not itemized here.
