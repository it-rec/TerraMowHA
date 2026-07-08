from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, TerraMowConfigEntry
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin
from .hub import TerraMowHub

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TerraMowBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a TerraMow binary sensor computed from cached hub state.

    ``push_dp_ids`` are the data point IDs whose pushes refresh the entity
    (see ``PushUpdateMixin``). ``is_on_fn`` (and the optional
    ``attributes_fn``) receive the hub; the generic entity already handles
    the hub-is-None case.
    """

    push_dp_ids: tuple[int, ...]
    is_on_fn: Callable[[TerraMowHub], bool | None]
    attributes_fn: Callable[[TerraMowHub], dict[str, Any]] | None = None


class TerraMowBinarySensor(PushUpdateMixin, TerraMowEntity, BinarySensorEntity):
    """Generic binary sensor driven entirely by its entity description."""

    entity_description: TerraMowBinarySensorEntityDescription

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
        description: TerraMowBinarySensorEntityDescription,
    ) -> None:
        super().__init__(basic_data, hass)
        self.entity_description = description
        self._unique_id_suffix = description.key
        self._push_dp_ids = description.push_dp_ids

    @property
    def is_on(self) -> bool | None:
        """Return the flag computed from the hub state."""
        hub = self.hub
        if hub is None:
            return None
        return self.entity_description.is_on_fn(hub)

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
# is_on / attribute helpers shared by the BINARY_SENSORS table
# ---------------------------------------------------------------------------


def _optional_bool(value: Any) -> bool | None:
    return bool(value) if value is not None else None


def _battery_flag(field: str) -> Callable[[TerraMowHub], bool | None]:
    """Boolean flag from the dp_108 battery status block."""

    def is_on_fn(hub: TerraMowHub) -> bool | None:
        return _optional_bool(hub.battery_status.get(field))

    return is_on_fn


def _navigation_located(hub: TerraMowHub) -> bool | None:
    return _optional_bool(hub.is_robot_navi_located)


def _firmware_upgrading(hub: TerraMowHub) -> bool | None:
    return _optional_bool(hub.is_upgrading)


def _problem(hub: TerraMowHub) -> bool:
    return bool(hub.has_error)


def _rain_detected(hub: TerraMowHub) -> bool:
    return bool(hub.back_to_station_reason == "BACK_TO_STATION_REASON_RAINING")


def _map_status_flag(field: str) -> Callable[[TerraMowHub], bool | None]:
    """Boolean flag from the dp_117 map_status block."""

    def is_on_fn(hub: TerraMowHub) -> bool | None:
        map_status = hub.map_status
        if not map_status:
            return None
        return _optional_bool(map_status.get(field))

    return is_on_fn


def _task_status_flag(field: str) -> Callable[[TerraMowHub], bool | None]:
    """Boolean flag from the dp_107 task_status block."""

    def is_on_fn(hub: TerraMowHub) -> bool | None:
        task_status = hub.task_status
        if not task_status:
            return None
        return _optional_bool(task_status.get(field))

    return is_on_fn


def _cellular_enabled(hub: TerraMowHub) -> bool | None:
    if not hub.cellular_info:
        return None
    return bool(hub.cellular_info.get("is_enabled"))


def _environment_flag(
    field: str, *, invert: bool = False
) -> Callable[[TerraMowHub], bool | None]:
    """Boolean flag from the dp_152 environment block, optionally inverted."""

    def is_on_fn(hub: TerraMowHub) -> bool | None:
        if not hub.environment_info:
            return None
        value = bool(hub.environment_info.get(field))
        return not value if invert else value

    return is_on_fn


def _extreme_weather(hub: TerraMowHub) -> bool | None:
    if not hub.weather_info:
        return None
    return bool(hub.weather_info.get("has_extream_weather"))


def _extreme_weather_attributes(hub: TerraMowHub) -> dict[str, Any]:
    if not hub.weather_info:
        return {}
    url = hub.weather_info.get("extream_weather_info_url")
    return {"info_url": url} if isinstance(url, str) and url else {}


def _advanced_setting_flag(*path: str) -> Callable[[TerraMowHub], bool | None]:
    """Nested boolean read via ``path`` from the dp_150 advanced settings."""

    def is_on_fn(hub: TerraMowHub) -> bool | None:
        if not hub.advanced_settings:
            return None
        node: object = hub.advanced_settings
        for key in path:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        return node if isinstance(node, bool) else None

    return is_on_fn


def _manual_mapping_flag(field: str) -> Callable[[TerraMowHub], bool | None]:
    """Boolean flag from the dp_152 ``manual_mapping`` block."""

    def is_on_fn(hub: TerraMowHub) -> bool | None:
        manual = hub.environment_info.get("manual_mapping")
        if not isinstance(manual, dict):
            return None
        value = manual.get(field)
        return value if isinstance(value, bool) else None

    return is_on_fn


def _state_flag_134(hub: TerraMowHub) -> bool | None:
    # ``1`` -> on, ``0`` -> off, anything else -> unknown.
    value = hub.state_flag_134.get("enum_value")
    if value == 0 or value == 1:
        return bool(value == 1)
    return None


BINARY_SENSORS: tuple[TerraMowBinarySensorEntityDescription, ...] = (
    TerraMowBinarySensorEntityDescription(
        key="charging_state",
        translation_key="charging_state",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(108,),
        is_on_fn=_battery_flag("charger_connected"),
    ),
    TerraMowBinarySensorEntityDescription(
        key="navigation_located",
        translation_key="navigation_located",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(107,),
        is_on_fn=_navigation_located,
    ),
    # RUNNING (on = upgrade running), not UPDATE: this reflects an in-progress
    # firmware install, whereas device_class=update reads as "update available".
    TerraMowBinarySensorEntityDescription(
        key="firmware_upgrading",
        translation_key="firmware_upgrading",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(107,),
        is_on_fn=_firmware_upgrading,
    ),
    TerraMowBinarySensorEntityDescription(
        key="power_switch",
        translation_key="power_switch",
        device_class=BinarySensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(108,),
        is_on_fn=_battery_flag("is_switch_on"),
    ),
    # The dp_107 has_error flag exposed as a problem.
    TerraMowBinarySensorEntityDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(107,),
        is_on_fn=_problem,
    ),
    # Signals when the robot returns due to rain.
    TerraMowBinarySensorEntityDescription(
        key="rain_detected",
        translation_key="rain_detected",
        device_class=BinarySensorDeviceClass.MOISTURE,
        push_dp_ids=(107,),
        is_on_fn=_rain_detected,
    ),
    # dp_117 map_status flags
    TerraMowBinarySensorEntityDescription(
        key="map_detected",
        translation_key="map_detected",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(117,),
        is_on_fn=_map_status_flag("is_map_detected"),
    ),
    # True when a build-map command would be accepted.
    TerraMowBinarySensorEntityDescription(
        key="map_buildable",
        translation_key="map_buildable",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(117,),
        is_on_fn=_map_status_flag("is_able_to_run_build_map"),
    ),
    TerraMowBinarySensorEntityDescription(
        key="map_backing_up",
        translation_key="map_backing_up",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(117,),
        is_on_fn=_map_status_flag("is_backing_up_map"),
    ),
    # dp_107 task_status flags. Per the data point documentation the robot may
    # not respond to operation commands while it is saving data.
    TerraMowBinarySensorEntityDescription(
        key="saving_data",
        translation_key="saving_data",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(107,),
        is_on_fn=_task_status_flag("is_saving_data"),
    ),
    TerraMowBinarySensorEntityDescription(
        key="data_conversion",
        translation_key="data_conversion",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(107,),
        is_on_fn=_task_status_flag("is_data_conversion_in_progress"),
    ),
    # Unofficial / reverse-engineered diagnostics; see
    # docs/en/developers/data_point_unofficial.md.
    # Whether the cellular/4G modem is enabled (dp_135). Only present on
    # models with a cellular modem; None until dp_135 arrives.
    TerraMowBinarySensorEntityDescription(
        key="cellular_enabled",
        translation_key="cellular_enabled",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(135,),
        is_on_fn=_cellular_enabled,
    ),
    # dp_152 environment flags
    TerraMowBinarySensorEntityDescription(
        key="defogger_heating",
        translation_key="defogger_heating",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(152,),
        is_on_fn=_environment_flag("is_defogger_heating"),
    ),
    TerraMowBinarySensorEntityDescription(
        key="illumination_light",
        translation_key="illumination_light",
        device_class=BinarySensorDeviceClass.LIGHT,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(152,),
        is_on_fn=_environment_flag("is_illuminate_light_on"),
    ),
    # Derived from ``is_not_in_daylight_period`` (inverted).
    TerraMowBinarySensorEntityDescription(
        key="daylight",
        translation_key="daylight",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(152,),
        is_on_fn=_environment_flag("is_not_in_daylight_period", invert=True),
    ),
    # Extreme-weather warning (dp_157): ``has_extream_weather`` (device
    # spelling); an optional info URL is exposed as an attribute.
    TerraMowBinarySensorEntityDescription(
        key="extreme_weather",
        translation_key="extreme_weather",
        device_class=BinarySensorDeviceClass.SAFETY,
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(157,),
        is_on_fn=_extreme_weather,
        attributes_fn=_extreme_weather_attributes,
    ),
    # dp_150 advanced-setting readouts (read-only)
    TerraMowBinarySensorEntityDescription(
        key="cliff_detection",
        translation_key="cliff_detection",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(150,),
        is_on_fn=_advanced_setting_flag("enable_cliff_detection", "value"),
    ),
    TerraMowBinarySensorEntityDescription(
        key="slope_detection",
        translation_key="slope_detection",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(150,),
        is_on_fn=_advanced_setting_flag("enable_slope_detection", "value"),
    ),
    TerraMowBinarySensorEntityDescription(
        key="after_rain_auto_resume",
        translation_key="after_rain_auto_resume",
        entity_category=EntityCategory.DIAGNOSTIC,
        push_dp_ids=(150,),
        is_on_fn=_advanced_setting_flag(
            "after_rain_stop_setting", "enable_auto_resume"
        ),
    ),
    TerraMowBinarySensorEntityDescription(
        key="force_single_base_station",
        translation_key="force_single_base_station",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(150,),
        is_on_fn=_advanced_setting_flag("force_single_base_station_mode", "value"),
    ),
    TerraMowBinarySensorEntityDescription(
        key="force_cellular_network",
        translation_key="force_cellular_network",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(150,),
        is_on_fn=_advanced_setting_flag("force_cellular_network", "value"),
    ),
    # dp_152 ``manual_mapping`` flags (read-only): transient states during
    # manual mapping; off by default.
    TerraMowBinarySensorEntityDescription(
        key="manual_mapping_relocation",
        translation_key="manual_mapping_relocation",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(152,),
        is_on_fn=_manual_mapping_flag("need_relocation"),
    ),
    TerraMowBinarySensorEntityDescription(
        key="manual_mapping_takeover",
        translation_key="manual_mapping_takeover",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(152,),
        is_on_fn=_manual_mapping_flag("need_takeover"),
    ),
    TerraMowBinarySensorEntityDescription(
        key="manual_mapping_boundary_closed",
        translation_key="manual_mapping_boundary_closed",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(152,),
        is_on_fn=_manual_mapping_flag("is_boundary_closed"),
    ),
    # Undecoded binary flag (dp_134): the device sends ``{"enum_value":0|1}``
    # which toggles during operation; its meaning is unknown. Surfaced purely
    # so the flag can be correlated with mower behaviour and decoded.
    TerraMowBinarySensorEntityDescription(
        key="state_flag_134",
        translation_key="state_flag_134",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        push_dp_ids=(134,),
        is_on_fn=_state_flag_134,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow binary sensor entities."""
    basic_data = config_entry.runtime_data

    async_add_entities(
        TerraMowBinarySensor(basic_data, hass, description)
        for description in BINARY_SENSORS
    )
