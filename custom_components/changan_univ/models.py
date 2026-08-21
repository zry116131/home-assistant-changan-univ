"""Data models for the Changan UNI-V integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VehicleStatus:
    """A privacy-filtered vehicle status snapshot."""

    observed_at: str
    air_conditioner: bool | None = None
    fuel_percent: float | None = None
    remaining_range_km: int | None = None
    odometer_km: float | None = None
    engine_running: bool | None = None
    cabin_temperature_c: float | None = None
    exterior_temperature_c: float | None = None
    fuel_liters: float | None = None
    fuel_consumption_l_per_100km: float | None = None
    battery_voltage: float | None = None
    tire_pressure_fl_kpa: int | None = None
    tire_pressure_fr_kpa: int | None = None
    tire_pressure_rl_kpa: int | None = None
    tire_pressure_rr_kpa: int | None = None
    vehicle_reported_at: str | None = None
    status_codes: dict[str, Any] | None = None
