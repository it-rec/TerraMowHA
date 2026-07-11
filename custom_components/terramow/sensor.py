from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
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
from homeassistant.helpers.typing import StateType

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
from .hub import Mission, MissionState, SubMission, TerraMowHub

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TerraMowSensorEntityDescription(SensorEntityDescription):
    """Describes a TerraMow sensor computed from cached hub state.

    ``push_dp_ids`` are the data point IDs whose pushes refresh the entity
    (see ``PushUpdateMixin``). ``value_fn`` (and the optional
    ``attributes_fn``) receive the hub; the generic entity already handles
    the hub-is-None case, and filters enum values against ``options``.
    """

    push_dp_ids: tuple[int, ...]
    value_fn: Callable[[TerraMowHub], StateType]
    attributes_fn: Callable[[TerraMowHub], dict[str, Any]] | None = None


class TerraMowSensor(PushUpdateMixin, TerraMowEntity, SensorEntity):
    """Generic sensor driven entirely by its entity description."""

    entity_description: TerraMowSensorEntityDescription

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
        description: TerraMowSensorEntityDescription,
    ) -> None:
        super().__init__(basic_data, hass)
        self.entity_description = description
        self._unique_id_suffix = description.key
        self._push_dp_ids = description.push_dp_ids

    @property
    def native_value(self) -> StateType:
        """Return the sensor value computed from the hub state."""
        hub = self.hub
        if hub is None:
            return None
        value = self.entity_description.value_fn(hub)
        if (
            self.entity_description.device_class is SensorDeviceClass.ENUM
            and value not in (self.entity_description.options or ())
        ):
            return None
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        attributes_fn = self.entity_description.attributes_fn
        if attributes_fn is None:
            return None
        hub = self.hub
        if hub is None:
            return {}
        return attributes_fn(hub)


# ---------------------------------------------------------------------------
# value / attribute helpers shared by the SENSORS table
# ---------------------------------------------------------------------------


def _battery_enum(field: str) -> Callable[[TerraMowHub], StateType]:
    """Normalized enum token from the dp_108 battery status block."""

    def value_fn(hub: TerraMowHub) -> StateType:
        battery_status = hub.battery_status
        if not battery_status:
            return None
        return to_ha_enum_state(battery_status.get(field))

    return value_fn


def _statistics_field(field: str) -> Callable[[TerraMowHub], StateType]:
    """Raw field from the dp_124 lifetime statistics block."""

    def value_fn(hub: TerraMowHub) -> StateType:
        statistics_data = hub.statistics_data
        if not statistics_data:
            return None
        return cast("StateType", statistics_data.get(field))

    return value_fn


def _total_mowed_area(hub: TerraMowHub) -> StateType:
    statistics_data = hub.statistics_data
    if not statistics_data:
        return None
    clean_area = statistics_data.get("clean_area")
    if clean_area is None:
        return None
    # The protocol unit is 0.1 square meters
    return round(float(clean_area) / 10, 1)


def _current_session_area(hub: TerraMowHub) -> StateType:
    current_work_data = hub.current_work_data
    if not current_work_data:
        return None
    # clean_area is in units of 0.1 square meters; convert to square meters
    clean_area = current_work_data.get("clean_area")
    if clean_area is None:
        return None
    return round(float(clean_area) / 10, 1)


def _current_session_attributes(hub: TerraMowHub) -> dict[str, Any]:
    current_work_data = hub.current_work_data
    if not current_work_data:
        return {}

    attrs = {}
    work_type = current_work_data.get("type", "")
    if work_type:
        attrs["work_type"] = work_type

    total_area = current_work_data.get("total_area", 0)
    if total_area:
        attrs["total_area"] = round(total_area / 10, 1)

    is_completed = current_work_data.get("is_completed")
    if is_completed is not None:
        attrs["is_completed"] = is_completed

    return attrs


def _current_session_progress(hub: TerraMowHub) -> StateType:
    current_work_data = hub.current_work_data
    if not current_work_data:
        return None
    total_area = current_work_data.get("total_area") or 0
    clean_area = current_work_data.get("clean_area") or 0
    if total_area <= 0:
        return None
    progress = 100.0 * clean_area / total_area
    # Cap at 100; the device occasionally reports clean_area > total_area
    # near the very end of a session.
    return round(min(progress, 100.0), 1)


def _current_session_time(hub: TerraMowHub) -> StateType:
    current_work_data = hub.current_work_data
    if not current_work_data:
        return None
    return cast("StateType", current_work_data.get("work_duration"))


def _current_job_type(hub: TerraMowHub) -> StateType:
    current_work_data = hub.current_work_data
    if not current_work_data:
        return None
    return to_ha_enum_state(current_work_data.get("type"))


def _maintenance_remaining(
    time_attr: str, cycle: int
) -> Callable[[TerraMowHub], StateType]:
    """Minutes left in a maintenance cycle read from a dp int_value payload."""

    def value_fn(hub: TerraMowHub) -> StateType:
        data = getattr(hub, time_attr)
        if not data:
            return None
        used_time = int(data.get("int_value", 0))
        return max(0, cycle - used_time)

    return value_fn


def _maintenance_attributes(
    time_attr: str, cycle: int, cycle_unit_key: str, minutes_per_unit: int
) -> Callable[[TerraMowHub], dict[str, Any]]:
    def attributes_fn(hub: TerraMowHub) -> dict[str, Any]:
        data = getattr(hub, time_attr)
        if not data:
            return {}
        used_time = data.get("int_value", 0)
        return {
            "used_time": used_time,
            "recommended_cycle": cycle,
            cycle_unit_key: cycle // minutes_per_unit,
            "needs_maintenance": used_time >= cycle,
        }

    return attributes_fn


def _mow_height(hub: TerraMowHub) -> StateType:
    global_params = hub.global_params
    if not global_params:
        return None
    mow_height = global_params.get("mow_height", {})
    return cast("StateType", mow_height.get("value"))


def _next_scheduled_start(hub: TerraMowHub) -> StateType:
    schedule_data = hub.schedule_data
    if not schedule_data:
        return None

    # Check whether a schedule exists
    if not schedule_data.get("exist", False):
        return None

    start_time = schedule_data.get("start_time", {})
    if not start_time or "hour" not in start_time or "minute" not in start_time:
        return None

    # Return the formatted time string
    hour = start_time["hour"]
    minute = start_time["minute"]
    return f"{hour:02d}:{minute:02d}"


def _next_scheduled_start_attributes(hub: TerraMowHub) -> dict[str, Any]:
    schedule_data = hub.schedule_data
    if not schedule_data:
        return {}

    attrs: dict[str, Any] = {}

    if schedule_data.get("exist", False):
        attrs["has_schedule"] = True
        attrs["item_id"] = schedule_data.get("item_id")
        attrs["shift_id"] = schedule_data.get("shift_id")

        # End time
        end_time = schedule_data.get("end_time", {})
        if end_time and "hour" in end_time and "minute" in end_time:
            attrs["end_time"] = f"{end_time['hour']:02d}:{end_time['minute']:02d}"
    else:
        attrs["has_schedule"] = False

    return attrs


def _active_errors(hub: TerraMowHub) -> StateType:
    return len(hub.error_list)


def _active_errors_attributes(hub: TerraMowHub) -> dict[str, Any]:
    if not hub.error_list:
        return {}
    return {"errors": hub.error_list}


def _latest_event(hub: TerraMowHub) -> dict[str, Any] | None:
    if not hub.event_list:
        return None
    last = hub.event_list[-1]
    return last if isinstance(last, dict) else None


def _last_event_code(hub: TerraMowHub) -> StateType:
    last = _latest_event(hub)
    if last is None:
        return None
    code = last.get("code")
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def _last_event_attributes(hub: TerraMowHub) -> dict[str, Any]:
    last = _latest_event(hub)
    if not last:
        return {}
    event_time = last.get("time")
    return {"event_time": event_time} if event_time is not None else {}


def _cellular_signal(field: str) -> Callable[[TerraMowHub], StateType]:
    """Signal metric from dp_135; None while cellular is disabled."""

    def value_fn(hub: TerraMowHub) -> StateType:
        info = hub.cellular_info
        if not info or not info.get("is_enabled"):
            return None
        value = info.get(field)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    return value_fn


def _cellular_type(hub: TerraMowHub) -> StateType:
    info = hub.cellular_info
    if not info:
        return None
    value = info.get("type")
    return value if isinstance(value, str) and value else None


def _sun_time(field: str) -> Callable[[TerraMowHub], StateType]:
    """Device-reported local time-of-day (dp_152) as an ``HH:MM`` string."""

    def value_fn(hub: TerraMowHub) -> StateType:
        slot = hub.environment_info.get(field)
        if not isinstance(slot, dict):
            return None
        hour, minute = slot.get("hour"), slot.get("minute")
        if not isinstance(hour, int) or isinstance(hour, bool):
            return None
        if not isinstance(minute, int) or isinstance(minute, bool):
            return None
        return f"{hour:02d}:{minute:02d}"

    return value_fn


def _operating_mode(field: str) -> Callable[[TerraMowHub], StateType]:
    """Raw device enum (e.g. ``MOVE_MODE_MOW``) from the dp_154 block."""

    def value_fn(hub: TerraMowHub) -> StateType:
        value = hub.operating_modes.get(field)
        return value if isinstance(value, str) and value else None

    return value_fn


def _rain_sensor_threshold(hub: TerraMowHub) -> StateType:
    node = hub.advanced_settings.get("rain_sensor_threshold")
    if not isinstance(node, dict):
        return None
    value = node.get("upper_limit")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _after_rain_resume_delay(hub: TerraMowHub) -> StateType:
    setting = hub.advanced_settings.get("after_rain_stop_setting")
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


def _map_save_progress(hub: TerraMowHub) -> StateType:
    value = hub.map_save_progress.get("int_value")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _power_mode(hub: TerraMowHub) -> StateType:
    return to_ha_enum_state(hub.power_mode)


def _main_direction_mode(hub: TerraMowHub) -> StateType:
    global_params = hub.global_params
    if not global_params:
        return None

    main_direction_config = global_params.get("main_direction_angle_config", {})
    mode = main_direction_config.get("mode", "MAIN_DIRECTION_MODE_SINGLE")

    # Return the current mode as the sensor value (lowercase token to match
    # translation keys)
    return cast("StateType", to_ha_enum_state(mode))


def _main_direction_attributes(hub: TerraMowHub) -> dict[str, Any]:
    attrs: dict[str, Any] = {}

    global_params = hub.global_params
    if not global_params:
        return attrs

    main_direction_config = global_params.get("main_direction_angle_config", {})

    # Basic mode information
    mode = main_direction_config.get("mode", "MAIN_DIRECTION_MODE_SINGLE")
    attrs["mode"] = mode

    # Current angle (if any)
    current_angle = main_direction_config.get("current_angle")
    if current_angle is not None:
        attrs["current_angle"] = current_angle
        attrs["current_angle_degrees"] = f"{current_angle}°"

    # Add mode-specific configuration information
    if mode == "MAIN_DIRECTION_MODE_SINGLE":
        single_config = main_direction_config.get("single_mode_config", {})
        configured_angle = single_config.get("angle", 0)
        attrs["configured_angle"] = configured_angle
        attrs["configured_angle_degrees"] = f"{configured_angle}°"
        attrs["mode_description"] = "Single main direction"

    elif mode == "MAIN_DIRECTION_MODE_MULTIPLE":
        multiple_config = main_direction_config.get("multiple_mode_config", {})
        configured_angles = multiple_config.get("angles", [])
        attrs["configured_angles"] = configured_angles
        attrs["configured_angles_degrees"] = [f"{angle}°" for angle in configured_angles]
        attrs["angles_count"] = len(configured_angles)
        attrs["mode_description"] = "Multiple main directions"

    elif mode == "MAIN_DIRECTION_MODE_AUTO_ROTATE":
        auto_config = main_direction_config.get("auto_rotate_mode_config", {})
        interval = auto_config.get("angle_interval", 15)
        attrs["rotation_interval"] = interval
        attrs["rotation_interval_degrees"] = f"{interval}°"
        attrs["mode_description"] = "Auto rotate main direction"

    # Add a human-readable mode name
    mode_names = {
        "MAIN_DIRECTION_MODE_SINGLE": "Single Direction",
        "MAIN_DIRECTION_MODE_MULTIPLE": "Multiple Directions",
        "MAIN_DIRECTION_MODE_AUTO_ROTATE": "Auto Rotate",
    }
    attrs["mode_friendly_name"] = mode_names.get(mode, mode)

    return attrs


def _back_to_station_reason(hub: TerraMowHub) -> StateType:
    return to_ha_enum_state(hub.back_to_station_reason)


def _mission_enum(attr: str) -> Callable[[TerraMowHub], StateType]:
    """Normalized dp_107 mission/sub_mission/state enum value."""

    def value_fn(hub: TerraMowHub) -> StateType:
        member = getattr(hub, attr, None)
        if member is None:
            return None
        value = member.value if hasattr(member, "value") else str(member)
        return to_ha_enum_state(cast("str", value))

    return value_fn


BACK_TO_STATION_REASON_OPTIONS = [
    "back_to_station_reason_none",
    "back_to_station_reason_low_battery",
    "back_to_station_reason_raining",
    "back_to_station_reason_mow_motor_overheat",
    "back_to_station_reason_wheel_overheat",
    "back_to_station_reason_night_time",
]


SENSORS: tuple[TerraMowSensorEntityDescription, ...] = (
    # Battery status enums (dp_108)
    TerraMowSensorEntityDescription(
        key="battery_state",
        translation_key="battery_state",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "battery_state_discharge",
            "battery_state_charging",
            "battery_state_charged",
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(108,),
        value_fn=_battery_enum("state"),
    ),
    TerraMowSensorEntityDescription(
        key="battery_temperature_state",
        translation_key="battery_temperature_state",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "battery_tempreture_normal",
            "battery_tempreture_overheat",
            "battery_tempreture_underheat",
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(108,),
        # Firmware reports the field as 'tempreture' (typo preserved).
        value_fn=_battery_enum("tempreture"),
    ),
    # Lifetime statistics (dp_124)
    TerraMowSensorEntityDescription(
        key="total_mowing_time",
        translation_key="total_mowing_time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(124,),
        value_fn=_statistics_field("duration"),
    ),
    TerraMowSensorEntityDescription(
        key="total_mowing_jobs",
        translation_key="total_mowing_jobs",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(124,),
        value_fn=_statistics_field("clean_times"),
    ),
    TerraMowSensorEntityDescription(
        key="total_mowed_area",
        translation_key="total_mowed_area",
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        # SensorDeviceClass.AREA exists since HA 2024.12; stay None on older cores
        device_class=getattr(SensorDeviceClass, "AREA", None),
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(124,),
        value_fn=_total_mowed_area,
    ),
    # Current session (dp_113)
    TerraMowSensorEntityDescription(
        key="current_session_area",
        translation_key="current_session_area",
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        # SensorDeviceClass.AREA exists since HA 2024.12; stay None on older cores
        device_class=getattr(SensorDeviceClass, "AREA", None),
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(113,),
        value_fn=_current_session_area,
        attributes_fn=_current_session_attributes,
    ),
    TerraMowSensorEntityDescription(
        key="current_session_progress",
        translation_key="current_session_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(113,),
        value_fn=_current_session_progress,
    ),
    TerraMowSensorEntityDescription(
        key="current_session_time",
        translation_key="current_session_time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(113,),
        value_fn=_current_session_time,
    ),
    TerraMowSensorEntityDescription(
        key="current_job_type",
        translation_key="current_job_type",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "map_area_type_none",
            "map_area_type_build_map",
            "map_area_type_cleaning",
            "map_area_type_build_map_and_cleaning",
            "map_area_type_select_region_cleaning",
            "map_area_type_draw_region_cleaning",
            "map_area_type_edge_trim_cleaning",
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(113,),
        value_fn=_current_job_type,
    ),
    # Maintenance reminders (dp_126 / dp_125)
    TerraMowSensorEntityDescription(
        key="remaining_blade_time",
        translation_key="remaining_blade_time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(126,),
        # Recommended blade cleaning cycle is 240 hours, i.e. 14400 minutes
        value_fn=_maintenance_remaining(
            "blade_time", BLADE_MAINTENANCE_CYCLE_MINUTES
        ),
        attributes_fn=_maintenance_attributes(
            "blade_time",
            BLADE_MAINTENANCE_CYCLE_MINUTES,
            "recommended_cycle_hours",
            60,
        ),
    ),
    TerraMowSensorEntityDescription(
        key="remaining_base_station_time",
        translation_key="remaining_base_station_time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(125,),
        # Recommended base station cleaning cycle is 30 days, i.e. 43200 minutes
        value_fn=_maintenance_remaining(
            "base_station_time", BASE_STATION_MAINTENANCE_CYCLE_MINUTES
        ),
        attributes_fn=_maintenance_attributes(
            "base_station_time",
            BASE_STATION_MAINTENANCE_CYCLE_MINUTES,
            "recommended_cycle_days",
            60 * 24,
        ),
    ),
    # Global parameter display (dp_155)
    TerraMowSensorEntityDescription(
        key="mow_height",
        translation_key="mow_height",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(155,),
        value_fn=_mow_height,
    ),
    TerraMowSensorEntityDescription(
        key="main_direction_status",
        translation_key="main_direction_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(155,),
        value_fn=_main_direction_mode,
        attributes_fn=_main_direction_attributes,
    ),
    # Scheduled task (dp_138); no device class - display the time as a string
    TerraMowSensorEntityDescription(
        key="next_scheduled_start",
        translation_key="next_scheduled_start",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(138,),
        value_fn=_next_scheduled_start,
        attributes_fn=_next_scheduled_start_attributes,
    ),
    # Power mode (dp_107)
    TerraMowSensorEntityDescription(
        key="power_mode",
        translation_key="power_mode",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "power_mode_running",
            "power_mode_standby",
            "power_mode_hibernate",
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(107,),
        value_fn=_power_mode,
    ),
    # Mission state related (dp_107)
    TerraMowSensorEntityDescription(
        key="back_to_station_reason",
        translation_key="back_to_station_reason",
        device_class=SensorDeviceClass.ENUM,
        options=BACK_TO_STATION_REASON_OPTIONS.copy(),
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(107,),
        value_fn=_back_to_station_reason,
    ),
    TerraMowSensorEntityDescription(
        key="mission",
        translation_key="mission",
        device_class=SensorDeviceClass.ENUM,
        options=[to_ha_enum_state(member.value) for member in Mission],
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(107,),
        value_fn=_mission_enum("mission"),
    ),
    # Sub-mission surfaces transient states like waiting for rain.
    TerraMowSensorEntityDescription(
        key="sub_mission",
        translation_key="sub_mission",
        device_class=SensorDeviceClass.ENUM,
        options=[to_ha_enum_state(member.value) for member in SubMission],
        entity_category=EntityCategory.DIAGNOSTIC,
        # dp_118 (map-save progress) can retire a stale SAVING_MAP; refresh on
        # it too so the decay to idle shows without waiting for a poll (#142).
        push_dp_ids=(107, 118),
        value_fn=_mission_enum("display_sub_mission"),
    ),
    # Mission lifecycle state: idle / running / paused / abort / complete.
    TerraMowSensorEntityDescription(
        key="mission_state",
        translation_key="mission_state",
        device_class=SensorDeviceClass.ENUM,
        options=[to_ha_enum_state(member.value) for member in MissionState],
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(107, 118),
        value_fn=_mission_enum("display_mission_state"),
    ),
    # Unofficial / reverse-engineered diagnostics; see
    # docs/en/developers/data_point_unofficial.md.
    # Number of active device errors (dp_116): only the count is the state,
    # the raw list is attached as an attribute.
    TerraMowSensorEntityDescription(
        key="active_errors",
        translation_key="active_errors",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(116,),
        value_fn=_active_errors,
        attributes_fn=_active_errors_attributes,
    ),
    # Code of the most recent device event (dp_123); its timestamp is an
    # attribute. Raw event code, niche; off by default.
    TerraMowSensorEntityDescription(
        key="last_event",
        translation_key="last_event",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(123,),
        value_fn=_last_event_code,
        attributes_fn=_last_event_attributes,
    ),
    # Cellular / 4G diagnostics (dp_135). None while cellular is disabled.
    TerraMowSensorEntityDescription(
        key="cellular_signal_rsrp",
        translation_key="cellular_signal_rsrp",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(135,),
        value_fn=_cellular_signal("RSRP"),
    ),
    TerraMowSensorEntityDescription(
        key="cellular_signal_rsrq",
        translation_key="cellular_signal_rsrq",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(135,),
        value_fn=_cellular_signal("RSRQ"),
    ),
    # Niche; the enabled/RSRP/RSRQ sensors cover the useful cellular state.
    TerraMowSensorEntityDescription(
        key="cellular_connection_type",
        translation_key="cellular_connection_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(135,),
        value_fn=_cellular_type,
    ),
    # Device-reported sunrise/sunset (dp_152). Home Assistant already provides
    # these via the sun integration, so they are a niche extra: off by default.
    TerraMowSensorEntityDescription(
        key="sunrise",
        translation_key="sunrise",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(152,),
        value_fn=_sun_time("sunrise"),
    ),
    TerraMowSensorEntityDescription(
        key="sunset",
        translation_key="sunset",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(152,),
        value_fn=_sun_time("sunset"),
    ),
    # Operating-mode strings (dp_154). Advanced diagnostic enums; off by
    # default to avoid dashboard clutter.
    TerraMowSensorEntityDescription(
        key="move_mode",
        translation_key="move_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(154,),
        value_fn=_operating_mode("move_mode"),
    ),
    TerraMowSensorEntityDescription(
        key="map_mode",
        translation_key="map_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(154,),
        value_fn=_operating_mode("map_mode"),
    ),
    TerraMowSensorEntityDescription(
        key="mow_mode",
        translation_key="mow_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(154,),
        value_fn=_operating_mode("mow_mode"),
    ),
    # Advanced-settings readouts (dp_150, read-only); off by default.
    TerraMowSensorEntityDescription(
        key="rain_sensor_threshold",
        translation_key="rain_sensor_threshold",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(150,),
        value_fn=_rain_sensor_threshold,
    ),
    TerraMowSensorEntityDescription(
        key="after_rain_resume_delay",
        translation_key="after_rain_resume_delay",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(150,),
        value_fn=_after_rain_resume_delay,
    ),
    # Map-save / upload progress (dp_118): int_value 0-100 while the device
    # saves its map after a mow. Transient; off by default.
    TerraMowSensorEntityDescription(
        key="map_save_progress",
        translation_key="map_save_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(118,),
        value_fn=_map_save_progress,
    ),
)


# ---------------------------------------------------------------------------
# sensors with genuinely unique logic (kept as dedicated classes)
# ---------------------------------------------------------------------------


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
    entities: list[SensorEntity] = [
        # Sensors with unique logic
        BatterySensor(basic_data, hass),
        TerraMowPoseSensor(basic_data, hass),

        # Map-related sensors
        TerraMowMapStatusSensor(basic_data, hass),
        TerraMowMapAreaSensor(basic_data, hass),
        TerraMowCleanModeSensor(basic_data, hass),

        # Mow speed with its unknown-value tracking (dp_155)
        TerraMowMowSpeedSensor(basic_data, hass),

        # Version compatibility sensor (historical unique_id format)
        VersionCompatibilitySensor(basic_data, hass),
    ]

    # Description-driven sensors
    entities.extend(
        TerraMowSensor(basic_data, hass, description) for description in SENSORS
    )

    async_add_entities(entities)
