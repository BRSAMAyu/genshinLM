from __future__ import annotations

from pathlib import Path

from app_service.skill_manager import SkillStore


def _write_profile(root: Path, profile_id: str = "default_1920x1080") -> None:
    profiles = root / "configs" / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / f"{profile_id}.json").write_text(
        '{"profile_id":"default_1920x1080","window_title":"unit","source_resolution":[1920,1080],"normalized_resolution":[1280,720],"rois":{}}',
        encoding="utf-8",
    )


def _skill_payload(skill_id: str = "unit_skill") -> dict:
    return {
        "skill_id": skill_id,
        "name": "Unit Skill",
        "type": "ui",
        "version": 1,
        "metadata": {"source": "test"},
        "environment_profile": "default_1920x1080",
        "preconditions": ["require_focus"],
        "steps": [
            {
                "step_id": "wait_started",
                "type": "wait_visual_trigger",
                "timeout_ms": 1000,
                "interruptible": True,
                "params": {"trigger": "action_started", "chunk_ms": 100},
            }
        ],
        "visual_triggers": {"action_started": {"type": "target_color_green"}},
        "success_criteria": ["visual_action_completed"],
        "failure_policy": {"max_retries": 1, "fallback": "pause_and_reacquire"},
        "cleanup": [{"type": "release_all"}],
        "safety": {"dry_run_default": True, "interruptible": True, "require_focus": True, "max_duration_ms": 3000},
    }


def test_list_skills_recovers_when_index_read_denied(tmp_path: Path, monkeypatch) -> None:
    _write_profile(tmp_path)
    store = SkillStore(tmp_path)
    store.save_skill(_skill_payload("recover_from_read_deny"))

    original_read_text = Path.read_text

    def patched_read_text(path: Path, *args, **kwargs):  # type: ignore[override]
        if path == store._index_path:
            raise PermissionError("locked index")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", patched_read_text)
    listed = store.list_skills()["skills"]
    assert any(item["skill_id"] == "recover_from_read_deny" for item in listed)


def test_save_skill_survives_index_write_denied(tmp_path: Path, monkeypatch) -> None:
    _write_profile(tmp_path)
    store = SkillStore(tmp_path)

    original_write_text = Path.write_text

    def patched_write_text(path: Path, *args, **kwargs):  # type: ignore[override]
        if path.name == "index.json.tmp":
            raise PermissionError("index tmp write denied")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", patched_write_text)
    skill = store.save_skill(_skill_payload("recover_from_write_deny"))
    assert skill.skill_id == "recover_from_write_deny"
    listed = store.list_skills()["skills"]
    assert any(item["skill_id"] == "recover_from_write_deny" for item in listed)
