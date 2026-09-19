"""HAOS Dashboard Display — /dev/fb0 renderer for the HA Supervisor add-on.

Adapted from neon9809/haos's ``app/bin/fb_render.py``. Material
changes vs. the original:

  * Data source is the HA REST API (``/api/states``) instead of a local
    ``/api/status`` endpoint, queried via the Supervisor token injected into
    the add-on environment as ``SUPERVISOR_TOKEN``.
  * No fnOS CGI gateway / FPK packaging / fnOS-specific ``/vol*`` handling.
  * Renderer is canvas-agnostic: it can target the real ``/dev/fb0`` device
    via mmap, **or** a PIL-backed in-memory image via ``--dump-png``. The
    ``PILCanvas`` keeps the entire ``PageRenderer`` reusable for dev work
    on machines without a connected display.

The renderer opens ``/dev/fb0`` (or a PIL image), then runs a render loop
that alternates between enabled pages at ``page_interval`` seconds. When HA
is unreachable the last good frame is retained and an ``OFFLINE`` badge is
overlaid in the corner.
"""
from __future__ import annotations

import argparse
import asyncio
import errno
import json
import logging
import os
import random
import struct
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

try:
    import aiohttp  # only required when pulling from Home Assistant
except ImportError:  # pragma: no cover — Windows dev preview
    aiohttp = None  # type: ignore[assignment]

try:
    import fcntl  # POSIX only — used by FrameBuffer for flock + ioctl
except ImportError:  # pragma: no cover — Windows dev preview
    fcntl = None  # type: ignore[assignment]

from font import load_font
from themes import resolve_palette

_LOGGER = logging.getLogger("fb_render")


# ---------------------------------------------------------------------------
# Canvas protocol — anything with pixel/fill_rect/clear/text/flush + width/height
# ---------------------------------------------------------------------------


class _CanvasProtocol:
    """Type hint surface; not meant to be subclassed for behavior."""

    width: int
    height: int

    def pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None: ...
    def fill_rect(self, x: int, y: int, w: int, h: int,
                  color: tuple[int, int, int]) -> None: ...
    def clear(self, color: tuple[int, int, int]) -> None: ...
    def text(self, font, x: int, y: int, text: str, color,
             scale: int = 1) -> None: ...
    def flush(self) -> None: ...


# ---------------------------------------------------------------------------
# Real /dev/fb0 backend
# ---------------------------------------------------------------------------


@dataclass
class FBInfo:
    width: int
    height: int
    bpp: int
    stride: int
    size: int
    red_offset: int
    red_length: int
    green_offset: int
    green_length: int
    blue_offset: int
    blue_length: int


class FrameBuffer:
    """Open /dev/fb0 and provide pixel() / flush() primitives."""

    def __init__(self, device: str = "/dev/fb0") -> None:
        self.device = device
        self.fd: int | None = None
        self.info: FBInfo | None = None
        self.mmap: Any = None
        self._lockfile: int | None = None

    # ----- canvas surface -----

    @property
    def width(self) -> int:
        return self.info.width if self.info else 0

    @property
    def height(self) -> int:
        return self.info.height if self.info else 0

    # ----- lifecycle -----

    def open(self) -> None:
        if fcntl is None:
            raise RuntimeError(
                "FrameBuffer.open() requires the POSIX fcntl module; "
                "use --dump-png for headless development on non-Linux hosts."
            )
        self.fd = os.open(self.device, os.O_RDWR)
        info = self._read_info(self.fd)
        self.info = info
        self.mmap = _mmap_create(self.fd, info.size)
        lock_path = "/tmp/haos_fb.lock"
        self._lockfile = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o660)
        try:
            fcntl.flock(self._lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as err:
            raise RuntimeError(
                f"Another fb renderer holds {lock_path}: {err}"
            ) from err

    def close(self) -> None:
        if self.mmap is not None:
            _mmap_close(self.mmap)
            self.mmap = None
        if self._lockfile is not None:
            try:
                fcntl.flock(self._lockfile, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(self._lockfile)
            self._lockfile = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    # ----- drawing -----

    def clear(self, color: tuple[int, int, int]) -> None:
        if self.info is None or self.mmap is None:
            return
        self._fill_rect(0, 0, self.info.width, self.info.height, color)

    def pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if self.info is None or self.mmap is None:
            return
        if x < 0 or y < 0 or x >= self.info.width or y >= self.info.height:
            return
        if self.info.bpp == 32:
            offset = y * self.info.stride + x * 4
            value = _pack_rgb32(
                color,
                self.info.red_offset, self.info.red_length,
                self.info.green_offset, self.info.green_length,
                self.info.blue_offset, self.info.blue_length,
            )
            struct.pack_into("<I", self.mmap, offset, value)
        elif self.info.bpp == 16:
            offset = y * self.info.stride + x * 2
            value = _pack_rgb16(
                color,
                self.info.red_offset, self.info.red_length,
                self.info.green_offset, self.info.green_length,
                self.info.blue_offset, self.info.blue_length,
            )
            struct.pack_into("<H", self.mmap, offset, value)
        # 8-bit paletted / mono not supported — caller must ensure 16/32 bpp.

    def fill_rect(self, x: int, y: int, w: int, h: int,
                  color: tuple[int, int, int]) -> None:
        if self.info is None or self.mmap is None:
            return
        self._fill_rect(x, y, w, h, color)

    def _fill_rect(self, x: int, y: int, w: int, h: int,
                   color: tuple[int, int, int]) -> None:
        if self.info is None or self.mmap is None:
            return
        x2 = min(self.info.width, x + w)
        y2 = min(self.info.height, y + h)
        if self.info.bpp == 32:
            value = _pack_rgb32(
                color,
                self.info.red_offset, self.info.red_length,
                self.info.green_offset, self.info.green_length,
                self.info.blue_offset, self.info.blue_length,
            )
            for yy in range(y, y2):
                start = yy * self.info.stride + x * 4
                struct.pack_into(f"<{(x2 - x)}I", self.mmap, start,
                                 *([value] * (x2 - x)))
        elif self.info.bpp == 16:
            value = _pack_rgb16(
                color,
                self.info.red_offset, self.info.red_length,
                self.info.green_offset, self.info.green_length,
                self.info.blue_offset, self.info.blue_length,
            )
            for yy in range(y, y2):
                start = yy * self.info.stride + x * 2
                struct.pack_into(f"<{(x2 - x)}H", self.mmap, start,
                                 *([value] * (x2 - x)))

    def text(self, font, x: int, y: int, text: str, color,
             scale: int = 1) -> None:
        if self.info is None or self.mmap is None:
            return

        def _put(px: int, py: int, _c) -> None:
            self.pixel(px, py, color if isinstance(color, tuple) else color)

        font.draw(_put, x, y, text, color, scale)

    def flush(self) -> None:
        if self.fd is None or self.info is None or fcntl is None:
            return
        try:
            v = struct.pack("<I", 0)
            fcntl.ioctl(self.fd, 0x4606, v)  # FBIOPAN_DISPLAY
        except OSError as err:
            if err.errno not in (errno.ENOTTY, errno.EINVAL):
                _LOGGER.debug("FBIOPAN_DISPLAY failed: %s", err)

    # ----- helpers -----

    @staticmethod
    def _read_info(fd: int) -> FBInfo:
        """Read /dev/fb0 + sysfs to fill an FBInfo struct."""
        var_info = bytearray(160)
        fcntl.ioctl(fd, 0x4601, var_info)  # type: ignore[union-attr]
        xres = struct.unpack_from("<I", var_info, 0)[0]
        yres = struct.unpack_from("<I", var_info, 4)[0]
        bpp = struct.unpack_from("<H", var_info, 24)[0]
        red_off = struct.unpack_from("<H", var_info, 32)[0]
        red_len = struct.unpack_from("<H", var_info, 34)[0]
        green_off = struct.unpack_from("<H", var_info, 36)[0]
        green_len = struct.unpack_from("<H", var_info, 38)[0]
        blue_off = struct.unpack_from("<H", var_info, 40)[0]
        blue_len = struct.unpack_from("<H", var_info, 42)[0]

        fix_info = bytearray(68)
        fcntl.ioctl(fd, 0x4602, fix_info)  # type: ignore[union-attr]
        stride = struct.unpack_from("<I", fix_info, 0)[0]
        smem_len = struct.unpack_from("<I", fix_info, 32)[0]

        if stride == 0:
            stride = (xres * bpp + 31) // 32 * 4
        if smem_len == 0:
            smem_len = stride * yres

        return FBInfo(
            width=xres, height=yres, bpp=bpp, stride=stride, size=smem_len,
            red_offset=red_off, red_length=red_len,
            green_offset=green_off, green_length=green_len,
            blue_offset=blue_off, blue_length=blue_len,
        )


def _mmap_create(fd: int, size: int):
    """mmap the frame buffer."""
    import mmap as _mmap
    return _mmap.mmap(fd, size, _mmap.MAP_SHARED, _mmap.PROT_READ | _mmap.PROT_WRITE)


def _mmap_close(buf) -> None:
    buf.close()


# ---------------------------------------------------------------------------
# Headless canvas (PIL-backed) for --dump-png dev preview
# ---------------------------------------------------------------------------


class PILCanvas:
    """In-memory canvas that mimics the FrameBuffer drawing API.

    Lets the entire ``PageRenderer`` run unmodified in headless mode where no
    real frame buffer exists — render a frame, dump it to a PNG, done.
    """

    def __init__(self, width: int, height: int) -> None:
        from PIL import Image, ImageDraw
        self.width = int(width)
        self.height = int(height)
        self._image = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 255))
        self._draw = ImageDraw.Draw(self._image)

    def pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self._draw.point((x, y), fill=color + (255,))

    def fill_rect(self, x: int, y: int, w: int, h: int,
                  color: tuple[int, int, int]) -> None:
        # PIL clamps negative / oversize rects itself.
        self._draw.rectangle([x, y, x + w - 1, y + h - 1], fill=color + (255,))

    def clear(self, color: tuple[int, int, int]) -> None:
        self._image.paste(color + (255,), [0, 0, self.width, self.height])
        from PIL import ImageDraw
        self._draw = ImageDraw.Draw(self._image)

    def text(self, font, x: int, y: int, text: str, color,
             scale: int = 1) -> None:
        def _put(px: int, py: int, _color) -> None:
            if 0 <= px < self.width and 0 <= py < self.height:
                self._draw.point((px, py), fill=color + (255,))

        font.draw(_put, x, y, text, color, scale)

    def flush(self) -> None:
        """No-op for the headless canvas; ``save`` is the explicit sync point."""

    def save(self, path: str) -> None:
        """Write the current frame buffer to a PNG file."""
        self._image.save(path, format="PNG")


def _pack_rgb32(color, ro, rl, go, gl, bo, bl):
    r = (color[0] >> (8 - rl)) & ((1 << rl) - 1)
    g = (color[1] >> (8 - gl)) & ((1 << gl) - 1)
    b = (color[2] >> (8 - bl)) & ((1 << bl) - 1)
    return (r << ro) | (g << go) | (b << bo)


def _pack_rgb16(color, ro, rl, go, gl, bo, bl):
    r = (color[0] >> (8 - rl)) & ((1 << rl) - 1)
    g = (color[1] >> (8 - gl)) & ((1 << gl) - 1)
    b = (color[2] >> (8 - bl)) & ((1 << bl) - 1)
    return (r << ro) | (g << go) | (b << bo)


# ---------------------------------------------------------------------------
# Data fetching from Home Assistant
# ---------------------------------------------------------------------------


class HAClient:
    """Pulls sensor snapshots from the HA REST API."""

    def __init__(self, base_url: str, token: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._last_snapshot: dict[str, Any] = {}
        self._last_ok_ts: float = 0.0

    async def __aenter__(self) -> "HAClient":
        self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def last_ok_ts(self) -> float:
        return self._last_ok_ts

    @property
    def last_snapshot(self) -> dict[str, Any]:
        return self._last_snapshot

    async def fetch_snapshot(self) -> dict[str, Any] | None:
        if self._session is None:
            return None
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}/api/states"
        try:
            async with self._session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("HA fetch failed: %s", err)
            return None

        snapshot: dict[str, Any] = {
            "cpu": {"percent": 0.0, "per_core": [], "load": [0.0, 0.0, 0.0],
                     "freq_mhz": 0, "temp": None, "logical_cores": 0, "physical_cores": 0},
            "memory": {"percent": 0.0, "used": 0, "total": 0, "free": 0,
                        "swap_percent": 0.0, "swap_used": 0, "swap_total": 0},
            "disks": [],
            "network": {"interfaces": [], "bytes_sent": 0, "bytes_recv": 0,
                         "packets_sent": 0, "packets_recv": 0,
                         "up_kbps": 0.0, "down_kbps": 0.0},
            "temperatures": [],
            "processes": 0,
            "uptime_seconds": 0,
            "boot_time": 0,
            "hostname": "HAOS Dashboard",
            "os": "unknown",
            "kernel": "",
            "ts": time.time(),
        }

        for state in data:
            eid = state.get("entity_id", "")
            if not eid.startswith("sensor.haos_"):
                continue
            value = state.get("state")
            attrs = state.get("attributes") or {}
            snapshot = _merge_entity(snapshot, eid, value, attrs)

        self._last_snapshot = snapshot
        self._last_ok_ts = time.time()
        return snapshot


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "unknown", "unavailable"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    f = _safe_float(value)
    return int(f) if f is not None else None


def _merge_entity(snapshot: dict[str, Any], eid: str, value: Any,
                  attrs: dict[str, Any]) -> dict[str, Any]:
    short = eid[len("sensor.haos_"):]

    if short == "cpu_percent":
        v = _safe_float(value)
        if v is not None:
            snapshot["cpu"]["percent"] = v
    elif short == "cpu_load_1":
        v = _safe_float(value)
        if v is not None:
            snapshot["cpu"]["load"][0] = v
    elif short == "cpu_freq":
        v = _safe_float(value)
        if v is not None:
            snapshot["cpu"]["freq_mhz"] = v
    elif short == "cpu_temp":
        v = _safe_float(value)
        if v is not None:
            snapshot["cpu"]["temp"] = v
    elif short.startswith("cpu_core_"):
        v = _safe_float(value)
        if v is not None:
            snapshot["cpu"]["per_core"].append(v)
    elif short == "memory_percent":
        v = _safe_float(value)
        if v is not None:
            snapshot["memory"]["percent"] = v
    elif short == "memory_used":
        v = _safe_int(value)
        if v is not None:
            snapshot["memory"]["used"] = v
    elif short == "memory_total":
        v = _safe_int(value)
        if v is not None:
            snapshot["memory"]["total"] = v
    elif short == "memory_free":
        v = _safe_int(value)
        if v is not None:
            snapshot["memory"]["free"] = v
    elif short == "swap_percent":
        v = _safe_float(value)
        if v is not None:
            snapshot["memory"]["swap_percent"] = v
    elif short == "swap_used":
        v = _safe_int(value)
        if v is not None:
            snapshot["memory"]["swap_used"] = v
    elif short == "swap_total":
        v = _safe_int(value)
        if v is not None:
            snapshot["memory"]["swap_total"] = v
    elif short == "net_up":
        v = _safe_float(value)
        if v is not None:
            snapshot["network"]["up_kbps"] = v
    elif short == "net_down":
        v = _safe_float(value)
        if v is not None:
            snapshot["network"]["down_kbps"] = v
    elif short == "net_bytes_sent":
        v = _safe_int(value)
        if v is not None:
            snapshot["network"]["bytes_sent"] = v
    elif short == "net_bytes_recv":
        v = _safe_int(value)
        if v is not None:
            snapshot["network"]["bytes_recv"] = v
    elif short == "uptime":
        v = _safe_float(value)
        if v is not None:
            snapshot["uptime_seconds"] = int(v)
    elif short == "processes":
        v = _safe_int(value)
        if v is not None:
            snapshot["processes"] = v
    elif short == "hostname":
        snapshot["hostname"] = str(value)
    elif short == "os":
        snapshot["os"] = str(value)
    elif short.startswith("disk_"):
        rest = short[len("disk_"):]
        for metric in ("percent", "used", "free", "total"):
            if rest.endswith(f"_{metric}"):
                mount = rest[: -len(metric) - 1].replace("_", "/")
                if not mount.startswith("/"):
                    mount = "/" + mount
                _merge_disk(snapshot, mount, metric, value)
                break
    elif short.startswith("temperature_"):
        rest = short[len("temperature_"):]
        v = _safe_float(value)
        if v is not None:
            snapshot["temperatures"].append({
                "label": rest.replace("_", " "),
                "group": rest.split("_")[0] if "_" in rest else rest,
                "current": v,
                "high": attrs.get("high"),
                "critical": attrs.get("critical"),
            })
    return snapshot


def _merge_disk(snapshot: dict[str, Any], mount: str, metric: str,
                value: Any) -> None:
    disk = None
    for d in snapshot["disks"]:
        if d["mount"] == mount:
            disk = d
            break
    if disk is None:
        disk = {"mount": mount, "device": "", "fstype": ""}
        snapshot["disks"].append(disk)
    if metric == "percent":
        v = _safe_float(value)
        if v is not None:
            disk["percent"] = v
    else:
        v = _safe_int(value)
        if v is not None:
            disk[metric] = v


# ---------------------------------------------------------------------------
# Synthetic snapshot for --dump-png dev work without HA
# ---------------------------------------------------------------------------


def _make_synthetic_snapshot(width: int, height: int) -> dict[str, Any]:
    """Return a fake but realistic-looking snapshot for headless dev.

    Numbers drift slightly each call so the renderer's animations and bars
    can be visually checked.
    """
    now = time.time()
    rng = random.Random(int(now) // 4)
    cores = max(1, rng.randint(4, 16))
    per_core = [round(rng.uniform(2, 80), 1) for _ in range(cores)]
    cpu_percent = round(sum(per_core) / cores, 1)
    freq = rng.uniform(1800, 4200)
    cpu_temp = round(rng.uniform(38, 78), 1)
    load = [round(rng.uniform(0.05, 2.0), 2) for _ in range(3)]

    mem_total = 16 * 1024 * 1024 * 1024
    mem_used = int(mem_total * rng.uniform(0.15, 0.7))
    swap_total = 4 * 1024 * 1024 * 1024
    swap_used = int(swap_total * rng.uniform(0, 0.3))

    disks = [
        {"mount": "/", "device": "/dev/sda2", "fstype": "ext4",
         "total": 500 * 1024**3, "used": int(500 * 1024**3 * rng.uniform(0.2, 0.7)),
         "free": 0, "percent": round(rng.uniform(20, 70), 1)},
        {"mount": "/data", "device": "/dev/sdb1", "fstype": "ext4",
         "total": 2 * 1024**4, "used": int(2 * 1024**4 * rng.uniform(0.3, 0.85)),
         "free": 0, "percent": round(rng.uniform(30, 85), 1)},
    ]
    for d in disks:
        d["free"] = d["total"] - d["used"]

    interfaces = [
        {"name": "eth0", "is_up": True, "speed_mbps": 1000, "mtu": 1500},
        {"name": "wlan0", "is_up": False, "speed_mbps": 0, "mtu": 1500},
    ]
    network = {
        "interfaces": interfaces,
        "bytes_sent": rng.randint(1_000_000, 1_000_000_000),
        "bytes_recv": rng.randint(1_000_000, 5_000_000_000),
        "packets_sent": rng.randint(1000, 1_000_000),
        "packets_recv": rng.randint(1000, 5_000_000),
        "up_kbps": round(rng.uniform(0, 2000), 1),
        "down_kbps": round(rng.uniform(0, 8000), 1),
    }

    temps = [
        {"label": "CPU", "group": "coretemp", "current": cpu_temp,
         "high": 90.0, "critical": 100.0},
        {"label": "GPU", "group": "amdgpu", "current": round(rng.uniform(40, 70), 1),
         "high": 90.0, "critical": 105.0},
    ]

    boot = now - rng.randint(60, 60 * 60 * 24 * 14)

    return {
        "ts": now,
        "boot_time": boot,
        "uptime_seconds": int(now - boot),
        "hostname": "fnos-dev",
        "os": "Debian GNU/Linux 12 (bookworm)",
        "kernel": "6.1.0-21-amd64",
        "processes": rng.randint(120, 280),
        "cpu": {
            "percent": cpu_percent,
            "per_core": per_core,
            "load": load,
            "freq_mhz": freq,
            "temp": cpu_temp,
            "logical_cores": cores,
            "physical_cores": max(1, cores // 2),
        },
        "memory": {
            "percent": round(mem_used / mem_total * 100, 1),
            "used": mem_used,
            "total": mem_total,
            "free": mem_total - mem_used,
            "swap_percent": round(swap_used / swap_total * 100, 1),
            "swap_used": swap_used,
            "swap_total": swap_total,
        },
        "disks": disks,
        "network": network,
        "temperatures": temps,
    }


# ---------------------------------------------------------------------------
# Page renderer — operates on any canvas implementing the protocol
# ---------------------------------------------------------------------------


def _fmt_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    v = float(value)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.1f} {units[i]}"


def _fmt_rate(kbps: float | None) -> str:
    if kbps is None:
        return "—"
    if kbps >= 1024:
        return f"{kbps / 1024:.2f} MB/s"
    return f"{kbps:.1f} KB/s"


def _fmt_uptime(seconds: int | None) -> str:
    if not seconds:
        return "—"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    mins = (seconds % 3600) // 60
    if days:
        return f"{days}d {hours}h {mins}m"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def _fmt_temp(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "F":
        return f"{value * 9 / 5 + 32:.1f} F"
    return f"{value:.1f} C"


def _temp_color(value: float | None, palette) -> tuple[int, int, int]:
    if value is None:
        return palette["text_muted"]
    if value >= 80:
        return palette["temp_hot"]
    if value >= 65:
        return palette["temp_warm"]
    return palette["temp_ok"]


class PageRenderer:
    """Stateful helper that lays out content on whatever canvas is given."""

    def __init__(self, canvas: _CanvasProtocol, font, palette: dict) -> None:
        self.canvas = canvas
        self.font = font
        self.palette = palette

    # ----- drawing helpers -----

    def draw_text(self, x: int, y: int, text: str, color,
                  size: int = 16, scale: int = 1) -> int:
        self.canvas.text(self.font, x, y, text, color, scale)
        return x + self.font.text_width(text, scale)

    def draw_filled_round_rect(self, x: int, y: int, w: int, h: int,
                                color, radius: int = 6) -> None:
        if radius <= 0:
            self.canvas.fill_rect(x, y, w, h, color)
            return
        self.canvas.fill_rect(x + radius, y, w - 2 * radius, h, color)
        self.canvas.fill_rect(x, y + radius, w, h - 2 * radius, color)
        for cx, cy in (
            (x + radius, y + radius),
            (x + w - radius - 1, y + radius),
            (x + radius, y + h - radius - 1),
            (x + w - radius - 1, y + h - radius - 1),
        ):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if dx * dx + dy * dy <= radius * radius:
                        self.canvas.pixel(cx + dx, cy + dy, color)

    def draw_progress_bar(self, x: int, y: int, w: int, h: int,
                          value: float, fg, bg, max_value: float = 100.0) -> None:
        self.canvas.fill_rect(x, y, w, h, bg)
        filled = max(0, min(w, int(w * value / max_value)))
        if filled > 0:
            self.canvas.fill_rect(x, y, filled, h, fg)

    def draw_badge(self, x: int, y: int, w: int, h: int, label: str,
                   fg, bg, size: int = 12) -> None:
        self.draw_filled_round_rect(x, y, w, h, bg, 3)
        self.canvas.text(self.font, x + 4, y + (h - size) // 2, label, fg, 1)

    def layout_card(self, x: int, y: int, w: int, h: int) -> None:
        self.draw_filled_round_rect(x, y, w, h, self.palette["surface"], 8)
        self.canvas.fill_rect(x + 8, y, w - 16, 2, self.palette["accent"])

    def render_header(self, title: str, subtitle: str, online: bool) -> None:
        canvas = self.canvas
        w = canvas.width
        canvas.fill_rect(0, 0, w, 28, self.palette["surface"])
        canvas.text(self.font, 8, 7, title, self.palette["text"], 1)
        canvas.text(
            self.font,
            w - 8 - self.font.text_width(subtitle, 1),
            7,
            subtitle,
            self.palette["text_dim"],
            1,
        )
        dot_color = self.palette["success"] if online else self.palette["danger"]
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx * dx + dy * dy <= 9:
                    canvas.pixel(8 - 12 + dx, 14 + dy, dot_color)

    def render_footer(self, pages: list[str], current: int,
                       seconds_left: int) -> None:
        canvas = self.canvas
        w, h = canvas.width, canvas.height
        y = h - 22
        canvas.fill_rect(0, y, w, 22, self.palette["surface"])
        dot_x = 8
        for i, _ in enumerate(pages):
            color = self.palette["accent"] if i == current else self.palette["text_muted"]
            canvas.fill_rect(dot_x, y + 8, 8, 8, color)
            dot_x += 14
        cd = f"{seconds_left}s"
        canvas.text(
            self.font,
            w - 8 - self.font.text_width(cd, 1),
            y + 7,
            cd,
            self.palette["text_dim"],
            1,
        )

    # ----- pages -----

    def render_status(self, snap: dict[str, Any]) -> None:
        canvas = self.canvas
        w, h = canvas.width, canvas.height
        canvas.clear(self.palette["bg"])

        header_h = 28
        footer_h = 22
        card_pad = 6
        card_y = header_h + card_pad

        avail_h = h - header_h - footer_h - 2 * card_pad
        card_w = (w - 3 * card_pad) // 2
        card_h = (avail_h - card_pad) // 2

        positions = [
            (card_pad, card_y),
            (card_pad * 2 + card_w, card_y),
            (card_pad, card_y + card_h + card_pad),
            (card_pad * 2 + card_w, card_y + card_h + card_pad),
        ]

        cpu = snap["cpu"]
        self._draw_percent_card(
            *positions[0], card_w, card_h,
            "CPU", cpu.get("percent", 0),
            extra=f"{len(cpu.get('per_core', []))} cores @ {cpu.get('freq_mhz', 0):.0f}MHz",
            color=self.palette["cpu"],
        )

        mem = snap["memory"]
        self._draw_percent_card(
            *positions[1], card_w, card_h,
            "MEMORY", mem.get("percent", 0),
            extra=_fmt_bytes(mem.get("used")) + " / " + _fmt_bytes(mem.get("total")),
            color=self.palette["memory"],
        )

        self.layout_card(*positions[2], card_w, card_h)
        canvas.text(self.font, positions[2][0] + 10, positions[2][1] + 8,
                     "DISKS", self.palette["text_dim"], 1)
        yy = positions[2][1] + 24
        for disk in snap.get("disks", [])[:3]:
            canvas.text(self.font, positions[2][0] + 10, yy,
                         f"{disk['mount']}", self.palette["text"], 1)
            pct_text = f"{disk.get('percent', 0):.0f}%"
            canvas.text(
                self.font,
                positions[2][0] + card_w - 10 - self.font.text_width(pct_text, 1),
                yy,
                pct_text,
                self.palette["disk"],
                1,
            )
            self.draw_progress_bar(
                positions[2][0] + 10, yy + 12,
                card_w - 20, 4,
                disk.get("percent", 0),
                self.palette["disk"], self.palette["surface_alt"],
            )
            yy += 22

        self.layout_card(*positions[3], card_w, card_h)
        canvas.text(self.font, positions[3][0] + 10, positions[3][1] + 8,
                     "NETWORK", self.palette["text_dim"], 1)
        net = snap["network"]
        canvas.text(self.font, positions[3][0] + 10, positions[3][1] + 24,
                     f"UP  {_fmt_rate(net.get('up_kbps', 0))}",
                     self.palette["network"], 1)
        canvas.text(self.font, positions[3][0] + 10, positions[3][1] + 40,
                     f"DOWN  {_fmt_rate(net.get('down_kbps', 0))}",
                     self.palette["network"], 1)

        temps = snap.get("temperatures", [])
        cpu_temp = cpu.get("temp")
        if cpu_temp is not None:
            label = "CPU TEMP"
            color = _temp_color(cpu_temp, self.palette)
            canvas.text(self.font, positions[3][0] + 10, positions[3][1] + 60,
                         label, self.palette["text_dim"], 1)
            tc = _fmt_temp(cpu_temp, "C")
            canvas.text(
                self.font,
                positions[3][0] + card_w - 10 - self.font.text_width(tc, 1),
                positions[3][1] + 60,
                tc,
                color,
                1,
            )
        upt = _fmt_uptime(snap.get("uptime_seconds"))
        canvas.text(self.font, positions[3][0] + 10, positions[3][1] + 80,
                     f"UP  {upt}", self.palette["text"], 1)
        canvas.text(
            self.font,
            positions[3][0] + card_w - 10 - self.font.text_width(f"{snap.get('processes', 0)} PROC", 1),
            positions[3][1] + 80,
            f"{snap.get('processes', 0)} PROC",
            self.palette["text_dim"],
            1,
        )

    def _draw_percent_card(self, x: int, y: int, w: int, h: int,
                            title: str, value: float, extra: str,
                            color) -> None:
        self.layout_card(x, y, w, h)
        self.canvas.text(self.font, x + 10, y + 8, title, self.palette["text_dim"], 1)
        big = f"{value:.0f}%"
        self.canvas.text(self.font, x + 10, y + 24, big, color, 3)
        self.draw_progress_bar(x + 10, y + h - 20, w - 20, 6,
                                value, color, self.palette["surface_alt"])
        self.canvas.text(
            self.font,
            x + w - 10 - self.font.text_width(extra, 1),
            y + 8,
            extra,
            self.palette["text_dim"],
            1,
        )

    def render_cpu(self, snap: dict[str, Any]) -> None:
        canvas = self.canvas
        w = canvas.width
        canvas.clear(self.palette["bg"])
        cpu = snap["cpu"]
        cores = cpu.get("per_core", [])
        col_h = 16
        col_w = max(8, (w - 24) // max(1, len(cores)))
        y = 60
        for i, val in enumerate(cores):
            x = 12 + i * col_w
            canvas.fill_rect(x, y, col_w - 4, col_h, self.palette["surface_alt"])
            fill = int((col_w - 4) * max(0, min(100, val)) / 100)
            canvas.fill_rect(x, y, fill, col_h, self.palette["cpu"])
        caption = f"{len(cores)} cores @ {cpu.get('freq_mhz', 0):.0f}MHz  load {cpu.get('load', [0])[0]:.2f}"
        canvas.text(self.font, 12, y + col_h + 12, caption, self.palette["text"], 1)
        if cpu.get("temp") is not None:
            canvas.text(self.font, 12, y + col_h + 32,
                         f"CPU TEMP  {_fmt_temp(cpu['temp'], 'C')}",
                         _temp_color(cpu["temp"], self.palette), 1)
        for i, temp in enumerate(snap.get("temperatures", [])[:5]):
            ty = y + col_h + 56 + i * 18
            label = temp["label"][:20]
            canvas.text(self.font, 12, ty, label, self.palette["text_dim"], 1)
            tc = _fmt_temp(temp["current"], "C")
            canvas.text(
                self.font,
                w - 12 - self.font.text_width(tc, 1),
                ty,
                tc,
                _temp_color(temp["current"], self.palette),
                1,
            )

    def render_memory(self, snap: dict[str, Any]) -> None:
        canvas = self.canvas
        w = canvas.width
        canvas.clear(self.palette["bg"])
        mem = snap["memory"]
        canvas.text(self.font, 12, 40, "MEMORY",
                     self.palette["text_dim"], 1)
        pct = mem.get("percent", 0)
        self.draw_progress_bar(12, 56, w - 24, 12, pct,
                                self.palette["memory"], self.palette["surface_alt"])
        label = f"{_fmt_bytes(mem.get('used'))} / {_fmt_bytes(mem.get('total'))}  ({pct:.1f}%)"
        canvas.text(self.font, 12, 76, label, self.palette["memory"], 1)
        spct = mem.get("swap_percent", 0)
        canvas.text(self.font, 12, 110, "SWAP", self.palette["text_dim"], 1)
        self.draw_progress_bar(12, 126, w - 24, 12, spct,
                                self.palette["disk"], self.palette["surface_alt"])
        slabel = f"{_fmt_bytes(mem.get('swap_used'))} / {_fmt_bytes(mem.get('swap_total'))}  ({spct:.1f}%)"
        canvas.text(self.font, 12, 146, slabel, self.palette["disk"], 1)
        canvas.text(self.font, 12, 180,
                     f"{snap.get('processes', 0)} processes",
                     self.palette["text"], 1)
        canvas.text(self.font, 12, 200,
                     f"UP {_fmt_uptime(snap.get('uptime_seconds'))}",
                     self.palette["text_dim"], 1)

    def render_network(self, snap: dict[str, Any]) -> None:
        canvas = self.canvas
        w = canvas.width
        canvas.clear(self.palette["bg"])
        net = snap["network"]
        canvas.text(self.font, 12, 40, "UPLOAD",
                     self.palette["text_dim"], 1)
        canvas.text(self.font, 12, 56,
                     _fmt_rate(net.get("up_kbps", 0)),
                     self.palette["network"], 3)
        canvas.text(self.font, 12, 100, "DOWNLOAD",
                     self.palette["text_dim"], 1)
        canvas.text(self.font, 12, 116,
                     _fmt_rate(net.get("down_kbps", 0)),
                     self.palette["network"], 3)
        canvas.text(self.font, 12, 170,
                     f"Total sent: {_fmt_bytes(net.get('bytes_sent'))}",
                     self.palette["text"], 1)
        canvas.text(self.font, 12, 190,
                     f"Total recv: {_fmt_bytes(net.get('bytes_recv'))}",
                     self.palette["text"], 1)
        for i, iface in enumerate(net.get("interfaces", [])[:4]):
            ty = 220 + i * 18
            status = "UP" if iface.get("is_up") else "DOWN"
            color = self.palette["success"] if iface.get("is_up") else self.palette["danger"]
            canvas.text(self.font, 12, ty, iface["name"][:14],
                         self.palette["text_dim"], 1)
            canvas.text(
                self.font,
                w - 12 - self.font.text_width(status, 1),
                ty,
                status,
                color,
                1,
            )

    def render_disks(self, snap: dict[str, Any]) -> None:
        canvas = self.canvas
        w = canvas.width
        canvas.clear(self.palette["bg"])
        disks = snap.get("disks", [])
        if not disks:
            canvas.text(self.font, 12, 40, "No disks",
                         self.palette["text_muted"], 1)
            return
        y = 40
        for d in disks[:6]:
            canvas.text(self.font, 12, y,
                         f"{d['mount']}", self.palette["text"], 1)
            used = _fmt_bytes(d.get("used"))
            total = _fmt_bytes(d.get("total"))
            label = f"{used} / {total}"
            canvas.text(
                self.font,
                w - 12 - self.font.text_width(label, 1),
                y,
                label,
                self.palette["text_dim"],
                1,
            )
            self.draw_progress_bar(
                12, y + 14, w - 24, 6,
                d.get("percent", 0),
                self.palette["disk"],
                self.palette["surface_alt"],
            )
            y += 32

    def render_info(self, snap: dict[str, Any]) -> None:
        canvas = self.canvas
        w = canvas.width
        canvas.clear(self.palette["bg"])
        lines = [
            ("Hostname", snap.get("hostname", "")),
            ("OS", snap.get("os", "")),
            ("Kernel", snap.get("kernel", "")),
            ("Boot time", time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(snap.get("boot_time", 0)),
            ) if snap.get("boot_time") else "—"),
            ("Uptime", _fmt_uptime(snap.get("uptime_seconds"))),
            ("Processes", f"{snap.get('processes', 0)}"),
        ]
        y = 40
        for k, v in lines:
            canvas.text(self.font, 12, y, k, self.palette["text_dim"], 1)
            text_w = self.font.text_width(str(v), 1)
            canvas.text(
                self.font,
                w - 12 - text_w,
                y,
                str(v),
                self.palette["text"],
                1,
            )
            y += 24

    def render_offline(self, last: dict[str, Any] | None) -> None:
        canvas = self.canvas
        w = canvas.width
        text = "OFFLINE"
        bw = self.font.text_width(text, 1) + 16
        bh = 18
        x = w - bw - 8
        y = 32
        self.draw_filled_round_rect(x, y, bw, bh,
                                     self.palette["danger"], 3)
        canvas.text(self.font, x + 8, y + 3, text,
                     (255, 255, 255), 1)


# ---------------------------------------------------------------------------
# Config + main loop
# ---------------------------------------------------------------------------


def parse_config(path: str) -> dict[str, Any]:
    defaults = {
        "theme": "midnight",
        "accent": "",
        "refresh": 2,
        "temp_unit": "C",
        "rotate": 0,
        "screen_inches": 0,
        "page_interval": 10,
        "pages": ["status"],
    }
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            defaults.update({k: v for k, v in data.items() if k in defaults})
    except (FileNotFoundError, json.JSONDecodeError) as err:
        _LOGGER.warning("Config load failed (%s); using defaults", err)
    return defaults


def _resolve_page_renderers(renderer: PageRenderer) -> dict[str, Callable[[dict[str, Any]], None]]:
    return {
        "status": renderer.render_status,
        "cpu": renderer.render_cpu,
        "memory": renderer.render_memory,
        "network": renderer.render_network,
        "disks": renderer.render_disks,
        "info": renderer.render_info,
    }


def _read_text(path: str) -> str:
    """Read a /proc or /sys file, returning a string for logging."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read().strip()


def _list_dev_fb() -> str:
    """List /dev/fb* entries via glob (avoids depending on `ls`)."""
    import glob
    entries = sorted(glob.glob("/dev/fb*"))
    if not entries:
        return "<no /dev/fb* nodes>"
    out: list[str] = []
    for path in entries:
        try:
            st = os.stat(path)
            out.append(f"{path} (mode={oct(st.st_mode)} uid={st.st_uid} "
                       f"gid={st.st_gid} dev={oct(st.st_rdev)})")
        except OSError as err:
            out.append(f"{path} <stat failed: {err}>")
    return "\n".join(out)


async def run(args: argparse.Namespace) -> None:
    """Entry point dispatched on --dump-png vs. real fb0."""
    cfg = parse_config(args.config)
    palette = resolve_palette(cfg["theme"], cfg.get("accent") or None)
    font = load_font(16)

    canvas: _CanvasProtocol
    if args.dump_png:
        # Headless preview mode — render into a PIL image and dump to PNG.
        width = args.width or 1280
        height = args.height or 720
        canvas = PILCanvas(width, height)
        _LOGGER.info("dump-png mode: %dx%d -> %s", width, height, args.dump_png)
    else:
        fb = FrameBuffer(args.fb_device)
        try:
            fb.open()
        except Exception as err:
            # /dev/fb0 open failed. This happens when the add-on container
            # lacks the cgroup device permissions, when the host's fb driver
            # is write-only (efifb), or when the device node is orphaned
            # (driver not loaded). Collect as much diagnostic detail as we
            # can before falling back to headless PNG mode — the integration
            # user can then attach the Log tab to a GitHub issue and we can
            # see exactly why without SSH-ing into HAOS.
            _LOGGER.error(
                "Cannot open %s: %s (errno=%s). Falling back to headless PNG "
                "output. Diagnostic dump follows:",
                fb.device, err, getattr(err, "errno", "?"),
            )
            for label, fn in (
                ("uid/gid", lambda: f"uid={os.getuid()} gid={os.getgid()}"),
                ("cgroup", lambda: _read_text("/proc/self/cgroup")),
                ("device cgroup allow",
                 lambda: _read_text("/sys/fs/cgroup/devices.allow")),
                ("ls /dev/fb*",
                 lambda: "\n".join(_read_text("/dev").splitlines()) if False
                              else _list_dev_fb()),
                ("/proc/fb", lambda: _read_text("/proc/fb")),
            ):
                try:
                    _LOGGER.error("  %s: %s", label, fn())
                except Exception as diag_err:  # noqa: BLE001
                    _LOGGER.error("  %s: <unavailable: %s>", label, diag_err)

            # Switch to headless mode and dump frames to /share so the user
            # can at least see the dashboard rendered correctly while we
            # sort the cgroup / driver issue out.
            width = cfg.get("fb_width") or 1024
            height = cfg.get("fb_height") or 768
            args.dump_png = "/share/haos_fb/snapshot.png"
            try:
                os.makedirs(os.path.dirname(args.dump_png), exist_ok=True)
            except OSError as mk_err:
                _LOGGER.error("Cannot create %s: %s",
                              os.path.dirname(args.dump_png), mk_err)
            canvas = PILCanvas(width, height)
            _LOGGER.warning(
                "Running in headless PNG fallback mode. Frames will be "
                "dumped to %s; tail the Log tab for real-time updates.",
                args.dump_png,
            )
            args.headless_loop = True
            _LOGGER.info("dump-png fallback: %dx%d -> %s",
                         width, height, args.dump_png)
        else:
            info = fb.info
            _LOGGER.info(
                "fb0 opened: %dx%d, %d bpp, stride=%d",
                info.width, info.height, info.bpp, info.stride,
            )
            canvas = fb

    renderer = PageRenderer(canvas, font, palette)
    pages = cfg.get("pages") or ["status"]
    page_renderers = _resolve_page_renderers(renderer)
    active_pages = [p for p in pages if p in page_renderers]
    if not active_pages:
        active_pages = ["status"]

    refresh = max(1, int(cfg.get("refresh", 2)))
    page_interval = max(0, int(cfg.get("page_interval", 10)))
    base_url = os.environ.get("SUPERVISOR_URL", "http://supervisor/core/api")
    token = os.environ.get("SUPERVISOR_TOKEN", "")

    current_page = 0
    page_started = time.time()

    # In --dump-png mode skip the HA client entirely; use synthetic data so
    # the preview works on a dev machine with no Home Assistant reachable.
    if args.dump_png and (args.synthetic or not token):
        snapshots: list[dict[str, Any]] = [
            _make_synthetic_snapshot(canvas.width, canvas.height)
            for _ in range(max(1, args.frames))
        ]
        _render_pngs(renderer, snapshots, active_pages, page_interval,
                     args.dump_png, args.frames)
        return

    async with HAClient(base_url, token, timeout=refresh * 2) as client:
        last_snapshot: dict[str, Any] | None = None
        first_render = True
        while True:
            snap = await client.fetch_snapshot()
            now = time.time()

            online = snap is not None
            if snap is not None:
                last_snapshot = snap
            elif last_snapshot is None:
                last_snapshot = _empty_snapshot(now)

            if page_interval > 0 and (now - page_started) > page_interval:
                current_page = (current_page + 1) % len(active_pages)
                page_started = now

            page_name = active_pages[current_page]
            clock_str = time.strftime("%H:%M:%S")
            title = "HAOS Dashboard"
            renderer.render_header(title, clock_str, online)
            page_renderers[page_name](last_snapshot)
            seconds_left = max(0, page_interval - int(now - page_started)) if page_interval else 0
            renderer.render_footer(active_pages, current_page, seconds_left)
            if not online:
                renderer.render_offline(last_snapshot)
            if getattr(args, "headless_loop", False):
                # Headless fallback: dump a PNG snapshot every refresh tick so
                # the user can preview the dashboard via /share without a real
                # framebuffer device being accessible.
                try:
                    canvas.save(args.dump_png)
                except OSError as dump_err:
                    _LOGGER.error("PNG dump to %s failed: %s",
                                  args.dump_png, dump_err)
            else:
                canvas.flush()

            if first_render:
                _LOGGER.info("First frame rendered (%s)", page_name)
                first_render = False

            await asyncio.sleep(refresh)


def _empty_snapshot(now: float) -> dict[str, Any]:
    return {
        "cpu": {"percent": 0, "per_core": [], "load": [0, 0, 0],
                 "freq_mhz": 0, "temp": None, "logical_cores": 0, "physical_cores": 0},
        "memory": {"percent": 0, "used": 0, "total": 0, "free": 0,
                    "swap_percent": 0, "swap_used": 0, "swap_total": 0},
        "disks": [],
        "network": {"interfaces": [], "bytes_sent": 0, "bytes_recv": 0,
                     "up_kbps": 0, "down_kbps": 0},
        "temperatures": [],
        "processes": 0,
        "uptime_seconds": 0,
        "boot_time": 0,
        "hostname": "",
        "os": "",
        "kernel": "",
        "ts": now,
    }


def _render_pngs(renderer: PageRenderer,
                  snapshots: list[dict[str, Any]],
                  active_pages: list[str],
                  page_interval: int,
                  out_path: str,
                  frames: int) -> None:
    """Render --frames PNG frames in --dump-png mode.

    Cycles through ``active_pages`` like the live loop, writing ``out_path``
    for each frame. If ``out_path`` ends in ``%d.png`` a numbered sequence
    is produced; otherwise every frame overwrites ``out_path``.
    """
    is_sequence = "%d" in out_path
    if not is_sequence and frames > 1:
        _LOGGER.warning(
            "out_path has no %%d placeholder; all %d frames will overwrite it",
            frames,
        )

    title = "HAOS Dashboard (preview)"
    online = True
    start = time.time()
    for i, snap in enumerate(snapshots):
        current_page = i % len(active_pages)
        page_name = active_pages[current_page]
        now = start + i
        clock_str = time.strftime("%H:%M:%S", time.localtime(now))
        seconds_left = page_interval if page_interval else 0
        renderer.render_header(title, clock_str, online)
        page_fn = getattr(renderer, f"render_{page_name}", renderer.render_status)
        page_fn(snap)
        renderer.render_footer(active_pages, current_page, seconds_left)
        target = out_path.replace("%d", str(i)) if is_sequence else out_path
        assert isinstance(renderer.canvas, PILCanvas)
        renderer.canvas.save(target)
        _LOGGER.info("Wrote %s (%s)", target, page_name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HAOS Dashboard /dev/fb0 renderer (or PIL headless preview)",
    )
    parser.add_argument(
        "--config", default="/data/options.json",
        help="Path to the add-on options JSON file",
    )
    parser.add_argument(
        "--fb-device", default="/dev/fb0",
        help="Path to the Linux frame buffer device (real mode only)",
    )
    parser.add_argument(
        "--dump-png", default=None, metavar="PATH",
        help="Render to a PNG file instead of /dev/fb0. PATH may contain "
             "%%d for a numbered sequence (--frames N).",
    )
    parser.add_argument(
        "--width", type=int, default=0,
        help="Canvas width in --dump-png mode (default 1280)",
    )
    parser.add_argument(
        "--height", type=int, default=0,
        help="Canvas height in --dump-png mode (default 720)",
    )
    parser.add_argument(
        "--frames", type=int, default=1,
        help="Number of frames to render in --dump-png mode (default 1)",
    )
    parser.add_argument(
        "--synthetic", action="store_true",
        help="In --dump-png mode, use synthetic snapshot data instead of "
             "trying Home Assistant. Useful for dev work with no HA reachable.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()