# Draft: upstream feature request — local schedule writes (dp_122)

Ready-to-post issue text for the vendor's repo
([TerraMow/TerraMowHA](https://github.com/TerraMow/TerraMowHA/issues)).
Evidence gathered on a **V1000**, firmware overall **28**
(`schedule` module 5, `home_assistant` module 3), integration
`it-rec/TerraMowHA` v1.18.x.

---

**Title:** Feature request: accept schedule writes (dp_122) over the local
MQTT `home_assistant` channel

**Body:**

Hi! Thanks for the excellent local `home_assistant` MQTT interface — we've
built an editable-calendar feature on top of it and hit a firmware limit we
hope you can lift (or document the intended way).

**What works today**

- `data_point/122/app` with `{"cmd_type": "SCHEDULE_CMD_TYPE_GET", "seq": N}`
  is answered with the full `schedule_list` — read access is perfect.

**What doesn't**

Every write attempt on the same channel is silently dropped (no dp_119 ack,
no schedule change, no error). Tried on V1000 fw overall 28:

- `cmd_type` names: `SCHEDULE_CMD_TYPE_ADD` / `SET` / `UPDATE` / `SAVE`
- `cmd_type` as protobuf-JSON enum *numbers* 1–6
- payload shapes: item fields inline; `schedule_list.items` full-replace
  (mirroring the GET response exactly, including `id: 0` for new items);
  `item` / `schedule_item` / `schedule` wrappers

We also observed that dp_119 acks are only published for the internal
(BLE/cloud) commander (epoch-style `seq` values), never for external MQTT
clients, and that the official app writes schedules via BLE/cloud only —
so there is no way to learn the intended format from traffic.

**Request**

1. If a local write format already exists: document the dp_122 write message
   (cmd enum values + payload schema) in `docs/en/developers/data_point.md`.
2. If not: please consider adding schedule write support (and dp_119 acks
   for external clients) to the next `home_assistant` module version. The
   read schema (`SCHEDULE_TYPE_GLOBAL_V2` / `global_schedule_v2.basic_config`)
   would be a natural request schema too.

This would enable Home-Assistant-side calendar editing and weather-adaptive
scheduling for all HA users. Happy to test beta firmware and share our
negotiation logs. 🌱
