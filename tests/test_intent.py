"""Tests for the Assist "mow a zone" intent.

The matching is the part that decides whether a voice command mows the right
patch of grass, so it is pinned hard: exact and forgiving matches must work,
and ambiguity must never be resolved by guessing.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.intent import (
    INTENT_MOW_ZONE,
    MowZoneIntentHandler,
    async_setup_intents,
    match_zone,
    normalize_name,
    zone_choices,
)

HOST = "192.0.2.10"

MAP_DATA: dict[str, Any] = {
    "id": 1,
    "regions": [
        {
            "name": "Garden",
            "sub_regions": [
                {"id": 1, "name": "Front Lawn."},
                {"id": 2, "name": "Vorgärten"},
                {"id": 3, "name": "Back"},
                {"id": 4, "name": "Back Terrace"},
            ],
        }
    ],
}

CHOICES = zone_choices(MAP_DATA)


# ---------------------------------------------------------------------------
# name matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "folded"),
    [
        ("Front Lawn.", "front lawn"),
        ("Vorgärten", "vorgarten"),
        ("  Side   Yard  ", "side yard"),
        ("Zone-3", "zone 3"),
        ("ÉCOLE", "ecole"),
        ("", ""),
    ],
)
def test_normalize_name(raw: str, folded: str) -> None:
    assert normalize_name(raw) == folded


def test_zone_choices_skips_unusable_entries() -> None:
    assert CHOICES == [
        (1, "Front Lawn."),
        (2, "Vorgärten"),
        (3, "Back"),
        (4, "Back Terrace"),
    ]
    assert zone_choices({"regions": ["x"]}) == []
    assert zone_choices({"regions": [{"sub_regions": ["x"]}]}) == []
    # Unnamed or blank zones cannot be spoken, so they are not offered.
    assert zone_choices(
        {"regions": [{"sub_regions": [{"id": 1, "name": "  "}, {"id": 2}]}]}
    ) == []
    assert zone_choices(
        {"regions": [{"sub_regions": [{"id": True, "name": "x"}]}]}
    ) == []


def test_an_exact_match_wins() -> None:
    assert match_zone("front lawn", CHOICES)[0] == 1
    # Punctuation and accents in the device's name do not have to be spoken.
    assert match_zone("Front Lawn", CHOICES)[0] == 1
    assert match_zone("vorgarten", CHOICES)[0] == 2


def test_an_exact_match_beats_a_longer_name_containing_it() -> None:
    """"Back" must mow Back, not Back Terrace."""
    assert match_zone("back", CHOICES)[0] == 3


def test_a_unique_partial_match_is_accepted() -> None:
    assert match_zone("terrace", CHOICES)[0] == 4


def test_an_ambiguous_match_is_refused() -> None:
    """Two zones contain "lawn": acting on either would be a coin flip."""
    choices = [(1, "Front Lawn"), (2, "Back Lawn")]
    zone_id, names = match_zone("lawn", choices)
    assert zone_id is None
    assert names == ["Front Lawn", "Back Lawn"]


def test_an_unknown_or_empty_name_is_refused() -> None:
    assert match_zone("greenhouse", CHOICES)[0] is None
    assert match_zone("   ", CHOICES)[0] is None
    assert match_zone("front lawn", [])[0] is None


# ---------------------------------------------------------------------------
# the intent handler
# ---------------------------------------------------------------------------


def _hub(hass: HomeAssistant, map_data: dict[str, Any] | None = None) -> TerraMowHub:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value = MagicMock(rc=0)
    hub._map_data = json.loads(json.dumps(map_data if map_data is not None else MAP_DATA))
    hub.async_start_select_region_clean = AsyncMock()  # type: ignore[method-assign]
    return hub


def _entries(hass: HomeAssistant, *hubs: TerraMowHub | None) -> None:
    """Stand in for the config entries the handler walks."""
    entries = []
    for hub in hubs:
        basic_data = hub.basic_data if hub is not None else None
        entries.append(MagicMock(runtime_data=basic_data))
    hass.config_entries.async_entries = MagicMock(return_value=entries)  # type: ignore[method-assign]


async def _handle(hass: HomeAssistant, zone: str) -> intent.IntentResponse:
    await async_setup_intents(hass)
    return await intent.async_handle(
        hass, "test", INTENT_MOW_ZONE, {"zone": {"value": zone}}
    )


def _speech(response: intent.IntentResponse) -> str:
    return str(response.speech["plain"]["speech"])


async def test_a_named_zone_is_mowed(hass: HomeAssistant) -> None:
    hub = _hub(hass)
    _entries(hass, hub)

    response = await _handle(hass, "front lawn")

    hub.async_start_select_region_clean.assert_awaited_once_with([1])
    assert "front lawn" in _speech(response).lower()


async def test_an_unknown_zone_lists_the_real_names(hass: HomeAssistant) -> None:
    """Refusing is only useful if it says what could have been asked for."""
    hub = _hub(hass)
    _entries(hass, hub)

    response = await _handle(hass, "greenhouse")

    hub.async_start_select_region_clean.assert_not_awaited()
    speech = _speech(response)
    assert "Front Lawn." in speech
    assert "Back Terrace" in speech


async def test_a_mower_without_zones_says_so(hass: HomeAssistant) -> None:
    hub = _hub(hass, {"id": 1, "regions": []})
    _entries(hass, hub)

    response = await _handle(hass, "front lawn")

    hub.async_start_select_region_clean.assert_not_awaited()
    assert "not reported any zones" in _speech(response)


async def test_no_connected_mower_says_so(hass: HomeAssistant) -> None:
    _entries(hass, None)
    response = await _handle(hass, "front lawn")
    assert "not connected" in _speech(response)


async def test_the_mower_that_knows_the_zone_is_chosen(hass: HomeAssistant) -> None:
    """With two mowers, the one whose map has the zone is the one meant."""
    front = _hub(hass, {"id": 1, "regions": [{"sub_regions": [{"id": 7, "name": "Front"}]}]})
    back = _hub(hass, {"id": 2, "regions": [{"sub_regions": [{"id": 9, "name": "Orchard"}]}]})
    _entries(hass, front, back)

    await _handle(hass, "orchard")

    front.async_start_select_region_clean.assert_not_awaited()
    back.async_start_select_region_clean.assert_awaited_once_with([9])


async def test_the_intent_is_registered_once(hass: HomeAssistant) -> None:
    await async_setup_intents(hass)
    await async_setup_intents(hass)  # a second config entry must not blow up

    handler = MowZoneIntentHandler()
    assert handler.intent_type == INTENT_MOW_ZONE
    assert handler.description
