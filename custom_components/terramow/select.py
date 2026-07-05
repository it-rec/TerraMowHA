from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_component
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, TerraMowBasicData, TerraMowConfigEntry
from .const import (
    DEFAULT_BLADE_DISK_SPEED_TYPE,
    MIN_MOW_SPEED_VERSION_FOR_AUTO,
    MOW_SPEED_TYPE_ADAPTIVE_HIGH,
    MOW_SPEED_TYPE_AUTO,
    MOW_SPEED_TYPE_LOW,
    MOW_SPEED_TYPE_MEDIUM,
    MOW_SPEED_TYPES,
    to_device_enum,
    to_ha_enum_state,
)
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
    """Set up TerraMow select entities."""
    basic_data = config_entry.runtime_data

    # Create select entities
    entities = [
        TerraMowZoneSelect(basic_data, hass),
        MowSpeedSelect(basic_data, hass),
        BladeSpeedSelect(basic_data, hass),
        MainDirectionModeSelect(basic_data, hass),
        HighGrassEdgeTrimModeSelect(basic_data, hass),
    ]

    async_add_entities(entities)

class TerraMowZoneSelect(TerraMowEntity, SelectEntity):
    """Map zone selector - Zone selector for mowing specific areas."""

    _attr_entity_category = EntityCategory.CONFIG

    # Note: translation_key intentionally stays "region_select" rather than
    # "zone_select".
    # Reason: to preserve backward compatibility and avoid changing entity_id.
    # entity_id format: select.terramow_{host}_region_select
    # The actual display name is controlled by the translation files and has
    # been changed to "Zone Select" (with a localized name per language).
    _attr_translation_key = "region_select"

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        super().__init__(basic_data, hass)
        self._map_info: dict[str, Any] = {}
        self._current_option: str | None = None
        self._options = ["no_zones_available"]

        # Register the map info callback
        if hasattr(basic_data, 'lawn_mower') and basic_data.lawn_mower:
            basic_data.lawn_mower.register_map_callback(self._on_map_info)

    # Note: unique_id intentionally stays "region_select" for backward
    # compatibility. This ensures entity_id does not change after an upgrade,
    # so users' automation scripts need no modification.
    _unique_id_suffix = "region_select"

    @property
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        return self._options

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in self._options:
            _LOGGER.warning("Invalid zone option selected: %s", option)
            return

        if option == "no_zones_available" or option == "all_zones":
            # These are special options; do not perform an actual zone switch
            self._current_option = option
            self.async_write_ha_state()
            return

        # Parse the zone ID
        try:
            # Format: "zone name (ID: 123)"
            if " (ID: " in option:
                zone_id_str = option.split(" (ID: ")[1].rstrip(")")
                zone_id = int(zone_id_str)

                # Send the zone-select mowing command
                await self._start_zone_clean(zone_id)
                self._current_option = option
                self.async_write_ha_state()
            else:
                _LOGGER.warning("Unable to parse zone ID from option: %s", option)

        except (ValueError, IndexError) as e:
            _LOGGER.error("Error parsing zone option %s: %s", option, e)

    async def _start_zone_clean(self, zone_id: int) -> None:
        """Send the zone-clean command."""
        _LOGGER.info("Starting zone clean for zone ID: %d", zone_id)

        # Get the lawn_mower entity to send the command
        if hasattr(self.basic_data, 'lawn_mower') and self.basic_data.lawn_mower:
            command = {
                'seq': self.basic_data.lawn_mower.get_cmd_seq(),
                'mode': 'START_MODE_SELECT_REGION_CLEAN',  # Device protocol field, keep unchanged
                'select_region_clean': {  # Device protocol field, keep unchanged
                    'region_ids': [zone_id]  # Device protocol field name, keep unchanged
                }
            }
            self.basic_data.lawn_mower.publish_data_point(103, command)
            _LOGGER.info("Zone clean command sent: zone_id=%d", zone_id)
        else:
            _LOGGER.error("Cannot send zone clean command: lawn_mower not available")

    async def _on_map_info(self, map_info: dict[str, Any]) -> None:
        """Handle a map info update."""
        self._map_info = map_info
        self._update_options()
        safe_write_ha_state(self)

    def _update_options(self) -> None:
        """Update the list of selectable zones based on the map info."""
        if not self._map_info:
            self._options = ["no_zones_available"]
            self._current_option = "no_zones_available"
            return

        regions = self._map_info.get('regions', [])  # Device protocol field name, keep unchanged
        if not regions:
            self._options = ["no_zones_available"]
            self._current_option = "no_zones_available"
            return

        # Build the zone option list - only add sub-zones
        options = ["all_zones"]  # Add the "all zones" option

        for region in regions:
            # Only process sub-zones (the device protocol uses the sub_regions field name)
            sub_regions = region.get('sub_regions', [])  # Device protocol field name, keep unchanged
            for sub_zone in sub_regions:
                sub_zone_id = sub_zone.get('id')
                sub_zone_name = sub_zone.get('name', f'Sub-zone {sub_zone_id}')

                if sub_zone_name and sub_zone_name.strip():
                    sub_option = f"{sub_zone_name} (ID: {sub_zone_id})"
                else:
                    sub_option = f"Sub-zone {sub_zone_id} (ID: {sub_zone_id})"
                options.append(sub_option)

        self._options = options

        # Set the current option
        if not self._current_option or self._current_option not in self._options:
            self._current_option = "all_zones"

        _LOGGER.debug("Updated zone options: %d sub-zones available", len(self._options) - 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        if not self._map_info:
            return {}

        regions = self._map_info.get('regions', [])  # Device protocol field name, keep unchanged

        # Count all sub-zones
        all_sub_zones = []
        for region in regions:
            sub_regions = region.get('sub_regions', [])  # Device protocol field name, keep unchanged
            for sub_zone in sub_regions:
                sub_zone_info = {
                    'id': sub_zone.get('id'),
                    'name': sub_zone.get('name', ''),
                    'parent_region_id': region.get('id'),  # Device protocol field name, keep unchanged
                    'parent_region_name': region.get('name', '')
                }
                all_sub_zones.append(sub_zone_info)

        attrs = {
            'map_id': self._map_info.get('id'),
            'sub_zones_count': len(all_sub_zones),
            'available_sub_zones': all_sub_zones
        }

        # Show the current cleaning info
        clean_info = self._map_info.get('clean_info', {})
        if clean_info.get('mode') == 'MAP_CLEAN_INFO_MODE_SELECT_REGION':  # Device protocol constant, keep unchanged
            select_region = clean_info.get('select_region', {})  # Device protocol field name, keep unchanged
            selected_zone_ids = select_region.get('region_id', [])  # Device protocol field name, keep unchanged
            attrs['currently_selected_zones'] = selected_zone_ids

        return attrs


class MowSpeedSelect(PushUpdateMixin, TerraMowEntity, SelectEntity):
    """Mowing travel-speed selector - uses dp_155 data."""

    _push_dp_ids = (155,)

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "mow_speed_setting"

    # When the firmware does not support AUTO, only show the first three levels
    _BASE_OPTIONS = [
        MOW_SPEED_TYPE_LOW,
        MOW_SPEED_TYPE_MEDIUM,
        MOW_SPEED_TYPE_ADAPTIVE_HIGH,
    ]

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        super().__init__(basic_data, hass)
        self._current_option: str | None = MOW_SPEED_TYPE_MEDIUM  # Default: medium speed
        self._unknown_speed_type: str | None = None

    def _get_mow_speed_feature_version(self) -> int | None:
        """Get the firmware's mow-speed feature version number."""
        firmware_info = self.basic_data.firmware_version or {}
        module_info = firmware_info.get("module", {})
        version = module_info.get("mow_speed")

        if isinstance(version, bool):
            return None
        if isinstance(version, int):
            return version
        if isinstance(version, str):
            try:
                return int(version)
            except ValueError:
                return None
        return None

    def _get_device_speed_type(self) -> str | None:
        """Get the mow-speed enum currently reported by the device."""
        if not hasattr(self.basic_data, "lawn_mower") or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        mow_speed = global_params.get("mow_speed", {})
        speed_type = mow_speed.get("speed_type")
        if isinstance(speed_type, str) and speed_type:
            return speed_type
        return None

    def _is_auto_supported_by_firmware(self) -> bool:
        """Determine whether the firmware version supports the AUTO level."""
        feature_version = self._get_mow_speed_feature_version()
        return (
            feature_version is not None
            and feature_version >= MIN_MOW_SPEED_VERSION_FOR_AUTO
        )

    def _should_expose_auto_option(self) -> bool:
        """Determine whether the AUTO option should currently be exposed."""
        if self._is_auto_supported_by_firmware():
            return True
        # Compatibility fallback: if the device already reports AUTO, allow showing and selecting that option
        return self._get_device_speed_type() == MOW_SPEED_TYPE_AUTO

    _unique_id_suffix = "mow_speed_setting"

    @property
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        options = self._BASE_OPTIONS.copy()
        if self._should_expose_auto_option():
            options.append(MOW_SPEED_TYPE_AUTO)
        # Expose lowercase tokens to Home Assistant; device values stay UPPERCASE.
        return [to_ha_enum_state(o) for o in options]

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return to_ha_enum_state(self._current_option)

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return to_ha_enum_state(self._current_option)

        mow_speed = global_params.get('mow_speed', {})
        speed_type = mow_speed.get('speed_type')
        if not speed_type:
            self._unknown_speed_type = None
            self._current_option = None
            return None

        if speed_type in MOW_SPEED_TYPES:
            self._unknown_speed_type = None
            self._current_option = speed_type
            return to_ha_enum_state(self._current_option)

        if speed_type != self._unknown_speed_type:
            _LOGGER.warning(
                "Unknown mow speed type from device: %s. Expose raw value in attributes.",
                speed_type,
            )
            self._unknown_speed_type = speed_type

        self._current_option = None
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Home Assistant passes the lowercase token; map back to the device enum.
        option = to_device_enum(option)
        if option not in MOW_SPEED_TYPES:
            _LOGGER.error("Invalid mow speed option: %s", option)
            return

        if option == MOW_SPEED_TYPE_AUTO and not self._should_expose_auto_option():
            feature_version = self._get_mow_speed_feature_version()
            _LOGGER.warning(
                "Rejecting mow speed AUTO because firmware mow_speed version is %s (requires >= %d).",
                feature_version if feature_version is not None else "unknown",
                MIN_MOW_SPEED_VERSION_FOR_AUTO,
            )
            self.async_write_ha_state()
            return

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        # Send the set command to dp_155
        command = {
            'mow_speed': {
                'speed_type': option
            }
        }

        _LOGGER.info("Setting mow speed to %s", option)
        self.basic_data.lawn_mower.publish_data_point(155, command)
        self._current_option = option
        self._unknown_speed_type = None
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        feature_version = self._get_mow_speed_feature_version()
        auto_speed_supported = self._should_expose_auto_option()
        available_speeds: dict[str, str] = {
            MOW_SPEED_TYPE_LOW: 'Low Speed',
            MOW_SPEED_TYPE_MEDIUM: 'Medium Speed (Default)',
            MOW_SPEED_TYPE_ADAPTIVE_HIGH: 'Adaptive High Speed',
        }
        if auto_speed_supported:
            available_speeds[MOW_SPEED_TYPE_AUTO] = 'Auto (Load Adaptive)'

        attrs: dict[str, Any] = {
            'available_speeds': available_speeds,
            'auto_speed_supported': auto_speed_supported,
            'mow_speed_feature_version': feature_version if feature_version is not None else "unknown",
        }
        if self._unknown_speed_type:
            attrs['unknown_speed_type'] = self._unknown_speed_type
        return attrs


class BladeSpeedSelect(PushUpdateMixin, TerraMowEntity, SelectEntity):
    """Blade-disk speed selector - uses dp_155 data."""

    _push_dp_ids = (155,)

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "blade_speed"

    # Blade-disk speed options
    _attr_options = [
        "BLADE_DISK_SPEED_TYPE_LOW",
        "BLADE_DISK_SPEED_TYPE_MEDIUM",
        "BLADE_DISK_SPEED_TYPE_HIGH"
    ]

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        super().__init__(basic_data, hass)
        self._current_option = DEFAULT_BLADE_DISK_SPEED_TYPE  # Default: medium speed

    _unique_id_suffix = "blade_speed"

    @property
    def options(self) -> list[str]:
        """Return the selectable options as lowercase Home Assistant tokens."""
        return [to_ha_enum_state(o) for o in self._attr_options]

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return to_ha_enum_state(self._current_option)

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return to_ha_enum_state(self._current_option)

        blade_disk_speed = global_params.get('blade_disk_speed', {})
        speed_type = blade_disk_speed.get('speed_type')

        if speed_type and speed_type in self._attr_options:
            self._current_option = speed_type

        return to_ha_enum_state(self._current_option)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Home Assistant passes the lowercase token; map back to the device enum.
        option = to_device_enum(option)
        if option not in self._attr_options:
            _LOGGER.error("Invalid blade speed option: %s", option)
            return

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        # Send the set command to dp_155
        command = {
            'blade_disk_speed': {
                'speed_type': option
            }
        }

        _LOGGER.info("Setting blade speed to %s", option)
        self.basic_data.lawn_mower.publish_data_point(155, command)
        self._current_option = option
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return {
            'available_speeds': {
                'BLADE_DISK_SPEED_TYPE_LOW': 'Low Speed',
                'BLADE_DISK_SPEED_TYPE_MEDIUM': 'Medium Speed (Default)',
                'BLADE_DISK_SPEED_TYPE_HIGH': 'High Speed'
            }
        }


class MainDirectionModeSelect(PushUpdateMixin, TerraMowEntity, SelectEntity):
    """Main-direction mode selector - uses dp_155 data."""

    _push_dp_ids = (155,)

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "main_direction_mode"

    # Main-direction mode options
    _attr_options = [
        "MAIN_DIRECTION_MODE_SINGLE",
        "MAIN_DIRECTION_MODE_MULTIPLE",
        "MAIN_DIRECTION_MODE_AUTO_ROTATE"
    ]

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        super().__init__(basic_data, hass)
        self._current_option = "MAIN_DIRECTION_MODE_SINGLE"  # Default: single main direction
        self._pending_mode: str | None = None  # Cache the mode pending activation

        # Register the device-confirmation event listener
        self._register_device_confirmation_listener()

    def _register_device_confirmation_listener(self) -> None:
        """Register the device-confirmation event listener."""
        async def on_device_confirmed(event: Event) -> None:
            if event.data.get("device_host") == self.host:
                confirmed_mode = event.data.get("confirmed_mode")
                if confirmed_mode:
                    self.on_device_mode_confirmed(confirmed_mode)

        self.hass.bus.async_listen(f"{DOMAIN}_device_mode_confirmed", on_device_confirmed)

    _unique_id_suffix = "main_direction_mode"

    def get_effective_mode(self) -> str:
        """Get the currently effective mode (including any pending mode)."""
        # If there is a pending mode, return it in preference
        if self._pending_mode:
            return self._pending_mode

        # Otherwise try to get the actual mode from the device
        if hasattr(self.basic_data, 'lawn_mower') and self.basic_data.lawn_mower:
            global_params = self.basic_data.lawn_mower.global_params
            if global_params:
                main_direction_config = global_params.get('main_direction_angle_config', {})
                device_mode = main_direction_config.get('mode')
                if device_mode and device_mode in self._attr_options:
                    return str(device_mode)

        return self._current_option

    @property
    def options(self) -> list[str]:
        """Return the selectable options as lowercase Home Assistant tokens."""
        return [to_ha_enum_state(o) for o in self._attr_options]

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        mode = self.get_effective_mode()
        self._current_option = mode
        return to_ha_enum_state(mode)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Home Assistant passes the lowercase token; map back to the device enum.
        option = to_device_enum(option)
        if option not in self._attr_options:
            _LOGGER.error("Invalid main direction mode option: %s", option)
            return

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        # Save the old mode for the event notification
        old_mode = self._current_option

        # Set the pending state immediately to give instant feedback
        self._pending_mode = option
        self._current_option = option

        # Update the current entity state immediately
        self.async_write_ha_state()

        # Notify the related angle controllers to update availability immediately (pass the old and new modes)
        self._notify_angle_controllers_mode_change(old_mode, option)

        # Get the current global params to preserve the other configuration
        global_params = self.basic_data.lawn_mower.global_params or {}
        current_main_direction = global_params.get('main_direction_angle_config', {})

        # Build the main-direction configuration
        main_direction_config: dict[str, Any] = {
            'mode': option
        }

        # Add the corresponding configuration structure based on the mode
        if option == "MAIN_DIRECTION_MODE_SINGLE":
            # Keep the existing single-main-direction config, or use the default of 0 degrees
            current_single_config: dict[str, Any] = current_main_direction.get('single_mode_config', {})
            main_direction_config['single_mode_config'] = {
                'angle': current_single_config.get('angle', 0)
            }
        elif option == "MAIN_DIRECTION_MODE_MULTIPLE":
            # Keep the existing multiple-main-direction config, or use the default angle list
            current_multiple_config: dict[str, Any] = current_main_direction.get('multiple_mode_config', {})
            main_direction_config['multiple_mode_config'] = {
                'angles': current_multiple_config.get('angles', [0, 90])
            }
        elif option == "MAIN_DIRECTION_MODE_AUTO_ROTATE":
            # Keep the existing auto-rotate config, or use the default interval of 15 degrees
            current_auto_config: dict[str, Any] = current_main_direction.get('auto_rotate_mode_config', {})
            main_direction_config['auto_rotate_mode_config'] = {
                'angle_interval': current_auto_config.get('angle_interval', 15)
            }

        # Send the set command to dp_155
        command = {
            'main_direction_angle_config': main_direction_config
        }

        _LOGGER.info("Setting main direction mode from %s to %s", old_mode, option)
        self.basic_data.lawn_mower.publish_data_point(155, command)

        # Set a timeout to clear the pending state (prevents a failed device response from leaving the state stuck)
        self.hass.async_create_task(self._clear_pending_mode_after_timeout())

    def _notify_angle_controllers_mode_change(self, old_mode: str, new_mode: str) -> None:
        """Notify the related angle controllers that the mode has changed."""
        # Fire a Home Assistant event that the angle controllers can listen for
        self.hass.bus.fire(f"{DOMAIN}_main_direction_mode_changed", {
            "device_host": self.host,
            "old_mode": old_mode,
            "new_mode": new_mode,
            "source": "mode_select"
        })

        # Trigger a delayed state update for all related entities
        async def delayed_update() -> None:
            await self.hass.async_add_executor_job(self._force_update_related_entities)

        self.hass.async_create_task(delayed_update())

    def _force_update_related_entities(self) -> None:
        """Force a state update of the related angle-control entities."""
        try:
            # Simplified entity-update approach: update directly by inferring the entity_id
            related_entity_patterns = [
                "main_direction_single_angle",
                "main_direction_auto_rotate_interval",
                "multiple_direction_angle1",
                "multiple_direction_angle2"
            ]

            entities_to_update = []
            host_suffix = self.host.replace('.', '_')

            for pattern in related_entity_patterns:
                # Construct the expected entity_id
                entity_id = f"number.terramow_{host_suffix}_{pattern}"
                # Check whether the entity exists
                if self.hass.states.get(entity_id):
                    entities_to_update.append(entity_id)

            # Trigger a state update for these entities
            for entity_id in entities_to_update:
                try:
                    # Schedule the update asynchronously
                    self.hass.async_create_task(
                        entity_component.async_update_entity(self.hass, entity_id)
                    )
                except Exception as update_error:
                    _LOGGER.debug("Could not update entity %s: %s", entity_id, update_error)

            _LOGGER.debug("Triggered state update for angle control entities: %s", entities_to_update)
        except Exception as e:
            _LOGGER.warning("Failed to force update related entities: %s", e)

    async def _clear_pending_mode_after_timeout(self) -> None:
        """Clear the pending state after a timeout."""
        import asyncio
        await asyncio.sleep(10)  # 10-second timeout
        if self._pending_mode:
            _LOGGER.info("Clearing pending mode %s after timeout", self._pending_mode)
            self._pending_mode = None
            self.async_write_ha_state()

    def on_device_mode_confirmed(self, confirmed_mode: str) -> None:
        """Callback invoked after the device confirms a mode change."""
        if self._pending_mode == confirmed_mode:
            _LOGGER.debug("Device confirmed mode change to %s, clearing pending state", confirmed_mode)
            self._pending_mode = None
            safe_write_ha_state(self)
        elif self._pending_mode:
            _LOGGER.warning("Device confirmed mode %s but pending mode was %s",
                          confirmed_mode, self._pending_mode)
            self._pending_mode = None
            self._current_option = confirmed_mode
            safe_write_ha_state(self)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs: dict[str, Any] = {
            'available_modes': {
                'MAIN_DIRECTION_MODE_SINGLE': 'Single Direction',
                'MAIN_DIRECTION_MODE_MULTIPLE': 'Multiple Directions',
                'MAIN_DIRECTION_MODE_AUTO_ROTATE': 'Auto Rotate Direction'
            }
        }

        # Add status information
        if self._pending_mode:
            attrs['status'] = 'changing_mode'
            attrs['pending_mode'] = self._pending_mode
        else:
            attrs['status'] = 'active'

        # Add detailed information about the current configuration
        if hasattr(self.basic_data, 'lawn_mower') and self.basic_data.lawn_mower:
            global_params = self.basic_data.lawn_mower.global_params
            if global_params:
                main_direction_config = global_params.get('main_direction_angle_config', {})
                current_angle = main_direction_config.get('current_angle')
                if current_angle is not None:
                    attrs['current_angle'] = current_angle

                mode = main_direction_config.get('mode')
                if mode == 'MAIN_DIRECTION_MODE_SINGLE':
                    single_config = main_direction_config.get('single_mode_config', {})
                    attrs['single_angle'] = single_config.get('angle', 0)
                elif mode == 'MAIN_DIRECTION_MODE_MULTIPLE':
                    multiple_config = main_direction_config.get('multiple_mode_config', {})
                    attrs['multiple_angles'] = multiple_config.get('angles', [])
                elif mode == 'MAIN_DIRECTION_MODE_AUTO_ROTATE':
                    auto_config = main_direction_config.get('auto_rotate_mode_config', {})
                    attrs['auto_rotate_interval'] = auto_config.get('angle_interval', 15)

        return attrs


class HighGrassEdgeTrimModeSelect(PushUpdateMixin, TerraMowEntity, SelectEntity):
    """High grass edge trim mode selector — published via dp_155.

    Note: high_grass_edge_trim_mode is reported under map_info["mow_param"],
    but the documented data point for global operation parameter writes is
    dp_155. Until a dedicated DP for the mow_param fields is documented,
    we publish the selection to dp_155 with the matching sub-dict — adjust
    if firmware exposes a different DP.
    """

    _push_map_info = True

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "high_grass_edge_trim_mode"

    _attr_options = [
        "HIGH_GRASS_EDGE_TRIM_STANDARD",
        "HIGH_GRASS_EDGE_TRIM_INTENSIVE",
    ]

    _unique_id_suffix = "high_grass_edge_trim_mode"

    def _get_mow_param(self) -> dict[str, Any] | None:
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None
        map_info = self.basic_data.lawn_mower.map_info
        if not map_info:
            return None
        mow_param = map_info.get('mow_param')
        if not isinstance(mow_param, dict):
            return None
        return mow_param

    @property
    def options(self) -> list[str]:
        """Return the selectable options as lowercase Home Assistant tokens."""
        return [to_ha_enum_state(o) for o in self._attr_options]

    @property
    def current_option(self) -> str | None:
        mow_param = self._get_mow_param()
        if mow_param is None:
            return None
        trim_cfg = mow_param.get('high_grass_edge_trim_mode')
        if not isinstance(trim_cfg, dict):
            return None
        mode = trim_cfg.get('mode')
        if mode in self._attr_options:
            return to_ha_enum_state(mode)
        return None

    async def async_select_option(self, option: str) -> None:
        # Home Assistant passes the lowercase token; map back to the device enum.
        option = to_device_enum(option)
        if option not in self._attr_options:
            _LOGGER.error("Invalid high grass edge trim mode option: %s", option)
            return

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        command = {
            'high_grass_edge_trim_mode': {
                'mode': option,
            }
        }

        _LOGGER.info("Setting high grass edge trim mode to %s", option)
        self.basic_data.lawn_mower.publish_data_point(155, command)
        self.async_write_ha_state()
