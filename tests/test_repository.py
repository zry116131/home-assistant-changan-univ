"""Repository, privacy, and safety-boundary tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

from custom_components.changan_univ.const import PLATFORMS
from custom_components.changan_univ.models import VehicleStatus

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "changan_univ"


def test_hacs_repository_layout_and_manifest() -> None:
    integrations = [path for path in (ROOT / "custom_components").iterdir() if path.is_dir()]
    assert integrations == [INTEGRATION]
    assert (ROOT / "README.md").is_file()
    assert (ROOT / "hacs.json").is_file()
    assert (INTEGRATION / "brand" / "icon.png").is_file()

    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    assert manifest["domain"] == "changan_univ"
    assert manifest["name"] == "Changan UNI-V"
    assert manifest["config_flow"] is True
    assert manifest["single_config_entry"] is True
    assert manifest["requirements"] == []
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    for key in ("codeowners", "documentation", "issue_tracker", "iot_class"):
        assert manifest[key]


def test_read_only_release_has_no_vehicle_control_platform() -> None:
    assert PLATFORMS == ["binary_sensor", "sensor"]
    source = "\n".join(
        path.read_text() for path in INTEGRATION.glob("*.py") if path.name != "const.py"
    )
    for forbidden in (
        "carControl",
        "check-pin",
        "OpenAir",
        "set_air_conditioner",
        "async_turn_on",
        "async_turn_off",
    ):
        assert forbidden not in source


def test_vehicle_model_cannot_retain_exact_location_or_account_identity() -> None:
    model_fields = VehicleStatus.__dataclass_fields__
    for forbidden in (
        "latitude",
        "longitude",
        "location",
        "vin",
        "car_id",
        "access_token",
        "refresh_token",
        "phone",
        "sms_code",
        "pin",
    ):
        assert forbidden not in model_fields
