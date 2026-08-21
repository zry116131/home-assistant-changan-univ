"""Config flow for Changan UNI-V."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ChanganApi, ChanganApiError, ChanganAuthError
from .auth import (
    CaptchaChallenge,
    ChanganAuthClient,
    ChanganAuthSession,
    ChanganLoginConnectionError,
    ChanganLoginRejected,
    generate_fingerprint,
)
from .captcha import (
    async_register_captcha_view,
    async_remove_captcha,
    async_store_captcha,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_CLIENT_FINGERPRINT,
    CONF_DISPLAY_NAME,
    CONF_IS_NEV,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_VCS_APP_ID,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_IS_NEV,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VCS_APP_ID,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

FIELD_PHONE = "phone"
FIELD_GRAPHICS_CODE = "graphics_code"
FIELD_SMS_CODE = "sms_code"

_PHONE_PATTERN = re.compile(r"^1\d{10}$")
_GRAPHICS_CODE_PATTERN = re.compile(r"^\d{4}$")
_SMS_CODE_PATTERN = re.compile(r"^\d{4,8}$")


def _secret_text(*, autocomplete: str | None = None) -> selector.TextSelector:
    return selector.TextSelector(
        selector.TextSelectorConfig(
            type=selector.TextSelectorType.PASSWORD,
            autocomplete=autocomplete,
        )
    )


def _phone_text() -> selector.TextSelector:
    return selector.TextSelector(
        selector.TextSelectorConfig(
            type=selector.TextSelectorType.TEL,
            autocomplete="tel",
        )
    )


class ChanganConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Changan UNI-V setup and SMS reauthentication."""

    VERSION = 1

    def __init__(self) -> None:
        self._auth_client: ChanganAuthClient | None = None
        self._client_fingerprint = ""
        self._phone = ""
        self._graphics_key = ""
        self._captcha_token: str | None = None
        self._captcha_url = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create the read-only entry before account authentication."""
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
            data_schema=self._settings_schema({}),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose between account authentication and ordinary settings."""
        del user_input
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["reconfigure_account", "reconfigure_settings"],
        )

    async def async_step_reconfigure_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start SMS authentication from a reconfigure flow."""
        return await self._async_account_step("reconfigure_account", user_input)

    async def async_step_reconfigure_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update display and polling settings without touching credentials."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            updated = dict(entry.data)
            updated.update(user_input)
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(entry, data_updates=updated)
        return self.async_show_form(
            step_id="reconfigure_settings",
            data_schema=self._settings_schema(entry.data),
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start an expired-session flow."""
        del entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the phone number without exposing stored session values."""
        return await self._async_account_step("reauth_confirm", user_input)

    async def _async_account_step(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            phone = str(user_input.get(FIELD_PHONE, "")).strip()
            if not _PHONE_PATTERN.fullmatch(phone):
                errors[FIELD_PHONE] = "invalid_phone"
            else:
                self._phone = phone
                entry = self._account_entry()
                fingerprint = entry.data.get(CONF_CLIENT_FINGERPRINT)
                if not isinstance(fingerprint, str) or not fingerprint:
                    fingerprint = generate_fingerprint()
                self._client_fingerprint = fingerprint
                self._auth_client = ChanganAuthClient(
                    async_get_clientsession(self.hass),
                    fingerprint,
                )
                try:
                    challenge = await self._auth_client.async_get_captcha(phone)
                    self._store_challenge(challenge)
                except ChanganLoginRejected as err:
                    errors["base"] = _rejection_error(err, "request_rejected")
                except (ChanganLoginConnectionError, ValueError):
                    errors["base"] = "cannot_connect"
                else:
                    return await self.async_step_graphics_captcha()

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(FIELD_PHONE): _phone_text()}),
            errors=errors,
        )

    async def async_step_graphics_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate the four-digit image captcha and request an SMS."""
        errors: dict[str, str] = {}
        if not self._phone or not self._graphics_key or self._auth_client is None:
            return self.async_abort(reason="authentication_flow_expired")

        if user_input is not None:
            graphics_code = str(user_input.get(FIELD_GRAPHICS_CODE, "")).strip()
            if not _GRAPHICS_CODE_PATTERN.fullmatch(graphics_code):
                errors[FIELD_GRAPHICS_CODE] = "invalid_graphics_code"
            else:
                try:
                    await self._auth_client.async_send_sms(
                        self._phone,
                        graphics_code,
                        self._graphics_key,
                    )
                except ChanganLoginRejected as err:
                    errors["base"] = _rejection_error(err, "invalid_graphics_code")
                except ChanganLoginConnectionError:
                    errors["base"] = "cannot_connect"
                else:
                    self._clear_captcha()
                    return await self.async_step_sms_code()

        return self.async_show_form(
            step_id="graphics_captcha",
            data_schema=vol.Schema(
                {vol.Required(FIELD_GRAPHICS_CODE): _secret_text(autocomplete="one-time-code")}
            ),
            errors=errors,
            description_placeholders={"captcha_url": self._captcha_url},
        )

    async def async_step_sms_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Exchange the SMS code and validate a read-only vehicle session."""
        errors: dict[str, str] = {}
        if not self._phone or self._auth_client is None:
            return self.async_abort(reason="authentication_flow_expired")

        if user_input is not None:
            sms_code = str(user_input.get(FIELD_SMS_CODE, "")).strip()
            if not _SMS_CODE_PATTERN.fullmatch(sms_code):
                errors[FIELD_SMS_CODE] = "invalid_sms_code"
            else:
                try:
                    auth_session = await self._auth_client.async_login(self._phone, sms_code)
                    result = await self._async_finish_auth(auth_session)
                except ChanganLoginRejected as err:
                    errors["base"] = _rejection_error(err, "invalid_sms_code")
                except (ChanganLoginConnectionError, ChanganApiError):
                    errors["base"] = "cannot_connect"
                else:
                    self._clear_sensitive_flow_state()
                    return result

        return self.async_show_form(
            step_id="sms_code",
            data_schema=vol.Schema(
                {vol.Required(FIELD_SMS_CODE): _secret_text(autocomplete="one-time-code")}
            ),
            errors=errors,
        )

    async def _async_finish_auth(self, session: ChanganAuthSession) -> ConfigFlowResult:
        entry = self._account_entry()
        updated = dict(entry.data)
        updated.update(
            {
                CONF_ACCESS_TOKEN: session.access_token,
                CONF_REFRESH_TOKEN: session.refresh_token,
                CONF_CAR_ID: session.car_id,
                CONF_CLIENT_FINGERPRINT: self._client_fingerprint,
                CONF_IS_NEV: DEFAULT_IS_NEV,
                CONF_VCS_APP_ID: DEFAULT_VCS_APP_ID,
            }
        )

        validation_updates: dict[str, Any] = {}
        api = ChanganApi(
            async_get_clientsession(self.hass),
            updated,
            validation_updates.update,
        )
        try:
            await api.async_get_status()
        except ChanganAuthError as err:
            raise ChanganLoginRejected("invalid_session") from err
        if validation_updates:
            updated.update(validation_updates)

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_mismatch()
        return self.async_update_reload_and_abort(entry, data_updates=updated)

    def _account_entry(self) -> config_entries.ConfigEntry:
        if self.context["source"] == config_entries.SOURCE_REAUTH:
            return self._get_reauth_entry()
        return self._get_reconfigure_entry()

    def _store_challenge(self, challenge: CaptchaChallenge) -> None:
        async_register_captcha_view(self.hass)
        self._clear_captcha()
        self._graphics_key = challenge.graphics_key
        self._captcha_token, self._captcha_url = async_store_captcha(
            self.hass,
            challenge.image_base64,
        )

    def _clear_captcha(self) -> None:
        async_remove_captcha(self.hass, self._captcha_token)
        self._captcha_token = None
        self._captcha_url = ""
        self._graphics_key = ""

    def _clear_sensitive_flow_state(self) -> None:
        self._clear_captcha()
        self._phone = ""
        self._auth_client = None

    @staticmethod
    def _settings_schema(current: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(
                    CONF_DISPLAY_NAME,
                    default=current.get(CONF_DISPLAY_NAME, DEFAULT_DISPLAY_NAME),
                ): str,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )


def _rejection_error(error: ChanganLoginRejected, fallback: str) -> str:
    if error.reason == "rate_limited" or error.code == "429":
        return "rate_limited"
    return fallback
