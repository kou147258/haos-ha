"""Diagnostics support for HAOS Dashboard."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {"hostname"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for the config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    snapshot = coordinator.data or {}
    redacted = async_redact_data(snapshot, TO_REDACT)
    return {
        "entry": {
            "title": entry.title,
            "options": dict(entry.options),
        },
        "snapshot": redacted,
    }