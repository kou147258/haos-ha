"""Collect HA Core / Supervisor / HAOS / integration / add-on metadata.

The info sensor surfaces a one-shot snapshot of everything we know about the
HA installation plus the running add-on. Counts (entities / devices /
integrations) are not part of ``async_collect_info`` -- they're refreshed
inside the coordinator's main tick.

Designed for Home Assistant 2026.8 and newer:
  * ``homeassistant.helpers.system_info.async_get_system_info`` returns the
    full picture (HA Core version, installation type, Supervisor info, HAOS
    info) in a single awaitable call.
  * ``entity_registry.async_get`` / ``device_registry.async_get`` are
    callback-style -- no await needed.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .const import ADDON_SLUG
from .addon import get_addon_info  # module-level so tests can patch it

_LOGGER = logging.getLogger(__name__)

# Module-level: read our own manifest.json once at import time.
# Doing this at module level (not inside an async function) avoids the
# blocking-I/O warnings HA emits when importlib or file IO runs on the
# event loop. The fallback covers the test-stub case where the manifest
# doesn't exist on disk.
_MANIFEST_PATH = Path(__file__).parent / "manifest.json"
try:
    with _MANIFEST_PATH.open(encoding="utf-8") as _fh:
        _INTEGRATION_VERSION: str = json.loads(_fh.read()).get("version", "unknown")
except (FileNotFoundError, OSError, ValueError):  # pragma: no cover
    _INTEGRATION_VERSION = "unknown"

_INTEGRATION_LOADED_AT: str = datetime.now(timezone.utc).isoformat()

# Compress long installation-type names for the short state string.
_SHORT_INSTALLATION = {
    "Home Assistant OS": "OS",
    "Home Assistant Container": "Container",
    "Home Assistant Core": "Core",
    "Home Assistant Supervised": "Supervised",
}


def _short_installation_type(full: str | None) -> str:
    """Compress 'Home Assistant OS' -> 'OS' for the short state string."""
    if not full:
        return ""
    return _SHORT_INSTALLATION.get(full, full)


def build_state_string(info: dict[str, Any]) -> str:
    """Compose the short state string for the info sensor.

    Examples:
        "2026.8.0 · OS · 234 entities"
        "2026.8.0 · Container · 234 entities"
        "2026.8.0 · — entities" (counts not yet available)
        "2026.8.0" (no installation type detected)
    """
    version = info.get("ha_core_version") or "?"
    short = info.get("ha_installation_type_short") or ""
    count = info.get("entity_count")
    count_part = f"{count} entities" if isinstance(count, int) else "— entities"
    if short:
        return f"{version} · {short} · {count_part}"
    return f"{version} · {count_part}"


def build_attributes(info: dict[str, Any]) -> dict[str, Any]:
    """Filter out None values from the info dict for clean HA attributes."""
    return {k: v for k, v in info.items() if v is not None}


async def async_collect_info(
    hass: Any,
    *,
    include_counts: bool = False,
) -> dict[str, Any]:
    """Collect one-shot HA / Supervisor / HAOS / add-on metadata.

    ``include_counts`` is False by default -- counts come from the coordinator's
    main tick so they update with the polling interval. Pass ``True`` when
    you want a single self-contained snapshot (e.g. from the diagnostics
    endpoint).
    """
    # Lazy imports keep unit tests happy: the conftest stubs only what the
    # integration actually touches, and homeassistant / system_info may not be
    # importable in the test env.
    from homeassistant.const import __version__ as _HA_VERSION
    from homeassistant.helpers.system_info import async_get_system_info

    info: dict[str, Any] = {
        # HA Core
        "ha_core_version": _HA_VERSION,
        "ha_installation_type": None,
        "ha_installation_type_short": "",
        "ha_arch": None,
        "ha_python_version": None,
        "ha_time_zone": None,
        "ha_location_name": None,
        "ha_docker": None,
        "ha_dev": None,
        # Supervisor + HAOS (filled below when hassio is present)
        "hassio": False,
        "supervisor_version": None,
        "supervisor_healthy": None,
        "supervisor_update_available": None,
        "haos_version": None,
        "haos_board": None,
        # This integration
        "integration_version": _INTEGRATION_VERSION,
        "integration_loaded_at": _INTEGRATION_LOADED_AT,
        # Companion add-on
        "addon_slug": ADDON_SLUG,
        "addon_version": None,
        "addon_state": None,
        # Counts (filled by coordinator tick)
        "entity_count": None,
        "device_count": None,
        "integration_count": None,
    }

    # ----- HA system info (one call covers Core + Supervisor + HAOS) -----
    try:
        sys_info = await async_get_system_info(hass)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("async_get_system_info failed; metadata will be partial", exc_info=True)
        sys_info = {}

    if isinstance(sys_info, dict):
        info["ha_core_version"] = sys_info.get("version") or info["ha_core_version"]
        full_inst = sys_info.get("installation_type")
        info["ha_installation_type"] = full_inst if isinstance(full_inst, str) else None
        info["ha_installation_type_short"] = _short_installation_type(
            info["ha_installation_type"]
        )
        info["ha_arch"] = sys_info.get("arch")
        info["ha_python_version"] = sys_info.get("python_version")
        info["ha_time_zone"] = sys_info.get("timezone")
        info["ha_docker"] = sys_info.get("docker")
        info["ha_dev"] = sys_info.get("dev")
        info["hassio"] = bool(sys_info.get("hassio"))

        sup = sys_info.get("supervisor")
        if isinstance(sup, dict):
            info["supervisor_version"] = sup.get("version")
            info["supervisor_healthy"] = sup.get("healthy")
            info["supervisor_update_available"] = sup.get("update_available")
        host = sys_info.get("host_os")
        if isinstance(host, dict):
            info["haos_version"] = host.get("version")
            info["haos_board"] = host.get("board")

    # ----- HA location name (not in system_info) -----
    try:
        loc = hass.config.location_name
        info["ha_location_name"] = loc if isinstance(loc, str) else None
    except Exception:  # noqa: BLE001
        info["ha_location_name"] = None

    # ----- Companion add-on (via Supervisor) -----
    try:
        addon_info = await get_addon_info(hass)
    except Exception:  # noqa: BLE001
        addon_info = None
    if isinstance(addon_info, dict):
        info["addon_version"] = addon_info.get("version")
        info["addon_state"] = addon_info.get("state")

    # ----- Counts (optional) -----
    if include_counts:
        info["entity_count"] = _safe_entity_count(hass)
        info["device_count"] = _safe_device_count(hass)
        info["integration_count"] = _safe_integration_count(hass)

    return info


def _safe_entity_count(hass: Any) -> int | None:
    """Count active entities via the state machine."""
    try:
        ids = hass.states.async_entity_ids()
        return len(ids) if ids is not None else None
    except Exception:  # noqa: BLE001
        return None


def _safe_device_count(hass: Any) -> int | None:
    """Count registered devices via the device registry."""
    try:
        reg = hass.helpers.device_registry.async_get(hass)
        return len(reg.devices) if reg is not None else None
    except Exception:  # noqa: BLE001
        return None


def _safe_integration_count(hass: Any) -> int | None:
    """Count loaded integrations via the config components tuple."""
    try:
        comps = hass.config.components
        return len(comps) if comps is not None else None
    except Exception:  # noqa: BLE001
        return None