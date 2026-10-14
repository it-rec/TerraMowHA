"""Tests for the schedule master / weekday switches (dp_122 Schedule Control).

The switches mirror the device's own ``schedule_list`` report: every change
waits for its own dp_122 reply (seq + cmd_type) and is then confirmed by a
fresh GET. These tests drive the hub and the switch entities against a
scripted fake device and pin each boundary: capability gate, unknown-until-
read, reply matching, rejection/timeout/ignored writes, frequency mode and
other-client changes.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow.const import CONF_SERIAL, DOMAIN
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.switch import ScheduleSwitch, ScheduleWeekdaySwitch

HOST = "192.0.2.11"
SERIAL = "MP511SSW01"
MASTER = "switch.terramow_schedule"
MONDAY = "switch.terramow_monday_schedule"

SET_GLOBAL = "SCHEDULE_CMD_TYPE_SET_GLOBAL_DISABLED"
SET_DAYS = "SCHEDULE_CMD_TYPE_SET_DISABLED_WEEK_DAYS"
GET = "SCHEDULE_CMD_TYPE_GET"


def _fake_hub_start(self: TerraMowHub) -> None:
    client = MagicMock()
    client.is_connected.return_value = True
    client.publish.return_value = MagicMock(rc=0)
    self.mqtt_client = client
    self.register_all_callbacks()


async def setup_terramow(hass: HomeAssistant) -> TerraMowHub:
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
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    return hub


class FakeDevice:
    """Scripted mower answering dp_122 GET / SET requests.

    GET replies omit ``cmd_type`` and ``code`` (their protobuf zero values)
    and omit default-false / empty fields, exactly like the device.
    """

    def __init__(self, hub: TerraMowHub, schedule_version: Any = 5) -> None:
        self.hub = hub
        self.global_disabled = False
        self.disabled_days: set[str] = set()
        self.schedule_mode: str | None = None
        self.set_code = 0
        self.apply_sets = True
        self.answer_sets = True
        self.answer_gets = True
        self.duplicate_replies = False
        self.requests: list[dict[str, Any]] = []
        hub.basic_data.firmware_version = {"module": {"schedule": schedule_version}}
        hub._last_control_time -= 10  # step past the command rate limiter
        hub.mqtt_client.publish.side_effect = self._on_publish

    def reply(self, payload: Any) -> None:
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        msg = SimpleNamespace(topic="data_point/122/robot", payload=raw.encode())
        self.hub.on_mqtt_message(None, None, msg)

    def _send(self, payload: dict[str, Any]) -> None:
        self.reply(payload)
        if self.duplicate_replies:
            self.reply(payload)

    def schedule_list(self) -> dict[str, Any]:
        data: dict[str, Any] = {"items": []}
        if self.global_disabled:
            data["global_disabled"] = True
        if self.disabled_days:
            data["disabled_week_days"] = sorted(self.disabled_days)
        if self.schedule_mode is not None:
            data["schedule_mode"] = self.schedule_mode
        return data

    def _on_publish(self, topic: str, payload: str, qos: int = 0) -> MagicMock:
        if topic != "data_point/122/app":
            return MagicMock(rc=0)
        data = json.loads(payload)
        self.requests.append(data)
        cmd, seq = data["cmd_type"], data["seq"]
        if cmd == GET:
            if self.answer_gets:
                self._send({"seq": seq, "schedule_list": self.schedule_list()})
            return MagicMock(rc=0)
        if self.set_code == 0 and self.apply_sets:
            if cmd == SET_GLOBAL:
                self.global_disabled = data["set_global_disabled_param"][
                    "global_disabled"
                ]
            else:
                param = data["set_disabled_week_days_param"]
                if param["disabled"]:
                    self.disabled_days.add(param["week_day"])
                else:
                    self.disabled_days.discard(param["week_day"])
        if self.answer_sets:
            reply: dict[str, Any] = {"cmd_type": cmd, "seq": seq}
            if self.set_code:
                reply["code"] = self.set_code
            self._send(reply)
        return MagicMock(rc=0)

    @property
    def commands(self) -> list[str]:
        return [request["cmd_type"] for request in self.requests]


@pytest.fixture
def short_timeout():
    with patch("custom_components.terramow.hub.COMMAND_REPLY_TIMEOUT", 0.05):
        yield


# ---------------------------------------------------------------------------
# hub: capability gate and raw state mirror
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "expected_version", "supported"),
    [(5, 5, True), ("2", 2, True), (1, 1, False), ("x", None, False), (None, None, False)],
)
async def test_schedule_switch_capability_gate(
    hass: HomeAssistant, version: Any, expected_version: int | None, supported: bool
) -> None:
    hub = await setup_terramow(hass)
    FakeDevice(hub, schedule_version=version)
    assert hub.schedule_module_version == expected_version
    assert hub.schedule_switch_supported is supported


async def test_schedule_state_unknown_until_read(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    assert hub.schedule_enabled is None
    assert hub.schedule_weekday_enabled("WEEK_DAY_MONDAY") is None
    assert hub.schedule_weekdays_configurable is False

    # An all-default (empty) list still counts as read: everything enabled.
    device.reply({"seq": 1, "schedule_list": {}})
    await hass.async_block_till_done()
    assert hub.schedule_enabled is True
    assert hub.schedule_weekday_enabled("WEEK_DAY_MONDAY") is True
    assert hub.schedule_weekdays_configurable is True


async def test_schedule_state_mirrors_report(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    device.reply(
        {
            "schedule_list": {
                "global_disabled": True,
                "disabled_week_days": ["WEEK_DAY_MONDAY"],
            }
        }
    )
    await hass.async_block_till_done()
    assert hub.schedule_enabled is False
    assert hub.schedule_weekday_enabled("WEEK_DAY_MONDAY") is False
    assert hub.schedule_weekday_enabled("WEEK_DAY_TUESDAY") is True

    # Malformed fields are unknown rather than guessed.
    device.reply(
        {"schedule_list": {"global_disabled": "yes", "disabled_week_days": ["X"]}}
    )
    await hass.async_block_till_done()
    assert hub.schedule_enabled is None
    assert hub.schedule_weekday_enabled("WEEK_DAY_MONDAY") is None
    assert hub.schedule_weekdays_configurable is False

    # Frequency schedules ignore the weekday list.
    device.reply({"schedule_list": {"schedule_mode": "SCHEDULE_MODE_FREQUENCY"}})
    await hass.async_block_till_done()
    assert hub.schedule_weekday_enabled("WEEK_DAY_MONDAY") is True
    assert hub.schedule_weekdays_configurable is False


# ---------------------------------------------------------------------------
# hub: writes
# ---------------------------------------------------------------------------


async def test_set_schedule_enabled_confirmed(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    device.duplicate_replies = True  # a repeated reply is ignored

    await hub.async_set_schedule_enabled(False)
    assert device.commands == [SET_GLOBAL, GET]
    assert device.requests[0]["set_global_disabled_param"] == {"global_disabled": True}
    assert 0 < device.requests[0]["seq"] <= 0x7FFFFFFF
    assert hub.schedule_enabled is False
    await hass.async_block_till_done()
    # Our own SET reply did not trigger an extra GET.
    assert device.commands == [SET_GLOBAL, GET]
    assert hub._schedule_own_seqs == set()

    hub._last_control_time -= 10
    await hub.async_set_schedule_enabled(True)
    assert device.global_disabled is False
    assert hub.schedule_enabled is True


async def test_set_schedule_unsupported_firmware(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub, schedule_version=1)
    with pytest.raises(ServiceValidationError) as err:
        await hub.async_set_schedule_enabled(False)
    assert err.value.translation_key == "schedule_switch_unsupported"
    assert err.value.translation_placeholders == {"schedule_version": "1"}
    assert device.requests == []


async def test_set_schedule_rate_limited(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    await hub.async_set_schedule_enabled(False)
    with pytest.raises(HomeAssistantError) as err:
        await hub.async_set_schedule_enabled(True)
    assert err.value.translation_key == "command_rate_limited"
    assert device.commands == [SET_GLOBAL, GET]


async def test_set_schedule_rejected_still_rereads(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    device.set_code = 7
    with pytest.raises(HomeAssistantError) as err:
        await hub.async_set_schedule_enabled(False)
    assert err.value.translation_key == "command_rejected"
    assert err.value.translation_placeholders == {"code": "7"}
    assert device.commands == [SET_GLOBAL, GET]
    assert hub.schedule_enabled is True


async def test_set_schedule_lost_reply_rereads(
    hass: HomeAssistant, short_timeout: None
) -> None:
    """A SET whose reply is lost may have applied: the GET shows the truth."""
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    device.answer_sets = False
    with pytest.raises(HomeAssistantError) as err:
        await hub.async_set_schedule_enabled(False)
    assert err.value.translation_key == "schedule_switch_unconfirmed"
    assert device.commands == [SET_GLOBAL, GET]
    assert hub.schedule_enabled is False  # applied despite the lost reply
    assert hub._schedule_own_seqs == set()


async def test_set_schedule_no_get_reply(
    hass: HomeAssistant, short_timeout: None
) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    device.answer_gets = False
    with pytest.raises(HomeAssistantError) as err:
        await hub.async_set_schedule_enabled(False)
    assert err.value.translation_key == "schedule_switch_unconfirmed"


async def test_set_schedule_ignored_by_device(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    device.apply_sets = False
    with pytest.raises(HomeAssistantError) as err:
        await hub.async_set_schedule_enabled(False)
    assert err.value.translation_key == "schedule_switch_unconfirmed"
    assert hub.schedule_enabled is True


async def test_reply_matching_ignores_foreign_payloads(
    hass: HomeAssistant, short_timeout: None
) -> None:
    """Non-JSON, non-dict, wrong-seq and wrong-cmd replies never resolve."""
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    device.answer_sets = False
    device.answer_gets = False

    original = device._on_publish

    def _noise(topic: str, payload: str, qos: int = 0) -> MagicMock:
        result = original(topic, payload, qos)
        seq = json.loads(payload)["seq"]
        device.reply("not json")
        device.reply("[1]")
        device.reply({"cmd_type": SET_GLOBAL, "seq": seq + 1})
        device.reply({"cmd_type": SET_DAYS, "seq": seq, "code": 3})
        return result

    hub.mqtt_client.publish.side_effect = _noise
    with pytest.raises(HomeAssistantError) as err:
        await hub.async_set_schedule_enabled(False)
    assert err.value.translation_key == "schedule_switch_unconfirmed"


async def test_set_weekday_confirmed(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    device.reply({"schedule_list": {}})
    await hass.async_block_till_done()

    await hub.async_set_schedule_weekday_enabled("WEEK_DAY_MONDAY", False)
    assert device.commands == [SET_DAYS, GET]
    assert device.requests[0]["set_disabled_week_days_param"] == {
        "week_day": "WEEK_DAY_MONDAY",
        "disabled": True,
    }
    assert hub.schedule_weekday_enabled("WEEK_DAY_MONDAY") is False
    # The master switch is untouched by a weekday change.
    assert hub.schedule_enabled is True


async def test_set_weekday_requires_time_slot_list(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    with pytest.raises(ServiceValidationError) as err:
        await hub.async_set_schedule_weekday_enabled("WEEK_DAY_MONDAY", False)
    assert err.value.translation_key == "schedule_weekday_unavailable"
    assert device.requests == []


async def test_set_weekday_ignored_by_device(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)
    device.reply({"schedule_list": {}})
    await hass.async_block_till_done()
    device.apply_sets = False
    with pytest.raises(HomeAssistantError) as err:
        await hub.async_set_schedule_weekday_enabled("WEEK_DAY_MONDAY", False)
    assert err.value.translation_key == "schedule_switch_unconfirmed"


async def test_other_client_change_triggers_reread(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    device = FakeDevice(hub)

    # Rejected foreign SETs and GET replies do not trigger a read.
    device.reply({"cmd_type": SET_GLOBAL, "seq": 99, "code": 4})
    device.reply({"cmd_type": "SCHEDULE_CMD_TYPE_ADD", "seq": 98})
    await hass.async_block_till_done()
    assert device.requests == []

    device.global_disabled = True
    device.reply({"cmd_type": SET_GLOBAL, "seq": 99})
    await hass.async_block_till_done()
    assert device.commands == [GET]
    await hass.async_block_till_done()
    assert hub.schedule_enabled is False


# ---------------------------------------------------------------------------
# switch entities
# ---------------------------------------------------------------------------


async def test_switch_entities_follow_device(hass: HomeAssistant) -> None:
    hub = await setup_terramow(hass)
    assert hass.states.get(MASTER).state == STATE_UNAVAILABLE  # no dp_127 yet
    assert hass.states.get(MONDAY).state == STATE_UNAVAILABLE

    device = FakeDevice(hub)
    device.reply({"schedule_list": {"disabled_week_days": ["WEEK_DAY_MONDAY"]}})
    await hass.async_block_till_done()
    assert hass.states.get(MASTER).state == "on"
    assert hass.states.get(MONDAY).state == "off"
    assert hass.states.get("switch.terramow_tuesday_schedule").state == "on"

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": MASTER}, blocking=True
    )
    assert hass.states.get(MASTER).state == "off"

    hub._last_control_time -= 10
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": MONDAY}, blocking=True
    )
    assert hass.states.get(MONDAY).state == "on"
    assert device.disabled_days == set()

    # Frequency mode: weekday switches go unavailable, the master stays.
    device.reply({"schedule_list": {"schedule_mode": "SCHEDULE_MODE_FREQUENCY"}})
    await hass.async_block_till_done()
    assert hass.states.get(MONDAY).state == STATE_UNAVAILABLE
    assert hass.states.get(MASTER).state == "on"


async def test_switch_entities_without_hub(hass: HomeAssistant) -> None:
    basic_data = SimpleNamespace(host=HOST, lawn_mower=None, device_uid=SERIAL)
    master = ScheduleSwitch(basic_data, hass)  # type: ignore[arg-type]
    monday = ScheduleWeekdaySwitch(basic_data, hass, "monday")  # type: ignore[arg-type]
    assert monday.unique_id.endswith(".schedule_monday")
    for switch in (master, monday):
        assert switch.available is False
        assert switch.is_on is None
        await switch.async_turn_on()  # logs, does not raise
        await switch.async_turn_off()
