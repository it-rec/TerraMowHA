# TerraMow Integration Architecture

Maintainer-facing notes on the *internals* of the `terramow` custom integration
(`custom_components/terramow/`). It explains how the Python code is wired
together — the hub, the threading model, the data-point catalog, the map/path
pipeline and the config-entry lifecycle.

For the **on-the-wire protocol** (MQTT topics, data-point payloads, the map/path
HTTP capability, the `model/name` topic) see the protocol reference instead:

- [`docs/en/developers.md`](./en/developers.md) — MQTT topics, special topics, map JSON schema
- [`docs/en/developers/`](./en/developers/) — per-data-point and map/path capability docs

This document deliberately does **not** re-describe payload formats; it documents
how the integration *consumes* them.

## 1. Overview

TerraMow is a `local_push`, `device`-type integration (`manifest.json`,
`quality_scale: platinum`). A single config entry represents one mower reached
over its built-in, unauthenticated MQTT broker on port 1883 (username
`terramow`, password = the app pairing password). All protocol state lives in a
single **hub** object (`hub.TerraMowHub`); the 11 entity platforms are thin
read/command surfaces over that hub. Because the device pushes state, entities
refresh reactively (via callbacks) rather than by polling — every platform sets
`PARALLEL_UPDATES = 0`.

The 11 platforms (`__init__.PLATFORMS`): `lawn_mower`, `sensor`,
`binary_sensor`, `select`, `number`, `camera`, `update`, `button`, `switch`,
`event`, `calendar`.

## 2. Component map

| Module | Purpose |
| --- | --- |
| `__init__.py` | Config-entry setup/unload, `TerraMowBasicData`/`TerraMowConfigEntry`, device-id migration, version-compatibility logic, shared `start_select_region` service |
| `hub.py` | `TerraMowHub` — owns the MQTT client + worker thread, all dp caches, map/path HTTP fetching, command helpers, enums (`Mission`, `SubMission`, `MissionState`, …) |
| `entity.py` | `TerraMowEntity` base — shared `device_info`, `unique_id` scheme, default `available` |
| `entity_utils.py` | Thread-safe state helpers (`safe_write_ha_state`, `safe_schedule_update_ha_state`) and `PushUpdateMixin` |
| `config_flow.py` | User/zeroconf/reauth/reconfigure flows, options (map resolution), `validate_input`, `CannotConnect`/`InvalidAuth` |
| `const.py` | `DOMAIN`, MQTT constants, topic names, version thresholds, enum-token helpers (`to_ha_enum_state`/`to_device_enum`), map-resolution options |
| `diagnostics.py` | Redacted config-entry diagnostics dump (compatibility, device, cached state) |
| `issues.py` | Repair issues: firmware compatibility + blade/base-station maintenance |
| `lawn_mower.py` | `LawnMowerEntity` — maps hub mission state to `LawnMowerActivity`, forwards start/pause/dock |
| `sensor.py` | ~25 sensors (battery, statistics, session, maintenance, mission enums, pose, version) + imports map sensors |
| `map_sensor.py` | Map-derived sensors (`map_status`, `map_area`, `clean_mode`); added by the `sensor` platform, not its own platform |
| `binary_sensor.py` | Charging, navigation-located, upgrading, power switch, problem, rain, map-status and task-status binary sensors |
| `select.py` | Zone select, mow-speed, blade-speed, main-direction mode, high-grass edge-trim mode |
| `number.py` | Mow height/spacing, edge-cutting distance, main-direction angles/interval (all dp_155 writers) |
| `camera.py` | `TerraMowMapCamera` — renders map + path + history + live pose into a PNG scene; two variants (normal + clean-mode) |
| `update.py` | Read-only firmware `UpdateEntity` — real version from dp_102, `in_progress` from dp_107 `is_upgrading`, component versions from dp_129 |
| `button.py` | Edge-trim start, reset blade timer (dp_126←0), reset base-station timer (dp_125←0) |
| `switch.py` | Thorough-corner-cutting toggle (writes dp_155) |
| `event.py` | Fires HA events on mission phase transitions (started/paused/returning/docked/completed/error) |
| `calendar.py` | Read-only schedule calendar — full weekly slots (dp_122) when available, else the next scheduled mow (dp_138) |
| `map_card.py` | Interactive map card backend: serves `frontend/terramow-map-card.js` (auto-loaded via `frontend.add_extra_js_url`) and the `terramow/map/subscribe` WebSocket feed pushing the `build_scene` geometry + display robot pose to subscribed cards |
| `frontend/terramow-map-card.js` | The Lovelace card: canvas vector renderer (pan/zoom/fit, theme-aware), live robot marker, tap-to-mow zone selection calling `terramow.start_select_region` |

## 3. Config-entry lifecycle

`TerraMowConfigEntry = ConfigEntry[TerraMowBasicData]` — the live integration
state is carried in `entry.runtime_data`, not `hass.data`.

`async_setup_entry` (`__init__.py`):

1. **Device-identifier migration** — renames a legacy device identifier tuple
   `('TerraMowLanwMower', host)` (typo) to `('TerraMowLawnMower', host)`,
   skipping if a device with the new id already exists.
2. **Credential validation** — `validate_input()` opens a throwaway MQTT
   connection. `InvalidAuth` → `ConfigEntryAuthFailed` (triggers reauth);
   `CannotConnect` → `ConfigEntryNotReady` (HA retries setup later).
3. Builds `TerraMowBasicData(host, password, entry_id=…)` and assigns
   `entry.runtime_data`. HA clears `runtime_data` automatically on unload.
4. Creates and **starts the hub before forwarding platforms** so every entity
   can register callbacks in its `async_added_to_hass` regardless of platform
   load order. `TerraMowHub.__init__` sets `basic_data.lawn_mower = self` (the
   attribute keeps its historical name — entities reach the hub through
   `basic_data.lawn_mower`).
5. `async_forward_entry_setups(entry, PLATFORMS)`, then registers an update
   listener (`_async_options_updated` reloads the entry on options change) and
   the shared service.

`_async_register_services` — registers the domain-level `start_select_region`
service **idempotently** (`has_service` guard), so it is registered once even
with multiple entries. The handler resolves target entities via the entity
registry, validates each resolves to a loaded `runtime_data` with a ready
`lawn_mower`, then calls `basic_data.lawn_mower.start_select_region_clean()`.

`async_unload_entry`:

1. `async_unload_platforms`; on success:
2. clears the compatibility and both maintenance **repair issues**
   (`async_clear_compatibility_issue` / `async_clear_maintenance_issues`),
3. stops the hub (`await basic_data.lawn_mower.async_stop()`),
4. removes the shared `start_select_region` service **only when no other loaded
   entry remains** (`async_loaded_entries` minus this one).

`TerraMowBasicData` also owns the firmware-version compatibility logic
(`check_version_compatibility`, `get_compatibility_message`), producing a
`CompatibilityStatus` from the firmware's `overall` and `module.home_assistant`
versions against `const.MIN_REQUIRED_OVERALL_VERSION` / `MIN_SUPPORTED_HA_VERSION`
/ `CURRENT_HA_VERSION`.

## 4. The hub (`hub.TerraMowHub`)

The hub owns the MQTT connection and every piece of protocol state (dp caches,
robot mission/sub-mission/state enums, map/path/pose caches, HTTP fetch state).

- **`start()`** — constructs a `paho.mqtt.client.Client`, sets
  `on_connect`/`on_disconnect`/`on_message`, launches a **daemon worker thread**
  running `mqtt_loop()`, then calls `register_all_callbacks()`.
- **`mqtt_loop()`** — the reconnect loop. Connects, then blocks in
  `loop_forever()`. On any exception it increments a failure counter, sets the
  connection-error flag, and waits with **exponential backoff**
  (`MQTT_RECONNECT_BASE_DELAY * 2^(n-1)`, capped at `MQTT_RECONNECT_MAX_DELAY`).
  Logging is **throttled**: first failure is `WARNING`, subsequent ones drop to
  `DEBUG`, so an unreachable/sleeping/docked mower doesn't flood the log. The
  wait uses `self._stop_event.wait(delay)` so shutdown is immediate.
- **`on_mqtt_connect`** — subscribes to `data_point/{0..200}/robot`, the map
  info/meta topics, path/history meta, pose, and `model/name`; then actively
  requests compatibility info (publishes to dp 127). Clears the error flag and
  notifies state listeners.
- **`async_stop()`** — sets `_stop_event`, cancels retry tasks and pending meta,
  calls `mqtt_client.disconnect()` (so `loop_forever()` returns), then
  **joins the worker thread** in an executor with `MQTT_THREAD_JOIN_TIMEOUT`
  so a reload/reconfigure never leaves a zombie thread reconnecting in the
  background.

Callback registries:

| Registry | Registrar | Fired from |
| --- | --- | --- |
| `callbacks: dict[int, list]` (per dp_id) | `register_callback(dp_id, cb)` | `on_mqtt_message` dp dispatch |
| `map_callbacks` | `register_map_callback` | `_update_map_info` / meta fetch |
| `pose_callbacks` | `register_pose_callback` | pose topic |
| `path_callbacks` / `history_path_callbacks` | `register_path_callback` / `register_history_path_callback` | meta-driven HTTP fetch |
| `_state_listeners` | `register_state_listener` | `_notify_state_listeners` (connection, dp_107, model) |

The map/pose/path/history registrars immediately replay the last cached value
to a newly-registered callback (via `hass.add_job`) so late-arriving entities
get current data.

**`on_mqtt_message`** dispatches by topic: `map/current/meta`,
`path/current/meta`, `path/history/meta` cache the raw meta then schedule the
async handler; `pose/current` caches and fans out to pose callbacks;
`map/current/info` and `model/name` are handled inline; anything matching
`data_point/{id}/robot` (regex `TOPIC_PATTERN`) is routed to the registered dp
callbacks.

## 5. Threading model (important)

Two execution contexts exist and the boundary matters for correctness.

**Runs on the MQTT worker thread** (not the event loop):
`mqtt_loop`, `on_mqtt_connect`, `on_mqtt_disconnect`, `on_mqtt_message`, and
anything they call *synchronously* — notably `_set_connection_error()` and
`_handle_model_name()`, both of which call `_notify_state_listeners()`.

**Marshalled onto the HA event loop:** dp callbacks and pose/map/path callbacks
are dispatched with **`hass.add_job(callback, payload)`**, so every `on_*`
handler (`on_mission_status`, `on_battery_status`, …) and every push refresh
runs on the loop. Device-registry updates are likewise scheduled with
`hass.add_job`.

Consequence — the split responsibilities:

- **dp callbacks / `on_*` handlers run on the loop.** They may safely mutate
  caches and call loop-only APIs. `on_mission_status` (dp_107) calls
  `_notify_state_listeners()`, but since it was itself dispatched via
  `add_job`, that path is already on the loop.
- **State listeners may run on the MQTT thread.** They fire from
  `_set_connection_error` (connection changes, from `mqtt_loop`) and from
  `_handle_model_name` (from `on_mqtt_message`). Therefore any
  `register_state_listener` callback **must be thread-safe**:
  - `lawn_mower.TerraMowLawnMowerEntity._on_hub_state` uses
    `safe_schedule_update_ha_state`.
  - `event.TerraMowMowerEventEntity._on_hub_state` computes the transition, then
    hands the actual `_trigger_event`/state-write to the loop via
    `hass.add_job(self._async_drain_pending)`.

`entity_utils` provides the guards:

- **`safe_write_ha_state` / `safe_schedule_update_ha_state`** — no-op (return
  early) when `entity.hass is None or entity.entity_id is None`, i.e. before
  `async_added_to_hass` completes or after removal, and swallow the
  `RuntimeError: Attribute hass is None` that MQTT-timing races otherwise raise
  (upstream issue #77). Everything that can write state off the happy path goes
  through these.
- **`PushUpdateMixin`** — declarative push updates. A subclass sets
  `_push_dp_ids: tuple[int, ...]` (and/or `_push_map_info = True`); in
  `async_added_to_hass` the mixin registers `_handle_push_update` for each dp id
  and `_handle_map_push_update` for the map topic. Both simply call
  `safe_write_ha_state(self)`, so the entity re-renders the moment the relevant
  MQTT data arrives instead of waiting for HA's 30 s poll. `for TYPE_CHECKING`
  the mixin declares an `Entity` base (dropped at runtime) so mypy resolves
  `super().async_added_to_hass()`.

## 6. Data-point catalog

Handlers registered in `register_all_callbacks()`. The device→HA payloads are
cached on the hub and exposed via `@property`; consuming entities read those
properties (mostly through `PushUpdateMixin._push_dp_ids`).

| dp_id | Dir | Hub handler | Cached property | Consumed by | Meaning |
| --- | --- | --- | --- | --- | --- |
| 8 | in | `on_battery_level` | `battery_level` | `BatterySensor` (push) | Battery percentage |
| 102 | in | `on_device_info` | `firmware_version_name`, `_robot_info` | firmware `UpdateEntity` (installed/latest version), device `sw_version` | Device/network info; carries the real app firmware version (`version`, e.g. "9.9.210") plus SN/MAC/IP (kept private) |
| 103 | **out** | — (`_start_normal_mow`, `start_select_region_clean`, `_start_edge_trim`, `_start_normal_recharge`) | — | lawn_mower, button, service | Start-mode command (global/select-region/edge-trim/return) |
| 105 | **out** | `_send_pause_command` | — | lawn_mower pause | Pause command |
| 106 | **out** | `_resume_mow` / `_resume_recharge` | — | lawn_mower resume | Resume command |
| 107 | in | `on_mission_status` | `task_status`, `mission`, `sub_mission`, `mission_state`, `power_mode`, `is_robot_navi_located`, `is_upgrading`, `has_error`, `back_to_station_reason`, `is_saving_data`, `is_data_conversion_in_progress` | lawn_mower, event, mission/sub-mission/state sensors, power-mode, back-to-station, problem/rain/navigation/upgrading/saving/conversion binary sensors | Mission status (drives the whole activity model); fires state listeners |
| 108 | in | `on_battery_status` | `battery_status` | battery state/temperature sensors, charging + power-switch binary sensors, camera (battery-connected) | Battery status payload |
| 113 | in | `on_current_work_data` | `current_work_data` | current-session area/time/progress + job-type sensors | Current mowing-session work data |
| 116 | in | `on_error_list` | `error_list` | Active-errors sensor | *Unofficial* — active-error list; see [`data_point_unofficial.md`](./en/developers/data_point_unofficial.md) |
| 117 | in | `on_map_status` | `map_status` | `map_status` sensor, map-detected/buildable/backing-up binary sensors | Map status flags |
| 118 | in | `on_map_save_progress` | `map_save_progress` | Map-save-progress sensor (diagnostic, disabled by default) | *Unofficial* — map-save/upload progress 0–100 %; see [`data_point_unofficial.md`](./en/developers/data_point_unofficial.md) |
| 122 | in / **out** | `on_full_schedule` | `full_schedule` | schedule calendar (full weekly view) | *Unofficial* — full weekly schedule list; requested on connect via `SCHEDULE_CMD_TYPE_GET`, only sent in response; see [`data_point_unofficial.md`](./en/developers/data_point_unofficial.md) |
| 123 | in | `on_event_data` | `event_list` | Last-event sensor | *Unofficial* — device event log; see [`data_point_unofficial.md`](./en/developers/data_point_unofficial.md) |
| 124 | in | `on_statistics_data` | `statistics_data` | total mowing time/jobs/area sensors | Lifetime statistics |
| 125 | in / **out** | `on_base_station_time` | `base_station_time` | remaining base-station-time sensor, reset button (writes `int_value:0`) | Base-station usage minutes; syncs maintenance repair issue |
| 126 | in / **out** | `on_blade_time` | `blade_time` | remaining blade-time sensor, reset button (writes `int_value:0`) | Blade-disk usage minutes; syncs maintenance repair issue |
| 127 | in / **out** | `on_compatibility_info` (`COMPATIBILITY_INFO_DP`) | `firmware_version_info`, `compatibility_status`/`_message` | version-compatibility sensor, firmware update entity (version *fallback* only) | Version/compatibility info (`overall.ha_module`, e.g. "28.3" — an internal compat number, **not** the app firmware version); requested on connect, drives compatibility repair issue + device `sw_version` fallback |
| 129 | in | `on_component_versions` | `component_versions` | firmware `UpdateEntity` attributes | Per-component firmware versions (`ap_app`, `main_controller`, `drive_wheel`, `mow_motor`, loaders) |
| 134 | in | `on_state_flag_134` | `state_flag_134` | "State flag 134" binary sensor (diagnostic, disabled by default) | *Unofficial* — undecoded binary flag (`enum_value` toggles 0/1); see [`data_point_unofficial.md`](./en/developers/data_point_unofficial.md) |
| 135 | in | `on_cellular_info` | `cellular_info` | cellular enabled/RSRP/RSRQ/type sensors | *Unofficial* — cellular/4G modem info; see [`data_point_unofficial.md`](./en/developers/data_point_unofficial.md) |
| 138 | in | `on_schedule_data` | `schedule_data` | next-scheduled-start sensor, schedule calendar | Upcoming scheduled mow slot |
| 150 | in | `on_advanced_settings` | `advanced_settings` | cliff/slope/after-rain-resume/force-single-base/force-cellular binary sensors, rain-threshold + resume-delay sensors | *Unofficial* — advanced settings (read-only); see [`data_point_unofficial.md`](./en/developers/data_point_unofficial.md) |
| 152 | in | `on_environment_info` | `environment_info` | sunrise/sunset sensors, defogger/illumination/daylight + manual-mapping binary sensors | *Unofficial* — environment/status; see [`data_point_unofficial.md`](./en/developers/data_point_unofficial.md) |
| 154 | in | `on_operating_modes` | `operating_modes` | move/map/mow-mode sensors | *Unofficial* — operating modes; see [`data_point_unofficial.md`](./en/developers/data_point_unofficial.md) |
| 157 | in | `on_weather_info` | `weather_info` | extreme-weather binary sensor | *Unofficial* — extreme-weather warning; see [`data_point_unofficial.md`](./en/developers/data_point_unofficial.md) |
| 155 | in / **out** | `on_global_params` | `global_params` | mow-height/speed sensors, main-direction status, mow-speed/blade-speed/main-direction selects, all `number` entities, thorough-corner-cutting switch | Global work parameters; writes go back to dp_155 |

Notes:

- **Directions.** `in` = `data_point/{id}/robot` (device→HA); `out` =
  `data_point/{id}/app` published via `publish_data_point`. dp 103/105/106 are
  command-only. dp 155/125/126/127 are bidirectional.
- **dp_112 vs dp_127.** The compatibility handler is registered under
  `COMPATIBILITY_INFO_DP` (= **127**) and both the request and response use dp
  127. `on_compatibility_info`'s docstring says "(dp_112)", but that is a stale
  reference — there is **no** live handler bound to dp_112. Treat 127 as the
  compatibility/version data point.
- **Undocumented-dp discovery.** In `on_mqtt_message`, a
  `data_point/{id}/robot` message with no registered callback is logged once at
  `INFO` (with the first payload, truncated) and thereafter at `DEBUG`; the
  seen ids accumulate in `_seen_unknown_dp_ids` and appear in diagnostics under
  `unknown_data_points_seen`, while the latest raw payload per unhandled id is
  kept in `_unknown_dp_payloads` and exported under
  `unknown_data_point_payloads`. In addition, a bounded, timestamped **change
  history** per unhandled id (`_unknown_dp_history`, only value changes, capped
  at `UNKNOWN_DP_HISTORY_MAXLEN`) is exported under `unknown_data_point_history`
  so a single export shows how *dynamic* dps move over time. This is the
  intended way to discover new dps (lift-off alarms, error codes, schedule
  toggles, …) — export diagnostics and read the payloads/history to identify
  them.

## 7. Map / path pipeline

Live map/path/history are delivered as **metadata over MQTT** pointing at a
**gzipped JSON body fetched over HTTP** (HA compat v3+). The three flows are
symmetric — `_async_handle_map_meta`, `_async_handle_path_meta`,
`_async_handle_history_path_meta`:

1. `on_mqtt_message` (worker thread) caches the raw meta and schedules the
   async handler with `hass.add_job` (→ loop).
2. **Seq guard.** Each meta carries a `seq`. A meta with `seq <= _{kind}_seq` is
   dropped. Path/history additionally detect a **backward seq** (new mowing
   session republishing from 0) and reset `_{kind}_seq`/`_{kind}_etag` so the
   fresh path isn't hidden until reload.
3. **No-seq throttle.** When `seq == -1` (unsequenced), fetches are rate-limited
   to one per `_no_seq_min_interval` (5 s) via `_{kind}_no_seq_last_fetch`.
4. **In-flight coalescing.** While a fetch is running (`_fetching_{kind}`) a
   newer meta is stored as `_pending_{kind}_meta` (kept only if it supersedes
   the pending one, per `_should_replace_pending`) and re-run in the `finally`.
5. **`_async_fetch_json`** builds `http://{host}:{http_port}{http_path}` with a
   `Bearer {token}` header and an **`If-None-Match: {etag}`** conditional. A
   `304` returns "not modified"; `>=400` fails; otherwise it captures the new
   `ETag`, manually gunzips bodies starting with the gzip magic
   (`\x1f\x8b`, decompressed in an executor), parses JSON, and caches it.
   Returns `(data, etag, ok, not_modified)`.
6. **Retry/backoff.** On failure `_schedule_{kind}_retry` runs
   `_async_retry_{kind}` after a growing delay (`_get_retry_delay`:
   2/5/10/30 s) using the last meta; a successful fetch resets the retry state.

Parsed map data is folded into `_map_info` by `_build_map_info_from_map_data`
(tolerant of `id`/`map_id`/`mapId` etc.; a changed map id resets the merge) and
fanned out to `map_callbacks`; path/history data fan out to their callbacks.

**Camera.** `TerraMowMapCamera` (`camera.py`) registers map, path, history,
pose and battery (dp_108) callbacks. Each callback stores the layer, invalidates
the cached PNG, rebuilds the static base image in an executor, and writes state.
`async_camera_image` renders the final scene (static map + paths + live robot
pose) off-thread. A `CoordinateTransformer` maps device coordinates into the
output canvas; output resolution comes from the `map_resolution` option. Two
entities are created: the normal camera and an opt-in borderless "clean-mode"
variant (`entity_registry_enabled_default = False`).

## 8. Repair issues (`issues.py`)

Repair issues surface conditions that a bare sensor would bury, as actionable
dashboard cards.

- **Firmware compatibility** — `async_sync_compatibility_issue` mirrors
  `basic_data.compatibility_status` (computed in `on_compatibility_info` from
  dp_127). `UPGRADE_REQUIRED` → `firmware_ha_module_too_low` /
  `firmware_overall_too_low` (ERROR); `INCOMPATIBLE` → `firmware_incompatible`
  (ERROR); `DOWNGRADE_RECOMMENDED` → `plugin_downgrade_recommended` (WARNING);
  `COMPATIBLE` (including the version-limited case) **deletes** the issue. Issue
  id is per-entry (`firmware_incompatible_{entry_id}`).
- **Maintenance** — `async_sync_blade_maintenance_issue` (from dp_126) and
  `async_sync_base_station_maintenance_issue` (from dp_125) read the payload's
  `int_value` usage minutes and raise a WARNING issue once it reaches the cycle
  (`BLADE_MAINTENANCE_CYCLE_MINUTES` = 14400 min / 240 h;
  `BASE_STATION_MAINTENANCE_CYCLE_MINUTES` = 43200 min / 30 d), clearing it
  otherwise. Reset buttons write `int_value:0` back to dp_125/126, which clears
  the issue on the next report.

All three are cleared on unload by `async_clear_compatibility_issue` /
`async_clear_maintenance_issues`.

## 9. Config & discovery (`config_flow.py`)

- **User flow** (`async_step_user`) — asks for host + password, runs
  `validate_input`, sets the **host as the unique id** and aborts if already
  configured.
- **Zeroconf** (`async_step_zeroconf`) — triggered by `_mqtt._tcp.local.` with a
  `terramow*` name (`manifest.json`). Sets the unique id from the discovered
  host (updating `CONF_HOST` on an existing entry), then routes to
  `async_step_user_pass` which only asks for the password.
- **Reauth** (`async_step_reauth` → `_confirm`) — re-prompts for the password,
  re-validates, updates the entry and reloads. Entered when setup raised
  `ConfigEntryAuthFailed`.
- **Reconfigure** (`async_step_reconfigure`) — lets the user change host/password
  (e.g. after a DHCP IP change), aborting if the new host collides with another
  entry, then reloads.
- **Options** (`TerraMowOptionsFlow`) — a single `map_resolution` choice from
  `MAP_RESOLUTION_OPTIONS` (1024–4096), default 1024. Changing it fires
  `_async_options_updated`, which reloads the entry.

`validate_input` proves connectivity by attempting an MQTT connect in an
executor: rc 4/5 → `InvalidAuth`, any other failure → `CannotConnect`.

## 10. Testing & quality gates

CI (`.github/workflows/validate.yml`) enforces:

- **100 % coverage** — `pytest … --cov=custom_components/terramow
  --cov-fail-under=100`, with `branch = true` in `[tool.coverage.run]`. The
  suite covers every line **and branch**; the floor cannot silently regress.
- **`mypy` strict** — `mypy` with `[tool.mypy] strict = true`,
  `disallow_untyped_defs`, `warn_return_any`; `follow_imports = silent` so
  third-party gaps (homeassistant, paho) don't break the gate. Every shipped
  module is fully typed.
- **hassfest** and **HACS** validation (the HACS job ignores store-only repo
  metadata: `topics description issues`).
- Ruff lint (non-blocking, `continue-on-error`) and `compileall`.

The **single `# pragma: no cover`** is in `hub.on_mqtt_message`: the
`int(match.group(1))` `ValueError` branch is unreachable because the topic regex
(`TOPIC_PATTERN`, `data_point/(\d+)/robot`) already guarantees the captured
group parses as an int — it exists only as defensive code, so it is excluded
from the coverage requirement. `[tool.coverage.report]` also excludes
`if TYPE_CHECKING:` blocks.
