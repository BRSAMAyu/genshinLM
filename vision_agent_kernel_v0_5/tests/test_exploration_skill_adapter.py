"""Tests for ExplorationSkillAdapter: waypoint/chest/oculus interaction."""
from __future__ import annotations

from exploration.exploration_skill_adapter import (
    ExplorationSkillAdapter,
    ExplorationSkillAdapterConfig,
)
from execution.console_backend import ConsoleInputBackend


def test_activate_waypoint():
    adapter = ExplorationSkillAdapter(
        backend=ConsoleInputBackend(),
        config=ExplorationSkillAdapterConfig(max_interact_retries=1),
    )
    result = adapter.activate_waypoint()
    assert result is True


def test_open_chest():
    adapter = ExplorationSkillAdapter(
        backend=ConsoleInputBackend(),
        config=ExplorationSkillAdapterConfig(max_interact_retries=1),
    )
    result = adapter.open_chest()
    assert result is True


def test_collect_oculus():
    adapter = ExplorationSkillAdapter(
        backend=ConsoleInputBackend(),
        config=ExplorationSkillAdapterConfig(max_interact_retries=1),
    )
    result = adapter.collect_oculus()
    assert result is True


def test_interact_with_object():
    adapter = ExplorationSkillAdapter(
        backend=ConsoleInputBackend(),
        config=ExplorationSkillAdapterConfig(max_interact_retries=1),
    )
    result = adapter.interact_with_object("statue")
    assert result is True


def test_interact_with_object_default_type():
    adapter = ExplorationSkillAdapter(
        backend=ConsoleInputBackend(),
        config=ExplorationSkillAdapterConfig(max_interact_retries=1),
    )
    result = adapter.interact_with_object()
    assert result is True
