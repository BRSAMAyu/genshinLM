from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_service.skill_manager import SkillDryRunRuntime, SkillRecorder, SkillReplayRuntime, SkillStore, SkillValidator
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker


CASES = ("open_demo_menu_skill", "collect_visible_item_skill", "basic_combat_combo_skill")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real test-window skill recording and replay acceptance checks.")
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    selected = [args.case] if args.case else list(CASES)
    ok = True
    for case in selected:
        passed = run_case(case)
        ok = ok and passed
        print(f"{case}: {'PASS' if passed else 'FAIL'}", flush=True)
    return 0 if ok else 1


def run_case(skill_id: str) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="aurora_skill_recording_"))
    try:
        shutil.copytree(ROOT / "configs", tmp / "configs", dirs_exist_ok=True)
        recorder = SkillRecorder()
        recorder.start(
            active_window_title="pseudo3d_scene - authorized testbed",
            backend_name="test-window",
            focus_state="FOCUSED",
            roi_profile="default_1920x1080",
            observation_frame_id=1,
            target_state="TRACKED",
            visual_triggers={"target_visible": True},
        )
        _record_case_events(recorder, skill_id)
        draft = recorder.stop()
        if not draft.raw_events or not draft.segments:
            return False
        payload = recorder.draft_to_skill_payload(draft, skill_id=skill_id, name=skill_id.replace("_", " ").title())
        store = SkillStore(tmp)
        skill = store.save_skill(payload)
        if SkillValidator(tmp).validate(skill):
            return False
        dry_run = SkillDryRunRuntime().run(skill)
        if dry_run.status != "SUCCESS":
            return False
        backend = ConsoleInputBackend()
        worker = InputWorker(backend=backend)
        worker.start()
        try:
            replay = SkillReplayRuntime(worker).replay(skill, mode="safe-window", confirm=True, focus_ok=True)
        finally:
            worker.stop()
        if replay.status != "SUCCESS" or replay.payload.get("leases_submitted", 0) <= 0:
            return False
        store.save_skill({**payload, "metadata": {**payload.get("metadata", {}), "updated": True}})
        versions = store.versions(skill.skill_id)
        rolled = store.rollback(skill.skill_id)
        return bool(versions["versions"]) and rolled.version >= 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _record_case_events(recorder: SkillRecorder, skill_id: str) -> None:
    now = time.time()
    if skill_id == "open_demo_menu_skill":
        recorder.add_event("key_down", {"key": "TAB"}, timestamp=now + 0.02, target_state="TRACKED")
        recorder.add_event("key_up", {"key": "TAB"}, timestamp=now + 0.10, target_state="TRACKED")
        recorder.add_event("visual_snapshot_summary", {"summary": "demo menu opened"}, timestamp=now + 0.26, target_state="TRACKED", visual_triggers={"action_completed": True})
    elif skill_id == "collect_visible_item_skill":
        recorder.add_event("mouse_move", {"dx": 3, "dy": -1}, timestamp=now + 0.02, target_state="TRACKED")
        recorder.add_event("key_down", {"key": "E"}, timestamp=now + 0.08, target_state="TRACKED", visual_triggers={"interaction_prompt_visible": True})
        recorder.add_event("key_up", {"key": "E"}, timestamp=now + 0.16, target_state="TRACKED")
        recorder.add_event("visual_snapshot_summary", {"summary": "item disappeared"}, timestamp=now + 0.31, target_state="TRACKED", visual_triggers={"action_completed": True})
    else:
        recorder.add_event("mouse_click", {"button": "left"}, timestamp=now + 0.03, target_state="TRACKED")
        recorder.add_event("wait", {"duration_ms": 120}, timestamp=now + 0.18, target_state="TRACKED")
        recorder.add_event("key_down", {"key": "Q"}, timestamp=now + 0.33, target_state="TRACKED")
        recorder.add_event("key_up", {"key": "Q"}, timestamp=now + 0.42, target_state="TRACKED")
        recorder.add_event("visual_snapshot_summary", {"summary": "target defeated"}, timestamp=now + 0.58, target_state="TRACKED", visual_triggers={"action_completed": True})


if __name__ == "__main__":
    raise SystemExit(main())
