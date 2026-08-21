"""Binary sensor entities for Changan UNI-V."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ChanganConfigEntry
from .entity import ChanganEntity
from .models import VehicleStatus


@dataclass(frozen=True, kw_only=True)
class ChanganBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[VehicleStatus], bool | None]


BINARY_SENSORS: tuple[ChanganBinarySensorDescription, ...] = (
    ChanganBinarySensorDescription(
        key="engine_running",
        translation_key="engine_running",
        value_fn=lambda s: s.engine_running,
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    ChanganBinarySensorDescription(
        key="air_conditioner",
        translation_key="air_conditioner",
        value_fn=lambda s: s.air_conditioner,
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChanganConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    del hass
    entities: list[BinarySensorEntity] = [
        ChanganAuthenticationRequiredBinarySensor(entry),
        *(ChanganStatusBinarySensor(entry, description) for description in BINARY_SENSORS),
    ]
    async_add_entities(entities)


class ChanganAuthenticationRequiredBinarySensor(ChanganEntity, BinarySensorEntity):
    _attr_translation_key = "authentication_required"

    def __init__(self, entry: ChanganConfigEntry) -> None:
        super().__init__(entry, entry.runtime_data.coordinator, "authentication_required")

    @property
    def is_on(self) -> bool:
        return self.coordinator.auth_required

    @property
    def available(self) -> bool:
        return True


class ChanganStatusBinarySensor(ChanganEntity, BinarySensorEntity):
    def __init__(self, entry, description: ChanganBinarySensorDescription) -> None:
        super().__init__(entry, entry.runtime_data.coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None and super().available
