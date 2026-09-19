"""Tests for the HA integration — entity value extraction + addon helpers.

Uses the stubs from ``conftest.py`` so we can exercise the coordinator's
snapshot dict → entity ``native_value`` path without spinning up HA.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.haos.const import (
    ADDON_SLUG,
    CONF_REFRESH_INTERVAL,
    CONF_TEMP_UNIT,
    DEFAULT_TEMP_UNIT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SKIP_FS_TYPES,
    TEMP_UNITS,
    DEFAULT_SCAN_INTERVAL,
)
from custom_components.haos.coordinator import FnOSDashboardCoordinator


# ---------------------------------------------------------------------------
# Coordinator behaviour
# ---------------------------------------------------------------------------


def test_coordinator_builds_initial_snapshot_from_psutil(monkeypatch):
    """_collect_snapshot should always return a non-empty dict on real psutil."""
    hass = MagicMock()
    entry = MagicMock()
    entry.options = {}
    coordinator = FnOSDashboardCoordinator(hass, entry)
    snap = coordinator._collect_snapshot()
    assert snap["processes"] > 0
    assert snap["hostname"]
    assert snap["os"]
    assert isinstance(snap["cpu"]["per_core"], list)
    # First call primes cpu_percent; second call gives real value.
    snap2 = coordinator._collect_snapshot()
    assert "cpu" in snap2
    assert "memory" in snap2


def test_coordinator_clamps_refresh_interval(monkeypatch):
    """Out-of-range refresh options should clamp into [MIN, MAX]."""
    hass = MagicMock()
    entry = MagicMock()
    entry.options = {CONF_REFRESH_INTERVAL: 99999}
    coordinator = FnOSDashboardCoordinator(hass, entry)
    # update_interval is a timedelta; total_seconds gives the clamped value.
    assert coordinator.update_interval.total_seconds() <= 30


def test_coordinator_clamps_too_small_interval():
    hass = MagicMock()
    entry = MagicMock()
    entry.options = {CONF_REFRESH_INTERVAL: 0}
    coordinator = FnOSDashboardCoordinator(hass, entry)
    assert coordinator.update_interval.total_seconds() >= 1


def test_coordinator_first_refresh_failure_raises_updatefailed():
    hass = MagicMock()
    entry = MagicMock()
    entry.options = {}
    coordinator = FnOSDashboardCoordinator(hass, entry)

    async def run():
        with patch.object(
            coordinator, "_collect_snapshot",
            side_effect=RuntimeError("boom"),
        ):
            # Patch async_add_executor_job so it just calls the patched fn.
            async def fake_exec(fn, *args):
                return fn(*args)
            coordinator.hass.async_add_executor_job = fake_exec
            with pytest.raises(Exception):
                await coordinator.async_config_entry_first_refresh()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Sensor value extraction — uses static descriptions + mock_snapshot
# ---------------------------------------------------------------------------


def test_static_descriptions_all_return_value(mock_snapshot):
    """Every static description's value_fn should extract something sensible."""
    from custom_components.haos.sensor import _STATIC_DESCRIPTIONS, _VALUE_FNS

    for key, desc in _STATIC_DESCRIPTIONS.items():
        assert key in _VALUE_FNS, f"missing value extractor for {key}"
        value = _VALUE_FNS[key](mock_snapshot)
        # All extractors should at least not crash. Some return None when the
        # underlying field is genuinely absent (e.g. cpu_temp on hosts with
        # no /sys/class/thermal entries); we just verify the extractor ran.
        assert value is None or isinstance(value, (int, float, str))


def test_per_core_value_extractor(mock_snapshot):
    from custom_components.haos.sensor import PerCoreCpuSensor
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    entry.title = "Test"
    sensor = PerCoreCpuSensor(
        coordinator=MagicMock(data=mock_snapshot),
        entry=entry,
        index=1,
        temp_unit="C",
    )
    assert sensor.native_value == pytest.approx(20.0)
    # Out-of-range index returns None.
    sensor2 = PerCoreCpuSensor(
        coordinator=MagicMock(data=mock_snapshot),
        entry=entry,
        index=99,
        temp_unit="C",
    )
    assert sensor2.native_value is None


def test_disk_value_extractor(mock_snapshot):
    from custom_components.haos.sensor import DiskSensor
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    entry.title = "Test"
    sensor = DiskSensor(
        coordinator=MagicMock(data=mock_snapshot),
        entry=entry,
        disk=mock_snapshot["disks"][0],
        metric="percent",
        safe_mount="_",
        label_suffix="% Used",
    )
    assert sensor.native_value == pytest.approx(40.0)


def test_temperature_value_extractor(mock_snapshot):
    from custom_components.haos.sensor import TemperatureSensor
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    entry.title = "Test"
    sensor = TemperatureSensor(
        coordinator=MagicMock(data=mock_snapshot),
        entry=entry,
        sensor=mock_snapshot["temperatures"][0],
        index=0,
        temp_unit="C",
    )
    assert sensor.native_value == pytest.approx(55.0)
    assert sensor.extra_state_attributes == {"group": "coretemp",
                                              "high": 90.0,
                                              "critical": 100.0}


# ---------------------------------------------------------------------------
# Add-on Supervisor helpers — graceful degradation when Supervisor is absent
# ---------------------------------------------------------------------------


def test_addon_helpers_graceful_without_supervisor():
    """When SUPERVISOR_TOKEN is not set, helpers should return None/False."""
    from custom_components.haos.addon import addon_installed, get_addon_info

    hass = MagicMock()
    hass.config.as_dict.return_value = {}  # no SUPERVISOR_TOKEN
    assert asyncio.run(addon_installed(hass)) is False
    assert asyncio.run(get_addon_info(hass)) is None


def test_addon_helpers_url_targets_supervisor():
    """All add-on calls route through http://supervisor (HA convention)."""
    from custom_components.haos import addon as addon_mod
    from homeassistant.helpers import aiohttp_client

    hass = MagicMock()
    hass.config.as_dict.return_value = {"SUPERVISOR_TOKEN": "abc"}

    captured_urls: list[str] = []
    captured_methods: list[str] = []

    class FakeResp:
        status = 200

        async def json(self_inner):
            return {"data": {"state": "started"}}

        async def __aenter__(self_inner):
            return self_inner

        async def __aexit__(self_inner, *exc):
            return False

        def raise_for_status(self_inner):
            pass

    class FakeSession:
        def get(self, url, **kwargs):
            captured_urls.append(url)
            captured_methods.append("GET")
            return FakeResp()

        def post(self, url, **kwargs):
            captured_urls.append(url)
            captured_methods.append("POST")
            return FakeResp()

    # Patch HA's aiohttp_client + addon module's aiohttp so the helpers can
    # build a FakeSession() instead of trying to import real aiohttp.
    # Both ``aiohttp_client.async_get_clientsession`` (source module) and
    # ``addon_mod.async_get_clientsession`` (imported binding) need patching.
    fake_aiohttp = MagicMock()
    fake_aiohttp.ClientTimeout = lambda **kw: None
    fake_aiohttp.ClientError = Exception
    with patch.object(aiohttp_client, "async_get_clientsession",
                       return_value=FakeSession()), \
         patch.object(addon_mod, "async_get_clientsession",
                       return_value=FakeSession()), \
         patch.object(addon_mod, "aiohttp", fake_aiohttp):
        async def run():
            await addon_mod.addon_installed(hass)
            await addon_mod.get_addon_info(hass)
            await addon_mod.async_start_addon(hass)
            await addon_mod.async_stop_addon(hass)
        asyncio.run(run())

    assert len(captured_urls) == 4, captured_urls
    for url in captured_urls:
        assert url.startswith("http://supervisor/addons/")
        assert ADDON_SLUG in url
    assert captured_methods.count("GET") == 2
    assert captured_methods.count("POST") == 2


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


def test_constants_have_expected_values():
    from custom_components.haos.const import (
        ADDON_SLUG,
        DEFAULT_SCAN_INTERVAL,
        DOMAIN,
        MAX_SCAN_INTERVAL,
        MIN_SCAN_INTERVAL,
        SKIP_FS_TYPES,
        TEMP_UNITS,
    )
    assert DOMAIN == "haos"
    assert ADDON_SLUG == "haos_fb"
    assert DEFAULT_SCAN_INTERVAL.total_seconds() == 2
    assert MIN_SCAN_INTERVAL == 1
    assert MAX_SCAN_INTERVAL == 30
    assert TEMP_UNITS == ("C", "F")
    # Skip list must include all the common virtual FS types.
    assert "tmpfs" in SKIP_FS_TYPES
    assert "overlay" in SKIP_FS_TYPES
    assert "proc" in SKIP_FS_TYPES


def test_temp_unit_default():
    assert DEFAULT_TEMP_UNIT == "C"