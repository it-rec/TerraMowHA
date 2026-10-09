"""Tests for the dp_119 command-acknowledgement channel.

Covers the hub's ack bookkeeping (futures per seq, rejection logging,
diagnostics), the confirmed-command helper ``async_publish_with_ack``, the
confirmed ``terramow.start_select_region`` service path, and the dp_122
app-direction schedule-write capture.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import SERVICE_START_SELECT_REGION
from custom_components.terramow.const import (
    CONF_SERIAL,
    DOMAIN,
)
from custom_components.terramow.hub import TerraMowHub

HOST = "192.0.2.10"
SERIAL = "MP511ACK01"


def _fake_hub_start(self: TerraMowHub) -> None:
    """Start the hub without network: mock client, real callback wiring."""
    client = MagicMock()
    client.is_connected.return_value = True
    client.publish.return_value = MagicMock(rc=0)
    self.mqtt_client = client
    self.register_all_callbacks()


async def setup_terramow(hass: HomeAssistant) -> MockConfigEntry:
    """Set the integration up for real and return the loaded config entry."""
    from homeassistant.const import CONF_HOST, CONF_PASSWORD

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
    return entry


def _push_ack(hub: TerraMowHub, seq: int, code: int) -> None:
    """Deliver a dp_119 ack exactly like the MQTT worker thread would."""
    msg = SimpleNamespace(
        topic="data_point/119/robot",
        payload=json.dumps({"seq": seq, "code": code}).encode(),
    )
    hub.on_mqtt_message(None, None, msg)


async def test_ack_resolves_confirmed_command(hass: HomeAssistant) -> None:
    """A code-0 ack completes async_publish_with_ack with 0."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    task = hass.async_create_task(
        hub.async_publish_with_ack(103, {"seq": 42, "mode": "X"})
    )
    await asyncio.sleep(0)  # let the command publish and park its future
    _push_ack(hub, 42, 0)
    assert await task == 0
    assert hub.last_command_ack == {"dp": 119, "seq": 42, "code": 0}
    assert not hub._pending_acks

    snapshot = hub.diagnostics_snapshot()
    assert snapshot["last_command_ack"] == {"dp": 119, "seq": 42, "code": 0}


async def test_ack_rejection_raises(hass: HomeAssistant) -> None:
    """A non-zero ack code raises a translated HomeAssistantError."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    task = hass.async_create_task(
        hub.async_publish_with_ack(103, {"seq": 43, "mode": "X"})
    )
    await asyncio.sleep(0)
    _push_ack(hub, 43, 7)
    with pytest.raises(HomeAssistantError):
        await task
    assert not hub._pending_acks


async def test_ack_timeout_is_optimistic(hass: HomeAssistant) -> None:
    """No ack within the timeout keeps fire-and-forget semantics (None)."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    result = await hub.async_publish_with_ack(
        103, {"seq": 44, "mode": "X"}, timeout=0.05
    )
    assert result is None
    assert not hub._pending_acks


async def test_publish_failure_cleans_pending(hass: HomeAssistant) -> None:
    """A failed publish propagates and leaves no orphaned future."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    hub.mqtt_client.is_connected.return_value = False
    with pytest.raises(HomeAssistantError):
        await hub.async_publish_with_ack(103, {"seq": 45, "mode": "X"})
    assert not hub._pending_acks


async def test_unsolicited_rejection_is_logged(
    hass: HomeAssistant, caplog: Any
) -> None:
    """A rejected fire-and-forget command shows up as a warning."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    _push_ack(hub, 99, 3)
    await hass.async_block_till_done()
    assert "rejected command seq=99 with code=3 (dp_119)" in caplog.text

    # ...while a code-0 ack stays quiet
    caplog.clear()
    _push_ack(hub, 100, 0)
    await hass.async_block_till_done()
    assert "rejected" not in caplog.text


async def test_ack_for_already_completed_future_is_ignored(
    hass: HomeAssistant,
) -> None:
    """A late ack for an already-resolved future is dropped silently."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    future: asyncio.Future[int] = hass.loop.create_future()
    future.set_result(0)
    hub._pending_acks[77] = future
    _push_ack(hub, 77, 5)
    await hass.async_block_till_done()
    assert 77 not in hub._pending_acks
    assert future.result() == 0  # unchanged


async def test_invalid_ack_payload_is_tolerated(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Garbage on dp_119 logs a warning instead of crashing the handler."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    msg = SimpleNamespace(topic="data_point/119/robot", payload=b"not json")
    hub.on_mqtt_message(None, None, msg)
    await hass.async_block_till_done()
    assert "Invalid dp_119 command ack payload" in caplog.text


async def _call_select_region(
    hass: HomeAssistant, hub: TerraMowHub, ack_code: int
) -> None:
    """Call the service and deliver the device ack while it waits."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "lawn_mower", DOMAIN, f"lawn_mower.terramow@{SERIAL}"
    )
    assert entity_id is not None

    async def _deliver_ack() -> None:
        for _ in range(50):
            await asyncio.sleep(0.01)
            if hub._pending_acks:
                seq = next(iter(hub._pending_acks))
                _push_ack(hub, seq, ack_code)
                return

    hass.async_create_task(_deliver_ack())
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SELECT_REGION,
        {"entity_id": entity_id, "region_ids": [7]},
        blocking=True,
    )


async def test_service_waits_for_ack(hass: HomeAssistant) -> None:
    """The zone service completes once the device acks the command."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    await _call_select_region(hass, hub, ack_code=0)

    topic, payload = hub.mqtt_client.publish.call_args[0][:2]
    assert topic == "data_point/103/app"
    command = json.loads(payload)
    assert command["mode"] == "START_MODE_SELECT_REGION_CLEAN"
    # Outbound schema the firmware acts on (matches select.py); the inbound
    # clean_info uses select_region/region_id, which is a different thing (#140).
    assert command["select_region_clean"]["region_ids"] == [7]


async def test_service_surfaces_rejection(hass: HomeAssistant) -> None:
    """A device rejection reaches the service caller as an error."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    with pytest.raises(HomeAssistantError):
        await _call_select_region(hass, hub, ack_code=9)


async def test_confirmed_select_region_ignores_empty_ids(
    hass: HomeAssistant,
) -> None:
    """An empty region list is a no-op, exactly like the sync variant."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    hub.mqtt_client.publish.reset_mock()
    await hub.async_start_select_region_clean([])
    hub.mqtt_client.publish.assert_not_called()


async def test_app_direction_capture(hass: HomeAssistant) -> None:
    """App-direction traffic on ANY data point is captured with its topic."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    payload = json.dumps({"cmd_type": "SCHEDULE_CMD_TYPE_ADD", "seq": 1})
    msg = SimpleNamespace(topic="data_point/122/app", payload=payload.encode())
    hub.on_mqtt_message(None, None, msg)
    # The schedule channel is not confirmed to be dp_122 — other app-direction
    # data points must land in the same capture.
    msg2 = SimpleNamespace(topic="data_point/121/app", payload=b'{"x": 1}')
    hub.on_mqtt_message(None, None, msg2)

    captures = hub.diagnostics_snapshot()["app_dp_captures"]
    assert [(topic, pl) for _, topic, pl in captures] == [
        ("data_point/122/app", payload),
        ("data_point/121/app", '{"x": 1}'),
    ]


# ---------------------------------------------------------------------------
# Same-dp command replies (dp_103/105/106 ``{seq, ret}``)
# ---------------------------------------------------------------------------


def _push_reply(hub: TerraMowHub, dp_id: int, payload: Any) -> None:
    """Deliver a /robot reply on a control data point like the MQTT worker."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    msg = SimpleNamespace(topic=f"data_point/{dp_id}/robot", payload=raw.encode())
    hub.on_mqtt_message(None, None, msg)


async def _reply_when_pending(
    hub: TerraMowHub, dp_id: int, extra: dict[str, Any]
) -> None:
    """Answer the first parked command on ``dp_id`` with ``extra`` merged in."""
    for _ in range(100):
        await asyncio.sleep(0.01)
        if hub._pending_acks:
            seq = next(iter(hub._pending_acks))
            _push_reply(hub, dp_id, {"seq": seq, **extra})
            return


async def test_same_dp_reply_resolves_confirmed_command(
    hass: HomeAssistant,
) -> None:
    """A dp_103 reply completes the wait; an omitted ret means accepted."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    task = hass.async_create_task(
        hub.async_publish_with_ack(103, {"seq": 50, "mode": "X"})
    )
    await asyncio.sleep(0)
    _push_reply(hub, 103, {"seq": 50})  # protobuf JSON drops ret=0
    assert await task == 0
    assert hub.last_command_ack == {"dp": 103, "seq": 50, "code": 0}
    assert not hub._pending_acks


async def test_start_mowing_service_waits_for_reply(hass: HomeAssistant) -> None:
    """lawn_mower.start_mowing publishes dp_103 and completes on its reply."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    entity_id = er.async_get(hass).async_get_entity_id(
        "lawn_mower", DOMAIN, f"lawn_mower.terramow@{SERIAL}"
    )
    assert entity_id is not None

    hub._last_control_time = 0.0
    hass.async_create_task(_reply_when_pending(hub, 103, {"ret": 0}))
    await hass.services.async_call(
        "lawn_mower", "start_mowing", {"entity_id": entity_id}, blocking=True
    )
    topic, payload = hub.mqtt_client.publish.call_args[0][:2]
    assert topic == "data_point/103/app"
    assert json.loads(payload)["mode"] == "START_MODE_GLOBAL_CLEAN"
    assert hub.last_command_ack["dp"] == 103


async def test_dock_service_surfaces_rejection(hass: HomeAssistant) -> None:
    """A non-zero ret on the command's own dp reaches the caller."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    entity_id = er.async_get(hass).async_get_entity_id(
        "lawn_mower", DOMAIN, f"lawn_mower.terramow@{SERIAL}"
    )
    assert entity_id is not None

    hub._last_control_time = 0.0
    hass.async_create_task(_reply_when_pending(hub, 103, {"ret": 911}))
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "lawn_mower", "dock", {"entity_id": entity_id}, blocking=True
        )
    assert not hub._pending_acks


async def test_confirmed_pause_uses_dp105_reply(hass: HomeAssistant) -> None:
    """Pause is confirmed through dp_105, not dp_119."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    await hub.on_mission_status(
        json.dumps(
            {"mission": "MISSION_GLOBAL_CLEAN", "state": "MISSION_STATE_RUNNING"}
        )
    )
    hub._last_control_time = 0.0
    hass.async_create_task(_reply_when_pending(hub, 105, {"ret": 0}))
    await hub.async_pause()
    topic = hub.mqtt_client.publish.call_args[0][0]
    assert topic == "data_point/105/app"
    assert hub.last_command_ack["dp"] == 105


async def test_confirmed_command_with_nothing_to_send(hass: HomeAssistant) -> None:
    """When the plan is a no-op (pausing an idle mower) nothing is published."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    hub.mqtt_client.publish.reset_mock()
    hub._last_control_time = 0.0
    await hub.async_pause()
    hub.mqtt_client.publish.assert_not_called()
    assert not hub._pending_acks


async def test_unsolicited_reply_rejection_is_logged(
    hass: HomeAssistant, caplog: Any
) -> None:
    """A rejected fire-and-forget command's same-dp reply is a warning."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    _push_reply(hub, 106, {"seq": 123, "ret": 4})
    await hass.async_block_till_done()
    assert "rejected command seq=123 with code=4 (dp_106)" in caplog.text
    assert hub.last_command_ack == {"dp": 106, "seq": 123, "code": 4}


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[1, 2]",
        {"ret": 0},  # no seq: not a command reply
        {"seq": "7", "ret": 0},
        {"seq": 7, "ret": "bad"},
    ],
)
async def test_non_reply_payloads_are_ignored(
    hass: HomeAssistant, payload: Any
) -> None:
    """Anything that isn't ``{seq:int, ret:int}`` leaves acks untouched."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    future: asyncio.Future[int] = hass.loop.create_future()
    hub._pending_acks[7] = future
    _push_reply(hub, 103, payload)
    await hass.async_block_till_done()
    assert not future.done()
    assert hub.last_command_ack == {}
    hub._pending_acks.clear()
