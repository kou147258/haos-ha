"""Guard against accidentally mutating SensorEntityDescription at runtime.

HA 2026+ makes ``SensorEntityDescription`` a frozen dataclass. Setting any
attribute on an instance (or on our subclass's ``value_fn``) raises
``FrozenInstanceError``. Setting it from inside an entity's ``__init__``
explodes the moment a user installs the integration on real HA.

The conftest stub mirrors that frozen behaviour. These tests are
intentionally minimal -- they don't need to validate correctness, only that
nothing in the integration tries to mutate ``entity_description.<anything>``
after construction.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.haos.sensor import (
    DiskSensor,
    InfoSensor,
    PerCoreCpuSensor,
    SensorEntityDescription,
    StaticSensor,
    TemperatureSensor,
    _STATIC_DESCRIPTIONS,
)


def _make_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Test"
    return entry


@pytest.mark.parametrize("field,value", [
    ("key", "hacked"),
    ("translation_key", "hacked"),
    ("name", "hacked"),
    ("icon", "mdi:hacked"),
    ("device_class", "hacked"),
    ("state_class", "hacked"),
    ("native_unit_of_measurement", "hacked"),
    ("suggested_display_precision", 99),
])
def test_sensor_entity_description_is_frozen(field, value):
    """The stub raises on any field assignment, matching real HA 2026+."""
    desc = SensorEntityDescription(key="orig", name="orig")
    with pytest.raises(AttributeError, match="frozen"):
        setattr(desc, field, value)


@pytest.mark.parametrize("description", list(_STATIC_DESCRIPTIONS.values()))
def test_static_descriptions_immutable_after_construction(description):
    """Frozen-on-construct -- no description should be re-mutable."""
    with pytest.raises(AttributeError, match="frozen"):
        description.key = "rebound"


def test_disk_sensor_does_not_mutate_its_description(mock_snapshot):
    """Regression test for the v1.0.0 frozen-dataclass bug.

    The original DiskSensor.__init__ rebound entity_description.value_fn
    with a per-mount closure. HA 2026+'s frozen dataclass raises
    FrozenInstanceError on that line -- the integration would crash the
    moment the first disk sensor was constructed on real HA.
    """
    coordinator = MagicMock(data=mock_snapshot)
    sensor = DiskSensor(
        coordinator=coordinator,
        entry=_make_entry(),
        disk=mock_snapshot["disks"][0],
        metric="percent",
        safe_mount="_",
        label_suffix="% Used",
    )

    # Sanity: native_value still pulls the right number via the mount lookup.
    assert sensor.native_value == pytest.approx(40.0)
    # Sanity: description still belongs to the shared _DISK_DESCRIPTIONS,
    # not a mutated copy.
    assert sensor.entity_description is not None


def test_per_core_sensor_does_not_mutate_description():
    sensor = PerCoreCpuSensor(
        coordinator=MagicMock(data={"cpu": {"per_core": [10.0]}}),
        entry=_make_entry(),
        index=0,
        temp_unit="C",
    )
    # Static class-level description must remain the singleton.
    assert sensor.entity_description is PerCoreCpuSensor.entity_description


def test_temperature_sensor_does_not_mutate_description(mock_snapshot):
    sensor = TemperatureSensor(
        coordinator=MagicMock(data=mock_snapshot),
        entry=_make_entry(),
        sensor=mock_snapshot["temperatures"][0],
        index=0,
        temp_unit="C",
    )
    assert sensor.native_value == pytest.approx(55.0)


def test_temperature_sensor_unique_id_with_duplicate_labels():
    """Regression: real hosts (especially VMs) can have multiple temperature
    sensors under the same group with identical label strings. The unique_id
    must use (group, index) so they don't collide."""
    from custom_components.haos.sensor import TemperatureSensor
    snapshot = {
        "temperatures": [
            {"label": "acpitz", "group": "acpitz", "current": 27.8},
            {"label": "acpitz", "group": "acpitz", "current": 29.0},
            {"label": "acpitz", "group": "acpitz", "current": 30.5},
        ],
    }
    coordinator = MagicMock(data=snapshot)
    entry = MagicMock()
    entry.entry_id = "01M2W83KX897NJ7XQK58EQVPJA"
    entry.title = "Test"
    sensors = [
        TemperatureSensor(
            coordinator=coordinator, entry=entry,
            sensor=snapshot["temperatures"][i],
            index=i, temp_unit="C",
        )
        for i in range(3)
    ]
    unique_ids = {s._attr_unique_id for s in sensors}
    # All three must produce distinct unique_ids even though every
    # (group, label) pair is identical.
    assert len(unique_ids) == 3, f"unique_ids collide: {unique_ids}"
    # Each must still resolve to its own current value, not the first one.
    assert sensors[0].native_value == pytest.approx(27.8)
    assert sensors[1].native_value == pytest.approx(29.0)
    assert sensors[2].native_value == pytest.approx(30.5)


def test_static_sensor_does_not_mutate_description():
    sensor = StaticSensor(
        coordinator=MagicMock(data={"cpu": {"percent": 42.5}}),
        entry=_make_entry(),
        description_key="cpu_percent",
    )
    assert sensor.native_value == pytest.approx(42.5)


def test_info_sensor_does_not_mutate_description():
    """InfoSensor uses a class-level entity_description (the standard
    pattern) instead of mutating one in __init__. This guards against
    anyone adding a per-instance rebind later -- which would crash on
    real HA's frozen dataclass."""
    sensor = InfoSensor(
        coordinator=MagicMock(meta={"ha_core_version": "1.0.0"}, data={}),
        entry=_make_entry(),
    )
    # Class-level description is shared across instances and is immutable.
    assert sensor.entity_description is InfoSensor.entity_description
    # Construction must not mutate the description.
    with pytest.raises(AttributeError, match="frozen"):
        sensor.entity_description.name = "hacked"
    # State + attrs still resolve through the description's translation_key
    # and the override properties.
    assert sensor.native_value == "1.0.0 · — entities"