"""dp_120 map edits: thorough corner cutting and high-grass edge trim mode.

Pins the vendor protocol (docs/en/developers/map_edit.md): requests carry
``seq``, the current map's ``map_id``, the command name and exactly that
command's parameter object; replies are matched by ``seq`` and report in
``code`` (missing = 0). Only code 0 confirms; a timeout, code 203 (edit may
already be applied) and other codes do not. The settings are map-level and
are not written to dp_155.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import (
    COMPATIBILITY_INFO_DP,
    MAP_EDIT_CMD_SET_HIGH_GRASS_EDGE_TRIM_MODE,
    MAP_EDIT_CMD_SET_THOROUGH_CORNER_CUTTING,
    MAP_EDIT_DP,
)
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.select import HighGrassEdgeTrimModeSelect
from custom_components.terramow.switch import ThoroughCornerCuttingSwitch


def _hub(map_id: Any = 7) -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.60", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    if map_id is not None:
        hub._map_info = {"id": map_id, "mow_param": {}}
    return hub


def _reply_with(hub: TerraMowHub, reply: dict[str, Any] | None) -> list[dict]:
    """Make the mocked mower answer each dp_120 request with ``reply``.

    ``reply`` gets the request's ``seq`` unless it already sets one; ``None``
    sends no reply at all. Returns the list of published requests.
    """
    sent: list[dict] = []

    def publish(topic: str, payload: str, **_kwargs: Any) -> MagicMock:
        request = json.loads(payload)
        sent.append({"topic": topic, **request})
        if reply is not None:
            answer = {"seq": request["seq"], **reply}
            asyncio.get_running_loop().create_task(
                hub.on_map_edit_reply(json.dumps(answer))
            )
        return MagicMock(rc=0)

    hub.mqtt_client.publish.side_effect = publish
    return sent


def _run(hub: TerraMowHub, coro_factory) -> None:
    async def runner() -> None:
        hub.hass.loop = asyncio.get_running_loop()
        await coro_factory()

    asyncio.run(runner())


# ---------------------------------------------------------------------------
# request shape
# ---------------------------------------------------------------------------


def test_corner_cutting_request_shape_and_map_binding() -> None:
    hub = _hub(map_id=7)
    sent = _reply_with(hub, {"code": 0})
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)

    _run(hub, switch.async_turn_on)
    _run(hub, switch.async_turn_off)

    assert [request["topic"] for request in sent] == [
        f"data_point/{MAP_EDIT_DP}/app"
    ] * 2
    first, second = sent
    assert first["map_id"] == 7
    assert first["command"] == MAP_EDIT_CMD_SET_THOROUGH_CORNER_CUTTING
    assert first["set_thorough_corner_cutting_param"] == {
        "enable_thorough_corner_cutting": True
    }
    assert second["set_thorough_corner_cutting_param"] == {
        "enable_thorough_corner_cutting": False
    }
    # Exactly the command's own parameter object, no wrapper, fresh seq.
    assert set(first) == {
        "topic",
        "seq",
        "map_id",
        "command",
        "set_thorough_corner_cutting_param",
    }
    assert second["seq"] != first["seq"]
    # Raw stays raw: no optimistic state before the map reports the value.
    assert switch.is_on is None


@pytest.mark.parametrize(
    ("option", "device_mode"),
    [
        ("high_grass_edge_trim_disabled", "HIGH_GRASS_EDGE_TRIM_DISABLED"),
        ("high_grass_edge_trim_standard", "HIGH_GRASS_EDGE_TRIM_STANDARD"),
        ("high_grass_edge_trim_enhanced", "HIGH_GRASS_EDGE_TRIM_ENHANCED"),
    ],
)
def test_high_grass_request_shape(option: str, device_mode: str) -> None:
    hub = _hub(map_id=3)
    sent = _reply_with(hub, {})  # protobuf JSON omits a zero code
    select = HighGrassEdgeTrimModeSelect(hub.basic_data, hub.hass)

    _run(hub, lambda: select.async_select_option(option))

    (request,) = sent
    assert request["topic"] == f"data_point/{MAP_EDIT_DP}/app"
    assert request["map_id"] == 3
    assert request["command"] == MAP_EDIT_CMD_SET_HIGH_GRASS_EDGE_TRIM_MODE
    assert request["set_high_grass_edge_trim_mode_param"] == {
        "high_grass_edge_trim_mode": {"mode": device_mode}
    }


def test_settings_are_not_written_to_dp155() -> None:
    hub = _hub()
    sent = _reply_with(hub, {"code": 0})
    _run(hub, ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass).async_turn_on)
    _run(
        hub,
        lambda: HighGrassEdgeTrimModeSelect(
            hub.basic_data, hub.hass
        ).async_select_option("high_grass_edge_trim_standard"),
    )
    assert all(request["topic"] == "data_point/120/app" for request in sent)


@pytest.mark.parametrize("map_info", [{}, {"id": "7"}, {"id": True}, {"id": None}])
def test_no_current_map_id_refuses_to_send(map_info: dict) -> None:
    hub = _hub(map_id=None)
    hub._map_info = map_info
    with pytest.raises(HomeAssistantError) as err:
        _run(
            hub,
            lambda: hub.async_map_edit(
                MAP_EDIT_CMD_SET_THOROUGH_CORNER_CUTTING,
                "set_thorough_corner_cutting_param",
                {"enable_thorough_corner_cutting": True},
            ),
        )
    assert err.value.translation_key == "map_edit_no_map"
    hub.mqtt_client.publish.assert_not_called()


# ---------------------------------------------------------------------------
# reply outcomes
# ---------------------------------------------------------------------------


def _edit(hub: TerraMowHub) -> None:
    _run(
        hub,
        lambda: hub.async_map_edit(
            MAP_EDIT_CMD_SET_THOROUGH_CORNER_CUTTING,
            "set_thorough_corner_cutting_param",
            {"enable_thorough_corner_cutting": True},
        ),
    )


def test_code_zero_confirms() -> None:
    hub = _hub()
    _reply_with(hub, {"code": 0})
    _edit(hub)
    assert hub._pending_acks == {}
    assert hub.last_command_ack["dp"] == MAP_EDIT_DP


def test_timeout_is_not_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("custom_components.terramow.hub.COMMAND_REPLY_TIMEOUT", 0.01)
    hub = _hub()
    _reply_with(hub, None)
    with pytest.raises(HomeAssistantError) as err:
        _edit(hub)
    assert err.value.translation_key == "map_edit_unconfirmed"
    assert hub._pending_acks == {}


def test_code_203_may_already_be_applied() -> None:
    hub = _hub()
    _reply_with(hub, {"code": 203})
    with pytest.raises(HomeAssistantError) as err:
        _edit(hub)
    assert err.value.translation_key == "map_edit_map_not_sent"


@pytest.mark.parametrize("code", [201, 202])
def test_other_codes_are_rejections(code: int) -> None:
    hub = _hub()
    _reply_with(hub, {"code": code})
    with pytest.raises(HomeAssistantError) as err:
        _edit(hub)
    assert err.value.translation_key == "command_rejected"
    assert err.value.translation_placeholders == {"code": str(code)}


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        json.dumps([1, 2]),
        json.dumps({"code": 0}),  # missing seq is never success
        json.dumps({"seq": "5", "code": 0}),
        json.dumps({"seq": True, "code": 0}),
        json.dumps({"seq": 5, "code": "0"}),
    ],
)
def test_malformed_replies_resolve_nothing(payload: str) -> None:
    hub = _hub()
    future = MagicMock()
    hub._pending_acks[5] = future
    asyncio.run(hub.on_map_edit_reply(payload))
    assert hub._pending_acks == {5: future}
    future.set_result.assert_not_called()


def test_reply_for_other_seq_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("custom_components.terramow.hub.COMMAND_REPLY_TIMEOUT", 0.01)
    hub = _hub()
    _reply_with(hub, {"seq": 999_999_999, "code": 0})
    with pytest.raises(HomeAssistantError) as err:
        _edit(hub)
    assert err.value.translation_key == "map_edit_unconfirmed"


def test_reply_callback_is_registered() -> None:
    hub = _hub()
    hub.register_all_callbacks()
    callbacks = hub.callbacks[MAP_EDIT_DP]
    assert any(
        getattr(cb, "__func__", None) is TerraMowHub.on_map_edit_reply
        for cb in callbacks
    )


# ---------------------------------------------------------------------------
# dp_127 feature-version gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module", "available"),
    [
        (None, True),  # dp_127 not reported yet: assume current firmware
        ({}, True),
        ({"thorough_corner_cutting": 0}, False),  # unsupported
        ({"thorough_corner_cutting": 1}, False),  # legacy dp_150 global
        ({"thorough_corner_cutting": 2}, True),  # map-level dp_120
        ({"thorough_corner_cutting": "3"}, True),
    ],
)
def test_corner_cutting_version_gate(module: dict | None, available: bool) -> None:
    hub = _hub()
    if module is not None:
        hub.basic_data.firmware_version = {"module": module}
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)
    assert switch.available is available


@pytest.mark.parametrize(
    ("module", "available"),
    [
        (None, True),
        ({"high_grass_edge_trim": 0}, False),  # unsupported
        ({"high_grass_edge_trim": 1}, False),  # legacy dp_150 boolean
        ({"high_grass_edge_trim": 2}, False),  # legacy dp_150 three-mode
        ({"high_grass_edge_trim": 3}, True),  # map-level dp_120
        ({"high_grass_edge_trim": 4}, True),
    ],
)
def test_high_grass_version_gate(module: dict | None, available: bool) -> None:
    hub = _hub()
    if module is not None:
        hub.basic_data.firmware_version = {"module": module}
    select = HighGrassEdgeTrimModeSelect(hub.basic_data, hub.hass)
    assert select.available is available


def test_entities_without_hub_are_unavailable() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    assert not ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass).available
    assert not HighGrassEdgeTrimModeSelect(hub.basic_data, hub.hass).available


def test_entities_refresh_on_compatibility_info() -> None:
    assert COMPATIBILITY_INFO_DP in ThoroughCornerCuttingSwitch._push_dp_ids
    assert COMPATIBILITY_INFO_DP in HighGrassEdgeTrimModeSelect._push_dp_ids


# ---------------------------------------------------------------------------
# state stays map-scoped
# ---------------------------------------------------------------------------


def test_state_follows_the_current_map() -> None:
    hub = _hub()
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)
    select = HighGrassEdgeTrimModeSelect(hub.basic_data, hub.hass)
    hub._update_map_info(
        {
            "id": 1,
            "mow_param": {
                "enable_thorough_corner_cutting": True,
                "high_grass_edge_trim_mode": {"mode": "HIGH_GRASS_EDGE_TRIM_ENHANCED"},
            },
        }
    )
    assert switch.is_on is True
    assert select.current_option == "high_grass_edge_trim_enhanced"

    # Another map without the settings: nothing carried over from map 1.
    hub._update_map_info({"id": 2, "mow_param": {}})
    assert switch.is_on is None
    assert select.current_option is None
