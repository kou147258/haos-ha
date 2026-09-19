"""5x7 ASCII bitmap font tests — no HA dependency."""
from __future__ import annotations

import string

from font import (
    BitmapFont,
    _ASCII_5X7,
    _cjk_placeholder,
)


def test_all_printable_ascii_present():
    printable = set(string.printable)
    glyph_keys = set(_ASCII_5X7.keys())
    missing = printable - glyph_keys - set("\t\n\r\x0b\x0c")
    assert not missing, f"Missing ASCII glyphs: {missing!r}"


def test_glyph_dimensions():
    for ch, glyph in _ASCII_5X7.items():
        assert len(glyph) == 7, f"Glyph {ch!r} not 7 rows"
        for row in glyph:
            assert 0 <= row <= 0x1F, f"Glyph {ch!r} row out of 5-bit range"


def test_cjk_placeholder_is_solid_block():
    glyph = _cjk_placeholder("\u4e2d")
    assert all(row == 0x1F for row in glyph)


def test_space_is_blank():
    assert all(row == 0 for row in _ASCII_5X7[" "])


def test_zero_glyph_has_no_lit_pixels():
    assert sum(_ASCII_5X7[" "]) == 0


def test_text_width_scales_linearly():
    font = BitmapFont()
    one = font.text_width("A", 1)
    ten = font.text_width("A" * 10, 1)
    assert ten == one * 10
    scale2 = font.text_width("A", 2)
    assert scale2 == one * 2


def test_draw_calls_callback_for_lit_pixels():
    font = BitmapFont()
    pixels = []

    def _put(px, py, color):
        pixels.append((px, py, color))

    font.draw(_put, 0, 0, "A", (255, 255, 255), 1)
    # "A" has multiple lit pixels; just ensure something was drawn.
    assert len(pixels) > 0
    # All callbacks should receive a color tuple.
    for px, py, color in pixels:
        assert isinstance(px, int)
        assert isinstance(py, int)
        assert isinstance(color, tuple)


def test_draw_calls_pixels_within_bounds():
    """Glyph pixels should not escape the canvas (renderer scales at runtime)."""
    font = BitmapFont()
    pixels = []

    def _put(px, py, color):
        pixels.append((px, py, color))

    font.draw(_put, 0, 0, "Hello", (255, 255, 255), 1)
    for px, py, _ in pixels:
        assert 0 <= px < 50   # "Hello" is ~30 cols, well within bounds
        assert 0 <= py < 10   # glyph is 7 rows tall