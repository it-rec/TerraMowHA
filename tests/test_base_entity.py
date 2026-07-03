"""Tests for the shared TerraMowEntity base class."""

from unittest.mock import MagicMock

from custom_components.terramow.entity import TerraMowEntity


def _basic_data(host: str = "192.0.2.10", model: str | None = "TerraMow S1200"):
    basic_data = MagicMock()
    basic_data.host = host
    if model is None:
        basic_data.lawn_mower = None
    else:
        basic_data.lawn_mower.device_model = model
    return basic_data


def test_init_sets_shared_attributes() -> None:
    basic_data = _basic_data()
    hass = object()
    entity = TerraMowEntity(basic_data, hass)
    assert entity.basic_data is basic_data
    assert entity.host == "192.0.2.10"
    assert entity.hass is hass


def test_init_without_hass_keeps_entity_default() -> None:
    entity = TerraMowEntity(_basic_data())
    assert entity.hass is None


def test_unique_id_uses_suffix() -> None:
    class Suffixed(TerraMowEntity):
        _unique_id_suffix = "battery"

    entity = Suffixed(_basic_data())
    assert entity.unique_id == "lawn_mower.terramow@192.0.2.10.battery"


def test_unique_id_without_suffix_is_the_device_id() -> None:
    """The lawn mower entity itself keeps the historical suffix-less id."""
    entity = TerraMowEntity(_basic_data())
    assert entity.unique_id == "lawn_mower.terramow@192.0.2.10"


def test_device_info_is_shared_and_uses_device_model() -> None:
    entity = TerraMowEntity(_basic_data(model="TerraMow S800"))
    info = entity.device_info
    assert info["identifiers"] == {("TerraMowLawnMower", "192.0.2.10")}
    assert info["name"] == "TerraMow"
    assert info["manufacturer"] == "TerraMow"
    assert info["model"] == "TerraMow S800"


def test_device_info_before_lawn_mower_exists() -> None:
    entity = TerraMowEntity(_basic_data(model=None))
    assert entity.device_info["model"] is None


def test_available_tracks_lawn_mower_presence() -> None:
    basic_data = _basic_data()
    entity = TerraMowEntity(basic_data)
    assert entity.available is True

    basic_data.lawn_mower = None
    assert entity.available is False


def test_all_platform_entities_inherit_the_base() -> None:
    """Every entity class in the integration must use the shared base."""
    import importlib
    import inspect
    import sys

    from homeassistant.helpers.entity import Entity

    # HA's camera component imports turbojpeg, which the test harness
    # does not ship; a stub is enough for an import-and-inspect test.
    sys.modules.setdefault("turbojpeg", MagicMock())

    platforms = [
        "lawn_mower",
        "sensor",
        "binary_sensor",
        "select",
        "number",
        "switch",
        "button",
        "update",
        "map_sensor",
        "camera",
    ]
    missing = []
    for platform in platforms:
        module = importlib.import_module(f"custom_components.terramow.{platform}")
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module.__name__:
                continue
            if issubclass(cls, Entity) and not issubclass(cls, TerraMowEntity):
                missing.append(f"{platform}.{name}")
    assert not missing, f"Entities missing TerraMowEntity base: {missing}"
