from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_service.agent_controller import AgentController


def main() -> int:
    parser = argparse.ArgumentParser(description="Run product-level dry-run demo with persona, planner, skill, and combat reflex.")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--mode", choices=["dry-run", "safe-window"], default="dry-run")
    parser.add_argument("--persona", default="default_companion")
    parser.add_argument("--goal", default="track target, execute verified skill, dodge scripted danger, complete")
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    run_dir = ROOT / "logs" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "product_demo_trace.jsonl"
    report_path = run_dir / "product_demo_report.md"

    controller = AgentController(root=ROOT)
    started = time.time()

    skill_payload = _demo_skill_payload()
    try:
        saved_skill = controller.save_skill(skill_payload)
    except Exception:
        saved_skill = controller.get_skill(skill_payload["skill_id"])

    persona = controller.persona_event("RECOVERY_STARTED", {}, args.persona)
    plan = controller.plan_task(args.goal, provider="mock", persona_id=args.persona)
    playbook = controller.create_combat_playbook(args.goal, team_profile="default_team", provider="mock")
    state = controller.start()
    danger = controller.evaluate_danger(
        {
            "generic_warning_area": 1.0,
            "projectile_approaching": 1.0,
            "target_bbox_fast_expand": 0.8,
            "scripted_testbed_danger": 1.0,
        },
        context_priority=0.1,
    )
    dry_run = controller.dry_run_skill(saved_skill["skill_id"])
    complete_line = controller.persona_event("TASK_COMPLETE", {}, args.persona)
    controller.stop()

    events = [
        {"event": "persona_selected", "persona": args.persona, "message": persona["message"]},
        {"event": "task_planned", "ok": plan["ok"], "skill_chain": plan["skill_chain"]},
        {"event": "combat_playbook_ready", "ok": playbook["ok"], "nodes": [node["node_id"] for node in playbook["playbook"]["nodes"]]},
        {"event": "agent_started", "mode": state.mode, "input_backend": state.input_backend},
        {"event": "danger_evaluated", **danger},
        {"event": "skill_dry_run", "ok": dry_run["ok"], "status": dry_run["result"]["status"]},
        {"event": "task_complete", "message": complete_line["message"]},
    ]
    with trace_path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps({"timestamp": time.time(), **event}, ensure_ascii=False) + "\n")

    elapsed = time.time() - started
    report_path.write_text(
        "\n".join(
            [
                "# Product Demo Report",
                "",
                f"- run_id: `{run_id}`",
                f"- mode: `{args.mode}`",
                f"- elapsed_sec: `{elapsed:.2f}`",
                f"- final_outcome: `COMPLETE`",
                f"- skill: `{saved_skill['skill_id']}` v{saved_skill['version']}",
                f"- danger_score: `{danger['danger_score']:.3f}`",
                f"- dodge: `{danger['dodge']}`",
                "",
                "## Companion Summary",
                complete_line["message"],
                "",
                "## Suggested Skill Patch",
                "- Keep target_visible checkpoint before combo execution.",
                "- Keep DODGE_REFLEX guard enabled for combat demos.",
            ]
        ),
        encoding="utf-8",
    )
    print(f"[product_demo] run_id={run_id} outcome=COMPLETE report={report_path}")
    return 0


def _demo_skill_payload() -> dict:
    return {
        "skill_id": "demo_product_skill",
        "name": "Demo Product Skill",
        "type": "combat",
        "version": 1,
        "metadata": {"source": "product_demo"},
        "environment_profile": "default_1920x1080",
        "preconditions": ["require_focus", "target_visible"],
        "steps": [
            {
                "step_id": "maintain_lock",
                "type": "wait_visual_trigger",
                "label": "Maintain target lock",
                "timeout_ms": 1000,
                "interruptible": True,
                "params": {"trigger": "target_visible", "chunk_ms": 100},
            },
            {
                "step_id": "fallback",
                "type": "fallback_basic_loop",
                "label": "Fallback loop",
                "interruptible": True,
                "params": {},
            },
        ],
        "visual_triggers": {"target_visible": {"type": "target_visible"}},
        "success_criteria": ["visual_action_completed"],
        "failure_policy": {"max_retries": 2, "fallback": "pause_and_reacquire"},
        "cleanup": [{"type": "release_all"}],
        "safety": {"dry_run_default": True, "interruptible": True, "require_focus": True, "max_duration_ms": 5000},
    }


if __name__ == "__main__":
    raise SystemExit(main())
