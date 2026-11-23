"""Small helpers shared by several test modules."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr


def find_device(
    registry: dr.DeviceRegistry, identifier: tuple[str, str]
) -> dr.DeviceEntry | None:
    """Return the first device carrying ``identifier``, or None.

    Current Home Assistant deprecates ``DeviceRegistry.async_get_device`` and
    using ``registry.devices`` as a mapping (both raise in tests), while their
    replacements do not exist on the oldest release the CI matrix covers.
    Iterating ``registry.devices`` works on both: it yields the device entries
    on current releases and the device ids on older ones.
    """
    for item in registry.devices:
        device = item if isinstance(item, dr.DeviceEntry) else registry.async_get(item)
        if device is not None and identifier in device.identifiers:
            return device
    return None
