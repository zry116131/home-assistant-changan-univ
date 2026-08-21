"""Authentication transport for the Changan Gravity Domain app API.

Only the short-lived configuration flow retains a phone number, captcha answer,
or SMS code. Successful authentication returns the minimum CAC vehicle session
needed by the read-only integration.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import string
import time
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientSession
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import USER_AGENT

API_ROOT = "https://api.uni.changan.com.cn"
APP_CODE = "ca-boot-ui-yunli-app"
APP_VERSION = "3.1.0"
SIGN_SALT = "hyzh-unistar-5KWJKH291IvadR"

BOOTSTRAP_PATH = "/appinit/getpktriple"
CAPTCHA_PATH = "/login/getGraphics"
SMS_PATH = "/login/getSmsCodeNew"
LOGIN_PATH = "/login/loginBySmsCode"
CAC_TOKEN_PATH = "/login/getCacToken"
CAR_AUTH_PATH = "/ser/carAuth/getCarAuthInPersonNew"

_KEY_RULE = dict(
    zip(
        string.ascii_lowercase + string.ascii_uppercase,
        "QUPALZMTGBWOKSNXEYJIDCRFHVskdafgjhlqzxwmpeconirvbtyu",
        strict=True,
    )
)


class ChanganLoginError(RuntimeError):
    """Base class for sanitized login failures."""


class ChanganLoginConnectionError(ChanganLoginError):
    """The authentication service could not be reached."""


class ChanganLoginRejected(ChanganLoginError):
    """The authentication service rejected a request."""

    def __init__(self, reason: str, code: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True, slots=True, repr=False)
class CaptchaChallenge:
    """An ephemeral image captcha challenge."""

    graphics_key: str
    image_base64: str


@dataclass(frozen=True, slots=True, repr=False)
class ChanganAuthSession:
    """Minimum read-only vehicle session persisted by Home Assistant."""

    access_token: str
    refresh_token: str
    car_id: str


class ChanganAuthClient:
    """Client for the app's encrypted SMS authentication flow."""

    def __init__(self, session: ClientSession, fingerprint: str) -> None:
        self._session = session
        self._fingerprint = fingerprint
        self._public_key: str | None = None

    async def async_get_captcha(self, phone: str) -> CaptchaChallenge:
        """Request an image captcha for a phone number."""
        data = await self._async_encrypted_request(CAPTCHA_PATH, {"phone": phone})
        graphics_key = _required_string(data, "graphicsKey")
        image_base64 = _required_string(data, "graphicsValue")
        return CaptchaChallenge(graphics_key=graphics_key, image_base64=image_base64)

    async def async_send_sms(
        self,
        phone: str,
        graphics_code: str,
        graphics_key: str,
    ) -> None:
        """Validate the image captcha and request an SMS code."""
        await self._async_encrypted_request(
            SMS_PATH,
            {
                "phone": phone,
                "graphicsCode": graphics_code,
                "graphicsKey": graphics_key,
            },
        )

    async def async_login(self, phone: str, sms_code: str) -> ChanganAuthSession:
        """Exchange an SMS code for a CAC token and discover the vehicle."""
        login_data = await self._async_encrypted_request(
            LOGIN_PATH,
            {
                "phone": phone,
                "smsCode": sms_code,
                "pushId": "0",
                "registerChannel": 3,
                "channel": "",
            },
        )
        uni_token = _required_string(login_data, "token")

        cac_data = await self._async_encrypted_request(
            CAC_TOKEN_PATH,
            {"thirdParty": "10"},
            token=uni_token,
            third_party="10",
        )
        car_data = await self._async_encrypted_request(
            CAR_AUTH_PATH,
            {"newIncall": "1"},
            token=uni_token,
        )

        access_token = _optional_string(cac_data, "accessToken")
        refresh_token = _optional_string(cac_data, "refreshToken")
        nested_cac = car_data.get("cacToken")
        if isinstance(nested_cac, dict):
            access_token = access_token or _optional_string(nested_cac, "accessToken")
            refresh_token = refresh_token or _optional_string(nested_cac, "refreshToken")

        car_id = _optional_string(car_data, "carId")
        car_auth = car_data.get("carAuth")
        if not car_id and isinstance(car_auth, dict):
            car_id = _optional_string(car_auth, "carId")

        if not access_token or not refresh_token or not car_id:
            raise ChanganLoginRejected("incomplete_session")
        return ChanganAuthSession(
            access_token=access_token,
            refresh_token=refresh_token,
            car_id=car_id,
        )

    async def _async_get_public_key(self) -> str:
        if self._public_key:
            return self._public_key

        timestamp = str(int(time.time() * 1000))
        headers = self._base_headers(timestamp)
        headers.update(
            {
                "seccode": "",
                "codelab": "",
                "sign": "",
                "body": _md5_upper("{}"),
            }
        )
        response = await self._async_post_json(BOOTSTRAP_PATH, b"", headers)
        if str(response.get("code")) != "0":
            raise ChanganLoginRejected("bootstrap_rejected", _response_code(response))
        encoded_key = response.get("data")
        if not isinstance(encoded_key, str) or not encoded_key:
            raise ChanganLoginConnectionError("invalid_bootstrap_response")
        try:
            der = base64.b64decode(_decode_public_key(encoded_key), validate=True)
            key = serialization.load_der_public_key(der)
        except (TypeError, ValueError) as err:
            raise ChanganLoginConnectionError("invalid_bootstrap_response") from err
        if not isinstance(key, RSAPublicKey):
            raise ChanganLoginConnectionError("invalid_bootstrap_response")
        self._public_key = encoded_key
        return encoded_key

    async def _async_encrypted_request(
        self,
        path: str,
        data: dict[str, Any],
        *,
        token: str = "",
        third_party: str = "",
    ) -> dict[str, Any]:
        public_key = await self._async_get_public_key()
        request_key = _request_key()
        plaintext = _compact_json(data)
        encrypted_body = _compact_json({"paramEncr": _encrypt_aes(plaintext, request_key)})
        timestamp = str(int(time.time() * 1000))
        headers = self._base_headers(timestamp)
        headers.update(
            {
                "seccode": _encrypt_rsa(public_key, _transformed_key(request_key)),
                "codelab": request_key,
                "sign": _md5_upper(encrypted_body + timestamp + SIGN_SALT),
                "body": _md5_upper(plaintext),
            }
        )
        if token:
            headers["token"] = token
        if third_party:
            headers["thirdParty"] = third_party

        response = await self._async_post_json(path, encrypted_body.encode(), headers)
        if str(response.get("code")) != "0":
            raise ChanganLoginRejected("request_rejected", _response_code(response))

        response_data = response.get("data")
        if response.get("encr") is True and isinstance(response_data, str):
            try:
                response_data = json.loads(_decrypt_aes(response_data, request_key))
            except (TypeError, ValueError, json.JSONDecodeError) as err:
                raise ChanganLoginConnectionError("invalid_encrypted_response") from err
        if response_data is None:
            return {}
        if not isinstance(response_data, dict):
            raise ChanganLoginConnectionError("invalid_encrypted_response")
        return response_data

    async def _async_post_json(
        self,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        try:
            async with self._session.post(
                API_ROOT + path,
                data=body,
                headers=headers,
                timeout=15,
            ) as response:
                if response.status == 429:
                    raise ChanganLoginRejected("rate_limited", "429")
                if response.status != 200:
                    raise ChanganLoginConnectionError("authentication_request_failed")
                payload = await response.json(content_type=None)
        except ChanganLoginError:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise ChanganLoginConnectionError("authentication_request_failed") from err
        if not isinstance(payload, dict):
            raise ChanganLoginConnectionError("invalid_authentication_response")
        return payload

    def _base_headers(self, timestamp: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "timestamp": timestamp,
            "os": "Android",
            "osVersion": "10",
            "fingerprint": self._fingerprint,
            "loginChannel": "3",
            "appVersion": APP_VERSION,
            "model": "Home Assistant",
            "brand": "Home Assistant",
            "operatorName": "",
            "networkState": "WIFI",
            "x-tenant-app": APP_CODE,
            "User-Agent": USER_AGENT,
        }


def generate_fingerprint() -> str:
    """Create a stable, installation-local synthetic client identifier."""
    return secrets.token_hex(16)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _md5_upper(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest().upper()


def _decode_public_key(value: str) -> str:
    """Undo the two numeric markers and two-byte insertion used by the app."""
    try:
        first = value.index("eh8Fj") + 5
        value = value[:first] + str(int(value[first : first + 3]) * 2) + value[first + 3 :]
        second = value.index("J8Ju1") + 5
        value = (
            value[:second] + format(int(value[second : second + 6]) // 2, "x") + value[second + 6 :]
        )
    except (ValueError, IndexError) as err:
        raise ValueError("invalid encoded public key") from err
    return value[:10] + value[12:]


def _request_key() -> str:
    return str(int(time.time() * 1000)) + "".join(
        secrets.choice(string.ascii_letters) for _ in range(3)
    )


def _transformed_key(value: str) -> str:
    try:
        return value[:-3] + "".join(_KEY_RULE[character] for character in value[-3:])
    except KeyError as err:
        raise ValueError("invalid request key") from err


def _encrypt_aes(plaintext: str, key: str) -> str:
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(key[:16].encode()))
    encryptor = cipher.encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


def _decrypt_aes(ciphertext: str, key: str) -> str:
    cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(key[:16].encode()))
    decryptor = cipher.decryptor()
    padded = decryptor.update(base64.b64decode(ciphertext, validate=True)) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode()


def _encrypt_rsa(public_key: str, value: str) -> str:
    der = base64.b64decode(_decode_public_key(public_key), validate=True)
    key = serialization.load_der_public_key(der)
    if not isinstance(key, RSAPublicKey):
        raise TypeError("invalid RSA public key")
    encrypted = key.encrypt(value.encode(), asymmetric_padding.PKCS1v15())
    return base64.b64encode(encrypted).decode()


def _required_string(data: dict[str, Any], key: str) -> str:
    value = _optional_string(data, key)
    if not value:
        raise ChanganLoginConnectionError("invalid_authentication_response")
    return value


def _optional_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) and value else ""


def _response_code(response: dict[str, Any]) -> str | None:
    code = response.get("code")
    return str(code)[:16] if isinstance(code, (str, int)) else None
