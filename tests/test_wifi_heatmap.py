"""Self-sampled Wi-Fi heatmap (issue #200, approach B).

The firmware exposes a ``wifi_signal_map_index`` in map_data but never serves
the raster locally (probe 2026-07-23: no MQTT traffic even with the vendor
app's Wi-Fi map view open). The hub therefore builds its own heatmap: each
realtime pose is paired with the latest dp_109 mower-side signal % and folded
into a coarse grid via an exponential moving average. Persisted per host,
cleared on map change.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import (
    WIFI_CELL_MM,
    WIFI_EMA_ALPHA,
    WIFI_MAP_SAVE_DELAY,
    TerraMowHub,
)


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.150", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def _pose(x: Any = 1000, y: Any = 2000) -> dict[str, Any]:
    return {"x": x, "y": y, "yaw": 0.5}


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------


def test_no_sample_without_signal() -> None:
    hub = _hub()
    hub._sample_wifi_cell(_pose())
    assert hub.wifi_map_cells == {}
    assert hub.wifi_map_rev == 0


def test_no_sample_for_malformed_pose() -> None:
    hub = _hub()
    hub._wifi_signal = 70
    for pose in ("junk", {}, {"x": 1}, _pose(x=None), _pose(x="a"), _pose(x=True)):
        hub._sample_wifi_cell(pose)  # type: ignore[arg-type]
    assert hub.wifi_map_cells == {}


def test_first_sample_creates_cell_and_schedules_save() -> None:
    hub = _hub()
    hub._wifi_signal = 70
    hub._map_data = {"id": 4}
    hub._sample_wifi_cell(_pose(x=1000, y=2000))
    cell = (round(1000 / WIFI_CELL_MM), round(2000 / WIFI_CELL_MM))
    assert hub.wifi_map_cells == {cell: 70.0}
    assert hub.wifi_map_rev == 1
    assert hub._wifi_map_id == 4  # adopted from the current map
    hub._wifi_map_store.async_delay_save.assert_called_once_with(
        hub._wifi_map_save_data, WIFI_MAP_SAVE_DELAY
    )


def test_ema_moves_value_and_bumps_rev_on_visible_change() -> None:
    hub = _hub()
    hub._wifi_signal = 50
    hub._sample_wifi_cell(_pose())
    hub._wifi_signal = 90
    hub._sample_wifi_cell(_pose())
    cell = next(iter(hub.wifi_map_cells))
    assert hub.wifi_map_cells[cell] == 50 + WIFI_EMA_ALPHA * 40
    assert hub.wifi_map_rev == 2


def test_invisible_change_skips_rev_and_save() -> None:
    hub = _hub()
    hub._wifi_signal = 50
    hub._sample_wifi_cell(_pose())
    hub._wifi_map_store.async_delay_save.reset_mock()
    hub._wifi_signal = 51  # EMA: 50 + 0.4*1 = 50.4 — rounds to the same 50
    hub._sample_wifi_cell(_pose())
    cell = next(iter(hub.wifi_map_cells))
    assert hub.wifi_map_cells[cell] == 50 + WIFI_EMA_ALPHA * 1
    assert hub.wifi_map_rev == 1  # unchanged
    hub._wifi_map_store.async_delay_save.assert_not_called()


def test_cell_count_is_bounded(monkeypatch: Any) -> None:
    monkeypatch.setattr("custom_components.terramow.hub.MAX_WIFI_CELLS", 2)
    hub = _hub()
    hub._wifi_signal = 60
    for i in range(3):
        hub._sample_wifi_cell(_pose(x=i * 10 * WIFI_CELL_MM, y=0))
    assert len(hub.wifi_map_cells) == 2
    # the oldest-inserted cell was dropped
    assert (0, 0) not in hub.wifi_map_cells


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


def test_wifi_store_created_lazily_once() -> None:
    hub = _hub()
    store = hub._get_wifi_map_store()
    assert store is hub._get_wifi_map_store()  # cached
    assert store.created_with == (1, "terramow.wifi_map_192.0.2.150")


def test_save_data_uses_string_keys_and_rounds() -> None:
    hub = _hub()
    hub._wifi_map_id = 7
    hub._wifi_cells = {(1, -2): 55.5555, (0, 3): 80.0}
    assert hub._wifi_map_save_data() == {
        "map_id": 7,
        "cells": {"1,-2": 55.6, "0,3": 80.0},
    }


def test_restore_parses_cells_and_map_id() -> None:
    hub = _hub()
    store = hub._get_wifi_map_store()
    store.async_load = AsyncMock(
        return_value={"map_id": 3, "cells": {"1,-2": 55.6, "0,3": 80}}
    )
    asyncio.run(hub.async_restore_wifi_map())
    assert hub.wifi_map_cells == {(1, -2): 55.6, (0, 3): 80.0}
    assert hub._wifi_map_id == 3
    assert hub.wifi_map_rev == 1


def test_restore_ignores_empty_or_malformed_payloads() -> None:
    for data in (None, {}, {"cells": []}, {"cells": "junk"}, {"cells": {}}):
        hub = _hub()
        store = hub._get_wifi_map_store()
        store.async_load = AsyncMock(return_value=data)
        asyncio.run(hub.async_restore_wifi_map())
        assert hub.wifi_map_cells == {}


def test_restore_skips_malformed_entries_keeps_rest() -> None:
    hub = _hub()
    store = hub._get_wifi_map_store()
    store.async_load = AsyncMock(
        return_value={
            "map_id": 1,
            "cells": {"bad": 10, "1,x": 20, "2,2": None, "3,4": 66},
        }
    )
    asyncio.run(hub.async_restore_wifi_map())
    assert hub.wifi_map_cells == {(3, 4): 66.0}


def test_restore_with_only_malformed_entries_keeps_nothing() -> None:
    hub = _hub()
    store = hub._get_wifi_map_store()
    store.async_load = AsyncMock(return_value={"cells": {"bad": 10}})
    asyncio.run(hub.async_restore_wifi_map())
    assert hub.wifi_map_cells == {}
    assert hub.wifi_map_rev == 0


def test_restore_trims_to_cell_bound(monkeypatch: Any) -> None:
    monkeypatch.setattr("custom_components.terramow.hub.MAX_WIFI_CELLS", 2)
    hub = _hub()
    store = hub._get_wifi_map_store()
    store.async_load = AsyncMock(
        return_value={"cells": {"0,0": 10, "1,1": 20, "2,2": 30}}
    )
    asyncio.run(hub.async_restore_wifi_map())
    assert hub.wifi_map_cells == {(1, 1): 20.0, (2, 2): 30.0}


def test_restore_survives_a_corrupt_store() -> None:
    hub = _hub()
    store = hub._get_wifi_map_store()
    store.async_load = AsyncMock(side_effect=OSError("corrupt"))
    asyncio.run(hub.async_restore_wifi_map())  # must not raise
    assert hub.wifi_map_cells == {}


# ---------------------------------------------------------------------------
# map change clears the heatmap (cells are map-frame coordinates)
# ---------------------------------------------------------------------------


def test_map_change_clears_cells() -> None:
    hub = _hub()
    hub._wifi_signal = 70
    hub._map_data = {"id": 1}
    hub._sample_wifi_cell(_pose())
    hub._wifi_map_store.async_delay_save.reset_mock()
    hub._apply_map_data({"id": 2})
    assert hub.wifi_map_cells == {}
    assert hub._wifi_map_id == 2
    assert hub.wifi_map_rev == 2
    hub._wifi_map_store.async_delay_save.assert_called_once()


def test_same_map_keeps_cells() -> None:
    hub = _hub()
    hub._wifi_signal = 70
    hub._map_data = {"id": 1}
    hub._sample_wifi_cell(_pose())
    hub._apply_map_data({"id": 1})
    assert len(hub.wifi_map_cells) == 1
    assert hub._wifi_map_id == 1


def test_map_without_id_keeps_cells_and_owner() -> None:
    hub = _hub()
    hub._wifi_signal = 70
    hub._map_data = {"id": 1}
    hub._sample_wifi_cell(_pose())
    hub._apply_map_data({})
    assert len(hub.wifi_map_cells) == 1
    assert hub._wifi_map_id == 1
