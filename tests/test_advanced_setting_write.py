"""Tests for the writable dp_150 advanced settings.

The write format is undocumented, so the hub negotiates: each candidate
payload shape is judged by its dp_119 ack and verified against the device's
own follow-up dp_150 report. These tests drive that loop with a scripted fake
device, and pin the behaviour on firmware that ignores the writes entirely.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.number import (
    AfterRainResumeDelayNumber,
    RainSensorThresholdNumber,
)
from custom_components.terramow.switch import ADVANCED_SWITCHES, AdvancedSettingSwitch

HOST = "192.0.2.10"

# The dp_150 block as the reference device reports it.
REPORTED: dict[str, Any] = {
    "enable_cliff_detection": {"value": True},
    "enable_slope_detection": {"value": False},
    "rain_sensor_threshold": {"upper_limit": 1000},
    "after_rain_stop_setting": {
        "enable_auto_resume": False,
        "auto_resume_delay_time": {"hours": 2, "minutes": 0},
    },
}


def _label(payload: dict[str, Any]) -> str:
    """Mirror the hub's candidate labels from a write payload."""
    fields = [key for key in payload if key != "seq"]
    if "advanced_setting" in fields:
        return "wrapped_field"
    if len(fields) > 1:
        return "merged_block"
    (field,) = fields
    node = payload[field]
    if isinstance(node, dict) and set(node) & {"value"}:
        return "nested_field"
    if isinstance(node, dict):
        return "nested_field"
    return "flat_field"


class FakeDevice:
    """Scripted mower: acks dp_150 writes and reports accepted ones back.

    ``accept`` is the set of candidate labels the firmware actually applies;
    everything else is acked (or silently dropped, per ``ack``) without
    changing the reported block — exactly how the dp_122 schedule writes
    behave on current firmware.
    """

    def __init__(
        self,
        hub: TerraMowHub,
        accept: set[str] | None = None,
        ack: dict[str, int | None] | None = None,
    ) -> None:
        self.hub = hub
        self.accept = accept if accept is not None else {"merged_block"}
        self.ack = ack or {}
        self.attempts: list[tuple[str, dict[str, Any]]] = []
        self.settings = json.loads(json.dumps(REPORTED))
        hub.mqtt_client.publish.side_effect = self._on_publish

    def _deliver(self, dp_id: int, payload: dict[str, Any]) -> None:
        msg = SimpleNamespace(
            topic=f"data_point/{dp_id}/robot",
            payload=json.dumps(payload).encode(),
        )
        self.hub.on_mqtt_message(None, None, msg)

    def _on_publish(self, topic: str, payload: str, qos: int = 0) -> MagicMock:
        if topic == "data_point/150/app":
            data = json.loads(payload)
            label = _label(data)
            self.attempts.append((label, data))
            code = self.ack.get(label, 0)
            if code is not None:
                self._deliver(119, {"seq": data["seq"], "code": code})
            # ``None`` models the firmware that never acks this integration's
            # commands (V1000 fw28) — it can still apply the write.
            if code in (0, None) and label in self.accept:
                applied = dict(data)
                applied.pop("seq")
                if label == "wrapped_field":
                    applied = applied["advanced_setting"]
                if label == "flat_field":
                    # However the write is phrased, the device reports its own
                    # canonical shape back: the scalar stays wrapped in
                    # ``{"value": ...}``.
                    applied = {key: {"value": val} for key, val in applied.items()}
                self.settings = TerraMowHub._deep_merge(self.settings, applied)
                self._deliver(150, self.settings)
        return MagicMock(rc=0)


@pytest.fixture(name="hub")
async def hub_fixture(hass: HomeAssistant) -> AsyncGenerator[TerraMowHub]:
    """A hub wired to a mocked MQTT client, with the dp_150 block loaded.

    The verify window is shortened so the "device ignores the write" paths
    don't spend the real timeout per candidate, and the command rate limiter
    is disabled so a test can write twice in a row (it has its own test).
    """
    basic_data = TerraMowBasicData(host=HOST, password="secret")
    hub = TerraMowHub(basic_data, hass)
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value = MagicMock(rc=0)
    hub.register_all_callbacks()
    hub._control_interval = 0.0
    await hub.on_advanced_settings(json.dumps(REPORTED))
    with (
        patch("custom_components.terramow.hub.ADVANCED_SETTING_VERIFY_TIMEOUT", 0.05),
        patch("custom_components.terramow.hub.COMMAND_ACK_TIMEOUT", 0.05),
    ):
        yield hub


# ---------------------------------------------------------------------------
# hub-level negotiation
# ---------------------------------------------------------------------------


async def test_write_succeeds_with_the_merged_block(hub: TerraMowHub) -> None:
    """The safest shape is tried first and is enough on a cooperative device."""
    device = FakeDevice(hub)

    await hub.async_write_advanced_setting(("enable_slope_detection", "value"), True)

    assert [label for label, _ in device.attempts] == ["merged_block"]
    # The merged candidate echoes the whole block, so nothing else is lost.
    assert device.settings["enable_cliff_detection"] == {"value": True}
    assert device.settings["enable_slope_detection"] == {"value": True}
    assert hub.advanced_settings["enable_slope_detection"] == {"value": True}


async def test_write_falls_through_to_a_narrower_shape(hub: TerraMowHub) -> None:
    """A firmware that only accepts the bare nested field still gets written."""
    device = FakeDevice(hub, accept={"nested_field"})

    await hub.async_write_advanced_setting(("enable_slope_detection", "value"), True)

    assert [label for label, _ in device.attempts] == ["merged_block", "nested_field"]
    assert hub.advanced_settings["enable_slope_detection"] == {"value": True}


async def test_proven_shape_is_tried_first_next_time(hub: TerraMowHub) -> None:
    """The negotiated shape is remembered, so later writes go straight there."""
    device = FakeDevice(hub, accept={"nested_field"})
    await hub.async_write_advanced_setting(("enable_slope_detection", "value"), True)
    device.attempts.clear()

    await hub.async_write_advanced_setting(("enable_slope_detection", "value"), False)

    assert device.attempts[0][0] == "nested_field"


async def test_rejected_candidate_is_skipped(hub: TerraMowHub) -> None:
    """A non-zero ack is a clean rejection: move on without waiting."""
    device = FakeDevice(hub, accept={"nested_field"}, ack={"merged_block": 7})

    await hub.async_write_advanced_setting(("enable_slope_detection", "value"), True)

    assert [label for label, _ in device.attempts] == ["merged_block", "nested_field"]


async def test_flat_shape_is_offered_for_value_wrapped_settings(
    hub: TerraMowHub,
) -> None:
    """``{"enable_x": true}`` is tried when the device's scalar wrapper fails."""
    device = FakeDevice(hub, accept={"flat_field"})

    await hub.async_write_advanced_setting(("enable_slope_detection", "value"), True)

    labels = [label for label, _ in device.attempts]
    assert labels == ["merged_block", "nested_field", "flat_field"]
    # The device answers in its canonical wrapped shape either way.
    assert device.settings["enable_slope_detection"] == {"value": True}


async def test_wrapped_shape_is_the_last_resort(hub: TerraMowHub) -> None:
    device = FakeDevice(hub, accept={"wrapped_field"})

    await hub.async_write_advanced_setting(
        ("after_rain_stop_setting", "enable_auto_resume"), True
    )

    labels = [label for label, _ in device.attempts]
    # No "value" leaf here, so the flat variant is not offered.
    assert labels == ["merged_block", "nested_field", "wrapped_field"]


async def test_write_raises_when_the_device_ignores_every_shape(
    hub: TerraMowHub,
) -> None:
    """The expected outcome on firmware without local dp_150 writes."""
    device = FakeDevice(hub, accept=set())

    with pytest.raises(HomeAssistantError) as err:
        await hub.async_write_advanced_setting(
            ("enable_slope_detection", "value"), True
        )

    assert err.value.translation_key == "advanced_setting_write_failed"
    placeholders = err.value.translation_placeholders or {}
    assert placeholders["setting"] == "enable_slope_detection.value"
    # Every candidate is named in the error, so the log shows what was tried.
    for label, _ in device.attempts:
        assert label in placeholders["attempts"]
    # The device's own report is untouched.
    assert hub.advanced_settings["enable_slope_detection"] == {"value": False}


async def test_write_without_ack_still_verifies_by_report(hub: TerraMowHub) -> None:
    """Current firmware never acks; the follow-up report is the only judge."""
    device = FakeDevice(hub, accept={"merged_block"}, ack={"merged_block": None})

    await hub.async_write_advanced_setting(("enable_slope_detection", "value"), True)

    assert device.attempts[0][0] == "merged_block"
    assert hub.advanced_settings["enable_slope_detection"] == {"value": True}


async def test_write_of_the_value_already_in_effect_is_a_no_op(
    hub: TerraMowHub,
) -> None:
    """Requesting the current value verifies from the cache, without a report."""
    device = FakeDevice(hub, accept=set())

    await hub.async_write_advanced_setting(("enable_cliff_detection", "value"), True)

    assert [label for label, _ in device.attempts] == ["merged_block"]


async def test_verification_ignores_unrelated_and_malformed_reports(
    hub: TerraMowHub,
) -> None:
    """Only a report carrying the requested value ends the wait."""
    path = ("enable_slope_detection", "value")

    task = asyncio.create_task(hub._async_await_setting(150, path, True, timeout=5))
    await asyncio.sleep(0)  # let the wait register its callback

    # Drive the wait's own callback directly: delivering through the MQTT
    # dispatcher would leave the ordering to the scheduler, and this test is
    # about what each payload does, not about when it arrives.
    on_settings = hub.callbacks[150][-1]
    for payload in ("not json", '["list"]', json.dumps({"other": 1})):
        await on_settings(payload)
    assert not task.done()

    match = json.dumps({"enable_slope_detection": {"value": True}})
    await on_settings(match)
    # A second report finds the wait already settled and must not raise.
    await on_settings(match)

    assert await task


async def test_verification_times_out_without_a_matching_report(
    hub: TerraMowHub,
) -> None:
    assert not await hub._async_await_setting(
        150, ("enable_slope_detection", "value"), True, timeout=0.01
    )


async def test_write_is_rate_limited_like_every_other_command(
    hub: TerraMowHub,
) -> None:
    FakeDevice(hub)
    hub._can_accept_command = MagicMock(return_value=False)  # type: ignore[method-assign]

    with pytest.raises(HomeAssistantError) as err:
        await hub.async_write_advanced_setting(
            ("enable_slope_detection", "value"), True
        )
    assert err.value.translation_key == "command_rate_limited"


# ---------------------------------------------------------------------------
# value matching (protobuf-JSON omits defaults)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reported", "expected", "matches"),
    [
        (True, True, True),
        (False, True, False),
        (None, False, True),  # omitted default satisfies a falsy request
        (None, 0, True),
        (None, True, False),
        (1000, 1000, True),
        ({"hours": 2}, {"hours": 2, "minutes": 0}, True),  # minutes omitted
        ({"hours": 2, "minutes": 30}, {"hours": 2, "minutes": 0}, False),
        ("scalar", {"hours": 0}, True),  # non-dict report, all-falsy request
    ],
)
def test_setting_value_matches(reported: Any, expected: Any, matches: bool) -> None:
    assert TerraMowHub.setting_value_matches(reported, expected) is matches


def test_resolve_setting_walks_missing_nodes() -> None:
    assert TerraMowHub.resolve_setting(REPORTED, ("nope", "value")) is None
    assert (
        TerraMowHub.resolve_setting(
            REPORTED, ("rain_sensor_threshold", "upper_limit", "deeper")
        )
        is None
    )


# ---------------------------------------------------------------------------
# entities
# ---------------------------------------------------------------------------


def _switch(hub: TerraMowHub, key: str) -> AdvancedSettingSwitch:
    (description,) = [d for d in ADVANCED_SWITCHES if d.key == key]
    return AdvancedSettingSwitch(hub.basic_data, hub.hass, description)


async def test_switch_reads_the_reported_flag(hub: TerraMowHub) -> None:
    assert _switch(hub, "cliff_detection").is_on is True
    assert _switch(hub, "slope_detection").is_on is False
    assert _switch(hub, "after_rain_auto_resume").is_on is False


async def test_switch_reports_unknown_without_data(hass: HomeAssistant) -> None:
    basic_data = TerraMowBasicData(host=HOST, password="secret")
    hub = TerraMowHub(basic_data, hass)
    switch = _switch(hub, "cliff_detection")
    assert switch.is_on is None

    # A block that does not carry the flag at all is also "unknown".
    await hub.on_advanced_settings(json.dumps({"something_else": 1}))
    assert switch.is_on is None

    basic_data.lawn_mower = None
    assert switch.is_on is None


async def test_switch_turn_on_and_off_write_through(hub: TerraMowHub) -> None:
    FakeDevice(hub)
    switch = _switch(hub, "slope_detection")

    await switch.async_turn_on()
    assert switch.is_on is True

    await switch.async_turn_off()
    assert switch.is_on is False


async def test_switch_without_a_hub_does_not_write(hub: TerraMowHub) -> None:
    switch = _switch(hub, "slope_detection")
    hub.basic_data.lawn_mower = None
    await switch.async_turn_on()  # logs and returns
    hub.mqtt_client.publish.assert_not_called()


async def test_switch_unique_ids_are_distinct_from_the_binary_sensors(
    hub: TerraMowHub,
) -> None:
    suffixes = {_switch(hub, d.key).unique_id for d in ADVANCED_SWITCHES}
    assert len(suffixes) == len(ADVANCED_SWITCHES)
    assert all(".setting_" in uid for uid in suffixes)


async def test_rain_threshold_number_round_trip(hub: TerraMowHub) -> None:
    FakeDevice(hub)
    number = RainSensorThresholdNumber(hub.basic_data, hub.hass)

    assert number.native_value == 1000.0

    await number.async_set_native_value(1500)
    assert number.native_value == 1500.0


async def test_rain_threshold_number_clamps_and_guards(hub: TerraMowHub) -> None:
    number = RainSensorThresholdNumber(hub.basic_data, hub.hass)

    await hub.on_advanced_settings(json.dumps({"rain_sensor_threshold": {"upper_limit": 99999}}))
    assert number.native_value == 4095.0

    await hub.on_advanced_settings(json.dumps({"rain_sensor_threshold": {"upper_limit": True}}))
    assert number.native_value is None

    await hub.on_advanced_settings(json.dumps({}))
    assert number.native_value is None

    hub.basic_data.lawn_mower = None
    assert number.native_value is None


async def test_resume_delay_number_converts_hours_and_minutes(
    hub: TerraMowHub,
) -> None:
    FakeDevice(hub)
    number = AfterRainResumeDelayNumber(hub.basic_data, hub.hass)

    assert number.native_value == 120.0

    await number.async_set_native_value(195)
    assert hub.advanced_settings["after_rain_stop_setting"][
        "auto_resume_delay_time"
    ] == {"hours": 3, "minutes": 15}
    assert number.native_value == 195.0


async def test_resume_delay_number_handles_partial_reports(hub: TerraMowHub) -> None:
    number = AfterRainResumeDelayNumber(hub.basic_data, hub.hass)

    await hub.on_advanced_settings(
        json.dumps({"after_rain_stop_setting": {"auto_resume_delay_time": {"hours": 1}}})
    )
    assert number.native_value == 60.0

    await hub.on_advanced_settings(
        json.dumps(
            {
                "after_rain_stop_setting": {
                    "auto_resume_delay_time": {"hours": True, "minutes": "x"}
                }
            }
        )
    )
    assert number.native_value == 0.0

    await hub.on_advanced_settings(json.dumps({"after_rain_stop_setting": {}}))
    assert number.native_value is None


async def test_number_without_a_hub_does_not_write(hub: TerraMowHub) -> None:
    number = RainSensorThresholdNumber(hub.basic_data, hub.hass)
    hub.basic_data.lawn_mower = None
    await number.async_set_native_value(1200)
    hub.mqtt_client.publish.assert_not_called()
