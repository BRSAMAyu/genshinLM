from __future__ import annotations

from pathlib import Path

from app_service.goal_executor import GoalExecutor
from app_service.skill_manager import SkillStore


def _write_profile(root: Path, profile_id: str = "default_1920x1080") -> None:
    profiles = root / "configs" / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / f"{profile_id}.json").write_text(
        '{"profile_id":"default_1920x1080","window_title":"unit","source_resolution":[1920,1080],"normalized_resolution":[1280,720],"rois":{}}',
        encoding="utf-8",
    )


def test_execute_goal_daily_commission_compiles_known_template(tmp_path: Path) -> None:
    _write_profile(tmp_path)
    executor = GoalExecutor(tmp_path, SkillStore(tmp_path))

    result = executor.execute_goal(
        goal_text="完成每日委托",
        profile="default_1920x1080",
        live_mode=False,
        mode="safe-window",
        exploration_profile="aggressive_deep_probe",
    )

    assert result.ok is True
    assert result.compiled_strategy == "known_template_daily_commission"
    assert "claim_daily_reward" in result.completed_nodes
    assert result.goal_phase == "completed"


def test_execute_goal_unknown_task_generates_learning_review_queue(tmp_path: Path) -> None:
    _write_profile(tmp_path)
    store = SkillStore(tmp_path)
    executor = GoalExecutor(tmp_path, store)

    result = executor.execute_goal(
        goal_text="做这个新的支线任务",
        profile="default_1920x1080",
        live_mode=False,
        mode="safe-window",
        exploration_profile="aggressive_deep_probe",
    )

    assert result.ok is True
    assert result.compiled_strategy == "unknown_autonomous_exploration"
    assert len(result.learning_review_queue) >= 1
    queue = executor.list_learning_review_queue()
    assert len(queue) >= 1
    patch_id = queue[0]["patch_id"]
    adjusted = executor.adjust_learning_patch(patch_id, {"aggressiveness": "high"})
    assert adjusted["ok"] is True
    rolled_back = executor.rollback_learning_patch(patch_id)
    assert rolled_back["ok"] is True
