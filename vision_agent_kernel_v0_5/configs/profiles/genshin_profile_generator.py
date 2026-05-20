from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResolutionScale:
    width: int
    height: int
    scale: float


SUPPORTED_RESOLUTIONS = [
    ResolutionScale(1280, 720, 0.667),
    ResolutionScale(1920, 1080, 1.0),
    ResolutionScale(2560, 1440, 1.333),
    ResolutionScale(3840, 2160, 2.0),
    ResolutionScale(2560, 1080, 1.0),
]

_REF_PROFILE_PATH = Path(__file__).parent / "genshin_1920x1080.json"


def _load_reference_profile() -> dict:
    with open(_REF_PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _scale_offset(offset: int | list[int], scale: float) -> int | list[int]:
    if isinstance(offset, list):
        return [int(round(v * scale)) for v in offset]
    return int(round(offset * scale))


def _scale_roi(roi_def: dict, sx: float, sy: float, res_w: int, res_h: int) -> dict:
    mode = roi_def.get("mode", "anchor")
    scaled = dict(roi_def)

    if mode == "anchor":
        anchor = roi_def.get("anchor", "top-left")

        if "offset_x_px" in roi_def:
            scaled["offset_x_px"] = _scale_offset(roi_def["offset_x_px"], sx)
        if "offset_y_px" in roi_def:
            scaled["offset_y_px"] = _scale_offset(roi_def["offset_y_px"], sy)
        if "width_px" in roi_def:
            scaled["width_px"] = int(round(roi_def["width_px"] * sx))
        if "height_px" in roi_def:
            scaled["height_px"] = int(round(roi_def["height_px"] * sy))

    return scaled


def generate_profile(resolution: ResolutionScale) -> dict:
    """Generate a Genshin profile for the given resolution.

    Scales all anchor-based ROI offsets from the 1920x1080 reference.
    Relative ROIs stay the same (they're fractions of the viewport).
    """
    ref = _load_reference_profile()

    sx = resolution.width / 1920.0
    sy = resolution.height / 1080.0

    profile: dict = {
        "profile_id": f"genshin_{resolution.width}x{resolution.height}",
        "window_title": ref["window_title"],
        "alt_window_title": ref["alt_window_title"],
        "process_name": ref["process_name"],
        "alt_process_name": ref["alt_process_name"],
        "source_resolution": [resolution.width, resolution.height],
        "normalized_resolution": [resolution.width, resolution.height],
        "display_mode": ref["display_mode"],
        "environment": ref["environment"],
        "rois": {},
    }

    for roi_name, roi_def in ref.get("rois", {}).items():
        profile["rois"][roi_name] = _scale_roi(roi_def, sx, sy, resolution.width, resolution.height)

    profile["created_at"] = ref.get("created_at", "")
    return profile


def generate_all_profiles(output_dir: Path) -> list[Path]:
    """Generate profiles for all supported resolutions."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for res in SUPPORTED_RESOLUTIONS:
        if res.width == 1920 and res.height == 1080:
            continue  # skip reference, it already exists

        profile = generate_profile(res)
        filename = f"genshin_{res.width}x{res.height}.json"
        out_path = output_dir / filename

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
            f.write("\n")

        paths.append(out_path)

    return paths
