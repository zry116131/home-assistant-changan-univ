"""Shared entity implementation for Changan UNI-V."""

from __future__ import annotations

from hashlib import sha256

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ChanganConfigEntry
from .const import ATTRIBUTION, CONF_DISPLAY_NAME, DEFAULT_DISPLAY_NAME, DOMAIN
from .coordinator import ChanganCoordinator


class ChanganEntity(CoordinatorEntity[ChanganCoordinator]):
    """Base class that never exposes the raw vehicle identifier."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        entry: ChanganConfigEntry,
        coordinator: ChanganCoordinator,
        entity_key: str,
    ) -> None:
        super().__init__(coordinator)
        privacy_id = sha256(entry.entry_id.encode()).hexdigest()[:16]
        self._attr_unique_id = f"{privacy_id}_{entity_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, privacy_id)},
            name=str(entry.data.get(CONF_DISPLAY_NAME, DEFAULT_DISPLAY_NAME)),
            manufacturer="长安汽车",
            model="UNI-V",
        )
