"""Tests for schedule item editing (dp_122 ADD / MODIFY / DELETE).

The vendor protocol: ``add_param`` / ``modify_param`` carry the schedule
type plus its ``global_schedule_v2`` object, ``delete_param`` only the id.
The device's own dp_122 reply (seq + cmd_type) never carries the assigned
id, so every edit runs baseline GET -> edit -> verification GET. These tests
drive the hub against a scripted fake device and pin each boundary: request
shapes, id assignment, rejected / lost / ignored edits, concurrent ADDs,
content mismatches, malformed readbacks and preservation of unknown fields.
"""

from __future__ import annotations

import copy
import json
from datetime import time as dt_time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import (
    SERVICE_ADD_SCHEDULE,
    SERVICE_DELETE_SCHEDULE,
)
from custom_components.terramow.const import CONF_SERIAL, DOMAIN
from custom_components.terramow.hub import TerraMowHub

HOST = "192.0.2.10"
SERIAL = "MP511SCH01"

GET = "SCHEDULE_CMD_TYPE_GET"
ADD = "SCHEDULE_CMD_TYPE_ADD"
MODIFY = "SCHEDULE_CMD_TYPE_MODIFY"
DELETE = "SCHEDULE_CMD_TYPE_DELETE"

ITEM = TerraMowHub.build_schedule_item(
    week_days=["WEEK_DAY_TUESDAY", "WEEK_DAY_THURSDAY"],
    start_hour=7,
    start_minute=45,
    end_hour=9,
    end_minute=15,
)


def _device_item(item_id: int, item: dict[str, Any] | None = None) -> dict[str, Any]:
    """The slot as the device reports it (zero id omitted, like protobuf)."""
    data = copy.deepcopy(item or ITEM)
    return {"id": item_id, **data} if item_id else data


def _fake_hub_start(self: TerraMowHub) -> None:
    client = MagicMock()
    client.is_connected.return_value = True
    client.publish.return_value = MagicMock(rc=0)
    self.mqtt_client = client
    self.register_all_callbacks()


async def setup_terramow(hass: HomeAssistant) -> MockConfigEntry:
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


@pytest.fixture
def short_timeout():
    with patch("custom_components.terramow.hub.COMMAND_REPLY_TIMEOUT", 0.05):
        yield


class FakeDevice:
    """Scripted mower implementing the vendor dp_122 edit protocol.

    Replies on ``data_point/122/robot`` with ``cmd_type`` + ``seq`` (+ a
    non-zero ``code`` on rejection); GET replies omit the zero-valued
    ``cmd_type`` and ``code``. Knobs model the failure boundaries.
    """

    def __init__(self, hub: TerraMowHub, items: list[dict[str, Any]] | None = None):
        self.hub = hub
        self.items: list[dict[str, Any]] = items or []
        self.next_id = 1 + max([entry.get("id", 0) for entry in self.items] + [0])
        self.code = 0
        self.apply_writes = True
        self.answer_writes = True
        self.get_override: Any = None  # replaces the schedule_list once set
        self.concurrent_add = False  # another client adds a slot alongside
        self.mangle = False  # the device stores something else than asked
        self.requests: list[dict[str, Any]] = []
        hub._last_control_time -= 10  # step past the command rate limiter
        hub.mqtt_client.publish.side_effect = self._on_publish

    def _reply(self, payload: dict[str, Any]) -> None:
        msg = SimpleNamespace(
            topic="data_point/122/robot", payload=json.dumps(payload).encode()
        )
        self.hub.on_mqtt_message(None, None, msg)

    def _stored(self, param: dict[str, Any]) -> dict[str, Any]:
        stored = copy.deepcopy(param)
        if self.mangle:
            config = stored["global_schedule_v2"]["basic_config"]
            config["end_time"] = {"hour": 23}
        return stored

    def _apply(self, cmd: str, data: dict[str, Any]) -> None:
        if cmd == ADD:
            self.items.append({"id": self.next_id, **self._stored(data["add_param"])})
            self.next_id += 1
            if self.concurrent_add:
                self.items.append({"id": self.next_id, **copy.deepcopy(ITEM)})
                self.next_id += 1
        elif cmd == MODIFY:
            param = copy.deepcopy(data["modify_param"])
            item_id = param["id"]
            self.items = [
                {**self._stored(param), "id": item_id}
                if entry.get("id", 0) == item_id
                else entry
                for entry in self.items
            ]
        else:
            target = data["delete_param"]["id"]
            self.items = [e for e in self.items if e.get("id", 0) != target]

    def _on_publish(self, topic: str, payload: str, qos: int = 0) -> MagicMock:
        if topic != "data_point/122/app":
            return MagicMock(rc=0)
        data = json.loads(payload)
        self.requests.append(data)
        cmd, seq = data["cmd_type"], data["seq"]
        if cmd == GET:
            schedule_list: Any = (
                self.get_override
                if self.get_override is not None
                else {"items": copy.deepcopy(self.items)}
            )
            self._reply({"seq": seq, "schedule_list": schedule_list})
            return MagicMock(rc=0)
        if self.code == 0 and self.apply_writes:
            self._apply(cmd, data)
        if self.answer_writes:
            reply: dict[str, Any] = {"cmd_type": cmd, "seq": seq}
            if self.code:
                reply["code"] = self.code
            self._reply(reply)
        return MagicMock(rc=0)

    @property
    def commands(self) -> list[str]:
        return [request["cmd_type"] for request in self.requests]


# ---------------------------------------------------------------------------
# ADD
# ---------------------------------------------------------------------------


async def test_add_schedule_confirmed(hass: HomeAssistant) -> None:
    """ADD sends add_param, the single new id is read back and returned."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub, items=[_device_item(0)])

    item_id = await hub.async_add_schedule(copy.deepcopy(ITEM))
    assert item_id == 1
    assert device.commands == [GET, ADD, GET]
    add = device.requests[1]
    assert set(add) == {"cmd_type", "seq", "add_param"}
    assert add["add_param"]["schedule_type"] == "SCHEDULE_TYPE_GLOBAL_V2"
    config = add["add_param"]["global_schedule_v2"]["basic_config"]
    assert "run_once" not in config  # unused optional field omitted
    assert config["disabled"] is False
    # every request has its own int32 seq
    seqs = [request["seq"] for request in device.requests]
    assert len(set(seqs)) == 3 and all(0 < seq <= 0x7FFFFFFF for seq in seqs)
    # the verification GET refreshed the cache
    assert len(hub.full_schedule["items"]) == 2


async def test_add_schedule_rejected(hass: HomeAssistant) -> None:
    """A non-zero code fails without verification and refreshes the cache."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub)
    device.code = -1

    with pytest.raises(HomeAssistantError) as err:
        await hub.async_add_schedule(copy.deepcopy(ITEM))
    assert err.value.translation_key == "command_rejected"
    assert device.commands == [GET, ADD, GET]  # the last GET is the refresh
    assert device.items == []


async def test_add_schedule_lost_reply(hass: HomeAssistant, short_timeout) -> None:
    """No reply is unconfirmed even if the device applied the write."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub)
    device.answer_writes = False

    with pytest.raises(HomeAssistantError) as err:
        await hub.async_add_schedule(copy.deepcopy(ITEM))
    assert err.value.translation_key == "schedule_edit_unconfirmed"
    await hass.async_block_till_done()
    # the refresh shows the device's real state (the write did land)
    assert len(hub.full_schedule["items"]) == 1


@pytest.mark.parametrize(
    ("knob", "items_after"),
    [("ignored", 0), ("concurrent", 2), ("mangled", 1)],
)
async def test_add_schedule_unconfirmed_readback(
    hass: HomeAssistant, knob: str, items_after: int
) -> None:
    """Acked ADDs whose readback is not exactly one matching new id fail."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub)
    device.apply_writes = knob != "ignored"
    device.concurrent_add = knob == "concurrent"
    device.mangle = knob == "mangled"

    with pytest.raises(HomeAssistantError) as err:
        await hub.async_add_schedule(copy.deepcopy(ITEM))
    assert err.value.translation_key == "schedule_edit_unconfirmed"
    # never retried, never rolled back
    assert device.commands == [GET, ADD, GET]
    assert len(device.items) == items_after


@pytest.mark.parametrize(
    "schedule_list",
    [
        None,
        {"items": "x"},
        {"items": [1]},
        {"items": [{"id": "1"}]},
        {"items": [{"id": 1}, {"id": 1}]},
    ],
)
async def test_malformed_baseline_aborts(
    hass: HomeAssistant, schedule_list: Any
) -> None:
    """A malformed GET cannot confirm anything: no edit is sent."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub)
    device.get_override = schedule_list if schedule_list is not None else "bad"

    with pytest.raises(HomeAssistantError) as err:
        await hub.async_add_schedule(copy.deepcopy(ITEM))
    assert err.value.translation_key == "schedule_edit_unconfirmed"
    assert device.commands == [GET]


async def test_baseline_get_timeout(hass: HomeAssistant, short_timeout) -> None:
    """A silent GET reports the edit as unconfirmed."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub)
    hub.mqtt_client.publish.side_effect = lambda *a, **k: MagicMock(rc=0)

    with pytest.raises(HomeAssistantError) as err:
        await hub.async_delete_schedule(1)
    assert err.value.translation_key == "schedule_edit_unconfirmed"
    assert device.requests == []


# ---------------------------------------------------------------------------
# MODIFY
# ---------------------------------------------------------------------------


async def test_modify_schedule_preserves_unknown_fields(hass: HomeAssistant) -> None:
    """MODIFY sends the full replacement, keeping fields it does not manage."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    existing = _device_item(7)
    existing["global_schedule_v2"]["repeat_until_end_time"] = True
    existing["global_schedule_v2"]["basic_config"]["disabled"] = True
    existing["global_schedule_v2"]["basic_config"]["run_once"] = True
    device = FakeDevice(hub, items=[existing])

    new = TerraMowHub.build_schedule_item(
        week_days=["WEEK_DAY_FRIDAY"],
        start_hour=10,
        start_minute=0,
        end_hour=11,
        end_minute=30,
        disabled=None,
    )
    await hub.async_modify_schedule(7, new)
    assert device.commands == [GET, MODIFY, GET]
    param = device.requests[1]["modify_param"]
    assert param["id"] == 7
    assert param["schedule_type"] == "SCHEDULE_TYPE_GLOBAL_V2"
    assert param["global_schedule_v2"]["repeat_until_end_time"] is True
    config = param["global_schedule_v2"]["basic_config"]
    assert config["week_days"] == ["WEEK_DAY_FRIDAY"]
    assert config["end_time"] == {"hour": 11, "minute": 30}
    assert config["disabled"] is True  # preserved
    assert config["run_once"] is False  # explicitly cleared: now weekly


async def test_modify_schedule_minimal_existing_item(hass: HomeAssistant) -> None:
    """An item reported without settings still gets a complete replacement."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub, items=[{"schedule_type": "SCHEDULE_TYPE_GLOBAL_V2"}])

    await hub.async_modify_schedule(0, copy.deepcopy(ITEM))
    config = device.requests[1]["modify_param"]["global_schedule_v2"]["basic_config"]
    assert "run_once" not in config  # never reported, not requested
    assert device.items[0]["id"] == 0


async def test_modify_schedule_unknown_or_foreign_item(hass: HomeAssistant) -> None:
    """Unknown ids and other schedule types are refused before writing."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(
        hub, items=[{"id": 4, "schedule_type": "SCHEDULE_TYPE_ZONE", "zone": {}}]
    )

    with pytest.raises(ServiceValidationError) as err:
        await hub.async_modify_schedule(9, copy.deepcopy(ITEM))
    assert err.value.translation_key == "schedule_item_not_found"
    assert err.value.translation_placeholders == {"item_id": "9"}

    hub._last_control_time -= 10
    with pytest.raises(ServiceValidationError) as err:
        await hub.async_modify_schedule(4, copy.deepcopy(ITEM))
    assert err.value.translation_key == "schedule_item_not_editable"
    assert MODIFY not in device.commands
    assert device.items[0]["zone"] == {}  # untouched


@pytest.mark.parametrize("knob", ["mangled", "deleted", "retyped"])
async def test_modify_schedule_unconfirmed_readback(
    hass: HomeAssistant, knob: str
) -> None:
    """A readback differing from the request is reported as unconfirmed."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub, items=[_device_item(3)])
    device.mangle = knob == "mangled"
    original_apply = device._apply

    def _apply(cmd: str, data: dict[str, Any]) -> None:
        original_apply(cmd, data)
        if knob == "deleted":
            device.items = []
        elif knob == "retyped":
            device.items[0]["schedule_type"] = "SCHEDULE_TYPE_GLOBAL"

    device._apply = _apply  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError) as err:
        await hub.async_modify_schedule(3, copy.deepcopy(ITEM))
    assert err.value.translation_key == "schedule_edit_unconfirmed"


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


async def test_delete_schedule_confirmed(hass: HomeAssistant) -> None:
    """DELETE sends only the id (including the protobuf-omitted id 0)."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub, items=[_device_item(0), _device_item(3)])

    await hub.async_delete_schedule(0)
    assert device.commands == [GET, DELETE, GET]
    assert device.requests[1]["delete_param"] == {"id": 0}
    assert [entry["id"] for entry in device.items] == [3]


async def test_delete_schedule_unknown_id(hass: HomeAssistant) -> None:
    """Deleting a nonexistent id fails fast without writing."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub, items=[_device_item(3)])

    with pytest.raises(ServiceValidationError) as err:
        await hub.async_delete_schedule(99)
    assert err.value.translation_key == "schedule_item_not_found"
    assert device.commands == [GET]


async def test_delete_schedule_still_present(hass: HomeAssistant) -> None:
    """An acked DELETE whose target reads back is unconfirmed."""
    hub = (await setup_terramow(hass)).runtime_data.lawn_mower
    device = FakeDevice(hub, items=[_device_item(3)])
    device.apply_writes = False

    with pytest.raises(HomeAssistantError) as err:
        await hub.async_delete_schedule(3)
    assert err.value.translation_key == "schedule_edit_unconfirmed"


# ---------------------------------------------------------------------------
# helpers, services, lifecycle
# ---------------------------------------------------------------------------


def test_build_schedule_item_optional_fields() -> None:
    """run_once only when set; disabled=None leaves the flag out."""
    item = TerraMowHub.build_schedule_item(
        ["WEEK_DAY_MONDAY"], 1, 2, 3, 4, disabled=None, run_once=True
    )
    config = item["global_schedule_v2"]["basic_config"]
    assert config == {
        "week_days": ["WEEK_DAY_MONDAY"],
        "start_time": {"hour": 1, "minute": 2},
        "end_time": {"hour": 3, "minute": 4},
        "run_once": True,
    }


def test_schedule_items_match_edge_cases() -> None:
    """Omitted defaults normalize; config-less items never match."""
    assert not TerraMowHub._schedule_items_match(None, ITEM)
    assert not TerraMowHub._schedule_items_match({"global_schedule_v2": {}}, ITEM)
    assert not TerraMowHub._schedule_items_match({"global_schedule_v2": 1}, ITEM)
    reordered = _device_item(9)
    config = reordered["global_schedule_v2"]["basic_config"]
    config["week_days"].reverse()
    del config["disabled"]  # protobuf omits false
    assert TerraMowHub._schedule_items_match(reordered, ITEM)
    config["disabled"] = True
    assert not TerraMowHub._schedule_items_match(reordered, ITEM)


async def test_services_dispatch(hass: HomeAssistant) -> None:
    """The services convert fields and reach the hub."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    device = FakeDevice(hub)
    entity_id = er.async_get(hass).async_get_entity_id(
        "lawn_mower", DOMAIN, f"lawn_mower.terramow@{SERIAL}"
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_SCHEDULE,
        {
            "entity_id": entity_id,
            "week_days": ["tuesday", "thursday"],
            "start_time": dt_time(7, 45),
            "end_time": dt_time(9, 15),
        },
        blocking=True,
    )
    assert len(device.items) == 1
    config = device.requests[1]["add_param"]["global_schedule_v2"]["basic_config"]
    assert config["week_days"] == ["WEEK_DAY_TUESDAY", "WEEK_DAY_THURSDAY"]
    assert config["start_time"] == {"hour": 7, "minute": 45}
    assert config["end_time"] == {"hour": 9, "minute": 15}
    assert config["disabled"] is False

    hub._last_control_time -= 10
    await hass.services.async_call(
        DOMAIN,
        SERVICE_DELETE_SCHEDULE,
        {"entity_id": entity_id, "item_id": 1},
        blocking=True,
    )
    assert device.items == []


async def test_unload_keeps_schedule_services(hass: HomeAssistant) -> None:
    """Unloading the last entry leaves the schedule actions registered."""
    entry = await setup_terramow(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert hass.services.has_service(DOMAIN, SERVICE_ADD_SCHEDULE)
    assert hass.services.has_service(DOMAIN, SERVICE_DELETE_SCHEDULE)


async def test_unload_keeps_services_while_other_entry_loaded(
    hass: HomeAssistant,
) -> None:
    """Shared services survive as long as another entry is loaded."""
    entry_one = await setup_terramow(hass)
    entry_two = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.11", CONF_PASSWORD: "secret"},
        unique_id="second",
    )
    entry_two.add_to_hass(hass)
    with (
        patch(
            "custom_components.terramow.validate_input",
            return_value={"title": "TerraMow (192.0.2.11)"},
        ),
        patch.object(TerraMowHub, "start", _fake_hub_start),
    ):
        assert await hass.config_entries.async_setup(entry_two.entry_id)
        await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry_one.entry_id)
    assert hass.services.has_service(DOMAIN, SERVICE_ADD_SCHEDULE)
