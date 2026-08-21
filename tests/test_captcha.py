"""Security tests for ephemeral captcha image handling."""

from __future__ import annotations

import base64

import pytest
from homeassistant.core import HomeAssistant

from custom_components.changan_univ.captcha import (
    _decode_image,
    async_remove_captcha,
    async_store_captcha,
)

TEST_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nprivate-pixels").decode()


def test_captcha_accepts_raster_and_rejects_svg() -> None:
    content, content_type = _decode_image(TEST_PNG)
    assert content.startswith(b"\x89PNG")
    assert content_type == "image/png"

    svg = base64.b64encode(b'<svg onload="alert(1)"></svg>').decode()
    with pytest.raises(ValueError, match="unsupported"):
        _decode_image(svg)


def test_captcha_store_uses_random_url_and_can_be_removed(hass: HomeAssistant) -> None:
    token, url = async_store_captcha(hass, TEST_PNG)

    assert url == f"/api/changan_univ/captcha/{token}"
    assert TEST_PNG not in url
    assert len(token) >= 32

    async_remove_captcha(hass, token)
    _, second_url = async_store_captcha(hass, TEST_PNG)
    assert second_url != url
