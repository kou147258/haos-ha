"""Config flow for HAOS Dashboard."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import (
    CONF_REFRESH_INTERVAL,
    CONF_TEMP_UNIT,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TEMP_UNIT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    TEMP_UNITS,
)


class FnOSDashboardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-step config flow: just confirm the integration is enabled.

    There is no host / port / token to validate because the integration polls
    psutil on the host where HA itself runs. The only knob the user must
    confirm up-front is whether they want the default name.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the single step of the config flow."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {vol.Optional("name", default=DEFAULT_NAME): str}
                ),
            )

        return self.async_create_entry(
            title=user_input.get("name", DEFAULT_NAME),
            data={},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow handler."""
        return FnOSDashboardOptionsFlow(config_entry)


class FnOSDashboardOptionsFlow(OptionsFlow):
    """Options flow: refresh interval and temperature unit."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show / apply the options form."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.entry.options.get(
            CONF_REFRESH_INTERVAL,
            int(DEFAULT_SCAN_INTERVAL.total_seconds()),
        )
        current_temp_unit = self.entry.options.get(
            CONF_TEMP_UNIT, DEFAULT_TEMP_UNIT
        )
        if current_temp_unit not in TEMP_UNITS:
            current_temp_unit = DEFAULT_TEMP_UNIT

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_REFRESH_INTERVAL,
                        default=current_interval,
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                    vol.Optional(
                        CONF_TEMP_UNIT,
                        default=current_temp_unit,
                    ): vol.In(list(TEMP_UNITS)),
                }
            ),
        )