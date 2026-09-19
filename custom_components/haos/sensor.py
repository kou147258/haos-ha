"""Sensor platform for HAOS Dashboard.

Exposes the coordinator snapshot as a tree of sensor entities:
  - Overall CPU usage / load / temperature / frequency
  - One sensor per logical CPU core
  - Memory + Swap
  - One sensor group per detected disk mount (percent, used, free, total)
  - Network up / down rate and totals
  - One sensor per detected temperature probe
  - System info: uptime, processes, hostname, OS
  - Info sensor summarising HA / Supervisor / HAOS / add-on metadata

Design note: ``SensorEntityDescription`` is a frozen dataclass in HA 2026+
(``FrozenOrThawed`` metaclass in ``frozen_dataclass_compat.py`` -- it routes
all kwargs through the underlying frozen ``_dataclass.__init__`` and rejects
unknown fields with ``TypeError``). We therefore do NOT subclass it to add
custom fields; value extractors live in ``_VALUE_FNS`` (below) keyed by
``description.key``, and entity instances look up the extractor at native_value
time.
"""
from __future__ import annotations

from collections.abc import Callable
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
        StaticSensor(coordinator, entry, "cpu_percent"),
        StaticSensor(coordinator, entry, "cpu_load_1"),
        StaticSensor(coordinator, entry, "cpu_freq"),
        StaticSensor(coordinator, entry, "cpu_temp"),
        StaticSensor(coordinator, entry, "memory_percent"),
        StaticSensor(coordinator, entry, "memory_used"),
        StaticSensor(coordinator, entry, "memory_total"),
        StaticSensor(coordinator, entry, "memory_free"),
        StaticSensor(coordinator, entry, "swap_percent"),
        StaticSensor(coordinator, entry, "swap_used"),
        StaticSensor(coordinator, entry, "swap_total"),
        StaticSensor(coordinator, entry, "net_up"),
        StaticSensor(coordinator, entry, "net_down"),
        StaticSensor(coordinator, entry, "net_bytes_sent"),
        StaticSensor(coordinator, entry, "net_bytes_recv"),
        StaticSensor(coordinator, entry, "uptime"),
        StaticSensor(coordinator, entry, "processes"),
        StaticSensor(coordinator, entry, "hostname"),
        StaticSensor(coordinator, entry, "os"),
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
# Value extractors -- separate from descriptions
# ---------------------------------------------------------------------------
#
# In HA 2026+ ``SensorEntityDescription`` is a frozen dataclass. Subclassing
# it to add a ``value_fn`` field blows up at construction time (TypeError:
# unexpected keyword argument 'value_fn'). Instead we keep extractors in a
# plain dict keyed by ``description.key`` and look them up on the entity.
#
# The dict is module-level so it doesn't allocate per entity instance.

_VALUE_FNS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "cpu_percent": lambda d: d.get("cpu", {}).get("percent"),
    "cpu_load_1": lambda d: (d.get("cpu", {}).get("load") or [None])[0],
    "cpu_freq": lambda d: d.get("cpu", {}).get("freq_mhz"),
    "cpu_temp": lambda d: d.get("cpu", {}).get("temp"),
    "memory_percent": lambda d: d.get("memory", {}).get("percent"),
    "memory_used": lambda d: d.get("memory", {}).get("used"),
    "memory_total": lambda d: d.get("memory", {}).get("total"),
    "memory_free": lambda d: d.get("memory", {}).get("free"),
    "swap_percent": lambda d: d.get("memory", {}).get("swap_percent"),
    "swap_used": lambda d: d.get("memory", {}).get("swap_used"),
    "swap_total": lambda d: d.get("memory", {}).get("swap_total"),
    "net_up": lambda d: d.get("network", {}).get("up_kbps"),
    "net_down": lambda d: d.get("network", {}).get("down_kbps"),
    "net_bytes_sent": lambda d: d.get("network", {}).get("bytes_sent"),
    "net_bytes_recv": lambda d: d.get("network", {}).get("bytes_recv"),
    "uptime": lambda d: d.get("uptime_seconds"),
    "processes": lambda d: d.get("processes"),
    "hostname": lambda d: d.get("hostname"),
    "os": lambda d: d.get("os"),
}


def _disk_value(data: dict[str, Any], mount: str, key: str) -> Any:
    """Look up the value of a disk metric for a given mount."""
    for disk in data.get("disks", []):
        if disk.get("mount") == mount:
            return disk.get(key)
    return None


# ---------------------------------------------------------------------------
# Descriptions (plain SensorEntityDescription, no custom fields)
# ---------------------------------------------------------------------------


_STATIC_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    "cpu_percent": SensorEntityDescription(
        key="cpu_percent",
        translation_key="cpu_percent",
        name="CPU Usage",
        icon="mdi:cpu-64-bit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
    ),
    "cpu_load_1": SensorEntityDescription(
        key="cpu_load_1",
        translation_key="cpu_load_1",
        name="CPU Load (1 min)",
        icon="mdi:gauge",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=2,
    ),
    "cpu_freq": SensorEntityDescription(
        key="cpu_freq",
        translation_key="cpu_freq",
        name="CPU Frequency",
        icon="mdi:sine-wave",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        suggested_display_precision=0,
    ),
    "cpu_temp": SensorEntityDescription(
        key="cpu_temp",
        translation_key="cpu_temp",
        name="CPU Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    "memory_percent": SensorEntityDescription(
        key="memory_percent",
        translation_key="memory_percent",
        name="Memory Usage",
        icon="mdi:memory",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
    ),
    "memory_used": SensorEntityDescription(
        key="memory_used",
        translation_key="memory_used",
        name="Memory Used",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
    ),
    "memory_total": SensorEntityDescription(
        key="memory_total",
        translation_key="memory_total",
        name="Memory Total",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
    ),
    "memory_free": SensorEntityDescription(
        key="memory_free",
        translation_key="memory_free",
        name="Memory Available",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
    ),
    "swap_percent": SensorEntityDescription(
        key="swap_percent",
        translation_key="swap_percent",
        name="Swap Usage",
        icon="mdi:harddisk",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
    ),
    "swap_used": SensorEntityDescription(
        key="swap_used",
        translation_key="swap_used",
        name="Swap Used",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
    ),
    "swap_total": SensorEntityDescription(
        key="swap_total",
        translation_key="swap_total",
        name="Swap Total",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
    ),
    "net_up": SensorEntityDescription(
        key="net_up",
        translation_key="net_up",
        name="Network Upload",
        icon="mdi:upload",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        suggested_display_precision=1,
    ),
    "net_down": SensorEntityDescription(
        key="net_down",
        translation_key="net_down",
        name="Network Download",
        icon="mdi:download",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        suggested_display_precision=1,
    ),
    "net_bytes_sent": SensorEntityDescription(
        key="net_bytes_sent",
        translation_key="net_bytes_sent",
        name="Network Bytes Sent",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
    ),
    "net_bytes_recv": SensorEntityDescription(
        key="net_bytes_recv",
        translation_key="net_bytes_recv",
        name="Network Bytes Received",
        icon="mdi:download-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
    ),
    "uptime": SensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        name="Uptime",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
    ),
    "processes": SensorEntityDescription(
        key="processes",
        translation_key="processes",
        name="Processes",
        icon="mdi:application-cog",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="processes",
        suggested_display_precision=0,
    ),
    "hostname": SensorEntityDescription(
        key="hostname",
        translation_key="hostname",
        name="Hostname",
        icon="mdi:server",
    ),
    "os": SensorEntityDescription(
        key="os",
        translation_key="os",
        name="Operating System",
        icon="mdi:linux",
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
    entity_description: SensorEntityDescription

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
    """Sensor backed by a static description + the matching ``_VALUE_FNS`` extractor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: FnOSDashboardCoordinator,
        entry: ConfigEntry,
        description_key: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = _STATIC_DESCRIPTIONS[description_key]
        self._value_fn = _VALUE_FNS[description_key]
        self._attr_unique_id = f"{entry.entry_id}_{description_key}"

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self._value_fn(self.coordinator.data)


class PerCoreCpuSensor(_BaseSensor):
    """One sensor per logical CPU core."""

    entity_description = SensorEntityDescription(
        key="cpu_core",
        translation_key="cpu_core",
        name="CPU Core",
        icon="mdi:cpu-64-bit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
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

    _DISK_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
        "percent": SensorEntityDescription(
            key="disk_percent",
            translation_key="disk_percent",
            name="% Used",
            icon="mdi:harddisk",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            suggested_display_precision=1,
        ),
        "used": SensorEntityDescription(
            key="disk_used",
            translation_key="disk_used",
            name="Used",
            icon="mdi:harddisk",
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfInformation.BYTES,
            suggested_display_precision=0,
        ),
        "free": SensorEntityDescription(
            key="disk_free",
            translation_key="disk_free",
            name="Free",
            icon="mdi:harddisk",
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfInformation.BYTES,
            suggested_display_precision=0,
        ),
        "total": SensorEntityDescription(
            key="disk_total",
            translation_key="disk_total",
            name="Total",
            icon="mdi:harddisk",
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfInformation.BYTES,
            suggested_display_precision=0,
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
        # Bind mount + metric into a closure for the value extractor.
        self._value_fn = (
            lambda d, m=self._disk_mount, k=self._metric: _disk_value(d, m, k)
        )
        self._attr_unique_id = f"{entry.entry_id}_disk_{safe_mount}_{metric}"
        self._attr_translation_placeholders = {"mount": disk["mount"]}
        self._attr_name = label_suffix

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self._value_fn(self.coordinator.data)


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

    entity_description = SensorEntityDescription(
        key="info",
        translation_key="info",
        name="Info",
        icon="mdi:information-outline",
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