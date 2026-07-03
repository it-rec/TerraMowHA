from __future__ import annotations
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, DOMAIN
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin, safe_write_ha_state

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow binary sensor entities."""
    basic_data = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        TerraMowChargingSensor(basic_data, hass),
        NavigationLocatedSensor(basic_data, hass),
        FirmwareUpgradingSensor(basic_data, hass),
        PowerSwitchSensor(basic_data, hass),
        TerraMowProblemSensor(basic_data, hass),
        TerraMowRainSensor(basic_data, hass),
        TerraMowMapDetectedBinarySensor(basic_data, hass),
        TerraMowMapBuildableBinarySensor(basic_data, hass),
        TerraMowMapBackingUpBinarySensor(basic_data, hass),
        TerraMowSavingDataBinarySensor(basic_data, hass),
        TerraMowDataConversionBinarySensor(basic_data, hass),
    ]

    async_add_entities(entities)


class TerraMowChargingSensor(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Binary sensor for the TerraMow charging state."""

    _push_dp_ids = (108,)

    _attr_translation_key = "charging_state"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the charging sensor."""
        super().__init__(basic_data, hass)
        self._attr_is_on: bool | None = None
        _LOGGER.info("TerraMowChargingSensor entity created") # Callback is no longer needed here

    _unique_id_suffix = "charging_state"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        battery_status = self.basic_data.lawn_mower.battery_status
        charger_connected = battery_status.get('charger_connected')

        return bool(charger_connected) if charger_connected is not None else None


class NavigationLocatedSensor(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Binary sensor for whether the robot is navigation-located."""

    _push_dp_ids = (107,)

    _attr_translation_key = "navigation_located"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:crosshairs-gps"

    _unique_id_suffix = "navigation_located"

    @property
    def is_on(self) -> bool | None:
        """Return true if the robot is navigation-located."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        value = self.basic_data.lawn_mower.is_robot_navi_located
        return bool(value) if value is not None else None


class FirmwareUpgradingSensor(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Binary sensor for whether the robot firmware is upgrading."""

    _push_dp_ids = (107,)

    _attr_device_class = BinarySensorDeviceClass.UPDATE
    _attr_translation_key = "firmware_upgrading"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _unique_id_suffix = "firmware_upgrading"

    @property
    def is_on(self) -> bool | None:
        """Return true if the firmware is upgrading."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        value = self.basic_data.lawn_mower.is_upgrading
        return bool(value) if value is not None else None


class PowerSwitchSensor(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Binary sensor for the TerraMow power switch state."""

    _push_dp_ids = (108,)

    _attr_translation_key = "power_switch"
    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _unique_id_suffix = "power_switch"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        battery_status = self.basic_data.lawn_mower.battery_status
        is_switch_on = battery_status.get('is_switch_on')

        return bool(is_switch_on) if is_switch_on is not None else None


class TerraMowProblemSensor(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Binary sensor exposing the dp_107 has_error flag as a problem."""

    _push_dp_ids = (107,)

    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        super().__init__(basic_data, hass)
        _LOGGER.info("TerraMowProblemSensor entity created")

    _unique_id_suffix = "problem"

    @property
    def is_on(self) -> bool | None:
        """Return true if the robot reports an error."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None
        return bool(self.basic_data.lawn_mower.has_error)


class TerraMowRainSensor(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Binary sensor that signals when the robot returns due to rain."""

    _push_dp_ids = (107,)

    _attr_translation_key = "rain_detected"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        super().__init__(basic_data, hass)
        _LOGGER.info("TerraMowRainSensor entity created")

    _unique_id_suffix = "rain_detected"

    @property
    def is_on(self) -> bool | None:
        """Return true if the back-to-station reason is raining."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None
        return self.basic_data.lawn_mower.back_to_station_reason == "BACK_TO_STATION_REASON_RAINING"


class _MapStatusBinarySensorBase(TerraMowEntity, BinarySensorEntity):
    """Shared base for dp_117 map_status flag binary sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _map_status_field: str = ""
    _unique_id_suffix: str = ""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.basic_data.lawn_mower:
            self.basic_data.lawn_mower.register_callback(117, self._handle_dp_117)

    async def _handle_dp_117(self, _payload: str) -> None:
        safe_write_ha_state(self)

    @property
    def is_on(self) -> bool | None:
        if not self.basic_data.lawn_mower:
            return None
        map_status = self.basic_data.lawn_mower.map_status
        if not map_status:
            return None
        value = map_status.get(self._map_status_field)
        return bool(value) if value is not None else None


class TerraMowMapDetectedBinarySensor(_MapStatusBinarySensorBase):
    """True when the device reports an active/detected map."""

    _attr_translation_key = "map_detected"
    _attr_icon = "mdi:map-check"
    _map_status_field = "is_map_detected"
    _unique_id_suffix = "map_detected"


class TerraMowMapBuildableBinarySensor(_MapStatusBinarySensorBase):
    """True when the device is in a state where a build-map command would be accepted."""

    _attr_translation_key = "map_buildable"
    _attr_icon = "mdi:map-plus"
    _map_status_field = "is_able_to_run_build_map"
    _unique_id_suffix = "map_buildable"


class TerraMowMapBackingUpBinarySensor(_MapStatusBinarySensorBase):
    """True while a map backup is in progress."""

    _attr_translation_key = "map_backing_up"
    _attr_icon = "mdi:cloud-upload-outline"
    _map_status_field = "is_backing_up_map"
    _unique_id_suffix = "map_backing_up"


class _TaskStatusBinarySensorBase(TerraMowEntity, BinarySensorEntity):
    """Shared base for dp_107 task_status flag binary sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _task_status_field: str = ""
    _unique_id_suffix: str = ""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.basic_data.lawn_mower:
            self.basic_data.lawn_mower.register_callback(107, self._handle_dp_107)

    async def _handle_dp_107(self, _payload: str) -> None:
        safe_write_ha_state(self)

    @property
    def is_on(self) -> bool | None:
        if not self.basic_data.lawn_mower:
            return None
        task_status = self.basic_data.lawn_mower.task_status
        if not task_status:
            return None
        value = task_status.get(self._task_status_field)
        return bool(value) if value is not None else None


class TerraMowSavingDataBinarySensor(_TaskStatusBinarySensorBase):
    """True while the robot is saving data.

    Per the data point documentation the robot may not respond to
    operation commands while this flag is set.
    """

    _attr_translation_key = "saving_data"
    _attr_icon = "mdi:content-save-cog"
    _task_status_field = "is_saving_data"
    _unique_id_suffix = "saving_data"


class TerraMowDataConversionBinarySensor(_TaskStatusBinarySensorBase):
    """True while a data compatibility conversion is in progress."""

    _attr_translation_key = "data_conversion"
    _attr_icon = "mdi:database-sync"
    _task_status_field = "is_data_conversion_in_progress"
    _unique_id_suffix = "data_conversion"
