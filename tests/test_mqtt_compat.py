"""Tests for the paho-mqtt 1.x/2.x compatibility helper."""

import logging
from unittest.mock import MagicMock, patch

import paho.mqtt.client as mqtt_client
import pytest

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.mqtt_compat import create_mqtt_client


def test_create_mqtt_client_returns_client() -> None:
    client = create_mqtt_client()
    assert isinstance(client, mqtt_client.Client)


def test_create_mqtt_client_requests_version1_on_paho_2x() -> None:
    if not hasattr(mqtt_client, "CallbackAPIVersion"):
        pytest.skip("paho-mqtt 1.x installed")
    with patch.object(mqtt_client, "Client") as mock_client:
        create_mqtt_client()
    mock_client.assert_called_once_with(mqtt_client.CallbackAPIVersion.VERSION1)


def test_create_mqtt_client_falls_back_on_paho_1x(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate paho-mqtt 1.x, where CallbackAPIVersion does not exist.
    monkeypatch.delattr(mqtt_client, "CallbackAPIVersion", raising=False)
    with patch.object(mqtt_client, "Client") as mock_client:
        create_mqtt_client()
    mock_client.assert_called_once_with()


def test_hub_start_does_not_log_password(caplog: pytest.LogCaptureFixture) -> None:
    basic_data = TerraMowBasicData(host="192.0.2.10", password="super-secret")
    hub = TerraMowHub(basic_data, MagicMock())
    with (
        patch("custom_components.terramow.hub.create_mqtt_client") as mock_create,
        patch("custom_components.terramow.hub.threading.Thread"),
    ):
        caplog.set_level(logging.DEBUG)
        hub.start()
    assert "super-secret" not in caplog.text
    mock_create.assert_called_once_with()
