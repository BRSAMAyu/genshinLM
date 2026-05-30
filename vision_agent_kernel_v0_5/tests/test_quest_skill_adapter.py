"""Tests for QuestSkillAdapter: dialog/cutscene/quest state management."""
from __future__ import annotations

from planning.quest_skill_adapter import (
    QuestSkillAdapter,
    QuestSkillAdapterConfig,
)
from execution.console_backend import ConsoleInputBackend


class _FakeBus:
    class _Slot:
        def get(self):
            return None

    latest_observation = _Slot()


def test_drive_dialog_no_bus():
    adapter = QuestSkillAdapter(
        backend=ConsoleInputBackend(),
        config=QuestSkillAdapterConfig(max_dialog_steps=3),
    )
    # No bus → dialog won't detect end, hits max steps → returns False
    result = adapter.drive_dialog()
    assert result is False


def test_drive_dialog_with_fake_bus():
    adapter = QuestSkillAdapter(
        backend=ConsoleInputBackend(),
        state_bus=_FakeBus(),
        config=QuestSkillAdapterConfig(max_dialog_steps=3),
    )
    # Fake bus returns None obs → dialog won't detect end
    result = adapter.drive_dialog()
    assert result is False


def test_skip_cutscene_no_bus():
    adapter = QuestSkillAdapter(
        backend=ConsoleInputBackend(),
        config=QuestSkillAdapterConfig(cutscene_check_interval_ms=100),
    )
    # No bus → can't detect screen state → timeout
    result = adapter.skip_cutscene(timeout_sec=0.5)
    assert result is False


def test_advance_quest_no_sm():
    adapter = QuestSkillAdapter(backend=ConsoleInputBackend())
    result = adapter.advance_quest(evidence="test")
    assert result is True


def test_check_prerequisites_no_sm():
    adapter = QuestSkillAdapter(backend=ConsoleInputBackend())
    result = adapter.check_prerequisites(current_ar=10)
    assert result is True


def test_follow_quest_marker():
    adapter = QuestSkillAdapter(backend=ConsoleInputBackend())
    result = adapter.follow_quest_marker(navigate_fn=lambda: True)
    assert result is True


def test_follow_quest_marker_failure():
    adapter = QuestSkillAdapter(backend=ConsoleInputBackend())
    result = adapter.follow_quest_marker(navigate_fn=lambda: False)
    assert result is False


def test_follow_quest_marker_exception():
    adapter = QuestSkillAdapter(backend=ConsoleInputBackend())

    def _fail():
        raise RuntimeError("test error")

    result = adapter.follow_quest_marker(navigate_fn=_fail)
    assert result is False
