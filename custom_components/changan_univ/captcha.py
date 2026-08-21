"""Ephemeral same-origin image serving for the account config flow."""

from __future__ import annotations

import base64
import secrets
import time
from dataclasses import dataclass

from aiohttp import web
from homeassistant.components.http import KEY_HASS
from homeassistant.components.http.view import HomeAssistantView
from homeassistant.core import HomeAssistant, callback

_STORE_KEY = "changan_univ_captcha_store"
_VIEW_KEY = "changan_univ_captcha_view_registered"
_MAX_IMAGE_BYTES = 512 * 1024
_CAPTCHA_TTL_SECONDS = 10 * 60


@dataclass(slots=True)
class _CaptchaImage:
    content: bytes
    content_type: str
    expires_at: float


class ChanganCaptchaView(HomeAssistantView):
    """Serve an unguessable, expiring captcha image without browser auth headers."""

    url = "/api/changan_univ/captcha/{token}"
    name = "api:changan_univ:captcha"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        """Return an active captcha image."""
        hass: HomeAssistant = request.app[KEY_HASS]
        store: dict[str, _CaptchaImage] = hass.data.get(_STORE_KEY, {})
        image = store.get(token)
        if image is None or image.expires_at <= time.monotonic():
            store.pop(token, None)
            raise web.HTTPNotFound()
        return web.Response(
            body=image.content,
            content_type=image.content_type,
            headers={
                "Cache-Control": "no-store, max-age=0",
                "Pragma": "no-cache",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )


@callback
def async_register_captcha_view(hass: HomeAssistant) -> None:
    """Register the captcha image view exactly once."""
    if hass.data.get(_VIEW_KEY):
        return
    if hass.http is None:
        hass.data.setdefault(_STORE_KEY, {})
        return
    hass.http.register_view(ChanganCaptchaView())
    hass.data[_VIEW_KEY] = True
    hass.data.setdefault(_STORE_KEY, {})


@callback
def async_store_captcha(hass: HomeAssistant, image_base64: str) -> tuple[str, str]:
    """Validate and store a captcha, returning its token and relative URL."""
    content, content_type = _decode_image(image_base64)
    token = secrets.token_urlsafe(32)
    store: dict[str, _CaptchaImage] = hass.data.setdefault(_STORE_KEY, {})
    now = time.monotonic()
    for stale_token, image in list(store.items()):
        if image.expires_at <= now:
            store.pop(stale_token, None)
    store[token] = _CaptchaImage(
        content=content,
        content_type=content_type,
        expires_at=now + _CAPTCHA_TTL_SECONDS,
    )
    return token, f"/api/changan_univ/captcha/{token}"


@callback
def async_remove_captcha(hass: HomeAssistant, token: str | None) -> None:
    """Remove a captcha image as soon as its challenge is submitted."""
    if not token:
        return
    store: dict[str, _CaptchaImage] = hass.data.get(_STORE_KEY, {})
    store.pop(token, None)


def _decode_image(value: str) -> tuple[bytes, str]:
    if not isinstance(value, str) or not value:
        raise ValueError("captcha image is empty")
    if value.startswith("data:"):
        try:
            _, value = value.split(",", 1)
        except ValueError as err:
            raise ValueError("captcha image data URI is invalid") from err
    normalized = "".join(value.split())
    try:
        content = base64.b64decode(normalized, validate=True)
    except (ValueError, TypeError) as err:
        raise ValueError("captcha image is not valid base64") from err
    if not content or len(content) > _MAX_IMAGE_BYTES:
        raise ValueError("captcha image has an invalid size")
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return content, "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return content, "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return content, "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return content, "image/webp"
    raise ValueError("captcha image type is unsupported")
