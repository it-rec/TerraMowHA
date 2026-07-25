"""Every translation key referenced in code must exist in strings.json.

Two complementary sweeps keep this maintainable and hard to dodge:

1. A source scan: every string literal on a ``translation_key`` line of every
   integration module must exist under the platform section that module
   implements (``entity.<platform>.<key>``), or under ``exceptions`` /
   ``issues`` for hub/init/issues code. A module not in the map that starts
   using translation keys fails loudly so the map stays complete.
2. A structural check through the real description tables and entity classes:
   the SENSORS/BINARY_SENSORS tables and the select/sensor enum options must
   resolve, including their per-state translations (the lowercase tokens the
   entities actually publish).
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.terramow.binary_sensor import BINARY_SENSORS
from custom_components.terramow.const import MOW_SPEED_TYPES, to_ha_enum_state
from custom_components.terramow.issues import (
    BASE_STATION_MAINTENANCE_ISSUE,
    BLADE_MAINTENANCE_ISSUE,
)
from custom_components.terramow.select import (
    BladeSpeedSelect,
    HighGrassEdgeTrimModeSelect,
    MainDirectionModeSelect,
)
from custom_components.terramow.sensor import SENSORS, TerraMowMowSpeedSensor

COMPONENT_DIR = Path(__file__).parents[1] / "custom_components" / "terramow"

# Which strings.json entity platform section each module's translation keys
# live in. Modules missing here must not use translation keys at all.
PLATFORM_FOR_MODULE = {
    "sensor.py": "sensor",
    "map_sensor.py": "sensor",
    "binary_sensor.py": "binary_sensor",
    "select.py": "select",
    "number.py": "number",
    "switch.py": "switch",
    "light.py": "light",
    "button.py": "button",
    "update.py": "update",
    "event.py": "event",
    "camera.py": "camera",
    "lawn_mower.py": "lawn_mower",
    "calendar.py": "calendar",
    "todo.py": "todo",
}

# Modules whose translation keys refer to HomeAssistantError exceptions.
EXCEPTION_MODULES = {"hub.py", "__init__.py"}

# Modules whose translation keys refer to repair issues.
ISSUE_MODULES = {"issues.py"}

_LITERAL = re.compile(r'"([a-z0-9_]+)"')


@cache
def _strings() -> dict[str, Any]:
    """Load strings.json once for the whole module."""
    return json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))


def _keys_in_module(module: Path) -> set[str]:
    """Collect every string literal on a (non-comment) translation_key line."""
    keys: set[str] = set()
    for line in module.read_text(encoding="utf-8").splitlines():
        if "translation_key" not in line or line.lstrip().startswith("#"):
            continue
        keys.update(_LITERAL.findall(line))
    return keys


def _entity_section(platform: str) -> dict[str, Any]:
    section = _strings()["entity"].get(platform)
    assert isinstance(section, dict), f"strings.json has no entity.{platform} section"
    return section


# ---------------------------------------------------------------------------
# source scan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module_name", "platform"), sorted(PLATFORM_FOR_MODULE.items())
)
def test_entity_translation_keys_exist(module_name: str, platform: str) -> None:
    keys = _keys_in_module(COMPONENT_DIR / module_name)
    assert keys, f"{module_name} unexpectedly defines no translation keys"
    section = _entity_section(platform)
    for key in sorted(keys):
        assert key in section, (
            f"{module_name} uses translation_key '{key}' but strings.json has no "
            f"entity.{platform}.{key}"
        )


@pytest.mark.parametrize("module_name", sorted(EXCEPTION_MODULES))
def test_exception_translation_keys_exist(module_name: str) -> None:
    keys = _keys_in_module(COMPONENT_DIR / module_name)
    assert keys, f"{module_name} unexpectedly defines no translation keys"
    exceptions = _strings()["exceptions"]
    for key in sorted(keys):
        assert key in exceptions, (
            f"{module_name} raises with translation_key '{key}' but strings.json "
            f"has no exceptions.{key}"
        )
        assert exceptions[key].get("message"), f"exceptions.{key} has no message"


def test_issue_translation_keys_exist() -> None:
    issues = _strings()["issues"]
    for module_name in sorted(ISSUE_MODULES):
        for key in sorted(_keys_in_module(COMPONENT_DIR / module_name)):
            assert key in issues, (
                f"{module_name} creates an issue with translation_key '{key}' but "
                f"strings.json has no issues.{key}"
            )
    # The maintenance issue kinds are passed as ``translation_key=kind``
    # variables, invisible to the literal scan; pin them explicitly.
    assert BLADE_MAINTENANCE_ISSUE in issues
    assert BASE_STATION_MAINTENANCE_ISSUE in issues


def test_no_translation_keys_outside_mapped_modules() -> None:
    """A new module using translation keys must be added to the maps above."""
    mapped = set(PLATFORM_FOR_MODULE) | EXCEPTION_MODULES | ISSUE_MODULES
    for module in sorted(COMPONENT_DIR.glob("*.py")):
        if module.name in mapped:
            continue
        keys = _keys_in_module(module)
        assert not keys, (
            f"{module.name} uses translation keys {sorted(keys)} but is not "
            "mapped to a strings.json section in test_translation_keys.py"
        )


def test_command_rate_limited_exception_key_exists() -> None:
    """The rate-limit error raised by every command path must be translatable."""
    assert "command_rate_limited" in _strings()["exceptions"]
    assert "command_not_delivered" in _strings()["exceptions"]


# ---------------------------------------------------------------------------
# structural checks through the real tables / classes
# ---------------------------------------------------------------------------


def test_sensor_table_keys_and_enum_options_are_translated() -> None:
    section = _entity_section("sensor")
    for description in SENSORS:
        key = description.translation_key
        assert key in section, f"entity.sensor.{key} missing for SENSORS['{key}']"
        if description.options:
            states = section[key].get("state", {})
            for option in description.options:
                assert option == option.lower(), (
                    f"SENSORS['{key}'] option '{option}' is not a lowercase token"
                )
                assert option in states, (
                    f"entity.sensor.{key}.state.{option} missing"
                )


def test_binary_sensor_table_keys_are_translated() -> None:
    section = _entity_section("binary_sensor")
    for description in BINARY_SENSORS:
        key = description.translation_key
        assert key in section, (
            f"entity.binary_sensor.{key} missing for BINARY_SENSORS['{key}']"
        )


@pytest.mark.parametrize(
    ("select_cls", "key"),
    [
        (BladeSpeedSelect, "blade_speed"),
        (MainDirectionModeSelect, "main_direction_mode"),
        (HighGrassEdgeTrimModeSelect, "high_grass_edge_trim_mode"),
    ],
)
def test_static_select_options_are_translated(select_cls: type, key: str) -> None:
    """Each select's published (lowercase) option has a state translation."""
    # _attr_* class attributes are wrapped by HA's CachedProperties
    # metaclass; instantiate to read the actual values.
    entity = select_cls(MagicMock(), MagicMock())
    assert entity._attr_translation_key == key
    states = _entity_section("select")[key].get("state", {})
    device_options = entity._attr_options
    assert device_options, f"{select_cls.__name__} has no static options"
    for device_enum in device_options:
        option = to_ha_enum_state(device_enum)
        assert option == option.lower()
        assert option in states, f"entity.select.{key}.state.{option} missing"


def test_mow_speed_options_are_translated() -> None:
    """Both the select and the sensor expose the mow-speed tokens."""
    select_states = _entity_section("select")["mow_speed_setting"].get("state", {})
    sensor_states = _entity_section("sensor")["mow_speed"].get("state", {})
    sensor = TerraMowMowSpeedSensor(MagicMock(), MagicMock())
    assert sensor._attr_options == [to_ha_enum_state(t) for t in MOW_SPEED_TYPES]
    for speed_type in MOW_SPEED_TYPES:
        option = to_ha_enum_state(speed_type)
        assert option in select_states
        assert option in sensor_states
    # The zone select's two special (non-dynamic) options are translated too.
    zone_states = _entity_section("select")["region_select"].get("state", {})
    assert "no_zones_available" in zone_states
    assert "all_zones" in zone_states


def test_service_translations_exist() -> None:
    from custom_components.terramow import ATTR_REGION_IDS, SERVICE_START_SELECT_REGION

    services = _strings()["services"]
    assert SERVICE_START_SELECT_REGION in services
    service = services[SERVICE_START_SELECT_REGION]
    assert service.get("name") and service.get("description")
    assert ATTR_REGION_IDS in service.get("fields", {})
