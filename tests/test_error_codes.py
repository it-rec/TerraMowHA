"""The community-sourced error- and event-code catalogs (issue #171, upstream #86)."""

from custom_components.terramow.error_codes import (
    ERROR_CODES,
    EVENT_CODES,
    describe_error,
    describe_event,
)


def test_known_codes_resolve_to_text() -> None:
    assert describe_error(103) == "Cutting height adjustment stuck"
    assert describe_error(201) == "Mower lifted"
    assert describe_error(903) == "Mower stuck"
    assert describe_error(909) == "Mower stuck"
    # every catalog entry resolves through describe_error
    for code, text in ERROR_CODES.items():
        assert describe_error(code) == text


def test_unknown_and_malformed_codes_fall_back() -> None:
    assert describe_error(42) == "Error 42"
    assert describe_error(None) == "Error None"
    assert describe_error("x") == "Error x"
    # bools are ints in Python but never valid device codes
    assert describe_error(True) == "Error True"


def test_known_event_codes_resolve_to_text() -> None:
    # upstream TerraMow/TerraMowHA #86: a start refused outside the window
    assert describe_event(135) == "Outside operating time"
    for code, text in EVENT_CODES.items():
        assert describe_event(code) == text


def test_unknown_and_malformed_event_codes_fall_back() -> None:
    assert describe_event(8) == "Event 8"
    assert describe_event(None) == "Event None"
    assert describe_event(True) == "Event True"
