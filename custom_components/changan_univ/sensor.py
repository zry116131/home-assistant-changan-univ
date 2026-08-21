"""Sensor entities for Changan UNI-V."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ChanganConfigEntry
from .entity import ChanganEntity
from .models import VehicleStatus


@dataclass(frozen=True, kw_only=True)
class ChanganSensorDescription(SensorEntityDescription):
    value_fn: Callable[[VehicleStatus], Any]


SENSORS: tuple[ChanganSensorDescription, ...] = (
    ChanganSensorDescription(
        key="fuel_percent",
        translation_key="fuel_percent",
        value_fn=lambda s: s.fuel_percent,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    ChanganSensorDescription(
        key="remaining_range",
        translation_key="remaining_range",
        value_fn=lambda s: s.remaining_range_km,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    ChanganSensorDescription(
        key="odometer",
        translation_key="odometer",
        value_fn=lambda s: s.odometer_km,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    ChanganSensorDescription(
        key="cabin_temperature",
        translation_key="cabin_temperature",
        value_fn=lambda s: s.cabin_temperature_c,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    ChanganSensorDescription(
        key="exterior_temperature",
        translation_key="exterior_temperature",
        value_fn=lambda s: s.exterior_temperature_c,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    ChanganSensorDescription(
        key="fuel_liters",
        translation_key="fuel_liters",
        value_fn=lambda s: s.fuel_liters,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        state_class=None,
        suggested_display_precision=1,
    ),
    ChanganSensorDescription(
        key="fuel_consumption",
        translation_key="fuel_consumption",
        value_fn=lambda s: s.fuel_consumption_l_per_100km,
        native_unit_of_measurement="L/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    ChanganSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        value_fn=lambda s: s.battery_voltage,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    ChanganSensorDescription(
        key="tire_pressure_fl",
        translation_key="tire_pressure_fl",
        value_fn=lambda s: s.tire_pressure_fl_kpa,
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    ChanganSensorDescription(
        key="tire_pressure_fr",
        translation_key="tire_pressure_fr",
        value_fn=lambda s: s.tire_pressure_fr_kpa,
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    ChanganSensorDescription(
        key="tire_pressure_rl",
        translation_key="tire_pressure_rl",
        value_fn=lambda s: s.tire_pressure_rl_kpa,
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    ChanganSensorDescription(
        key="tire_pressure_rr",
        translation_key="tire_pressure_rr",
        value_fn=lambda s: s.tire_pressure_rr_kpa,
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    ChanganSensorDescription(
        key="vehicle_reported_at",
        translation_key="vehicle_reported_at",
        value_fn=lambda s: s.vehicle_reported_at,
        state_class=None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChanganConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    del hass
    async_add_entities(
        ChanganSensor(entry, entry.runtime_data.coordinator, description) for description in SENSORS
    )


class ChanganSensor(ChanganEntity, SensorEntity):
    def __init__(self, entry, coordinator, description: ChanganSensorDescription) -> None:
        super().__init__(entry, coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None and super().available
