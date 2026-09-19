"""HAOS Dashboard integration for Home Assistant.

Adapted from https://github.com/neon9809/haos . Strips the fnOS-only
FPK packaging / udev rules / CGI gateway / .neon-dash module system and keeps
only the system monitor and the /dev/fb0 display renderer (now shipped as a
HA Supervisor add-on so HA OS can drive a connected HDMI/VGA screen).

Provides:
  - System monitor sensors (CPU / memory / disk / network / temperature)
  - Binary sensor + switch for the companion display add-on
  - Options flow for refresh interval and temperature unit
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import FnOSDashboardCoordinator
from .info import async_collect_info

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Set up HAOS Dashboard from a config entry."""
    coordinator = FnOSDashboardCoordinator(hass, entry)

    # Collect one-shot HA / Supervisor / HAOS / add-on metadata BEFORE the
    # first refresh so the info sensor has its attributes on the very first
    # state write. Failures here are non-fatal -- the sensor still works with
    # whatever attributes came through.
    try:
        coordinator.meta = await async_collect_info(hass, include_counts=False)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("async_collect_info failed; info sensor will be partial", exc_info=True)
        coordinator.meta = None

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(f"Initial data fetch failed: {err}") from err

    # HA 2026+ recommendation: store per-entry state under hass.data[DOMAIN]
    # instead of touching ConfigEntry.runtime_data directly.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)