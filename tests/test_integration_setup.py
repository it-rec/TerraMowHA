"""Full-stack integration tests: real hass, real config-entry setup.

Unlike most of the suite (unit tests around individual entity classes), these
tests load the config entry through ``hass.config_entries.async_setup`` so
every platform creates real entities whose REAL states are asserted via
``hass.states.get``. This is the class of test that catches wiring bugs the
unit tests cannot — e.g. a select publishing lowercase state tokens while a
number entity compares them against UPPERCASE device enums.

The hub is real; only its MQTT layer is neutralized: ``TerraMowHub.start`` is
replaced by a stub that installs a mock (connected) MQTT client and registers
the hub's own data-point callbacks, without spawning the network thread.
Device pushes are simulated by feeding ``hub.on_mqtt_message`` real MQTT-shaped
messages, exercising the full dispatch path into the entities.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import PLATFORMS, SERVICE_START_SELECT_REGION
from custom_components.terramow.binary_sensor import BINARY_SENSORS
from custom_components.terramow.const import CONF_SERIAL, DOMAIN
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.sensor import SENSORS

HOST = "192.0.2.10"
SERIAL = "MP511TEST42"
# Every entity unique_id shares this historical prefix (see TerraMowEntity).
UID_PREFIX = f"lawn_mower.terramow@{SERIAL}"


def _fake_hub_start(self: TerraMowHub) -> None:
    """Start the hub without network: mock client, real callback wiring."""
    client = MagicMock()
    client.is_connected.return_value = True
    client.publish.return_value = MagicMock(rc=0)
    self.mqtt_client = client
    self.register_all_callbacks()


async def setup_terramow(hass: HomeAssistant) -> MockConfigEntry:
    """Set the integration up for real and return the loaded config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_PASSWORD: "secret", CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.terramow.validate_input",
            return_value={"title": f"TerraMow ({HOST})"},
        ),
        patch.object(TerraMowHub, "start", _fake_hub_start),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def _settle(hass: HomeAssistant) -> None:
    """Wait until dispatched handlers AND their state writes have landed.

    ``async_block_till_done`` only waits for tasks; entities notified via
    ``schedule_update_ha_state`` write state from a ``call_soon_threadsafe``
    callback, which needs one more event-loop iteration to run.
    """
    await hass.async_block_till_done()
    await asyncio.sleep(0)
    await hass.async_block_till_done()


async def push_dp(
    hass: HomeAssistant, hub: TerraMowHub, dp_id: int, payload: dict[str, Any]
) -> None:
    """Deliver a data-point push exactly like the MQTT worker thread would."""
    msg = SimpleNamespace(
        topic=f"data_point/{dp_id}/robot", payload=json.dumps(payload).encode()
    )
    hub.on_mqtt_message(None, None, msg)
    await _settle(hass)


async def push_topic(
    hass: HomeAssistant, hub: TerraMowHub, topic: str, payload: str
) -> None:
    """Deliver a special-topic MQTT message (map info, model name, ...)."""
    msg = SimpleNamespace(topic=topic, payload=payload.encode())
    hub.on_mqtt_message(None, None, msg)
    await _settle(hass)


def resolve_entity_id(
    hass: HomeAssistant, platform: str, unique_suffix: str | None = None
) -> str:
    """Resolve an entity_id from the stable unique_id scheme."""
    unique_id = (
        UID_PREFIX if unique_suffix is None else f"{UID_PREFIX}.{unique_suffix}"
    )
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, f"no {platform} entity with unique_id {unique_id}"
    return entity_id


# ---------------------------------------------------------------------------
# setup / entity creation
# ---------------------------------------------------------------------------


async def test_setup_loads_and_creates_all_platform_entities(
    hass: HomeAssistant,
) -> None:
    entry = await setup_terramow(hass)

    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    per_platform: dict[str, int] = {}
    for reg_entry in entries:
        per_platform[reg_entry.domain] = per_platform.get(reg_entry.domain, 0) + 1

    # Every forwarded platform created at least one entity...
    for platform in PLATFORMS:
        assert per_platform.get(str(platform), 0) > 0, f"no {platform} entities"

    # ...and the exact per-platform counts match the platform modules.
    assert per_platform == {
        "lawn_mower": 1,
        "camera": 2,
        "image": 1,
        "update": 1,
        "button": 3,
        "switch": 1,
        "event": 1,
        "calendar": 1,
        "todo": 1,
        "select": 5,
        "number": 7,
        "binary_sensor": len(BINARY_SENSORS),
        # 9 hand-written sensors (battery, pose, 3 map, mow speed, version
        # compatibility, 2 wear forecasts) + the description table.
        "sensor": 9 + len(SENSORS),
    }

    # The integration-level service is registered while an entry is loaded.
    assert hass.services.has_service(DOMAIN, SERVICE_START_SELECT_REGION)

    # Real states exist for every enabled entity (nothing failed to add);
    # disabled-by-default entities (pose, cellular, ...) have no state.
    for reg_entry in entries:
        if reg_entry.disabled_by is None:
            assert (
                hass.states.get(reg_entry.entity_id) is not None
            ), reg_entry.entity_id


async def test_key_entities_get_the_expected_stable_entity_ids(
    hass: HomeAssistant,
) -> None:
    await setup_terramow(hass)

    # The suffix-less unique_id belongs to the lawn mower itself.
    assert (
        resolve_entity_id(hass, "lawn_mower") == "lawn_mower.terramow_lawn_mower"
    )
    expected = {
        ("select", "main_direction_mode"): "select.terramow_main_direction_mode",
        ("select", "region_select"): "select.terramow_zone_select",
        ("number", "mowing_height"): "number.terramow_mowing_height_setting",
        ("sensor", "battery"): "sensor.terramow_battery",
        ("sensor", "mission"): "sensor.terramow_mission",
        ("binary_sensor", "problem"): "binary_sensor.terramow_problem",
        ("calendar", "schedule"): "calendar.terramow_mowing_schedule",
    }
    for (platform, suffix), entity_id in expected.items():
        assert resolve_entity_id(hass, platform, suffix) == entity_id


async def test_lawn_mower_starts_docked_and_available(hass: HomeAssistant) -> None:
    await setup_terramow(hass)
    state = hass.states.get(resolve_entity_id(hass, "lawn_mower"))
    assert state is not None
    assert state.state == "docked"


# ---------------------------------------------------------------------------
# main-direction select: lowercase state regression
# ---------------------------------------------------------------------------


async def test_main_direction_select_state_is_a_lowercase_token(
    hass: HomeAssistant,
) -> None:
    """Regression: the select publishes lowercase HA tokens, never the
    UPPERCASE device enum (which once broke consumers comparing states)."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    entity_id = resolve_entity_id(hass, "select", "main_direction_mode")

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "main_direction_mode_single"
    assert state.state == state.state.lower()
    options = state.attributes["options"]
    assert options == [option.lower() for option in options]
    assert state.state in options

    # A device push changes the state, still as a lowercase token.
    await push_dp(
        hass,
        hub,
        155,
        {
            "main_direction_angle_config": {
                "mode": "MAIN_DIRECTION_MODE_AUTO_ROTATE",
                "auto_rotate_mode_config": {"angle_interval": 45},
            }
        },
    )
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "main_direction_mode_auto_rotate"


async def test_main_direction_numbers_follow_device_reported_mode(
    hass: HomeAssistant,
) -> None:
    """The angle numbers' availability tracks the DEVICE mode (UPPERCASE
    enums), end to end — the exact wiring the uppercase/lowercase state bug
    broke: only the controls of the active mode are usable."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower

    single = resolve_entity_id(hass, "number", "main_direction_single_angle")
    auto = resolve_entity_id(hass, "number", "main_direction_auto_rotate_interval")
    angle1 = resolve_entity_id(hass, "number", "multiple_direction_angle1")
    angle2 = resolve_entity_id(hass, "number", "multiple_direction_angle2")

    # Before any device data every angle control is unavailable.
    for entity_id in (single, auto, angle1, angle2):
        state = hass.states.get(entity_id)
        assert state is not None and state.state == STATE_UNAVAILABLE

    # Device reports SINGLE mode: only the single-angle control is usable.
    await push_dp(
        hass,
        hub,
        155,
        {
            "mow_height": {"value": 60},
            "main_direction_angle_config": {
                "mode": "MAIN_DIRECTION_MODE_SINGLE",
                "single_mode_config": {"angle": 42},
            },
        },
    )
    assert hass.states.get(single).state == "42.0"
    assert hass.states.get(auto).state == STATE_UNAVAILABLE
    assert hass.states.get(angle1).state == STATE_UNAVAILABLE
    assert hass.states.get(angle2).state == STATE_UNAVAILABLE
    # A plain (mode-independent) number picked up the same push.
    assert (
        hass.states.get(resolve_entity_id(hass, "number", "mowing_height")).state
        == "60.0"
    )

    # Device switches to AUTO_ROTATE: availability flips accordingly.
    await push_dp(
        hass,
        hub,
        155,
        {
            "main_direction_angle_config": {
                "mode": "MAIN_DIRECTION_MODE_AUTO_ROTATE",
                "auto_rotate_mode_config": {"angle_interval": 45},
            }
        },
    )
    assert hass.states.get(single).state == STATE_UNAVAILABLE
    assert hass.states.get(auto).state == "45.0"

    # And MULTIPLE exposes the two paired angle controls.
    await push_dp(
        hass,
        hub,
        155,
        {
            "main_direction_angle_config": {
                "mode": "MAIN_DIRECTION_MODE_MULTIPLE",
                "multiple_mode_config": {"angles": [10, 100]},
            }
        },
    )
    assert hass.states.get(single).state == STATE_UNAVAILABLE
    assert hass.states.get(auto).state == STATE_UNAVAILABLE
    assert hass.states.get(angle1).state == "10.0"
    assert hass.states.get(angle2).state == "100.0"


# ---------------------------------------------------------------------------
# hub pushes drive real entity states
# ---------------------------------------------------------------------------


async def test_dp116_error_list_surfaces_as_problem_and_error(
    hass: HomeAssistant,
) -> None:
    """A fault reported only via dp_116 (has_error false) must surface (#171)."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower

    mower = resolve_entity_id(hass, "lawn_mower")
    problem = resolve_entity_id(hass, "binary_sensor", "problem")
    active_errors = resolve_entity_id(hass, "sensor", "active_errors")

    # Mowing cleanly, no error flag.
    await push_dp(
        hass,
        hub,
        107,
        {"mission": "MISSION_GLOBAL_CLEAN", "state": "MISSION_STATE_RUNNING",
         "has_error": False},
    )
    assert hass.states.get(mower).state == "mowing"
    assert hass.states.get(problem).state == "off"

    # The mower reports a fault only through the dp_116 error list.
    await push_dp(hass, hub, 116, {"error_list": [{"code": 42}]})
    assert hass.states.get(active_errors).state == "1"
    assert hass.states.get(problem).state == "on"
    assert hass.states.get(problem).attributes["error_codes"] == [42]
    assert hass.states.get(mower).state == "error"

    # Clearing the list recovers both the problem sensor and the mower.
    await push_dp(hass, hub, 116, {"error_list": []})
    assert hass.states.get(problem).state == "off"
    assert hass.states.get(mower).state == "mowing"


async def test_mission_status_pushes_update_real_states(hass: HomeAssistant) -> None:
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower

    mower = resolve_entity_id(hass, "lawn_mower")
    mission = resolve_entity_id(hass, "sensor", "mission")
    mission_state = resolve_entity_id(hass, "sensor", "mission_state")
    problem = resolve_entity_id(hass, "binary_sensor", "problem")

    await push_dp(
        hass,
        hub,
        107,
        {
            "mission": "MISSION_GLOBAL_CLEAN",
            "sub_mission": "SUB_MISSION_IDLE",
            "state": "MISSION_STATE_RUNNING",
            "has_error": False,
        },
    )
    assert hass.states.get(mower).state == "mowing"
    assert hass.states.get(mission).state == "mission_global_clean"
    assert hass.states.get(mission_state).state == "mission_state_running"
    assert hass.states.get(problem).state == "off"

    await push_dp(
        hass,
        hub,
        107,
        {
            "mission": "MISSION_GLOBAL_CLEAN",
            "state": "MISSION_STATE_PAUSE",
            "has_error": False,
        },
    )
    assert hass.states.get(mower).state == "paused"

    await push_dp(
        hass,
        hub,
        107,
        {
            "mission": "MISSION_GLOBAL_CLEAN",
            "state": "MISSION_STATE_RUNNING",
            "has_error": True,
        },
    )
    assert hass.states.get(mower).state == "error"
    assert hass.states.get(problem).state == "on"

    # Recovery: back to a recharge run.
    await push_dp(
        hass,
        hub,
        107,
        {
            "mission": "MISSION_RECHARGE",
            "state": "MISSION_STATE_RUNNING",
            "has_error": False,
        },
    )
    assert hass.states.get(mower).state == "returning"


async def test_battery_pushes_update_real_states(hass: HomeAssistant) -> None:
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower

    battery = resolve_entity_id(hass, "sensor", "battery")
    temperature_state = resolve_entity_id(
        hass, "sensor", "battery_temperature_state"
    )
    charging = resolve_entity_id(hass, "binary_sensor", "charging_state")

    assert hass.states.get(battery).state == "unknown"

    await push_dp(hass, hub, 8, {"int_value": 76})
    assert hass.states.get(battery).state == "76"

    await push_dp(
        hass,
        hub,
        108,
        {
            "state": "BATTERY_STATE_CHARGING",
            "tempreture": "BATTERY_TEMPRETURE_NORMAL",  # device typo, verbatim
            "charger_connected": True,
            "is_switch_on": True,
        },
    )
    state = hass.states.get(battery)
    assert state.state == "76"
    assert state.attributes["state"] == "BATTERY_STATE_CHARGING"
    assert state.attributes["temperature"] == "BATTERY_TEMPERATURE_NORMAL"
    # The enum sensor exposes the (typo'd) device token, lowercased.
    assert hass.states.get(temperature_state).state == "battery_tempreture_normal"
    assert hass.states.get(charging).state == "on"


async def test_zone_select_populates_from_map_info_push(hass: HomeAssistant) -> None:
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    zone_select = resolve_entity_id(hass, "select", "region_select")

    # No map info yet: no zone has ever been selected.
    state = hass.states.get(zone_select)
    assert state.state == "unknown"
    assert state.attributes["options"] == ["no_zones_available"]

    map_info = {
        "id": 1,
        "name": "Garden",
        "map_state": "MAP_STATE_COMPLETE",
        "regions": [
            {
                "id": 10,
                "name": "Main",
                "sub_regions": [
                    {"id": 7, "name": "Front lawn"},
                    {"id": 8, "name": "Back lawn"},
                ],
            }
        ],
    }
    await push_topic(hass, hub, "map/current/info", json.dumps(map_info))

    state = hass.states.get(zone_select)
    assert state.state == "all_zones"
    assert state.attributes["options"] == [
        "all_zones",
        "Front lawn (ID: 7)",
        "Back lawn (ID: 8)",
    ]

    # Selecting a real zone sends the select-region command to dp_103.
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": zone_select, "option": "Front lawn (ID: 7)"},
        blocking=True,
    )
    assert hass.states.get(zone_select).state == "Front lawn (ID: 7)"
    publish = hub.mqtt_client.publish
    topic, payload = publish.call_args[0][0], publish.call_args[0][1]
    assert topic == "data_point/103/app"
    command = json.loads(payload)
    assert command["mode"] == "START_MODE_SELECT_REGION_CLEAN"
    assert command["select_region_clean"]["region_ids"] == [7]


# ---------------------------------------------------------------------------
# unload
# ---------------------------------------------------------------------------


async def test_unload_entry_stops_hub_and_removes_service(
    hass: HomeAssistant,
) -> None:
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    mower = resolve_entity_id(hass, "lawn_mower")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    # The hub was stopped: shutdown signalled, no connection task left behind.
    assert hub._stop_event.is_set()
    assert hub._mqtt_task is None
    # The shared service is dropped with the last loaded entry.
    assert not hass.services.has_service(DOMAIN, SERVICE_START_SELECT_REGION)
    # The entity is torn down; only a restored unavailable state remains.
    state = hass.states.get(mower)
    assert state is not None and state.state == STATE_UNAVAILABLE
