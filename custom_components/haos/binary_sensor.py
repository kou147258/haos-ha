"""Binary sensor: companion display add-on running."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .addon import get_addon_info
from .const import ADDON_SLUG, DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the display-running binary sensor."""
    async_add_entities([DisplayRunningBinarySensor(hass, entry)])


class DisplayRunningBinarySensor(BinarySensorEntity):
    """Whether the companion /dev/fb0 add-on is currently running."""

    _attr_has_entity_name = True
    _attr_translation_key = "display_running"
    _attr_name = "Display running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_display_running"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model="System Monitor",
            name=entry.title,
            entry_type=None,
        )
        self._is_on: bool | None = None
        self._available: bool = True

    async def async_update(self) -> None:
        """Query the Supervisor for the add-on state."""
        info = await get_addon_info(self.hass)
        if info is None:
            self._available = False
            self._is_on = None
            return
        self._available = True
        self._is_on = info.get("state") == "started"

    @property
    def is_on(self) -> bool | None:
        return self._is_on

    @property
    def available(self) -> bool:
        return self._available

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return {"addon_slug": ADDON_SLUG}