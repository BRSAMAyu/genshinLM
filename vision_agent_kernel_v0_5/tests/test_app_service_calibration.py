from __future__ import annotations

from pathlib import Path

from app_service.calibration import CalibrationProfile, CalibrationStore, RoiDefinition
from app_service.model_manager import ModelManager


def test_calibration_store_saves_versions_and_tests_profile(tmp_path: Path) -> None:
    store = CalibrationStore(tmp_path)
    profile = CalibrationProfile(
        profile_id="unit_profile",
        window_title="unit",
        source_resolution=(1920, 1080),
        normalized_resolution=(1280, 720),
        rois={
            "main_view": RoiDefinition(mode="relative", x=0.1, y=0.1, w=0.8, h=0.7),
            "minimap": RoiDefinition(
                mode="anchor",
                anchor="top-right",
                offset_x_px=-320,
                offset_y_px=16,
                width_px=280,
                height_px=280,
            ),
        },
    )

    store.save_profile(profile)
    store.save_profile(profile)
    result = store.test_profile("unit_profile")

    assert result["ok"] is True
    assert store.list_profiles()["active_profile_id"] == "unit_profile"
    assert store.get_profile("unit_profile").rois["minimap"].anchor == "top-right"
    assert list((tmp_path / "configs" / "profiles" / "versions").glob("unit_profile.*.json"))


def test_model_manager_status_without_model(tmp_path: Path) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "model.yaml").write_text(
        "detector:\n  backend: ultralytics\n  model_path: models/missing.pt\n  tracker: botsort.yaml\n  device: cpu\n  half: false\n",
        encoding="utf-8",
    )

    status = ModelManager(tmp_path).status()

    assert status.detector_backend == "ultralytics"
    assert status.model_exists is False
    assert status.tracker_available is True
