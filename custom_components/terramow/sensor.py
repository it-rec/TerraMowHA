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
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
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
    CURRENT_HA_VERSION,
    MIN_REQUIRED_OVERALL_VERSION,
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
        hub = self.hub
        if not hub:
            return {}

        battery_status = hub.battery_status
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
        hub = self.hub
        if not hub:
            return None

        battery_status = hub.battery_status
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
        hub = self.hub
        if not hub:
            return None

        battery_status = hub.battery_status
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
        hub = self.hub
        if not hub:
            return None

        statistics_data = hub.statistics_data
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
        hub = self.hub
        if not hub:
            return None

        statistics_data = hub.statistics_data
        if not statistics_data:
            return None

        return cast("int | None", statistics_data.get('clean_times'))


class TotalMowedAreaSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Lifetime mowed area sensor - uses dp_124 data"""

    _push_dp_ids = (124,)

    _attr_native_unit_of_measurement = UnitOfArea.SQUARE_METERS
    # SensorDeviceClass.AREA exists since HA 2024.12; stay None on older cores
    _attr_device_class = getattr(SensorDeviceClass, "AREA", None)
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "total_mowed_area"

    _unique_id_suffix = "total_mowed_area"

    @property
    def native_value(self) -> float | None:
        """Return the lifetime mowed area in square meters."""
        hub = self.hub
        if not hub:
            return None

        statistics_data = hub.statistics_data
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
    # SensorDeviceClass.AREA exists since HA 2024.12; stay None on older cores
    _attr_device_class = getattr(SensorDeviceClass, "AREA", None)
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "current_session_area"

    _unique_id_suffix = "current_session_area"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        hub = self.hub
        if not hub:
            return None

        current_work_data = hub.current_work_data
        if not current_work_data:
            return None

        # clean_area is in units of 0.1 square meters; convert to square meters
        clean_area = current_work_data.get('clean_area')
        if clean_area is None:
            return None
        return round(float(clean_area) / 10, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        hub = self.hub
        if not hub:
            return {}

        current_work_data = hub.current_work_data
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


class CurrentSessionProgressSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Progress (%) of the current session, derived from dp_113 clean_area/total_area."""

    _push_dp_ids = (113,)

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "current_session_progress"

    _unique_id_suffix = "current_session_progress"

    @property
    def native_value(self) -> float | None:
        hub = self.hub
        if not hub:
            return None
        current_work_data = hub.current_work_data
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
        hub = self.hub
        if not hub:
            return None

        current_work_data = hub.current_work_data
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
        hub = self.hub
        if not hub:
            return None

        current_work_data = hub.current_work_data
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
        hub = self.hub
        if not hub:
            return None

        blade_time = hub.blade_time
        if not blade_time:
            return None

        used_time = int(blade_time.get('int_value', 0))
        # Recommended blade cleaning cycle is 240 hours, i.e. 14400 minutes
        remaining_time = BLADE_MAINTENANCE_CYCLE_MINUTES - used_time
        return max(0, remaining_time)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        hub = self.hub
        if not hub:
            return {}

        blade_time = hub.blade_time
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
        hub = self.hub
        if not hub:
            return None

        base_station_time = hub.base_station_time
        if not base_station_time:
            return None

        used_time = int(base_station_time.get('int_value', 0))
        # Recommended base station cleaning cycle is 30 days, i.e. 43200 minutes
        remaining_time = BASE_STATION_MAINTENANCE_CYCLE_MINUTES - used_time
        return max(0, remaining_time)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        hub = self.hub
        if not hub:
            return {}

        base_station_time = hub.base_station_time
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
        hub = self.hub
        if not hub:
            return None

        global_params = hub.global_params
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
        hub = self.hub
        if not hub:
            return None

        global_params = hub.global_params
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
        hub = self.hub
        if not hub:
            return {}

        global_params = hub.global_params
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
        hub = self.hub
        if not hub:
            return None

        schedule_data = hub.schedule_data
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
        hub = self.hub
        if not hub:
            return {}

        schedule_data = hub.schedule_data
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
        return f"version_compatibility.terramow@{self.device_uid}"

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

    async def async_added_to_hass(self) -> None:
        """Register the pose callback once the entity is actually added.

        Registering here (with the unsubscribe handed to ``async_on_remove``)
        instead of in ``__init__`` means a registry-disabled or removed entity
        does not keep receiving ~2 Hz pose pushes from the hub.
        """
        await super().async_added_to_hass()
        hub = self.hub
        if hub:
            self.async_on_remove(
                hub.register_pose_callback(self._on_pose)
            )

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


class ActiveErrorsSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Number of active device errors (dp_116, undocumented/reverse-engineered).

    The device publishes ``{"error_list": [...]}``. Only the count is exposed
    as the state; the raw list is attached as an attribute. See
    ``docs/en/developers/data_point_unofficial.md``.
    """

    _push_dp_ids = (116,)
    _attr_translation_key = "active_errors"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unique_id_suffix = "active_errors"

    @property
    def native_value(self) -> int | None:
        """Return the number of active errors."""
        lawn_mower = self.basic_data.lawn_mower
        if lawn_mower is None:
            return None
        return len(lawn_mower.error_list)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw error list."""
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower or not lawn_mower.error_list:
            return {}
        return {"errors": lawn_mower.error_list}


class LastEventSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Code of the most recent device event (dp_123, undocumented).

    The device publishes ``{"event_list": [{"code": int, "time": str}]}``. The
    latest event's code is the state; its timestamp is an attribute.
    """

    _push_dp_ids = (123,)
    _attr_translation_key = "last_event"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Raw event code, niche; off by default.
    _attr_entity_registry_enabled_default = False
    _unique_id_suffix = "last_event"

    def _latest_event(self) -> dict[str, Any] | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower or not lawn_mower.event_list:
            return None
        last = lawn_mower.event_list[-1]
        return last if isinstance(last, dict) else None

    @property
    def native_value(self) -> int | None:
        """Return the latest event code."""
        last = self._latest_event()
        if last is None:
            return None
        code = last.get("code")
        return code if isinstance(code, int) and not isinstance(code, bool) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the latest event's timestamp."""
        last = self._latest_event()
        if not last:
            return {}
        event_time = last.get("time")
        return {"event_time": event_time} if event_time is not None else {}


class _CellularSensorBase(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Base for the cellular/4G diagnostic sensors (dp_135, unofficial)."""

    _push_dp_ids = (135,)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _cellular(self) -> dict[str, Any] | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower or not lawn_mower.cellular_info:
            return None
        return cast("dict[str, Any]", lawn_mower.cellular_info)


class CellularSignalRsrpSensor(_CellularSensorBase):
    """Cellular RSRP signal strength (dp_135). None while cellular is disabled."""

    _attr_translation_key = "cellular_signal_rsrp"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unique_id_suffix = "cellular_signal_rsrp"

    @property
    def native_value(self) -> int | None:
        info = self._cellular()
        if not info or not info.get("is_enabled"):
            return None
        value = info.get("RSRP")
        return value if isinstance(value, int) and not isinstance(value, bool) else None


class CellularSignalRsrqSensor(_CellularSensorBase):
    """Cellular RSRQ signal quality (dp_135). None while cellular is disabled."""

    _attr_translation_key = "cellular_signal_rsrq"
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unique_id_suffix = "cellular_signal_rsrq"

    @property
    def native_value(self) -> int | None:
        info = self._cellular()
        if not info or not info.get("is_enabled"):
            return None
        value = info.get("RSRQ")
        return value if isinstance(value, int) and not isinstance(value, bool) else None


class CellularConnectionTypeSensor(_CellularSensorBase):
    """Cellular connection type (dp_135), e.g. 'CELLULAR_TYPE_UNKNOWN'."""

    _attr_translation_key = "cellular_connection_type"
    # Niche; the enabled/RSRP/RSRQ sensors cover the useful cellular state.
    _attr_entity_registry_enabled_default = False
    _unique_id_suffix = "cellular_connection_type"

    @property
    def native_value(self) -> str | None:
        info = self._cellular()
        if not info:
            return None
        value = info.get("type")
        return value if isinstance(value, str) and value else None


class _SunTimeSensorBase(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Base for the device-reported sunrise/sunset times (dp_152, unofficial).

    The device reports a local time-of-day as ``{"hour":int,"minute":int}``;
    exposed as an ``HH:MM`` string. Set ``_field`` on the subclass.
    """

    _push_dp_ids = (152,)
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Home Assistant already provides sunrise/sunset via the sun integration, so
    # these device-reported times are a niche extra: off by default.
    _attr_entity_registry_enabled_default = False
    _field = ""

    @property
    def native_value(self) -> str | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower:
            return None
        slot = lawn_mower.environment_info.get(self._field)
        if not isinstance(slot, dict):
            return None
        hour, minute = slot.get("hour"), slot.get("minute")
        if not isinstance(hour, int) or isinstance(hour, bool):
            return None
        if not isinstance(minute, int) or isinstance(minute, bool):
            return None
        return f"{hour:02d}:{minute:02d}"


class _OperatingModeSensorBase(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Base for the dp_154 operating-mode string sensors (unofficial).

    Reports the raw device enum (e.g. ``MOVE_MODE_MOW``) as the state; set
    ``_field`` on the subclass.
    """

    _push_dp_ids = (154,)
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Advanced diagnostic enums; off by default to avoid dashboard clutter.
    _attr_entity_registry_enabled_default = False
    _field = ""

    @property
    def native_value(self) -> str | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower:
            return None
        value = lawn_mower.operating_modes.get(self._field)
        return value if isinstance(value, str) and value else None


class MoveModeSensor(_OperatingModeSensorBase):
    """Current movement mode (dp_154)."""

    _attr_translation_key = "move_mode"
    _field = "move_mode"
    _unique_id_suffix = "move_mode"


class MapModeSensor(_OperatingModeSensorBase):
    """Current map mode (dp_154)."""

    _attr_translation_key = "map_mode"
    _field = "map_mode"
    _unique_id_suffix = "map_mode"


class MowModeSensor(_OperatingModeSensorBase):
    """Current mow mode (dp_154)."""

    _attr_translation_key = "mow_mode"
    _field = "mow_mode"
    _unique_id_suffix = "mow_mode"


class RainSensorThresholdSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Rain-sensor upper-limit threshold (dp_150, unofficial, read-only)."""

    _push_dp_ids = (150,)
    _attr_translation_key = "rain_sensor_threshold"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    # Advanced config readout; off by default.
    _attr_entity_registry_enabled_default = False
    _unique_id_suffix = "rain_sensor_threshold"

    @property
    def native_value(self) -> int | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower:
            return None
        node = lawn_mower.advanced_settings.get("rain_sensor_threshold")
        if not isinstance(node, dict):
            return None
        value = node.get("upper_limit")
        return value if isinstance(value, int) and not isinstance(value, bool) else None


class AfterRainResumeDelaySensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """After-rain auto-resume delay in minutes (dp_150, unofficial, read-only)."""

    _push_dp_ids = (150,)
    _attr_translation_key = "after_rain_resume_delay"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Advanced config readout; off by default.
    _attr_entity_registry_enabled_default = False
    _unique_id_suffix = "after_rain_resume_delay"

    @property
    def native_value(self) -> int | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower:
            return None
        setting = lawn_mower.advanced_settings.get("after_rain_stop_setting")
        if not isinstance(setting, dict):
            return None
        delay = setting.get("auto_resume_delay_time")
        if not isinstance(delay, dict):
            return None

        def _int(value: Any) -> int | None:
            return value if isinstance(value, int) and not isinstance(value, bool) else None

        hours, minutes = _int(delay.get("hours")), _int(delay.get("minutes"))
        if hours is None and minutes is None:
            return None
        return (hours or 0) * 60 + (minutes or 0)


class MapSaveProgressSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Map-save / upload progress (dp_118, unofficial).

    ``int_value`` 0-100, ramping while the device saves its map after a mow
    (``SUB_MISSION_SAVING_MAP`` / "map is being saved"). Diagnostic, disabled by
    default. See ``docs/en/developers/data_point_unofficial.md``.
    """

    _push_dp_ids = (118,)
    _attr_translation_key = "map_save_progress"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Transient (only meaningful during a save); off by default.
    _attr_entity_registry_enabled_default = False
    _unique_id_suffix = "map_save_progress"

    @property
    def native_value(self) -> int | None:
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower:
            return None
        value = lawn_mower.map_save_progress.get("int_value")
        return value if isinstance(value, int) and not isinstance(value, bool) else None


class SunriseSensor(_SunTimeSensorBase):
    """Device-reported sunrise time (dp_152)."""

    _attr_translation_key = "sunrise"
    _field = "sunrise"
    _unique_id_suffix = "sunrise"


class SunsetSensor(_SunTimeSensorBase):
    """Device-reported sunset time (dp_152)."""

    _attr_translation_key = "sunset"
    _field = "sunset"
    _unique_id_suffix = "sunset"


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

        # Unofficial / reverse-engineered diagnostic sensors
        ActiveErrorsSensor(basic_data, hass),
        LastEventSensor(basic_data, hass),
        CellularSignalRsrpSensor(basic_data, hass),
        CellularSignalRsrqSensor(basic_data, hass),
        CellularConnectionTypeSensor(basic_data, hass),
        SunriseSensor(basic_data, hass),
        SunsetSensor(basic_data, hass),
        MoveModeSensor(basic_data, hass),
        MapModeSensor(basic_data, hass),
        MowModeSensor(basic_data, hass),
        RainSensorThresholdSensor(basic_data, hass),
        AfterRainResumeDelaySensor(basic_data, hass),
        MapSaveProgressSensor(basic_data, hass),
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
        hub = self.hub
        if not hub:
            return None

        power_mode = to_ha_enum_state(hub.power_mode)
        if power_mode in self._attr_options:
            return power_mode
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
        hub = self.hub
        if not hub:
            return None

        global_params = hub.global_params
        if not global_params:
            return None

        main_direction_config = global_params.get('main_direction_angle_config', {})
        mode = main_direction_config.get('mode', 'MAIN_DIRECTION_MODE_SINGLE')

        # Return the current mode as the sensor value (lowercase token to match translation keys)
        return cast("str | None", to_ha_enum_state(mode))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs: dict[str, Any] = {}

        hub = self.hub
        if not hub:
            return attrs

        global_params = hub.global_params
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
        hub = self.hub
        if not hub:
            return None
        reason = to_ha_enum_state(hub.back_to_station_reason)
        if reason in self._attr_options:
            return reason
        return None


class _MissionEnumSensorBase(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Shared base for the dp_107 mission/sub_mission/state enum sensors."""

    _push_dp_ids = (107,)

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM

    _enum_attr: str = ""
    _unique_id_suffix: str = ""

    @property
    def native_value(self) -> str | None:
        hub = self.hub
        if not hub:
            return None
        member = getattr(hub, self._enum_attr, None)
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
