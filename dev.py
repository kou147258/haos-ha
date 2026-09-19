#!/usr/bin/env python3
"""HAOS Dashboard — local development helper.

Run as ``python dev.py`` (or ``make dev`` via the bundled Makefile). Does
two things in one shot:

  1. Renders every page defined in ``options.example.json`` (or whichever
     config file you pass via ``--config``) into a numbered PNG sequence
     using ``fb_render.py --dump-png --synthetic``.
  2. Stitches those PNGs into a 3 × 2 overview grid so you can eyeball the
     whole layout in one image instead of flipping between six files.

Useful flags:

  --theme NAME           Override the theme for this run (midnight / graphite
                         / emerald / sunshine / cherry / cloud).
  --accent NAME          Override the accent color (cyan, purple, ..., or
                         #rrggbb).
  --cell-width  N        Width of each cell in the overview (default 480).
  --cell-height N        Height of each cell in the overview (default 320).
  --output    PATH       Path of the overview PNG (default ./dev-overview.png).
  --keep-cells           Keep the per-page PNGs after stitching (default off).
  --pages a,b,c          Subset of pages to render (default: all 6).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent
RENDERER = REPO_ROOT / "haos_fb" / "fb_render.py"
DEFAULT_CONFIG = REPO_ROOT / "haos_fb" / "options.example.json"

ALL_PAGES = ["status", "cpu", "memory", "network", "disks", "info"]


def _render_pages(
    pages: list[str],
    config: Path,
    theme: str | None,
    accent: str | None,
    out_dir: Path,
) -> list[Path]:
    """Run ``fb_render.py --dump-png`` for the given pages and return paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "page_%d.png")
    cmd = [
        sys.executable,
        str(RENDERER),
        "--config", str(config),
        "--dump-png", pattern,
        "--frames", str(len(pages)),
        "--synthetic",
        "--width", "800",
        "--height", "480",
    ]
    # Pass theme / accent via a tiny merged config file so we don't have to
    # plumb new CLI flags through fb_render.py.
    import json
    cfg_data = json.load(open(config, encoding="utf-8"))
    cfg_data["pages"] = pages
    if theme:
        cfg_data["theme"] = theme
    if accent:
        cfg_data["accent"] = accent
    cfg_path = out_dir / "_dev_config.json"
    cfg_path.write_text(json.dumps(cfg_data, indent=2), encoding="utf-8")
    cmd[cmd.index(str(config))] = str(cfg_path)

    print(f"[dev] Rendering {len(pages)} pages...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(f"fb_render.py failed with code {result.returncode}")
    # fb_render.py writes preview_0.png..preview_(n-1).png
    paths = sorted(out_dir.glob("page_*.png"))
    if len(paths) != len(pages):
        raise SystemExit(
            f"Expected {len(pages)} pages but got {len(paths)}: {paths}"
        )
    return paths


def _stitch(
    page_paths: list[Path],
    pages: list[str],
    out_path: Path,
    cell_w: int,
    cell_h: int,
    cols: int = 3,
    pad: int = 12,
) -> None:
    """Build a ``cols`` × ``rows`` overview PNG with a small label per cell."""
    rows = (len(page_paths) + cols - 1) // cols
    label_h = 24
    cell_total_h = cell_h + label_h

    grid_w = cols * cell_w + (cols + 1) * pad
    grid_h = rows * cell_total_h + (rows + 1) * pad

    canvas = Image.new("RGBA", (grid_w, grid_h), (10, 12, 20, 255))
    draw = ImageDraw.Draw(canvas)

    try:
        font = ImageFont.truetype(
            "C:/Windows/Fonts/consola.ttf", 14
        ) if os.name == "nt" else ImageFont.load_default()
    except OSError:
        font = ImageFont.load_default()

    for idx, (path, page) in enumerate(zip(page_paths, pages)):
        col = idx % cols
        row = idx // cols
        x = pad + col * (cell_w + pad)
        y = pad + row * (cell_total_h + pad)

        # Resize page into the cell.
        cell_img = Image.open(path).convert("RGBA")
        cell_img = cell_img.resize((cell_w, cell_h), Image.Resampling.LANCZOS)
        canvas.paste(cell_img, (x, y))

        # Caption strip under the cell.
        caption_y = y + cell_h + 4
        draw.rectangle(
            [x, y + cell_h, x + cell_w, y + cell_h + label_h],
            fill=(20, 28, 48, 255),
        )
        draw.text(
            (x + 8, caption_y),
            f"{idx + 1}. {page}",
            fill=(180, 200, 220, 255),
            font=font,
        )

    canvas.save(out_path, format="PNG")
    print(f"[dev] Wrote overview: {out_path} ({grid_w}x{grid_h})")


def _cleanup(temp_dir: Path, keep_cells: bool) -> None:
    if keep_cells:
        return
    for p in temp_dir.glob("page_*.png"):
        p.unlink()
    cfg = temp_dir / "_dev_config.json"
    if cfg.exists():
        cfg.unlink()
    try:
        temp_dir.rmdir()
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render + stitch a 3x2 overview of the HAOS Dashboard.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="Add-on options JSON to render against.")
    parser.add_argument("--theme", choices=[
        "midnight", "graphite", "emerald", "sunshine", "cherry", "cloud",
    ], default=None, help="Override the theme.")
    parser.add_argument("--accent", default=None,
                        help="Override the accent color (name or #rrggbb).")
    parser.add_argument("--cell-width", type=int, default=480,
                        help="Width of each cell in the overview PNG.")
    parser.add_argument("--cell-height", type=int, default=320,
                        help="Height of each cell in the overview PNG.")
    parser.add_argument("--output", type=Path,
                        default=REPO_ROOT / "dev-overview.png",
                        help="Output overview PNG path.")
    parser.add_argument("--keep-cells", action="store_true",
                        help="Keep individual page PNGs after stitching.")
    parser.add_argument("--pages", default=",".join(ALL_PAGES),
                        help="Comma-separated subset of pages to render.")
    args = parser.parse_args()

    pages = [p.strip() for p in args.pages.split(",") if p.strip()]
    if not pages:
        parser.error("--pages must list at least one page")
    unknown = [p for p in pages if p not in ALL_PAGES]
    if unknown:
        parser.error(f"Unknown pages: {unknown}. Valid: {ALL_PAGES}")

    with tempfile.TemporaryDirectory(prefix="fnd-dev-") as tmp:
        temp_dir = Path(tmp)
        try:
            page_paths = _render_pages(
                pages, args.config, args.theme, args.accent, temp_dir,
            )
            _stitch(
                page_paths, pages, args.output,
                cell_w=args.cell_width, cell_h=args.cell_height,
            )
        finally:
            _cleanup(temp_dir, args.keep_cells)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())