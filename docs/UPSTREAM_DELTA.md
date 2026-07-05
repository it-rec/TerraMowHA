# What this fork adds over upstream

This document tracks the differences between `it-rec/TerraMowHA` and the
upstream project [`TerraMow/TerraMowHA`](https://github.com/TerraMow/TerraMowHA).
Keep it up to date when landing changes that diverge from upstream.

At the time of writing, upstream's latest tag is **v0.3.0**; this fork is on the
**v1.0.x** line. The fork is a strict superset — every upstream capability is
retained — plus the additions below.

## New platforms & entities

| Platform | What it adds |
|---|---|
| **Event** (`event.py`) | A mower event entity firing `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, each with the raw mission fields as attributes. Lets automations react to transitions without polling. |
| **Calendar** (`calendar.py`) | A read-only mowing-schedule calendar built from dp_138 (next scheduled mow), with active/upcoming/next-day and past-midnight handling. |
| Camera | A second, default-disabled *clean* map-only camera for dashboards, plus a configurable output resolution. |
| Sensor | A default-disabled pose sensor. |

## New user-facing capabilities

- **Repair issues** (`issues.py`): actionable dashboard cards for
  incompatible/too-old firmware (from dp_127) and for due blade (240 h) /
  base-station (30 day) maintenance (from dp_126 / dp_125), which clear
  themselves once resolved.
- **Diagnostics** (`diagnostics.py`): a redacted JSON snapshot for bug reports.
- **`terramow.start_select_region` service** with translated exceptions.
- **Reauthentication** and **reconfigure** flows, **Zeroconf/mDNS discovery**
  (`_mqtt._tcp.local.`, `terramow*`), and an **options flow** (map resolution).
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
- **Hardened hub**: MQTT auto-reconnect with exponential backoff and throttled
  logging; map/path HTTP fetch over Home Assistant's shared aiohttp session with
  ETag caching, sequence guards, retry/backoff and pending-meta requeue; a clean
  worker-thread join on unload.
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
