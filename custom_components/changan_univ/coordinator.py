"""Update coordinator for the Changan UNI-V integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ChanganApi, ChanganApiError, ChanganAuthError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import VehicleStatus

_LOGGER = logging.getLogger(__name__)


class ChanganCoordinator(DataUpdateCoordinator[VehicleStatus]):
    """Coordinate one safe cloud poll for all vehicle entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: ChanganApi,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=int(entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            ),
            always_update=False,
        )
        self.api = api
        self.auth_required = not api.configured

    async def _async_update_data(self) -> VehicleStatus:
        try:
            status = await self.api.async_get_status()
            self.auth_required = False
            return status
        except ChanganAuthError as err:
            self.auth_required = True
            raise ConfigEntryAuthFailed("Changan account authentication is required") from err
        except ChanganApiError as err:
            raise UpdateFailed(str(err)) from err
