"""Actions are registered by the integration, not by a config entry.

Home Assistant validates automations against the registered actions. When the
actions only existed while a mower entry was loaded, a mower that was offline
at startup (entry in setup retry) made every automation using
``terramow.plan_due_zones`` & co. raise an "unknown action" repair. These
tests pin the actions to ``async_setup`` so they exist regardless of entry
state, while calls still fail cleanly until the mower is ready.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import (
    SERVICE_ADD_SCHEDULE,
    SERVICE_DELETE_SCHEDULE,
    SERVICE_PLAN_DUE_ZONES,
    SERVICE_START_DUE_ZONES,
    SERVICE_START_SELECT_REGION,
)
from custom_components.terramow.config_flow import CannotConnect
from custom_components.terramow.const import DOMAIN
from custom_components.terramow.intent import INTENT_MOW_ZONE

ALL_SERVICES = (
    SERVICE_START_SELECT_REGION,
    SERVICE_ADD_SCHEDULE,
    SERVICE_DELETE_SCHEDULE,
    SERVICE_PLAN_DUE_ZONES,
    SERVICE_START_DUE_ZONES,
)


def _intent_registered(hass: HomeAssistant) -> bool:
    return any(
        handler.intent_type == INTENT_MOW_ZONE for handler in intent.async_get(hass)
    )


async def test_actions_registered_without_any_entry(hass: HomeAssistant) -> None:
    """Setting up the integration alone registers every action."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    for service in ALL_SERVICES:
        assert hass.services.has_service(DOMAIN, service), service
    # The Assist intent needs a loaded mower and stays with the entries.
    assert not _intent_registered(hass)


async def test_actions_exist_while_entry_retries_setup(
    hass: HomeAssistant,
) -> None:
    """An unreachable mower leaves the actions in place and callable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.10", CONF_PASSWORD: "secret"},
        unique_id="192.0.2.10",
    )
    entry.add_to_hass(hass)
    # The mower entity is known from an earlier run, as after a restart.
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create("lawn_mower", DOMAIN, "unique", config_entry=entry)
    entity_id = ent_reg.async_get_entity_id("lawn_mower", DOMAIN, "unique")

    with patch(
        "custom_components.terramow.validate_input", side_effect=CannotConnect
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    for service in ALL_SERVICES:
        assert hass.services.has_service(DOMAIN, service), service
    assert not _intent_registered(hass)

    # Calling an action before the mower is ready fails with a clear error
    # instead of the action being unknown.
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PLAN_DUE_ZONES,
            {"entity_id": entity_id},
            blocking=True,
            return_response=True,
        )
    assert err.value.translation_key == "lawn_mower_not_ready"
