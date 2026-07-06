Unofficial / Reverse-Engineered Data Points
===

> ⚠️ **This is NOT official TerraMow documentation.**
>
> The data points on this page are **not** described in the official
> [`data_point.md`](./data_point.md). Their field names and meanings were
> **reverse-engineered from the live diagnostics of a single device**
> (TerraMow S1200, serial `MP511…`, firmware `9.9.210`). They may differ — or
> be absent — on **other models (S800, V1000, …) and other firmware versions**.
>
> Every entity built from these data points:
> - parses **defensively** — a missing or differently-shaped field makes the
>   entity report `None` / `unavailable`, it never crashes the integration;
> - is categorised as **diagnostic** so it is clearly separated from the
>   officially-supported entities; the more niche ones are **disabled by
>   default** — enable them in the entity settings if you need them;
> - is derived from observed payloads only, so treat the semantics below as a
>   best-effort interpretation, not a contract.
>
> The authoritative reference remains [`data_point.md`](./data_point.md). If you
> can confirm or correct any of these on your device/firmware, please open an
> issue with a diagnostics export (`Settings → Devices & Services → TerraMow →
> ⋮ → Download diagnostics`, block `unknown_data_point_payloads`).

## How these were found

The integration subscribes to `data_point/0..200/robot`. Any id without a
registered handler is logged once and its latest payload is kept for the
diagnostics export (`unknown_data_point_payloads`). The entries below come from
such an export.

The export also carries a **timestamped change-history** per undocumented dp
(`unknown_data_point_history`) — only *value changes* are recorded, so it is a
compact trace of transitions rather than raw traffic. This is the best way to
decode the **dynamic** dps (e.g. dp_109, dp_134): enable debug logging, drive
the mower through a few deliberate actions (start/stop mowing, dock, change a
setting), then export **once** and line the timestamps up with what you did.

## Implemented data points

| ID | Meaning | Observed payload | Surfaced as |
|----|---------|------------------|-------------|
| 102 | Device / network info; carries the real app firmware version | `{"version":"9.9.210","sn":"…","wifi_mac":"…","ip":"…","ssid":"…","warranty":{…}}` | firmware `update` entity version + device `sw_version` (identifiers kept private) |
| 116 | Active-error list | `{"error_list":[]}` | **Active errors** sensor (count + `errors` attribute) |
| 122 | Full weekly schedule (richer than dp_138). Only the `SCHEDULE_CMD_TYPE_GET` response carries a `schedule_list`; `ADD`/`DELETE` are write commands acked without one (the schedule is therefore writable over MQTT — a possible future "edit calendar" feature). The hub issues the `GET` on connect | `{"cmd_type":"SCHEDULE_CMD_TYPE_GET","schedule_list":{"items":[{"id":0,"schedule_type":"SCHEDULE_TYPE_GLOBAL_V2","global_schedule_v2":{"basic_config":{"week_days":["WEEK_DAY_MONDAY",…],"start_time":{"hour":9,"minute":30},"end_time":{"hour":11,"minute":0},"disabled":false,"run_once":false}}}],"global_disabled":false,"disabled_week_days":[],…}}` | Schedule `calendar` entity: renders every recurring weekly slot when available, otherwise falls back to the dp_138 next-slot view |
| 123 | Event log | `{"event_list":[{"code":8,"time":"…Z"}]}` | **Last event** sensor (latest `code` + `event_time` attribute) |
| 129 | Per-component firmware versions | `{"ap_app":"9.9.210","main_controller":"09.09.210",…}` | firmware `update` entity `component_versions` attribute |
| 134 | Undecoded binary flag. Observed toggling `enum_value` between `0` and `1` during operation — so it is a live state, **not** a constant. Its actual meaning is unknown; surfaced only so it can be correlated with mower behaviour and decoded | **State flag 134** binary sensor (raw `enum_value`: `1` → on, `0` → off; diagnostic, **disabled by default**) |
| 135 | Cellular / 4G modem info (only on models with a modem) | `{"is_enabled":false,"RSRP":0,"RSRQ":0,"type":"CELLULAR_TYPE_UNKNOWN",…}` | **Cellular enabled** binary sensor; **Cellular RSRP** / **RSRQ** / **type** sensors (signal sensors are `None` while disabled) |
| 150 | Advanced settings (partly writable on the device; surfaced read-only here) | `{"enable_cliff_detection":{"value":true},"enable_slope_detection":{"value":false},"rain_sensor_threshold":{"upper_limit":1000},"after_rain_stop_setting":{"enable_auto_resume":false,"auto_resume_delay_time":{"hours":2,"minutes":0}},…}` | **Cliff detection** / **Slope detection** / **After-rain auto-resume** / **Force single base station** / **Force cellular network** binary sensors; **Rain sensor threshold** / **After-rain resume delay** sensors (`mow_spacing`/`mow_speed` come via dp_155; `disable_wifi_*` truncated in the sample, not surfaced) |
| 152 | Environment / status | `{"is_defogger_heating":false,"is_illuminate_light_on":false,"sunrise":{"hour":5,"minute":29},"sunset":{…},"is_not_in_daylight_period":false,"manual_mapping":{…}}` | **Sunrise** / **Sunset** sensors; **Defogger heating** / **Illumination** / **Daylight** binary sensors; **Manual mapping: relocation / takeover / boundary-closed** binary sensors |
| 154 | Operating modes | `{"move_mode":"MOVE_MODE_MOW","map_mode":"MAP_MODE_BASE_STATION","mow_mode":"MOW_MODE_GLOBAL"}` | **Movement** / **Map** / **Mowing** mode sensors (raw device enum) |
| 157 | Extreme-weather warning (note device spelling `extream`) | `{"has_extream_weather":false,"extream_weather_info_url":""}` | **Extreme weather** binary sensor (safety; `info_url` attribute) |

## Observed but not yet surfaced

Documented here for future work; not decoded into entities yet.

| ID | Likely meaning | Observed payload (truncated) |
|----|----------------|------------------------------|
| 109 | **Dynamic** scalar — observed rising `54 → 55 → 58 → 61 → 67 → 68 → 70` while the mower ran, so it is a live gauge, **not** a constant. Range/behaviour is consistent with a temperature (°C) or a load/utilisation metric; needs correlation against a known quantity to confirm | `{"int_value":70}` |
| 110 | Unknown scalar | `{"int_value":60}` |
| 111 | Upload progress | `{"is_uploading":false,"process":0}` |
| 114 | Unknown scalar | `{"int_value":8}` |
| 118 | Unknown scalar (percentage?) | `{"int_value":100}` |
| 119 | Command acknowledgement — echoes the request's `seq` with `code:0` (= OK). The `seq` values match those sent in dp_122 `GET`/`ADD`/`DELETE` (and other writes), i.e. this is the generic per-command ack channel | `{"seq":1783335426,"code":0}` |
| 145 | Custom-passage creation status | `{"stage":"CUSTOM_PASSAGE_STAGE_INVALID","is_on_grass":false,…}` |
| 146 | Unknown scalar | `{"int_value":1}` |
