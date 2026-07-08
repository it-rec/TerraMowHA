"""Tests for the map HUD localization table."""

from custom_components.terramow.map_strings import (
    HUD_STRINGS,
    hud_strings,
    resolve_language,
)


def test_english_is_the_complete_baseline() -> None:
    base_keys = set(HUD_STRINGS["en"])
    assert base_keys
    # every other language may only use keys that exist in English
    for lang, table in HUD_STRINGS.items():
        assert set(table) <= base_keys, f"{lang} has unknown keys"


def test_resolve_exact_and_base_subtag() -> None:
    assert resolve_language("de") == "de"
    assert resolve_language("de-DE") == "de"
    assert resolve_language("pt-BR") == "pt"
    assert resolve_language("fr-CA") == "fr"


def test_resolve_chinese_variants() -> None:
    assert resolve_language("zh-Hans") == "zh-Hans"
    assert resolve_language("zh-Hant") == "zh-Hant"
    assert resolve_language("zh") == "zh-Hans"
    assert resolve_language("zh-TW") == "zh-Hant"
    assert resolve_language("zh-HK") == "zh-Hant"


def test_resolve_unknown_and_empty_fall_back_to_english() -> None:
    assert resolve_language("xx") == "en"
    assert resolve_language("") == "en"
    assert resolve_language(None) == "en"
    assert resolve_language(123) == "en"  # type: ignore[arg-type]


def test_hud_strings_is_always_key_complete() -> None:
    base_keys = set(HUD_STRINGS["en"])
    for lang in ("en", "de", "fr", "zh-Hant", "xx", None):
        table = hud_strings(lang)
        assert set(table) == base_keys


def test_hud_strings_translates_and_fills_missing_from_english() -> None:
    german = hud_strings("de")
    assert german["snapshot"] == "Karten-Schnappschuss"
    # a language that is not in the table returns pure English
    english = hud_strings("xx")
    assert english == HUD_STRINGS["en"]
