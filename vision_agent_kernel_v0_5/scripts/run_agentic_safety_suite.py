from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentic.ui_explorer import UIExplorer


def main() -> int:
    checks = {
        "destructive_ui_blacklist": _destructive_ui_blacklist(),
        "safe_high_confidence_proposal": _safe_high_confidence_proposal(),
        "low_confidence_requires_confirmation": _low_confidence_requires_confirmation(),
    }
    for name, ok in checks.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}", flush=True)
    return 0 if all(checks.values()) else 1


def _destructive_ui_blacklist() -> bool:
    result = UIExplorer().explore_once([{"text": "确认删除五星武器", "bbox": (10, 10, 180, 50), "confidence": 0.97}])[0]
    return result["gate"]["level"] == "HUMAN_OVERRIDE_REQUIRED" and result["action"]["action_type"] == "blocked"


def _safe_high_confidence_proposal() -> bool:
    result = UIExplorer().explore_once([{"text": "开始测试", "bbox": (10, 10, 120, 50), "confidence": 0.92}])[0]
    return result["gate"]["level"] == "DRY_RUN_ONLY" and bool(result["gate"]["allow"])


def _low_confidence_requires_confirmation() -> bool:
    result = UIExplorer().explore_once([{"text": "继续", "bbox": (10, 10, 90, 50), "confidence": 0.42}])[0]
    return result["gate"]["level"] == "REQUEST_DEMONSTRATION" and not result["gate"]["allow"]


if __name__ == "__main__":
    raise SystemExit(main())
