"""Protocol and privacy tests for Gravity Domain authentication."""

from __future__ import annotations

import base64
import json
from typing import Any, Self
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from custom_components.changan_univ.auth import (
    ChanganAuthClient,
    ChanganAuthSession,
    _decode_public_key,
    _decrypt_aes,
    _encrypt_aes,
)

FIXED_REQUEST_KEY = "1699999999999AbC"


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
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def _encrypted_response(data: dict[str, Any]) -> FakeResponse:
    return FakeResponse(
        200,
        {
            "code": 0,
            "encr": True,
            "data": _encrypt_aes(json.dumps(data, separators=(",", ":")), FIXED_REQUEST_KEY),
        },
    )


def _test_public_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(der).decode()


def _decrypt_request(call: dict[str, Any]) -> dict[str, Any]:
    encrypted = json.loads(call["data"])["paramEncr"]
    return json.loads(_decrypt_aes(encrypted, FIXED_REQUEST_KEY))


def test_recovered_aes_and_public_key_transform() -> None:
    plaintext = '{"phone":"privacy-test"}'
    assert _decrypt_aes(_encrypt_aes(plaintext, FIXED_REQUEST_KEY), FIXED_REQUEST_KEY) == plaintext
    assert (
        _decode_public_key("0123456789XXeh8Fj123abcJ8Ju1123456tail")
        == "0123456789eh8Fj246abcJ8Ju1f120tail"
    )


@pytest.mark.asyncio
async def test_login_exchanges_minimum_session_and_discovers_car() -> None:
    session = FakeSession(
        [
            FakeResponse(200, {"code": 0, "data": "encoded-server-public-key"}),
            _encrypted_response({"token": "ephemeral-uni-token", "phone": "not-retained"}),
            _encrypted_response(
                {
                    "accessToken": "cac-access",
                    "refreshToken": "cac-refresh",
                    "userId": "not-retained",
                    "openid": "not-retained",
                }
            ),
            _encrypted_response(
                {
                    "carId": "private-car-id",
                    "carAuth": {"vin": "not-retained", "phone": "not-retained"},
                }
            ),
        ]
    )
    public_key = _test_public_key()
    client = ChanganAuthClient(session, "synthetic-fingerprint")  # type: ignore[arg-type]

    with (
        patch(
            "custom_components.changan_univ.auth._decode_public_key",
            return_value=public_key,
        ),
        patch(
            "custom_components.changan_univ.auth._request_key",
            return_value=FIXED_REQUEST_KEY,
        ),
        patch(
            "custom_components.changan_univ.auth._encrypt_rsa",
            return_value="rsa-seccode",
        ),
    ):
        result = await client.async_login("13800138000", "654321")

    assert result == ChanganAuthSession(
        access_token="cac-access",
        refresh_token="cac-refresh",
        car_id="private-car-id",
    )
    assert "cac-access" not in repr(result)
    assert _decrypt_request(session.calls[1]) == {
        "phone": "13800138000",
        "smsCode": "654321",
        "pushId": "0",
        "registerChannel": 3,
        "channel": "",
    }
    assert _decrypt_request(session.calls[2]) == {"thirdParty": "10"}
    assert session.calls[2]["headers"]["thirdParty"] == "10"
    assert session.calls[2]["headers"]["token"] == "ephemeral-uni-token"
    assert _decrypt_request(session.calls[3]) == {"newIncall": "1"}
    assert set(result.__dataclass_fields__) == {"access_token", "refresh_token", "car_id"}


@pytest.mark.asyncio
async def test_captcha_and_sms_request_shapes() -> None:
    session = FakeSession(
        [
            FakeResponse(200, {"code": 0, "data": "encoded-server-public-key"}),
            _encrypted_response(
                {
                    "graphicsKey": "ephemeral-key",
                    "graphicsValue": "ephemeral-image",
                }
            ),
            _encrypted_response({}),
        ]
    )
    client = ChanganAuthClient(session, "synthetic-fingerprint")  # type: ignore[arg-type]

    with (
        patch(
            "custom_components.changan_univ.auth._decode_public_key",
            return_value=_test_public_key(),
        ),
        patch(
            "custom_components.changan_univ.auth._request_key",
            return_value=FIXED_REQUEST_KEY,
        ),
        patch(
            "custom_components.changan_univ.auth._encrypt_rsa",
            return_value="rsa-seccode",
        ),
    ):
        challenge = await client.async_get_captcha("13800138000")
        await client.async_send_sms("13800138000", "1234", challenge.graphics_key)

    assert "ephemeral-image" not in repr(challenge)
    assert _decrypt_request(session.calls[1]) == {"phone": "13800138000"}
    assert _decrypt_request(session.calls[2]) == {
        "phone": "13800138000",
        "graphicsCode": "1234",
        "graphicsKey": "ephemeral-key",
    }
