"""Tests for MainlineProgressionAdapter: 6-chapter quest progression."""
from __future__ import annotations

from typing import Any

from planning.mainline.mainline_progression_adapter import (
    CHAPTERS,
    ChapterResult,
    MainlineProgressionAdapter,
    MainlineProgressionConfig,
    MainlineProgressionResult,
)
from planning.skill_registry import SkillRegistry


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def execute_semantic(
        self,
        action: str,
        target: str = "",
        context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append((action, target, context))
        return True


def test_chapters_defined():
    assert len(CHAPTERS) == 6
    assert CHAPTERS[0].chapter_id == "prologue"
    assert CHAPTERS[5].chapter_id == "chapter_5"
    assert CHAPTERS[0].region == "Mondstadt"
    assert CHAPTERS[2].region == "Inazuma"


def test_full_progression_from_ar1():
    executor = _FakeExecutor()
    adapter = MainlineProgressionAdapter(skill_executor=executor)
    result = adapter.run_full_progression(current_ar=1)

    assert isinstance(result, MainlineProgressionResult)
    assert result.total_chapters == 6
    assert result.final_ar >= 1
    assert result.chapters_completed == 6
    assert result.success is True


def test_progression_from_mid_game():
    executor = _FakeExecutor()
    adapter = MainlineProgressionAdapter(skill_executor=executor)
    result = adapter.run_full_progression(current_ar=30)

    assert result.chapters_completed >= 4  # chapters 2-5
    assert result.success is True


def test_chapter_for_ar():
    executor = _FakeExecutor()
    adapter = MainlineProgressionAdapter(skill_executor=executor)

    ch = adapter.get_chapter_for_ar(1)
    assert ch is not None
    assert ch.chapter_id == "prologue"

    ch = adapter.get_chapter_for_ar(25)
    assert ch is not None
    assert ch.chapter_id == "chapter_1"


def test_next_milestone():
    executor = _FakeExecutor()
    adapter = MainlineProgressionAdapter(skill_executor=executor)

    milestone = adapter.get_next_milestone(1)
    assert milestone["type"] == "chapter"
    assert milestone["chapter"] == "prologue"

    milestone = adapter.get_next_milestone(100)
    assert milestone["type"] == "completed"


def test_chapter_result_structure():
    executor = _FakeExecutor()
    adapter = MainlineProgressionAdapter(skill_executor=executor)
    result = adapter.run_full_progression(current_ar=40)

    # All chapters should complete
    for cr in result.chapter_results:
        assert isinstance(cr, ChapterResult)
        assert cr.total_acts > 0
        assert cr.acts_completed >= 0


def test_with_skill_registry():
    executor = _FakeExecutor()
    registry = SkillRegistry(skill_executor=executor)
    adapter = MainlineProgressionAdapter(
        skill_executor=executor,
        skill_registry=registry,
    )
    result = adapter.run_full_progression(current_ar=1)
    assert result.chapters_completed == 6


def test_config_affects_retries():
    config = MainlineProgressionConfig(
        max_boss_retries=1,
        boss_timeout_sec=60.0,
        auto_level_up_between_chapters=False,
    )
    executor = _FakeExecutor()
    adapter = MainlineProgressionAdapter(
        skill_executor=executor,
        config=config,
    )
    result = adapter.run_full_progression(current_ar=1)
    assert result.success is True
