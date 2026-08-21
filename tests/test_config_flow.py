"""Config-flow tests for Changan UNI-V."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.changan_univ.auth import CaptchaChallenge, ChanganAuthSession
from custom_components.changan_univ.const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_CLIENT_FINGERPRINT,
    CONF_DISPLAY_NAME,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_VCS_APP_ID,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_VCS_APP_ID,
    DOMAIN,
)

TEST_CAPTCHA_IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_DISPLAY_NAME,
        unique_id=DOMAIN,
        data={
            CONF_DISPLAY_NAME: DEFAULT_DISPLAY_NAME,
            CONF_SCAN_INTERVAL: 120,
            CONF_ACCESS_TOKEN: "stored-access-must-not-be-returned",
            CONF_REFRESH_TOKEN: "stored-refresh-must-not-be-returned",
            CONF_CAR_ID: "stored-car-id-must-not-be-returned",
        },
    )


async def test_user_flow_creates_pending_read_only_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_DISPLAY_NAME: DEFAULT_DISPLAY_NAME,
            CONF_SCAN_INTERVAL: 120,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DEFAULT_DISPLAY_NAME
    assert result["data"] == {
        CONF_DISPLAY_NAME: DEFAULT_DISPLAY_NAME,
        CONF_SCAN_INTERVAL: 120,
    }
    assert CONF_ACCESS_TOKEN not in result["data"]
    assert CONF_CAR_ID not in result["data"]


async def test_second_entry_is_rejected(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_reconfigure_never_prefills_stored_secrets(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {
        "reconfigure_account",
        "reconfigure_settings",
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "reconfigure_account"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure_account"
    schema_keys = {marker.schema for marker in result["data_schema"].schema}
    assert schema_keys == {"phone"}
    serialized = repr(result)
    assert "stored-access-must-not-be-returned" not in serialized
    assert "stored-refresh-must-not-be-returned" not in serialized
    assert "stored-car-id-must-not-be-returned" not in serialized


async def test_reauthentication_uses_captcha_sms_and_stores_minimum_session(
    hass: HomeAssistant,
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    captcha = AsyncMock(
        return_value=CaptchaChallenge(
            graphics_key="ephemeral-graphics-key",
            image_base64=TEST_CAPTCHA_IMAGE,
        )
    )
    send_sms = AsyncMock()
    login = AsyncMock(
        return_value=ChanganAuthSession(
            access_token="new-access",
            refresh_token="new-refresh",
            car_id="new-private-car-id",
        )
    )

    with (
        patch(
            "custom_components.changan_univ.config_flow.generate_fingerprint",
            return_value="synthetic-client-fingerprint",
        ),
        patch(
            "custom_components.changan_univ.auth.ChanganAuthClient.async_get_captcha",
            captcha,
        ),
        patch(
            "custom_components.changan_univ.auth.ChanganAuthClient.async_send_sms",
            send_sms,
        ),
        patch(
            "custom_components.changan_univ.auth.ChanganAuthClient.async_login",
            login,
        ),
        patch(
            "custom_components.changan_univ.api.ChanganApi.async_get_status",
            AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"phone": "13800138000"},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "graphics_captcha"
        captcha_url = result["description_placeholders"]["captcha_url"]
        assert captcha_url.startswith("/api/changan_univ/captcha/")
        assert "13800138000" not in repr(result)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"graphics_code": "1234"},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "sms_code"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"sms_code": "654321"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    captcha.assert_awaited_once_with("13800138000")
    send_sms.assert_awaited_once_with(
        "13800138000",
        "1234",
        "ephemeral-graphics-key",
    )
    login.assert_awaited_once_with("13800138000", "654321")
    assert entry.data[CONF_ACCESS_TOKEN] == "new-access"
    assert entry.data[CONF_REFRESH_TOKEN] == "new-refresh"
    assert entry.data[CONF_CAR_ID] == "new-private-car-id"
    assert entry.data[CONF_VCS_APP_ID] == DEFAULT_VCS_APP_ID
    assert entry.data[CONF_CLIENT_FINGERPRINT] == "synthetic-client-fingerprint"
    assert "phone" not in entry.data
    assert "graphics_code" not in entry.data
    assert "sms_code" not in entry.data


async def test_invalid_phone_is_rejected_without_network_request(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    captcha = AsyncMock()

    with patch(
        "custom_components.changan_univ.auth.ChanganAuthClient.async_get_captcha",
        captcha,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"phone": "123"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"phone": "invalid_phone"}
    captcha.assert_not_awaited()
