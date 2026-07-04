"""Coverage for the integration setup / unload and the region service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import (
    SERVICE_START_SELECT_REGION,
    TerraMowBasicData,
    _async_register_services,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.terramow.config_flow import CannotConnect, InvalidAuth
from custom_components.terramow.const import DOMAIN

USER_INPUT = {CONF_HOST: "192.0.2.10", CONF_PASSWORD: "secret"}


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10")
    entry.add_to_hass(hass)
    return entry


# ---------------------------------------------------------------------------
# async_setup_entry failure paths
# ---------------------------------------------------------------------------


async def test_setup_entry_invalid_auth_raises_auth_failed(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    with (
        patch("custom_components.terramow.validate_input", side_effect=InvalidAuth),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await async_setup_entry(hass, entry)


async def test_setup_entry_cannot_connect_raises_not_ready(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    with (
        patch("custom_components.terramow.validate_input", side_effect=CannotConnect),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)


async def test_setup_entry_migrates_device_identifier(hass: HomeAssistant) -> None:
    """The old misspelled 'TerraMowLanwMower' identifier is migrated."""
    entry = _entry(hass)
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("TerraMowLanwMower", "192.0.2.10")},
    )

    # Migration runs before the credential check; use a connect failure so the
    # hub is never started.
    with (
        patch("custom_components.terramow.validate_input", side_effect=CannotConnect),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)

    assert (
        device_registry.async_get_device({("TerraMowLawnMower", "192.0.2.10")})
        is not None
    )
    assert (
        device_registry.async_get_device({("TerraMowLanwMower", "192.0.2.10")}) is None
    )


# ---------------------------------------------------------------------------
# async_unload_entry
# ---------------------------------------------------------------------------


async def test_unload_entry_stops_hub_and_clears_data(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    hub = MagicMock()
    hub.async_stop = AsyncMock()
    basic_data = TerraMowBasicData(
        host="192.0.2.10", password="secret", entry_id=entry.entry_id
    )
    basic_data.lawn_mower = hub
    entry.runtime_data = basic_data

    with patch("custom_components.terramow.async_clear_compatibility_issue") as clear:
        result = await async_unload_entry(hass, entry)

    assert result is True
    hub.async_stop.assert_awaited_once()
    clear.assert_called_once()
    # It was the only entry, so the shared service is removed.
    assert not hass.services.has_service(DOMAIN, SERVICE_START_SELECT_REGION)


# ---------------------------------------------------------------------------
# start_select_region service
# ---------------------------------------------------------------------------


async def test_start_select_region_service_dispatches_to_hub(
    hass: HomeAssistant,
) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = _entry(hass)
    hub = MagicMock()
    basic_data = TerraMowBasicData(
        host="192.0.2.10", password="secret", entry_id=entry.entry_id
    )
    basic_data.lawn_mower = hub
    entry.runtime_data = basic_data

    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "lawn_mower", DOMAIN, "unique", config_entry=entry
    )
    entity_id = ent_reg.async_get_entity_id("lawn_mower", DOMAIN, "unique")

    _async_register_services(hass)
    assert hass.services.has_service(DOMAIN, SERVICE_START_SELECT_REGION)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SELECT_REGION,
        {"entity_id": entity_id, "region_ids": [1, 2]},
        blocking=True,
    )
    hub.start_select_region_clean.assert_called_once_with([1, 2])


async def test_start_select_region_service_rejects_unknown_entity(
    hass: HomeAssistant,
) -> None:
    _async_register_services(hass)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_SELECT_REGION,
            {"entity_id": "lawn_mower.does_not_exist", "region_ids": [1]},
            blocking=True,
        )
