"""Tests for the shared entity helpers (safe state writes, device lookup)."""

from unittest.mock import MagicMock

from custom_components.terramow.entity_utils import (
    async_get_entry_device,
    safe_schedule_update_ha_state,
    safe_write_ha_state,
)


def _entity(hass, entity_id):
    entity = MagicMock()
    entity.hass = hass
    entity.entity_id = entity_id
    return entity


def test_write_skipped_before_entity_is_added() -> None:
    entity = _entity(hass=None, entity_id=None)
    safe_write_ha_state(entity)
    entity.async_write_ha_state.assert_not_called()

    entity = _entity(hass=object(), entity_id=None)
    safe_write_ha_state(entity)
    entity.async_write_ha_state.assert_not_called()


def test_write_happens_when_entity_is_registered() -> None:
    entity = _entity(hass=object(), entity_id="sensor.terramow_pose")
    safe_write_ha_state(entity)
    entity.async_write_ha_state.assert_called_once()


def test_late_runtime_error_is_swallowed() -> None:
    entity = _entity(hass=object(), entity_id="sensor.terramow_pose")
    entity.async_write_ha_state.side_effect = RuntimeError("Attribute hass is None")
    safe_write_ha_state(entity)  # must not raise


def test_schedule_update_guards_the_same_way() -> None:
    entity = _entity(hass=None, entity_id=None)
    safe_schedule_update_ha_state(entity)
    entity.schedule_update_ha_state.assert_not_called()

    entity = _entity(hass=object(), entity_id="lawn_mower.terramow")
    safe_schedule_update_ha_state(entity)
    entity.schedule_update_ha_state.assert_called_once()

    entity.schedule_update_ha_state.side_effect = RuntimeError("not added")
    safe_schedule_update_ha_state(entity)  # must not raise


def test_push_update_mixin_registers_callbacks() -> None:
    from custom_components.terramow.entity_utils import PushUpdateMixin

    class Base:
        def __init__(self) -> None:
            self.on_remove_callbacks = []

        async def async_added_to_hass(self) -> None:
            return None

        def async_on_remove(self, func) -> None:
            self.on_remove_callbacks.append(func)

    class Probe(PushUpdateMixin, Base):
        _push_dp_ids = (108, 155)
        _push_map_info = True

    probe = Probe()
    lawn_mower = MagicMock()
    probe.basic_data = MagicMock()
    probe.basic_data.lawn_mower = lawn_mower

    import asyncio

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        probe.async_added_to_hass()
    )

    registered = [call.args[0] for call in lawn_mower.register_callback.call_args_list]
    assert registered == [108, 155]
    lawn_mower.register_map_callback.assert_called_once()
    # every registration handed its unsubscribe to async_on_remove
    assert probe.on_remove_callbacks == [
        lawn_mower.register_callback.return_value,
        lawn_mower.register_callback.return_value,
        lawn_mower.register_map_callback.return_value,
    ]


def test_device_lookup_is_scoped_to_the_config_entry() -> None:
    """Newer cores: use the entry-scoped lookup, never async_get_device (#348)."""
    registry = MagicMock()
    device = MagicMock()
    registry.async_get_device_by_identifier.return_value = device

    found = async_get_entry_device(registry, ("terramow", "SN1"), "entry-1")

    assert found is device
    registry.async_get_device_by_identifier.assert_called_once_with(
        ("terramow", "SN1"), "entry-1"
    )
    registry.async_get_device.assert_not_called()


def test_device_lookup_without_entry_id_finds_nothing() -> None:
    registry = MagicMock()

    assert async_get_entry_device(registry, ("terramow", "SN1"), None) is None
    registry.async_get_device_by_identifier.assert_not_called()
    registry.async_get_device.assert_not_called()


def test_device_lookup_falls_back_on_older_cores() -> None:
    """Cores without async_get_device_by_identifier keep the old lookup."""
    registry = MagicMock(spec=["async_get_device"])
    device = MagicMock()
    registry.async_get_device.return_value = device

    assert async_get_entry_device(registry, ("terramow", "SN1"), "entry-1") is device
    registry.async_get_device.assert_called_once_with({("terramow", "SN1")})
