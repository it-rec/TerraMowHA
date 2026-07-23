"""The community-sourced error-code catalog (issue #171)."""

from custom_components.terramow.error_codes import ERROR_CODES, describe_error


def test_known_codes_resolve_to_text() -> None:
    assert describe_error(201) == "Mower lifted"
    assert describe_error(903) == "Mower stuck"
    # every catalog entry resolves through describe_error
    for code, text in ERROR_CODES.items():
        assert describe_error(code) == text


def test_unknown_and_malformed_codes_fall_back() -> None:
    assert describe_error(42) == "Error 42"
    assert describe_error(None) == "Error None"
    assert describe_error("x") == "Error x"
    # bools are ints in Python but never valid device codes
    assert describe_error(True) == "Error True"
