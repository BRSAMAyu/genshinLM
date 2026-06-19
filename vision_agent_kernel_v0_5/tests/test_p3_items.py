"""Tests for P3 items: API budget, receipt state machine, screen state kind,
failure analyzer, sentinel coverage, crash recovery physical, telemetry replay,
checkpoint coordinator, skill versioning."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---- API Budget Limiter ----

from runtime.api_budget_limiter import ApiBudgetLimiter, BudgetConfig, BudgetExhausted


class TestApiBudgetLimiter:
    def test_allows_within_budget(self):
        limiter = ApiBudgetLimiter(BudgetConfig(max_calls_per_session=5))
        entry = limiter.record_call("test_api", "gpt-4", 0.01)
        assert entry.api_name == "test_api"
        assert limiter.total_calls == 1
        assert limiter.total_cost_usd == 0.01

    def test_blocks_over_call_limit(self):
        limiter = ApiBudgetLimiter(BudgetConfig(max_calls_per_session=2))
        limiter.record_call("a")
        limiter.record_call("a")
        with pytest.raises(BudgetExhausted, match="call limit"):
            limiter.record_call("a")

    def test_blocks_over_cost_limit(self):
        limiter = ApiBudgetLimiter(BudgetConfig(max_cost_usd_per_session=0.01))
        limiter.record_call("a", estimated_cost_usd=0.009)
        with pytest.raises(BudgetExhausted, match="cost limit"):
            limiter.record_call("a", estimated_cost_usd=0.005)

    def test_try_record_returns_none_on_exhausted(self):
        limiter = ApiBudgetLimiter(BudgetConfig(max_calls_per_session=1))
        limiter.record_call("a")
        assert limiter.try_record_call("a") is None

    def test_summary(self):
        limiter = ApiBudgetLimiter(BudgetConfig(max_cost_usd_per_session=1.0))
        limiter.record_call("vlm", estimated_cost_usd=0.05)
        limiter.record_call("vlm", estimated_cost_usd=0.03)
        summary = limiter.get_summary()
        assert summary["total_calls"] == 2
        assert summary["total_cost_usd"] == 0.08
        assert summary["calls_per_api"]["vlm"] == 2

    def test_per_api_limit(self):
        config = BudgetConfig(max_calls_per_api_per_session={"expensive": 2})
        limiter = ApiBudgetLimiter(config)
        limiter.record_call("expensive")
        limiter.record_call("expensive")
        with pytest.raises(BudgetExhausted, match="API limit"):
            limiter.record_call("expensive")

    def test_reset(self):
        limiter = ApiBudgetLimiter()
        limiter.record_call("a")
        limiter.reset()
        assert limiter.total_calls == 0
        assert limiter.total_cost_usd == 0.0


# ---- Receipt State Machine ----

from execution.receipt_state_machine import (
    ReceiptState, validate_transition, enforce_transition,
    InvalidTransition, is_terminal, next_expected_step,
)


class TestReceiptStateMachine:
    def test_valid_happy_path(self):
        result = validate_transition(ReceiptState.PENDING, ReceiptState.SUBMITTED)
        assert result.success

    def test_invalid_skip(self):
        result = validate_transition(ReceiptState.PENDING, ReceiptState.EXECUTED)
        assert not result.success
        assert "Invalid transition" in result.error

    def test_failure_from_any_non_terminal(self):
        for state in [ReceiptState.PENDING, ReceiptState.SUBMITTED, ReceiptState.LEASE_ACCEPTED]:
            result = validate_transition(state, ReceiptState.FAILED)
            assert result.success, f"Should allow FAILED from {state}"

    def test_terminal_states_no_transitions(self):
        for terminal in [ReceiptState.VERIFIED, ReceiptState.FAILED]:
            for target in ReceiptState:
                result = validate_transition(terminal, target)
                assert not result.success, f"Terminal {terminal} should not transition"

    def test_enforce_raises_on_invalid(self):
        with pytest.raises(InvalidTransition):
            enforce_transition(ReceiptState.VERIFIED, ReceiptState.PENDING)

    def test_is_terminal(self):
        assert is_terminal(ReceiptState.VERIFIED)
        assert is_terminal(ReceiptState.FAILED)
        assert not is_terminal(ReceiptState.PENDING)

    def test_next_expected_step(self):
        assert next_expected_step(ReceiptState.PENDING) == "submit"
        assert next_expected_step(ReceiptState.EXECUTED) == "verify"


# ---- ScreenStateKind ----

from perception.screen_state_kind import ScreenStateKind, canonicalize, register_game_mapping


class TestScreenStateKind:
    def test_genshin_loading(self):
        assert canonicalize("loading_screen", "genshin") == ScreenStateKind.LOADING

    def test_genshin_overworld(self):
        assert canonicalize("world_hud", "genshin") == ScreenStateKind.OVERWORLD

    def test_direct_enum_match(self):
        assert canonicalize("combat") == ScreenStateKind.COMBAT

    def test_unknown_state(self):
        assert canonicalize("totally_made_up_state") == ScreenStateKind.UNKNOWN

    def test_custom_game_mapping(self):
        register_game_mapping("mygame", {"lobby": ScreenStateKind.MENU})
        assert canonicalize("lobby", "mygame") == ScreenStateKind.MENU

    def test_fallback_to_any_game_mapping(self):
        # "loading_screen" exists in genshin map, should be found even without game_id
        assert canonicalize("loading_screen") == ScreenStateKind.LOADING


# ---- Generic Failure Analyzer ----

from learning.generic_failure_analyzer import (
    GenericFailureAnalyzer, FailureCategory, FailureSignature,
    make_failure_signature,
)


class TestGenericFailureAnalyzer:
    def test_record_and_stats(self):
        analyzer = GenericFailureAnalyzer()
        sig = make_failure_signature(FailureCategory.TARGET_LOST, encounter_id="enemy_1")
        analyzer.record_failure(sig)
        stats = analyzer.get_failure_stats()
        assert stats["target_lost"] == 1

    def test_pattern_detection_requires_threshold(self):
        analyzer = GenericFailureAnalyzer()
        for i in range(3):
            analyzer.record_failure(make_failure_signature(
                FailureCategory.HP_DEPLETED, encounter_id="boss_1",
            ))
        patterns = analyzer.analyze_patterns()
        assert any(p.category == FailureCategory.HP_DEPLETED for p in patterns)

    def test_no_patterns_below_threshold(self):
        analyzer = GenericFailureAnalyzer()
        analyzer.record_failure(make_failure_signature(FailureCategory.COMBAT_TIMEOUT))
        patterns = analyzer.analyze_patterns()
        assert not patterns

    def test_suggestions(self):
        analyzer = GenericFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(make_failure_signature(
                FailureCategory.NAVIGATION_FAILED, region="mondstadt",
            ))
        suggestions = analyzer.get_suggestions()
        assert len(suggestions) >= 1

    def test_signature_fields(self):
        sig = make_failure_signature(
            FailureCategory.SKILL_MISS, encounter_id="boss", step_index=5,
            region="liyue", game_specific={"element": "pyro"},
        )
        assert sig.category == FailureCategory.SKILL_MISS
        assert sig.encounter_id == "boss"
        assert sig.game_specific["element"] == "pyro"


# ---- Sentinel Coverage ----

from control.sentinel.sentinel_coverage import (
    SentinelCoverageTracker, SentinelSpec,
)


class TestSentinelCoverage:
    def test_register_and_coverage(self):
        tracker = SentinelCoverageTracker()
        tracker.register_spec(SentinelSpec("focus_loss", "Focus lost", critical=True))
        tracker.register_spec(SentinelSpec("stuck_state", "Stuck state"))
        tracker.record_fire("focus_loss")
        assert tracker.coverage_pct == 50.0
        assert tracker.critical_coverage_pct == 100.0

    def test_uncovered(self):
        tracker = SentinelCoverageTracker()
        tracker.register_spec(SentinelSpec("a", "A", critical=True))
        tracker.register_spec(SentinelSpec("b", "B"))
        tracker.record_fire("a")
        uncovered = tracker.get_uncovered()
        assert len(uncovered) == 1
        assert uncovered[0].sentinel_id == "b"

    def test_uncovered_critical(self):
        tracker = SentinelCoverageTracker()
        tracker.register_spec(SentinelSpec("a", "A", critical=True))
        tracker.register_spec(SentinelSpec("b", "B"))
        assert len(tracker.get_uncovered_critical()) == 1

    def test_summary(self):
        tracker = SentinelCoverageTracker()
        tracker.register_spec(SentinelSpec("a", "A", critical=True, category="safety"))
        tracker.record_fire("a")
        summary = tracker.get_summary()
        assert summary["total_sentinels"] == 1
        assert summary["covered_sentinels"] == 1
        assert summary["by_category"]["safety"]["covered"] == 1

    def test_reset_keeps_specs(self):
        tracker = SentinelCoverageTracker()
        tracker.register_spec(SentinelSpec("a", "A"))
        tracker.record_fire("a")
        tracker.reset()
        assert tracker.coverage_pct == 0.0


# ---- Telemetry Replay ----

from telemetry.telemetry_replay import TelemetryReplay, ReplayEvent


class TestTelemetryReplay:
    def test_load_jsonl(self, tmp_path: Path):
        events_file = tmp_path / "events.jsonl"
        lines = [
            json.dumps({"timestamp": 1.0, "event_type": "click", "payload": {"x": 100}}),
            json.dumps({"timestamp": 2.0, "event_type": "key", "payload": {"key": "W"}}),
        ]
        events_file.write_text("\n".join(lines), encoding="utf-8")

        replay = TelemetryReplay(events_file)
        count = replay.load()
        assert count == 2
        assert replay.event_count == 2

    def test_filter_by_type(self, tmp_path: Path):
        events_file = tmp_path / "events.jsonl"
        lines = [
            json.dumps({"timestamp": 1.0, "event_type": "click", "payload": {}}),
            json.dumps({"timestamp": 2.0, "event_type": "key", "payload": {}}),
            json.dumps({"timestamp": 3.0, "event_type": "click", "payload": {}}),
        ]
        events_file.write_text("\n".join(lines), encoding="utf-8")

        replay = TelemetryReplay(events_file, event_filter={"click"})
        replay.load()
        assert replay.event_count == 2

    def test_instant_iteration(self, tmp_path: Path):
        events_file = tmp_path / "events.jsonl"
        lines = [
            json.dumps({"timestamp": float(i), "event_type": "tick", "payload": {}})
            for i in range(5)
        ]
        events_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        replay = TelemetryReplay(events_file)
        events = list(replay.iterate_instant())
        assert len(events) == 5

    def test_find_events(self, tmp_path: Path):
        events_file = tmp_path / "events.jsonl"
        lines = [
            json.dumps({"timestamp": 1.0, "event_type": "click", "payload": {"x": 1}}),
            json.dumps({"timestamp": 2.0, "event_type": "click", "payload": {"x": 2}}),
        ]
        events_file.write_text("\n".join(lines), encoding="utf-8")

        replay = TelemetryReplay(events_file)
        clicks = replay.find_events("click")
        assert len(clicks) == 2

    def test_stats(self, tmp_path: Path):
        events_file = tmp_path / "events.jsonl"
        lines = [
            json.dumps({"timestamp": 1.0, "event_type": "a", "payload": {}}),
            json.dumps({"timestamp": 5.0, "event_type": "b", "payload": {}}),
        ]
        events_file.write_text("\n".join(lines), encoding="utf-8")

        replay = TelemetryReplay(events_file)
        stats = replay.get_stats()
        assert stats.total_events == 2
        assert stats.time_span_sec == 4.0

    def test_missing_file(self):
        replay = TelemetryReplay("/nonexistent/file.jsonl")
        assert replay.load() == 0


# ---- Crash Recovery Physical ----

from execution.crash_recovery_physical import (
    CrashRecoveryPhysicalActions, RecoveryStep, RecoveryAction, PhysicalExecutor,
)


class TestCrashRecoveryPhysical:
    def test_restart_sequence_planned(self):
        actions = CrashRecoveryPhysicalActions(executor=None)
        steps = actions.execute_restart_sequence("GenshinImpact.exe")
        assert len(steps) >= 2
        assert steps[0].action == RecoveryAction.LAUNCH_GAME

    def test_reconnect_sequence_planned(self):
        actions = CrashRecoveryPhysicalActions(executor=None)
        steps = actions.execute_reconnect_sequence()
        assert len(steps) >= 2
        assert any(s.action == RecoveryAction.WAIT for s in steps)

    def test_restore_sequence_with_quest(self):
        actions = CrashRecoveryPhysicalActions(executor=None)
        steps = actions.execute_restore_sequence(quest_id="q_1001", quest_phase="phase_2")
        assert len(steps) == 2
        assert steps[0].params["quest_id"] == "q_1001"

    def test_executed_steps_with_mock(self):
        mock_executor = MagicMock(spec=PhysicalExecutor)
        mock_executor.execute_step.return_value = True
        actions = CrashRecoveryPhysicalActions(executor=mock_executor)
        steps = actions.execute_restart_sequence()
        assert mock_executor.execute_step.call_count == len(steps)


# ---- Checkpoint Coordinator ----

from runtime.checkpoint_coordinator import CheckpointCoordinator, CheckpointWriter


class _MemoryWriter:
    def __init__(self) -> None:
        self.data: dict[str, Any] | None = None
    def save_checkpoint(self, data: dict) -> str:
        self.data = data
        return "ok"
    def load_latest(self) -> dict | None:
        return self.data


class TestCheckpointCoordinator:
    def test_save_all(self):
        qw = _MemoryWriter()
        ew = _MemoryWriter()
        coord = CheckpointCoordinator(quest_writer=qw, execution_writer=ew)
        cp = coord.save_all(
            quest_data={"quest_id": "q1"},
            execution_data={"node_id": "n1"},
        )
        assert cp.quest_context["quest_id"] == "q1"
        assert qw.data is not None
        assert ew.data is not None

    def test_load_all(self):
        qw = _MemoryWriter()
        qw.data = {"quest_id": "q1"}
        coord = CheckpointCoordinator(quest_writer=qw)
        cp = coord.load_all()
        assert cp is not None
        assert cp.quest_context["quest_id"] == "q1"

    def test_empty_load(self):
        coord = CheckpointCoordinator()
        assert coord.load_all() is None

    def test_save_count(self):
        coord = CheckpointCoordinator()
        coord.save_all(quest_data={"a": 1})
        coord.save_all(quest_data={"b": 2})
        assert coord.save_count == 2


# ---- Skill Versioning ----

from planning.skill_registry import SkillRegistry, LearnedSkill


class TestSkillVersioning:
    def test_new_skill_version_1(self, tmp_path: Path):
        path = str(tmp_path / "skills.json")
        registry = SkillRegistry(persist_path=path)
        skill = LearnedSkill(
            skill_id="test_1", action="test", steps=(),
        )
        registry.register_learned_skill(skill)
        assert registry.get_skill_version("test_1") == 1

    def test_version_increments_on_reregister(self, tmp_path: Path):
        path = str(tmp_path / "skills.json")
        registry = SkillRegistry(persist_path=path)
        skill = LearnedSkill(
            skill_id="test_2", action="test", steps=(),
        )
        registry.register_learned_skill(skill)
        registry.register_learned_skill(skill)
        assert registry.get_skill_version("test_2") == 2

    def test_version_persisted(self, tmp_path: Path):
        path = str(tmp_path / "skills.json")
        registry = SkillRegistry(persist_path=path)
        skill = LearnedSkill(
            skill_id="test_3", action="test", steps=(),
        )
        registry.register_learned_skill(skill)
        registry.register_learned_skill(skill)

        # Reload from disk
        registry2 = SkillRegistry(persist_path=path)
        loaded = registry2.get_learned_skill("test_3")
        assert loaded is not None
        assert loaded.version == 2

    def test_hot_reload(self, tmp_path: Path):
        path = str(tmp_path / "skills.json")
        registry = SkillRegistry(persist_path=path)
        skill = LearnedSkill(
            skill_id="test_4", action="test", steps=(),
        )
        registry.register_learned_skill(skill)

        # Simulate external modification
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data.append({
            "skill_id": "test_5", "action": "new", "steps": [],
            "confidence": 0.5, "verification_count": 0,
            "trust_level": "candidate", "capsule_id": "",
            "created_at": 0.0, "version": 1,
        })
        Path(path).write_text(json.dumps(data), encoding="utf-8")

        count = registry.hot_reload_skills()
        assert registry.get_learned_skill("test_5") is not None
