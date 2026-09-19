"""Sensor platform for HAOS Dashboard.

Exposes the coordinator snapshot as a tree of sensor entities:
  - Overall CPU usage / load / temperature / frequency
  - One sensor per logical CPU core
  - Memory + Swap
  - One sensor group per detected disk mount (percent, used, free, total)
  - Network up / down rate and totals
  - One sensor per detected temperature probe
  - System info: uptime, processes, hostname, OS
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfDataRate,
    UnitOfFrequency,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_TEMP_UNIT, DOMAIN, MANUFACTURER, TEMP_UNITS
from .coordinator import FnOSDashboardCoordinator
from .info import build_attributes, build_state_string


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: FnOSDashboardCoordinator = hass.data[DOMAIN][entry.entry_id]
    temp_unit = entry.options.get("temp_unit", DEFAULT_TEMP_UNIT)
    if temp_unit not in TEMP_UNITS:
        temp_unit = DEFAULT_TEMP_UNIT

    entities: list[SensorEntity] = [
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["cpu_percent"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["cpu_load_1"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["cpu_freq"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["cpu_temp"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["memory_percent"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["memory_used"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["memory_total"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["memory_free"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["swap_percent"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["swap_used"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["swap_total"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["net_up"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["net_down"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["net_bytes_sent"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["net_bytes_recv"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["uptime"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["processes"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["hostname"]),
        StaticSensor(coordinator, entry, _STATIC_DESCRIPTIONS["os"]),
    ]
    temp_unit_const = (
        UnitOfTemperature.CELSIUS if temp_unit == "C" else UnitOfTemperature.FAHRENHEIT
    )

    data = coordinator.data or {}
    cpu = data.get("cpu", {})

    # Info sensor is always added; its attributes come from the coordinator's
    # ``meta`` (set by ``__init__`` via ``async_collect_info``) plus the
    # ``counts`` block that every coordinator tick appends.
    entities.append(InfoSensor(coordinator, entry))
    for index in range(len(cpu.get("per_core", []))):
        entities.append(
            PerCoreCpuSensor(coordinator, entry, index, temp_unit_const)
        )
    for index, disk in enumerate(data.get("disks", [])):
        entities.extend(_disk_sensors_for_mount(coordinator, entry, disk, index))
    for temp in data.get("temperatures", []):
        entities.append(
            TemperatureSensor(coordinator, entry, temp, temp_unit_const)
        )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------


class FnOSDashboardSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor.

    Plain subclass (not @dataclass) so we can accept the full HA
    SensorEntityDescription kwargs plus our own ``value_fn`` regardless of
    whether the test suite has stubbed out the HA dataclass.

    Uses ``object.__setattr__`` for ``value_fn`` so the frozen-style guard
    on the parent class (HA 2026+ makes SensorEntityDescription immutable)
    doesn't block this one extension field.
    """

    def __init__(self, value_fn: Callable[[dict[str, Any]], Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "value_fn", value_fn)


_STATIC_DESCRIPTIONS: dict[str, FnOSDashboardSensorDescription] = {
    "cpu_percent": FnOSDashboardSensorDescription(
        key="cpu_percent",
        translation_key="cpu_percent",
        name="CPU Usage",
        icon="mdi:cpu-64-bit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("cpu", {}).get("percent"),
    ),
    "cpu_load_1": FnOSDashboardSensorDescription(
        key="cpu_load_1",
        translation_key="cpu_load_1",
        name="CPU Load (1 min)",
        icon="mdi:gauge",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=2,
        value_fn=lambda d: (d.get("cpu", {}).get("load") or [None])[0],
    ),
    "cpu_freq": FnOSDashboardSensorDescription(
        key="cpu_freq",
        translation_key="cpu_freq",
        name="CPU Frequency",
        icon="mdi:sine-wave",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("cpu", {}).get("freq_mhz"),
    ),
    "cpu_temp": FnOSDashboardSensorDescription(
        key="cpu_temp",
        translation_key="cpu_temp",
        name="CPU Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("cpu", {}).get("temp"),
    ),
    "memory_percent": FnOSDashboardSensorDescription(
        key="memory_percent",
        translation_key="memory_percent",
        name="Memory Usage",
        icon="mdi:memory",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("memory", {}).get("percent"),
    ),
    "memory_used": FnOSDashboardSensorDescription(
        key="memory_used",
        translation_key="memory_used",
        name="Memory Used",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("memory", {}).get("used"),
    ),
    "memory_total": FnOSDashboardSensorDescription(
        key="memory_total",
        translation_key="memory_total",
        name="Memory Total",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("memory", {}).get("total"),
    ),
    "memory_free": FnOSDashboardSensorDescription(
        key="memory_free",
        translation_key="memory_free",
        name="Memory Available",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("memory", {}).get("free"),
    ),
    "swap_percent": FnOSDashboardSensorDescription(
        key="swap_percent",
        translation_key="swap_percent",
        name="Swap Usage",
        icon="mdi:harddisk",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("memory", {}).get("swap_percent"),
    ),
    "swap_used": FnOSDashboardSensorDescription(
        key="swap_used",
        translation_key="swap_used",
        name="Swap Used",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("memory", {}).get("swap_used"),
    ),
    "swap_total": FnOSDashboardSensorDescription(
        key="swap_total",
        translation_key="swap_total",
        name="Swap Total",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("memory", {}).get("swap_total"),
    ),
    "net_up": FnOSDashboardSensorDescription(
        key="net_up",
        translation_key="net_up",
        name="Network Upload",
        icon="mdi:upload",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("network", {}).get("up_kbps"),
    ),
    "net_down": FnOSDashboardSensorDescription(
        key="net_down",
        translation_key="net_down",
        name="Network Download",
        icon="mdi:download",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("network", {}).get("down_kbps"),
    ),
    "net_bytes_sent": FnOSDashboardSensorDescription(
        key="net_bytes_sent",
        translation_key="net_bytes_sent",
        name="Network Bytes Sent",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("network", {}).get("bytes_sent"),
    ),
    "net_bytes_recv": FnOSDashboardSensorDescription(
        key="net_bytes_recv",
        translation_key="net_bytes_recv",
        name="Network Bytes Received",
        icon="mdi:download-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("network", {}).get("bytes_recv"),
    ),
    "uptime": FnOSDashboardSensorDescription(
        key="uptime",
        translation_key="uptime",
        name="Uptime",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("uptime_seconds"),
    ),
    "processes": FnOSDashboardSensorDescription(
        key="processes",
        translation_key="processes",
        name="Processes",
        icon="mdi:application-cog",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="processes",
        suggested_display_precision=0,
        value_fn=lambda d: d.get("processes"),
    ),
    "hostname": FnOSDashboardSensorDescription(
        key="hostname",
        translation_key="hostname",
        name="Hostname",
        icon="mdi:server",
        value_fn=lambda d: d.get("hostname"),
    ),
    "os": FnOSDashboardSensorDescription(
        key="os",
        translation_key="os",
        name="Operating System",
        icon="mdi:linux",
        value_fn=lambda d: d.get("os"),
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=MANUFACTURER,
        model="System Monitor",
        name=entry.title,
        entry_type=None,
    )


def _disk_sensors_for_mount(
    coordinator: FnOSDashboardCoordinator,
    entry: ConfigEntry,
    disk: dict[str, Any],
    index: int,
) -> list[SensorEntity]:
    mount = disk["mount"]
    safe = mount.replace("/", "_").strip("_") or f"disk{index}"
    return [
        DiskSensor(coordinator, entry, disk, "percent", safe, "% Used"),
        DiskSensor(coordinator, entry, disk, "used", safe, "Used"),
        DiskSensor(coordinator, entry, disk, "free", safe, "Free"),
        DiskSensor(coordinator, entry, disk, "total", safe, "Total"),
    ]


def _disk_value(data: dict[str, Any], mount: str, key: str) -> Any:
    """Look up the value of a disk metric for a given mount."""
    for disk in data.get("disks", []):
        if disk.get("mount") == mount:
            return disk.get(key)
    return None


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class _BaseSensor(CoordinatorEntity[FnOSDashboardCoordinator], SensorEntity):
    """Base class shared by every HAOS Dashboard sensor."""

    _attr_has_entity_name = True
    entity_description: FnOSDashboardSensorDescription

    def __init__(
        self,
        coordinator: FnOSDashboardCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = _device_info(entry)
        self._entry = entry

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None


class StaticSensor(_BaseSensor):
    """Sensor backed by a static description + value_fn."""

    entity_description: FnOSDashboardSensorDescription

    def __init__(
        self,
        coordinator: FnOSDashboardCoordinator,
        entry: ConfigEntry,
        description: FnOSDashboardSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class PerCoreCpuSensor(_BaseSensor):
    """One sensor per logical CPU core."""

    entity_description = FnOSDashboardSensorDescription(
        key="cpu_core",
        translation_key="cpu_core",
        name="CPU Core",
        icon="mdi:cpu-64-bit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d, idx=0: (d.get("cpu", {}).get("per_core") or [None])[idx],
    )

    def __init__(
        self,
        coordinator: FnOSDashboardCoordinator,
        entry: ConfigEntry,
        index: int,
        temp_unit: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._index = index
        self._attr_unique_id = f"{entry.entry_id}_cpu_core_{index}"
        self._attr_translation_placeholders = {"core": str(index)}

    @property
    def name(self) -> str | None:
        return f"CPU Core {self._index}"

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        per_core = self.coordinator.data.get("cpu", {}).get("per_core") or []
        if self._index >= len(per_core):
            return None
        return per_core[self._index]


class DiskSensor(_BaseSensor):
    """Disk metric (percent / used / free / total) for a single mount."""

    _DISK_DESCRIPTIONS: dict[str, FnOSDashboardSensorDescription] = {
        "percent": FnOSDashboardSensorDescription(
            key="disk_percent",
            translation_key="disk_percent",
            name="% Used",
            icon="mdi:harddisk",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            suggested_display_precision=1,
            value_fn=lambda d, mount="": _disk_value(d, mount, "percent"),
        ),
        "used": FnOSDashboardSensorDescription(
            key="disk_used",
            translation_key="disk_used",
            name="Used",
            icon="mdi:harddisk",
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfInformation.BYTES,
            suggested_display_precision=0,
            value_fn=lambda d, mount="": _disk_value(d, mount, "used"),
        ),
        "free": FnOSDashboardSensorDescription(
            key="disk_free",
            translation_key="disk_free",
            name="Free",
            icon="mdi:harddisk",
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfInformation.BYTES,
            suggested_display_precision=0,
            value_fn=lambda d, mount="": _disk_value(d, mount, "free"),
        ),
        "total": FnOSDashboardSensorDescription(
            key="disk_total",
            translation_key="disk_total",
            name="Total",
            icon="mdi:harddisk",
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfInformation.BYTES,
            suggested_display_precision=0,
            value_fn=lambda d, mount="": _disk_value(d, mount, "total"),
        ),
    }

    def __init__(
        self,
        coordinator: FnOSDashboardCoordinator,
        entry: ConfigEntry,
        disk: dict[str, Any],
        metric: str,
        safe_mount: str,
        label_suffix: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._disk_mount = disk["mount"]
        self._metric = metric
        self.entity_description = self._DISK_DESCRIPTIONS[metric]
        self._attr_unique_id = f"{entry.entry_id}_disk_{safe_mount}_{metric}"
        self._attr_translation_placeholders = {"mount": disk["mount"]}
        self._attr_name = label_suffix

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        for disk in self.coordinator.data.get("disks", []):
            if disk["mount"] == self._disk_mount:
                return disk.get(self._metric)
        return None


class TemperatureSensor(_BaseSensor):
    """One sensor per psutil-detected temperature probe."""

    def __init__(
        self,
        coordinator: FnOSDashboardCoordinator,
        entry: ConfigEntry,
        sensor: dict[str, Any],
        temp_unit: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._label = sensor["label"]
        self._group = sensor["group"]
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = temp_unit
        self._attr_suggested_display_precision = 1
        self._attr_unique_id = (
            f"{entry.entry_id}_temp_{sensor['group']}_{sensor['label']}"
        ).replace(" ", "_")
        self._attr_translation_placeholders = {"label": sensor["label"]}

    @property
    def name(self) -> str | None:
        return f"Temperature {self._label}"

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        for temp in self.coordinator.data.get("temperatures", []):
            if temp["label"] == self._label and temp["group"] == self._group:
                return temp["current"]
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.coordinator.data is None:
            return None
        for temp in self.coordinator.data.get("temperatures", []):
            if temp["label"] == self._label and temp["group"] == self._group:
                attrs: dict[str, Any] = {"group": temp["group"]}
                if temp.get("high") is not None:
                    attrs["high"] = temp["high"]
                if temp.get("critical") is not None:
                    attrs["critical"] = temp["critical"]
                return attrs
        return None


class InfoSensor(_BaseSensor):
    """Single sensor summarising HA / Supervisor / HAOS / add-on metadata.

    State is a short human-readable string (``"2026.8.0 · OS · 234 entities"``);
    every other field lands in ``extra_state_attributes``. Counts refresh with
    the coordinator's main tick; everything else is captured once at setup
    and stays put until the integration reloads.

    Uses the standard ``entity_description`` pattern (name + translation_key
    on the description class attribute) so HA's metaclass-managed
    ``@cached_property`` machinery for ``name`` / ``icon`` / ``translation_key``
    picks everything up automatically -- no need to override those properties
    on the entity subclass.
    """

    entity_description = FnOSDashboardSensorDescription(
        key="info",
        translation_key="info",
        name="Info",
        icon="mdi:information-outline",
        value_fn=None,  # native_value is overridden; value_fn is unused
    )
    # Deliberately NOT setting device_class / state_class / unit: this is a
    # text summary, not a measurement, so HA's numeric-state path short-circuits.

    def __init__(
        self,
        coordinator: FnOSDashboardCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_info"

    @property
    def native_value(self) -> str | None:
        info = self._compose_info()
        if not info:
            return None
        return build_state_string(info)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        info = self._compose_info()
        if not info:
            return None
        attrs = build_attributes(info)
        # Add the coordinator's last-refresh timestamp so consumers can see
        # when the counts were last refreshed alongside the snapshot version.
        data = self.coordinator.data or {}
        ts = data.get("ts")
        if isinstance(ts, (int, float)):
            attrs["integration_last_refresh"] = ts
        return attrs or None

    def _compose_info(self) -> dict[str, Any] | None:
        """Merge one-shot metadata with the latest counts from coordinator.data."""
        base = dict(self.coordinator.meta) if self.coordinator.meta else {}
        if not base:
            return None
        data = self.coordinator.data or {}
        counts = data.get("counts") or {}
        base["entity_count"] = counts.get("entity", base.get("entity_count"))
        base["device_count"] = counts.get("device", base.get("device_count"))
        base["integration_count"] = counts.get("integration", base.get("integration_count"))
        return base


@callback
def async_describe_logging_changes(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Hook for tests; placeholder for future per-entry diagnostics."""