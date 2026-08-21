"""Read-only client for the Changan cloud API."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_IS_NEV,
    CONF_REFRESH_TOKEN,
    CONF_VCS_APP_ID,
)
from .models import VehicleStatus


class ChanganApiError(RuntimeError):
    """Base error for sanitized Changan API failures."""


class ChanganAuthError(ChanganApiError):
    """The Changan account must be authenticated again."""


class ChanganApi:
    """Changan cloud API client with read-only vehicle support."""

    BASE_URL = "https://m.iov.changan.com.cn"
    STATUS_PATH = "/app2/api/car/data"
    REFRESH_BASE_URL = "https://incallapi.changan.com.cn"
    REFRESH_TOKEN_PATH = "/cac/api/v1/oauth2/refresh_token"
    CAC_CLIENT_ID = "2c918082632162010163388048d60158"

    def __init__(
        self,
        session: ClientSession,
        config: Mapping[str, Any],
        session_updated: Callable[[dict[str, Any]], None],
    ) -> None:
        self._session = session
        self._config = dict(config)
        self._session_updated = session_updated

    @property
    def configured(self) -> bool:
        """Return whether the minimum read-only session exists."""
        return all(
            isinstance(self._config.get(key), str) and bool(self._config[key])
            for key in (CONF_ACCESS_TOKEN, CONF_CAR_ID)
        )

    async def async_get_status(self) -> VehicleStatus:
        """Fetch one privacy-filtered status snapshot."""
        if not self.configured:
            raise ChanganAuthError("Changan account authentication is required")
        try:
            return await self._async_request_status()
        except ChanganAuthError:
            await self._async_refresh_session()
            return await self._async_request_status()

    async def _async_request_status(self) -> VehicleStatus:
        form = {
            "carId": self._config[CONF_CAR_ID],
            "keys": "*",
            "isNev": self._config.get(CONF_IS_NEV, ""),
            "token": self._config[CONF_ACCESS_TOKEN],
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "Home-Assistant-Changan-UNI-V/0.4.0",
        }
        if self._config.get(CONF_VCS_APP_ID):
            headers["vcs-app-id"] = self._config[CONF_VCS_APP_ID]
        try:
            async with self._session.post(
                self.BASE_URL + self.STATUS_PATH,
                data=form,
                headers=headers,
                timeout=15,
            ) as response:
                await _raise_for_auth(response)
                if response.status != 200:
                    raise ChanganApiError(f"Changan status returned HTTP {response.status}")
                payload = await response.json(content_type=None)
        except ChanganApiError:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise ChanganApiError("Changan status request failed") from err
        return parse_status(payload)

    async def _async_refresh_session(self) -> None:
        refresh_token = self._config.get(CONF_REFRESH_TOKEN)
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ChanganAuthError("Changan account authentication is required")
        params = {
            "client_id": self.CAC_CLIENT_ID,
            "refresh_token": refresh_token,
        }
        headers = {
            "Accept": "application/json",
            "response-form": "json",
            "User-Agent": "Home-Assistant-Changan-UNI-V/0.4.0",
        }
        try:
            async with self._session.get(
                self.REFRESH_BASE_URL + self.REFRESH_TOKEN_PATH,
                params=params,
                headers=headers,
                timeout=15,
            ) as response:
                if response.status in {400, 401, 403}:
                    raise ChanganAuthError("Changan account authentication is required")
                if response.status != 200:
                    raise ChanganApiError(f"Changan token refresh returned HTTP {response.status}")
                payload = await response.json(content_type=None)
        except ChanganApiError:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise ChanganApiError("Changan token refresh failed") from err

        token_data = _find_token_data(payload)
        access_token = token_data.get("access_token") or token_data.get("accessToken")
        if not isinstance(access_token, str) or not access_token:
            raise ChanganAuthError("Changan account authentication is required")

        self._config[CONF_ACCESS_TOKEN] = access_token
        rotated_refresh = token_data.get("refresh_token") or token_data.get("refreshToken")
        if isinstance(rotated_refresh, str) and rotated_refresh:
            self._config[CONF_REFRESH_TOKEN] = rotated_refresh
        self._session_updated(dict(self._config))


async def _raise_for_auth(response: ClientResponse) -> None:
    if response.status in {401, 403}:
        raise ChanganAuthError("Changan account authentication is required")


def parse_status(payload: Any) -> VehicleStatus:
    """Parse a status payload without retaining account or location data."""
    if not isinstance(payload, dict):
        raise ChanganApiError("Changan status response is invalid")
    if payload.get("success") is False or not isinstance(payload.get("data"), dict):
        if str(payload.get("code")) in {"2", "401", "403", "1001", "2010"}:
            raise ChanganAuthError("Changan account authentication is required")
        raise ChanganApiError("Changan status response was rejected")

    data = payload["data"]
    air_code = _as_int(data.get("airStatus"))
    engine_speed = _as_float(data.get("engineSpeed"))
    status_codes = {
        key: data.get(key)
        for key in (
            "status",
            "airStatus",
            "engineStatus",
            "driverDoorLock",
            "passengerDoorLock",
            "leftFrontDoorLock",
            "rightFrontDoorLock",
            "leftRearDoorLock",
            "rightRearDoorLock",
            "window",
            "sunroof",
            "trunk",
            "hood",
        )
        if key in data
    }
    return VehicleStatus(
        observed_at=datetime.now(UTC).isoformat(),
        air_conditioner=False if air_code == 0 else True if air_code == 1 else None,
        fuel_percent=_as_float(data.get("remainingFuel")),
        remaining_range_km=_as_int(data.get("remainedOilMile")),
        odometer_km=_as_float(data.get("totalOdometer")),
        engine_running=engine_speed is not None and engine_speed > 100,
        cabin_temperature_c=_as_float(data.get("vehicleTemperature")),
        exterior_temperature_c=_as_float(data.get("environmentalTemp")),
        fuel_liters=_as_float(data.get("fuelLeftover")),
        fuel_consumption_l_per_100km=_as_float(data.get("fuelConsumption100km")),
        battery_voltage=_as_float(data.get("batteryVoltage")),
        tire_pressure_fl_kpa=_as_int(data.get("lfTyrePressure")),
        tire_pressure_fr_kpa=_as_int(data.get("rfTyrePressure")),
        tire_pressure_rl_kpa=_as_int(data.get("lrTyrePressure")),
        tire_pressure_rr_kpa=_as_int(data.get("rrTyrePressure")),
        vehicle_reported_at=_as_string(data.get("lastUpdatedTime")),
        status_codes=status_codes,
    )


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    parsed = _as_float(value)
    return int(parsed) if parsed is not None else None


def _as_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _find_token_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if any(key in payload for key in ("access_token", "accessToken")):
        return payload
    for key in ("data", "result", "content"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = _find_token_data(nested)
            if found:
                return found
    return {}
