"""Coverage mop-up for the smaller modules.

Platform async_setup_entry, the firmware update entity, the map sensors, the
lawn-mower activity mapping, the map/task binary sensors, the push-update
mixin helpers, diagnostics and the issues reason parser.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.components.lawn_mower import LawnMowerActivity
from homeassistant.const import CONF_HOST, CONF_PASSWORD

from custom_components.terramow import DOMAIN, TerraMowBasicData
from custom_components.terramow.binary_sensor import (
    FirmwareUpgradingSensor,
    NavigationLocatedSensor,
    PowerSwitchSensor,
    TerraMowChargingSensor,
    TerraMowMapBuildableBinarySensor,
    TerraMowMapDetectedBinarySensor,
    TerraMowProblemSensor,
    TerraMowRainSensor,
    TerraMowSavingDataBinarySensor,
    async_setup_entry as binary_setup,
)
from custom_components.terramow.switch import ThoroughCornerCuttingSwitch
from custom_components.terramow.button import async_setup_entry as button_setup
from custom_components.terramow.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.issues import _reason_version
from custom_components.terramow.lawn_mower import (
    TerraMowLawnMowerEntity,
    async_setup_entry as lawn_mower_setup,
)
from custom_components.terramow.map_sensor import (
    TerraMowMapStatusSensor,
    async_setup_entry as map_setup,
)
from custom_components.terramow.switch import async_setup_entry as switch_setup
from custom_components.terramow.update import (
    TerraMowFirmwareUpdate,
    async_setup_entry as update_setup,
)


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.110", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


def _run_setup(setup, hub) -> list:
    added: list = []
    entry = SimpleNamespace(entry_id="e1", runtime_data=hub.basic_data)
    asyncio.run(setup(hub.hass, entry, added.extend))
    return added


# ---------------------------------------------------------------------------
# platform setups
# ---------------------------------------------------------------------------


def test_platform_setups_create_entities() -> None:
    assert len(_run_setup(binary_setup, _hub())) == 25
    assert len(_run_setup(button_setup, _hub())) == 3
    assert len(_run_setup(switch_setup, _hub())) == 1
    assert len(_run_setup(update_setup, _hub())) == 1
    assert len(_run_setup(map_setup, _hub())) == 3
    assert len(_run_setup(lawn_mower_setup, _hub())) == 1


# ---------------------------------------------------------------------------
# firmware update entity
# ---------------------------------------------------------------------------


def test_firmware_update_versions() -> None:
    hub = _hub()
    update = TerraMowFirmwareUpdate(hub.basic_data, hub.hass)
    assert update.installed_version is None  # no info yet

    _feed(hub.on_compatibility_info, {"overall": 26, "module": {"home_assistant": 3}})
    assert update.installed_version == "26.3"
    assert update.latest_version == update.installed_version

    # overall-only firmware (no module.home_assistant) reports the bare version
    _feed(hub.on_compatibility_info, {"overall": 30})
    assert update.installed_version == "30"

    # no lawn_mower -> None
    hub.basic_data.lawn_mower = None
    assert update.installed_version is None


def test_firmware_update_push_callback() -> None:
    hub = _hub()
    update = TerraMowFirmwareUpdate(hub.basic_data, hub.hass)
    update.entity_id = "update.fw"
    update.async_write_ha_state = MagicMock()
    asyncio.run(update._handle_compat_info(""))


# ---------------------------------------------------------------------------
# map sensor None / attributes
# ---------------------------------------------------------------------------


def test_map_status_sensor_none_and_attributes() -> None:
    hub = _hub()
    sensor = TerraMowMapStatusSensor(hub.basic_data, hub.hass)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}

    _feed(hub.on_map_status, {
        "map_state": "MAP_STATE_COMPLETE",
        "is_map_detected": True,
        "map_id": 4,
        "map_number": 2,
    })
    assert sensor.native_value == "map_state_complete"
    attrs = sensor.extra_state_attributes
    assert attrs["map_id"] == 4
    assert attrs["map_number"] == 2


# ---------------------------------------------------------------------------
# lawn mower activity mapping
# ---------------------------------------------------------------------------


def _lawn_mower(hub) -> TerraMowLawnMowerEntity:
    entity = TerraMowLawnMowerEntity(hub.basic_data, hub.hass)
    return entity


def test_lawn_mower_activity_states() -> None:
    hub = _hub()
    entity = _lawn_mower(hub)

    # running a mow mission -> MOWING
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN", "state": "MISSION_STATE_RUNNING",
    })
    entity.update_activity_from_state()
    assert entity.activity == LawnMowerActivity.MOWING

    # station-wait sub-mission -> PAUSED
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN",
        "sub_mission": "SUB_MISSION_FLEXIBLE_STATION_WAIT",
        "state": "MISSION_STATE_RUNNING",
    })
    entity.update_activity_from_state()
    assert entity.activity == LawnMowerActivity.PAUSED

    # recharge mission -> RETURNING (RETURNING exists on this HA)
    _feed(hub.on_mission_status, {
        "mission": "MISSION_RECHARGE", "state": "MISSION_STATE_RUNNING",
    })
    entity.update_activity_from_state()
    assert entity.activity in (LawnMowerActivity.RETURNING, LawnMowerActivity.DOCKED)

    # paused mission -> PAUSED
    _feed(hub.on_mission_status, {
        "mission": "MISSION_IDLE", "state": "MISSION_STATE_PAUSE",
    })
    entity.update_activity_from_state()
    assert entity.activity == LawnMowerActivity.PAUSED

    # connection error -> ERROR
    hub.connection_error = True
    entity.update_activity_from_state()
    assert entity.activity == LawnMowerActivity.ERROR


def test_lawn_mower_saving_map_and_docked_branches() -> None:
    hub = _hub()
    entity = _lawn_mower(hub)

    # saving the map while running -> treated as DOCKED
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN",
        "sub_mission": "SUB_MISSION_SAVING_MAP",
        "state": "MISSION_STATE_RUNNING",
    })
    entity.update_activity_from_state()
    assert entity.activity == LawnMowerActivity.DOCKED

    # a running mission that is neither mow nor recharge -> DOCKED
    _feed(hub.on_mission_status, {"mission": "MISSION_IDLE", "state": "MISSION_STATE_RUNNING"})
    entity.update_activity_from_state()
    assert entity.activity == LawnMowerActivity.DOCKED

    # idle -> DOCKED
    _feed(hub.on_mission_status, {"mission": "MISSION_IDLE", "state": "MISSION_STATE_IDLE"})
    entity.update_activity_from_state()
    assert entity.activity == LawnMowerActivity.DOCKED


def test_lawn_mower_commands_delegate_to_hub() -> None:
    hub = _hub()
    hub._last_control_time = 0.0
    entity = _lawn_mower(hub)
    entity.start_mowing()
    assert hub.mqtt_client.publish.called
    assert entity.available is True


# ---------------------------------------------------------------------------
# map / task binary sensors + push mixin helpers
# ---------------------------------------------------------------------------


def test_map_and_task_binary_sensors() -> None:
    hub = _hub()
    detected = TerraMowMapDetectedBinarySensor(hub.basic_data, hub.hass)
    saving = TerraMowSavingDataBinarySensor(hub.basic_data, hub.hass)
    assert detected.is_on is None  # no map_status yet

    _feed(hub.on_map_status, {"is_map_detected": True})
    assert detected.is_on is True

    _feed(hub.on_mission_status, {"is_saving_data": True})
    assert saving.is_on is True


def test_push_update_mixin_handlers() -> None:
    hub = _hub()
    sensor = TerraMowChargingSensor(hub.basic_data, hub.hass)
    sensor.entity_id = "binary_sensor.charging"
    sensor.async_write_ha_state = MagicMock()
    asyncio.run(sensor._handle_push_update(""))
    asyncio.run(sensor._handle_map_push_update({}))
    assert sensor.async_write_ha_state.call_count == 2


def test_binary_sensors_none_without_data() -> None:
    hub = _hub()
    for cls in (
        TerraMowChargingSensor,
        NavigationLocatedSensor,
        FirmwareUpgradingSensor,
        PowerSwitchSensor,
        TerraMowMapBuildableBinarySensor,
    ):
        assert cls(hub.basic_data, hub.hass).is_on is None
    # problem/rain default to a concrete False rather than None
    assert TerraMowProblemSensor(hub.basic_data, hub.hass).is_on is False
    assert TerraMowRainSensor(hub.basic_data, hub.hass).is_on is False


def test_binary_sensors_none_without_lawn_mower() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    for cls in (
        TerraMowChargingSensor,
        NavigationLocatedSensor,
        FirmwareUpgradingSensor,
        PowerSwitchSensor,
        TerraMowProblemSensor,
        TerraMowRainSensor,
        TerraMowMapDetectedBinarySensor,
        TerraMowSavingDataBinarySensor,
    ):
        assert cls(hub.basic_data, hub.hass).is_on is None


def test_map_task_binary_sensor_missing_fields() -> None:
    hub = _hub()
    # map_status present but the specific flag is absent -> None
    _feed(hub.on_map_status, {"map_id": 1})
    assert TerraMowMapDetectedBinarySensor(hub.basic_data, hub.hass).is_on is None
    _feed(hub.on_mission_status, {"mission": "MISSION_IDLE"})
    assert TerraMowSavingDataBinarySensor(hub.basic_data, hub.hass).is_on is None


def test_binary_sensors_reflect_device_flags() -> None:
    hub = _hub()
    _feed(hub.on_battery_status, {"charger_connected": True, "is_switch_on": True})
    assert TerraMowChargingSensor(hub.basic_data, hub.hass).is_on is True
    assert PowerSwitchSensor(hub.basic_data, hub.hass).is_on is True

    _feed(hub.on_mission_status, {
        "is_robot_navi_located": True,
        "is_upgrading": True,
        "has_error": True,
        "back_to_station_reason": "BACK_TO_STATION_REASON_RAINING",
    })
    assert NavigationLocatedSensor(hub.basic_data, hub.hass).is_on is True
    assert FirmwareUpgradingSensor(hub.basic_data, hub.hass).is_on is True
    assert TerraMowProblemSensor(hub.basic_data, hub.hass).is_on is True
    assert TerraMowRainSensor(hub.basic_data, hub.hass).is_on is True


# ---------------------------------------------------------------------------
# thorough corner cutting switch None branches
# ---------------------------------------------------------------------------


def test_corner_switch_none_and_missing_lawn_mower() -> None:
    hub = _hub()
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)
    assert switch.is_on is None  # no map_info / mow_param

    hub.basic_data.lawn_mower = None
    asyncio.run(switch.async_turn_on())  # bails without a lawn_mower
    assert switch.is_on is None


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------


def test_diagnostics_without_lawn_mower() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    hass = hub.hass
    entry = SimpleNamespace(
        entry_id="e1",
        data={CONF_HOST: "192.0.2.1", CONF_PASSWORD: "secret"},
        options={},
        runtime_data=hub.basic_data,
    )
    diag = asyncio.run(async_get_config_entry_diagnostics(hass, entry))
    assert diag["device"] is None
    # host/password are redacted
    assert diag["entry"]["data"][CONF_HOST] != "192.0.2.1"


def test_diagnostics_missing_integration_data() -> None:
    hub = _hub()
    hass = hub.hass
    entry = SimpleNamespace(entry_id="missing", data={}, options={}, runtime_data=None)
    diag = asyncio.run(async_get_config_entry_diagnostics(hass, entry))
    assert diag["error"] == "integration data not loaded"


# ---------------------------------------------------------------------------
# issues reason parser
# ---------------------------------------------------------------------------


def test_reason_version_parser() -> None:
    assert _reason_version("ha_version_low:1.2.3") == "1.2.3"
    assert _reason_version("no-colon-here") == "unknown"


# ---------------------------------------------------------------------------
# entity-disabled-by-default (Gold quality scale)
# ---------------------------------------------------------------------------


def test_high_frequency_entities_are_disabled_by_default() -> None:
    import sys

    sys.modules.setdefault("turbojpeg", MagicMock())
    from custom_components.terramow.camera import TerraMowMapCamera
    from custom_components.terramow.sensor import TerraMowPoseSensor

    hub = _hub()
    # the 2 Hz pose sensor is opt-in
    assert TerraMowPoseSensor(hub.basic_data, hub.hass).entity_registry_enabled_default is False
    # the clean-mode camera is opt-in, the main map camera stays enabled
    assert TerraMowMapCamera(hub.basic_data, hub.hass, clean_mode=True).entity_registry_enabled_default is False
    assert TerraMowMapCamera(hub.basic_data, hub.hass).entity_registry_enabled_default is True
