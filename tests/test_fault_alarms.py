"""Lift / anti-theft boundary alarms from the dp_116 fault list (upstream #34).

Pins the boundaries of ``TerraMowHub.fault_snapshot_codes``: unknown until a
complete fault list arrives on the current connection, cleared again on
connect and on connection loss, and never set by the single-code channels
(dp_115 latest fault, dp_123 event log).
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiomqtt
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.binary_sensor import (
    BINARY_SENSORS,
    TerraMowBinarySensor,
)
from custom_components.terramow.error_codes import describe_error
from custom_components.terramow.hub import TerraMowHub

_DESCRIPTIONS = {description.key: description for description in BINARY_SENSORS}
_ALARMS = ("lift_alarm", "anti_theft_boundary_alarm")


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.34", password="secret")
    return TerraMowHub(basic_data, MagicMock())


def _alarm(hub: TerraMowHub, key: str) -> TerraMowBinarySensor:
    return TerraMowBinarySensor(hub.basic_data, hub.hass, _DESCRIPTIONS[key])


def _states(hub: TerraMowHub) -> tuple[bool | None, bool | None]:
    lift, boundary = (_alarm(hub, key) for key in _ALARMS)
    return lift.is_on, boundary.is_on


def _feed(handler, payload: str) -> None:
    asyncio.run(handler(payload))


def test_alarm_descriptions() -> None:
    for key in _ALARMS:
        description = _DESCRIPTIONS[key]
        assert description.translation_key == key
        assert description.device_class == BinarySensorDeviceClass.TAMPER
        # main device section, not diagnostic: meant for automations
        assert description.entity_category is None
        assert description.push_dp_ids == (116,)
        assert description.refresh_on_connection is True
    # every other binary sensor keeps the push-only refresh
    assert [d.key for d in BINARY_SENSORS if d.refresh_on_connection] == list(
        _ALARMS
    )


def test_alarm_codes_have_catalog_text() -> None:
    assert describe_error(202) == "Mower lifted"
    assert describe_error(1409) == "Anti-theft boundary crossed"


def test_only_complete_fault_list_drives_alarms() -> None:
    hub = _hub()
    assert hub.fault_snapshot_codes is None
    assert _states(hub) == (None, None)

    # single-code channels never resolve the alarms
    _feed(hub.on_active_error_code, json.dumps({"int_value": 201}))
    _feed(hub.on_event_data, json.dumps({"event_list": [{"code": 1409}]}))
    assert _states(hub) == (None, None)

    # protobuf JSON omits an empty repeated field: "{}" is an all-clear list
    _feed(hub.on_error_list, "{}")
    assert hub.fault_snapshot_codes == frozenset()
    assert _states(hub) == (False, False)

    _feed(
        hub.on_error_list,
        json.dumps({"error_list": [{"code": 201}, {"code": 1409}, {"code": 903}]}),
    )
    assert _states(hub) == (True, True)
    _feed(hub.on_error_list, json.dumps({"error_list": [{"code": 202}]}))
    assert _states(hub) == (True, False)

    # malformed reports leave the last complete list in place
    for invalid in (
        "not json",
        "[]",
        json.dumps({"unexpected": True}),
        json.dumps({"error_list": "bad"}),
    ):
        _feed(hub.on_error_list, invalid)
    assert _states(hub) == (True, False)
    assert hub.error_list == [{"code": 202}]

    # malformed entries inside a list are skipped, not trusted
    _feed(
        hub.on_error_list,
        json.dumps({"error_list": [{"code": True}, "opaque", {"code": 1409}]}),
    )
    assert hub.fault_snapshot_codes == frozenset({1409})
    assert _states(hub) == (False, True)

    _feed(hub.on_error_list, json.dumps({"error_list": []}))
    assert _states(hub) == (False, False)


def test_empty_object_clears_active_fault() -> None:
    hub = _hub()
    _feed(hub.on_error_list, json.dumps({"error_list": [{"code": 903}]}))
    assert hub.has_active_error is True
    _feed(hub.on_error_list, "{}")
    assert hub.error_list == []
    assert hub.has_active_error is False


def test_reconnect_waits_for_a_fresh_list() -> None:
    hub = _hub()
    _feed(hub.on_error_list, json.dumps({"error_list": [{"code": 201}]}))
    assert _states(hub) == (True, False)

    observed: list[frozenset[int] | None] = []
    hub.register_state_listener(lambda: observed.append(hub.fault_snapshot_codes))
    client = MagicMock()
    client.subscribe = AsyncMock()
    asyncio.run(hub._async_on_connected(client))
    # listeners already see the reset when they are told about the connect
    assert observed == [None]
    assert _states(hub) == (None, None)
    # the raw list itself stays a mirror of the last device report
    assert hub.error_list == [{"code": 201}]

    _feed(hub.on_error_list, "{}")
    assert _states(hub) == (False, False)


def test_connection_loss_clears_the_list() -> None:
    hub = _hub()
    _feed(hub.on_error_list, json.dumps({"error_list": [{"code": 1409}]}))
    observed: list[tuple[bool, frozenset[int] | None]] = []
    hub.register_state_listener(
        lambda: observed.append((hub.connection_error, hub.fault_snapshot_codes))
    )
    attempts = {"n": 0}

    def failing_client(**kwargs):
        attempts["n"] += 1
        raise aiomqtt.MqttError("connection refused")

    async def main() -> None:
        with (
            patch(
                "custom_components.terramow.hub.aiomqtt.Client",
                side_effect=failing_client,
            ),
            patch("custom_components.terramow.hub.MQTT_RECONNECT_BASE_DELAY", 0),
        ):
            task = asyncio.get_running_loop().create_task(hub._async_mqtt_runner())
            for _ in range(200):
                await asyncio.sleep(0)
                if attempts["n"] >= 1 and observed:
                    break
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(main())
    assert hub.fault_snapshot_codes is None
    assert observed[0] == (True, None)
    entity = _alarm(hub, "anti_theft_boundary_alarm")
    assert entity.is_on is None
    assert entity.available is False


def test_alarm_refreshes_on_connection_changes() -> None:
    hub = _hub()
    alarm = _alarm(hub, "lift_alarm")
    with patch(
        "custom_components.terramow.binary_sensor.safe_write_ha_state"
    ) as write:
        asyncio.run(alarm.async_added_to_hass())
        hub._set_connection_error(True)
        write.assert_called_once_with(alarm)
        # removing the entity drops the hub listener
        for remove in alarm._on_remove or []:
            remove()
        hub._set_connection_error(False)
        write.assert_called_once()


def test_other_sensors_and_unloaded_hub_skip_state_listener() -> None:
    hub = _hub()
    problem = TerraMowBinarySensor(hub.basic_data, hub.hass, _DESCRIPTIONS["problem"])
    asyncio.run(problem.async_added_to_hass())
    assert hub._state_listeners == []

    alarm = _alarm(hub, "lift_alarm")
    hub.basic_data.lawn_mower = None
    asyncio.run(alarm.async_added_to_hass())
    assert hub._state_listeners == []
    assert alarm.is_on is None
