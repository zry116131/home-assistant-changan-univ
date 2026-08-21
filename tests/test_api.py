from __future__ import annotations

from typing import Any, Self

import pytest

from custom_components.changan_univ.api import ChanganApi, ChanganAuthError, parse_status
from custom_components.changan_univ.const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_REFRESH_TOKEN,
)


class FakeResponse:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def json(self, content_type: object = None) -> dict[str, Any]:
        del content_type
        return self._payload


class FakeSession:
    def __init__(
        self,
        post_responses: list[FakeResponse],
        get_responses: list[FakeResponse] | None = None,
    ) -> None:
        self.post_responses = post_responses
        self.get_responses = get_responses or []
        self.post_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.post_calls.append({"url": url, **kwargs})
        return self.post_responses.pop(0)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.get_calls.append({"url": url, **kwargs})
        return self.get_responses.pop(0)


def test_parse_status_filters_and_maps_vehicle_data() -> None:
    payload = {
        "success": True,
        "data": {
            "airStatus": "1",
            "remainingFuel": "66",
            "remainedOilMile": "510",
            "totalOdometer": "12345.6",
            "engineSpeed": "720",
            "vehicleTemperature": "25.5",
            "environmentalTemp": "18",
            "fuelLeftover": "31.2",
            "fuelConsumption100km": "7.1",
            "batteryVoltage": "12.6",
            "lfTyrePressure": "235",
            "rfTyrePressure": "236",
            "lrTyrePressure": "240",
            "rrTyrePressure": "239",
            "lastUpdatedTime": "2026-08-21 09:30:00",
            "latitude": "31.0000",
            "longitude": "121.0000",
            "vin": "SHOULD-NOT-BE-RETAINED",
        },
    }

    status = parse_status(payload)

    assert status.air_conditioner is True
    assert status.fuel_percent == 66.0
    assert status.remaining_range_km == 510
    assert status.odometer_km == 12345.6
    assert status.engine_running is True
    assert status.tire_pressure_rr_kpa == 239
    assert not hasattr(status, "latitude")
    assert not hasattr(status, "longitude")
    assert "vin" not in (status.status_codes or {})


def test_parse_status_raises_sanitized_auth_error() -> None:
    try:
        parse_status({"success": False, "code": 401, "data": None})
    except ChanganAuthError as err:
        assert "token" not in str(err).lower()
    else:
        raise AssertionError("expected ChanganAuthError")


def test_parse_status_accepts_string_auth_error_code() -> None:
    with pytest.raises(ChanganAuthError, match="authentication is required"):
        parse_status({"success": False, "code": "2010", "data": None})


@pytest.mark.asyncio
async def test_expired_access_token_refreshes_once_and_retries() -> None:
    status_payload = {
        "success": True,
        "data": {"remainingFuel": "55", "engineSpeed": "0"},
    }
    session = FakeSession(
        post_responses=[
            FakeResponse(401, {}),
            FakeResponse(200, status_payload),
        ],
        get_responses=[
            FakeResponse(
                200,
                {
                    "data": {
                        "access_token": "rotated-access",
                        "refresh_token": "rotated-refresh",
                    }
                },
            )
        ],
    )
    updates: list[dict[str, Any]] = []
    api = ChanganApi(
        session,  # type: ignore[arg-type]
        {
            CONF_ACCESS_TOKEN: "expired-access",
            CONF_REFRESH_TOKEN: "valid-refresh",
            CONF_CAR_ID: "private-car-id",
        },
        updates.append,
    )

    status = await api.async_get_status()

    assert status.fuel_percent == 55.0
    assert len(session.get_calls) == 1
    assert len(session.post_calls) == 2
    assert session.post_calls[1]["data"]["token"] == "rotated-access"
    assert updates[-1][CONF_ACCESS_TOKEN] == "rotated-access"
    assert updates[-1][CONF_REFRESH_TOKEN] == "rotated-refresh"


@pytest.mark.asyncio
async def test_expired_access_token_without_refresh_requires_authentication() -> None:
    session = FakeSession(post_responses=[FakeResponse(401, {})])
    api = ChanganApi(
        session,  # type: ignore[arg-type]
        {
            CONF_ACCESS_TOKEN: "expired-access",
            CONF_CAR_ID: "private-car-id",
        },
        lambda updated: None,
    )

    with pytest.raises(ChanganAuthError, match="authentication is required"):
        await api.async_get_status()

    assert session.get_calls == []
