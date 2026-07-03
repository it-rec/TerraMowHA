"""Tests for the safe state-write guards (upstream issue #77)."""

from unittest.mock import MagicMock

from custom_components.terramow.entity_utils import (
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
        async def async_added_to_hass(self) -> None:
            return None

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
