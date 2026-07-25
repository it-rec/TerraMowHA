"""Tests for the dp_152 actuators: the illumination light and the defogger.

Both go through the same verified write negotiation as the dp_150 settings,
with one deliberate difference: dp_152 also carries device-computed state
(sunrise, sunset, manual-mapping flags), so the block is never echoed back
wholesale — there is no merged-block candidate.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import ENVIRONMENT_INFO_DP
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.light import (
    IlluminationLight,
    async_setup_entry as light_setup,
)
from custom_components.terramow.switch import ADVANCED_SWITCHES, AdvancedSettingSwitch

HOST = "192.0.2.10"

# The dp_152 block as the reference device reports it: two actuators plus
# read-only state that must never be written back.
ENVIRONMENT: dict[str, Any] = {
    "is_defogger_heating": False,
    "is_illuminate_light_on": False,
    "sunrise": {"hour": 5, "minute": 29},
    "sunset": {"hour": 21, "minute": 12},
    "is_not_in_daylight_period": False,
    "manual_mapping": {"need_relocation": False},
}


class FakeDevice:
    """Scripted mower for dp_152 writes."""

    def __init__(self, hub: TerraMowHub, accept: set[str] | None = None) -> None:
        self.hub = hub
        self.accept = accept if accept is not None else {"nested_field"}
        self.attempts: list[dict[str, Any]] = []
        self.environment = json.loads(json.dumps(ENVIRONMENT))
        hub.mqtt_client.publish.side_effect = self._on_publish

    def _deliver(self, dp_id: int, payload: dict[str, Any]) -> None:
        self.hub.on_mqtt_message(
            None,
            None,
            SimpleNamespace(
                topic=f"data_point/{dp_id}/robot",
                payload=json.dumps(payload).encode(),
            ),
        )

    def _on_publish(self, topic: str, payload: str, qos: int = 0) -> MagicMock:
        if topic == f"data_point/{ENVIRONMENT_INFO_DP}/app":
            data = json.loads(payload)
            self.attempts.append(data)
            label = (
                "wrapped_field" if "environment_setting" in data else "nested_field"
            )
            self._deliver(119, {"seq": data["seq"], "code": 0})
            if label in self.accept:
                applied = dict(data)
                applied.pop("seq")
                if label == "wrapped_field":
                    applied = applied["environment_setting"]
                self.environment = TerraMowHub._deep_merge(self.environment, applied)
                self._deliver(ENVIRONMENT_INFO_DP, self.environment)
        return MagicMock(rc=0)


@pytest.fixture(name="hub")
async def hub_fixture(hass: HomeAssistant) -> AsyncGenerator[TerraMowHub]:
    """A hub with the dp_152 block loaded and short write timeouts."""
    basic_data = TerraMowBasicData(host=HOST, password="secret")
    hub = TerraMowHub(basic_data, hass)
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value = MagicMock(rc=0)
    hub.register_all_callbacks()
    hub._control_interval = 0.0
    await hub.on_environment_info(json.dumps(ENVIRONMENT))
    with (
        patch("custom_components.terramow.hub.ADVANCED_SETTING_VERIFY_TIMEOUT", 0.05),
        patch("custom_components.terramow.hub.COMMAND_ACK_TIMEOUT", 0.05),
    ):
        yield hub


def _defogger(hub: TerraMowHub) -> AdvancedSettingSwitch:
    (description,) = [d for d in ADVANCED_SWITCHES if d.key == "defogger_heating"]
    return AdvancedSettingSwitch(hub.basic_data, hub.hass, description)


# ---------------------------------------------------------------------------
# candidate shapes
# ---------------------------------------------------------------------------


async def test_environment_writes_never_echo_the_whole_block(
    hub: TerraMowHub,
) -> None:
    """dp_152 carries sunrise/sunset/mapping state — never write it back."""
    device = FakeDevice(hub, accept=set())

    with pytest.raises(HomeAssistantError):
        await hub.async_write_environment_setting(("is_illuminate_light_on",), True)

    assert device.attempts, "no write was attempted"
    for attempt in device.attempts:
        assert "sunrise" not in attempt
        assert "sunset" not in attempt
        assert "manual_mapping" not in attempt
    # Only the narrow shapes are offered, in order.
    assert [set(a) - {"seq"} for a in device.attempts] == [
        {"is_illuminate_light_on"},
        {"environment_setting"},
    ]


async def test_environment_write_falls_through_to_the_wrapped_shape(
    hub: TerraMowHub,
) -> None:
    device = FakeDevice(hub, accept={"wrapped_field"})

    await hub.async_write_environment_setting(("is_illuminate_light_on",), True)

    assert len(device.attempts) == 2
    assert hub.environment_info["is_illuminate_light_on"] is True


async def test_advanced_writes_still_offer_the_merged_block(
    hub: TerraMowHub,
) -> None:
    """The dp_150 path is unchanged by the generalisation."""
    candidates = hub._setting_candidates(
        150,
        ("enable_cliff_detection", "value"),
        True,
        allow_merged=True,
        wrapper_key="advanced_setting",
    )
    assert [label for label, _ in candidates] == [
        "merged_block",
        "nested_field",
        "flat_field",
        "wrapped_field",
    ]


async def test_proven_shape_is_remembered_per_data_point(hub: TerraMowHub) -> None:
    """dp_150 and dp_152 negotiate independently."""
    FakeDevice(hub, accept={"wrapped_field"})
    await hub.async_write_environment_setting(("is_illuminate_light_on",), True)

    assert hub._setting_write_field == {ENVIRONMENT_INFO_DP: "wrapped_field"}


def test_setting_block_falls_back_to_the_advanced_settings(hass: HomeAssistant) -> None:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    assert hub.setting_block(ENVIRONMENT_INFO_DP) is hub.environment_info
    assert hub.setting_block(150) is hub.advanced_settings


# ---------------------------------------------------------------------------
# light entity
# ---------------------------------------------------------------------------


async def test_light_setup_creates_one_entity(hub: TerraMowHub) -> None:
    added: list[Any] = []
    entry = SimpleNamespace(entry_id="e1", runtime_data=hub.basic_data)
    await light_setup(hub.hass, entry, added.extend)  # type: ignore[arg-type]
    assert len(added) == 1
    assert isinstance(added[0], IlluminationLight)


async def test_light_reports_onoff_only(hub: TerraMowHub) -> None:
    light = IlluminationLight(hub.basic_data, hub.hass)
    assert light.color_mode is ColorMode.ONOFF
    assert light.supported_color_modes == {ColorMode.ONOFF}


async def test_light_reads_the_reported_flag(hub: TerraMowHub) -> None:
    light = IlluminationLight(hub.basic_data, hub.hass)
    assert light.is_on is False

    await hub.on_environment_info(json.dumps({"is_illuminate_light_on": True}))
    assert light.is_on is True


async def test_light_reports_unknown_without_data(hass: HomeAssistant) -> None:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    light = IlluminationLight(hub.basic_data, hass)
    assert light.is_on is None

    await hub.on_environment_info(json.dumps({"something_else": 1}))
    assert light.is_on is None

    hub.basic_data.lawn_mower = None
    assert light.is_on is None


async def test_light_turn_on_and_off(hub: TerraMowHub) -> None:
    FakeDevice(hub)
    light = IlluminationLight(hub.basic_data, hub.hass)

    await light.async_turn_on()
    assert light.is_on is True

    await light.async_turn_off()
    assert light.is_on is False


async def test_light_raises_when_the_firmware_ignores_the_write(
    hub: TerraMowHub,
) -> None:
    FakeDevice(hub, accept=set())
    light = IlluminationLight(hub.basic_data, hub.hass)

    with pytest.raises(HomeAssistantError) as err:
        await light.async_turn_on()
    assert err.value.translation_key == "advanced_setting_write_failed"
    assert light.is_on is False


async def test_light_without_a_hub_does_not_write(hub: TerraMowHub) -> None:
    light = IlluminationLight(hub.basic_data, hub.hass)
    hub.basic_data.lawn_mower = None
    await light.async_turn_on()  # logs an error instead of raising
    hub.mqtt_client.publish.assert_not_called()


# ---------------------------------------------------------------------------
# defogger switch
# ---------------------------------------------------------------------------


async def test_defogger_switch_reads_and_writes_dp_152(hub: TerraMowHub) -> None:
    FakeDevice(hub)
    switch = _defogger(hub)

    assert switch.is_on is False
    assert switch._push_dp_ids == (ENVIRONMENT_INFO_DP,)

    await switch.async_turn_on()
    assert switch.is_on is True
    assert hub.environment_info["is_defogger_heating"] is True

    await switch.async_turn_off()
    assert switch.is_on is False


async def test_defogger_switch_is_unknown_without_data(hass: HomeAssistant) -> None:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    switch = _defogger(hub)
    assert switch.is_on is None
