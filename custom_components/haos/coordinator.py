"""Data update coordinator for HAOS Dashboard.

Polls psutil for system stats and exposes a JSON snapshot. The same snapshot
is consumed by HA sensor entities and the companion /dev/fb0 add-on.

Heavy lifting lives in `_collect_snapshot` which runs in the executor — every
psutil call is blocking I/O and must not run on the event loop.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import psutil
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SKIP_FS_TYPES,
)
from .info import (
    _safe_device_count,
    _safe_entity_count,
    _safe_integration_count,
)

_LOGGER = logging.getLogger(__name__)


class FnOSDashboardCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that snapshots system stats for the integration and add-on."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        scan_interval = entry.options.get("refresh_interval")
        if not isinstance(scan_interval, (int, float)):
            scan_interval = DEFAULT_SCAN_INTERVAL.total_seconds()
        scan_interval = max(MIN_SCAN_INTERVAL, min(MAX_SCAN_INTERVAL, int(scan_interval)))

        self.config_entry = entry
        self._last_net: psutil._common.snetio | None = None
        self._last_net_ts: float | None = None
        self._cpu_sample_started: bool = False
        # Populated by ``__init__`` in this package after ``async_collect_info``
        # runs. Entity platforms read this to merge one-shot metadata with
        # the live counts that come from ``_async_update_data``.
        self.meta: dict[str, Any] | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=DEFAULT_SCAN_INTERVAL.__class__(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch a fresh snapshot.

        psutil work runs in the executor (blocking I/O). The HA registry /
        state-machine counts are filled in on the event loop afterwards --
        ``async_get`` is a @callback and registry dict access is cheap, but
        we still want hass reads to happen on the main loop thread.
        """
        try:
            snapshot = await self.hass.async_add_executor_job(self._collect_snapshot)
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Snapshot collection failed: {err}") from err
        snapshot["counts"] = {
            "entity": _safe_entity_count(self.hass),
            "device": _safe_device_count(self.hass),
            "integration": _safe_integration_count(self.hass),
        }
        return snapshot

    def _collect_snapshot(self) -> dict[str, Any]:
        """Build a JSON-serializable snapshot of system stats.

        Mirrors the JSON shape the original haos backend exposed at
        /api/status so the add-on renderer can reuse the same parsing code
        with minimal changes.
        """
        now = time.time()

        # First call returns 0.0 for cpu_percent — prime it once and report
        # 0 on the very first tick instead of misleading the user.
        if not self._cpu_sample_started:
            psutil.cpu_percent(interval=None)
            psutil.cpu_percent(interval=None, percpu=True)
            self._cpu_sample_started = True

        cpu_percent = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        load = _safe_loadavg()
        cpu_freq = psutil.cpu_freq()
        cpu_temp = _read_cpu_temp()
        cpu_count_logical = psutil.cpu_count(logical=True) or 1
        cpu_count_physical = psutil.cpu_count(logical=False) or 1

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        disks = _collect_disks()

        net = psutil.net_io_counters()
        net_if_stats = psutil.net_if_stats()
        net_if = [
            {
                "name": name,
                "is_up": stats.isup,
                "speed_mbps": stats.speed,
                "mtu": stats.mtu,
            }
            for name, stats in net_if_stats.items()
        ]

        up_kbps, down_kbps = _network_rate(net, self._last_net, self._last_net_ts, now)
        self._last_net = net
        self._last_net_ts = now

        temps = _collect_temperatures()

        boot_time = psutil.boot_time()
        uname = _safe_uname()

        return {
            "ts": now,
            "boot_time": boot_time,
            "uptime_seconds": now - boot_time,
            "hostname": uname["node"],
            "os": uname["os"],
            "kernel": uname["release"],
            "processes": len(psutil.pids()),
            "cpu": {
                "percent": cpu_percent,
                "per_core": per_core,
                "load": load,
                "freq_mhz": cpu_freq.current if cpu_freq else 0,
                "temp": cpu_temp,
                "logical_cores": cpu_count_logical,
                "physical_cores": cpu_count_physical,
            },
            "memory": {
                "percent": mem.percent,
                "used": mem.used,
                "total": mem.total,
                "free": mem.available,
                "swap_percent": swap.percent,
                "swap_used": swap.used,
                "swap_total": swap.total,
            },
            "disks": disks,
            "network": {
                "interfaces": net_if,
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
                "packets_sent": net.packets_sent,
                "packets_recv": net.packets_recv,
                "up_kbps": up_kbps,
                "down_kbps": down_kbps,
            },
            "temperatures": temps,
        }


def _safe_loadavg() -> list[float]:
    """Return 1/5/15min load average, or zeros on unsupported platforms."""
    try:
        return [round(x, 2) for x in psutil.getloadavg()]
    except (OSError, AttributeError):
        return [0.0, 0.0, 0.0]


def _safe_uname() -> dict[str, str]:
    """Best-effort platform info without raising on exotic environments."""
    try:
        uname = psutil.uname()
        return {
            "system": uname.system,
            "node": uname.node,
            "release": uname.release,
            "version": uname.version,
            "os": f"{uname.system} {uname.release}",
        }
    except Exception:  # noqa: BLE001
        return {"system": "unknown", "node": "unknown", "release": "", "version": "", "os": "unknown"}


def _collect_disks() -> list[dict[str, Any]]:
    """List real disks, skipping virtual / pseudo filesystems."""
    disks: list[dict[str, Any]] = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype in SKIP_FS_TYPES:
            continue
        if part.mountpoint in ("/dev", "/run", "/boot/efi"):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        disks.append({
            "mount": part.mountpoint,
            "device": part.device,
            "fstype": part.fstype,
            "total": int(usage.total),
            "used": int(usage.used),
            "free": int(usage.free),
            "percent": float(usage.percent),
        })
    return disks


def _collect_temperatures() -> list[dict[str, Any]]:
    """Read all temperature sensors via psutil (Linux / macOS only)."""
    temps: list[dict[str, Any]] = []
    if not hasattr(psutil, "sensors_temperatures"):
        return temps
    try:
        sensors = psutil.sensors_temperatures(fahrenheit=False)
    except Exception:  # noqa: BLE001
        return temps
    for group, entries in sensors.items():
        for entry in entries:
            temps.append({
                "label": entry.label or group,
                "group": group,
                "current": float(entry.current),
                "high": float(entry.high) if entry.high else None,
                "critical": float(entry.critical) if entry.critical else None,
            })
    return temps


def _network_rate(
    current: psutil._common.snetio,
    previous: psutil._common.snetio | None,
    previous_ts: float | None,
    now: float,
) -> tuple[float, float]:
    """Compute instantaneous up/down KB/s; zeros when no prior sample exists."""
    if previous is None or previous_ts is None:
        return 0.0, 0.0
    dt = now - previous_ts
    if dt <= 0:
        return 0.0, 0.0
    up = (current.bytes_sent - previous.bytes_sent) / dt / 1024
    down = (current.bytes_recv - previous.bytes_recv) / dt / 1024
    return max(0.0, up), max(0.0, down)


def _read_cpu_temp() -> float | None:
    """Try a few common Linux sysfs locations, then psutil, then give up.

    On Windows / macOS this returns None — sensors_temperatures entity
    gracefully stays unknown instead of fabricating values.
    """
    for path in (
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/devices/virtual/thermal/thermal_zone0/temp",
    ):
        try:
            with open(path, encoding="utf-8") as fh:
                return round(int(fh.read().strip()) / 1000.0, 1)
        except (FileNotFoundError, ValueError, OSError):
            continue
    if not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        sensors = psutil.sensors_temperatures(fahrenheit=False)
    except Exception:  # noqa: BLE001
        return None
    if not sensors:
        return None
    for label in ("coretemp", "k10temp", "zenpower", "acpitz", "cpu_thermal"):
        if label in sensors and sensors[label]:
            return float(sensors[label][0].current)
    first = next(iter(sensors.values()))
    return float(first[0].current) if first else None