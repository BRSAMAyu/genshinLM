from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.types import SkillResult
from execution.combat_verifier import CombatVerifier
from execution.collection_verifier import CollectionVerifier
from execution.mission_node_executor import MissionNodeExecutor
from execution.verifier_base import VerifierContext
from planning.intent_parser import IntentParser
from planning.mission_runner import MissionRunner
from planning.task_spec_builder import TaskSpecBuilder
from testbed.realistic_scenarios import RealisticTestbed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run realistic testbed acceptance suite.")
    parser.add_argument("--case", choices=["combat_task", "collection_task", "mixed_task", "target_lost_recovery", "mission_resume"])
    args = parser.parse_args()
    cases = [args.case] if args.case else ["combat_task", "collection_task", "mixed_task", "target_lost_recovery", "mission_resume"]
    ok = True
    for case in cases:
        passed = CASES[case]()
        ok = ok and passed
        print(f"{case}: {'PASS' if passed else 'FAIL'}", flush=True)
    return 0 if ok else 1


def combat_task() -> bool:
    env = RealisticTestbed()
    executor = MissionNodeExecutor()
    node = {"id": "combat", "type": "combat", "skill_binding": "basic_combat_combo_skill", "failure_policy": {"on_failed": "recover_or_skip", "cleanup_skill": "return_to_safe_anchor_v1"}}
    result = executor.execute(node, [_skill("basic_combat_combo_skill", "combat")], CombatVerifier(), env.context({"combat_started": True}), skill_runner=lambda *_: _attack_runner(env))
    return result.status == "SUCCESS" and result.verifier_result.ok and env.state.target_hp_ratio <= 0.0


def collection_task() -> bool:
    env = RealisticTestbed()
    env.approach_collectable()
    executor = MissionNodeExecutor()
    node = {"id": "collect", "type": "collect", "skill_binding": "collect_visible_item_skill", "failure_policy": {"on_failed": "recover_or_skip", "cleanup_skill": "step_back_safe"}}
    result = executor.execute(node, [_skill("collect_visible_item_skill", "collect")], CollectionVerifier(), env.context(), skill_runner=lambda *_: _collect_runner(env))
    return result.status == "SUCCESS" and result.verifier_result.ok and not env.state.collectable_visible


def mixed_task() -> bool:
    return combat_task() and collection_task()


def target_lost_recovery() -> bool:
    env = RealisticTestbed()
    env.lose_target()
    lost = not env.context().target_track
    env.reacquire()
    recovered = bool(env.context().target_track)
    return lost and recovered


def mission_resume() -> bool:
    env = RealisticTestbed()
    queue = TaskSpecBuilder().build(IntentParser().parse("prepare material x"))
    available = [_skill("enter_region_a_v1", "enter_region"), _skill("acquire_monster_a_v1", "acquire_target"), _skill("safe_combat_playbook_v1", "combat")]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        runner = MissionRunner(Path(tmp))
        partial = runner.run(queue, available, env.context({"combat_started": True}), lambda skill_id, *_: _mission_skill_runner(env, skill_id))
        resumed = runner.run(queue, available, env.context({"combat_started": True}), lambda skill_id, *_: _mission_skill_runner(env, skill_id), resume=True)
    return partial.ok and resumed.ok and resumed.resumed


def _attack_runner(env: RealisticTestbed) -> tuple[SkillResult, VerifierContext]:
    start = time.perf_counter()
    env.attack()
    env.attack()
    return SkillResult("basic_combat_combo_skill", "SUCCESS", None, start, time.perf_counter(), {"actual_execution": "testbed_attack"}), env.context({"combat_started": True})


def _collect_runner(env: RealisticTestbed) -> tuple[SkillResult, VerifierContext]:
    start = time.perf_counter()
    env.collect()
    return SkillResult("collect_visible_item_skill", "SUCCESS", None, start, time.perf_counter(), {"actual_execution": "testbed_collect"}), env.context()


def _mission_skill_runner(env: RealisticTestbed, skill_id: str) -> tuple[SkillResult, VerifierContext]:
    start = time.perf_counter()
    if "combat" in skill_id:
        env.attack()
        env.attack()
        context = env.context({"combat_started": True})
    else:
        context = env.context({"success": True, "target_visible": True})
    return SkillResult(skill_id, "SUCCESS", None, start, time.perf_counter(), {"actual_execution": "mission_runner"}), context


def _skill(skill_id: str, skill_type: str) -> dict[str, str]:
    return {"skill_id": skill_id, "type": skill_type, "environment_profile": "default_1920x1080"}


CASES = {
    "combat_task": combat_task,
    "collection_task": collection_task,
    "mixed_task": mixed_task,
    "target_lost_recovery": target_lost_recovery,
    "mission_resume": mission_resume,
}


if __name__ == "__main__":
    raise SystemExit(main())
