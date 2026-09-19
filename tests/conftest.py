"""Test fixtures + minimal HA stubs.

The real ``homeassistant`` package is heavy and version-pinned; for unit
tests of helpers + entity value extraction we don't need it. This conftest
defines the minimal stubs that the integration's modules import, so tests
can exercise the coordinator / sensors / switch / binary_sensor logic
without spinning up a HA container.

If you want to test against a real Home Assistant, set
``HAOS_USE_REAL_HA=1`` in the environment; the conftest will skip
the stubs and require ``homeassistant`` to be importable instead.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from typing import Generic, TypeVar

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ADDON_DIR = REPO_ROOT / "haos_fb"
INTEGRATION_DIR = REPO_ROOT / "custom_components" / "haos"

# Make the integration + add-on importable.
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(ADDON_DIR))


# ---------------------------------------------------------------------------
# HA stubs (only injected when HAOS_USE_REAL_HA is not set)
# ---------------------------------------------------------------------------


_USE_REAL_HA = os.environ.get("HAOS_USE_REAL_HA") == "1"


def _install_ha_stubs() -> None:
    """Inject minimal HA stubs so the integration's modules import."""
    if "homeassistant" in sys.modules:
        return

    ha = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha

    # helpers.* is a namespace package — create the parent so ``from
    # homeassistant.helpers import aiohttp_client`` works.
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # namespace package marker
    sys.modules["homeassistant.helpers"] = helpers

    # config_entries — both ConfigEntry (data) AND ConfigFlow (config flow).
    ce = types.ModuleType("homeassistant.config_entries")

    class ConfigEntry:
        def __init__(self, *, entry_id="test", options=None, title="Test", data=None):
            self.entry_id = entry_id
            self.options = options or {}
            self.title = title
            self.data = data or {}

        def async_on_unload(self, fn):
            return None

        def add_update_listener(self, fn):
            return None

    class ConfigFlow:
        VERSION = 1

        async def async_show_form(self, *, step_id, data_schema=None, **kwargs):
            return {"type": "form", "step_id": step_id,
                    "data_schema": data_schema, **kwargs}

        async def async_create_entry(self, *, title, data):
            return {"type": "create_entry", "title": title, "data": data}

        def async_abort(self, *, reason):
            return {"type": "abort", "reason": reason}

        def _async_current_entries(self):
            return []

    class OptionsFlow:
        def __init__(self, entry):
            self.entry = entry

        async def async_show_form(self, *, step_id, data_schema=None, **kwargs):
            return {"type": "form", "step_id": step_id,
                    "data_schema": data_schema, **kwargs}

        async def async_create_entry(self, *, title, data):
            return {"type": "create_entry", "title": title, "data": data}

    ce.ConfigEntry = ConfigEntry
    ce.ConfigFlow = ConfigFlow
    ce.ConfigFlowResult = dict
    ce.OptionsFlow = OptionsFlow
    sys.modules["homeassistant.config_entries"] = ce

    # const
    const = types.ModuleType("homeassistant.const")
    const.PERCENTAGE = "%"
    const.Platform = types.SimpleNamespace(
        SENSOR="sensor", BINARY_SENSOR="binary_sensor", SWITCH="switch",
    )

    class _Unit:
        CELSIUS = "°C"
        FAHRENHEIT = "°F"
        SECONDS = "s"
        BYTES = "B"
        MEGAHERTZ = "MHz"
        KILOBYTES_PER_SECOND = "kB/s"

    const.UnitOfDataRate = _Unit
    const.UnitOfFrequency = _Unit
    const.UnitOfInformation = _Unit
    const.UnitOfTemperature = _Unit
    const.UnitOfTime = _Unit
    sys.modules["homeassistant.const"] = const

    # core
    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:  # pragma: no cover
        pass

    class Config:  # pragma: no cover
        def as_dict(self):
            return {}

    HomeAssistant.config = Config()
    core.HomeAssistant = HomeAssistant
    core.callback = lambda f: f
    sys.modules["homeassistant.core"] = core

    # exceptions
    exc_mod = types.ModuleType("homeassistant.exceptions")

    class ConfigEntryNotReady(Exception):
        pass

    exc_mod.ConfigEntryNotReady = ConfigEntryNotReady
    sys.modules["homeassistant.exceptions"] = exc_mod

    # helpers.update_coordinator — DataUpdateCoordinator AND CoordinatorEntity
    uc = types.ModuleType("homeassistant.helpers.update_coordinator")
    _T = TypeVar("_T")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator(Generic[_T]):
        def __init__(self, hass, logger, *, name, update_interval):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None
            self.last_update_success = True

        async def async_config_entry_first_refresh(self):
            return await self._async_update_data()

        async def _async_update_data(self):
            return self.data

        async def async_add_executor_job(self, fn, *args):
            return fn(*args)

    class CoordinatorEntity(Generic[_T]):
        def __init__(self, coordinator):
            self.coordinator = coordinator

        @property
        def available(self):
            return self.coordinator.last_update_success

    uc.DataUpdateCoordinator = DataUpdateCoordinator
    uc.CoordinatorEntity = CoordinatorEntity
    uc.UpdateFailed = UpdateFailed
    sys.modules["homeassistant.helpers.update_coordinator"] = uc

    # helpers.device_registry
    dr = types.ModuleType("homeassistant.helpers.device_registry")

    class DeviceInfo:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    dr.DeviceInfo = DeviceInfo
    sys.modules["homeassistant.helpers.device_registry"] = dr

    # helpers.aiohttp_client
    aiohttp_h = types.ModuleType("homeassistant.helpers.aiohttp_client")

    def async_get_clientsession(hass):
        import aiohttp
        return aiohttp.ClientSession()

    aiohttp_h.async_get_clientsession = async_get_clientsession
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_h

    # helpers.entity_platform
    ep = types.ModuleType("homeassistant.helpers.entity_platform")

    def async_add_entities(entities, update_before_add=False):
        pass

    ep.AddEntitiesCallback = type("AddEntitiesCallback", (), {})
    ep.async_add_entities = async_add_entities
    sys.modules["homeassistant.helpers.entity_platform"] = ep

    # components.sensor
    sensor = types.ModuleType("homeassistant.components.sensor")

    class SensorDeviceClass:
        BATTERY = "battery"
        DATA_SIZE = "data_size"
        DATA_RATE = "data_rate"
        DURATION = "duration"
        FREQUENCY = "frequency"
        TEMPERATURE = "temperature"

    class SensorStateClass:
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"

    class SensorEntityDescription:
        """Stub matching HA's @dataclass SensorEntityDescription shape.

        The integration subclasses this with another @dataclass that adds
        ``value_fn``; the subclass's generated ``__init__`` calls ours with
        ``**kwargs``, so we just stash everything.
        """

        key: str | None = None
        translation_key: str | None = None
        name: str | None = None
        icon: str | None = None
        device_class: str | None = None
        state_class: str | None = None
        native_unit_of_measurement: str | None = None
        suggested_display_precision: int | None = None

        def __init__(self, *, key=None, translation_key=None, name=None,
                     icon=None, device_class=None, state_class=None,
                     native_unit_of_measurement=None,
                     suggested_display_precision=None, **_extra):
            self.key = key
            self.translation_key = translation_key
            self.name = name
            self.icon = icon
            self.device_class = device_class
            self.state_class = state_class
            self.native_unit_of_measurement = native_unit_of_measurement
            self.suggested_display_precision = suggested_display_precision

    class SensorEntity:
        _attr_has_entity_name = False
        _attr_device_class = None
        _attr_state_class = None
        _attr_native_unit_of_measurement = None
        _attr_suggested_display_precision = None
        _attr_unique_id = None
        _attr_translation_key = None
        _attr_translation_placeholders = None
        _attr_name = None
        entity_description = None

        def __init__(self):
            self.hass = None

        @property
        def native_value(self):
            return None

        @property
        def extra_state_attributes(self):
            return None

        @property
        def available(self):
            return True

    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorStateClass = SensorStateClass
    sensor.SensorEntityDescription = SensorEntityDescription
    sensor.SensorEntity = SensorEntity
    sys.modules["homeassistant.components.sensor"] = sensor

    # components.binary_sensor
    bs = types.ModuleType("homeassistant.components.binary_sensor")

    class BinarySensorDeviceClass:
        RUNNING = "running"

    class BinarySensorEntity:
        _attr_has_entity_name = False
        _attr_unique_id = None
        _attr_device_info = None
        _attr_translation_key = None
        _attr_name = None

        def __init__(self):
            self.hass = None

        @property
        def is_on(self):
            return None

        @property
        def available(self):
            return True

        @property
        def extra_state_attributes(self):
            return None

        async def async_update(self):
            pass

        def async_write_ha_state(self):
            pass

    bs.BinarySensorDeviceClass = BinarySensorDeviceClass
    bs.BinarySensorEntity = BinarySensorEntity
    sys.modules["homeassistant.components.binary_sensor"] = bs

    # components.switch
    sw = types.ModuleType("homeassistant.components.switch")

    class SwitchDeviceClass:
        SWITCH = "switch"

    class SwitchEntity:
        _attr_has_entity_name = False
        _attr_unique_id = None
        _attr_device_info = None
        _attr_translation_key = None
        _attr_name = None

        def __init__(self):
            self.hass = None

        @property
        def is_on(self):
            return None

        @property
        def available(self):
            return True

        async def async_turn_on(self, **kwargs):
            pass

        async def async_turn_off(self, **kwargs):
            pass

        def async_write_ha_state(self):
            pass

    sw.SwitchDeviceClass = SwitchDeviceClass
    sw.SwitchEntity = SwitchEntity
    sys.modules["homeassistant.components.switch"] = sw

    # diagnostics
    diag = types.ModuleType("homeassistant.components.diagnostics")

    async def async_redact_data(data, keys):
        if isinstance(data, dict):
            return {k: ("[REDACTED]" if k in keys else v) for k, v in data.items()}
        return data

    diag.async_redact_data = async_redact_data
    sys.modules["homeassistant.components.diagnostics"] = diag


if not _USE_REAL_HA:
    _install_ha_stubs()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_snapshot() -> dict:
    """A deterministic system snapshot for sensor value assertions."""
    return {
        "ts": 1_700_000_000.0,
        "boot_time": 1_700_000_000.0 - 86_400 * 3,
        "uptime_seconds": 86_400 * 3,
        "hostname": "testhost",
        "os": "Debian GNU/Linux 12",
        "kernel": "6.1.0-21-amd64",
        "processes": 234,
        "cpu": {
            "percent": 42.5,
            "per_core": [10.0, 20.0, 30.0, 40.0],
            "load": [0.5, 0.6, 0.7],
            "freq_mhz": 2400.0,
            "temp": 55.0,
            "logical_cores": 4,
            "physical_cores": 2,
        },
        "memory": {
            "percent": 60.0,
            "used": 6 * 1024 * 1024 * 1024,
            "total": 16 * 1024 * 1024 * 1024,
            "free": 10 * 1024 * 1024 * 1024,
            "swap_percent": 10.0,
            "swap_used": 200 * 1024 * 1024,
            "swap_total": 2 * 1024 * 1024 * 1024,
        },
        "disks": [
            {"mount": "/", "device": "/dev/sda1", "fstype": "ext4",
             "total": 500 * 1024**3, "used": 200 * 1024**3, "free": 300 * 1024**3,
             "percent": 40.0},
        ],
        "network": {
            "interfaces": [
                {"name": "eth0", "is_up": True, "speed_mbps": 1000, "mtu": 1500},
                {"name": "wlan0", "is_up": False, "speed_mbps": 0, "mtu": 1500},
            ],
            "bytes_sent": 1_000_000,
            "bytes_recv": 10_000_000,
            "packets_sent": 1000,
            "packets_recv": 10_000,
            "up_kbps": 50.0,
            "down_kbps": 800.0,
        },
        "temperatures": [
            {"label": "CPU", "group": "coretemp", "current": 55.0,
             "high": 90.0, "critical": 100.0},
        ],
    }


@pytest.fixture
def config_entry():
    from homeassistant.config_entries import ConfigEntry
    return ConfigEntry(entry_id="test_entry", options={}, title="Test")