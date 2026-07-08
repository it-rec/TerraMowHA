"""Tests for the hub callback lifecycle (register -> unsubscribe).

Every hub registration method returns an unsubscribe callable that entities
hand to ``async_on_remove``; a disabled or removed entity must be removed
from the hub's callback lists instead of leaking and being invoked forever.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.event import TerraMowMowerEventEntity
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.lawn_mower import TerraMowLawnMowerEntity
from custom_components.terramow.map_sensor import TerraMowMapAreaSensor
from custom_components.terramow.select import TerraMowZoneSelect
from custom_components.terramow.sensor import (
    SENSORS,
    TerraMowPoseSensor,
    TerraMowSensor,
)

_MISSION_DESCRIPTION = next(d for d in SENSORS if d.key == "mission")


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.180", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    # run loop dispatches inline so callbacks fire synchronously
    hub.hass.loop.call_soon_threadsafe = MagicMock(side_effect=lambda fn, *a: fn(*a))
    return hub


def _msg(topic: str, payload: bytes):
    msg = MagicMock()
    msg.topic = topic
    msg.payload = payload
    return msg


# ---------------------------------------------------------------------------
# hub: every register_* returns a working, idempotent unsubscribe
# ---------------------------------------------------------------------------


def test_register_callback_returns_idempotent_unsubscribe() -> None:
    hub = _hub()
    cb = MagicMock()
    unsubscribe = hub.register_callback(199, cb)
    assert cb in hub.callbacks[199]

    unsubscribe()
    assert cb not in hub.callbacks[199]
    unsubscribe()  # second call must be a no-op, not a ValueError
    assert cb not in hub.callbacks[199]


def test_register_stream_callbacks_return_idempotent_unsubscribe() -> None:
    hub = _hub()
    for register, callbacks in (
        (hub.register_map_callback, hub.map_callbacks),
        (hub.register_pose_callback, hub.pose_callbacks),
        (hub.register_path_callback, hub.path_callbacks),
        (hub.register_history_path_callback, hub.history_path_callbacks),
    ):
        cb = MagicMock()
        unsubscribe = register(cb)
        assert cb in callbacks

        unsubscribe()
        assert cb not in callbacks
        unsubscribe()  # idempotent
        assert cb not in callbacks


def test_register_state_listener_returns_idempotent_unsubscribe() -> None:
    hub = _hub()
    listener = MagicMock()
    unsubscribe = hub.register_state_listener(listener)
    hub._notify_state_listeners()
    listener.assert_called_once()

    unsubscribe()
    unsubscribe()  # idempotent
    hub._notify_state_listeners()
    listener.assert_called_once()  # not invoked again


def test_unsubscribed_dp_callback_no_longer_dispatched() -> None:
    hub = _hub()
    cb = MagicMock()
    unsubscribe = hub.register_callback(199, cb)

    hub.on_mqtt_message(None, None, _msg("data_point/199/robot", b'{"x": 1}'))
    cb.assert_called_once_with('{"x": 1}')

    unsubscribe()
    hub.on_mqtt_message(None, None, _msg("data_point/199/robot", b'{"x": 2}'))
    cb.assert_called_once()  # no further dispatch after unsubscribe


def test_unsubscribed_pose_callback_no_longer_dispatched() -> None:
    hub = _hub()
    cb = MagicMock()
    unsubscribe = hub.register_pose_callback(cb)

    hub.on_mqtt_message(None, None, _msg("pose/current", b'{"x": 1.0}'))
    cb.assert_called_once_with({"x": 1.0})

    unsubscribe()
    hub.on_mqtt_message(None, None, _msg("pose/current", b'{"x": 2.0}'))
    cb.assert_called_once()


# ---------------------------------------------------------------------------
# entities: removal deregisters from the hub via async_on_remove
# ---------------------------------------------------------------------------


def test_push_update_mixin_deregisters_on_entity_removal() -> None:
    hub = _hub()
    sensor = TerraMowSensor(hub.basic_data, hub.hass, _MISSION_DESCRIPTION)
    asyncio.run(sensor.async_added_to_hass())
    assert sensor._handle_push_update in hub.callbacks[107]

    sensor._call_on_remove_callbacks()
    assert sensor._handle_push_update not in hub.callbacks[107]


def test_pose_sensor_registers_on_add_and_deregisters_on_removal() -> None:
    hub = _hub()
    sensor = TerraMowPoseSensor(hub.basic_data, hub.hass)
    # constructing the entity must not register anything yet
    assert hub.pose_callbacks == []

    asyncio.run(sensor.async_added_to_hass())
    assert sensor._on_pose in hub.pose_callbacks

    sensor._call_on_remove_callbacks()
    assert hub.pose_callbacks == []


def test_zone_select_registers_on_add_and_deregisters_on_removal() -> None:
    hub = _hub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    assert hub.map_callbacks == []

    asyncio.run(select.async_added_to_hass())
    assert select._on_map_info in hub.map_callbacks

    select._call_on_remove_callbacks()
    assert hub.map_callbacks == []


def test_map_sensor_registers_on_add_and_deregisters_on_removal() -> None:
    hub = _hub()
    sensor = TerraMowMapAreaSensor(hub.basic_data, hub.hass)
    assert hub.map_callbacks == []

    asyncio.run(sensor.async_added_to_hass())
    assert sensor._on_map_info in hub.map_callbacks

    # the custom map handler still caches the map info for the entity state
    asyncio.run(sensor._on_map_info({"total_area": 123}))
    assert sensor.native_value == 12.3

    sensor._call_on_remove_callbacks()
    assert hub.map_callbacks == []


def test_map_sensor_added_without_lawn_mower_is_noop() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    sensor = TerraMowMapAreaSensor(hub.basic_data, hub.hass)
    asyncio.run(sensor.async_added_to_hass())  # must not raise
    assert sensor.native_value is None


def test_lawn_mower_deregisters_state_listener_on_removal() -> None:
    hub = _hub()
    entity = TerraMowLawnMowerEntity(hub.basic_data, hub.hass)
    asyncio.run(entity.async_added_to_hass())
    assert entity._on_hub_state in hub._state_listeners

    entity._call_on_remove_callbacks()
    assert entity._on_hub_state not in hub._state_listeners


def test_event_entity_deregisters_state_listener_on_removal() -> None:
    hub = _hub()
    entity = TerraMowMowerEventEntity(hub.basic_data, hub.hass)
    with patch(
        "homeassistant.components.event.EventEntity.async_added_to_hass", AsyncMock()
    ):
        asyncio.run(entity.async_added_to_hass())
    assert entity._on_hub_state in hub._state_listeners

    entity._call_on_remove_callbacks()
    assert entity._on_hub_state not in hub._state_listeners
