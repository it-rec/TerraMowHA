"""Confirmed maintenance-counter resets (dp_125 / dp_126).

The counters have no command reply: the mower resets on ``int_value: 0`` and
then reports the new value. ``TerraMowHub.async_reset_maintenance_counter``
treats that zero report as the confirmation. These tests pin its boundaries:
only a zero report of the same data point confirms, a missing one times out
with a translated error, a failed publish propagates, and the pending waiter
never outlives the call.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.125", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def _handler(hub: TerraMowHub, dp_id: int):
    return hub.on_base_station_time if dp_id == 125 else hub.on_blade_time


def _answer_with(hub: TerraMowHub, dp_id: int, payload: str) -> None:
    """Make the mocked mower answer every publish with ``payload`` on ``dp_id``."""

    def publish(*_args, **_kwargs):
        loop = asyncio.get_running_loop()
        loop.create_task(_handler(hub, dp_id)(payload))
        return MagicMock(rc=0)

    hub.mqtt_client.publish.side_effect = publish


@pytest.mark.parametrize("dp_id", [125, 126])
def test_zero_report_confirms_the_reset(dp_id: int) -> None:
    hub = _hub()
    _answer_with(hub, dp_id, json.dumps({"int_value": 0}))
    asyncio.run(hub.async_reset_maintenance_counter(dp_id))
    topic, payload = hub.mqtt_client.publish.call_args.args
    assert topic == f"data_point/{dp_id}/app"
    assert json.loads(payload) == {"int_value": 0}
    assert hub._counter_reset_waiters == {}


@pytest.mark.parametrize(
    "payload",
    [
        json.dumps({"int_value": 240}),  # the counter did not reset
        json.dumps([0]),  # not an object
        "not json",
    ],
)
def test_other_reports_do_not_confirm(payload: str) -> None:
    hub = _hub()
    _answer_with(hub, 126, payload)
    with (
        patch("custom_components.terramow.hub.COMMAND_REPLY_TIMEOUT", 0.05),
        pytest.raises(HomeAssistantError) as err,
    ):
        asyncio.run(hub.async_reset_maintenance_counter(126))
    assert err.value.translation_key == "maintenance_reset_unconfirmed"
    assert hub._counter_reset_waiters == {}


def test_zero_report_of_the_other_counter_does_not_confirm() -> None:
    hub = _hub()
    _answer_with(hub, 125, json.dumps({"int_value": 0}))
    with (
        patch("custom_components.terramow.hub.COMMAND_REPLY_TIMEOUT", 0.05),
        pytest.raises(HomeAssistantError),
    ):
        asyncio.run(hub.async_reset_maintenance_counter(126))


def test_unsolicited_zero_report_is_harmless() -> None:
    hub = _hub()
    asyncio.run(hub.on_blade_time(json.dumps({"int_value": 0})))
    assert hub._counter_reset_waiters == {}


def test_failed_publish_propagates_and_clears_the_waiter() -> None:
    hub = _hub()
    hub.mqtt_client.is_connected.return_value = False
    with pytest.raises(HomeAssistantError) as err:
        asyncio.run(hub.async_reset_maintenance_counter(125))
    assert err.value.translation_key == "command_not_delivered"
    assert hub._counter_reset_waiters == {}


def test_overlapping_resets_keep_the_newer_waiter() -> None:
    # A second press while the first still waits takes over the slot; the
    # first one's cleanup must not remove the newer waiter.
    hub = _hub()

    async def main() -> None:
        with patch("custom_components.terramow.hub.COMMAND_REPLY_TIMEOUT", 0.05):
            first = asyncio.create_task(hub.async_reset_maintenance_counter(126))
            await asyncio.sleep(0)
        # the second press gets the normal timeout, so it outlives the first
        with patch("custom_components.terramow.hub.COMMAND_REPLY_TIMEOUT", 5):
            second = asyncio.create_task(hub.async_reset_maintenance_counter(126))
            await asyncio.sleep(0)
            newer = hub._counter_reset_waiters[126]
            with pytest.raises(HomeAssistantError):
                await first
            assert hub._counter_reset_waiters[126] is newer
            await hub.on_blade_time(json.dumps({"int_value": 0}))
            await second
        assert hub._counter_reset_waiters == {}

    asyncio.run(main())
