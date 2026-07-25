"""Device tracker: the mower's position as real-world coordinates.

The mower reports where it is only in *map* coordinates — millimetres in a
screen-style frame whose origin and orientation are whatever the mapping run
happened to produce. That is enough to draw a map and useless for anything
geographic.

Given one anchor — the base station's real latitude/longitude and the compass
bearing the top of the map points to — those map coordinates become GPS
coordinates, and the mower shows up on Home Assistant's map alongside
everything else: zone triggers, proximity, "the mower left the property".

The projection is a local flat-earth approximation. Over a lawn (hundreds of
metres at most) its error is far below the mower's own positioning accuracy;
it is not meant for anything larger.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, TerraMowConfigEntry
from .const import (
    CONF_GPS_HEADING,
    CONF_GPS_LATITUDE,
    CONF_GPS_LONGITUDE,
    DEFAULT_GPS_HEADING,
    GPS_MIN_INTERVAL_SECONDS,
    GPS_MIN_MOVE_METERS,
)
from .entity import TerraMowEntity
from .entity_utils import safe_write_ha_state

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

# Metres per degree of latitude (WGS-84 mean). Longitude scales with the
# cosine of the latitude.
METERS_PER_DEGREE_LATITUDE = 111320.0


def project_pose(
    pose: dict[str, Any],
    station_pose: dict[str, Any] | None,
    *,
    anchor_latitude: float,
    anchor_longitude: float,
    heading: float,
) -> tuple[float, float] | None:
    """Project a map-frame pose onto latitude/longitude.

    ``heading`` is the compass bearing (degrees, 0 = north, clockwise) that
    the **top of the rendered map** points to — the direction a user reads off
    a satellite image when lining the lawn up.

    The map frame is screen-style: +X is to the right of the rendered map and
    +Y points *down* it. With the map's top at bearing H, +X therefore lies at
    H+90 and +Y at H+180, which is where the signs below come from.

    Returns None when either pose lacks usable coordinates.
    """
    origin = station_pose if isinstance(station_pose, dict) else None
    if origin is None:
        return None
    try:
        dx = float(pose["x"]) - float(origin["x"])
        dy = float(pose["y"]) - float(origin["y"])
    except (KeyError, TypeError, ValueError):
        return None

    theta = math.radians(heading)
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    # Millimetres in the map frame -> metres east/north of the anchor.
    east = (dx * cos_t - dy * sin_t) / 1000.0
    north = (-dx * sin_t - dy * cos_t) / 1000.0

    latitude = anchor_latitude + north / METERS_PER_DEGREE_LATITUDE
    # Guard the polar singularity so a nonsensical anchor cannot divide by ~0.
    scale = math.cos(math.radians(anchor_latitude))
    if abs(scale) < 1e-6:
        return (latitude, anchor_longitude)
    longitude = anchor_longitude + east / (METERS_PER_DEGREE_LATITUDE * scale)
    return (latitude, longitude)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the tracker, but only when an anchor has been configured."""
    options = config_entry.options
    latitude = options.get(CONF_GPS_LATITUDE)
    longitude = options.get(CONF_GPS_LONGITUDE)
    if latitude is None or longitude is None:
        # Without an anchor there is nothing to project onto; an entity that
        # can only ever report "unknown" would be noise.
        return
    async_add_entities(
        [
            TerraMowDeviceTracker(
                config_entry.runtime_data,
                hass,
                latitude=float(latitude),
                longitude=float(longitude),
                heading=float(options.get(CONF_GPS_HEADING, DEFAULT_GPS_HEADING)),
            )
        ]
    )


class TerraMowDeviceTracker(TerraMowEntity, TrackerEntity):
    """The mower's live position, projected onto the configured anchor.

    Throttled on purpose: the pose arrives at ~2 Hz, and a device_tracker
    that wrote state that often would fill the recorder with sub-centimetre
    jitter. A new position is published once the mower has moved
    ``GPS_MIN_MOVE_METERS`` or ``GPS_MIN_INTERVAL_SECONDS`` have passed —
    whichever comes first — plus always on the first fix.
    """

    _attr_translation_key = "mower_position"
    _attr_source_type = SourceType.GPS

    _unique_id_suffix = "device_tracker"

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
        *,
        latitude: float,
        longitude: float,
        heading: float,
    ) -> None:
        super().__init__(basic_data, hass)
        self._anchor_latitude = latitude
        self._anchor_longitude = longitude
        self._heading = heading
        self._position: tuple[float, float] | None = None
        self._published_at: float | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to the pose stream once the entity is really added."""
        await super().async_added_to_hass()
        hub = self.hub
        if hub:
            self.async_on_remove(hub.register_pose_callback(self._on_pose))

    async def _on_pose(self, pose: dict[str, Any]) -> None:
        hub = self.hub
        if hub is None:
            return
        position = project_pose(
            pose,
            hub.map_data.get("station_pose"),
            anchor_latitude=self._anchor_latitude,
            anchor_longitude=self._anchor_longitude,
            heading=self._heading,
        )
        if position is None:
            return
        if not self._should_publish(position):
            return
        self._position = position
        self._published_at = time.monotonic()
        safe_write_ha_state(self)

    def _should_publish(self, position: tuple[float, float]) -> bool:
        """Whether this fix is worth a state write (see the class docstring)."""
        previous = self._position
        if previous is None or self._published_at is None:
            return True
        if time.monotonic() - self._published_at >= GPS_MIN_INTERVAL_SECONDS:
            return True
        return self._distance_meters(previous, position) >= GPS_MIN_MOVE_METERS

    @staticmethod
    def _distance_meters(
        first: tuple[float, float], second: tuple[float, float]
    ) -> float:
        """Flat-earth distance between two nearby coordinates, in metres."""
        d_lat = (second[0] - first[0]) * METERS_PER_DEGREE_LATITUDE
        d_lon = (
            (second[1] - first[1])
            * METERS_PER_DEGREE_LATITUDE
            * math.cos(math.radians(first[0]))
        )
        return math.hypot(d_lat, d_lon)

    @property
    def latitude(self) -> float | None:
        return None if self._position is None else self._position[0]

    @property
    def longitude(self) -> float | None:
        return None if self._position is None else self._position[1]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the anchor, so a wrong-looking position can be diagnosed."""
        return {
            "anchor_latitude": self._anchor_latitude,
            "anchor_longitude": self._anchor_longitude,
            "map_heading": self._heading,
        }
