"""Changan UNI-V integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ChanganApi
from .const import CONF_ACCESS_TOKEN, CONF_CAR_ID, PLATFORMS
from .coordinator import ChanganCoordinator


@dataclass(slots=True)
class ChanganRuntimeData:
    """Runtime objects for a Changan config entry."""

    api: ChanganApi
    coordinator: ChanganCoordinator


ChanganConfigEntry = ConfigEntry[ChanganRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: ChanganConfigEntry) -> bool:
    """Set up Changan UNI-V from a config entry."""

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
