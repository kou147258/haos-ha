"""Unit / precision lock-down tests for the sensor platform.

The integration pins its display units explicitly so that HA's
locale-dependent auto-conversion doesn't change what users see across
Metric/Imperial settings:

  * memory_* / swap_*              -> GB (decimal, 1e9 bytes per GB)
  * net_bytes_sent / net_bytes_received  -> MB (decimal, 1e6 bytes per MB)
  * net_up / net_down            -> MB/s (decimal, 1000 KB/s per MB/s)
  * cpu_freq / cpu_temp / cpu_percent / memory_percent / etc  unchanged

This module also pins precision by category (HA precision rules):
  * integer / count / frequency / byte-based -> 0 decimals (whole units)
  * percentage / temperature / network rate   -> 1 decimal
"""
from __future__ import annotations

import pytest

from homeassistant.const import (
    UnitOfDataRate,
    UnitOfInformation,
)

from custom_components.haos.sensor import (
    _STATIC_DESCRIPTIONS,
    _VALUE_FNS,
    _bytes_to_gb,
    _bytes_to_mb,
    _kbps_to_mbps,
)


# ---------------------------------------------------------------------------
# Pure unit-conversion helpers
# ---------------------------------------------------------------------------


def test_bytes_to_gb_decimal_6gb():
    # 6 GB binary = 6 * 1024**3 bytes; in decimal that is 6 * 1024**3 / 1e9 ≈ 6.44.
    assert _bytes_to_gb(6 * 1024**3) == round(6 * 1024**3 / 1e9, 4)
    # 1 GB exactly.
    assert _bytes_to_gb(1_000_000_000) == 1.0
    assert _bytes_to_gb(1_500_000_000) == 1.5


def test_bytes_to_mb_decimal_10mb():
    assert _bytes_to_mb(10_000_000) == 10.0
    assert _bytes_to_mb(10_500_000) == 10.5


def test_kbps_to_mbps():
    assert _kbps_to_mbps(1000) == 1.0
    assert _kbps_to_mbps(500) == 0.5
    assert _kbps_to_mbps(1234) == round(1234 / 1000.0, 4)


def test_conversion_helpers_return_none_for_none():
    assert _bytes_to_gb(None) is None
    assert _bytes_to_mb(None) is None
    assert _kbps_to_mbps(None) is None


# ---------------------------------------------------------------------------
# Description units pinned -- prevents accidental "back to BYTES" drift
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key,expected_unit", [
    ("memory_used",      UnitOfInformation.GIGABYTES),
    ("memory_total",     UnitOfInformation.GIGABYTES),
    ("memory_free",      UnitOfInformation.GIGABYTES),
    ("swap_used",        UnitOfInformation.GIGABYTES),
    ("swap_total",       UnitOfInformation.GIGABYTES),
    ("net_up",           UnitOfDataRate.MEGABYTES_PER_SECOND),
    ("net_down",         UnitOfDataRate.MEGABYTES_PER_SECOND),
    ("net_bytes_sent",   UnitOfInformation.MEGABYTES),
    ("net_bytes_recv",   UnitOfInformation.MEGABYTES),
])
def test_static_description_uses_pinned_unit(key, expected_unit):
    assert _STATIC_DESCRIPTIONS[key].native_unit_of_measurement == expected_unit


# ---------------------------------------------------------------------------
# Value extractors produce numbers in the unit the description declares
# ---------------------------------------------------------------------------


def test_value_fns_use_correct_units_against_mock_snapshot(mock_snapshot):
    # mock_snapshot has mem.used = 6 * 1024**3 bytes.
    # _VALUE_FNS["memory_used"] returns bytes / 1e9 -> GB.
    assert _VALUE_FNS["memory_used"](mock_snapshot) == round(6 * 1024**3 / 1e9, 4)
    # net.bytes_sent = 1_000_000 -> 1 MB.
    assert _VALUE_FNS["net_bytes_sent"](mock_snapshot) == 1.0
    # net.bytes_recv = 10_000_000 -> 10 MB.
    assert _VALUE_FNS["net_bytes_recv"](mock_snapshot) == 10.0
    # net.up_kbps = 50.0 -> 0.05 MB/s.
    assert _VALUE_FNS["net_up"](mock_snapshot) == 0.05


# ---------------------------------------------------------------------------
# Precision rules by category (the value the user picked)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", [
    "memory_used", "memory_total", "memory_free",
    "swap_used", "swap_total",
    "net_bytes_sent", "net_bytes_recv",
    "cpu_freq",
    "uptime",
    "processes",
])
def test_integer_or_byte_sensors_use_precision_zero(key):
    # Memory / bytes / frequency / uptime / counts -- whole units look clean.
    assert _STATIC_DESCRIPTIONS[key].suggested_display_precision == 0, (
        f"{key} should be precision 0 (whole units)"
    )


@pytest.mark.parametrize("key", [
    "cpu_percent",
    "cpu_temp",
    "cpu_load_1",
    "net_up", "net_down",
    "memory_percent", "swap_percent",
])
def test_rate_percent_temp_sensors_use_precision_one_or_two(key):
    # Percent / temperature / network rate -- 1 decimal for granularity.
    # cpu_load_1 stays at 2 decimals because 0.xx range needs more resolution.
    p = _STATIC_DESCRIPTIONS[key].suggested_display_precision
    assert p in (1, 2), f"{key} should be 1 or 2 decimals, got {p}"