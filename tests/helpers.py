"""Small helpers shared by several test modules."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr


def find_device(
    registry: dr.DeviceRegistry, identifier: tuple[str, str]
) -> dr.DeviceEntry | None:
    """Return the first device carrying ``identifier``, or None.

    ``DeviceRegistry.async_get_device`` is deprecated on current Home
    Assistant (identifiers are no longer unique across config entries) and
    raises in tests, while its replacements do not exist on the oldest
    release the CI matrix covers. Scanning the registry works on both.
    """
    return next(
        (
            device
            for device in registry.devices.values()
            if identifier in device.identifiers
        ),
        None,
    )
