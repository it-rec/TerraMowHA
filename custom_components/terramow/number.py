from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, TerraMowConfigEntry
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
    """Set up TerraMow number entities."""
    basic_data = config_entry.runtime_data

    # Create number control entities
    entities = [
        MowingHeightNumber(basic_data, hass),
        EdgeCuttingDistanceNumber(basic_data, hass),
        MowingSpacingNumber(basic_data, hass),
        MainDirectionSingleAngleNumber(basic_data, hass),
        MainDirectionAutoRotateIntervalNumber(basic_data, hass),
        MultipleDirectionAngle1Number(basic_data, hass),
        MultipleDirectionAngle2Number(basic_data, hass),
    ]

    async_add_entities(entities)


class TerraMowNumberBase(PushUpdateMixin, TerraMowEntity, NumberEntity):
    """Base class for TerraMow number controls."""

    _push_dp_ids = (155,)

    # Cached mode pushed by the main-direction-mode selector event; None when
    # the entity should fall back to reading the device's global params.
    _cached_mode: str | None = None

    # Angle controllers refresh promptly on the shared main-direction
    # mode-change event; the plain number entities leave this False.
    _listens_for_mode_change: bool = False

    # Angle controllers are only usable while the device is in a specific
    # main-direction mode (device enum string); None means always usable.
    _required_mode: str | None = None

    async def async_added_to_hass(self) -> None:
        """Register push callbacks and, for angle controllers, the mode listener."""
        await super().async_added_to_hass()
        if self._listens_for_mode_change:
            self._register_mode_change_listener()

    async def _handle_push_update(self, _payload: str) -> None:
        # Device data is authoritative once it arrives; drop the optimistic
        # mode cached from the selector's mode-change event.
        self._cached_mode = None
        await super()._handle_push_update(_payload)

    def _current_main_direction_mode(self) -> str | None:
        """Return the effective main-direction mode as a device enum string.

        Prefers the mode cached from the selector's mode-change event (instant
        feedback while the device has not confirmed yet) and falls back to the
        device-reported global params.
        """
        if self._cached_mode:
            return self._cached_mode

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        main_direction_config = global_params.get('main_direction_angle_config', {})
        return str(main_direction_config.get('mode', 'MAIN_DIRECTION_MODE_SINGLE'))

    @property
    def available(self) -> bool:
        """Return True when connected and, for angle controls, in the right mode."""
        if not super().available:
            return False
        if self._required_mode is None:
            return True
        return self._current_main_direction_mode() == self._required_mode

    def _register_mode_change_listener(self) -> None:
        """Refresh on the shared main-direction mode-change event.

        The unsubscribe callable is handed to ``async_on_remove`` so the
        listener is torn down when the entity is removed (reload/reconfigure).
        Without it, stale listeners accumulate across reloads and keep writing
        state on removed entities.
        """
        async def on_mode_changed(event: Event) -> None:
            if event.data.get("device_host") == self.host:
                new_mode = event.data.get("new_mode")
                if new_mode:
                    self._cached_mode = new_mode
                safe_write_ha_state(self)

        self.async_on_remove(
            self.hass.bus.async_listen(
                f"{DOMAIN}_main_direction_mode_changed", on_mode_changed
            )
        )
        self._cached_mode = None  # Initialize the cached mode

    def _clamp_native(self, value: float) -> float:
        """Clamp a device-reported value into the entity's declared range.

        Some firmware reports a value slightly outside the advertised range;
        returning it unclamped makes Home Assistant log a "not within range"
        warning on every state write. Clamping keeps the readout within the
        entity's contract.
        """
        return min(self.native_max_value, max(self.native_min_value, value))


class MowingHeightNumber(TerraMowNumberBase):
    """Mowing height setting controller - uses dp_155 data."""

    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_device_class = NumberDeviceClass.DISTANCE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "mowing_height"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 20
    _attr_native_max_value = 70
    _attr_native_step = 1

    _unique_id_suffix = "mowing_height"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        mow_height = global_params.get('mow_height', {})
        value = mow_height.get('value')
        return self._clamp_native(float(value)) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the mowing height."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        # Send the set command to dp_155
        command = {
            'mow_height': {
                'value': int(value)
            }
        }

        _LOGGER.info("Setting mowing height to %d mm", int(value))
        self.basic_data.lawn_mower.publish_data_point(155, command)


class EdgeCuttingDistanceNumber(TerraMowNumberBase):
    """Edge cutting distance setting controller - uses dp_155 data."""

    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_device_class = NumberDeviceClass.DISTANCE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "edge_cutting_distance"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -150
    _attr_native_max_value = 150
    _attr_native_step = 1

    _unique_id_suffix = "edge_cutting_distance"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        edge_cutting_distance = global_params.get('edge_cutting_distance', {})
        value = edge_cutting_distance.get('value')
        return self._clamp_native(float(value)) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the edge cutting distance."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        # Send the set command to dp_155
        command = {
            'edge_cutting_distance': {
                'value': int(value)
            }
        }

        _LOGGER.info("Setting edge cutting distance to %d mm", int(value))
        self.basic_data.lawn_mower.publish_data_point(155, command)


class MowingSpacingNumber(TerraMowNumberBase):
    """Mowing spacing setting controller - uses dp_155 data."""

    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_device_class = NumberDeviceClass.DISTANCE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "mowing_spacing"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 80  # 8cm minimum
    _attr_native_max_value = 140  # 14cm maximum
    _attr_native_step = 10  # 1cm step

    _unique_id_suffix = "mowing_spacing"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        mow_spacing = global_params.get('mow_spacing', {})
        value = mow_spacing.get('value')
        return self._clamp_native(float(value)) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs: dict[str, Any] = {
            'valid_range': '80-140mm (8-14cm)',
            'warning': 'Changing this value will reset mowing progress'
        }
        # dp_155's current_mow_spacing is reported by the robot only and
        # represents the mowing spacing actually in effect (the set value may
        # not take effect until the mowing progress is reset).
        if hasattr(self.basic_data, 'lawn_mower') and self.basic_data.lawn_mower:
            global_params = self.basic_data.lawn_mower.global_params or {}
            current = global_params.get('current_mow_spacing')
            if current is not None:
                attrs['current_mow_spacing'] = current
        return attrs

    async def async_set_native_value(self, value: float) -> None:
        """Set the mowing spacing."""
        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        # Validate the input range
        int_value = int(value)
        if int_value < 80 or int_value > 140:
            _LOGGER.error("Invalid mowing spacing value: %d mm. Valid range: 80-140mm", int_value)
            return

        # Send the set command to dp_155
        command = {
            'mow_spacing': {
                'value': int_value
            }
        }

        _LOGGER.info("Setting mowing spacing to %d mm (will reset mowing progress)", int_value)
        self.basic_data.lawn_mower.publish_data_point(155, command)


class MainDirectionSingleAngleNumber(TerraMowNumberBase):
    """Single main-direction angle setting controller - uses dp_155 data."""

    _attr_native_unit_of_measurement = "°"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "main_direction_single_angle"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 359
    _attr_native_step = 1
    _listens_for_mode_change = True
    _required_mode = 'MAIN_DIRECTION_MODE_SINGLE'

    _unique_id_suffix = "main_direction_single_angle"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.available:
            return None

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        main_direction_config = global_params.get('main_direction_angle_config', {})
        single_config = main_direction_config.get('single_mode_config', {})
        angle = single_config.get('angle')
        return float(angle) if angle is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the single main direction angle."""
        if not self.available:
            _LOGGER.error("Single angle control not available in current mode")
            return

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        # Ensure the angle value stays within the 0-359 range
        angle_value = int(value) % 360

        # Send the set command to dp_155
        command = {
            'main_direction_angle_config': {
                'mode': 'MAIN_DIRECTION_MODE_SINGLE',
                'single_mode_config': {
                    'angle': angle_value
                }
            }
        }

        _LOGGER.info("Setting single main direction angle to %d degrees", angle_value)
        self.basic_data.lawn_mower.publish_data_point(155, command)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            'valid_range': '0-359 degrees',
            'description': 'Angle for single main direction mode'
        }

        # Add the current angle information
        if hasattr(self.basic_data, 'lawn_mower') and self.basic_data.lawn_mower:
            global_params = self.basic_data.lawn_mower.global_params
            if global_params:
                main_direction_config = global_params.get('main_direction_angle_config', {})
                current_angle = main_direction_config.get('current_angle')
                if current_angle is not None:
                    attrs['current_robot_angle'] = current_angle

        return attrs


class MainDirectionAutoRotateIntervalNumber(TerraMowNumberBase):
    """Auto-rotate main-direction interval setting controller - uses dp_155 data."""

    _attr_native_unit_of_measurement = "°"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "main_direction_auto_rotate_interval"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 180
    _attr_native_step = 1
    _listens_for_mode_change = True
    _required_mode = 'MAIN_DIRECTION_MODE_AUTO_ROTATE'

    _unique_id_suffix = "main_direction_auto_rotate_interval"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.available:
            return None

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        main_direction_config = global_params.get('main_direction_angle_config', {})
        auto_config = main_direction_config.get('auto_rotate_mode_config', {})
        interval = auto_config.get('angle_interval')
        return float(interval) if interval is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the auto rotate interval."""
        if not self.available:
            _LOGGER.error("Auto rotate interval control not available in current mode")
            return

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        interval_value = int(value)

        # Send the set command to dp_155
        command = {
            'main_direction_angle_config': {
                'mode': 'MAIN_DIRECTION_MODE_AUTO_ROTATE',
                'auto_rotate_mode_config': {
                    'angle_interval': interval_value
                }
            }
        }

        _LOGGER.info("Setting auto rotate interval to %d degrees", interval_value)
        self.basic_data.lawn_mower.publish_data_point(155, command)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            'valid_range': '1-180 degrees',
            'description': 'Angle interval for auto rotate mode'
        }

        # Add the current angle information
        if hasattr(self.basic_data, 'lawn_mower') and self.basic_data.lawn_mower:
            global_params = self.basic_data.lawn_mower.global_params
            if global_params:
                main_direction_config = global_params.get('main_direction_angle_config', {})
                current_angle = main_direction_config.get('current_angle')
                if current_angle is not None:
                    attrs['current_robot_angle'] = current_angle

        return attrs


class MultipleDirectionAngle1Number(TerraMowNumberBase):
    """First multiple-main-direction angle setting controller - uses dp_155 data."""

    _attr_native_unit_of_measurement = "°"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "multiple_direction_angle1"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 359
    _attr_native_step = 1
    _listens_for_mode_change = True
    _required_mode = 'MAIN_DIRECTION_MODE_MULTIPLE'

    _unique_id_suffix = "multiple_direction_angle1"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.available:
            return None

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        main_direction_config = global_params.get('main_direction_angle_config', {})
        multiple_config = main_direction_config.get('multiple_mode_config', {})
        angles = multiple_config.get('angles', [0, 90])

        # Return the first angle, or 0 if the array is empty
        return float(angles[0]) if len(angles) > 0 else 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the first multiple direction angle."""
        if not self.available:
            _LOGGER.error("Multiple direction angle1 control not available in current mode")
            return

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        # Ensure the angle value stays within the 0-359 range
        angle1_value = int(value) % 360

        # Get the current second angle
        global_params = self.basic_data.lawn_mower.global_params or {}
        main_direction_config = global_params.get('main_direction_angle_config', {})
        multiple_config = main_direction_config.get('multiple_mode_config', {})
        current_angles = multiple_config.get('angles', [0, 90])

        # Get the second angle, or use the default of 90 if it does not exist
        angle2_value = current_angles[1] if len(current_angles) > 1 else 90

        # Check whether the two angles are the same
        if angle1_value == angle2_value:
            _LOGGER.warning("Angle1 (%d°) is same as Angle2 (%d°), this may not be effective",
                          angle1_value, angle2_value)

        # Send the set command to dp_155
        command = {
            'main_direction_angle_config': {
                'mode': 'MAIN_DIRECTION_MODE_MULTIPLE',
                'multiple_mode_config': {
                    'angles': [angle1_value, angle2_value]
                }
            }
        }

        _LOGGER.info("Setting multiple direction angles to [%d°, %d°]", angle1_value, angle2_value)
        self.basic_data.lawn_mower.publish_data_point(155, command)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            'valid_range': '0-359 degrees',
            'description': 'First angle for multiple main direction mode'
        }

        # Add current angle information and second-angle information
        if hasattr(self.basic_data, 'lawn_mower') and self.basic_data.lawn_mower:
            global_params = self.basic_data.lawn_mower.global_params
            if global_params:
                main_direction_config = global_params.get('main_direction_angle_config', {})
                current_angle = main_direction_config.get('current_angle')
                if current_angle is not None:
                    attrs['current_robot_angle'] = current_angle

                # Show the paired second angle
                multiple_config = main_direction_config.get('multiple_mode_config', {})
                angles = multiple_config.get('angles', [])
                if len(angles) > 1:
                    attrs['paired_angle2'] = angles[1]
                    attrs['angle_difference'] = abs(angles[1] - angles[0])

        return attrs


class MultipleDirectionAngle2Number(TerraMowNumberBase):
    """Second multiple-main-direction angle setting controller - uses dp_155 data."""

    _attr_native_unit_of_measurement = "°"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "multiple_direction_angle2"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 359
    _attr_native_step = 1
    _listens_for_mode_change = True
    _required_mode = 'MAIN_DIRECTION_MODE_MULTIPLE'

    _unique_id_suffix = "multiple_direction_angle2"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.available:
            return None

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            return None

        global_params = self.basic_data.lawn_mower.global_params
        if not global_params:
            return None

        main_direction_config = global_params.get('main_direction_angle_config', {})
        multiple_config = main_direction_config.get('multiple_mode_config', {})
        angles = multiple_config.get('angles', [0, 90])

        # Return the second angle, or 90 if the array is too short
        return float(angles[1]) if len(angles) > 1 else 90.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the second multiple direction angle."""
        if not self.available:
            _LOGGER.error("Multiple direction angle2 control not available in current mode")
            return

        if not hasattr(self.basic_data, 'lawn_mower') or not self.basic_data.lawn_mower:
            _LOGGER.error("Lawn mower not available")
            return

        # Ensure the angle value stays within the 0-359 range
        angle2_value = int(value) % 360

        # Get the current first angle
        global_params = self.basic_data.lawn_mower.global_params or {}
        main_direction_config = global_params.get('main_direction_angle_config', {})
        multiple_config = main_direction_config.get('multiple_mode_config', {})
        current_angles = multiple_config.get('angles', [0, 90])

        # Get the first angle, or use the default of 0 if it does not exist
        angle1_value = current_angles[0] if len(current_angles) > 0 else 0

        # Check whether the two angles are the same
        if angle1_value == angle2_value:
            _LOGGER.warning("Angle2 (%d°) is same as Angle1 (%d°), this may not be effective",
                          angle2_value, angle1_value)

        # Send the set command to dp_155
        command = {
            'main_direction_angle_config': {
                'mode': 'MAIN_DIRECTION_MODE_MULTIPLE',
                'multiple_mode_config': {
                    'angles': [angle1_value, angle2_value]
                }
            }
        }

        _LOGGER.info("Setting multiple direction angles to [%d°, %d°]", angle1_value, angle2_value)
        self.basic_data.lawn_mower.publish_data_point(155, command)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            'valid_range': '0-359 degrees',
            'description': 'Second angle for multiple main direction mode'
        }

        # Add current angle information and first-angle information
        if hasattr(self.basic_data, 'lawn_mower') and self.basic_data.lawn_mower:
            global_params = self.basic_data.lawn_mower.global_params
            if global_params:
                main_direction_config = global_params.get('main_direction_angle_config', {})
                current_angle = main_direction_config.get('current_angle')
                if current_angle is not None:
                    attrs['current_robot_angle'] = current_angle

                # Show the paired first angle
                multiple_config = main_direction_config.get('multiple_mode_config', {})
                angles = multiple_config.get('angles', [])
                if len(angles) > 0:
                    attrs['paired_angle1'] = angles[0]
                    if len(angles) > 1:
                        attrs['angle_difference'] = abs(angles[1] - angles[0])

        return attrs
