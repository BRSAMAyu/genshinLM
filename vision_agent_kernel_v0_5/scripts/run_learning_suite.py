from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from learning.failure_signature import FailureSignatureBuilder, PrivacyMask
from learning.skill_patch_suggester import SkillPatchSuggester
from learning.telemetry_ingestor import TelemetryFailureIngestor


def main() -> int:
    checks = {
        "failure_log_ingest": _failure_log_ingest(),
        "privacy_mask_redacts": _privacy_mask_redacts(),
        "skill_patch_suggested": _skill_patch_suggested(),
    }
    for name, ok in checks.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}", flush=True)
    return 0 if all(checks.values()) else 1


def _failure_log_ingest() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "telemetry.jsonl"
        records = [
            {"event": "target_lost", "node_type": "combat", "skill_id": "safe_combat_v1", "context": {"target_confidence_drop": True}},
            {"event": "state_transition", "from": "TRACK", "to": "RECOVER"},
        ]
        path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
        signatures = TelemetryFailureIngestor().ingest_jsonl(path)
    return len(signatures) == 1 and signatures[0].failure_code == "TARGET_LOST"


def _privacy_mask_redacts() -> bool:
    image = np.full((20, 20, 3), 255, dtype=np.uint8)
    masked = PrivacyMask().mask(image, (5, 5, 10, 10), redacted_rois=[(7, 7, 2, 2)])
    return bool(masked[0, 0].sum() == 0 and masked[6, 6].sum() > 0 and masked[7, 7].sum() == 0)


def _skill_patch_suggested() -> bool:
    signature = FailureSignatureBuilder().build(
        node_type="combat",
        skill_id="safe_combat_v1",
        failure_code="TARGET_LOST",
        observation={"target_confidence_drop": True, "visual_pollution_high": True},
        context={"profile_id": "default_1920x1080"},
    )
    patch = SkillPatchSuggester().suggest(signature)
    return any("reacquire" in str(item).lower() or "coasting" in str(item).lower() for item in patch.get("patches", []))


if __name__ == "__main__":
    raise SystemExit(main())
