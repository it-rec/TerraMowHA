"""Tests for the writable schedule (dp_122 ADD/DELETE negotiation).

The write format is undocumented, so the hub negotiates: each candidate
payload shape is judged by its dp_119 ack and verified against a fresh
GET. These tests drive that loop with a scripted fake device that acks
commands and answers GETs.
"""

from __future__ import annotations

import asyncio
import json
from datetime import time as dt_time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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

ITEM = TerraMowHub.build_schedule_item(
    week_days=["WEEK_DAY_TUESDAY", "WEEK_DAY_THURSDAY"],
    start_hour=7,
    start_minute=45,
    end_hour=9,
    end_minute=15,
)


def _attempt_label(data: dict[str, Any]) -> str:
    """Mirror the hub's candidate labels from a write payload."""
    cmd = data["cmd_type"]
    extras = [k for k in data if k not in ("cmd_type", "seq")]
    if isinstance(cmd, int):
        return f"cmd{cmd}_schedule_list"
    if cmd == "SCHEDULE_CMD_TYPE_GET" and "schedule_list" in data:
        return "get_with_list"
    if cmd == "SCHEDULE_CMD_TYPE_SET":
        return "set_schedule_list"
    if cmd == "SCHEDULE_CMD_TYPE_UPDATE":
        return "update_schedule_list"
    if cmd == "SCHEDULE_CMD_TYPE_SAVE":
        return "save_schedule_list"
    if cmd == "SCHEDULE_CMD_TYPE_DELETE":
        return {
            "id": "delete_id",
            "item_id": "delete_item_id",
            "ids": "delete_ids",
            "item": "delete_item",
        }[extras[0]]
    if "schedule_type" in data:
        return "add_inline"
    return {
        "schedule_list": "add_schedule_list",
        "item": "add_item",
        "schedule_item": "add_schedule_item",
        "schedule": "add_schedule",
    }[extras[0]]


def _device_item(item_id: int) -> dict[str, Any]:
    """The slot as the device would report it in a GET response."""
    return {"id": item_id, **json.loads(json.dumps(ITEM))}


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


class FakeDevice:
    """Scripted mower: acks dp_122 writes and answers GETs.

    ``ack_codes`` maps a write-payload field name ("item", "id", ...) to
    the dp_119 code to answer with; unlisted fields get code 0.
    ``accept_fields`` is the set of field names whose ADD/DELETE actually
    mutates the fake schedule (an acked-but-ignored write is modelled by
    acking 0 without listing the field here).
    """

    def __init__(
        self,
        hub: TerraMowHub,
        items: list[dict[str, Any]] | None = None,
        ack_codes: dict[str, int] | None = None,
        accept_fields: set[str] | None = None,
    ) -> None:
        self.hub = hub
        self.items = items or []
        self.ack_codes = ack_codes or {}
        self.accept_fields = (
            accept_fields
            if accept_fields is not None
            else {"add_inline", "delete_id"}
        )
        self.write_attempts: list[dict[str, Any]] = []
        hub.mqtt_client.publish.side_effect = self._on_publish

    def _reply(self, dp_id: int, payload: dict[str, Any]) -> None:
        msg = SimpleNamespace(
            topic=f"data_point/{dp_id}/robot",
            payload=json.dumps(payload).encode(),
        )
        self.hub.on_mqtt_message(None, None, msg)

    def _on_publish(self, topic: str, payload: str, qos: int = 0) -> MagicMock:
        if topic == "data_point/122/app":
            data = json.loads(payload)
            cmd = data.get("cmd_type")
            if cmd == "SCHEDULE_CMD_TYPE_GET" and "schedule_list" not in data:
                self._reply(
                    122,
                    {
                        "cmd_type": "SCHEDULE_CMD_TYPE_GET",
                        "schedule_list": {"items": list(self.items)},
                    },
                )
            else:
                self.write_attempts.append(data)
                label = _attempt_label(data)
                code = self.ack_codes.get(label, 0)
                if code == 0 and label in self.accept_fields:
                    if label.startswith("cmd") or label in (
                        "set_schedule_list",
                        "get_with_list",
                    ):
                        # full-replace semantics; re-id new entries (id 0)
                        items = data["schedule_list"]["items"]
                        next_id = max(
                            [e.get("id", 0) for e in items] + [0]
                        ) + 1
                        self.items = [
                            e if e.get("id") else {**e, "id": next_id}
                            for e in items
                        ]
                    elif cmd == "SCHEDULE_CMD_TYPE_ADD":
                        submitted = dict(data)
                        submitted.pop("cmd_type"), submitted.pop("seq")
                        if label == "add_schedule_list":
                            submitted = data["schedule_list"]["items"][0]
                        elif label != "add_inline":
                            (submitted,) = [
                                v for k, v in submitted.items()
                            ]
                        submitted = {k: v for k, v in submitted.items() if k != "id"}
                        self.items.append(
                            {"id": len(self.items) + 1, **submitted}
                        )
                    else:  # DELETE variants
                        target = data.get("id", data.get("item_id"))
                        if "ids" in data:
                            target = data["ids"][0]
                        if "item" in data:
                            target = data["item"]["id"]
                        self.items = [
                            entry for entry in self.items if entry["id"] != target
                        ]
                self._reply(119, {"seq": data["seq"], "code": code})
        elif topic == "data_point/127/app":
            pass  # compatibility request — irrelevant here
        return MagicMock(rc=0)


async def test_add_schedule_first_candidate(hass: HomeAssistant) -> None:
    """The primary "item" shape is acked, lands in the GET, id returned."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    device = FakeDevice(hub)

    item_id = await hub.async_add_schedule(dict(ITEM))
    assert item_id == 1
    assert hub._schedule_write_field == "add_inline"
    assert len(device.write_attempts) == 1
    assert "schedule_type" in device.write_attempts[0]  # inline item fields


async def test_add_schedule_falls_back_on_rejection(hass: HomeAssistant) -> None:
    """A rejected first shape falls through to the next candidate."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    device = FakeDevice(
        hub,
        ack_codes={"add_inline": 5},
        accept_fields={"add_schedule_list"},
    )

    item_id = await hub.async_add_schedule(dict(ITEM))
    assert item_id == 1
    assert hub._schedule_write_field == "add_schedule_list"
    labels = [_attempt_label(a) for a in device.write_attempts]
    assert labels == ["add_inline", "add_schedule_list"]

    # The proven shape is tried first on the next write
    hub._last_control_time -= 10  # step past the command rate limiter
    await hub.async_add_schedule(
        TerraMowHub.build_schedule_item(
            week_days=["WEEK_DAY_MONDAY"],
            start_hour=10,
            start_minute=0,
            end_hour=11,
            end_minute=0,
        )
    )
    assert _attempt_label(device.write_attempts[-1]) == "add_schedule_list"


async def test_add_schedule_acked_but_ignored_moves_on(
    hass: HomeAssistant,
) -> None:
    """An ack-0 shape whose slot never appears is not trusted."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    # everything acks 0, but only "set_schedule_list" actually mutates it
    device = FakeDevice(hub, accept_fields={"set_schedule_list"})

    item_id = await hub.async_add_schedule(dict(ITEM))
    assert item_id == 1
    assert hub._schedule_write_field == "set_schedule_list"
    labels = [_attempt_label(a) for a in device.write_attempts]
    assert labels == ["add_inline", "add_schedule_list", "set_schedule_list"]


async def test_add_schedule_all_rejected(hass: HomeAssistant) -> None:
    """Total rejection raises with the attempted codes in the message."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    labels = [
        "add_inline", "add_schedule_list", "set_schedule_list",
        "update_schedule_list", "save_schedule_list", "add_item",
        "add_schedule_item", "add_schedule",
    ]
    FakeDevice(hub, ack_codes=dict.fromkeys(labels, 3))

    with pytest.raises(HomeAssistantError):
        await hub.async_add_schedule(dict(ITEM))


async def test_delete_schedule(hass: HomeAssistant) -> None:
    """Deleting an existing slot verifies its disappearance."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    device = FakeDevice(hub, items=[_device_item(3)])

    await hub.async_delete_schedule(3)
    assert device.items == []


async def test_delete_schedule_unknown_id(hass: HomeAssistant) -> None:
    """Deleting a nonexistent id fails fast with a clear error."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    FakeDevice(hub, items=[_device_item(3)])

    with pytest.raises(HomeAssistantError):
        await hub.async_delete_schedule(99)


async def test_refresh_timeout_returns_cached(hass: HomeAssistant) -> None:
    """A silent device leaves the cached schedule in place."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    hub._full_schedule = {"items": [_device_item(7)]}

    result = await hub.async_refresh_full_schedule(timeout=0.05)
    assert result == {"items": [_device_item(7)]}


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
    config = device.write_attempts[0]["global_schedule_v2"]["basic_config"]
    assert config["week_days"] == ["WEEK_DAY_TUESDAY", "WEEK_DAY_THURSDAY"]
    assert config["start_time"] == {"hour": 7, "minute": 45}
    assert config["end_time"] == {"hour": 9, "minute": 15}
    assert config["disabled"] is False
    assert config["run_once"] is False

    # The rate limiter guards writes; step past it for the delete call.
    hub._last_control_time -= 10
    await hass.services.async_call(
        DOMAIN,
        SERVICE_DELETE_SCHEDULE,
        {"entity_id": entity_id, "item_id": 1},
        blocking=True,
    )
    assert device.items == []


async def test_delete_schedule_all_candidates_fail(hass: HomeAssistant) -> None:
    """Rejected and acked-but-ineffective DELETE shapes both raise."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower

    # all delete shapes rejected outright
    delete_labels = [
        "delete_id", "delete_item_id", "delete_ids", "delete_item",
        "set_schedule_list",
    ]
    FakeDevice(
        hub,
        items=[_device_item(3)],
        ack_codes=dict.fromkeys(delete_labels, 4),
    )
    with pytest.raises(HomeAssistantError):
        await hub.async_delete_schedule(3)

    # all delete shapes acked but the slot never disappears
    hub._last_control_time -= 10
    FakeDevice(hub, items=[_device_item(3)], accept_fields=set())
    with pytest.raises(HomeAssistantError):
        await hub.async_delete_schedule(3)


async def test_refresh_ignores_noise_payloads(hass: HomeAssistant) -> None:
    """Garbage and schedule-less dp_122 payloads don't satisfy the refresh."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower

    def _reply(payload: bytes) -> None:
        msg = SimpleNamespace(topic="data_point/122/robot", payload=payload)
        hub.on_mqtt_message(None, None, msg)

    task = hass.async_create_task(hub.async_refresh_full_schedule(timeout=1))
    await asyncio.sleep(0)
    _reply(b"not json")
    _reply(b'{"cmd_type": "SCHEDULE_CMD_TYPE_ADD"}')  # ack-style, no list
    good = json.dumps(
        {"cmd_type": "SCHEDULE_CMD_TYPE_GET", "schedule_list": {"items": []}}
    ).encode()
    # delivered twice back-to-back: the second hits the future-done guard
    _reply(good)
    _reply(good)
    assert await task == {"items": []}


async def test_unload_removes_services_tolerates_missing(
    hass: HomeAssistant,
) -> None:
    """Unload removes all services, skipping any already gone."""
    entry = await setup_terramow(hass)
    hass.services.async_remove(DOMAIN, SERVICE_ADD_SCHEDULE)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hass.services.has_service(DOMAIN, SERVICE_DELETE_SCHEDULE)


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


async def test_numeric_verb_probe_on_empty_schedule(
    hass: HomeAssistant,
) -> None:
    """With an empty schedule, numeric verbs are probed; cmd3 wins here."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    device = FakeDevice(hub, accept_fields={"cmd3_schedule_list"})

    item_id = await hub.async_add_schedule(dict(ITEM))
    assert item_id == 1
    assert hub._schedule_write_field == "cmd3_schedule_list"
    labels = [_attempt_label(a) for a in device.write_attempts]
    assert "cmd1_schedule_list" in labels and "cmd3_schedule_list" in labels

    # Deleting reuses the proven numeric verb with replace semantics
    hub._last_control_time -= 10
    await hub.async_delete_schedule(1)
    assert device.items == []
    assert _attempt_label(device.write_attempts[-1]) == "cmd3_schedule_list"


async def test_numeric_verbs_gated_off_with_existing_slots(
    hass: HomeAssistant,
) -> None:
    """Numeric probing must never run against a non-empty schedule."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    device = FakeDevice(hub, items=[_device_item(0)], accept_fields=set())

    other = TerraMowHub.build_schedule_item(
        week_days=["WEEK_DAY_MONDAY"],
        start_hour=10,
        start_minute=0,
        end_hour=11,
        end_minute=0,
    )
    with pytest.raises(HomeAssistantError):
        await hub.async_add_schedule(other)
    labels = [_attempt_label(a) for a in device.write_attempts]
    assert not any(label.startswith("cmd") and label[3].isdigit() for label in labels)


async def test_schedule_items_match_edge_cases() -> None:
    """Non-dict and config-less items never match."""
    assert not TerraMowHub._schedule_items_match(None, ITEM)
    assert not TerraMowHub._schedule_items_match({"global_schedule_v2": {}}, ITEM)
    assert TerraMowHub._schedule_items_match(_device_item(9), ITEM)
