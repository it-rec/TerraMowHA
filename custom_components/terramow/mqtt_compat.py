"""Compatibility helpers for paho-mqtt 1.x and 2.x."""

from __future__ import annotations

import paho.mqtt.client as mqtt_client


def create_mqtt_client() -> mqtt_client.Client:
    """Create a paho MQTT ``Client`` on both paho-mqtt 1.x and 2.x.

    paho-mqtt 2.0 introduced a ``callback_api_version`` constructor argument
    without a default value, so ``Client()`` raises there. The integration
    uses the VERSION1 callback signatures, so request VERSION1 explicitly on
    2.x and fall back to the implicit v1 behaviour on 1.x.
    """
    callback_api_version = getattr(mqtt_client, "CallbackAPIVersion", None)
    if callback_api_version is not None:
        return mqtt_client.Client(callback_api_version.VERSION1)
    return mqtt_client.Client()
