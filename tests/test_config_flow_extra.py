"""Additional config flow coverage: validate_input, zeroconf, options."""

from types import SimpleNamespace
from unittest.mock import patch

import aiomqtt
import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow.config_flow import (
    CannotConnect,
    InvalidAuth,
    validate_input,
)
from custom_components.terramow.const import (
    CONF_ASSUME_JOB_COMPLETE,
    CONF_GPS_HEADING,
    CONF_MAP_RESOLUTION,
    CONF_MAP_SHOW_COVERAGE,
    CONF_MAP_THEME,
    DEFAULT_ASSUME_JOB_COMPLETE,
    DEFAULT_GPS_HEADING,
    DEFAULT_MAP_SHOW_COVERAGE,
    DEFAULT_MAP_THEME,
    DOMAIN,
    MAP_RESOLUTION_OPTIONS,
)

USER_INPUT = {CONF_HOST: "192.0.2.10", CONF_PASSWORD: "secret"}


class _FakeAiomqttClient:
    """Minimal aiomqtt stand-in whose connect delivers a scripted outcome."""

    error: Exception | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        if type(self).error is not None:
            raise type(self).error
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


def _patch_client(error: Exception | None = None):
    client_cls = type("ScriptedClient", (_FakeAiomqttClient,), {"error": error})
    return patch(
        "custom_components.terramow.config_flow.aiomqtt.Client",
        side_effect=client_cls,
    )


# ---------------------------------------------------------------------------
# validate_input
# ---------------------------------------------------------------------------


async def test_validate_input_success(hass: HomeAssistant) -> None:
    with _patch_client():
        info = await validate_input(hass, USER_INPUT)
    assert info["title"] == "TerraMow (192.0.2.10)"


@pytest.mark.parametrize(
    "error",
    [
        # MQTT 3.1.1 CONNACK: 4 = bad username/password, 5 = not authorized
        aiomqtt.MqttCodeError(4),
        aiomqtt.MqttCodeError(5),
        # paho 2.x may normalize those to MQTT 5 ReasonCode objects (134/135)
        aiomqtt.MqttCodeError(SimpleNamespace(value=134)),
        aiomqtt.MqttCodeError(SimpleNamespace(value=135)),
    ],
)
async def test_validate_input_auth_failure(
    hass: HomeAssistant, error: Exception
) -> None:
    with _patch_client(error=error), pytest.raises(InvalidAuth):
        await validate_input(hass, USER_INPUT)


async def test_validate_input_cannot_connect_on_exception(hass: HomeAssistant) -> None:
    with (
        _patch_client(error=OSError("no route to host")),
        pytest.raises(CannotConnect),
    ):
        await validate_input(hass, USER_INPUT)


async def test_validate_input_cannot_connect_on_refusal(hass: HomeAssistant) -> None:
    # a CONNACK refusal other than bad credentials -> CannotConnect
    with (
        _patch_client(error=aiomqtt.MqttCodeError(3)),
        pytest.raises(CannotConnect),
    ):
        await validate_input(hass, USER_INPUT)


async def test_validate_input_cannot_connect_on_timeout(hass: HomeAssistant) -> None:
    with _patch_client(error=TimeoutError()), pytest.raises(CannotConnect):
        await validate_input(hass, USER_INPUT)


# ---------------------------------------------------------------------------
# zeroconf discovery
# ---------------------------------------------------------------------------


class _Discovery:
    def __init__(self, host):
        self.host = host


async def test_zeroconf_discovery_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_Discovery("192.0.2.55"),
    )
    # discovery moves straight to the password step
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user_pass"

    with patch(
        "custom_components.terramow.config_flow.validate_input",
        return_value={"title": "TerraMow (192.0.2.55)"},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "secret"}
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "192.0.2.55", CONF_PASSWORD: "secret"}


async def test_zeroconf_without_host_aborts(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_Discovery(None),
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_zeroconf_password_step_reports_invalid_auth(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_Discovery("192.0.2.55"),
    )
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "wrong"}
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


# ---------------------------------------------------------------------------
# options flow
# ---------------------------------------------------------------------------


async def test_options_flow_sets_map_resolution(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    resolution = MAP_RESOLUTION_OPTIONS[-1]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MAP_RESOLUTION: resolution}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    # unset fields fall back to their defaults
    assert result["data"] == {
        CONF_MAP_RESOLUTION: resolution,
        CONF_MAP_THEME: DEFAULT_MAP_THEME,
        CONF_MAP_SHOW_COVERAGE: DEFAULT_MAP_SHOW_COVERAGE,
        CONF_ASSUME_JOB_COMPLETE: DEFAULT_ASSUME_JOB_COMPLETE,
        CONF_GPS_HEADING: DEFAULT_GPS_HEADING,
    }


async def test_options_flow_sets_theme_and_coverage(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_MAP_RESOLUTION: MAP_RESOLUTION_OPTIONS[0],
            CONF_MAP_THEME: "dark",
            CONF_MAP_SHOW_COVERAGE: True,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAP_THEME] == "dark"
    assert result["data"][CONF_MAP_SHOW_COVERAGE] is True
