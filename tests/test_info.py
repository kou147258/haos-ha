"""Tests for ``info.py`` -- HA Core / Supervisor / HAOS metadata collection."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.haos import info as info_mod
from custom_components.haos.info import (
    _short_installation_type,
    async_collect_info,
    build_attributes,
    build_state_string,
)


# ---------------------------------------------------------------------------
# Pure helpers (no HA involvement)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("full,short", [
    ("Home Assistant OS", "OS"),
    ("Home Assistant Container", "Container"),
    ("Home Assistant Core", "Core"),
    ("Home Assistant Supervised", "Supervised"),
    ("Custom Build", "Custom Build"),  # unknown → returned unchanged
])
def test_short_installation_type(full, short):
    assert _short_installation_type(full) == short


@pytest.mark.parametrize("value", [None, ""])
def test_short_installation_type_empty(value):
    assert _short_installation_type(value) == ""


def test_build_state_string_with_counts_and_short_type():
    info = {
        "ha_core_version": "2026.8.0",
        "ha_installation_type_short": "OS",
        "entity_count": 234,
    }
    assert build_state_string(info) == "2026.8.0 · OS · 234 entities"


def test_build_state_string_without_installation_type():
    info = {"ha_core_version": "2026.8.0", "entity_count": 5}
    assert build_state_string(info) == "2026.8.0 · 5 entities"


def test_build_state_string_without_counts():
    info = {"ha_core_version": "2026.8.0", "ha_installation_type_short": "Core"}
    assert build_state_string(info) == "2026.8.0 · Core · — entities"


def test_build_state_string_empty_core_version():
    info = {"entity_count": 1}
    assert build_state_string(info) == "? · 1 entities"


def test_build_attributes_strips_none():
    info = {
        "ha_core_version": "2026.8.0",
        "ha_installation_type": "Home Assistant OS",
        "haos_version": None,        # should be dropped
        "supervisor_version": None,  # should be dropped
        "addon_state": "started",
    }
    attrs = build_attributes(info)
    assert "haos_version" not in attrs
    assert "supervisor_version" not in attrs
    assert attrs["ha_core_version"] == "2026.8.0"
    assert attrs["addon_state"] == "started"


# ---------------------------------------------------------------------------
# Module-level: integration version read from manifest.json
# ---------------------------------------------------------------------------


def test_integration_version_read_from_manifest():
    # Manifest exists; version field should be a non-empty string.
    assert isinstance(info_mod._INTEGRATION_VERSION, str)
    assert info_mod._INTEGRATION_VERSION != "unknown"


def test_integration_loaded_at_is_iso_timestamp():
    # ISO 8601 string ending in +00:00 or Z.
    ts = info_mod._INTEGRATION_LOADED_AT
    assert "T" in ts
    assert ts.endswith(("+00:00", "Z"))


# ---------------------------------------------------------------------------
# async_collect_info -- integration with HA stubs
# ---------------------------------------------------------------------------


def _make_stub_hass(installation_type=None, *, hassio=False, supervisor=None,
                    host_os=None, location="Home", components=("haos",)):
    """Build a MagicMock hass that responds to the bits async_collect_info reads."""
    hass = MagicMock()
    hass._stub_system_info = {
        "installation_type": installation_type,
        "version": "2026.8.0",
        "hassio": hassio,
        "timezone": "UTC",
        "python_version": "3.14.0",
        "arch": "x86_64",
        "docker": False,
        "dev": False,
        "supervisor": supervisor,
        "host_os": host_os,
    }
    hass.config.location_name = location
    hass.config.components = components
    return hass


def test_async_collect_info_no_supervisor_container():
    """Container install: no Supervisor fields populated, but Core fields OK."""
    hass = _make_stub_hass(
        installation_type="Home Assistant Container",
        components=("haos", "frontend", "hassio"),
    )

    async def run():
        with patch.object(info_mod, "get_addon_info", AsyncMock(return_value=None)):
            return await async_collect_info(hass)
    info = asyncio.run(run())

    assert info["ha_core_version"] == "2026.8.0"
    assert info["ha_installation_type"] == "Home Assistant Container"
    assert info["ha_installation_type_short"] == "Container"
    assert info["haos_version"] is None
    assert info["supervisor_version"] is None
    assert info["hassio"] is False
    assert info["ha_location_name"] == "Home"


def test_async_collect_info_haos_with_supervisor():
    """HAOS install: Supervisor + HAOS fields populated from system_info."""
    hass = _make_stub_hass(
        installation_type="Home Assistant OS",
        hassio=True,
        supervisor={
            "version": "2026.08.0",
            "healthy": True,
            "update_available": False,
        },
        host_os={"version": "14.1", "board": "Generic x86-64"},
    )

    async def run():
        with patch.object(info_mod, "get_addon_info",
                          AsyncMock(return_value={"version": "1.0.0", "state": "started"})):
            return await async_collect_info(hass)
    info = asyncio.run(run())

    assert info["ha_installation_type_short"] == "OS"
    assert info["supervisor_version"] == "2026.08.0"
    assert info["supervisor_healthy"] is True
    assert info["supervisor_update_available"] is False
    assert info["haos_version"] == "14.1"
    assert info["haos_board"] == "Generic x86-64"
    assert info["addon_version"] == "1.0.0"
    assert info["addon_state"] == "started"
    assert info["addon_slug"] == "haos_fb"


def test_async_collect_info_unknown_installation_type():
    """Unknown / empty: empty short name, no crash."""
    hass = _make_stub_hass(installation_type="Unknown")

    async def run():
        with patch.object(info_mod, "get_addon_info", AsyncMock(return_value=None)):
            return await async_collect_info(hass)
    info = asyncio.run(run())

    assert info["ha_installation_type"] == "Unknown"
    # Unrecognised values pass through unchanged (matches ``Custom Build``
    # in the parametrised short-name test).
    assert info["ha_installation_type_short"] == "Unknown"


def test_async_collect_info_include_counts_calls_registry():
    """include_counts=True should hit hass.states + device_registry."""
    hass = _make_stub_hass(installation_type="Home Assistant OS", components=("a", "b"))
    hass.states.async_entity_ids = MagicMock(return_value=["s.x", "s.y", "s.z"])
    hass.helpers.device_registry.async_get = MagicMock(
        return_value=MagicMock(devices=["d1", "d2"])
    )

    async def run():
        with patch.object(info_mod, "get_addon_info", AsyncMock(return_value=None)):
            return await async_collect_info(hass, include_counts=True)
    info = asyncio.run(run())

    assert info["entity_count"] == 3
    assert info["device_count"] == 2
    assert info["integration_count"] == 2


def test_async_collect_info_handles_missing_counts_gracefully():
    """Counts accessors that raise should yield None, not blow up."""
    hass = _make_stub_hass(installation_type="Home Assistant OS")
    hass.states.async_entity_ids = MagicMock(side_effect=RuntimeError("boom"))
    hass.helpers.device_registry.async_get = MagicMock(
        side_effect=RuntimeError("registry gone")
    )

    async def run():
        with patch.object(info_mod, "get_addon_info", AsyncMock(return_value=None)):
            return await async_collect_info(hass, include_counts=True)
    info = asyncio.run(run())

    assert info["entity_count"] is None
    assert info["device_count"] is None


def test_async_collect_info_handles_addon_info_failure():
    """If get_addon_info raises, the rest of the info should still come back."""
    hass = _make_stub_hass(installation_type="Home Assistant OS")

    async def run():
        with patch.object(info_mod, "get_addon_info",
                          AsyncMock(side_effect=RuntimeError("supervisor dead"))):
            return await async_collect_info(hass)
    info = asyncio.run(run())

    assert info["addon_version"] is None
    assert info["addon_state"] is None
    assert info["ha_installation_type_short"] == "OS"


def test_async_collect_info_handles_system_info_failure():
    """If async_get_system_info raises, we get a partial dict, no crash."""
    hass = MagicMock()
    hass._stub_system_info = None  # forces the stub to raise

    async def run():
        with patch("homeassistant.helpers.system_info.async_get_system_info",
                   AsyncMock(side_effect=RuntimeError("nope"))), \
             patch.object(info_mod, "get_addon_info", AsyncMock(return_value=None)):
            return await async_collect_info(hass)

    # Patch the system_info module-level reference (the stub reads from
    # ``hass._stub_system_info`` only when present, so we need to clear it
    # AND make the stub raise).
    hass._stub_system_info = None
    with patch("homeassistant.helpers.system_info.async_get_system_info",
               AsyncMock(side_effect=RuntimeError("nope"))):
        info = asyncio.run(run())

    # Fallback values -- integration_version still resolved, ha_* fields
    # stay at their default (mostly None / "").
    assert info["haos_version"] is None
    assert info["supervisor_version"] is None
    assert info["ha_installation_type_short"] == ""
    assert info["addon_version"] is None
    assert info["integration_version"] != "unknown"  # manifest read still works