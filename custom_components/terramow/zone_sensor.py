"""Per-zone "last mowed" sensors, created from the map's sub-regions.

The map card already shades how much of each zone the current cycle has
covered, but that lives inside the card: an automation cannot ask "has the
terrace been mowed in the last ten days?".

This adds one timestamp sensor per zone. Its value is the last time the
device reported a pose *inside* that zone's boundary — an observation, not an
inferred schedule — with the running cycle's coverage fraction along as an
attribute.

Zones only exist once the mower has sent its map, and they change when the
map does, so the entities are created on the map callback rather than at
platform setup, and each is keyed by the zone id so a reload reuses the same
registry entry.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import TerraMowConfigEntry
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin, safe_write_ha_state
from .map_render import CUTTING_WIDTH_MM
from .map_scene import coverage_ratios_for_zones, zone_boundaries_from_map

if TYPE_CHECKING:
    from . import TerraMowBasicData

_LOGGER = logging.getLogger(__name__)


def zone_records(map_info: dict[str, Any]) -> list[tuple[int, str]]:
    """The (id, display name) of every sub-region in a map payload.

    The name falls back to the parent region's, then to the bare id, because
    the device leaves sub-region names empty on maps that were never renamed
    in the app.
    """
    records: list[tuple[int, str]] = []
    for region in map_info.get("regions") or []:
        if not isinstance(region, dict):
            continue
        region_name = region.get("name")
        for sub in region.get("sub_regions") or []:
            if not isinstance(sub, dict):
                continue
            zone_id = sub.get("id")
            if not isinstance(zone_id, int) or isinstance(zone_id, bool):
                continue
            name = sub.get("name") or region_name or f"#{zone_id}"
            records.append((zone_id, str(name)))
    return records


def async_setup_zone_sensors(
    config_entry: TerraMowConfigEntry,
    hass: HomeAssistant,
    basic_data: TerraMowBasicData,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create a zone sensor per sub-region, now and whenever the map changes.

    The map subscription is handed to ``config_entry.async_on_unload``: the
    callback closes over ``basic_data``, which reaches the hub, so a
    subscription surviving an unload would keep the whole hub alive.
    """
    lawn_mower = basic_data.lawn_mower
    if lawn_mower is None:
        return
    known: set[int] = set()
    # The map callback is dispatched as a task, so it can land after the entry
    # has begun unloading. Entities added then are never tracked for removal,
    # and their pose subscriptions would keep the whole hub alive — so the
    # window is closed explicitly rather than left to the race.
    active = True

    def _stop() -> None:
        nonlocal active
        active = False

    async def _on_map(map_info: dict[str, Any]) -> None:
        if not active:
            return
        fresh = [
            ZoneLastMowedSensor(basic_data, hass, zone_id, name)
            for zone_id, name in zone_records(map_info)
            if zone_id not in known
        ]
        if not fresh:
            return
        known.update(sensor.zone_id for sensor in fresh)
        _LOGGER.debug("Adding %d zone sensors", len(fresh))
        async_add_entities(fresh)

    # The hub replays the cached map to a fresh callback, so a map that
    # arrived before this platform was set up still creates its sensors.
    config_entry.async_on_unload(lawn_mower.register_map_callback(_on_map))
    config_entry.async_on_unload(_stop)


class ZoneLastMowedSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """When the mower was last seen inside one zone.

    Derived state (see the AGENTS.md contract): built from poses the device
    reported, stamped only while the mower is actually inside the boundary.
    It is cleared when the map changes — the zone ids belong to that map —
    and is otherwise deliberately long-lived: "not mowed for ten days" is the
    whole point, so unlike the display latches it has no decay.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "zone_last_mowed"

    _push_map_info = True

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
        zone_id: int,
        name: str,
    ) -> None:
        super().__init__(basic_data, hass)
        self.zone_id = zone_id
        self._attr_translation_placeholders = {"zone": name}
        self._unique_id_suffix = f"zone_{zone_id}_last_mowed"

    async def async_added_to_hass(self) -> None:
        """Also refresh on the pose stream, which is what moves the stamp."""
        await super().async_added_to_hass()
        hub = self.hub
        if hub:
            self.async_on_remove(hub.register_pose_callback(self._on_pose))

    async def _on_pose(self, _pose: dict[str, Any]) -> None:
        # The hub samples zone presence on an interval; a state write per pose
        # would be 2 Hz of churn, so only write when the stamp actually moved.
        if self._stamp() != self._last_written:
            self._last_written = self._stamp()
            safe_write_ha_state(self)

    _last_written: str | None = None

    def _stamp(self) -> str | None:
        hub = self.hub
        return None if hub is None else hub.zone_last_seen.get(self.zone_id)

    @property
    def native_value(self) -> datetime | None:
        stamp = self._stamp()
        return None if stamp is None else dt_util.parse_datetime(stamp)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The running cycle's coverage of this zone, when there is one."""
        hub = self.hub
        if hub is None:
            return {"zone_id": self.zone_id}
        ratios = coverage_ratios_for_zones(
            zone_boundaries_from_map(hub.map_data),
            hub.coverage_segments,
            CUTTING_WIDTH_MM,
        )
        return {"zone_id": self.zone_id, "cycle_coverage": ratios.get(self.zone_id)}
