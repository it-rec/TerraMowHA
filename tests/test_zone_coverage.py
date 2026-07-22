"""Per-zone progress from the cycle coverage (issue #197).

The scene payload annotates every sub-region with the mowed fraction of the
running cycle, derived from the coverage segments: a segment edge counts for
the zone its midpoint lies in, covered area is edge length × cutting width,
capped at the zone area.
"""

from unittest.mock import AsyncMock, MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.map_card import (
    _zone_coverage_ratios,
    build_scene_payload,
)
from custom_components.terramow.map_scene import (
    build_scene,
    point_in_polygon,
    polygon_area,
)

# 10 m × 10 m zone at the origin (mm coordinates)
ZONE = {
    "id": 7,
    "name": "Front",
    "boundary": {
        "points": [
            {"x": 0, "y": 0},
            {"x": 10000, "y": 0},
            {"x": 10000, "y": 10000},
            {"x": 0, "y": 10000},
        ]
    },
}
MAP_DATA = {
    "id": 1,
    "name": "Garden",
    "map_state": "MAP_STATE_COMPLETE",
    "width": 100,
    "height": 80,
    "resolution": 100,
    "origin": {"x": 0, "y": 0},
    "regions": [
        {"id": 1, "name": "Main", "boundary": ZONE["boundary"], "sub_regions": [ZONE]}
    ],
}


def _scene(coverage_segments):
    return build_scene(
        MAP_DATA, {}, {}, False, session_path_segments=coverage_segments
    )


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------


def test_polygon_area_square_and_degenerate() -> None:
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert polygon_area(square) == 100.0
    assert polygon_area([(0, 0), (10, 10)]) == 0.0


def test_point_in_polygon() -> None:
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert point_in_polygon((5.0, 5.0), square) is True
    assert point_in_polygon((15.0, 5.0), square) is False
    assert point_in_polygon((-1.0, -1.0), square) is False


# ---------------------------------------------------------------------------
# ratio computation
# ---------------------------------------------------------------------------


def test_partial_coverage_ratio() -> None:
    # one 10 m track inside the 100 m² zone: 10 000 mm × 320 mm = 3.2 m² → 3.2 %
    scene = _scene([[{"x": 500, "y": 5000}, {"x": 9500, "y": 5000}]])
    ratios = _zone_coverage_ratios(scene)
    assert ratios == {7: 0.029}  # 9 000 mm × 320 / 100 m²


def test_ratio_caps_at_one() -> None:
    # a dense back-and-forth track whose raw product exceeds the zone area
    segment = []
    for i in range(40):
        y = 125 + i * 250
        segment.append({"x": 100, "y": y})
        segment.append({"x": 9900, "y": y})
    scene = _scene([segment])
    assert _zone_coverage_ratios(scene)[7] == 1.0


def test_edges_outside_the_zone_do_not_count() -> None:
    scene = _scene([[{"x": 20000, "y": 20000}, {"x": 30000, "y": 20000}]])
    assert _zone_coverage_ratios(scene) == {}


def test_no_segments_short_circuits() -> None:
    assert _zone_coverage_ratios(_scene([])) == {}


def test_single_point_segments_yield_no_edges() -> None:
    scene = _scene([[{"x": 500, "y": 500}]])
    assert _zone_coverage_ratios(scene) == {}


def test_degenerate_zone_is_skipped() -> None:
    map_data = {
        **MAP_DATA,
        "regions": [
            {
                "id": 1,
                "name": "Main",
                "boundary": ZONE["boundary"],
                "sub_regions": [
                    {**ZONE, "id": None},
                    {
                        "id": 9,
                        "name": "Line",
                        "boundary": {
                            "points": [
                                {"x": 0, "y": 0},
                                {"x": 1000, "y": 0},
                                {"x": 2000, "y": 0},
                            ]
                        },
                    },
                ],
            }
        ],
    }
    scene = build_scene(
        map_data,
        {},
        {},
        False,
        session_path_segments=[[{"x": 500, "y": 0}, {"x": 900, "y": 0}]],
    )
    assert _zone_coverage_ratios(scene) == {}


# ---------------------------------------------------------------------------
# payload plumbing
# ---------------------------------------------------------------------------


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.170", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    return hub


def test_payload_carries_the_zone_coverage() -> None:
    hub = _hub()
    hub._map_data = MAP_DATA
    hub._coverage_segments = [[{"x": 500, "y": 5000}, {"x": 9500, "y": 5000}]]
    payload = build_scene_payload(hub)
    sub = payload["regions"][0]["sub_regions"][0]
    assert sub["coverage"] == 0.029


def test_payload_coverage_is_none_when_untouched() -> None:
    hub = _hub()
    hub._map_data = MAP_DATA
    payload = build_scene_payload(hub)
    sub = payload["regions"][0]["sub_regions"][0]
    assert sub["coverage"] is None
