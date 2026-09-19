"""Switch entity: toggle the companion display add-on on / off."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .addon import (
    addon_installed,
    async_start_addon,
    async_stop_addon,
    get_addon_info,
)
from .const import ADDON_SLUG, DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the display-enabled switch."""
    async_add_entities([DisplaySwitch(hass, entry)])


class DisplaySwitch(SwitchEntity):
    """Start/stop the companion /dev/fb0 add-on."""

    _attr_has_entity_name = True
    _attr_translation_key = "display_enabled"
    _attr_name = "Display enabled"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_display_enabled"
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
        """Query Supervisor for current state."""
        if not await addon_installed(self.hass):
            self._available = False
            self._is_on = None
            return
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

    async def async_turn_on(self, **kwargs) -> None:  # noqa: ARG002
        """Start the add-on."""
        ok = await async_start_addon(self.hass)
        if not ok:
            _LOGGER.warning(
                "Failed to start add-on %s; check Supervisor logs",
                ADDON_SLUG,
            )
            return
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:  # noqa: ARG002
        """Stop the add-on."""
        ok = await async_stop_addon(self.hass)
        if not ok:
            _LOGGER.warning(
                "Failed to stop add-on %s; check Supervisor logs",
                ADDON_SLUG,
            )
            return
        self._is_on = False
        self.async_write_ha_state()