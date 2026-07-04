"""Coverage for the hub command senders (lawn-mower start/pause/dock).

These map the current dp_107 mission/sub-mission/state onto the right device
command (dp_103/105/106) and are guarded by the command rate limiter.
"""

import asyncio
import json
from unittest.mock import MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.40", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    # start every test with the command rate limiter cleared
    hub._last_control_time = 0.0
    return hub


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


def _published(hub) -> tuple[str, dict]:
    topic, payload = hub.mqtt_client.publish.call_args.args
    return topic, json.loads(payload)


def _clear_limiter(hub) -> None:
    hub._last_control_time = 0.0


# ---------------------------------------------------------------------------
# start_mowing
# ---------------------------------------------------------------------------


def test_start_mowing_idle_starts_global_clean() -> None:
    hub = _hub()
    hub.start_mowing()
    topic, command = _published(hub)
    assert topic == "data_point/103/app"
    assert command["mode"] == "START_MODE_GLOBAL_CLEAN"
    assert command["global_clean"] == {"restart": False}


def test_start_mowing_paused_job_resumes() -> None:
    hub = _hub()
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN",
        "state": "MISSION_STATE_PAUSE",
    })
    _clear_limiter(hub)
    hub.start_mowing()
    topic, command = _published(hub)
    # resume is dp_106
    assert topic == "data_point/106/app"
    assert "seq" in command


def test_start_mowing_station_wait_resumes() -> None:
    hub = _hub()
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN",
        "sub_mission": "SUB_MISSION_FLEXIBLE_STATION_WAIT",
    })
    _clear_limiter(hub)
    hub.start_mowing()
    topic, _ = _published(hub)
    assert topic == "data_point/106/app"


# ---------------------------------------------------------------------------
# pause
# ---------------------------------------------------------------------------


def test_pause_running_job_sends_pause() -> None:
    hub = _hub()
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN",
        "state": "MISSION_STATE_RUNNING",
    })
    _clear_limiter(hub)
    hub.pause()
    topic, _ = _published(hub)
    # pause is dp_105
    assert topic == "data_point/105/app"


# ---------------------------------------------------------------------------
# dock
# ---------------------------------------------------------------------------


def test_dock_from_mowing_starts_return() -> None:
    hub = _hub()
    hub.dock()
    topic, command = _published(hub)
    assert topic == "data_point/103/app"
    assert command["mode"] == "START_MODE_RETURN"


def test_dock_resumes_paused_recharge() -> None:
    hub = _hub()
    _feed(hub.on_mission_status, {
        "mission": "MISSION_RECHARGE",
        "state": "MISSION_STATE_PAUSE",
    })
    _clear_limiter(hub)
    hub.dock()
    topic, _ = _published(hub)
    # resuming recharge routes through resume mowing (dp_106)
    assert topic == "data_point/106/app"


# ---------------------------------------------------------------------------
# select region clean
# ---------------------------------------------------------------------------


def test_start_select_region_clean_publishes_region_ids() -> None:
    hub = _hub()
    hub.start_select_region_clean([4, 5])
    topic, command = _published(hub)
    assert topic == "data_point/103/app"
    assert command["mode"] == "START_MODE_SELECT_REGION_CLEAN"
    assert command["select_region"] == {"region_id": [4, 5]}


def test_start_select_region_clean_ignores_empty_ids() -> None:
    hub = _hub()
    hub.start_select_region_clean([])
    hub.mqtt_client.publish.assert_not_called()


# ---------------------------------------------------------------------------
# rate limiter
# ---------------------------------------------------------------------------


def test_command_rate_limiter_blocks_rapid_second_command() -> None:
    hub = _hub()
    hub.dock()
    assert hub.mqtt_client.publish.call_count == 1
    # immediate second command is skipped by the rate limiter
    hub.dock()
    assert hub.mqtt_client.publish.call_count == 1
