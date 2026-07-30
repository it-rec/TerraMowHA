"""Per-zone service-level planning."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.zone_planner import build_zone_plan


def _map(map_id: int = 1) -> dict[str, object]:
    return {
        "id": map_id,
        "regions": [
            {
                "sub_regions": [
                    {"id": 1, "name": "Front"},
                    {"id": 2, "name": "Side"},
                    {"id": 3, "name": "Orchard"},
                    {"id": 4, "name": "Play"},
                ]
            }
        ],
    }


def _hub() -> TerraMowHub:
    return TerraMowHub(
        TerraMowBasicData(host="192.0.2.218", password="secret"),
        MagicMock(),
    )


def test_deterministic_due_order_and_every_decision() -> None:
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    plan = build_zone_plan(
        map_data=_map(),
        last_seen={
            1: (now - timedelta(days=5)).isoformat(),
            2: (now - timedelta(days=10)).isoformat(),
            4: (now - timedelta(days=1)).isoformat(),
        },
        policies={
            1: {"interval_days": 3, "priority": 5},
            2: {"interval_days": 7, "priority": 1},
            3: {"interval_days": 1, "manual_only": True},
            4: {"interval_days": 3, "enabled": False},
            5: {"interval_days": 1},
            6: {"interval_days": 1, "map_id": 2},
        },
        unknown_choice="ask",
        now=now,
    )
    assert plan["region_ids"] == [1, 2]
    assert [item["reason"] for item in plan["decisions"]] == [
        "due",
        "due",
        "manual_only",
        "disabled",
        "removed",
        "removed",
    ]
    assert not plan["blocked_on_unknown"]


def test_unknown_renamed_invalid_not_due_and_bad_choice() -> None:
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    policies = {
        1: {"interval_days": 3, "expected_name": "Old"},
        2: {"interval_days": 3},
        3: {"interval_days": 0},
        4: {"interval_days": 3},
    }
    plan = build_zone_plan(
        map_data=_map(),
        last_seen={
            3: "bad",
            4: (now - timedelta(days=1)).replace(tzinfo=None).isoformat(),
        },
        policies=policies,
        unknown_choice="ask",
        now=now,
    )
    assert [item["reason"] for item in plan["decisions"]] == [
        "renamed",
        "unknown_ask",
        "invalid_policy",
        "not_due",
    ]
    assert plan["blocked_on_unknown"]

    included = build_zone_plan(
        map_data=_map(),
        last_seen={},
        policies={2: {"interval_days": 3, "priority": 2}},
        unknown_choice="include",
        now=now,
    )
    assert included["region_ids"] == [2]
    excluded = build_zone_plan(
        map_data=_map(),
        last_seen={},
        policies={2: {"interval_days": 3}},
        unknown_choice="exclude",
        now=now,
    )
    assert excluded["region_ids"] == []
    with pytest.raises(ValueError):
        build_zone_plan(
            map_data=_map(),
            last_seen={},
            policies={},
            unknown_choice="guess",
            now=now,
        )


async def test_hub_persists_plans_and_uses_confirmed_start() -> None:
    hub = _hub()
    hub._map_data = _map()
    hub._zone_last_seen = {
        1: (datetime.now(UTC) - timedelta(days=5)).isoformat()
    }
    store = hub._get_zone_policy_store()
    store.async_save = AsyncMock()
    policies = {
        "1": {"interval_days": 3, "priority": 5},
        "2": {"interval_days": 3, "manual_only": True},
    }
    plan = await hub.async_plan_due_zones(
        policies=policies, unknown_choice="exclude"
    )
    assert plan["region_ids"] == [1]
    assert hub.last_zone_plan == plan
    saved = store.async_save.await_args.args[0]["policies"]
    assert saved["1"]["map_id"] == 1
    assert saved["1"]["expected_name"] == "Front"

    hub.async_start_select_region_clean = AsyncMock()
    started = await hub.async_start_due_zones(unknown_choice="exclude")
    assert started["region_ids"] == [1]
    hub.async_start_select_region_clean.assert_awaited_once_with([1])

    hub._zone_last_seen = {}
    with pytest.raises(HomeAssistantError):
        await hub.async_start_due_zones(unknown_choice="ask")


async def test_policy_restore_and_validation() -> None:
    hub = _hub()
    hub._map_data = _map()
    store = hub._get_zone_policy_store()
    store.async_load = AsyncMock(
        return_value={
            "policies": {
                "1": {"interval_days": 3},
                "bad": {"interval_days": 4},
                "2": "bad",
            }
        }
    )
    await hub.async_restore_zone_policies()
    assert hub._zone_policies == {1: {"interval_days": 3}}
    store.async_load = AsyncMock(return_value={"policies": "bad"})
    await hub.async_restore_zone_policies()
    store.async_load = AsyncMock(side_effect=OSError("broken"))
    await hub.async_restore_zone_policies()

    store.async_save = AsyncMock()
    with pytest.raises(HomeAssistantError):
        await hub.async_set_zone_policies({"bad": {}})
    with pytest.raises(HomeAssistantError):
        await hub.async_set_zone_policies({True: {}})
    with pytest.raises(HomeAssistantError):
        await hub.async_set_zone_policies({1: "bad"})


def test_planner_skips_malformed_map_and_flags_mismatches() -> None:
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    messy = {
        "id": 1,
        "regions": [
            "bad",
            {
                "sub_regions": [
                    "bad",
                    {"id": True, "name": "Bool"},
                    {"id": 7, "name": ""},
                    {"id": 8, "name": "Eight"},
                ]
            },
        ],
    }
    plan = build_zone_plan(
        map_data=messy,
        last_seen={8: "not-a-timestamp"},
        policies={
            7: {"interval_days": 1, "map_id": 2},
            8: {"interval_days": 1},
        },
        unknown_choice="exclude",
        now=now,
    )
    by_id = {item["region_id"]: item for item in plan["decisions"]}
    # a policy bound to another map is refused, never re-applied blindly
    assert by_id[7]["reason"] == "map_mismatch"
    # an empty device-reported name stays None instead of ""
    assert by_id[7]["name"] is None
    # an unparseable timestamp counts as unknown, never guessed at
    assert by_id[8]["reason"] == "unknown_exclude"
    assert by_id[8]["included"] is False

    # the hub-side name scan skips the same malformed shapes
    hub = _hub()
    hub._map_data = messy
    assert hub._zone_names() == {7: None, 8: "Eight"}


async def test_start_due_zones_without_due_ids_does_not_start() -> None:
    hub = _hub()
    hub._map_data = _map()
    hub._zone_last_seen = {
        1: (datetime.now(UTC) - timedelta(days=1)).isoformat()
    }
    store = hub._get_zone_policy_store()
    store.async_save = AsyncMock()
    hub.async_start_select_region_clean = AsyncMock()
    plan = await hub.async_start_due_zones(
        policies={"1": {"interval_days": 30}}, unknown_choice="exclude"
    )
    assert plan["region_ids"] == []
    hub.async_start_select_region_clean.assert_not_awaited()


async def test_due_zone_services_dispatch_and_respond(hass) -> None:
    from homeassistant.const import CONF_HOST, CONF_PASSWORD
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.terramow import (
        SERVICE_PLAN_DUE_ZONES,
        SERVICE_START_DUE_ZONES,
        _async_register_services,
    )
    from custom_components.terramow.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.10", CONF_PASSWORD: "s"},
        unique_id="192.0.2.10",
    )
    entry.add_to_hass(hass)
    hub = MagicMock()
    hub.async_plan_due_zones = AsyncMock(return_value={"region_ids": []})
    hub.async_start_due_zones = AsyncMock(return_value={"region_ids": [2]})
    basic_data = TerraMowBasicData(
        host="192.0.2.10", password="s", entry_id=entry.entry_id
    )
    basic_data.lawn_mower = hub
    entry.runtime_data = basic_data

    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create("lawn_mower", DOMAIN, "unique", config_entry=entry)
    entity_id = ent_reg.async_get_entity_id("lawn_mower", DOMAIN, "unique")

    _async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAN_DUE_ZONES,
        {"entity_id": entity_id, "policies": {"1": {"interval_days": 3}}},
        blocking=True,
        return_response=True,
    )
    assert response == {"plans": [{"region_ids": []}]}
    hub.async_plan_due_zones.assert_awaited_once_with(
        policies={"1": {"interval_days": 3}}, unknown_choice="ask"
    )

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_START_DUE_ZONES,
        {"entity_id": entity_id, "unknown_choice": "exclude"},
        blocking=True,
        return_response=True,
    )
    assert response == {"plans": [{"region_ids": [2]}]}
    hub.async_start_due_zones.assert_awaited_once_with(
        policies=None, unknown_choice="exclude"
    )
