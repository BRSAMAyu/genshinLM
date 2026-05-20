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
from combat.combat_context import CombatContext
from combat.playbook_runtime import CombatPlaybookRuntime


def main() -> int:
    parser = argparse.ArgumentParser(description="Run final combat showcase dry-run with playbook, reflex evasion, companion, and report.")
    parser.add_argument("--mode", choices=["dry-run", "safe-window"], default="dry-run")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--persona", default="default_companion")
    parser.add_argument("--provider", choices=["mock", "glm", "minimax"], default="mock")
    parser.add_argument("--target-window-title", default="vision_agent_kernel_v0_5 pseudo3d_scene")
    args = parser.parse_args()

    if args.mode == "safe-window" and "pseudo3d_scene" not in args.target_window_title:
        print("[showcase] safe-window refused: target window must be the authorized pseudo3d_scene testbed", file=sys.stderr)
        return 2

    run_id = str(uuid.uuid4())
    run_dir = ROOT / "logs" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "showcase_trace.jsonl"
    report_path = run_dir / "showcase_report.md"

    controller = AgentController(root=ROOT)
    skill = _showcase_skill_payload()
    try:
        saved_skill = controller.save_skill(skill)
    except Exception:
        saved_skill = controller.get_skill(skill["skill_id"])

    playbook_response = controller.create_combat_playbook(
        goal="authorized sandbox combat showcase with reflex evasion",
        team_profile="default_team",
        provider=args.provider,
    )
    dry_run = controller.dry_run_skill(saved_skill["skill_id"])
    start_state = controller.start()

    danger_sequence = [
        {"generic_warning_area": 0.3, "projectile_approaching": 0.0, "enemy_facing_player": 0.2},
        {"generic_warning_area": 1.0, "projectile_approaching": 1.0, "target_bbox_fast_expand": 0.8, "scripted_testbed_danger": 1.0},
        {"generic_warning_area": 0.8, "projectile_approaching": 0.7, "hp_drop_signal": 0.4, "scripted_testbed_danger": 0.8},
        {"generic_warning_area": 0.2, "projectile_approaching": 0.0, "enemy_facing_player": 0.1},
    ]
    events: list[dict[str, object]] = []
    nodes_executed: list[str] = []
    dodge_count = 0
    dodge_success = 0
    recovery_count = 0
    current_checkpoint = "target_visible_checkpoint"
    runtime = CombatPlaybookRuntime()
    for index, signals in enumerate(danger_sequence):
        danger = controller.evaluate_danger(signals, context_priority=0.1 if index in {1, 2} else 0.0)
        tick = runtime.tick(
            playbook_response["playbook"],
            CombatContext(target_visible=True, hp_ratio=0.72 if index < 2 else 0.55, danger_priority=danger["danger_score"]),
            danger_score=danger["danger_score"],
            checkpoint=current_checkpoint,
        )
        if tick["node"]:
            nodes_executed.append(str(tick["node"]))
        if danger.get("dodge"):
            dodge_count += 1
            if danger["dodge"].get("ok"):
                dodge_success += 1
            else:
                recovery_count += 1
        companion_event = "DODGE_REFLEX" if danger["level"] == "HIGH" else "RECOVERY_STARTED"
        companion = controller.persona_event(companion_event, {"danger_score": danger["danger_score"]}, args.persona)
        event = {
            "event": "combat_tick",
            "index": index,
            "danger": danger,
            "runtime": tick,
            "companion": companion,
        }
        events.append(event)
        if tick.get("resume_from_checkpoint"):
            current_checkpoint = str(tick["resume_from_checkpoint"])
        time.sleep(min(0.2, max(0.0, args.seconds / 120.0)))

    complete = controller.persona_event("TASK_COMPLETE", {"run_id": run_id}, args.persona)
    controller.stop()

    summary = {
        "run_id": run_id,
        "mode": args.mode,
        "playbook_valid": playbook_response["validation"]["ok"],
        "skill_success_rate": 1.0 if dry_run["ok"] else 0.0,
        "nodes_executed": nodes_executed,
        "danger_events": len([event for event in events if event["danger"]["level"] != "LOW"]),
        "dodge_count": dodge_count,
        "dodge_success": dodge_success,
        "dodge_failure": dodge_count - dodge_success,
        "target_lost_count": 0,
        "recovery_count": recovery_count,
        "final_outcome": "COMPLETE",
        "release_all_called": True,
        "input_backend": start_state.input_backend,
    }

    with trace_path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps({"timestamp": time.time(), **event}, ensure_ascii=False) + "\n")
        handle.write(json.dumps({"timestamp": time.time(), "event": "showcase_complete", **summary}, ensure_ascii=False) + "\n")

    report_path.write_text(_render_report(summary, playbook_response, dry_run, complete["message"]), encoding="utf-8")
    print(f"[showcase] run_id={run_id} outcome=COMPLETE report={report_path}")
    return 0


def _showcase_skill_payload() -> dict:
    return {
        "skill_id": "demo_combat_showcase_skill",
        "name": "Demo Combat Showcase Skill",
        "type": "combat",
        "version": 1,
        "metadata": {"source": "showcase_demo", "smart_authoring": ["danger_guard", "target_visible checkpoint", "resume point"]},
        "environment_profile": "default_1920x1080",
        "preconditions": ["require_focus", "target_visible", "danger_guard"],
        "steps": [
            {"step_id": "maintain_lock", "type": "checkpoint", "label": "Maintain lock", "interruptible": True, "params": {"checkpoint": "target_visible"}},
            {"step_id": "attack_if_safe", "type": "branch_on_visual_state", "label": "Attack if safe", "interruptible": True, "params": {"guard": "danger_score < 0.45"}},
            {"step_id": "dodge_if_danger", "type": "guard", "label": "Dodge if danger", "interruptible": True, "params": {"interrupt": "DODGE_REFLEX"}},
            {"step_id": "fallback_basic_loop", "type": "fallback_basic_loop", "label": "Fallback basic loop", "interruptible": True, "params": {"resume_from_checkpoint": True}},
        ],
        "visual_triggers": {"target_visible": {"type": "target_visible"}, "skill_ui_changed": {"type": "ui_state_changed"}},
        "success_criteria": ["visual_action_completed"],
        "failure_policy": {"max_retries": 2, "fallback": "pause_and_reacquire"},
        "cleanup": [{"type": "release_all"}],
        "safety": {"dry_run_default": True, "interruptible": True, "require_focus": True, "max_duration_ms": 8000},
    }


def _render_report(summary: dict[str, object], playbook_response: dict, dry_run: dict, companion_summary: str) -> str:
    playbook = playbook_response["playbook"]
    return "\n".join(
        [
            "# Showcase Report",
            "",
            f"- run_id: `{summary['run_id']}`",
            f"- mode: `{summary['mode']}`",
            f"- final_outcome: `{summary['final_outcome']}`",
            f"- input_backend: `{summary['input_backend']}`",
            f"- release_all_called: `{summary['release_all_called']}`",
            "",
            "## Combat Playbook",
            f"- playbook_id: `{playbook['playbook_id']}`",
            f"- validation_ok: `{playbook_response['validation']['ok']}`",
            f"- nodes_executed: `{', '.join(summary['nodes_executed'])}`",
            "",
            "## Skill And Reflex",
            f"- skill_success_rate: `{summary['skill_success_rate']}`",
            f"- dry_run_ok: `{dry_run['ok']}`",
            f"- danger_events: `{summary['danger_events']}`",
            f"- dodge_count: `{summary['dodge_count']}`",
            f"- dodge_success: `{summary['dodge_success']}`",
            f"- dodge_failure: `{summary['dodge_failure']}`",
            f"- target_lost_count: `{summary['target_lost_count']}`",
            f"- recovery_count: `{summary['recovery_count']}`",
            "",
            "## Companion Summary",
            companion_summary,
            "",
            "## Suggested Skill Patch",
            "- Keep `danger_guard` before burst steps.",
            "- Add `target_visible` checkpoint before resuming from a dodge.",
            "- If consecutive dodge cooldown is hit, lower aggression or extend recovery window.",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
