"""Config-flow tests for Changan UNI-V."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.changan_univ.const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_DISPLAY_NAME,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_DISPLAY_NAME,
    DOMAIN,
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
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_DISPLAY_NAME,
        unique_id=DOMAIN,
        data={
            CONF_DISPLAY_NAME: DEFAULT_DISPLAY_NAME,
            CONF_SCAN_INTERVAL: 120,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_reconfigure_does_not_prefill_stored_secrets(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
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
    entry.add_to_hass(hass)

    with patch(
        "custom_components.changan_univ.api.ChanganApi.async_get_status",
        AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        )

    assert result["type"] is FlowResultType.FORM
    schema: dict[Any, Any] = result["data_schema"].schema
    secret_defaults = {
        marker.schema: marker.default()
        for marker in schema
        if marker.schema in {CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_CAR_ID}
    }
    assert secret_defaults == {
        CONF_ACCESS_TOKEN: "",
        CONF_REFRESH_TOKEN: "",
        CONF_CAR_ID: "",
    }
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reauthentication_updates_and_reloads_session(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_DISPLAY_NAME,
        unique_id=DOMAIN,
        data={
            CONF_DISPLAY_NAME: DEFAULT_DISPLAY_NAME,
            CONF_SCAN_INTERVAL: 120,
            CONF_ACCESS_TOKEN: "expired-access",
            CONF_REFRESH_TOKEN: "expired-refresh",
            CONF_CAR_ID: "private-car-id",
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.changan_univ.api.ChanganApi.async_get_status",
        AsyncMock(),
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
            {
                CONF_ACCESS_TOKEN: "new-access",
                CONF_CAR_ID: "private-car-id",
                CONF_REFRESH_TOKEN: "new-refresh",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "new-access"
    assert entry.data[CONF_REFRESH_TOKEN] == "new-refresh"
    await hass.config_entries.async_unload(entry.entry_id)
