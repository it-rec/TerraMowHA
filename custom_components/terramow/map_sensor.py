from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfArea
from homeassistant.core import HomeAssistant

from . import TerraMowBasicData
from .const import to_ha_enum_state
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin, safe_write_ha_state

# Note: this module is not a platform of its own. sensor.py imports these
# classes and adds them from its async_setup_entry.

class TerraMowMapSensorBase(TerraMowEntity, SensorEntity):
    """Base class for map sensors."""

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        super().__init__(basic_data, hass)
        self._map_info: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """Register the map info callback once the entity is actually added.

        Registering here (with the unsubscribe handed to ``async_on_remove``)
        instead of in ``__init__`` means a disabled or removed entity no
        longer receives map pushes from the hub.
        """
        await super().async_added_to_hass()
        hub = self.hub
        if hub:
            self.async_on_remove(
                hub.register_map_callback(self._on_map_info)
            )

    async def _on_map_info(self, map_info: dict[str, Any]) -> None:
        """Handle a map info update."""
        self._map_info = map_info
        safe_write_ha_state(self)

class TerraMowMapStatusSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Map status sensor - uses dp_117 data."""

    _push_dp_ids = (117,)

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "map_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["map_state_empty", "map_state_incomplete", "map_state_complete"]

    _unique_id_suffix = "map_status"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        hub = self.hub
        if not hub:
            return None

        map_status = hub.map_status
        if not map_status:
            return None

        state = to_ha_enum_state(map_status.get('map_state'))
        return state if state in self._attr_options else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        hub = self.hub
        if not hub:
            return {}

        map_status = hub.map_status
        if not map_status:
            return {}

        return {
            'is_map_detected': map_status.get('is_map_detected', False),
            'map_id': map_status.get('map_id'),
            'map_number': map_status.get('map_number', 0),
            'is_backing_up_map': map_status.get('is_backing_up_map', False),
            'backup_map_id': map_status.get('backup_map_id'),
            'main_direction_angle': map_status.get('main_direction_angle'),
            'is_spot_mode_map': map_status.get('is_spot_mode_map', False),
            'spot_mode_map_number': map_status.get('spot_mode_map_number', 0),
            'is_able_to_run_build_map': map_status.get('is_able_to_run_build_map', False),
        }

class TerraMowMapAreaSensor(TerraMowMapSensorBase):
    """Map area sensor."""

    _attr_native_unit_of_measurement = UnitOfArea.SQUARE_METERS
    # SensorDeviceClass.AREA exists since HA 2024.12; stay None on older cores
    _attr_device_class = getattr(SensorDeviceClass, "AREA", None)
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "map_area"

    _unique_id_suffix = "map_area"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self._map_info:
            return None

        # total_area is in units of 0.1 square meters; convert to square meters
        total_area = self._map_info.get('total_area')
        if total_area is None:
            return None
        return round(float(total_area) / 10, 1)


class TerraMowCleanModeSensor(TerraMowMapSensorBase):
    """Clean mode sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "clean_mode"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["map_clean_info_mode_global", "map_clean_info_mode_select_region", "map_clean_info_mode_draw_region", "map_clean_info_mode_move_to_target_point"]

    _unique_id_suffix = "clean_mode"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self._map_info:
            return None

        clean_info = self._map_info.get('clean_info', {})
        mode = to_ha_enum_state(clean_info.get('mode', ''))

        return mode if mode in self._attr_options else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        if not self._map_info:
            return {}

        clean_info = self._map_info.get('clean_info', {})
        attrs = {}

        # Show detailed information depending on the working mode
        if 'select_region' in clean_info:
            region_ids = clean_info['select_region'].get('region_id', [])
            attrs['selected_regions'] = region_ids
            attrs['selected_regions_count'] = len(region_ids)

        return attrs
