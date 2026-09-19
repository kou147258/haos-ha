"""Tests for ``InfoSensor`` -- the single info entity that surfaces all
HA / Supervisor / HAOS / add-on metadata in one place."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.haos.sensor import InfoSensor


def _make_coordinator(meta=None, data=None):
    coordinator = MagicMock()
    coordinator.meta = meta
    coordinator.data = data
    return coordinator


def _make_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Test"
    return entry


def test_info_sensor_state_with_full_meta_and_counts():
    """State = '<version> · <short> · <count> entities'."""
    meta = {
        "ha_core_version": "2026.8.0",
        "ha_installation_type": "Home Assistant OS",
        "ha_installation_type_short": "OS",
        "supervisor_version": "2026.08.0",
        "addon_version": "1.0.0",
    }
    data = {"counts": {"entity": 234, "device": 12, "integration": 45}, "ts": 1234.5}

    sensor = InfoSensor(coordinator=_make_coordinator(meta, data), entry=_make_entry())

    assert sensor.native_value == "2026.8.0 · OS · 234 entities"


def test_info_sensor_state_drops_counts_when_data_missing():
    """Before first refresh, state still shows version + installation."""
    meta = {
        "ha_core_version": "2026.8.0",
        "ha_installation_type": "Home Assistant OS",
        "ha_installation_type_short": "OS",
    }

    sensor = InfoSensor(coordinator=_make_coordinator(meta, data=None),
                        entry=_make_entry())

    assert sensor.native_value == "2026.8.0 · OS · — entities"


def test_info_sensor_state_is_none_without_meta():
    """No meta → no state. Defensive: shouldn't crash, shouldn't show ?."""
    sensor = InfoSensor(coordinator=_make_coordinator(meta=None, data={}),
                        entry=_make_entry())

    assert sensor.native_value is None


def test_info_sensor_attributes_merge_meta_and_counts():
    """All metadata fields + live counts land in extra_state_attributes."""
    meta = {
        "ha_core_version": "2026.8.0",
        "ha_installation_type": "Home Assistant OS",
        "ha_installation_type_short": "OS",
        "ha_arch": "x86_64",
        "ha_time_zone": "UTC",
        "haos_version": "14.1",
        "supervisor_version": "2026.08.0",
        "addon_slug": "haos_fb",
        "addon_version": "1.0.0",
        "addon_state": "started",
        "integration_version": "1.0.0",
        # should NOT appear (None values are stripped):
        "supervisor_healthy": None,
        "haos_board": None,
    }
    data = {"counts": {"entity": 100, "device": 5, "integration": 20}, "ts": 99.0}

    sensor = InfoSensor(coordinator=_make_coordinator(meta, data), entry=_make_entry())

    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert attrs["ha_core_version"] == "2026.8.0"
    assert attrs["ha_installation_type_short"] == "OS"
    assert attrs["haos_version"] == "14.1"
    assert attrs["supervisor_version"] == "2026.08.0"
    assert attrs["addon_slug"] == "haos_fb"
    assert attrs["entity_count"] == 100
    assert attrs["device_count"] == 5
    assert attrs["integration_count"] == 20
    assert attrs["integration_last_refresh"] == 99.0
    # None values stripped -- ``supervisor_healthy`` and ``haos_board``
    # should NOT appear in attributes at all.
    assert "supervisor_healthy" not in attrs
    assert "haos_board" not in attrs


def test_info_sensor_attributes_handle_empty_counts():
    """No data yet → counts keys absent (not set to None)."""
    meta = {"ha_core_version": "2026.8.0", "ha_installation_type_short": "OS"}

    sensor = InfoSensor(coordinator=_make_coordinator(meta, data=None),
                        entry=_make_entry())

    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert "entity_count" not in attrs  # build_attributes strips None


def test_info_sensor_attributes_none_without_meta():
    """No meta → attributes are None (sensor is unavailable / unconfigured)."""
    sensor = InfoSensor(coordinator=_make_coordinator(meta=None, data=None),
                        entry=_make_entry())

    assert sensor.extra_state_attributes is None


def test_info_sensor_unique_id_is_stable():
    """unique_id must include the entry id so reloading doesn't duplicate."""
    sensor = InfoSensor(coordinator=_make_coordinator({"ha_core_version": "1"}),
                        entry=_make_entry())

    assert sensor._attr_unique_id == "test_entry_info"


def test_info_sensor_translation_key_for_frontend():
    """Frontend pulls the displayed name from strings.json under this key."""
    sensor = InfoSensor(coordinator=_make_coordinator({"ha_core_version": "1"}),
                        entry=_make_entry())

    assert sensor._attr_translation_key == "info"


def test_info_sensor_does_not_set_state_class():
    """Info is a text summary, not a measurement -- no state_class / unit."""
    sensor = InfoSensor(coordinator=_make_coordinator({"ha_core_version": "1"}),
                        entry=_make_entry())

    # CoordinatorEntity + SensorEntity don't have a default state_class; we
    # deliberately leave it None.
    assert getattr(sensor, "_attr_state_class", None) is None
    assert getattr(sensor, "_attr_native_unit_of_measurement", None) is None
    assert getattr(sensor, "_attr_device_class", None) is None


def test_info_sensor_count_overrides_meta_baseline():
    """If meta already had a count (from include_counts=True at setup) and the
    coordinator later provides live counts, the live counts should win."""
    meta = {
        "ha_core_version": "2026.8.0",
        "ha_installation_type_short": "OS",
        "entity_count": 999,  # baseline (stale)
    }
    data = {"counts": {"entity": 50, "device": 5, "integration": 10}}

    sensor = InfoSensor(coordinator=_make_coordinator(meta, data), entry=_make_entry())

    assert sensor.native_value == "2026.8.0 · OS · 50 entities"
    assert sensor.extra_state_attributes["entity_count"] == 50