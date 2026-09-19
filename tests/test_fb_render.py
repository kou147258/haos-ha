"""Tests for fb_render helpers — pure Python, no HA dependency."""
from __future__ import annotations

import pytest

from fb_render import (
    HAClient,
    _make_synthetic_snapshot,
    _merge_disk,
    _merge_entity,
    _safe_float,
    _safe_int,
)


# ---------------------------------------------------------------------------
# _safe_float / _safe_int
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.5", 1.5),
        ("0", 0.0),
        (0, 0.0),
        (-3.14, -3.14),
    ],
)
def test_safe_float_happy(value, expected):
    assert _safe_float(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", [None, "unknown", "unavailable", "abc", []])
def test_safe_float_bad(value):
    assert _safe_float(value) is None


def test_safe_int_truncates():
    assert _safe_int("42.9") == 42
    assert _safe_int("-3.7") == -3


def test_safe_int_bad():
    assert _safe_int(None) is None
    assert _safe_int("xx") is None


# ---------------------------------------------------------------------------
# _make_synthetic_snapshot
# ---------------------------------------------------------------------------


def test_synthetic_snapshot_shape():
    snap = _make_synthetic_snapshot(800, 480)
    assert snap["hostname"]
    assert snap["os"]
    assert snap["kernel"]
    assert snap["processes"] > 0
    cpu = snap["cpu"]
    assert 0 <= cpu["percent"] <= 100
    assert len(cpu["per_core"]) == cpu["logical_cores"]
    assert all(0 <= v <= 100 for v in cpu["per_core"])
    assert len(snap["disks"]) >= 1
    for d in snap["disks"]:
        assert d["total"] > 0
        assert 0 <= d["percent"] <= 100
        assert d["used"] + d["free"] == d["total"]
    assert snap["memory"]["total"] > 0


def test_synthetic_snapshot_changes_per_call():
    """Different calls should produce slightly different values (animations).

    The synthetic generator seeds off the current time bucket; back-to-back
    calls in the same bucket can collide, so we explicitly offset the time
    argument to force a difference.
    """
    snap1 = _make_synthetic_snapshot(800, 480)
    # Force a different time bucket.
    import time as _t
    orig = _t.time
    try:
        _t.time = lambda: orig() + 100
        snap2 = _make_synthetic_snapshot(800, 480)
    finally:
        _t.time = orig
    # At least one of the volatile fields must differ.
    diff = (
        snap1["cpu"]["percent"] != snap2["cpu"]["percent"]
        or snap1["cpu"]["per_core"] != snap2["cpu"]["per_core"]
        or snap1["network"]["up_kbps"] != snap2["network"]["up_kbps"]
        or snap1["network"]["down_kbps"] != snap2["network"]["down_kbps"]
    )
    assert diff, "Synthetic snapshot did not change between calls"


# ---------------------------------------------------------------------------
# _merge_entity — the parsing pipeline that feeds the renderer
# ---------------------------------------------------------------------------


def _empty_snap() -> dict:
    return {
        "cpu": {"percent": 0.0, "per_core": [], "load": [0.0, 0.0, 0.0],
                 "freq_mhz": 0, "temp": None, "logical_cores": 0,
                 "physical_cores": 0},
        "memory": {"percent": 0.0, "used": 0, "total": 0, "free": 0,
                    "swap_percent": 0.0, "swap_used": 0, "swap_total": 0},
        "disks": [], "network": {"interfaces": [], "bytes_sent": 0,
                                  "bytes_recv": 0, "up_kbps": 0.0,
                                  "down_kbps": 0.0},
        "temperatures": [], "processes": 0, "uptime_seconds": 0,
        "boot_time": 0, "hostname": "", "os": "", "kernel": "", "ts": 0.0,
    }


def test_merge_entity_cpu_percent():
    snap = _merge_entity(
        _empty_snap(), "sensor.haos_cpu_percent", "42.5", {},
    )
    assert snap["cpu"]["percent"] == pytest.approx(42.5)


def test_merge_entity_unknown_entity_passthrough():
    snap = _merge_entity(
        _empty_snap(), "sensor.some_other_thing", "42", {},
    )
    # Nothing changed, snapshot still empty.
    assert snap["cpu"]["percent"] == 0.0


def test_merge_entity_disk_creates_new_entry():
    snap = _merge_entity(
        _empty_snap(), "sensor.haos_disk__percent", "75.0", {},
    )
    # mount "_" → "/" per the parser's underscore → slash conversion.
    assert len(snap["disks"]) == 1
    assert snap["disks"][0]["mount"] == "/"
    assert snap["disks"][0]["percent"] == pytest.approx(75.0)


def test_merge_entity_disk_updates_existing():
    snap = _merge_entity(
        _empty_snap(), "sensor.haos_disk__percent", "50.0", {},
    )
    snap = _merge_entity(
        snap, "sensor.haos_disk__used", "100000", {},
    )
    assert len(snap["disks"]) == 1
    assert snap["disks"][0]["percent"] == pytest.approx(50.0)
    assert snap["disks"][0]["used"] == 100000


def test_merge_entity_temperature_with_attributes():
    snap = _merge_entity(
        _empty_snap(),
        "sensor.haos_temperature_coretemp_cpu",
        "55.0",
        {"high": 90.0, "critical": 100.0},
    )
    assert len(snap["temperatures"]) == 1
    t = snap["temperatures"][0]
    assert t["label"] == "coretemp cpu"
    assert t["current"] == pytest.approx(55.0)
    assert t["high"] == pytest.approx(90.0)


def test_merge_entity_per_core_appends():
    snap = _empty_snap()
    snap = _merge_entity(snap, "sensor.haos_cpu_core_0", "10", {})
    snap = _merge_entity(snap, "sensor.haos_cpu_core_1", "20", {})
    snap = _merge_entity(snap, "sensor.haos_cpu_core_2", "30", {})
    assert snap["cpu"]["per_core"] == [10.0, 20.0, 30.0]


# ---------------------------------------------------------------------------
# _merge_disk
# ---------------------------------------------------------------------------


def test_merge_disk_creates():
    snap = _empty_snap()
    _merge_disk(snap, "/data", "percent", "20")
    assert snap["disks"][0]["mount"] == "/data"
    assert snap["disks"][0]["percent"] == pytest.approx(20.0)


def test_merge_disk_updates_existing_metric():
    snap = _empty_snap()
    _merge_disk(snap, "/", "percent", "10")
    _merge_disk(snap, "/", "used", "50000")
    assert len(snap["disks"]) == 1
    assert snap["disks"][0]["percent"] == pytest.approx(10.0)
    assert snap["disks"][0]["used"] == 50000


# ---------------------------------------------------------------------------
# HAClient URL building (not actually hitting HA)
# ---------------------------------------------------------------------------


def test_haclient_url_strips_trailing_slash():
    """Trim trailing slashes on construction (no HTTP call yet)."""
    import fb_render
    # Patch the aiohttp reference inside fb_render's namespace so HAClient
    # can call ``aiohttp.ClientTimeout`` even when aiohttp isn't installed.
    if fb_render.aiohttp is None:
        fb_render.aiohttp = types.SimpleNamespace(
            ClientTimeout=lambda **kw: None,
            ClientSession=lambda *a, **kw: None,
            ClientError=Exception,
        )
    client = HAClient(base_url="http://supervisor/core/api/", token="x")
    assert client.base_url == "http://supervisor/core/api"


import types  # noqa: E402  — used by the test above