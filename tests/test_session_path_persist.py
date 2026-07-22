"""Persistence of the archived session mow paths across HA restarts (#239).

A restart mid-job (integration update, reboot) used to drop everything mowed
before the restart, because the archived segments lived only in the hub's
memory and the device re-serves just the current leg's path. The hub now
persists the segments via a Store and re-adopts them after a restart when the
first dp_113 frame shows the session is still open.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import (
    MAX_SESSION_PATH_SEGMENTS,
    SESSION_PATH_SAVE_DELAY,
    TerraMowHub,
)

SEGMENT = [{"x": 0, "y": 0}, {"x": 5000, "y": 0}]
SEGMENT_B = [{"x": 0, "y": 1000}, {"x": 5000, "y": 1000}]


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.140", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def _work(hub: TerraMowHub, **fields) -> None:
    asyncio.run(hub.on_current_work_data(json.dumps(fields)))


def _restore(hub: TerraMowHub, data) -> MagicMock:
    store = hub._get_session_path_store()
    store.async_load = AsyncMock(return_value=data)
    asyncio.run(hub.async_restore_session_paths())
    return store


# ---------------------------------------------------------------------------
# store plumbing
# ---------------------------------------------------------------------------


def test_store_created_lazily_once() -> None:
    hub = _hub()
    store = hub._get_session_path_store()
    assert store is hub._get_session_path_store()  # cached
    assert store.created_with == (1, "terramow.session_paths_192.0.2.140")


def test_save_data_snapshots_segments_and_map() -> None:
    hub = _hub()
    hub._map_data = {"id": 7}
    hub._session_path_segments = [SEGMENT]
    assert hub._session_path_save_data() == {
        "map_id": 7,
        "segments": [SEGMENT],
        "coverage_segments": [],
        "coverage_cycle_done": False,
    }


def test_schedule_save_is_debounced() -> None:
    hub = _hub()
    hub._schedule_session_path_save()
    store = hub._session_path_store
    store.async_delay_save.assert_called_once_with(
        hub._session_path_save_data, SESSION_PATH_SAVE_DELAY
    )


# ---------------------------------------------------------------------------
# restoring on startup
# ---------------------------------------------------------------------------


def test_restore_parks_segments_and_map_id() -> None:
    hub = _hub()
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    assert hub._restored_session_paths == [SEGMENT]
    assert hub._restored_map_id == 1
    # not adopted yet: dp_113 decides
    assert hub.session_path_segments == []


def test_restore_ignores_empty_or_malformed_payloads() -> None:
    for data in (None, {}, {"segments": []}, {"segments": "junk"}):
        hub = _hub()
        _restore(hub, data)
        assert hub._restored_session_paths is None


def test_restore_survives_a_corrupt_store() -> None:
    hub = _hub()
    store = hub._get_session_path_store()
    store.async_load = AsyncMock(side_effect=OSError("corrupt"))
    asyncio.run(hub.async_restore_session_paths())  # must not raise
    assert hub._restored_session_paths is None


# ---------------------------------------------------------------------------
# dp_113 decides: adopt vs discard
# ---------------------------------------------------------------------------


def test_open_session_adopts_restored_segments() -> None:
    hub = _hub()
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    hub._session_path_store.async_delay_save.reset_mock()
    _work(hub, clean_area=413, work_duration=1628)
    assert hub.session_path_segments == [SEGMENT]
    assert hub._restored_session_paths is None
    hub._session_path_store.async_delay_save.assert_called_once()


def test_adopted_segments_precede_newly_archived_ones() -> None:
    hub = _hub()
    _restore(hub, {"map_id": None, "segments": [SEGMENT]})
    hub._session_path_segments = [SEGMENT_B]  # archived after the restart
    _work(hub, work_duration=99)
    assert hub.session_path_segments == [SEGMENT, SEGMENT_B]


def test_zeroed_counters_discard_restored_segments() -> None:
    hub = _hub()
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    hub._session_path_store.async_delay_save.reset_mock()
    _work(hub, clean_area=0, work_duration=0)
    assert hub.session_path_segments == []
    assert hub._restored_map_id is None
    hub._session_path_store.async_delay_save.assert_called_once()


def test_completed_frame_discards_restored_segments() -> None:
    hub = _hub()
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    _work(hub, clean_area=413, is_completed=True)
    assert hub.session_path_segments == []


def test_unparseable_counters_count_as_session_over() -> None:
    hub = _hub()
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    _work(hub, clean_area="junk", work_duration=None)
    assert hub.session_path_segments == []


def test_map_mismatch_at_adoption_discards() -> None:
    hub = _hub()
    hub._map_data = {"id": 2}
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    _work(hub, clean_area=413)
    assert hub.session_path_segments == []


def test_unknown_current_map_still_adopts() -> None:
    hub = _hub()  # map not fetched yet: current id is None
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    _work(hub, clean_area=413)
    assert hub.session_path_segments == [SEGMENT]


def test_adoption_caps_the_segment_count() -> None:
    hub = _hub()
    many = [[{"x": i, "y": 0}, {"x": i, "y": 1}] for i in range(MAX_SESSION_PATH_SEGMENTS)]
    _restore(hub, {"map_id": None, "segments": many})
    hub._session_path_segments = [SEGMENT_B]
    _work(hub, work_duration=1)
    assert len(hub.session_path_segments) == MAX_SESSION_PATH_SEGMENTS
    assert hub.session_path_segments[-1] == SEGMENT_B


def test_adopt_guard_without_parked_segments() -> None:
    hub = _hub()
    hub._adopt_or_discard_restored_paths({"clean_area": 5})  # no-op
    assert hub.session_path_segments == []


def test_work_data_without_parked_segments_skips_adoption() -> None:
    hub = _hub()
    _work(hub, clean_area=413)  # must not raise nor create a store
    assert hub._session_path_store is None


# ---------------------------------------------------------------------------
# map pushes vs parked/adopted segments
# ---------------------------------------------------------------------------


def _map(map_id) -> dict:
    return {"id": map_id, "width": 100, "height": 80, "resolution": 100}


def test_map_push_with_other_id_discards_parked_and_adopted() -> None:
    hub = _hub()
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    hub._session_path_segments = [SEGMENT_B]
    hub._session_path_store.async_delay_save.reset_mock()
    hub._apply_map_data(_map(2))
    assert hub._restored_session_paths is None
    assert hub.session_path_segments == []
    assert hub._restored_map_id is None
    hub._session_path_store.async_delay_save.assert_called_once()


def test_map_push_with_other_id_always_persists_the_discard() -> None:
    # Discarding parked segments must reach the disk too, otherwise the
    # stale store would restore them again on the next boot.
    hub = _hub()
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    hub._session_path_store.async_delay_save.reset_mock()
    hub._apply_map_data(_map(2))
    assert hub._restored_session_paths is None
    hub._session_path_store.async_delay_save.assert_called_once()


def test_map_push_with_matching_id_keeps_parked_segments() -> None:
    hub = _hub()
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    hub._apply_map_data(_map(1))
    assert hub._restored_session_paths == [SEGMENT]
    assert hub._restored_map_id is None  # marker consumed
    _work(hub, clean_area=413)
    assert hub.session_path_segments == [SEGMENT]


def test_map_push_without_id_keeps_the_marker() -> None:
    hub = _hub()
    _restore(hub, {"map_id": 1, "segments": [SEGMENT]})
    hub._apply_map_data({"width": 100})
    assert hub._restored_map_id == 1
