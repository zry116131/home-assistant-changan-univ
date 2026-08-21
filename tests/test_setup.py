"""Runtime setup and entity tests for Changan UNI-V."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.changan_univ import async_migrate_entry
from custom_components.changan_univ.api import ChanganAuthError
from custom_components.changan_univ.const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_DISPLAY_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from custom_components.changan_univ.models import VehicleStatus


def _entry_data(configured: bool) -> dict[str, str | int]:
    data: dict[str, str | int] = {
        CONF_DISPLAY_NAME: DEFAULT_DISPLAY_NAME,
        CONF_SCAN_INTERVAL: 500,
    }
    if configured:
        data.update(
            {
                CONF_ACCESS_TOKEN: "test-access",
                CONF_CAR_ID: "test-private-car-id",
            }
        )
    return data


def _entry(configured: bool) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_DISPLAY_NAME,
        unique_id=DOMAIN,
        data=_entry_data(configured),
    )


def _states_by_unique_suffix(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, str]:
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    result: dict[str, str] = {}
    for registry_entry in entries:
        state = hass.states.get(registry_entry.entity_id)
        assert state is not None
        result[registry_entry.unique_id[17:]] = state.state
    return result


async def test_legacy_high_frequency_polling_migrates_to_safe_default(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_DISPLAY_NAME,
        unique_id=DOMAIN,
        version=1,
        data={CONF_DISPLAY_NAME: DEFAULT_DISPLAY_NAME, CONF_SCAN_INTERVAL: 120},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 2
    assert entry.data[CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL == 500


async def test_migration_preserves_supported_polling_interval(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_DISPLAY_NAME,
        unique_id=DOMAIN,
        version=1,
        data={CONF_DISPLAY_NAME: DEFAULT_DISPLAY_NAME, CONF_SCAN_INTERVAL: 600},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 2
    assert entry.data[CONF_SCAN_INTERVAL] == 600
    assert MIN_SCAN_INTERVAL == 300
    assert MAX_SCAN_INTERVAL == 600


async def test_migration_replaces_invalid_polling_interval(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_DISPLAY_NAME,
        unique_id=DOMAIN,
        version=1,
        data={CONF_DISPLAY_NAME: DEFAULT_DISPLAY_NAME, CONF_SCAN_INTERVAL: "invalid"},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 2
    assert entry.data[CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL


async def test_pending_setup_creates_only_safe_unavailable_entities(
    hass: HomeAssistant,
) -> None:
    hass.config.language = "en"
    entry = _entry(configured=False)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    states = _states_by_unique_suffix(hass, entry)
    assert len(states) == 16
    assert states["authentication_required"] == STATE_ON
    assert set(states.values()) == {STATE_ON, STATE_UNAVAILABLE}
    registry_entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    auth_entry = next(
        item for item in registry_entries if item.unique_id.endswith("authentication_required")
    )
    auth_state = hass.states.get(auth_entry.entity_id)
    assert auth_state is not None
    assert "Account authentication required" in auth_state.attributes["friendly_name"]
    zh_translations = await async_get_translations(
        hass,
        "zh-Hans",
        "entity",
        integrations={DOMAIN},
    )
    assert (
        zh_translations["component.changan_univ.entity.binary_sensor.authentication_required.name"]
        == "账户需要认证"
    )


async def test_configured_setup_populates_read_only_entities(
    hass: HomeAssistant,
) -> None:
    entry = _entry(configured=True)
    entry.add_to_hass(hass)
    status = VehicleStatus(
        observed_at="2026-08-21T00:00:00+00:00",
        fuel_percent=66,
        remaining_range_km=510,
        engine_running=False,
        air_conditioner=True,
        battery_voltage=12.6,
    )

    with patch(
        "custom_components.changan_univ.api.ChanganApi.async_get_status",
        AsyncMock(return_value=status),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    states = _states_by_unique_suffix(hass, entry)
    assert len(states) == 16
    assert states["authentication_required"] == STATE_OFF
    assert states["fuel_percent"] == "66"
    assert states["remaining_range"] == "510"
    assert states["engine_running"] == STATE_OFF
    assert states["air_conditioner"] == STATE_ON
    assert states["battery_voltage"] == "12.6"


async def test_auth_failure_marks_entry_and_starts_reauthentication(
    hass: HomeAssistant,
) -> None:
    entry = _entry(configured=True)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.changan_univ.api.ChanganApi.async_get_status",
        AsyncMock(side_effect=ChanganAuthError("sanitized auth failure")),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    assert flows[0]["context"]["entry_id"] == entry.entry_id


async def test_periodic_auth_failure_starts_reauthentication(
    hass: HomeAssistant,
) -> None:
    entry = _entry(configured=True)
    entry.add_to_hass(hass)
    status = VehicleStatus(
        observed_at="2026-08-21T00:00:00+00:00",
        fuel_percent=66,
    )
    fetch = AsyncMock(side_effect=[status, ChanganAuthError("sanitized periodic auth failure")])

    with patch(
        "custom_components.changan_univ.api.ChanganApi.async_get_status",
        fetch,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    assert entry.runtime_data.coordinator.auth_required is True
