# TerraMow for Home Assistant

<div align="center">
  <p>
    <a href="#english-version"><img src="https://img.shields.io/badge/English-blue?style=for-the-badge" alt="English"/></a>
    <a href="docs/README_zh.md"><img src="https://img.shields.io/badge/中文-red?style=for-the-badge" alt="中文"/></a>
  </p>
  <p>
    <a href="https://github.com/TerraMow/TerraMowHA/actions/workflows/validate.yml"><img src="https://github.com/TerraMow/TerraMowHA/actions/workflows/validate.yml/badge.svg" alt="Validate"/></a>
    <a href="https://github.com/TerraMow/TerraMowHA/actions/workflows/release.yml"><img src="https://github.com/TerraMow/TerraMowHA/actions/workflows/release.yml/badge.svg" alt="Release"/></a>
  </p>
  <img src="docs/images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

---

<a id="english-version"></a>

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
- Firmware update entity and version compatibility sensor

**Integration quality of life**
- Zeroconf/mDNS auto-discovery
- Reconfigure flow (change host/IP without re-adding) and reauth flow
- Diagnostics download for easy bug reports
- Translated into 14 languages (en, cs, da, de, es, fi, fr, it, nb, nl, pl, pt, sv, zh-Hans)
- MQTT based local push communication — no cloud required

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

The following parameters are required:
- **Host**: IP address or hostname of the TerraMow device
- **Password**: MQTT password for authentication

### Requirements

- Home Assistant 2023.9.3 or later (tested with 2025.1.1)
- TerraMow firmware version 6.6.0 or later
- TerraMow APP version 1.6.0 or later

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

### Support

Open an issue on [GitHub](https://github.com/TerraMow/TerraMowHA/issues) for support.

### Developer Information

For developers interested in understanding or extending this integration, please refer to the [Developer Guide](docs/en/developers.md).

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.