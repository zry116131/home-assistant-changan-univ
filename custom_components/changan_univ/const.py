"""Constants for the Changan UNI-V integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "changan_univ"

CONF_ACCESS_TOKEN: Final = "access_token"
CONF_CAR_ID: Final = "car_id"
CONF_DISPLAY_NAME: Final = "display_name"
CONF_IS_NEV: Final = "is_nev"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_VCS_APP_ID: Final = "vcs_app_id"

DEFAULT_DISPLAY_NAME: Final = "长安 UNI-V"
DEFAULT_SCAN_INTERVAL: Final = 120
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 600

PLATFORMS: Final = ["binary_sensor", "sensor"]

ATTRIBUTION: Final = "数据来自长安汽车云服务"
