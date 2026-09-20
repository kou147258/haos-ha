"""Theme palette for the fb0 renderer.

Ported from the original haos themes. Each theme defines colors for
the surface, surface accents, text, dividers, and the data-driven accents
(CPU / memory / disk / network). Accent overrides a single color across themes.
"""
from __future__ import annotations

from typing import TypedDict


class Palette(TypedDict, total=False):
    bg: tuple[int, int, int]
    surface: tuple[int, int, int]
    surface_alt: tuple[int, int, int]
    border: tuple[int, int, int]
    text: tuple[int, int, int]
    text_dim: tuple[int, int, int]
    text_muted: tuple[int, int, int]
    success: tuple[int, int, int]
    warning: tuple[int, int, int]
    danger: tuple[int, int, int]
    accent: tuple[int, int, int]
    cpu: tuple[int, int, int]
    memory: tuple[int, int, int]
    disk: tuple[int, int, int]
    network: tuple[int, int, int]
    temp_ok: tuple[int, int, int]
    temp_warm: tuple[int, int, int]
    temp_hot: tuple[int, int, int]


# Twelve accent colors users can pick from the add-on config (hex -> rgb tuple)
ACCENT_COLORS: dict[str, tuple[int, int, int]] = {
    "cyan": (6, 182, 212),
    "purple": (168, 85, 247),
    "emerald": (16, 185, 129),
    "amber": (245, 158, 11),
    "rose": (244, 63, 94),
    "blue": (59, 130, 246),
    "indigo": (99, 102, 241),
    "lime": (132, 204, 22),
    "orange": (249, 115, 22),
    "pink": (236, 72, 153),
    "teal": (20, 184, 166),
    "yellow": (234, 179, 8),
}


THEMES: dict[str, Palette] = {
    "midnight": {
        "bg": (6, 8, 16),
        "surface": (15, 23, 42),
        "surface_alt": (30, 41, 59),
        "border": (51, 65, 85),
        "text": (226, 232, 240),
        "text_dim": (148, 163, 184),
        "text_muted": (100, 116, 139),
        "success": (16, 185, 129),
        "warning": (245, 158, 11),
        "danger": (239, 68, 68),
        "accent": (6, 182, 212),
        "cpu": (6, 182, 212),
        "memory": (168, 85, 247),
        "disk": (245, 158, 11),
        "network": (16, 185, 129),
        "temp_ok": (16, 185, 129),
        "temp_warm": (245, 158, 11),
        "temp_hot": (239, 68, 68),
    },
    "graphite": {
        "bg": (12, 12, 14),
        "surface": (24, 24, 28),
        "surface_alt": (38, 38, 44),
        "border": (58, 58, 66),
        "text": (230, 230, 235),
        "text_dim": (160, 160, 170),
        "text_muted": (110, 110, 120),
        "success": (120, 200, 120),
        "warning": (230, 180, 80),
        "danger": (220, 90, 90),
        "accent": (160, 160, 170),
        "cpu": (180, 180, 190),
        "memory": (140, 140, 150),
        "disk": (200, 180, 120),
        "network": (120, 200, 120),
        "temp_ok": (120, 200, 120),
        "temp_warm": (230, 180, 80),
        "temp_hot": (220, 90, 90),
    },
    "emerald": {
        "bg": (4, 16, 12),
        "surface": (10, 36, 26),
        "surface_alt": (16, 56, 40),
        "border": (24, 80, 56),
        "text": (220, 240, 230),
        "text_dim": (140, 180, 160),
        "text_muted": (90, 130, 110),
        "success": (16, 185, 129),
        "warning": (245, 158, 11),
        "danger": (239, 68, 68),
        "accent": (16, 185, 129),
        "cpu": (16, 185, 129),
        "memory": (132, 204, 22),
        "disk": (20, 184, 166),
        "network": (34, 197, 94),
        "temp_ok": (16, 185, 129),
        "temp_warm": (245, 158, 11),
        "temp_hot": (239, 68, 68),
    },
    "sunshine": {
        "bg": (28, 20, 8),
        "surface": (48, 36, 16),
        "surface_alt": (72, 52, 24),
        "border": (108, 78, 36),
        "text": (255, 240, 210),
        "text_dim": (220, 180, 130),
        "text_muted": (160, 130, 90),
        "success": (132, 204, 22),
        "warning": (245, 158, 11),
        "danger": (239, 68, 68),
        "accent": (249, 115, 22),
        "cpu": (249, 115, 22),
        "memory": (234, 179, 8),
        "disk": (245, 158, 11),
        "network": (132, 204, 22),
        "temp_ok": (132, 204, 22),
        "temp_warm": (245, 158, 11),
        "temp_hot": (239, 68, 68),
    },
    "cherry": {
        "bg": (24, 8, 16),
        "surface": (44, 16, 28),
        "surface_alt": (72, 24, 44),
        "border": (108, 36, 64),
        "text": (255, 220, 230),
        "text_dim": (220, 160, 180),
        "text_muted": (160, 110, 130),
        "success": (236, 72, 153),
        "warning": (245, 158, 11),
        "danger": (239, 68, 68),
        "accent": (236, 72, 153),
        "cpu": (236, 72, 153),
        "memory": (244, 63, 94),
        "disk": (168, 85, 247),
        "network": (236, 72, 153),
        "temp_ok": (236, 72, 153),
        "temp_warm": (245, 158, 11),
        "temp_hot": (239, 68, 68),
    },
    "cloud": {
        "bg": (240, 244, 248),
        "surface": (255, 255, 255),
        "surface_alt": (230, 236, 242),
        "border": (200, 210, 220),
        "text": (24, 32, 44),
        "text_dim": (80, 96, 110),
        "text_muted": (140, 152, 165),
        "success": (16, 185, 129),
        "warning": (234, 138, 18),
        "danger": (220, 38, 38),
        "accent": (37, 99, 235),
        "cpu": (37, 99, 235),
        "memory": (124, 58, 237),
        "disk": (217, 119, 6),
        "network": (16, 185, 129),
        "temp_ok": (16, 185, 129),
        "temp_warm": (234, 138, 18),
        "temp_hot": (220, 38, 38),
    },
}


def resolve_palette(theme: str, accent: str | None) -> Palette:
    """Return the palette for a theme, optionally overridden by an accent color."""
    palette = dict(THEMES.get(theme, THEMES["midnight"]))
    if accent:
        if accent in ACCENT_COLORS:
            palette["accent"] = ACCENT_COLORS[accent]
        elif accent.startswith("#") and len(accent) == 7:
            try:
                palette["accent"] = (
                    int(accent[1:3], 16),
                    int(accent[3:5], 16),
                    int(accent[5:7], 16),
                )
            except ValueError:
                pass
    return palette