from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, TerraMowConfigEntry
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin, safe_write_ha_state

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow binary sensor entities."""
    basic_data = config_entry.runtime_data

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

        # Unofficial / reverse-engineered diagnostic sensors
        CellularEnabledSensor(basic_data, hass),
        DefoggerHeatingSensor(basic_data, hass),
        IlluminationLightSensor(basic_data, hass),
        DaylightSensor(basic_data, hass),
        ExtremeWeatherSensor(basic_data, hass),
        CliffDetectionSensor(basic_data, hass),
        SlopeDetectionSensor(basic_data, hass),
        AfterRainAutoResumeSensor(basic_data, hass),
        ForceSingleBaseStationSensor(basic_data, hass),
        ForceCellularNetworkSensor(basic_data, hass),
        ManualMappingRelocationSensor(basic_data, hass),
        ManualMappingTakeoverSensor(basic_data, hass),
        ManualMappingBoundaryClosedSensor(basic_data, hass),
        StateFlag134Sensor(basic_data, hass),
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
        _LOGGER.debug("TerraMowChargingSensor entity created") # Callback is no longer needed here

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

    # RUNNING (on = upgrade running), not UPDATE: this reflects an in-progress
    # firmware install, whereas device_class=update reads as "update available".
    _attr_device_class = BinarySensorDeviceClass.RUNNING
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
        _LOGGER.debug("TerraMowProblemSensor entity created")

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
        _LOGGER.debug("TerraMowRainSensor entity created")

    _unique_id_suffix = "rain_detected"

    @property
    def is_on(self) -> bool | None:
        """Return true if the back-to-station reason is raining."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None
        return bool(
            self.basic_data.lawn_mower.back_to_station_reason
            == "BACK_TO_STATION_REASON_RAINING"
        )


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
    _map_status_field = "is_map_detected"
    _unique_id_suffix = "map_detected"


class TerraMowMapBuildableBinarySensor(_MapStatusBinarySensorBase):
    """True when the device is in a state where a build-map command would be accepted."""

    _attr_translation_key = "map_buildable"
    _map_status_field = "is_able_to_run_build_map"
    _unique_id_suffix = "map_buildable"


class TerraMowMapBackingUpBinarySensor(_MapStatusBinarySensorBase):
    """True while a map backup is in progress."""

    _attr_translation_key = "map_backing_up"
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
    _task_status_field = "is_saving_data"
    _unique_id_suffix = "saving_data"


class TerraMowDataConversionBinarySensor(_TaskStatusBinarySensorBase):
    """True while a data compatibility conversion is in progress."""

    _attr_translation_key = "data_conversion"
    _task_status_field = "is_data_conversion_in_progress"
    _unique_id_suffix = "data_conversion"


class CellularEnabledSensor(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Whether the cellular/4G modem is enabled (dp_135, unofficial).

    Only present on models with a cellular modem; ``None`` until dp_135 arrives.
    See ``docs/en/developers/data_point_unofficial.md``.
    """

    _push_dp_ids = (135,)
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "cellular_enabled"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unique_id_suffix = "cellular_enabled"

    @property
    def is_on(self) -> bool | None:
        """Return whether cellular is enabled."""
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower or not lawn_mower.cellular_info:
            return None
        return bool(lawn_mower.cellular_info.get("is_enabled"))


class _EnvironmentBinarySensorBase(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Base for the dp_152 environment binary sensors (unofficial)."""

    _push_dp_ids = (152,)
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Field read from environment_info and whether its boolean is inverted.
    _field = ""
    _invert = False

    @property
    def is_on(self) -> bool | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower or not lawn_mower.environment_info:
            return None
        value = bool(lawn_mower.environment_info.get(self._field))
        return not value if self._invert else value


class DefoggerHeatingSensor(_EnvironmentBinarySensorBase):
    """True while the station defogger is heating (dp_152)."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_translation_key = "defogger_heating"
    _field = "is_defogger_heating"
    _unique_id_suffix = "defogger_heating"


class IlluminationLightSensor(_EnvironmentBinarySensorBase):
    """True while the robot's illumination light is on (dp_152)."""

    _attr_device_class = BinarySensorDeviceClass.LIGHT
    _attr_translation_key = "illumination_light"
    _field = "is_illuminate_light_on"
    _unique_id_suffix = "illumination_light"


class DaylightSensor(_EnvironmentBinarySensorBase):
    """True while the robot considers it daytime (dp_152).

    Derived from ``is_not_in_daylight_period`` (inverted).
    """

    _attr_translation_key = "daylight"
    _field = "is_not_in_daylight_period"
    _invert = True
    _unique_id_suffix = "daylight"


class ExtremeWeatherSensor(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Extreme-weather warning (dp_157, unofficial).

    ``has_extream_weather`` (device spelling); an optional info URL is exposed
    as an attribute. See ``docs/en/developers/data_point_unofficial.md``.
    """

    _push_dp_ids = (157,)
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_translation_key = "extreme_weather"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unique_id_suffix = "extreme_weather"

    @property
    def is_on(self) -> bool | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower or not lawn_mower.weather_info:
            return None
        return bool(lawn_mower.weather_info.get("has_extream_weather"))

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower or not lawn_mower.weather_info:
            return {}
        url = lawn_mower.weather_info.get("extream_weather_info_url")
        return {"info_url": url} if isinstance(url, str) and url else {}


class _AdvancedSettingBinarySensorBase(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Base for the dp_150 advanced-setting binary sensors (unofficial, read-only).

    Reads a nested boolean via ``_path`` from the advanced-settings block.
    """

    _push_dp_ids = (150,)
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _path: tuple[str, ...] = ()

    @property
    def is_on(self) -> bool | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower or not lawn_mower.advanced_settings:
            return None
        node: object = lawn_mower.advanced_settings
        for key in self._path:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        return node if isinstance(node, bool) else None


class CliffDetectionSensor(_AdvancedSettingBinarySensorBase):
    """Whether cliff detection is enabled (dp_150)."""

    _attr_translation_key = "cliff_detection"
    _path = ("enable_cliff_detection", "value")
    _unique_id_suffix = "cliff_detection"


class SlopeDetectionSensor(_AdvancedSettingBinarySensorBase):
    """Whether slope detection is enabled (dp_150)."""

    _attr_translation_key = "slope_detection"
    _path = ("enable_slope_detection", "value")
    _unique_id_suffix = "slope_detection"


class AfterRainAutoResumeSensor(_AdvancedSettingBinarySensorBase):
    """Whether the mower auto-resumes after rain (dp_150)."""

    _attr_translation_key = "after_rain_auto_resume"
    _path = ("after_rain_stop_setting", "enable_auto_resume")
    _unique_id_suffix = "after_rain_auto_resume"


class ForceSingleBaseStationSensor(_AdvancedSettingBinarySensorBase):
    """Whether single-base-station mode is forced (dp_150)."""

    _attr_translation_key = "force_single_base_station"
    _attr_entity_registry_enabled_default = False
    _path = ("force_single_base_station_mode", "value")
    _unique_id_suffix = "force_single_base_station"


class ForceCellularNetworkSensor(_AdvancedSettingBinarySensorBase):
    """Whether the cellular network is forced (dp_150)."""

    _attr_translation_key = "force_cellular_network"
    _attr_entity_registry_enabled_default = False
    _path = ("force_cellular_network", "value")
    _unique_id_suffix = "force_cellular_network"


class _ManualMappingBinarySensorBase(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Base for the dp_152 ``manual_mapping`` flags (unofficial, read-only).

    Transient states during manual mapping; off by default. Set ``_field``.
    """

    _push_dp_ids = (152,)
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _field = ""

    @property
    def is_on(self) -> bool | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower:
            return None
        manual = lawn_mower.environment_info.get("manual_mapping")
        if not isinstance(manual, dict):
            return None
        value = manual.get(self._field)
        return value if isinstance(value, bool) else None


class ManualMappingRelocationSensor(_ManualMappingBinarySensorBase):
    """Manual mapping needs relocation (dp_152)."""

    _attr_translation_key = "manual_mapping_relocation"
    _field = "need_relocation"
    _unique_id_suffix = "manual_mapping_relocation"


class ManualMappingTakeoverSensor(_ManualMappingBinarySensorBase):
    """Manual mapping needs takeover (dp_152)."""

    _attr_translation_key = "manual_mapping_takeover"
    _field = "need_takeover"
    _unique_id_suffix = "manual_mapping_takeover"


class ManualMappingBoundaryClosedSensor(_ManualMappingBinarySensorBase):
    """Manual mapping boundary is closed (dp_152)."""

    _attr_translation_key = "manual_mapping_boundary_closed"
    _field = "is_boundary_closed"
    _unique_id_suffix = "manual_mapping_boundary_closed"


class StateFlag134Sensor(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Undecoded binary flag (dp_134, unofficial).

    The device sends ``{"enum_value":0|1}`` which toggles during operation; its
    meaning is unknown. Surfaced as a diagnostic, disabled-by-default binary
    sensor purely so the flag can be correlated with mower behaviour and
    decoded. ``1`` → on, ``0`` → off, anything else → unknown.
    See ``docs/en/developers/data_point_unofficial.md``.
    """

    _push_dp_ids = (134,)
    _attr_translation_key = "state_flag_134"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _unique_id_suffix = "state_flag_134"

    @property
    def is_on(self) -> bool | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower:
            return None
        value = lawn_mower.state_flag_134.get("enum_value")
        if value == 0 or value == 1:
            return bool(value == 1)
        return None
