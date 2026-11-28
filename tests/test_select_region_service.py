"""terramow.start_select_region: zone-ID validation and target resolution.

Zone IDs must be non-negative whole numbers (booleans and floats are not
truncated into IDs), must all exist on each targeted mower's current map
before anything is sent, and are sent once each. Targets may be entities,
devices or areas; device/area targets reach only TerraMow lawn mowers.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import (
    SERVICE_DELETE_SCHEDULE,
    SERVICE_START_SELECT_REGION,
    TerraMowBasicData,
    _async_register_services,
    _referenced_entity_ids,
    zone_id,
)
from custom_components.terramow.const import DOMAIN
from custom_components.terramow.hub import TerraMowHub

# ---------------------------------------------------------------------------
# zone_id validator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"), [(0, 0), (7, 7), ("12", 12), (" 3 ", 3)]
)
def test_zone_id_accepts_whole_numbers(value: Any, expected: int) -> None:
    assert zone_id(value) == expected


@pytest.mark.parametrize(
    "value", [True, False, 1.0, 1.9, -1, "-1", "1.5", "", "abc", "٣", None, [1]]
)
def test_zone_id_rejects_everything_else(value: Any) -> None:
    with pytest.raises(vol.Invalid):
        zone_id(value)


def test_current_zone_ids_reads_the_map() -> None:
    hub = TerraMowHub(TerraMowBasicData(host="192.0.2.70", password="x"), MagicMock())
    assert hub.current_zone_ids == set()
    hub._map_data = {
        "regions": [
            {"sub_regions": [{"id": 1}, {"id": 2, "name": "Front"}, {"id": True}]},
            "junk",
            {"sub_regions": [{"id": 9}, "junk"]},
        ]
    }
    assert hub.current_zone_ids == {1, 2, 9}


# ---------------------------------------------------------------------------
# service fixtures
# ---------------------------------------------------------------------------


def _mower(
    hass: HomeAssistant, unique: str, zones: set[int], area_id: str | None = None
) -> tuple[MagicMock, str, str]:
    """Register a fake TerraMow entry/device/mower; return (hub, entity, device)."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=unique)
    entry.add_to_hass(hass)
    hub = MagicMock()
    hub.current_zone_ids = zones
    hub.async_start_select_region_clean = AsyncMock()
    hub.async_delete_schedule = AsyncMock()
    basic_data = TerraMowBasicData(
        host=unique, password="secret", entry_id=entry.entry_id
    )
    basic_data.lawn_mower = hub
    entry.runtime_data = basic_data

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, unique)}
    )
    if area_id is not None:
        dr.async_get(hass).async_update_device(device.id, area_id=area_id)
    ent_reg = er.async_get(hass)
    mower = ent_reg.async_get_or_create(
        "lawn_mower", DOMAIN, unique, config_entry=entry, device_id=device.id
    )
    # A second entity on the same device must not make the mower run twice.
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{unique}-battery", config_entry=entry, device_id=device.id
    )
    return hub, mower.entity_id, device.id


async def _call(hass: HomeAssistant, data: dict[str, Any]) -> None:
    await hass.services.async_call(
        DOMAIN, SERVICE_START_SELECT_REGION, data, blocking=True
    )


# ---------------------------------------------------------------------------
# zone validation against the current map
# ---------------------------------------------------------------------------


async def test_ids_are_deduplicated_in_order(hass: HomeAssistant) -> None:
    hub, entity_id, _ = _mower(hass, "m1", {1, 2, 3})
    _async_register_services(hass)
    await _call(hass, {"entity_id": entity_id, "region_ids": [3, "1", 3, 1]})
    hub.async_start_select_region_clean.assert_awaited_once_with([3, 1])


async def test_unknown_zone_ids_send_nothing(hass: HomeAssistant) -> None:
    hub, entity_id, _ = _mower(hass, "m1", {1, 2})
    _async_register_services(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, {"entity_id": entity_id, "region_ids": [9, 1, 4]})
    assert err.value.translation_key == "unknown_zones"
    assert err.value.translation_placeholders == {"zone_ids": "4, 9"}
    hub.async_start_select_region_clean.assert_not_awaited()


async def test_map_without_zones_sends_nothing(hass: HomeAssistant) -> None:
    hub, entity_id, _ = _mower(hass, "m1", set())
    _async_register_services(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, {"entity_id": entity_id, "region_ids": [1]})
    assert err.value.translation_key == "no_zones"
    hub.async_start_select_region_clean.assert_not_awaited()


async def test_one_bad_target_blocks_all_targets(hass: HomeAssistant) -> None:
    good, good_id, _ = _mower(hass, "m1", {1})
    bad, bad_id, _ = _mower(hass, "m2", {2})
    _async_register_services(hass)
    with pytest.raises(ServiceValidationError):
        await _call(hass, {"entity_id": [good_id, bad_id], "region_ids": [1]})
    good.async_start_select_region_clean.assert_not_awaited()
    bad.async_start_select_region_clean.assert_not_awaited()


@pytest.mark.parametrize("region_ids", [[], [True], [1.5], [-1]])
async def test_schema_rejects_bad_ids(hass: HomeAssistant, region_ids: list) -> None:
    hub, entity_id, _ = _mower(hass, "m1", {0, 1})
    _async_register_services(hass)
    with pytest.raises(vol.Invalid):
        await _call(hass, {"entity_id": entity_id, "region_ids": region_ids})
    hub.async_start_select_region_clean.assert_not_awaited()


# ---------------------------------------------------------------------------
# target resolution
# ---------------------------------------------------------------------------


async def test_device_target(hass: HomeAssistant) -> None:
    hub, _, device_id = _mower(hass, "m1", {1})
    other, _, _ = _mower(hass, "m2", {1})
    _async_register_services(hass)
    await _call(hass, {"device_id": device_id, "region_ids": [1]})
    hub.async_start_select_region_clean.assert_awaited_once_with([1])
    other.async_start_select_region_clean.assert_not_awaited()


async def test_area_target_reaches_only_terramow_mowers(hass: HomeAssistant) -> None:
    area = ar.async_get(hass).async_create("Garden")
    hub, _, _ = _mower(hass, "m1", {1}, area_id=area.id)
    # A foreign entity in the same area is ignored, not an error.
    foreign = er.async_get(hass).async_get_or_create("light", "hue", "lamp")
    er.async_get(hass).async_update_entity(foreign.entity_id, area_id=area.id)
    _async_register_services(hass)
    await _call(hass, {"area_id": area.id, "region_ids": [1]})
    hub.async_start_select_region_clean.assert_awaited_once_with([1])


async def test_entity_match_all(hass: HomeAssistant) -> None:
    first, _, _ = _mower(hass, "m1", {1})
    second, _, _ = _mower(hass, "m2", {1})
    _async_register_services(hass)
    await _call(hass, {"entity_id": "all", "region_ids": [1]})
    first.async_start_select_region_clean.assert_awaited_once_with([1])
    second.async_start_select_region_clean.assert_awaited_once_with([1])


async def test_entities_of_one_device_run_it_once(hass: HomeAssistant) -> None:
    hub, entity_id, _ = _mower(hass, "m1", {1})
    _async_register_services(hass)
    sensor_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, "m1-battery")
    await _call(hass, {"entity_id": [entity_id, sensor_id], "region_ids": [1]})
    hub.async_start_select_region_clean.assert_awaited_once_with([1])


async def test_target_without_mowers(hass: HomeAssistant) -> None:
    area = ar.async_get(hass).async_create("Empty")
    _async_register_services(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, {"area_id": area.id, "region_ids": [1]})
    assert err.value.translation_key == "mower_not_found"


async def test_other_services_accept_device_targets(hass: HomeAssistant) -> None:
    hub, _, device_id = _mower(hass, "m1", {1})
    _async_register_services(hass)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_DELETE_SCHEDULE,
        {"device_id": device_id, "item_id": 3},
        blocking=True,
    )
    hub.async_delete_schedule.assert_awaited_once_with(3)


# ---------------------------------------------------------------------------
# HA-version shim: helpers.target (new) vs helpers.service (legacy)
# ---------------------------------------------------------------------------


def _selected() -> SimpleNamespace:
    return SimpleNamespace(referenced={"a.x"}, indirectly_referenced={"b.y"})


def test_referenced_ids_with_target_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("homeassistant.helpers.target")
    seen: dict[str, Any] = {}

    class TargetSelection:
        def __init__(self, data: Any) -> None:
            seen["data"] = data

    def extract(hass: Any, selection: Any) -> SimpleNamespace:
        seen["selection"] = selection
        return _selected()

    module.TargetSelection = TargetSelection  # type: ignore[attr-defined]
    module.async_extract_referenced_entity_ids = extract  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.target", module)
    call = ServiceCall(MagicMock(), DOMAIN, "x", {"device_id": ["d"]})

    assert _referenced_entity_ids(MagicMock(), call) == ({"a.x"}, {"b.y"})
    assert seen["data"] == {"device_id": ["d"]}
    assert isinstance(seen["selection"], TargetSelection)


def test_referenced_ids_with_legacy_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    import homeassistant.helpers.service as service_helpers

    # ``None`` in sys.modules makes the import raise ImportError.
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.target", None)
    legacy = MagicMock(return_value=_selected())
    monkeypatch.setattr(
        service_helpers, "async_extract_referenced_entity_ids", legacy, raising=False
    )
    call = ServiceCall(MagicMock(), DOMAIN, "x", {"area_id": ["a"]})

    assert _referenced_entity_ids(MagicMock(), call) == ({"a.x"}, {"b.y"})
    legacy.assert_called_once()
