"""Assist intent: mow a zone by the name it has on the map.

Home Assistant's built-in sentences can start and stop a lawn mower, but they
know nothing about zones — and zones are the thing worth saying out loud.
"Mow the front lawn" is a sentence; "call terramow.start_select_region with
region_ids [3]" is not.

This registers an intent that resolves a spoken zone name against the map the
mower reported and starts a selective mow. Matching is deliberately forgiving
about case, punctuation and accents, because a voice pipeline's transcript
rarely matches a name typed in the vendor app exactly — but it never guesses:
an unknown name, or one that matches several zones, is answered with what the
zones are actually called rather than mowing something at random.

The sentences that reach this intent live in the user's
``config/custom_sentences/`` directory; ready-made files ship in
``docs/custom_sentences/`` (see the dashboard guide).
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import intent

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

INTENT_MOW_ZONE = "TerraMowMowZone"

ATTR_ZONE = "zone"


def normalize_name(name: str) -> str:
    """Fold a zone name for matching: case, accents and punctuation.

    A transcript says "front lawn" for a zone named "Front Lawn." and
    "vorgarten" for "Vorgärten" — folding all three away makes the common
    case work without loosening the match to fuzzy guessing.
    """
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(
        char if char.isalnum() or char.isspace() else " " for char in stripped
    ).split())


def zone_choices(map_data: dict[str, Any]) -> list[tuple[int, str]]:
    """Every (zone id, name) pair the mower's map offers."""
    choices: list[tuple[int, str]] = []
    for region in map_data.get("regions") or []:
        if not isinstance(region, dict):
            continue
        for sub in region.get("sub_regions") or []:
            if not isinstance(sub, dict):
                continue
            zone_id = sub.get("id")
            name = sub.get("name")
            if (
                isinstance(zone_id, int)
                and not isinstance(zone_id, bool)
                and isinstance(name, str)
                and name.strip()
            ):
                choices.append((zone_id, name.strip()))
    return choices


def match_zone(
    spoken: str, choices: list[tuple[int, str]]
) -> tuple[int | None, list[str]]:
    """Resolve a spoken zone name; returns (id, all names) with id None on miss.

    An exact (folded) match wins outright. Failing that, a name that contains
    the spoken words counts — but only if exactly one does, because acting on
    an ambiguous match is worse than asking again.
    """
    names = [name for _, name in choices]
    wanted = normalize_name(spoken)
    if not wanted:
        return (None, names)
    exact = [zone_id for zone_id, name in choices if normalize_name(name) == wanted]
    if len(exact) == 1:
        return (exact[0], names)
    partial = [zone_id for zone_id, name in choices if wanted in normalize_name(name)]
    if len(partial) == 1:
        return (partial[0], names)
    return (None, names)


class MowZoneIntentHandler(intent.IntentHandler):
    """Start a selective mow for the zone named in the sentence."""

    intent_type = INTENT_MOW_ZONE
    description = "Mows a named zone of the TerraMow lawn"
    slot_schema = {vol.Required(ATTR_ZONE): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        spoken = slots[ATTR_ZONE]["value"]
        response = intent_obj.create_response()

        hubs = [
            entry.runtime_data.lawn_mower
            for entry in hass.config_entries.async_entries(DOMAIN)
            if getattr(entry, "runtime_data", None) is not None
            and entry.runtime_data.lawn_mower is not None
        ]
        if not hubs:
            response.async_set_speech("The mower is not connected.")
            return response

        # With several mowers configured, the one whose map knows the zone is
        # the one that was meant.
        for hub in hubs:
            zone_id, names = match_zone(spoken, zone_choices(hub.map_data))
            if zone_id is not None:
                await hub.async_start_select_region_clean([zone_id])
                response.async_set_speech(f"Mowing {spoken}.")
                return response

        known = zone_choices(hubs[0].map_data)
        if not known:
            response.async_set_speech("The mower has not reported any zones yet.")
        else:
            response.async_set_speech(
                "I don't know a zone called "
                f"{spoken}. The zones are: {', '.join(name for _, name in known)}."
            )
        return response


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Register the TerraMow intents (idempotent across config entries)."""
    intent.async_register(hass, MowZoneIntentHandler())
    _LOGGER.debug("Registered the %s intent", INTENT_MOW_ZONE)
