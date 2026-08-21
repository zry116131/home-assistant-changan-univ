from custom_components.changan_univ.api import ChanganAuthError, parse_status


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
