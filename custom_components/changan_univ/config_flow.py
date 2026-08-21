"""Config flow for Changan UNI-V."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_DISPLAY_NAME,
    CONF_IS_NEV,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_VCS_APP_ID,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


def _masked_text() -> selector.TextSelector:
    return selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    )


class ChanganConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Changan UNI-V setup and session reauthentication."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_DISPLAY_NAME],
                data=user_input,
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DISPLAY_NAME, default=DEFAULT_DISPLAY_NAME): str,
                    vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            updated = dict(entry.data)
            updated.update(user_input)
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(entry, data_updates=updated)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._session_schema(entry.data),
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        del entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        if user_input is not None:
            updated = dict(entry.data)
            updated.update(user_input)
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(entry, data_updates=updated)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self._session_schema(entry.data),
        )

    @staticmethod
    def _session_schema(current: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(
                    CONF_ACCESS_TOKEN,
                    default="",
                ): _masked_text(),
                vol.Required(
                    CONF_CAR_ID,
                    default="",
                ): _masked_text(),
                vol.Optional(
                    CONF_REFRESH_TOKEN,
                    default="",
                ): _masked_text(),
                vol.Optional(
                    CONF_VCS_APP_ID,
                    default="",
                ): _masked_text(),
                vol.Optional(
                    CONF_IS_NEV,
                    default=current.get(CONF_IS_NEV, ""),
                ): str,
            }
        )
