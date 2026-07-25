"""Image platform: a frozen report of the last finished mow session.

The map camera shows what the mower is doing *now*. This entity shows what it
did *last*: the lawn with the finished session's mow track shaded in, plus a
ribbon carrying the session's own numbers (area, duration, how it ended).

It is the image you attach to a "mowing finished" notification — a live camera
frame taken minutes later would already show the mower parked on an empty map,
because the device clears its path and counters when a session ends.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import TerraMowBasicData, TerraMowConfigEntry
from .const import (
    CONF_MAP_RESOLUTION,
    CONF_MAP_THEME,
    DEFAULT_MAP_RESOLUTION,
    DEFAULT_MAP_THEME,
)
from .entity import TerraMowEntity
from .entity_utils import safe_write_ha_state
from .map_render import render_mow_report
from .map_scene import build_scene

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow image entity."""
    theme = config_entry.options.get(CONF_MAP_THEME, DEFAULT_MAP_THEME)
    resolution = config_entry.options.get(CONF_MAP_RESOLUTION, DEFAULT_MAP_RESOLUTION)
    async_add_entities(
        [
            MowReportImage(
                config_entry.runtime_data, hass, theme=theme, resolution=resolution
            )
        ]
    )


class MowReportImage(TerraMowEntity, ImageEntity):
    """The last finished mow session, rendered once and held.

    The bytes are rendered from the hub's session snapshot and cached against
    that snapshot's timestamp, so the picture keeps showing the session it
    describes even after the mower has started the next one.
    """

    _attr_translation_key = "mow_report"
    _attr_content_type = "image/png"

    _unique_id_suffix = "mow_report"

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
        *,
        theme: str = DEFAULT_MAP_THEME,
        resolution: int = DEFAULT_MAP_RESOLUTION,
    ) -> None:
        # ImageEntity.__init__ needs ``hass`` while TerraMowEntity.__init__
        # takes none, and both would run through the same super() chain — so
        # the base's two attribute assignments are inlined here instead.
        ImageEntity.__init__(self, hass)
        self.basic_data = basic_data
        self.host = basic_data.host
        self.hass = hass
        self._theme = theme
        self._resolution = resolution
        # (finished_at, png) of the render currently held.
        self._rendered: tuple[Any, bytes] | None = None

    async def async_added_to_hass(self) -> None:
        """Refresh when a session ends (dp_107 carries the end-of-job frame)."""
        await super().async_added_to_hass()
        lawn_mower = self.basic_data.lawn_mower
        if lawn_mower is None:
            return
        for dp_id in (107, 113):
            self.async_on_remove(
                lawn_mower.register_callback(dp_id, self._handle_push_update)
            )

    async def _handle_push_update(self, _payload: str) -> None:
        report = self._report()
        held = self._rendered
        if report is not None and (held is None or held[0] != report["finished_at"]):
            # A newer session ended: drop the held render and let Home
            # Assistant fetch the new one.
            self._rendered = None
            self._attr_image_last_updated = report["finished_at"]
            safe_write_ha_state(self)

    def _report(self) -> dict[str, Any] | None:
        lawn_mower = self.basic_data.lawn_mower
        return None if lawn_mower is None else lawn_mower.last_mow_report

    @property
    def available(self) -> bool:
        """Available once a session has ended in this Home Assistant run."""
        return super().available and self._report() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The session's own numbers, for notification templates."""
        report = self._report()
        if report is None:
            return {}
        finished_at = report["finished_at"]
        return {
            "outcome": report["outcome"],
            "finished_at": finished_at.isoformat(),
            "area_m2": report["area_m2"],
            "total_area_m2": report["total_area_m2"],
            "duration_min": report["duration_min"],
            "job_type": report["job_type"],
            "map_id": report["map_id"],
        }

    async def async_image(self) -> bytes | None:
        """Return the report PNG, rendering it once per session."""
        report = self._report()
        if report is None:
            return None
        held = self._rendered
        if held is not None and held[0] == report["finished_at"]:
            return held[1]
        png = await self.hass.async_add_executor_job(self._render, report)
        self._rendered = (report["finished_at"], png)
        return png

    def _render(self, report: dict[str, Any]) -> bytes:
        """Render the report (executor: supersampled drawing is CPU-bound)."""
        lawn_mower = self.basic_data.lawn_mower
        map_data = lawn_mower.map_data if lawn_mower else {}
        scene = build_scene(
            map_data,
            {},
            {},
            True,  # the mow track is the point of this image
            session_path_segments=report["coverage_segments"],
        )
        return render_mow_report(
            scene,
            map_data,
            report=report,
            theme=self._theme,
            language=self.hass.config.language,
            output_resolution=self._resolution,
            finished_local=dt_util.as_local(report["finished_at"]),
        )
