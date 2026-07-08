# Dashboard example

A ready-to-paste Lovelace view for the TerraMow integration: live map,
mowing controls, job progress and the most useful diagnostics.

Replace `terramow` in the entity ids below if your entities use a
different prefix (check one of your TerraMow entities under Settings →
Devices & Services → TerraMow).

```yaml
type: sections
max_columns: 2
title: Lawn
sections:
  - type: grid
    cards:
      - type: picture-entity
        entity: camera.terramow_map
        show_state: false
        show_name: false
        camera_view: auto
        tap_action:
          action: more-info
  - type: grid
    cards:
      - type: entities
        title: Mower
        entities:
          - entity: lawn_mower.terramow
          - entity: select.terramow_zone_select
          - entity: button.terramow_edge_trim
      - type: gauge
        entity: sensor.terramow_current_session_progress
        name: Progress
        min: 0
        max: 100
        severity:
          green: 66
          yellow: 33
          red: 0
      - type: glance
        title: Status
        entities:
          - entity: sensor.terramow_battery
          - entity: sensor.terramow_current_session_area
          - entity: sensor.terramow_current_session_duration
          - entity: binary_sensor.terramow_rain_detected
      - type: entities
        title: Settings
        entities:
          - entity: number.terramow_mowing_height
          - entity: select.terramow_mow_speed
          - entity: select.terramow_blade_speed
          - entity: switch.terramow_thorough_corner_cutting
```

## Useful automations

Notify when the mower runs into a problem:

```yaml
automation:
  - alias: "TerraMow: problem notification"
    triggers:
      - trigger: state
        entity_id: binary_sensor.terramow_problem
        to: "on"
    actions:
      - action: notify.notify
        data:
          title: "TerraMow needs help"
          message: >
            The mower reports a problem
            (mission: {{ states('sensor.terramow_mission') }}).

  - alias: "TerraMow: returned because of rain"
    triggers:
      - trigger: state
        entity_id: binary_sensor.terramow_rain_detected
        to: "on"
    actions:
      - action: notify.notify
        data:
          message: "TerraMow returned to the station — rain detected."
```

Start zone mowing from a script (service call):

```yaml
script:
  mow_front_lawn:
    sequence:
      - action: terramow.start_select_region
        target:
          entity_id: lawn_mower.terramow
        data:
          region_ids: [1]
```

The exact entity ids on your installation may differ — Home Assistant
derives them from the device name and can be checked (or renamed) in the
entity settings.

## Map camera options

Settings → Devices & Services → TerraMow → **Configure** exposes options that
control how the map camera renders:

- **Map output resolution** — output side length of the PNG. Higher values look
  sharper on large dashboards but cost more bandwidth and CPU per render.
- **Map theme** — `light` (default) or `dark`. Pick `dark` to blend the map
  into dark dashboards.
- **Show mowed coverage** — shades the already-mowed area at the real cutting
  width underneath the path line, so it is easy to see which parts of the lawn
  still need work.

The map geometry is rendered supersampled and downsampled, so polygon and path
edges are anti-aliased, and the robot and station icons are drawn true to scale
(clamped so they stay legible on very large or very small lawns).

### Interactive map cards

The map camera publishes a `calibration_points` attribute (three
device-coordinate ↔ image-pixel reference points, expressed in the configured
output resolution). This is the calibration format used by the community
[Lovelace vacuum map cards], so a card configured with
`calibration_source: camera` can overlay clickable zones on
`camera.terramow_map` and drive `terramow.start_select_region` by tapping the
map. The pixel coordinates track the selected output resolution automatically.

[Lovelace vacuum map cards]: https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card
