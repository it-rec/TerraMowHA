"""Shared fixtures for the TerraMow test suite."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    yield


@pytest.fixture(autouse=True)
def mock_session_path_store(monkeypatch):
    """Replace the session-path Store with an in-memory mock (issue #239).

    Keeps every test hermetic (no ``.storage`` disk IO) and lets the hub's
    save/load plumbing run against MagicMock hass objects, where the real
    Store's delayed-save scheduling would choke.
    """
    stores: list[MagicMock] = []

    def factory(hass, version, key):
        store = MagicMock(name=f"SessionPathStore({key})")
        store.async_load = AsyncMock(return_value=None)
        store.created_with = (version, key)
        stores.append(store)
        return store

    monkeypatch.setattr("custom_components.terramow.hub.Store", factory)
    return stores
