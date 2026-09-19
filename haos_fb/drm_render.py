"""DRM/KMS renderer for HAOS Dashboard Display.

This module implements a Canvas-compatible drawable that writes to
``/dev/dri/card0`` via the Linux DRM subsystem instead of the legacy
``/dev/fb0`` framebuffer. Why this exists:

- ``/dev/fb0`` (efifb / vesafb / simplefb) maps the framebuffer as a
  kernel I/O memory region via ``vm_iomap_memory``.
- Recent Linux kernels (6.x) reject that mmap path inside unprivileged
  user-namespace containers even when the container has
  ``CAP_SYS_RAWIO`` + ``full_access: true`` granted by Supervisor — the
  ``lsm_file_mprotect`` / kernel-I/O-memory LSM hook refuses the mmap
  with ``EINVAL``.
- amdgpu / nouveau / i915 expose a modern path via ``/dev/dri/card0``
  using the **DRM dumb buffer** API. The dumb buffer's mmap is a
  normal anonymous page-cache mapping (not an I/O-memory remap), so
  it works inside the container.

The flow is:

1. ``drmOpen("/dev/dri/card0")`` — open the DRM device.
2. ``drmModeGetResources`` + ``drmModeGetConnector`` — find the first
   connected output and its preferred mode.
3. ``DRM_IOCTL_MODE_CREATE_DUMB`` — allocate a GPU buffer of width ×
   height × 32bpp.
4. ``DRM_IOCTL_MODE_MAP_DUMB`` — get the mmap offset for that buffer.
5. ``mmap(fd, ..., offset=offset)`` — map it into user space; this is
   the safe mmap path the container allows.
6. The renderer writes RGBA8888 into the mapped buffer.
7. On each frame flush, ``drmModeAddFB`` registers the buffer as a
   framebuffer object and ``drmModeSetCrtc`` swaps the display CRTC
   to point at it.

Limitations:

- Only the **first** connected connector is driven. Multi-head setups
  are out of scope (the HAOS Dashboard is single-display).
- 32 bpp only (XR24 / RGBA8888 little-endian). The legacy
  ``/dev/fb0`` path supports 16 / 32 bpp with arbitrary channel
  offsets via ``FBIOGET_FSCREENINFO``; for KMS we get one
  well-defined format.
- Requires ``libdrm`` (``apk add libdrm`` in the add-on image).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import fcntl
import logging
import mmap
import os
import struct
from dataclasses import dataclass
from typing import Any

_LOGGER = logging.getLogger("haos_fb.drm")


# ---------------------------------------------------------------------------
# libdrm ctypes bindings (only what we actually use).
# ---------------------------------------------------------------------------


class _LibDRM:
    """Lazy wrapper around libdrm.so.2."""

    def __init__(self) -> None:
        path = ctypes.util.find_library("drm") or "libdrm.so.2"
        try:
            self._lib = ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
        except OSError as exc:
            raise RuntimeError(
                f"Cannot load libdrm ({path}): {exc}. Make sure the "
                "add-on image has libdrm installed."
            ) from exc
        self._bind_signatures()

    # drm.h means drmMode means a bare int fd.
    def _bind_signatures(self) -> None:
        L = self._lib
        # int drmOpen(const char *name, const char *busid);
        L.drmOpen.restype = ctypes.c_int
        L.drmOpen.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        # int drmClose(int fd);
        L.drmClose.restype = ctypes.c_int
        L.drmClose.argtypes = [ctypes.c_int]
        # int drmIoctl(int fd, unsigned long request, void *arg);
        L.drmIoctl.restype = ctypes.c_int
        L.drmIoctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
        # drmModeResPtr drmModeGetResources(int fd);
        L.drmModeGetResources.restype = ctypes.c_void_p
        L.drmModeGetResources.argtypes = [ctypes.c_int]
        # drmModeConnectorPtr drmModeGetConnector(int fd, uint32_t connector_id);
        L.drmModeGetConnector.restype = ctypes.c_void_p
        L.drmModeGetConnector.argtypes = [ctypes.c_int, ctypes.c_uint32]
        # void drmModeFreeConnector(drmModeConnectorPtr ptr);
        L.drmModeFreeConnector.restype = None
        L.drmModeFreeConnector.argtypes = [ctypes.c_void_p]
        # drmModeEncoderPtr drmModeGetEncoder(int fd, uint32_t encoder_id);
        L.drmModeGetEncoder.restype = ctypes.c_void_p
        L.drmModeGetEncoder.argtypes = [ctypes.c_int, ctypes.c_uint32]
        # void drmModeFreeEncoder(drmModeEncoderPtr ptr);
        L.drmModeFreeEncoder.restype = None
        L.drmModeFreeEncoder.argtypes = [ctypes.c_void_p]
        # drmModeCrtcPtr drmModeGetCrtc(int fd, uint32_t crtc_id);
        L.drmModeGetCrtc.restype = ctypes.c_void_p
        L.drmModeGetCrtc.argtypes = [ctypes.c_int, ctypes.c_uint32]
        # void drmModeFreeCrtc(drmModeCrtcPtr ptr);
        L.drmModeFreeCrtc.restype = None
        L.drmModeFreeCrtc.argtypes = [ctypes.c_void_p]
        # int drmModeAddFB(int fd, uint32_t width, uint32_t height,
        #                  uint8_t depth, uint8_t bpp, uint32_t pitch,
        #                  uint32_t bo_handle, uint32_t *buf_id);
        L.drmModeAddFB.restype = ctypes.c_int
        L.drmModeAddFB.argtypes = [
            ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
        ]
        # int drmModeRmFB(int fd, uint32_t buffer_id);
        L.drmModeRmFB.restype = ctypes.c_int
        L.drmModeRmFB.argtypes = [ctypes.c_int, ctypes.c_uint32]
        # int drmModeSetCrtc(int fd, uint32_t crtc_id, uint32_t buffer_id,
        #                    uint32_t x, uint32_t y, uint32_t *connectors,
        #                    int count, drmModeModeInfoPtr mode);
        L.drmModeSetCrtc.restype = ctypes.c_int
        L.drmModeSetCrtc.argtypes = [
            ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32), ctypes.c_int, ctypes.c_void_p,
        ]
        # int drmModeSetCrtc — Sets CPCI mode

    @property
    def lib(self):
        return self._lib


# DRM ioctl numbers we need (from <drm.h> means <drm_mode.h>).
_DRM_IOCTL_BASE = ord("d")
_DRM_COMMAND_BASE = 0x40
_DRM_IOWR_MODE_CREATE_DUMB = (
    0xC02064A2  # DRM_IOWR(DRM_COMMAND_BASE + DRM_MODE_CREATE_DUMB, ...)
    if False else None
)
# The exact values from include/uapi/drm/drm.h:
_DRM_IOCTL_MODE_CREATE_DUMB = 0xC02064A2  # _IOWR('d', 0xA2, struct drm_mode_create_dumb)
_DRM_IOCTL_MODE_MAP_DUMB = 0xC01064B3      # _IOWR('d', 0xB3, struct drm_mode_map_dumb)
_DRM_IOCTL_MODE_DESTROY_DUMB = 0xC00064B4  # _IOWR('d', 0xB4, struct drm_mode_destroy_dumb)


# drm_mode_create_dumb  — 32-bit width/height + 32-bit bpp + 32-bit flags.
# struct drm_mode_create_dumb {
#     __u32 height, width, bpp, flags;
#     __u32 handle, pitch, size;
# };
_DRM_MODE_CREATE_DUMB_FMT = "<IIIIIIII"
_DRM_MODE_MAP_DUMB_FMT = "<II"
_DRM_MODE_DESTROY_DUMB_FMT = "<I"


@dataclass
class _ModeInfo:
    """Subset of drmModeModeInfo we care about."""
    clock: int
    hdisplay: int
    vdisplay: int
    hsync_start: int
    hsync_end: int
    htotal: int
    vsync_start: int
    vsync_end: int
    vtotal: int
    vrefresh: int
    flags: int
    type_: int
    name: str

    def as_struct(self) -> bytes:
        # struct drm_mode_modeinfo {
        #     uint32_t clock; uint16_t hdisplay, hsync_start, hsync_end, htotal,
        #                    vdisplay, vsync_start, vsync_end, vtotal,
        #                    hskew, vscan;
        #     uint16_t vrefresh, hsync, vsync, flags, type;
        #     uint32_t name;
        # };
        # 4 + 11*2 + 5*2 + 4 = 4 + 32 = 36 bytes... actually it's:
        # 4 (clock) + 5*2 (h*) + 5*2 (v*) + 2 (hskew) + 2 (vscan) + 5*2 (vrefresh...) = 36
        name_int = 0
        if self.name:
            # Encode up to 4 chars into the u32 name field like libdrm does.
            encoded = self.name.encode("ascii", "replace")[:4].ljust(4, b"\x00")
            name_int = int.from_bytes(encoded, "little")
        return struct.pack(
            "<I"           # clock
            "5H"           # hdisplay hsync_start hsync_end htotal hskew (hskew=1)
            "5H"           # vdisplay vsync_start vsync_end vtotal vscan
            "H"            # vrefresh
            "5H"           # hsync vsync flags type — plus one pad
            "I",           # name
            self.clock,
            self.hdisplay, self.hsync_start, self.hsync_end, self.htotal, 0,
            self.vdisplay, self.vsync_start, self.vsync_end, self.vtotal, 0,
            self.vrefresh,
            0, 0, self.flags, self.type_, 0,
            name_int,
        )


class DRMCanvas:
    """DRM/KMS render surface with the same drawing API as FrameBuffer / PILCanvas.

    The container can ``mmap`` a dumb-buffer allocation without going
    through kernel I/O memory, so this path sidesteps the LSM hook that
    rejects ``/dev/fb0`` ``mmap`` from user-namespace containers.
    """

    width: int
    height: int

    def __init__(self, device: str = "/dev/dri/card0") -> None:
        self.device = device
        self._drm = _LibDRM()
        self._fd: int | None = None
        self._crtc_id: int = 0
        self._connector_id: int = 0
        self._old_fb_id: int = 0
        self._fb_id: int = 0
        self._bo_handle: int = 0
        self._size: int = 0
        self._pitch: int = 0
        self._mmap: mmap.mmap | None = None
        # Original mode we should restore on close.
        self._saved_crtc: ctypes.c_void_p | None = None
        self._mode_blob = b""

    # ----- canvas surface -----

    def open(self) -> None:
        # 1. open DRM device.
        self._fd = self._drm.lib.drmOpen(self.device.encode(), None)
        if self._fd < 0:
            raise OSError(errno.EIO,
                          f"drmOpen({self.device}) failed: {self._fd}")
        try:
            # 2. find resources + connector.
            res_p = self._drm.lib.drmModeGetResources(self._fd)
            if not res_p:
                raise RuntimeError("drmModeGetResources returned NULL")
            try:
                # C struct: count_connectors, *connectors, count_encoders, ...
                # We need the connector IDs.
                res_struct = _StructView(res_p, [
                    ("count_fbs", "I"), ("fbs", "P"),
                    ("count_crtcs", "I"), ("crtcs", "P"),
                    ("count_connectors", "I"), ("connectors", "P"),
                    ("count_encoders", "I"), ("encoders", "P"),
                    ("min_width", "I"), ("max_width", "I"),
                    ("min_height", "I"), ("max_height", "I"),
                ])
                conn_ids = self._read_uint32_array(
                    res_struct.connectors, res_struct.count_connectors
                )
                crtc_ids = self._read_uint32_array(
                    res_struct.crtcs, res_struct.count_crtcs
                )
            finally:
                # drmModeFreeResources not strictly required — pointers
                # remain valid until next call. Skip to avoid binding one
                # more symbol.
                pass

            connector_id, mode_info = self._pick_connector(conn_ids)
            if connector_id == 0:
                raise RuntimeError(
                    "No connected DRM output found — is anything plugged in?"
                )

            # 3. find a CRTC that can drive this connector.
            crtc_id = self._pick_crtc(connector_id, crtc_ids)
            if crtc_id == 0:
                raise RuntimeError(
                    f"No usable CRTC for connector {connector_id}"
                )

            self._crtc_id = crtc_id
            self._connector_id = connector_id
            self.width = mode_info.hdisplay
            self.height = mode_info.vdisplay
            self._mode_blob = mode_info.as_struct()

            # 4. allocate dumb buffer (32 bpp RGBA little-endian).
            create = struct.pack(
                _DRM_MODE_CREATE_DUMB_FMT,
                self.height, self.width, 32, 0,
                0, 0, 0,
            )
            create_buf = ctypes.create_string_buffer(create)
            rc = self._drm.lib.drmIoctl(
                self._fd, _DRM_IOCTL_MODE_CREATE_DUMB,
                ctypes.cast(create_buf, ctypes.c_void_p),
            )
            if rc != 0:
                raise OSError(errno.EIO,
                              f"DRM_IOCTL_MODE_CREATE_DUMB failed: {rc}")
            (_, _, _, _, handle, pitch, size, _) = struct.unpack(
                _DRM_MODE_CREATE_DUMB_FMT, create_buf.raw
            )
            self._bo_handle = handle
            self._pitch = pitch
            self._size = size

            # 5. mmap the dumb buffer (the safe path in containers).
            map_arg = struct.pack(_DRM_MODE_MAP_DUMB_FMT, self._bo_handle, 0)
            map_buf = ctypes.create_string_buffer(map_arg)
            rc = self._drm.lib.drmIoctl(
                self._fd, _DRM_IOCTL_MODE_MAP_DUMB,
                ctypes.cast(map_buf, ctypes.c_void_p),
            )
            if rc != 0:
                raise OSError(errno.EIO,
                              f"DRM_IOCTL_MODE_MAP_DUMB failed: {rc}")
            (handle_out, offset) = struct.unpack(
                _DRM_MODE_MAP_DUMB_FMT, map_buf.raw
            )
            if handle_out != self._bo_handle:
                raise RuntimeError("DRM_MAP_DUMB returned wrong handle")
            self._mmap = mmap.mmap(
                self._fd, size,
                prot=mmap.PROT_READ | mmap.PROT_WRITE,
                flags=mmap.MAP_SHARED,
                offset=offset,
            )

            # 6. register the buffer as an fb object on the CRTC.
            buf_id = ctypes.c_uint32(0)
            rc = self._drm.lib.drmModeAddFB(
                self._fd,
                ctypes.c_uint32(self.width),
                ctypes.c_uint32(self.height),
                ctypes.c_uint8(24),
                ctypes.c_uint8(32),
                ctypes.c_uint32(self._pitch),
                ctypes.c_uint32(self._bo_handle),
                ctypes.byref(buf_id),
            )
            if rc != 0:
                raise OSError(errno.EIO, f"drmModeAddFB failed: {rc}")
            self._fb_id = buf_id.value

            # 7. set the CRTC to display our framebuffer.
            conn_id_c = ctypes.c_uint32(self._connector_id)
            mode_p = ctypes.c_char_p(self._mode_blob)
            rc = self._drm.lib.drmModeSetCrtc(
                self._fd,
                ctypes.c_uint32(self._crtc_id),
                ctypes.c_uint32(self._fb_id),
                ctypes.c_uint32(0), ctypes.c_uint32(0),
                ctypes.byref(conn_id_c),
                ctypes.c_int(1),
                mode_p,
            )
            if rc != 0:
                raise OSError(errno.EIO,
                              f"drmModeSetCrtc initial failed: {rc}")

        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._fd is not None:
            try:
                if self._fb_id:
                    self._drm.lib.drmModeRmFB(
                        self._fd, ctypes.c_uint32(self._fb_id)
                    )
                    self._fb_id = 0
                if self._bo_handle:
                    destroy = struct.pack(
                        _DRM_MODE_DESTROY_DUMB_FMT, self._bo_handle
                    )
                    self._drm.lib.drmIoctl(
                        self._fd, _DRM_IOCTL_MODE_DESTROY_DUMB,
                        ctypes.cast(ctypes.c_char_p(destroy),
                                    ctypes.c_void_p),
                    )
                    self._bo_handle = 0
                self._drm.lib.drmClose(self._fd)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("DRMCanvas.close: %s", err)
            self._fd = None
        if self._mmap is not None:
            try:
                self._mmap.close()
            except Exception:  # noqa: BLE001
                pass
            self._mmap = None

    # ----- drawing primitives (RGBA8888 little-endian in the dumb buffer) -----

    def _write_pixel(self, offset: int, color: tuple[int, int, int]) -> None:
        if self._mmap is None:
            return
        # XR24 little-endian: byte 0 = B, byte 1 = G, byte 2 = R, byte 3 = X.
        # Many amdgpu fb layouts use this when depth=24, bpp=32.
        struct.pack_into("<I", self._mmap, offset,
                         (color[2] << 16) | (color[1] << 8) | color[0])

    def clear(self, color: tuple[int, int, int]) -> None:
        if self._mmap is None:
            return
        row_bytes = self._pitch
        pixels_per_row = self.width
        value = (color[2] << 16) | (color[1] << 8) | color[0]
        for y in range(self.height):
            offset = y * row_bytes
            struct.pack_into(f"<{pixels_per_row}I", self._mmap, offset,
                             *([value] * pixels_per_row))

    def pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        self._write_pixel(y * self._pitch + x * 4, color)

    def fill_rect(self, x: int, y: int, w: int, h: int,
                  color: tuple[int, int, int]) -> None:
        if self._mmap is None:
            return
        x2 = min(self.width, x + w)
        y2 = min(self.height, y + h)
        if x < 0:
            x = 0
        if y < 0:
            y = 0
        if x >= x2 or y >= y2:
            return
        value = (color[2] << 16) | (color[1] << 8) | color[0]
        cols = x2 - x
        for yy in range(y, y2):
            offset = yy * self._pitch + x * 4
            struct.pack_into(f"<{cols}I", self._mmap, offset,
                             *([value] * cols))

    def text(self, font, x: int, y: int, text_str: str, color,
             scale: int = 1) -> None:
        if self._mmap is None:
            return

        def _put(px: int, py: int, _c) -> None:
            self.pixel(px, py, color if isinstance(color, tuple) else color)

        font.draw(_put, x, y, text_str, color, scale)

    def flush(self) -> None:
        """Re-set the CRTC to point at our framebuffer (cheap page flip)."""
        if self._fd is None or self._fb_id == 0:
            return
        conn_id_c = ctypes.c_uint32(self._connector_id)
        mode_p = ctypes.c_char_p(self._mode_blob)
        # No-op flip when the CRTC is already on our fb, but cheap enough.
        rc = self._drm.lib.drmModeSetCrtc(
            self._fd,
            ctypes.c_uint32(self._crtc_id),
            ctypes.c_uint32(self._fb_id),
            ctypes.c_uint32(0), ctypes.c_uint32(0),
            ctypes.byref(conn_id_c),
            ctypes.c_int(1),
            mode_p,
        )
        if rc != 0:
            _LOGGER.debug("drmModeSetCrtc refresh failed: %s", rc)

    # ----- discovery helpers -----

    def _read_uint32_array(self, ptr_value: int, count: int) -> list[int]:
        """Read `count` uint32_t values from a C array at `ptr_value`."""
        if ptr_value == 0 or count <= 0:
            return []
        # ctypes.cast from int to POINTER(c_uint32) gives us an array view.
        arr_type = ctypes.c_uint32 * count
        arr = ctypes.cast(ptr_value, ctypes.POINTER(arr_type)).contents
        return list(arr)

    def _pick_connector(self, conn_ids: list[int]) -> tuple[int, _ModeInfo]:
        """Return (connector_id, preferred mode)."""
        for cid in conn_ids:
            conn_p = self._drm.lib.drmModeGetConnector(self._fd,
                                                       ctypes.c_uint32(cid))
            if not conn_p:
                continue
            try:
                conn = _StructView(conn_p, [
                    ("connector_id", "I"), ("encoder_id", "I"),
                    ("connector_type", "I"), ("connector_type_id", "I"),
                    ("connection", "I"), ("mm_width", "I"), ("mm_height", "I"),
                    ("subpixel", "I"),
                    ("count_modes", "I"), ("modes", "P"),
                    ("count_props", "I"), ("props", "P"),
                    ("count_encoders", "I"), ("encoders", "P"),
                ])
                if conn.connection != 1:  # DRM_MODE_CONNECTED
                    continue
                # First mode is the preferred mode by libdrm convention.
                if conn.count_modes == 0 or conn.modes == 0:
                    continue
                mode_arr = ctypes.cast(
                    conn.modes,
                    ctypes.POINTER(_ModeInfoC * conn.count_modes),
                ).contents
                m = mode_arr[0]
                info = _ModeInfo(
                    clock=m.clock,
                    hdisplay=m.hdisplay, vdisplay=m.vdisplay,
                    hsync_start=m.hsync_start, hsync_end=m.hsync_end,
                    htotal=m.htotal,
                    vsync_start=m.vsync_start, vsync_end=m.vsync_end,
                    vtotal=m.vtotal,
                    vrefresh=m.vrefresh,
                    flags=m.flags, type_=m.type_,
                    name=m.name[:4].decode("ascii", "replace").rstrip("\x00"),
                )
                return conn.connector_id, info
            finally:
                self._drm.lib.drmModeFreeConnector(conn_p)
        return 0, _ModeInfo(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "")

    def _pick_crtc(self, connector_id: int, crtc_ids: list[int]) -> int:
        """Return the first CRTC reachable through the connector's encoder."""
        conn_p = self._drm.lib.drmModeGetConnector(self._fd,
                                                   ctypes.c_uint32(connector_id))
        if not conn_p:
            return 0
        try:
            conn = _StructView(conn_p, [
                ("connector_id", "I"), ("encoder_id", "I"),
                ("connector_type", "I"), ("connector_type_id", "I"),
                ("connection", "I"), ("mm_width", "I"), ("mm_height", "I"),
                ("subpixel", "I"),
                ("count_modes", "I"), ("modes", "P"),
                ("count_props", "I"), ("props", "P"),
                ("count_encoders", "I"), ("encoders", "P"),
            ])
            if conn.encoder_id:
                enc_p = self._drm.lib.drmModeGetEncoder(
                    self._fd, ctypes.c_uint32(conn.encoder_id)
                )
                if enc_p:
                    try:
                        enc = _StructView(enc_p, [
                            ("encoder_id", "I"), ("encoder_type", "I"),
                            ("crtc_id", "I"), ("possible_crtcs", "I"),
                            ("possible_clones", "I"),
                        ])
                        if enc.crtc_id:
                            return enc.crtc_id
                    finally:
                        self._drm.lib.drmModeFreeEncoder(enc_p)
            # Fallback: any CRTC that intersects the connector's possible bitmask.
            if conn.count_encoders and conn.encoders:
                enc_ids = self._read_uint32_array(
                    conn.encoders, conn.count_encoders
                )
                for eid in enc_ids:
                    enc_p = self._drm.lib.drmModeGetEncoder(
                        self._fd, ctypes.c_uint32(eid)
                    )
                    if not enc_p:
                        continue
                    try:
                        enc = _StructView(enc_p, [
                            ("encoder_id", "I"), ("encoder_type", "I"),
                            ("crtc_id", "I"), ("possible_crtcs", "I"),
                            ("possible_clones", "I"),
                        ])
                        if enc.crtc_id:
                            return enc.crtc_id
                    finally:
                        self._drm.lib.drmModeFreeEncoder(enc_p)
        finally:
            self._drm.lib.drmModeFreeConnector(conn_p)
        return crtc_ids[0] if crtc_ids else 0


class _StructView:
    """Tiny helper: read C struct fields by name into Python attributes."""

    _FMT_SIZES = {"I": 4, "H": 2, "B": 1, "P": 8}

    def __init__(self, ptr_value: int, fields: list[tuple[str, str]]) -> None:
        offset = 0
        for name, fmt in fields:
            size = self._FMT_SIZES[fmt]
            raw = (ctypes.c_uint8 * size).from_address(ptr_value + offset)
            if fmt == "I":
                value = int.from_bytes(bytes(raw), "little")
            elif fmt == "H":
                value = int.from_bytes(bytes(raw), "little")
            elif fmt == "B":
                value = raw[0]
            elif fmt == "P":
                # Pointer: read as uintptr_t (8 bytes on amd64).
                value = int.from_bytes(bytes(raw), "little")
            else:
                raise ValueError(f"Unsupported field fmt {fmt}")
            setattr(self, name, value)
            offset += size


# Mirror of drmModeModeInfo for the inner `_pick_connector` reader.
class _ModeInfoC(ctypes.Structure):
    """Subset of drm_mode_modeinfo. Layout is described in _ModeInfo.as_struct."""
    _fields_ = [
        ("clock", ctypes.c_uint32),
        ("hdisplay", ctypes.c_uint16),
        ("hsync_start", ctypes.c_uint16),
        ("hsync_end", ctypes.c_uint16),
        ("htotal", ctypes.c_uint16),
        ("hskew", ctypes.c_uint16),
        ("vdisplay", ctypes.c_uint16),
        ("vsync_start", ctypes.c_uint16),
        ("vsync_end", ctypes.c_uint16),
        ("vtotal", ctypes.c_uint16),
        ("vscan", ctypes.c_uint16),
        ("vrefresh", ctypes.c_uint16),
        ("hsync", ctypes.c_uint16),
        ("vsync", ctypes.c_uint16),
        ("flags", ctypes.c_uint16),
        ("type", ctypes.c_uint16),
        ("name", ctypes.c_uint8 * 4),
    ]