from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfArea,
    UnitOfLength,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, TerraMowConfigEntry
from .const import (
    BASE_STATION_MAINTENANCE_CYCLE_MINUTES,
    BLADE_MAINTENANCE_CYCLE_MINUTES,
    MOW_SPEED_TYPES,
    to_ha_enum_state,
)
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin, safe_write_ha_state
from .hub import Mission, MissionState, SubMission

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

class BatterySensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Representation of the battery sensor."""

    _attr_translation_key = "battery"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # dp_8 carries the percentage, dp_108 the charge state/temperature
    # attributes; a push on either refreshes this sensor immediately.
    _push_dp_ids = (8, 108)

    _unique_id_suffix = "battery"

    @property
    def native_value(self) -> int | None:
        """Return the battery percentage (dp_8)."""
        lawn_mower = self.basic_data.lawn_mower
        if lawn_mower is None:
            return None
        return cast("int | None", lawn_mower.battery_level)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return {}

        battery_status = self.basic_data.lawn_mower.battery_status
        if not battery_status:
            return {}

        return {
            'state': battery_status.get('state', 'unknown'),
            'temperature': (battery_status.get('tempreture') or 'unknown').replace('TEMPRETURE', 'TEMPERATURE'),
            'charger_connected': battery_status.get('charger_connected', 'unknown'),
            'is_switch_on': battery_status.get('is_switch_on', 'unknown')
        }


class BatteryStateSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Battery state sensor - uses dp_108 data."""

    _push_dp_ids = (108,)

    _attr_translation_key = "battery_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "battery_state_discharge",
        "battery_state_charging",
        "battery_state_charged",
    ]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _unique_id_suffix = "battery_state"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        battery_status = self.basic_data.lawn_mower.battery_status
        if not battery_status:
            return None

        state = to_ha_enum_state(battery_status.get('state'))
        if state in self._attr_options:
            return cast("str", state)
        return None


class BatteryTemperatureStateSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Battery temperature state sensor - uses dp_108 data."""

    _push_dp_ids = (108,)

    _attr_translation_key = "battery_temperature_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "battery_tempreture_normal",
        "battery_tempreture_overheat",
        "battery_tempreture_underheat",
    ]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _unique_id_suffix = "battery_temperature_state"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        battery_status = self.basic_data.lawn_mower.battery_status
        if not battery_status:
            return None

        # Firmware reports the field as 'tempreture' (typo preserved).
        value = to_ha_enum_state(battery_status.get('tempreture'))
        if value in self._attr_options:
            return cast("str", value)
        return None


class TotalMowingTimeSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Total mowing time sensor - uses dp_124 data"""

    _push_dp_ids = (124,)

    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "total_mowing_time"

    _unique_id_suffix = "total_mowing_time"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        statistics_data = self.basic_data.lawn_mower.statistics_data
        if not statistics_data:
            return None

        return cast("int | None", statistics_data.get('duration'))


class TotalMowingJobsSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Total mowing jobs sensor - uses dp_124 data"""

    _push_dp_ids = (124,)

    _attr_native_unit_of_measurement = None
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "total_mowing_jobs"

    _unique_id_suffix = "total_mowing_jobs"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        statistics_data = self.basic_data.lawn_mower.statistics_data
        if not statistics_data:
            return None

        return cast("int | None", statistics_data.get('clean_times'))


class TotalMowedAreaSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Lifetime mowed area sensor - uses dp_124 data"""

    _push_dp_ids = (124,)

    _attr_native_unit_of_measurement = UnitOfArea.SQUARE_METERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "total_mowed_area"

    _unique_id_suffix = "total_mowed_area"

    @property
    def native_value(self) -> float | None:
        """Return the lifetime mowed area in square meters."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        statistics_data = self.basic_data.lawn_mower.statistics_data
        if not statistics_data:
            return None

        clean_area = statistics_data.get('clean_area')
        if clean_area is None:
            return None
        # The protocol unit is 0.1 square meters
        return round(float(clean_area) / 10, 1)


class CurrentSessionAreaSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Current session mowing area sensor - uses dp_113 data"""

    _push_dp_ids = (113,)

    _attr_native_unit_of_measurement = UnitOfArea.SQUARE_METERS
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "current_session_area"

    _unique_id_suffix = "current_session_area"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        current_work_data = self.basic_data.lawn_mower.current_work_data
        if not current_work_data:
            return None

        # clean_area is in units of 0.1 square meters; convert to square meters
        clean_area = current_work_data.get('clean_area', 0)
        return round(clean_area / 10, 1) if clean_area else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return {}

        current_work_data = self.basic_data.lawn_mower.current_work_data
        if not current_work_data:
            return {}

        attrs = {}
        work_type = current_work_data.get('type', '')
        if work_type:
            attrs['work_type'] = work_type

        total_area = current_work_data.get('total_area', 0)
        if total_area:
            attrs['total_area'] = round(total_area / 10, 1)

        is_completed = current_work_data.get('is_completed')
        if is_completed is not None:
            attrs['is_completed'] = is_completed

        return attrs


class CurrentSessionProgressSensor(TerraMowEntity, SensorEntity):
    """Progress (%) of the current session, derived from dp_113 clean_area/total_area."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "current_session_progress"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.basic_data.lawn_mower:
            self.basic_data.lawn_mower.register_callback(113, self._handle_dp_113)

    async def _handle_dp_113(self, _payload: str) -> None:
        safe_write_ha_state(self)

    _unique_id_suffix = "current_session_progress"

    @property
    def native_value(self) -> float | None:
        if not self.basic_data.lawn_mower:
            return None
        current_work_data = self.basic_data.lawn_mower.current_work_data
        if not current_work_data:
            return None
        total_area = current_work_data.get('total_area') or 0
        clean_area = current_work_data.get('clean_area') or 0
        if total_area <= 0:
            return None
        progress = 100.0 * clean_area / total_area
        # Cap at 100; the device occasionally reports clean_area > total_area
        # near the very end of a session.
        return round(min(progress, 100.0), 1)


class CurrentSessionTimeSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Current session mowing time sensor - uses dp_113 data"""

    _push_dp_ids = (113,)

    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "current_session_time"

    _unique_id_suffix = "current_session_time"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        current_work_data = self.basic_data.lawn_mower.current_work_data
        if not current_work_data:
            return None

        return cast("int | None", current_work_data.get('work_duration'))


class CurrentJobTypeSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Current job type sensor - uses dp_113 data"""

    _push_dp_ids = (113,)

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "map_area_type_none",
        "map_area_type_build_map",
        "map_area_type_cleaning",
        "map_area_type_build_map_and_cleaning",
        "map_area_type_select_region_cleaning",
        "map_area_type_draw_region_cleaning",
        "map_area_type_edge_trim_cleaning",
    ]
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "current_job_type"

    _unique_id_suffix = "current_job_type"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        current_work_data = self.basic_data.lawn_mower.current_work_data
        if not current_work_data:
            return None

        job_type = to_ha_enum_state(current_work_data.get('type'))
        if job_type in self._attr_options:
            return cast("str", job_type)
        return None


class RemainingBladeTimeSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Remaining blade usage time sensor - uses dp_126 data"""

    _push_dp_ids = (126,)

    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "remaining_blade_time"

    _unique_id_suffix = "remaining_blade_time"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        blade_time = self.basic_data.lawn_mower.blade_time
        if not blade_time:
            return None

        used_time = int(blade_time.get('int_value', 0))
        # Recommended blade cleaning cycle is 240 hours, i.e. 14400 minutes
        remaining_time = BLADE_MAINTENANCE_CYCLE_MINUTES - used_time
        return max(0, remaining_time)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return {}

        blade_time = self.basic_data.lawn_mower.blade_time
        if not blade_time:
            return {}

        used_time = blade_time.get('int_value', 0)
        return {
            'used_time': used_time,
            'recommended_cycle': BLADE_MAINTENANCE_CYCLE_MINUTES,
            'recommended_cycle_hours': BLADE_MAINTENANCE_CYCLE_MINUTES // 60,
            'needs_maintenance': used_time >= BLADE_MAINTENANCE_CYCLE_MINUTES
        }


class RemainingBaseStationTimeSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Remaining base station cleaning time sensor - uses dp_125 data"""

    _push_dp_ids = (125,)

    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "remaining_base_station_time"

    _unique_id_suffix = "remaining_base_station_time"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        base_station_time = self.basic_data.lawn_mower.base_station_time
        if not base_station_time:
            return None

        used_time = int(base_station_time.get('int_value', 0))
        # Recommended base station cleaning cycle is 30 days, i.e. 43200 minutes
        remaining_time = BASE_STATION_MAINTENANCE_CYCLE_MINUTES - used_time
        return max(0, remaining_time)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return {}

        base_station_time = self.basic_data.lawn_mower.base_station_time
        if not base_station_time:
            return {}

        used_time = base_station_time.get('int_value', 0)
        return {
            'used_time': used_time,
            'recommended_cycle': BASE_STATION_MAINTENANCE_CYCLE_MINUTES,  # 30 days in minutes
            'recommended_cycle_days': BASE_STATION_MAINTENANCE_CYCLE_MINUTES // (60 * 24),
            'needs_maintenance': used_time >= BASE_STATION_MAINTENANCE_CYCLE_MINUTES
        }


class TerraMowMowHeightSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Mow height sensor - uses dp_155 data."""

    _push_dp_ids = (155,)

    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "mow_height"

    _unique_id_suffix = "mow_height"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        mow_height = global_params.get('mow_height', {})
        return cast("int | None", mow_height.get('value'))


class TerraMowMowSpeedSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Mow speed sensor - uses dp_155 data."""

    _push_dp_ids = (155,)

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "mow_speed"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [to_ha_enum_state(t) for t in MOW_SPEED_TYPES]

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        super().__init__(basic_data, hass)
        self._unknown_speed_type: str | None = None

    _unique_id_suffix = "mow_speed"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        mow_speed = global_params.get('mow_speed', {})
        speed_type = mow_speed.get('speed_type')
        if not speed_type:
            self._unknown_speed_type = None
            return None

        normalized = to_ha_enum_state(speed_type)
        if normalized in self._attr_options:
            self._unknown_speed_type = None
            return cast("str", normalized)

        if speed_type != self._unknown_speed_type:
            _LOGGER.warning(
                "Unknown mow speed type from device: %s. Expose raw value in attributes.",
                speed_type,
            )
            self._unknown_speed_type = speed_type

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return {}

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return {}

        attrs = {}

        # Mowing spacing
        mow_spacing = global_params.get('mow_spacing', {})
        if 'value' in mow_spacing:
            attrs['mow_spacing'] = mow_spacing['value']

        # Edge cutting distance
        edge_cutting_distance = global_params.get('edge_cutting_distance', {})
        if 'value' in edge_cutting_distance:
            attrs['edge_cutting_distance'] = edge_cutting_distance['value']

        # Blade disk speed
        blade_disk_speed = global_params.get('blade_disk_speed', {})
        if 'speed_type' in blade_disk_speed:
            attrs['blade_disk_speed'] = blade_disk_speed['speed_type']

        if self._unknown_speed_type:
            attrs['unknown_mow_speed_type'] = self._unknown_speed_type

        return attrs


class NextScheduledStartSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Next scheduled start sensor - uses dp_138 data"""

    _push_dp_ids = (138,)

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "next_scheduled_start"
    _attr_device_class = None  # display the time as a string

    _unique_id_suffix = "next_scheduled_start"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        schedule_data = self.basic_data.lawn_mower.schedule_data
        if not schedule_data:
            return None

        # Check whether a schedule exists
        if not schedule_data.get('exist', False):
            return None

        start_time = schedule_data.get('start_time', {})
        if not start_time or 'hour' not in start_time or 'minute' not in start_time:
            return None

        # Return the formatted time string
        hour = start_time['hour']
        minute = start_time['minute']
        return f"{hour:02d}:{minute:02d}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return {}

        schedule_data = self.basic_data.lawn_mower.schedule_data
        if not schedule_data:
            return {}

        attrs: dict[str, Any] = {}

        if schedule_data.get('exist', False):
            attrs['has_schedule'] = True
            attrs['item_id'] = schedule_data.get('item_id')
            attrs['shift_id'] = schedule_data.get('shift_id')

            # End time
            end_time = schedule_data.get('end_time', {})
            if end_time and 'hour' in end_time and 'minute' in end_time:
                attrs['end_time'] = f"{end_time['hour']:02d}:{end_time['minute']:02d}"
        else:
            attrs['has_schedule'] = False

        return attrs


class VersionCompatibilitySensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Version compatibility status sensor."""

    _push_dp_ids = (127,)

    _attr_translation_key = "version_compatibility"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity.

        Keeps the historical ``version_compatibility.terramow@...`` format
        so existing entity registry entries stay attached.
        """
        return f"version_compatibility.terramow@{self.basic_data.host}"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return cast("str", self.basic_data.compatibility_status)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attributes: dict[str, Any] = {}

        # Get the compatibility message
        attributes["message"] = self.basic_data.get_compatibility_message()

        # Add detailed version information
        firmware_info = self.basic_data.firmware_version
        if firmware_info:
            attributes["firmware_overall_version"] = firmware_info.get("overall", "unknown")
            module_info = firmware_info.get("module", {})
            attributes["firmware_ha_version"] = module_info.get("home_assistant", "unknown")
            attributes["firmware_map_version"] = module_info.get("map", "unknown")
            attributes["firmware_control_version"] = module_info.get("control", "unknown")

        from .const import CURRENT_HA_VERSION, MIN_REQUIRED_OVERALL_VERSION
        attributes["plugin_ha_version"] = CURRENT_HA_VERSION
        attributes["min_required_overall_version"] = MIN_REQUIRED_OVERALL_VERSION

        return attributes


class TerraMowPoseSensor(TerraMowEntity, SensorEntity):
    """Real-time pose sensor (2 Hz)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "pose"
    # The device pushes pose at ~2 Hz; enabling it floods the recorder, so it
    # is opt-in (mainly useful for the map camera overlay, which reads the raw
    # hub pose directly rather than this entity's state).
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        super().__init__(basic_data, hass)
        self._pose: dict[str, Any] = {}

        if hasattr(basic_data, 'lawn_mower') and basic_data.lawn_mower:
            basic_data.lawn_mower.register_pose_callback(self._on_pose)

    _unique_id_suffix = "pose"

    async def _on_pose(self, pose: dict[str, Any]) -> None:
        """Handle a pose update."""
        self._pose = pose
        safe_write_ha_state(self)

    @property
    def native_value(self) -> float | None:
        """Return the sensor value (yaw)."""
        if not self._pose:
            return None
        yaw = self._pose.get('yaw')
        return float(yaw) if yaw is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        if not self._pose:
            return {}
        return {
            'x': self._pose.get('x'),
            'y': self._pose.get('y'),
            'yaw': self._pose.get('yaw'),
            'timestamp_ms': self._pose.get('timestamp_ms'),
            'frame': self._pose.get('frame'),
        }

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    basic_data = config_entry.runtime_data

    # Import the map-related sensor classes
    from .map_sensor import (
        TerraMowCleanModeSensor,
        TerraMowMapAreaSensor,
        TerraMowMapStatusSensor,
    )

    # Build the list of sensor entities
    entities = [
        # Basic sensors
        BatterySensor(basic_data, hass),
        BatteryStateSensor(basic_data, hass),
        BatteryTemperatureStateSensor(basic_data, hass),
        TerraMowPoseSensor(basic_data, hass),

        # Map-related sensors
        TerraMowMapStatusSensor(basic_data, hass),
        TerraMowMapAreaSensor(basic_data, hass),
        TerraMowCleanModeSensor(basic_data, hass),

        # Global parameter display sensors (dp_155)
        TerraMowMowHeightSensor(basic_data, hass),
        TerraMowMowSpeedSensor(basic_data, hass),

        # Statistics and session sensors
        TotalMowingTimeSensor(basic_data, hass),
        TotalMowingJobsSensor(basic_data, hass),
        TotalMowedAreaSensor(basic_data, hass),
        CurrentSessionAreaSensor(basic_data, hass),
        CurrentSessionProgressSensor(basic_data, hass),
        CurrentSessionTimeSensor(basic_data, hass),
CurrentJobTypeSensor(basic_data, hass),

        # Maintenance reminder sensors
        RemainingBladeTimeSensor(basic_data, hass),
        RemainingBaseStationTimeSensor(basic_data, hass),

        # Scheduled task sensors
        NextScheduledStartSensor(basic_data, hass),

        # Version compatibility sensor
        VersionCompatibilitySensor(basic_data, hass),

        # Main direction status sensor
        MainDirectionStatusSensor(basic_data, hass),

        # Power mode sensor (dp_107)
        PowerModeSensor(basic_data, hass),

        # Mission state related (dp_107)
        BackToStationReasonSensor(basic_data, hass),
        TerraMowMissionSensor(basic_data, hass),
        TerraMowSubMissionSensor(basic_data, hass),
        TerraMowMissionStateSensor(basic_data, hass),
    ]

    async_add_entities(entities)


class PowerModeSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Power mode sensor - uses dp_107 data."""

    _push_dp_ids = (107,)

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "power_mode_running",
        "power_mode_standby",
        "power_mode_hibernate",
    ]
    _attr_translation_key = "power_mode"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _unique_id_suffix = "power_mode"

    @property
    def native_value(self) -> str | None:
        """Return the current power mode."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        power_mode = to_ha_enum_state(self.basic_data.lawn_mower.power_mode)
        if power_mode in self._attr_options:
            return cast("str", power_mode)
        return None


class MainDirectionStatusSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Main direction status sensor - shows the current main direction config and angle."""

    _push_dp_ids = (155,)

    _attr_translation_key = "main_direction_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _unique_id_suffix = "main_direction_status"

    @property
    def native_value(self) -> str | None:
        """Return the sensor value."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return "unavailable"

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return "no_config"

        main_direction_config = global_params.get('main_direction_angle_config', {})
        mode = main_direction_config.get('mode', 'MAIN_DIRECTION_MODE_SINGLE')

        # Return the current mode as the sensor value (lowercase token to match translation keys)
        return cast("str | None", to_ha_enum_state(mode))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs: dict[str, Any] = {}

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return attrs

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return attrs

        main_direction_config = global_params.get('main_direction_angle_config', {})

        # Basic mode information
        mode = main_direction_config.get('mode', 'MAIN_DIRECTION_MODE_SINGLE')
        attrs['mode'] = mode

        # Current angle (if any)
        current_angle = main_direction_config.get('current_angle')
        if current_angle is not None:
            attrs['current_angle'] = current_angle
            attrs['current_angle_degrees'] = f"{current_angle}°"

        # Add mode-specific configuration information
        if mode == 'MAIN_DIRECTION_MODE_SINGLE':
            single_config = main_direction_config.get('single_mode_config', {})
            configured_angle = single_config.get('angle', 0)
            attrs['configured_angle'] = configured_angle
            attrs['configured_angle_degrees'] = f"{configured_angle}°"
            attrs['mode_description'] = "Single main direction"

        elif mode == 'MAIN_DIRECTION_MODE_MULTIPLE':
            multiple_config = main_direction_config.get('multiple_mode_config', {})
            configured_angles = multiple_config.get('angles', [])
            attrs['configured_angles'] = configured_angles
            attrs['configured_angles_degrees'] = [f"{angle}°" for angle in configured_angles]
            attrs['angles_count'] = len(configured_angles)
            attrs['mode_description'] = "Multiple main directions"

        elif mode == 'MAIN_DIRECTION_MODE_AUTO_ROTATE':
            auto_config = main_direction_config.get('auto_rotate_mode_config', {})
            interval = auto_config.get('angle_interval', 15)
            attrs['rotation_interval'] = interval
            attrs['rotation_interval_degrees'] = f"{interval}°"
            attrs['mode_description'] = "Auto rotate main direction"

        # Add a human-readable mode name
        mode_names = {
            'MAIN_DIRECTION_MODE_SINGLE': 'Single Direction',
            'MAIN_DIRECTION_MODE_MULTIPLE': 'Multiple Directions',
            'MAIN_DIRECTION_MODE_AUTO_ROTATE': 'Auto Rotate'
        }
        attrs['mode_friendly_name'] = mode_names.get(mode, mode)

        return attrs


BACK_TO_STATION_REASON_OPTIONS = [
    "back_to_station_reason_none",
    "back_to_station_reason_low_battery",
    "back_to_station_reason_raining",
    "back_to_station_reason_mow_motor_overheat",
    "back_to_station_reason_wheel_overheat",
    "back_to_station_reason_night_time",
]


class BackToStationReasonSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Enum sensor exposing the dp_107 back_to_station_reason field."""

    _push_dp_ids = (107,)

    _attr_translation_key = "back_to_station_reason"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = BACK_TO_STATION_REASON_OPTIONS.copy()

    _unique_id_suffix = "back_to_station_reason"

    @property
    def native_value(self) -> str | None:
        """Return the raw back_to_station_reason enum string."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None
        reason = to_ha_enum_state(self.basic_data.lawn_mower.back_to_station_reason)
        if reason in self._attr_options:
            return cast("str", reason)
        return None


class _MissionEnumSensorBase(TerraMowEntity, SensorEntity):
    """Shared base for the dp_107 mission/sub_mission/state enum sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM

    _enum_attr: str = ""
    _unique_id_suffix: str = ""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.basic_data.lawn_mower:
            self.basic_data.lawn_mower.register_callback(107, self._handle_dp_107)

    async def _handle_dp_107(self, _payload: str) -> None:
        safe_write_ha_state(self)

    @property
    def native_value(self) -> str | None:
        if not self.basic_data.lawn_mower:
            return None
        member = getattr(self.basic_data.lawn_mower, self._enum_attr, None)
        if member is None:
            return None
        value = member.value if hasattr(member, "value") else str(member)
        value = to_ha_enum_state(value)
        if self._attr_options is not None and value in self._attr_options:
            return value
        return None


class TerraMowMissionSensor(_MissionEnumSensorBase):
    """Current top-level mission (dp_107)."""

    _attr_translation_key = "mission"
    _attr_options = [to_ha_enum_state(member.value) for member in Mission]
    _enum_attr = "mission"
    _unique_id_suffix = "mission"


class TerraMowSubMissionSensor(_MissionEnumSensorBase):
    """Current sub-mission (dp_107) — surfaces transient states like waiting for rain."""

    _attr_translation_key = "sub_mission"
    _attr_options = [to_ha_enum_state(member.value) for member in SubMission]
    _enum_attr = "sub_mission"
    _unique_id_suffix = "sub_mission"


class TerraMowMissionStateSensor(_MissionEnumSensorBase):
    """Mission lifecycle state (dp_107): idle / running / paused / abort / complete."""

    _attr_translation_key = "mission_state"
    _attr_options = [to_ha_enum_state(member.value) for member in MissionState]
    _enum_attr = "mission_state"
    _unique_id_suffix = "mission_state"
