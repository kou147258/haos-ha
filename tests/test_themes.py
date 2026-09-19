"""Theme palette tests — pure Python, no HA dependency."""
from __future__ import annotations

from themes import ACCENT_COLORS, THEMES, resolve_palette


def test_six_themes_defined():
    assert set(THEMES.keys()) == {
        "midnight", "graphite", "emerald", "sunshine", "cherry", "cloud",
    }


def test_twelve_accent_colors():
    assert len(ACCENT_COLORS) == 12
    for name, color in ACCENT_COLORS.items():
        assert isinstance(color, tuple)
        assert len(color) == 3
        for component in color:
            assert 0 <= component <= 255


def test_all_themes_have_full_palette():
    required = {
        "bg", "surface", "surface_alt", "border", "text", "text_dim",
        "text_muted", "success", "warning", "danger", "accent",
        "cpu", "memory", "disk", "network",
        "temp_ok", "temp_warm", "temp_hot",
    }
    for name, palette in THEMES.items():
        missing = required - set(palette.keys())
        assert not missing, f"Theme {name!r} missing keys: {missing}"


def test_resolve_known_theme_no_accent():
    palette = resolve_palette("midnight", None)
    assert palette["bg"] == THEMES["midnight"]["bg"]
    assert palette["accent"] == THEMES["midnight"]["accent"]


def test_resolve_known_accent():
    palette = resolve_palette("midnight", "cyan")
    assert palette["accent"] == ACCENT_COLORS["cyan"]


def test_resolve_hex_accent():
    palette = resolve_palette("graphite", "#ff8800")
    assert palette["accent"] == (255, 136, 0)


def test_resolve_unknown_accent_keeps_default():
    palette = resolve_palette("midnight", "neon-rainbow")
    assert palette["accent"] == THEMES["midnight"]["accent"]


def test_resolve_invalid_hex_keeps_default():
    palette = resolve_palette("midnight", "#zzzzzz")
    assert palette["accent"] == THEMES["midnight"]["accent"]


def test_resolve_unknown_theme_falls_back_to_midnight():
    palette = resolve_palette("not-a-theme", None)
    assert palette == resolve_palette("midnight", None)


def test_resolve_accent_does_not_mutate_theme():
    """Theme dicts must stay pristine for the next resolve_palette() call."""
    resolve_palette("emerald", "rose")
    assert THEMES["emerald"]["accent"] != ACCENT_COLORS["rose"]
    palette2 = resolve_palette("emerald", None)
    assert palette2["accent"] == THEMES["emerald"]["accent"]