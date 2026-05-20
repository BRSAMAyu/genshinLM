from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_beta.benchmark_suite import BenchmarkSuite
from open_beta.feedback_package import FeedbackPackageBuilder
from open_beta.skill_workshop import SkillWorkshop


def main() -> int:
    checks = {
        "benchmark_reads_run_folder": _benchmark_reads_run_folder(),
        "blueprint_validation_blocks_danger": _blueprint_validation_blocks_danger(),
        "feedback_package_redacted_by_default": _feedback_package_redacted_by_default(),
    }
    for name, ok in checks.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}", flush=True)
    return 0 if all(checks.values()) else 1


def _benchmark_reads_run_folder() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp) / "run_001"
        run.mkdir()
        (run / "trace.jsonl").write_text(
            "\n".join(
                [
                    json.dumps({"event": "state_transition", "to": "COMPLETE"}),
                    json.dumps({"event": "skill_result", "status": "SUCCESS"}),
                    json.dumps({"verifier_result": {"ok": True}}),
                ]
            ),
            encoding="utf-8",
        )
        summary = BenchmarkSuite().summarize_run_folder(Path(tmp))
    return summary["task_completion_rate"] == 1.0 and summary["skill_success_rate"] == 1.0


def _blueprint_validation_blocks_danger() -> bool:
    result = SkillWorkshop().validate_blueprint({"kind": "skill", "id": "bad", "dangerous_input": True})
    return not result.ok and any("dangerous" in error for error in result.errors)


def _feedback_package_redacted_by_default() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        path = FeedbackPackageBuilder().build(Path(tmp), "report", {}, [], {})
        payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["upload_default"] is False and payload["screenshots"] == "redacted_or_omitted_by_default"


if __name__ == "__main__":
    raise SystemExit(main())
