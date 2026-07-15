"""Coverage for the mower event entity.

Drives the hub's dp_107 mission state through every transition and asserts the
event entity fires the matching event type (with the raw mission fields as
attributes), seeds its phase without firing on startup, and stays silent when
nothing changes.
"""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.event import (
    EVENT_COMPLETED,
    EVENT_DOCKED,
    EVENT_ERROR,
    EVENT_PAUSED,
    EVENT_RETURNING,
    EVENT_STARTED,
    TerraMowMowerEventEntity,
    async_setup_entry,
)
from custom_components.terramow.hub import MAP_SAVE_DISPLAY_TIMEOUT, TerraMowHub


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.150", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def _entity(hub: TerraMowHub) -> TerraMowMowerEventEntity:
    ent = TerraMowMowerEventEntity(hub.basic_data, hub.hass)
    ent._trigger_event = MagicMock()  # type: ignore[method-assign]
    ent.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    return ent


def _added(ent: TerraMowMowerEventEntity) -> None:
    with patch(
        "homeassistant.components.event.EventEntity.async_added_to_hass", AsyncMock()
    ):
        asyncio.run(ent.async_added_to_hass())


def _feed(hub: TerraMowHub, **fields) -> None:
    asyncio.run(hub.on_mission_status(json.dumps(fields)))


def _feed_dp118(hub: TerraMowHub, int_value: int) -> None:
    asyncio.run(hub.on_map_save_progress(json.dumps({"int_value": int_value})))


def _fire(ent: TerraMowMowerEventEntity) -> None:
    ent._on_hub_state()
    asyncio.run(ent._async_drain_pending())


def test_schedule_drain_creates_task_on_loop() -> None:
    hub = _hub()
    ent = _entity(hub)
    created: list = []
    hub.hass.async_create_task = MagicMock(side_effect=created.append)
    ent._schedule_drain()
    assert len(created) == 1
    created[0].close()


def _last_event(ent: TerraMowMowerEventEntity) -> str | None:
    if not ent._trigger_event.called:
        return None
    return ent._trigger_event.call_args.args[0]


# ---------------------------------------------------------------------------
# platform setup + basic properties
# ---------------------------------------------------------------------------


def test_async_setup_entry_creates_event_entity() -> None:
    hub = _hub()
    added: list = []
    entry = SimpleNamespace(runtime_data=hub.basic_data)
    asyncio.run(async_setup_entry(hub.hass, entry, added.extend))
    assert len(added) == 1
    assert isinstance(added[0], TerraMowMowerEventEntity)


def test_available_reflects_lawn_mower_presence() -> None:
    hub = _hub()
    ent = _entity(hub)
    assert ent.available is True
    hub.basic_data.lawn_mower = None
    assert ent.available is False


def test_event_types_exposed() -> None:
    hub = _hub()
    ent = _entity(hub)
    assert set(ent.event_types) == {
        EVENT_STARTED,
        EVENT_PAUSED,
        EVENT_RETURNING,
        EVENT_DOCKED,
        EVENT_COMPLETED,
        EVENT_ERROR,
    }


# ---------------------------------------------------------------------------
# seeding: no event for the phase that already existed
# ---------------------------------------------------------------------------


def test_added_to_hass_seeds_phase_without_firing() -> None:
    hub = _hub()
    _feed(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_RUNNING")
    ent = _entity(hub)
    _added(ent)
    # the mower was already mowing -> feeding the same state fires nothing
    _fire(ent)
    ent._trigger_event.assert_not_called()


# ---------------------------------------------------------------------------
# transitions
# ---------------------------------------------------------------------------


def test_transition_to_mowing_fires_started() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    _feed(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_RUNNING")
    _fire(ent)
    assert _last_event(ent) == EVENT_STARTED
    attrs = ent._trigger_event.call_args.args[1]
    assert attrs["mission"] == "MISSION_GLOBAL_CLEAN"
    assert attrs["state"] == "MISSION_STATE_RUNNING"
    ent.async_write_ha_state.assert_called_once()


def test_transition_to_paused_fires_paused() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    _feed(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_PAUSE")
    _fire(ent)
    assert _last_event(ent) == EVENT_PAUSED


def test_station_wait_maps_to_paused() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    _feed(
        hub,
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_FLEXIBLE_STATION_WAIT",
        state="MISSION_STATE_RUNNING",
    )
    _fire(ent)
    assert _last_event(ent) == EVENT_PAUSED


def test_saving_map_maps_to_docked() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    _feed(
        hub,
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_SAVING_MAP",
        state="MISSION_STATE_RUNNING",
    )
    # starts docked already; force a different seed so we observe the change
    ent._last_phase = "mowing"
    _fire(ent)
    assert _last_event(ent) == EVENT_DOCKED


def test_transition_to_returning_carries_reason() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    _feed(
        hub,
        mission="MISSION_RECHARGE",
        state="MISSION_STATE_RUNNING",
        back_to_station_reason="BACK_TO_STATION_REASON_RAINING",
    )
    _fire(ent)
    assert _last_event(ent) == EVENT_RETURNING
    attrs = ent._trigger_event.call_args.args[1]
    assert attrs["back_to_station_reason"] == "BACK_TO_STATION_REASON_RAINING"


def test_running_non_mow_non_recharge_maps_to_docked() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    ent._last_phase = "mowing"
    _feed(hub, mission="MISSION_BACKUP_MAP", state="MISSION_STATE_RUNNING")
    _fire(ent)
    assert _last_event(ent) == EVENT_DOCKED


def test_transition_to_docked_fires_docked() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    ent._last_phase = "mowing"
    _feed(hub, mission="MISSION_IDLE", state="MISSION_STATE_IDLE")
    _fire(ent)
    assert _last_event(ent) == EVENT_DOCKED


def test_completion_fires_completed_and_resets() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    _feed(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_COMPLETE")
    _fire(ent)
    assert _last_event(ent) == EVENT_COMPLETED
    # a later non-complete state clears the completion latch
    ent._trigger_event.reset_mock()
    _feed(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_RUNNING")
    _fire(ent)
    assert _last_event(ent) == EVENT_STARTED


def test_error_fires_error_event() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    _feed(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_RUNNING", has_error=True)
    _fire(ent)
    assert _last_event(ent) == EVENT_ERROR
    assert ent._trigger_event.call_args.args[1]["has_error"] is True


def test_error_list_fault_fires_error_event() -> None:
    # A fault that shows up only in the dp_116 error list (has_error false) must
    # still fire an error event (issue #171).
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    _feed(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_RUNNING")
    _fire(ent)
    ent._trigger_event.reset_mock()
    asyncio.run(hub.on_error_list(json.dumps({"error_list": [{"code": 5}]})))
    _fire(ent)
    assert _last_event(ent) == EVENT_ERROR


def test_connection_error_does_not_fire_error_event() -> None:
    # A dropped MQTT connection is routine (mower asleep/docked/DHCP change)
    # and must not fire a spurious error event; only a real device fault does.
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    hub.connection_error = True
    _fire(ent)
    assert _last_event(ent) is None


def test_real_fault_still_fires_after_connection_blip() -> None:
    # A genuine has_error fault must still surface as an error event even after
    # a preceding connection blip that no longer produces one.
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    hub.connection_error = True
    _fire(ent)
    _feed(hub, mission="MISSION_GLOBAL_CLEAN", state="MISSION_STATE_RUNNING", has_error=True)
    _fire(ent)
    assert _last_event(ent) == EVENT_ERROR


# ---------------------------------------------------------------------------
# no-op paths
# ---------------------------------------------------------------------------


def test_no_event_when_phase_unchanged() -> None:
    hub = _hub()
    _feed(hub, mission="MISSION_IDLE", state="MISSION_STATE_IDLE")
    ent = _entity(hub)
    _added(ent)  # seeds "docked" and the shown display fields
    # Re-feeding the identical state changes nothing: no event, no refresh write.
    _feed(hub, mission="MISSION_IDLE", state="MISSION_STATE_IDLE")
    _fire(ent)
    ent._trigger_event.assert_not_called()
    ent.async_write_ha_state.assert_not_called()


# ---------------------------------------------------------------------------
# issue #142: the event entity's sub_mission/state must not freeze on a stale
# "Saving Map" / "Running" after the mower docks and finishes the map upload.
# ---------------------------------------------------------------------------


def test_extra_state_attributes_default_idle_without_activity() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    # A fresh hub sits at idle; the entity mirrors that (never a stale busy state).
    assert ent.extra_state_attributes == {
        "sub_mission": "SUB_MISSION_IDLE",
        "state": "MISSION_STATE_IDLE",
    }


def test_extra_state_attributes_show_save_while_incomplete() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    _feed(
        hub,
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_SAVING_MAP",
        state="MISSION_STATE_RUNNING",
    )
    _feed_dp118(hub, 40)
    # A genuinely in-progress save is still surfaced.
    assert ent.extra_state_attributes == {
        "sub_mission": "SUB_MISSION_SAVING_MAP",
        "state": "MISSION_STATE_RUNNING",
    }


def test_map_save_decay_rewrites_without_new_event() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    ent._last_phase = "mowing"  # force the docked transition to fire once
    _feed(
        hub,
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_SAVING_MAP",
        state="MISSION_STATE_RUNNING",
    )
    _fire(ent)
    assert _last_event(ent) == EVENT_DOCKED
    assert ent.extra_state_attributes["sub_mission"] == "SUB_MISSION_SAVING_MAP"

    ent._trigger_event.reset_mock()
    ent.async_write_ha_state.reset_mock()
    # The upload completes while the mower stays docked: no phase change, so no
    # new event fires -- but the entity must re-write so the stale busy fields
    # decay to idle instead of freezing for hours (issue #142).
    _feed_dp118(hub, 100)
    _fire(ent)
    ent._trigger_event.assert_not_called()
    ent.async_write_ha_state.assert_called_once()
    assert ent.extra_state_attributes == {
        "sub_mission": "SUB_MISSION_IDLE",
        "state": "MISSION_STATE_IDLE",
    }


def test_event_attributes_decay_after_timeout() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    _feed(
        hub,
        mission="MISSION_GLOBAL_CLEAN",
        sub_mission="SUB_MISSION_SAVING_MAP",
        state="MISSION_STATE_RUNNING",
    )
    _fire(ent)
    assert ent.extra_state_attributes["sub_mission"] == "SUB_MISSION_SAVING_MAP"
    # No progress signal ever arrives; the timeout fallback retires it anyway.
    hub._map_save_started_at = time.monotonic() - (MAP_SAVE_DISPLAY_TIMEOUT + 1)
    assert ent.extra_state_attributes == {
        "sub_mission": "SUB_MISSION_IDLE",
        "state": "MISSION_STATE_IDLE",
    }


def test_drain_without_pending_writes_nothing() -> None:
    hub = _hub()
    ent = _entity(hub)
    _added(ent)
    asyncio.run(ent._async_drain_pending())  # empty queue
    ent.async_write_ha_state.assert_not_called()
