"""Changan UNI-V integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import ChanganApi
from .captcha import async_register_captcha_view
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    PLATFORMS,
)
from .coordinator import ChanganCoordinator


@dataclass(slots=True)
class ChanganRuntimeData:
    """Runtime objects for a Changan config entry."""

    api: ChanganApi
    coordinator: ChanganCoordinator


ChanganConfigEntry = ConfigEntry[ChanganRuntimeData]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration-level ephemeral captcha view."""
    del config
    async_register_captcha_view(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ChanganConfigEntry) -> bool:
    """Move legacy high-frequency polling entries to the safe default."""
    if entry.version >= 2:
        return True

    updated = dict(entry.data)
    try:
        scan_interval = int(updated.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    except (TypeError, ValueError):
        scan_interval = None
    if scan_interval is None or not MIN_SCAN_INTERVAL <= scan_interval <= MAX_SCAN_INTERVAL:
        updated[CONF_SCAN_INTERVAL] = DEFAULT_SCAN_INTERVAL

    hass.config_entries.async_update_entry(entry, data=updated, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ChanganConfigEntry) -> bool:
    """Set up Changan UNI-V from a config entry."""
    async_register_captcha_view(hass)

    def _session_updated(updated: dict) -> None:
        hass.config_entries.async_update_entry(entry, data=updated)

    api = ChanganApi(async_get_clientsession(hass), entry.data, _session_updated)
    coordinator = ChanganCoordinator(hass, entry, api)
    entry.runtime_data = ChanganRuntimeData(api=api, coordinator=coordinator)

    configured = all(
        isinstance(entry.data.get(key), str) and bool(entry.data[key])
        for key in (CONF_ACCESS_TOKEN, CONF_CAR_ID)
    )
    if configured:
        await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChanganConfigEntry) -> bool:
    """Unload a Changan UNI-V config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
