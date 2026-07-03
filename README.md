# TerraMow for Home Assistant

<div align="center">
  <p>
    <a href="https://github.com/TerraMow/TerraMowHA/actions/workflows/validate.yml"><img src="https://github.com/TerraMow/TerraMowHA/actions/workflows/validate.yml/badge.svg" alt="Validate"/></a>
    <a href="https://github.com/TerraMow/TerraMowHA/actions/workflows/release.yml"><img src="https://github.com/TerraMow/TerraMowHA/actions/workflows/release.yml/badge.svg" alt="Release"/></a>
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
- Edge trim mowing button
- Settings from Home Assistant: mowing height, speed, spacing, blade speed, edge cutting distance, main direction mode and angles, thorough corner cutting, high-grass edge trim mode
- Maintenance: reset buttons for the blade disk and base station counters

**Monitoring**
- Live map camera with mowing path, robot pose and base station (plus a clean map-only camera for dashboards, resolution configurable via options)
- Battery: level, charging state, temperature state, charger connected, power switch
- Job progress: current session area, progress (%), duration and job type; lifetime mowing time, job count and mowed area
- Status: mission / sub-mission / mission state, operation mode, power mode, back-to-station reason, rain detection, problem indicator, saving-data and data-conversion indicators
- Map: status, area, detected / buildable / backing-up flags
- Schedule: next scheduled start
- Firmware update entity, firmware version on the device page, and version compatibility sensor
- All entities update instantly on device pushes — no polling delay

**Integration quality of life**
- Zeroconf/mDNS auto-discovery
- Reconfigure flow (change host/IP without re-adding) and reauth flow
- Diagnostics download for easy bug reports
- Translated into 14 languages (en, cs, da, de, es, fi, fr, it, nb, nl, pl, pt, sv, zh-Hans)
- MQTT based local push communication — no cloud required

### Supported entities

| Platform | Entities |
| --- | --- |
| Lawn mower | Start / pause / dock control with live activity |
| Camera | Map with path, robot and base station; clean map-only variant |
| Sensor | Battery level, battery state, battery temperature state, map status, map area, mow height, mow speed, operation mode, pose, total mowing time / jobs / mowed area, current session area / progress / duration / job type, remaining blade & base station time, next scheduled start, version compatibility, main direction status, power mode, back-to-station reason, mission, sub-mission, mission state |
| Binary sensor | Charging, navigation located, firmware upgrading, power switch, problem, rain detected, map detected / buildable / backing up, saving data, data conversion in progress |
| Select | Zone select, mow speed, blade speed, main direction mode, high-grass edge trim mode |
| Number | Mowing height, edge cutting distance, mowing spacing, single direction angle, auto-rotate angle interval, first / second direction angle |
| Switch | Thorough corner cutting |
| Button | Edge trim, reset blade timer, reset base station timer |
| Update | Firmware version |

### Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TerraMow&repository=TerraMowHA&category=Integration)

#### Method 1: HACS (Recommended)
1. Make sure [HACS](https://hacs.xyz/) is installed
2. Use the button above to add to HACS
3. Go to HACS → Integrations → + → Search for "TerraMow"
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
- *Options* (Configure): set the map camera output resolution. Higher values give a sharper dashboard image at the cost of bandwidth and CPU per render.
- If the device password changes, Home Assistant automatically starts a *reauthentication* flow.

### Requirements

- Home Assistant 2023.9.3 or later (tested with 2025.1.1)
- TerraMow firmware version 6.6.0 or later
- TerraMow APP version 1.6.0 or later
- Live map and mowing path require firmware HA module version 3; on version 2 (e.g. S800) everything else works and the version compatibility sensor reports it

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

### Diagnostics & troubleshooting

- **Diagnostics download**: Settings → Devices & Services → TerraMow → three-dot menu → *Download diagnostics* produces a redacted JSON snapshot (device state, firmware compatibility, raw data point caches) — please attach it to bug reports.
- **Discovering unsupported features**: the mower publishes more data points than are documented. The first payload of every unknown data point is logged once at INFO level; enable debug logging for the `terramow` integration to record all of them. If you find a data point for a missing feature (e.g. lift alarm, schedule switch, error codes), please share it in an issue.

### Languages

The integration is translated into: Čeština, Dansk, Deutsch, English, Español, Français, Italiano, Nederlands, Norsk (bokmål), Polski, Português, Suomi, Svenska and 简体中文.

### Upgrade notes

- **v0.5.0**: entity state values changed from uppercase to lowercase (e.g. `MISSION_IDLE` → `mission_idle`) to comply with Home Assistant translation requirements. Automations or templates comparing raw state strings need a one-time update; displayed names are unchanged.

### Support

Open an issue on [GitHub](https://github.com/TerraMow/TerraMowHA/issues) for support.

### Developer Information

For developers interested in understanding or extending this integration, please refer to the [Developer Guide](docs/en/developers.md).

To run the test suite locally:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
