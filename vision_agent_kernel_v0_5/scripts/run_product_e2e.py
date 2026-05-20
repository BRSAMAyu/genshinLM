from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_service.agent_controller import AgentController


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Product E2E acceptance chain.")
    parser.add_argument("--mode", choices=["dry-run", "safe-window"], default="dry-run")
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--skill", default=None)
    parser.add_argument("--task", default="complete product demo")
    parser.add_argument("--use-mock-llm", action="store_true")
    parser.add_argument("--chaos", choices=["none", "mild"], default="none")
    parser.add_argument("--confirm", action="store_true", help="Required for safe-window execution after selecting an authorized test window.")
    args = parser.parse_args()

    controller = AgentController(root=ROOT)
    result = controller.run_product_e2e(
        mode=args.mode,
        seconds=args.seconds,
        profile=args.profile,
        skill=args.skill,
        task=args.task,
        use_mock_llm=args.use_mock_llm or True,
        chaos=args.chaos,
        confirm=args.confirm,
    )
    print(json.dumps(_summary(result), ensure_ascii=False, indent=2))
    if not result["ok"]:
        print(f"[product_e2e] FAILED error={result.get('error')} report={result.get('report_path')}")
        return 2
    print(f"[product_e2e] PASS run_id={result['run_id']} report={result['report_path']}")
    return 0


def _summary(result: dict) -> dict:
    return {
        "ok": result["ok"],
        "run_id": result["run_id"],
        "execution_mode": result["execution_mode"],
        "selected_profile": result["selected_profile"],
        "selected_skill": result["selected_skill"],
        "planner_provider": result["planner_provider"],
        "task_validation": result["task_validation"],
        "release_all_called": result["release_all_called"],
        "confirm_required": result["confirm_required"],
        "report_path": result["report_path"],
        "checklist": [
            {"key": item["key"], "ok": item["ok"], "detail": item["detail"]}
            for item in result["checklist"]
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
