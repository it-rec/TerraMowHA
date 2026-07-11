"""Tests for the TerraMow hub and the lawn mower activity mapping."""

import asyncio
import json
import logging
import time
from unittest.mock import MagicMock

import pytest
from homeassistant.components.lawn_mower.const import LawnMowerActivity
from homeassistant.exceptions import HomeAssistantError

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import (
    MAP_SAVE_DISPLAY_TIMEOUT,
    Mission,
    MissionState,
    SubMission,
    TerraMowHub,
)
from custom_components.terramow.lawn_mower import TerraMowLawnMowerEntity


def _make_hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.10", password="secret")
    return TerraMowHub(basic_data, MagicMock())


def _feed_dp107(hub: TerraMowHub, **fields) -> None:
    asyncio.run(hub.on_mission_status(json.dumps(fields)))


def _feed_dp118(hub: TerraMowHub, int_value: int) -> None:
    asyncio.run(hub.on_map_save_progress(json.dumps({"int_value": int_value})))


def _allow_command(hub: TerraMowHub) -> None:
    """Rewind the rate limiter so the next command is accepted."""
    hub._last_control_time = time.monotonic() - 10


def test_hub_registers_itself_as_lawn_mower() -> None:
    hub = _make_hub()
    assert hub.basic_data.lawn_mower is hub


def test_mission_status_parsing() -> None:
    hub = _make_hub()
    _feed_dp107(
        hub,
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_IDLE",
        state="MISSION_STATE_RUNNING",
        power_mode="POWER_MODE_RUNNING",
        has_error=False,
        is_saving_data=True,
        is_robot_navi_located=True,
    )
    assert hub.mission is Mission.MISSION_GLOBAL_CLEAN
    assert hub.mission_state is MissionState.MISSION_STATE_RUNNING
    assert hub.task_status["mission"] == "MISSION_GLOBAL_CLEAN"  # raw payload
    assert hub.is_saving_data is True
    assert hub.has_error is False
    assert hub.is_robot_navi_located is True
    assert hub.power_mode == "POWER_MODE_RUNNING"


def test_mission_status_invalid_enum_keeps_previous_value() -> None:
    hub = _make_hub()
    _feed_dp107(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_RUNNING")
    _feed_dp107(hub, mission="MISSION_FROM_THE_FUTURE")
    # An unknown enum value (e.g. newer firmware) keeps the previous known
    # state instead of clobbering it with None
    assert hub.mission is Mission.MISSION_GLOBAL_CLEAN
    assert hub.mission_state is MissionState.MISSION_STATE_RUNNING


def test_display_mission_mirrors_raw_when_not_saving_map() -> None:
    hub = _make_hub()
    _feed_dp107(
        hub,
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_IDLE",
        state="MISSION_STATE_RUNNING",
    )
    # Outside a map save the display values are exactly the raw ones.
    assert hub.display_sub_mission is SubMission.SUB_MISSION_IDLE
    assert hub.display_mission_state is MissionState.MISSION_STATE_RUNNING


def test_saving_map_shown_while_upload_incomplete() -> None:
    hub = _make_hub()
    _feed_dp107(
        hub,
        mission="MISSION_BUILD_MAP",
        sub_mission="SUB_MISSION_SAVING_MAP",
        state="MISSION_STATE_RUNNING",
    )
    _feed_dp118(hub, 40)
    # The save is genuinely in progress, so it must still be shown.
    assert hub.display_sub_mission is SubMission.SUB_MISSION_SAVING_MAP
    assert hub.display_mission_state is MissionState.MISSION_STATE_RUNNING


def test_saving_map_decays_to_idle_on_upload_complete() -> None:
    hub = _make_hub()
    _feed_dp107(
        hub,
        mission="MISSION_BUILD_MAP",
        sub_mission="SUB_MISSION_SAVING_MAP",
        state="MISSION_STATE_RUNNING",
    )
    _feed_dp118(hub, 100)
    # Issue #142: once the upload finishes the stale busy state decays to idle.
    assert hub.display_sub_mission is SubMission.SUB_MISSION_IDLE
    assert hub.display_mission_state is MissionState.MISSION_STATE_IDLE
    # The raw values (and the diagnostics payload) are preserved untouched.
    assert hub.sub_mission is SubMission.SUB_MISSION_SAVING_MAP
    assert hub.mission_state is MissionState.MISSION_STATE_RUNNING
    assert hub.task_status["sub_mission"] == "SUB_MISSION_SAVING_MAP"


def test_saving_map_decays_to_idle_after_timeout() -> None:
    hub = _make_hub()
    _feed_dp107(
        hub,
        mission="MISSION_BUILD_MAP",
        sub_mission="SUB_MISSION_SAVING_MAP",
        state="MISSION_STATE_RUNNING",
    )
    # No progress signal ever arrives; the timeout fallback still retires it.
    assert hub.display_sub_mission is SubMission.SUB_MISSION_SAVING_MAP
    hub._map_save_started_at = time.monotonic() - (MAP_SAVE_DISPLAY_TIMEOUT + 1)
    assert hub.display_sub_mission is SubMission.SUB_MISSION_IDLE
    assert hub.display_mission_state is MissionState.MISSION_STATE_IDLE


def test_new_saving_map_episode_ignores_previous_completion() -> None:
    hub = _make_hub()
    _feed_dp107(
        hub,
        mission="MISSION_BUILD_MAP",
        sub_mission="SUB_MISSION_SAVING_MAP",
        state="MISSION_STATE_RUNNING",
    )
    _feed_dp118(hub, 100)
    assert hub.display_sub_mission is SubMission.SUB_MISSION_IDLE
    # Leave the save, then start a brand-new one: the stale 100 % from the first
    # episode must not make the second save look already finished.
    _feed_dp107(
        hub,
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_IDLE",
        state="MISSION_STATE_RUNNING",
    )
    _feed_dp107(
        hub,
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_SAVING_MAP",
        state="MISSION_STATE_RUNNING",
    )
    assert hub.display_sub_mission is SubMission.SUB_MISSION_SAVING_MAP
    assert hub.display_mission_state is MissionState.MISSION_STATE_RUNNING


def test_mission_status_notifies_state_listeners() -> None:
    hub = _make_hub()
    listener = MagicMock()
    hub.register_state_listener(listener)
    _feed_dp107(hub, mission="MISSION_RECHARGE")
    listener.assert_called_once()


def test_failing_state_listener_does_not_break_others() -> None:
    hub = _make_hub()
    hub.register_state_listener(MagicMock(side_effect=RuntimeError("boom")))
    good = MagicMock()
    hub.register_state_listener(good)
    _feed_dp107(hub, mission="MISSION_RECHARGE")
    good.assert_called_once()


def test_publish_data_point() -> None:
    hub = _make_hub()
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    hub.publish_data_point(103, {"seq": 1})
    topic, payload = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/103/app"
    assert json.loads(payload) == {"seq": 1}


def test_start_mowing_from_idle_sends_global_clean() -> None:
    hub = _make_hub()
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    _allow_command(hub)
    hub.start_mowing()
    topic, payload = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/103/app"
    assert json.loads(payload)["mode"] == "START_MODE_GLOBAL_CLEAN"


def test_start_mowing_resumes_paused_job_via_dp106() -> None:
    hub = _make_hub()
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    _feed_dp107(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_PAUSE")
    _allow_command(hub)
    hub.start_mowing()
    topic, _payload = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/106/app"


def test_start_mowing_while_running_sends_nothing() -> None:
    hub = _make_hub()
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    _feed_dp107(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_RUNNING")
    _allow_command(hub)
    hub.start_mowing()
    hub.mqtt_client.publish.assert_not_called()


def test_dock_sends_return_command() -> None:
    hub = _make_hub()
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    _allow_command(hub)
    hub.dock()
    topic, payload = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/103/app"
    assert json.loads(payload)["mode"] == "START_MODE_RETURN"


def test_command_rate_limit() -> None:
    hub = _make_hub()
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    _allow_command(hub)
    hub.start_edge_trim()
    with pytest.raises(HomeAssistantError):
        hub.start_edge_trim()  # immediately again -> rate limited, raises
    assert hub.mqtt_client.publish.call_count == 1


def test_dp_callback_dispatch_and_unknown_dp_logging() -> None:
    hub = _make_hub()
    received = MagicMock()
    hub.register_callback(8, received)

    # run the thread->loop dispatch inline so the callback fires synchronously
    hub.hass.loop.call_soon_threadsafe = MagicMock(side_effect=lambda fn, *a: fn(*a))

    msg = MagicMock()
    msg.topic = "data_point/8/robot"
    msg.payload = b'{"int_value": 55}'
    hub.on_mqtt_message(None, None, msg)
    received.assert_called_with('{"int_value": 55}')

    unknown = MagicMock()
    unknown.topic = "data_point/199/robot"
    unknown.payload = b"{}"
    hub.on_mqtt_message(None, None, unknown)
    assert 199 in hub._seen_unknown_dp_ids

    # a repeat of a known-unknown dp logs the payload only at DEBUG (the
    # slice is guarded by isEnabledFor). Pin the logger level explicitly for
    # both branches: the ambient level differs between environments (CI runs
    # the suite with debug logging enabled), so relying on it makes branch
    # coverage non-deterministic.
    logger = logging.getLogger("custom_components.terramow.hub")
    previous_level = logger.level
    try:
        logger.setLevel(logging.DEBUG)
        hub.on_mqtt_message(None, None, unknown)
        logger.setLevel(logging.INFO)
        hub.on_mqtt_message(None, None, unknown)  # slice skipped, no log
    finally:
        logger.setLevel(previous_level)
    assert hub._unknown_dp_payloads[199] == "{}"


class _Activity:
    """Helper wiring a lawn mower entity to a hub without HA running."""

    def __init__(self) -> None:
        self.hub = _make_hub()
        self.entity = TerraMowLawnMowerEntity(self.hub.basic_data, MagicMock())

    def feed(self, **fields) -> LawnMowerActivity:
        _feed_dp107(self.hub, **fields)
        self.entity.update_activity_from_state()
        return self.entity.activity


def test_activity_mowing_when_clean_mission_runs() -> None:
    probe = _Activity()
    activity = probe.feed(
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_IDLE",
        state="MISSION_STATE_RUNNING",
    )
    assert activity is LawnMowerActivity.MOWING


def test_activity_paused_in_flexible_station_wait() -> None:
    probe = _Activity()
    activity = probe.feed(
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_FLEXIBLE_STATION_WAIT",
        state="MISSION_STATE_RUNNING",
    )
    assert activity is LawnMowerActivity.PAUSED


def test_activity_docked_while_saving_map() -> None:
    probe = _Activity()
    activity = probe.feed(
        mission="MISSION_BUILD_MAP",
        sub_mission="SUB_MISSION_SAVING_MAP",
        state="MISSION_STATE_RUNNING",
    )
    assert activity is LawnMowerActivity.DOCKED


def test_activity_returning_during_recharge() -> None:
    probe = _Activity()
    activity = probe.feed(
        mission="MISSION_RECHARGE",
        sub_mission="SUB_MISSION_RETURN_TO_BASE",
        state="MISSION_STATE_RUNNING",
    )
    expected = (
        LawnMowerActivity.RETURNING
        if hasattr(LawnMowerActivity, "RETURNING")
        else LawnMowerActivity.DOCKED
    )
    assert activity is expected


def test_activity_paused_when_mission_paused() -> None:
    probe = _Activity()
    activity = probe.feed(mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_PAUSE")
    assert activity is LawnMowerActivity.PAUSED


def test_activity_error_on_device_fault() -> None:
    probe = _Activity()
    activity = probe.feed(
        mission="MISSION_GLOBAL_CLEAN",
        state="MISSION_STATE_RUNNING",
        has_error=True,
    )
    assert activity is LawnMowerActivity.ERROR


def test_activity_error_on_connection_loss_and_recovery() -> None:
    probe = _Activity()
    assert probe.feed(mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_RUNNING") is (
        LawnMowerActivity.MOWING
    )

    probe.hub._set_connection_error(True)
    probe.entity.update_activity_from_state()
    assert probe.entity.activity is LawnMowerActivity.ERROR

    probe.hub._set_connection_error(False)
    probe.entity.update_activity_from_state()
    assert probe.entity.activity is LawnMowerActivity.MOWING


def test_connection_error_availability_split() -> None:
    """Entities go unavailable on connection loss; the mower stays to show ERROR."""
    from custom_components.terramow.sensor import SENSORS, TerraMowSensor

    probe = _Activity()
    description = next(d for d in SENSORS if d.key == "battery_state")
    sensor = TerraMowSensor(probe.hub.basic_data, probe.hub.hass, description)
    assert sensor.available is True
    assert probe.entity.available is True

    probe.hub._set_connection_error(True)
    assert sensor.available is False
    assert probe.entity.available is True  # surfaces ERROR instead
