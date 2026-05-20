from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import strftime
from typing import Literal


Anchor = Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"]
RoiMode = Literal["relative", "anchor"]


@dataclass(frozen=True, slots=True)
class RoiDefinition:
    mode: RoiMode
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    anchor: Anchor | None = None
    offset_x_px: int | None = None
    offset_y_px: int | None = None
    width_px: int | None = None
    height_px: int | None = None


@dataclass(frozen=True, slots=True)
class CalibrationProfile:
    profile_id: str
    window_title: str
    source_resolution: tuple[int, int]
    normalized_resolution: tuple[int, int]
    rois: dict[str, RoiDefinition]
    created_at: str = field(default_factory=lambda: strftime("%Y-%m-%dT%H:%M:%S"))


class CalibrationStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._profiles_dir = root / "configs" / "profiles"
        self._versions_dir = self._profiles_dir / "versions"
        self._index_path = self._profiles_dir / "index.json"
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        self._versions_dir.mkdir(parents=True, exist_ok=True)
        if not self._index_path.exists():
            self._write_index({"active_profile_id": None, "profiles": []})

    def save_profile(self, profile: CalibrationProfile, activate: bool = True) -> CalibrationProfile:
        path = self._profile_path(profile.profile_id)
        if path.exists():
            version_path = self._versions_dir / f"{profile.profile_id}.{strftime('%Y%m%d-%H%M%S')}.json"
            shutil.copy2(path, version_path)
        path.write_text(json.dumps(self._profile_to_json(profile), indent=2), encoding="utf-8")
        index = self._read_index()
        profiles = [item for item in index.get("profiles", []) if item.get("profile_id") != profile.profile_id]
        profiles.append(
            {
                "profile_id": profile.profile_id,
                "window_title": profile.window_title,
                "path": str(path),
                "updated_at": profile.created_at,
            }
        )
        index["profiles"] = profiles
        if activate:
            index["active_profile_id"] = profile.profile_id
        self._write_index(index)
        return profile

    def list_profiles(self) -> dict[str, object]:
        return self._read_index()

    def get_profile(self, profile_id: str) -> CalibrationProfile:
        path = self._profile_path(profile_id)
        if not path.exists():
            raise FileNotFoundError(f"profile not found: {profile_id}")
        return self._profile_from_json(json.loads(path.read_text(encoding="utf-8")))

    def test_profile(self, profile_id: str | None = None) -> dict[str, object]:
        index = self._read_index()
        resolved = profile_id or index.get("active_profile_id")
        if not resolved:
            return {"ok": False, "message": "No active profile saved yet."}
        profile = self.get_profile(str(resolved))
        errors = []
        for name, roi in profile.rois.items():
            if roi.mode == "relative":
                values = [roi.x, roi.y, roi.w, roi.h]
                if any(value is None or value < 0.0 or value > 1.0 for value in values):
                    errors.append(f"{name}: relative ROI values must be in [0, 1]")
            else:
                if roi.anchor is None or roi.width_px is None or roi.height_px is None:
                    errors.append(f"{name}: anchor ROI requires anchor, width_px, height_px")
        return {"ok": not errors, "profile_id": profile.profile_id, "errors": errors}

    def restore_previous(self, profile_id: str) -> CalibrationProfile:
        versions = sorted(self._versions_dir.glob(f"{profile_id}.*.json"))
        if not versions:
            raise FileNotFoundError(f"no previous versions found for profile: {profile_id}")
        latest = versions[-1]
        shutil.copy2(latest, self._profile_path(profile_id))
        return self.get_profile(profile_id)

    def _profile_path(self, profile_id: str) -> Path:
        safe_id = "".join(char for char in profile_id if char.isalnum() or char in "-_")
        return self._profiles_dir / f"{safe_id}.json"

    def _read_index(self) -> dict[str, object]:
        return json.loads(self._index_path.read_text(encoding="utf-8"))

    def _write_index(self, index: dict[str, object]) -> None:
        self._index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    def _profile_to_json(self, profile: CalibrationProfile) -> dict[str, object]:
        data = asdict(profile)
        data["source_resolution"] = list(profile.source_resolution)
        data["normalized_resolution"] = list(profile.normalized_resolution)
        return data

    def _profile_from_json(self, data: dict[str, object]) -> CalibrationProfile:
        rois = {
            name: RoiDefinition(**roi)
            for name, roi in dict(data.get("rois", {})).items()
            if isinstance(roi, dict)
        }
        return CalibrationProfile(
            profile_id=str(data["profile_id"]),
            window_title=str(data["window_title"]),
            source_resolution=tuple(data["source_resolution"]),  # type: ignore[arg-type]
            normalized_resolution=tuple(data["normalized_resolution"]),  # type: ignore[arg-type]
            rois=rois,
            created_at=str(data.get("created_at", "")),
        )
