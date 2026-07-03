"""Tests for the TerraMow config flow."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow.config_flow import CannotConnect, InvalidAuth
from custom_components.terramow.const import DOMAIN

USER_INPUT = {CONF_HOST: "192.0.2.10", CONF_PASSWORD: "secret"}


def _patch_validate(**kwargs):
    return patch(
        "custom_components.terramow.config_flow.validate_input", **kwargs
    )


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}

    with _patch_validate(return_value={"title": "TerraMow (192.0.2.10)"}):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "TerraMow (192.0.2.10)"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == "192.0.2.10"


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (CannotConnect, "cannot_connect"),
        (InvalidAuth, "invalid_auth"),
        (ValueError, "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, side_effect: type[Exception], error: str
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with _patch_validate(side_effect=side_effect):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_user_flow_aborts_on_duplicate_host(hass: HomeAssistant) -> None:
    MockConfigEntry(
        domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10"
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with _patch_validate(return_value={"title": "TerraMow (192.0.2.10)"}):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_flow_updates_host_and_unique_id(
    hass: HomeAssistant,
) -> None:
    """Regression test for the reconfigure flow (upstream PR #81 port)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=USER_INPUT,
        unique_id="192.0.2.10",
        title="TerraMow (192.0.2.10)",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new_input = {CONF_HOST: "192.0.2.20", CONF_PASSWORD: "secret"}
    with (
        _patch_validate(return_value={"title": "TerraMow (192.0.2.20)"}),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], new_input
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.0.2.20"
    assert entry.unique_id == "192.0.2.20"


async def test_reconfigure_flow_aborts_when_host_taken(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10"
    )
    entry.add_to_hass(hass)
    other = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.20", CONF_PASSWORD: "x"},
        unique_id="192.0.2.20",
    )
    other.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    with _patch_validate(return_value={"title": "TerraMow (192.0.2.20)"}):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.20", CONF_PASSWORD: "secret"}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "192.0.2.10"


async def test_reauth_flow_updates_password(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10"
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with (
        _patch_validate(return_value={"title": "TerraMow (192.0.2.10)"}),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new-secret"}
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"
