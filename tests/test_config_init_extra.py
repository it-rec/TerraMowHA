"""Final coverage for __init__ and config_flow error / edge paths."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import (
    TerraMowBasicData,
    _async_options_updated,
    async_setup_entry,
)
from custom_components.terramow.config_flow import CannotConnect, InvalidAuth
from custom_components.terramow.const import DOMAIN, CompatibilityStatus

USER_INPUT = {CONF_HOST: "192.0.2.10", CONF_PASSWORD: "secret"}


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10")
    entry.add_to_hass(hass)
    return entry


# ---------------------------------------------------------------------------
# TerraMowBasicData.get_compatibility_message across every status/reason
# ---------------------------------------------------------------------------


def test_compatibility_messages_cover_all_reasons() -> None:
    bd = TerraMowBasicData(host="h", password="p")

    bd.compatibility_status = CompatibilityStatus.COMPATIBLE
    bd.compatibility_reason = "ha_version_limited:12"
    assert "live map" in bd.get_compatibility_message()
    bd.compatibility_reason = ""
    assert "all functions working" in bd.get_compatibility_message()

    bd.compatibility_status = CompatibilityStatus.UPGRADE_REQUIRED
    bd.compatibility_reason = "overall_version_low:5"
    assert "overall version too low" in bd.get_compatibility_message()
    bd.compatibility_reason = "ha_version_low:2"
    assert "HA module version too low" in bd.get_compatibility_message()
    bd.compatibility_reason = "something_else"
    assert "version too low" in bd.get_compatibility_message()

    bd.compatibility_status = CompatibilityStatus.DOWNGRADE_RECOMMENDED
    bd.compatibility_reason = "ha_version_high:40"
    assert "recommend upgrading plugin" in bd.get_compatibility_message()
    bd.compatibility_reason = ""
    assert "higher than plugin" in bd.get_compatibility_message()

    bd.compatibility_status = CompatibilityStatus.INCOMPATIBLE
    bd.compatibility_reason = ""
    assert "incompatible" in bd.get_compatibility_message()


# ---------------------------------------------------------------------------
# async_setup_entry success + options-updated + migration conflict
# ---------------------------------------------------------------------------


async def test_setup_entry_success_starts_hub_and_forwards(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    with (
        patch("custom_components.terramow.validate_input", return_value={"title": "T"}),
        patch("custom_components.terramow.TerraMowHub") as hub_cls,
        patch(
            "custom_components.terramow.async_setup_map_card", AsyncMock()
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", AsyncMock()
        ) as forward,
    ):
        hub_cls.return_value.async_restore_session_paths = AsyncMock()
        result = await async_setup_entry(hass, entry)

    assert result is True
    hub_cls.return_value.start.assert_called_once()
    forward.assert_awaited_once()
    assert entry.runtime_data is not None


async def test_options_updated_reloads_entry(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    with patch.object(
        hass.config_entries, "async_reload", AsyncMock()
    ) as reload:
        await _async_options_updated(hass, entry)
    reload.assert_awaited_once_with(entry.entry_id)


async def test_setup_entry_migration_conflict_keeps_old_device(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    device_registry = dr.async_get(hass)
    # both the old (misspelled) and the new identifier already exist
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("TerraMowLanwMower", "192.0.2.10")},
    )
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("terramow", "192.0.2.10")},
    )
    from homeassistant.exceptions import ConfigEntryNotReady

    with (
        patch("custom_components.terramow.validate_input", side_effect=CannotConnect),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)
    # the migration must not have removed the pre-existing old device
    assert device_registry.async_get_device({("TerraMowLanwMower", "192.0.2.10")})


# ---------------------------------------------------------------------------
# config_flow: user step unexpected error, zeroconf dict, user_pass errors
# ---------------------------------------------------------------------------


async def test_user_step_unexpected_error_is_unknown(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=RuntimeError("boom"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["errors"] == {"base": "unknown"}


async def test_zeroconf_accepts_dict_discovery(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data={"host": "192.0.2.77"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user_pass"


async def test_user_pass_reports_cannot_connect(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data={"host": "192.0.2.77"}
    )
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "x"}
        )
    assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# config_flow: reauth + reconfigure
# ---------------------------------------------------------------------------


async def test_reauth_flow_updates_password(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with (
        patch(
            "custom_components.terramow.config_flow.validate_input",
            return_value={"title": "T"},
        ),
        patch.object(hass.config_entries, "async_reload", AsyncMock()),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "newpass"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "newpass"


async def test_reauth_flow_reports_invalid_auth(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await entry.start_reauth_flow(hass)
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "bad"}
        )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_flow_reports_cannot_connect(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.99", CONF_PASSWORD: "p"}
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_pass_reports_unknown(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data={"host": "192.0.2.77"}
    )
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=RuntimeError("boom"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "x"}
        )
    assert result["errors"] == {"base": "unknown"}


async def test_reauth_reports_unknown(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await entry.start_reauth_flow(hass)
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=RuntimeError("boom"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "x"}
        )
    assert result["errors"] == {"base": "unknown"}


async def test_reconfigure_reports_invalid_auth_and_unknown(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.99", CONF_PASSWORD: "p"}
        )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await entry.start_reconfigure_flow(hass)
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=RuntimeError("boom"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.99", CONF_PASSWORD: "p"}
        )
    assert result["errors"] == {"base": "unknown"}


async def test_reconfigure_flow_updates_host(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    with (
        patch(
            "custom_components.terramow.config_flow.validate_input",
            return_value={"title": "T"},
        ),
        patch.object(hass.config_entries, "async_reload", AsyncMock()),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.88", CONF_PASSWORD: "p"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.0.2.88"


# ---------------------------------------------------------------------------
# exception translations (Gold quality scale)
# ---------------------------------------------------------------------------


def test_strings_json_defines_exception_messages() -> None:
    import json
    from pathlib import Path

    strings = json.loads(
        Path("custom_components/terramow/strings.json").read_text(encoding="utf-8")
    )
    exceptions = strings["exceptions"]
    assert "entity_not_registered" in exceptions
    assert "lawn_mower_not_ready" in exceptions
    assert "{entity_id}" in exceptions["entity_not_registered"]["message"]


async def test_service_error_carries_translation_key(hass: HomeAssistant) -> None:
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.terramow import (
        SERVICE_START_SELECT_REGION,
        _async_register_services,
    )

    _async_register_services(hass)
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_SELECT_REGION,
            {"entity_id": "lawn_mower.does_not_exist", "region_ids": [1]},
            blocking=True,
        )
    assert err.value.translation_key == "entity_not_registered"
    assert err.value.translation_domain == DOMAIN
