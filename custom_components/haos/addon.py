"""Supervisor add-on helpers.

All calls go through the Supervisor HTTP API. They gracefully degrade to
``None`` / ``False`` when Supervisor isn't available (HA Core / Container
installs) so the integration still works without the display side.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import ADDON_SLUG

# aiohttp is bundled with Home Assistant but we import it lazily so unit
# tests that mock ``homeassistant.helpers.aiohttp_client`` don't need the
# real package installed.
try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

_SUPERVISOR_BASE = "http://supervisor"


def _supervisor_available(hass: HomeAssistant) -> bool:
    """Return True if the Supervisor token / API is reachable."""
    return "SUPERVISOR_TOKEN" in hass.config.as_dict()


def _supervisor_headers(hass: HomeAssistant) -> dict[str, str]:
    token = hass.config.as_dict().get("SUPERVISOR_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def addon_installed(hass: HomeAssistant) -> bool:
    """Return True if the companion add-on is registered with Supervisor."""
    if not _supervisor_available(hass) or aiohttp is None:
        return False
    try:
        session = async_get_clientsession(hass)
        async with session.get(
            f"{_SUPERVISOR_BASE}/addons/{ADDON_SLUG}/info",
            headers=_supervisor_headers(hass),
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status == 404:
                return False
            resp.raise_for_status()
            return True
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        _LOGGER.debug("Supervisor add-on lookup failed: %s", err)
        return False


async def get_addon_info(hass: HomeAssistant) -> dict[str, Any] | None:
    """Return the Supervisor add-on info dict or None if unavailable."""
    if not _supervisor_available(hass) or aiohttp is None:
        return None
    try:
        session = async_get_clientsession(hass)
        async with session.get(
            f"{_SUPERVISOR_BASE}/addons/{ADDON_SLUG}/info",
            headers=_supervisor_headers(hass),
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status == 404:
                return None
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", {})
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        _LOGGER.debug("Supervisor add-on info failed: %s", err)
        return None


async def async_start_addon(hass: HomeAssistant) -> bool:
    """Start the add-on. Returns True on success."""
    return await _post_addon(hass, "start")


async def async_stop_addon(hass: HomeAssistant) -> bool:
    """Stop the add-on. Returns True on success."""
    return await _post_addon(hass, "stop")


async def _post_addon(hass: HomeAssistant, action: str) -> bool:
    if not _supervisor_available(hass) or aiohttp is None:
        _LOGGER.debug("Supervisor not available; cannot %s add-on", action)
        return False
    try:
        session = async_get_clientsession(hass)
        async with session.post(
            f"{_SUPERVISOR_BASE}/addons/{ADDON_SLUG}/{action}",
            headers=_supervisor_headers(hass),
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            return resp.status == 200
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        _LOGGER.debug("Supervisor %s failed: %s", action, err)
        return False