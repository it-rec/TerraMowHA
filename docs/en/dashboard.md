# Dashboard example

A ready-to-paste Lovelace view for the TerraMow integration: live map,
mowing controls, job progress and the most useful diagnostics.

Replace `terramow` in the entity ids below if your entities use a
different prefix (check one of your TerraMow entities under Settings →
Devices & Services → TerraMow).

## Interactive map card

The integration ships a custom Lovelace card and registers it
automatically — no manual resource, no separate HACS frontend install.
It appears in the card picker as **TerraMow Map Card** (with a UI
editor), or add it in YAML:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Unlike the PNG camera, the card renders the map as vectors over a live
WebSocket feed: crisp at any zoom level, themed with your dashboard, and
the robot marker moves without image reloads.

**Interactions**

- **Drag** to pan, **scroll / pinch** to zoom, **double-tap** (or the ⛶
  button) to fit the whole lawn again.
- **Tap a zone** to select it (tap again to deselect); an action bar
  appears with the zone names and total area — press it to start mowing
  exactly the selected zones via `terramow.start_select_region`. Zones
  the device itself reports as selected for the running job are tinted
  in the accent color.
- **Tap the robot marker** to open the mower's more-info dialog.
- **Contextual controls** (bottom right) offer exactly the actions that
  make sense for the current state: start when docked or paused, pause
  while mowing or returning, dock while working.
- The **follow button** (crosshair, top right) keeps the view centered
  on the mower while it works; panning or zooming releases it. The
  marker is tinted by activity (mowing green, returning blue, paused
  orange, error red) and pulses gently while mowing.

**Options**

| Option | Default | Description |
| --- | --- | --- |
| `entity` | *required* | Any TerraMow entity; the lawn mower entity is the natural choice |
| `show_controls` | `true` | Contextual start / pause / dock buttons on the card |
| `zone_selection` | `true` | Tap zones to start a selective mow |
| `show_coverage` | `false` | Shade the mowed swath at the true cutting width |
| `show_current_path` | `true` | Draw the running job's mowing path |
| `show_history_path` | `true` | Draw the previous job's path (faded) |
| `show_hud` | `true` | Status chips (state, battery, job progress, map) |
| `rotation` | `0` | Rotate the map view (degrees) |
| `fit_height` | `420` | Card canvas height in pixels |
| `fit_padding` | `0.95` | Fraction of the card the lawn fills on fit-to-view (`0.5`–`1.0`); higher zooms in tighter |

Fit-to-view frames the lawn itself — the drawn zones, no-go areas and
station — not the wider scanned area, so a small lawn on a large map fills
the card instead of sitting in empty space. Raise `fit_padding` toward `1`
for an even tighter zoom, or lower it for more margin.

The card is wall-tablet friendly: static geometry is cached between
frames, path updates stream as point deltas, and the live feed pauses
automatically while the tab is hidden.

**Notes**

- Live map data requires firmware HA module version 3 (same requirement
  as the map camera); on older firmware the card shows a placeholder.
- The card follows the active Home Assistant theme (light and dark).
- Headless / custom setups (or YAML resource mode, which the integration
  cannot write to) can still use the card by adding
  `/terramow-frontend/terramow-map-card.js` manually as a dashboard
  resource of type *JavaScript Module* (`module` — the `js` type is
  deprecated and no longer executes on HA 2026.7+).
- Right after the very first install, one hard refresh (Ctrl+Shift+R)
  may be needed so the browser picks up the freshly registered resource.

In the example view below you can swap the `picture-entity` camera card
for the interactive card one-to-one.

## Example view

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

The full (non-clean) map also overlays a **scale bar** with a round metric
distance, a compact **color legend** for the feature types present, and an
**"Updated HH:MM"** timestamp in the summary panel (in Home Assistant's local
time) so a stale image is easy to spot. The timestamp is also exposed as the
`map_updated_at` camera attribute.

The HUD labels (legend, summary panel, chips, placeholder text) follow your
**Home Assistant UI language** — German, French, Spanish, Italian, Dutch,
Portuguese and Chinese (simplified/traditional) are translated, and any other
language falls back to English. The resolved language is exposed as the
`map_language` camera attribute.

### Interactive map cards

The map camera publishes a `calibration_points` attribute (three
device-coordinate ↔ image-pixel reference points, expressed in the configured
output resolution). This is the calibration format used by the community
[Lovelace vacuum map cards], so a card configured with
`calibration_source: camera` can overlay clickable zones on
`camera.terramow_map` and drive `terramow.start_select_region` by tapping the
map. The pixel coordinates track the selected output resolution automatically.

[Lovelace vacuum map cards]: https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card
