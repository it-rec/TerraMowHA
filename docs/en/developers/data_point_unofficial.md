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
| 116 | Active-error list | `{"error_list":[{"code":…}]}` (empty on the reference device) | **Active errors** sensor (count + `errors` attribute) and the **Fault** sensor (the active fault as readable text via `error_codes.py`, `error_codes` attribute); also drives the **Problem** binary sensor / lawn-mower **error** state / mower **error** event (any non-empty list is a fault, `error_codes` attribute), because dp_107 `has_error` alone misses some faults (issue [#171]) |
| 118 | Map-save / upload progress (0–100 %). Ramps while the device saves its map after a mow (`SUB_MISSION_SAVING_MAP` / "map is being saved"), confirmed by watching it climb `1 → … → 100` in lock-step with the app's on-screen "map saving %" | `{"int_value":42}` | **Map save progress** sensor (`%`; diagnostic, **disabled by default**) |
| 119 | Command acknowledgement — echoes a command's `seq` with `code:0` (= OK) or a non-zero error code. **Field finding (V1000 fw28):** the device does *not* ack commands sent over local MQTT by this integration — dp_119 acks observed there carry epoch-like seqs belonging to the mower's internal (BLE/cloud) commander, and unparseable dp_122 payloads are dropped silently (no rejection code). Schedule-write negotiation therefore relies on `GET` verification | `{"seq":1783335426,"code":0}` | **Confirmed commands**: `terramow.start_select_region` (and the map card's tap-to-mow) waits for the ack and surfaces rejections; rejected fire-and-forget commands log a warning; last ack in diagnostics |
| 109 | **Wi-Fi signal strength** of the mower's own link, in percent (~= `2 * (RSSI dBm + 100)`). Identified empirically: pinned at 98 right next to an access point (router-side −42 dBm), a noisy 52–68 on the lawn through a wall (router-side −75…−80 dBm), 98 inside a concrete cellar (rules out the earlier GNSS-quality guess) and uncorrelated with the battery level. Note the FRITZ!Box-style router-side reading measures the *other* end of the asymmetric link and differs by up to ~10 dBm, more across mesh-AP roaming / 2.4↔5 GHz switches | `{"int_value":62}` | **Wi-Fi signal** sensor (%; diagnostic) |
| 122 | Full weekly schedule (richer than dp_138). Only the `SCHEDULE_CMD_TYPE_GET` response carries a `schedule_list`; `ADD`/`DELETE` are write commands acked without one (the schedule is therefore writable over MQTT — a possible future "edit calendar" feature). The hub issues the `GET` on connect, and captures app-direction dp_122 traffic (DEBUG log + diagnostics `schedule_app_captures`) so the exact `ADD`/`DELETE` write format can be documented from real app usage | `{"cmd_type":"SCHEDULE_CMD_TYPE_GET","schedule_list":{"items":[{"id":0,"schedule_type":"SCHEDULE_TYPE_GLOBAL_V2","global_schedule_v2":{"basic_config":{"week_days":["WEEK_DAY_MONDAY",…],"start_time":{"hour":9,"minute":30},"end_time":{"hour":11,"minute":0},"disabled":false,"run_once":false}}}],"global_disabled":false,"disabled_week_days":[],…}}` | Schedule `calendar` entity (weekly slots; event uid = item id) and the **writable schedule**: `terramow.add_schedule` / `terramow.delete_schedule` services. The exact write payload shape is negotiated per firmware — each candidate is verified against a fresh `GET` and every attempt is logged. **Conclusive field finding (V1000 fw overall 28, schedule module 5, home_assistant module 3):** every write candidate is silently dropped — named verbs (`ADD`/`SET`/`UPDATE`/`SAVE`), numeric `cmd_type` 1-6, and every plausible payload shape — while `GET` answers normally; the request message evidently carries only `cmd_type`+`seq`, i.e. **local schedule writes are not exposed by current firmware** (the vendor app writes over BLE/cloud). The services stay in place for future firmware; HA-side scheduling is covered by the weather-adaptive blueprint |
| 123 | Event log | `{"event_list":[{"code":8,"time":"…Z"}]}` | **Last event** sensor (latest `code` + `event_time` attribute) |
| 127 | **Compatibility handshake — and an undocumented capability inventory.** The integration reads only `module.home_assistant` from it (the version gate that drives `compatibility_status` and the firmware repair issues). The same payload also carries `overall`, a `dp` version, and a **~55-entry map of per-feature module versions** — in effect a machine-readable list of what the firmware can do. Observed on a V1000 `overall:28`: `map:16, mission_status:11, control:12, clean_record:7, cellular_network:7, voice_notification:6, custom_passage:5, schedule:5, main_direction_angle:5, anti_theft:4, …`. Two entries stand out by being **`0`** while every other is ≥1, which reads as "not present on this firmware": `custom_mowing` and **`overnight_auto_resume`** — the latter names exactly the behaviour behind issue [#214] (a job that stops at dusk and continues the next morning). Nothing beyond `home_assistant` is decoded yet; the full map is in every diagnostics download, so it is the cheapest place to check whether a feature exists before building for it | `{"overall":28,"dp":8,"module":{"home_assistant":3,"map":16,"overnight_auto_resume":0,…}}` | Firmware compatibility gate and repair issues; the rest of the map is visible in diagnostics only |
| 129 | Per-component firmware versions | `{"ap_app":"9.9.210","main_controller":"09.09.210",…}` | firmware `update` entity `component_versions` attribute |
| 134 | Undecoded binary flag. Observed toggling `enum_value` between `0` and `1` during operation — so it is a live state, **not** a constant. Its actual meaning is unknown; surfaced only so it can be correlated with mower behaviour and decoded | `{"enum_value":1}` | **State flag 134** binary sensor (raw `enum_value`: `1` → on, `0` → off; diagnostic, **disabled by default**) |
| 135 | Cellular / 4G modem info (only on models with a modem) | `{"is_enabled":false,"RSRP":0,"RSRQ":0,"type":"CELLULAR_TYPE_UNKNOWN",…}` | **Cellular enabled** binary sensor; **Cellular RSRP** / **RSRQ** / **type** sensors (signal sensors are `None` while disabled) |
| 150 | Advanced settings (partly writable on the device; surfaced read-only here) | `{"enable_cliff_detection":{"value":true},"enable_slope_detection":{"value":false},"rain_sensor_threshold":{"upper_limit":1000},"after_rain_stop_setting":{"enable_auto_resume":false,"auto_resume_delay_time":{"hours":2,"minutes":0}},…}` | **Cliff detection** / **Slope detection** / **After-rain auto-resume** / **Force single base station** / **Force cellular network** binary sensors; **Rain sensor threshold** / **After-rain resume delay** sensors (`mow_spacing`/`mow_speed` come via dp_155; `disable_wifi_*` truncated in the sample, not surfaced) |
| 152 | Environment / status | `{"is_defogger_heating":false,"is_illuminate_light_on":false,"sunrise":{"hour":5,"minute":29},"sunset":{…},"is_not_in_daylight_period":false,"manual_mapping":{…}}` | **Sunrise** / **Sunset** sensors; **Defogger heating** / **Illumination** / **Daylight** binary sensors; **Manual mapping: relocation / takeover / boundary-closed** binary sensors |
| 154 | Operating modes | `{"move_mode":"MOVE_MODE_MOW","map_mode":"MAP_MODE_BASE_STATION","mow_mode":"MOW_MODE_GLOBAL"}` | **Movement** / **Map** / **Mowing** mode sensors (raw device enum) |
| 157 | Extreme-weather warning (note device spelling `extream`) | `{"has_extream_weather":false,"extream_weather_info_url":""}` | **Extreme weather** binary sensor (safety; `info_url` attribute) |

## Observed but not yet surfaced

Documented here for future work; not decoded into entities yet.

| ID | Likely meaning | Observed payload (truncated) |
|----|----------------|------------------------------|
| 103 | **Ack echo of the dp_103 command channel** (the integration publishes selective-mow / clean commands to `data_point/103/app`): the `/robot` side answers `{seq, ret:0}` per accepted command. Live-confirmed (V1000 fw28): each `start_mowing` / `dock` sent over local MQTT produced exactly one echo with a monotonically increasing `seq` — so unlike dp_119 (which only carries the internal commander's acks on this firmware), dp_103 *does* ack local-MQTT commands. **Draw-region finding (2026-07-22):** a guarded brute-force run fired six draw-region command shapes (`START_MODE_DRAW_REGION_CLEAN` / `_CUSTOM_REGION_CLEAN` / `_DRAW_CLEAN` with `{polygon:{points}}`, `{points}`, `{draw_region_polygons:[…]}` fragments) — **none was acked at all**, while a `START_MODE_SELECT_REGION_CLEAN` control was acked (`ret:0`) and started the mower. So local dp_103 only accepts the documented start modes (`GLOBAL_CLEAN` / `SELECT_REGION_CLEAN` / `EDGE_TRIM_CLEAN` / `RETURN`); there is **no local draw-region start mode** on this firmware (the app draws regions over BLE/cloud), issue [#199] | `{"seq":917327464,"ret":0}` |
| 104 | **Ack fired by the app's "End job / clear auto-mode progress"** action (V1000 fw28): observed exactly once, in the same second the user confirmed "Clear" in the vendor app; presumably the `/robot` ack of an end/clear command channel (the app writes over BLE/cloud, so only the ack is visible locally). `seq` is epoch-like | `{"seq":1784657579,"ret":0}` |
| 110 | Unknown scalar | `{"int_value":60}` |
| 111 | Upload progress (companion of dp_118?). Stayed `{false, 0}` through a full mow with a mid-session recharge dock — whatever it uploads, a normal mow does not trigger it | `{"is_uploading":false,"process":0}` |
| 114 | **Latest event code** — mirrors the newest entry of the dp_123 event log. Observed `int_value:90` at the exact moment dp_123 appended `{code:90}` (a relocation event); earlier `int_value:8` matched dp_123 code 8. **Re-confirmed 2026-07-21 (V1000 fw28):** dp_114 and dp_123 arrive within <100 ms of each other, and a day's dp_114 values (`43`, `87`, `65`) each matched the newest dp_123 `code` with identical timestamps (`65` fired at a recharge-return dock; a cellar relocation had produced `135`) — this also refutes an earlier link-quality-metric hypothesis for this dp. Redundant with the **Last event** sensor, so not surfaced separately | `{"int_value":65}` |
| 115 | **Latest error code** — mirrors the newest entry of the dp_116 active-error list, exactly as dp_114 mirrors the dp_123 event log. Community-confirmed twice on an S1200 fw `9.9.210` (issue [#171]): `int_value:201` arrived in the same instant dp_116 appended `{code:201}` (mower lifted), and `int_value:903` matched `{code:903}` (mower stuck). Decoded into the hub (`active_error_code`); fault surfacing stays on the richer dp_116 list. Known code meanings live in `error_codes.py` | `{"int_value":903}` |
| 120 | Ack/echo-shaped, same family as dp_119 (`code` instead of `ret`); single observation while the mower idled docked, context unknown. `seq` epoch-like | `{"seq":1784579052,"code":0}` |
| 134 | Undecoded binary flag (surfaced as **State flag 134**). Note: it stayed **constant** through a full start/pause/resume/dock session, so it is **not** tied to the mowing state — meaning still unknown | `{"enum_value":0}` |
| 145 | Custom-passage creation status | `{"stage":"CUSTOM_PASSAGE_STAGE_INVALID","is_on_grass":false,…}` |
| 146 | Unknown scalar | `{"int_value":1}` |

## Behavioural findings (official data points)

Reverse-engineered *behaviour* of data points that **are** documented in
[`data_point.md`](./data_point.md), recorded here so that file stays a clean
vendor mirror.

**dp_107 `mission_status` — `mission` resets to `MISSION_IDLE` on docking, with
no pause-vs-complete signal.** When the mower returns to the dock **before it has
finished** (e.g. it ran out of daylight and will resume later), the firmware
reports `mission = MISSION_IDLE` / `sub_mission = SUB_MISSION_IDLE` /
`state = MISSION_STATE_IDLE` — byte-identical to a genuinely completed job.
`back_to_station_reason` does **not** disambiguate it: the official spec notes
that field is only meaningful while `sub_mission` is `SUB_MISSION_RETURN_TO_BASE`
or `SUB_MISSION_FLEXIBLE_STATION_WAIT`, so once the mower is docked-idle it reads
`BACK_TO_STATION_REASON_NONE` (confirmed on S1200 fw `9.9.210`, issue [#142]
comment [4961842352](https://github.com/it-rec/TerraMowHA/issues/142#issuecomment-4961842352)).
No observed dp_107 field marks "paused mid-session, will resume".

- *Consequence:* the raw **Mission** sensor correctly drops to *Idle* here; the
  session-level **Active Job** sensor reconstructs the in-progress job with a
  bounded latch (`ACTIVE_MISSION_DISPLAY_TIMEOUT`), because the device gives no
  direct signal (issue [#173](https://github.com/it-rec/TerraMowHA/issues/173)).
- *To watch for:* on future firmware / diagnostics captures, check dp_107 for a
  new field, or a `back_to_station_reason` that persists past docking, that would
  mark a resumable pause — as well as any still-undecoded neighbouring dp that
  tracks session progress. Any of these would let Active Job track true
  completion instead of relying on the timeout.

**dp_113 `current_work_data` — the counters answer what dp_107 cannot: is this a
new job or a resumed one.** The session counters (`clean_area`, `work_duration`)
do **not** reset when a job ends. Measured on a V1000 fw28: a mow finished at
11:10 with 177.0 m², and the device was still reporting 177.0 m² nine hours
later and through the night, unchanged, while docked. They restart at zero only
when the device actually begins a new job — visible as a vertical drop in the
history graph at the moment mowing starts (issue [#214] comment
[5293811298](https://github.com/it-rec/TerraMowHA/issues/214#issuecomment-5293811298),
where the reporter spotted it first).

That makes the counters the reliable cycle boundary, and it matters because
`MISSION_STATE_COMPLETE` is not one: the firmware sends the completion flag when
it docks at dusk with the lawn unfinished — observed at **85.8 % progress**,
minutes before sunset — and then resumes the same job the next morning. It also
sometimes omits the flag when a job really did end.

- *Consequence:* the cycle-level mowed coverage is cleared on a counter restart,
  not on the completion flag. Trusting the flag broke both ways on the same lawn
  within ten days — a resumed job lost the previous day's coverage, a genuinely
  new job inherited the previous one's (issue [#214]).
- *To watch for:* whether any firmware zeroes the counters at job end after all.
  That would make the drop ambiguous again, and the boundary would need a second
  signal.

**dp_108 `battery_status` — the pack is never run down, so the 20→80 charge
window never opens.** Over 65 days on a V1000 the lowest *daily minimum* was
33 %, and the typical minimum was 50 %: the firmware sends the mower home long
before the battery is low. The integration's battery-health aggregator only
records a charge sample when a charge starts at ≤ 20 % and reaches ≥ 80 %, so on
this usage pattern `charge_samples` stays `0` and `charge_20_80_minutes` /
`charge_percent_per_hour` stay `null` in every diagnostics download, next to 41
partial discharges and a *high* confidence rating.

- *Consequence:* this is expected, not a fault — worth knowing before someone
  reads a dump and goes looking for a broken charge detector. Discharge-side
  metrics (area and minutes per 10 %, efficiency trend) are unaffected and do
  populate.
- *To watch for:* if charge figures are wanted in practice, the window has to
  come down to what mowers actually do, e.g. any sufficiently large uninterrupted
  rise rather than a fixed 20→80 span.

**Recharge-return, manual job end and the missing `MISSION_STATE_COMPLETE`
(dp_107 / dp_113).** Live capture of a full interrupted job (V1000 fw28,
2026-07-21): when the battery ran low mid-job the mower reported
`mission = MISSION_RECHARGE` while returning, then docked into the usual
`MISSION_IDLE` (see the finding above) — the job stayed open device-side (the
app still offered *End*). After a full charge the mower did **not** resume the
remaining zone, and when the user ended the job in the app ("Clear auto-mode
progress?" → *Clear*), the device **zeroed the dp_113 session counters** —
without ever emitting `MISSION_STATE_COMPLETE`. The dp_104 ack (see table
above) fired at exactly that moment.

- *Consequence:* the session sensors detect "job over" from the dp_113
  counter reset (issues [#204]/[#207]): a job that ends this way counts as
  *aborted* — counters reset, **no** 100 % snap. `MISSION_STATE_COMPLETE`
  (and the 100 % snap) has so far only been observed for jobs the firmware
  itself finishes.
- *Reality check:* during this capture the **vendor app displayed 100 % and
  all zones green although one zone was never mowed** (dp_113 stood at 86 %,
  session area confirmed the gap). The data points are the honest source —
  when the app and the integration disagree, trust the data points.

**dp_107 `has_error` and dp_116 `error_list` are independent fault signals.**
A user reported a fault visible in the app ("mower could not find the home
station") that populated the dp_116 **error list** while dp_107 `has_error`
stayed `false`, so the mower's **Problem** binary sensor read *off* even though
the **Active errors** sensor showed the error (issue [#171]). The reference
device (S1200 fw `9.9.210`) always reports an empty `error_list`, which is why
this went unnoticed. The `error_list` clears when the fault resolves.

- *Consequence:* fault surfacing reads **both** signals — `has_active_error` is
  `has_error` OR a non-empty `error_list` — so the **Problem** binary sensor, the
  lawn-mower **error** activity and the **error** event all fire for either. The
  dp_116 error codes are surfaced as the Problem sensor's `error_codes`
  attribute. dp_116 does not flow through `on_mission_status`, so its handler
  notifies the mower / event listeners directly to surface the fault live.
- *Entry structure confirmed* (S1200 fw `9.9.210`, live captures in issue
  [#171]): `{"error_list": [{"code": int, "time": "<RFC3339>"}]}` — the same
  shape as the dp_123 event log. Each fault also fires dp_115 with the bare
  code (see the table above).
- *Known codes* (community-sourced, catalog in `error_codes.py`): `201` mower
  lifted, `903` and `909` mower stuck (two distinct stuck-type codes). The codes surface with
  readable text on the **Active errors** sensor (`errors[].text`), the
  **Problem** binary sensor (`error_descriptions`), the **error** event, and —
  as the entity state itself — the **Fault** sensor, which reads the joined
  descriptions (`"Mower stuck"`), or `OK` when there is no fault. The map card
  pins the same text where the fault was reported. Unknown codes fall back to
  `Error <code>` — every new capture in [#171] grows the catalog.

[#142]: https://github.com/it-rec/TerraMowHA/issues/142
[#171]: https://github.com/it-rec/TerraMowHA/issues/171
[#199]: https://github.com/it-rec/TerraMowHA/issues/199
[#204]: https://github.com/it-rec/TerraMowHA/issues/204
[#207]: https://github.com/it-rec/TerraMowHA/issues/207
[#214]: https://github.com/it-rec/TerraMowHA/issues/214
