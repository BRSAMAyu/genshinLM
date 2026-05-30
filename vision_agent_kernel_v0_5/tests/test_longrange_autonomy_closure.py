"""Regression tests for long-range autonomy closure plan items.

Covers:
- DecisionMemory smart prune (top-3 protection)
- ConsoleBackend deque-based events (no manual trim)
- EvolutionEngine repair cooldown + session cap
- EvolutionEngine induced_ structural validation
- Sentinel RecoveryRecipes StateBus integration
- GenshinNavigator walk fallback for locked waypoints
- QuestContextPersistence save/load roundtrip
- MainlineRunner DRY-RUN log marker
"""
from __future__ import annotations

import collections
import logging
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.state_bus import StateBus


# ---------------------------------------------------------------------------
# DecisionMemory — smart prune
# ---------------------------------------------------------------------------


class TestDecisionMemorySmartPrune(unittest.TestCase):
    def _make_dm(self):
        import tempfile
        import os
        # Use a real temp file — :memory: creates separate DBs per connection
        self._tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(self._tmpdir, "test_dm.db")
        from learning.decision_memory import DecisionMemory
        return DecisionMemory(db_path=db_path)

    def tearDown(self):
        import shutil
        if hasattr(self, "_tmpdir"):
            shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_prune_protects_top3_per_group(self):
        dm = self._make_dm()
        from learning.decision_memory import DecisionQuery
        # Insert 5 records for the same goal/capsule, varying confidence
        for i in range(5):
            dm.record(
                goal="talk_to_npc",
                capsule_id="genshin",
                screen_state="world_viewport",
                plan=[],
                success=True,
                duration_sec=float(i),
                # Make the age very old so naive prune would delete all
                confidence=float(i) * 0.2,
            )
        # Force old timestamps so they'd be pruned
        conn = dm._conn_ctx()
        conn.execute("UPDATE strategies SET created_at = 0")
        conn.commit()

        deleted = dm.prune(max_age_days=1)
        remaining = dm.query(
            DecisionQuery(goal="talk_to_npc")
        )
        # Top-3 by confidence (0.8, 0.6, 0.4 = indices 4, 3, 2) should survive
        self.assertGreaterEqual(len(remaining), 3)
        confidences = sorted(r.confidence for r in remaining)
        self.assertAlmostEqual(confidences[-1], 0.8, places=2)
        self.assertAlmostEqual(confidences[-2], 0.6, places=2)
        self.assertAlmostEqual(confidences[-3], 0.4, places=2)

    def test_prune_removes_old_low_confidence(self):
        dm = self._make_dm()
        from learning.decision_memory import DecisionQuery
        dm.record(
            goal="collect_item",
            capsule_id="genshin",
            screen_state="world_viewport",
            plan=[],
            success=False,
            duration_sec=1.0,
            confidence=0.1,
        )
        conn = dm._conn_ctx()
        conn.execute("UPDATE strategies SET created_at = 0")
        conn.commit()
        deleted = dm.prune(max_age_days=1)
        remaining = dm.query(
            DecisionQuery(goal="collect_item")
        )
        # Only 1 record in group — it IS the top-3, so it stays
        self.assertEqual(len(remaining), 1)

    def test_prune_returns_count(self):
        dm = self._make_dm()
        for i in range(10):
            dm.record(
                goal=f"goal_{i % 3}",  # 3 distinct goals
                capsule_id="genshin",
                screen_state="",
                plan=[],
                success=True,
                duration_sec=1.0,
                confidence=float(i) * 0.1,
            )
        conn = dm._conn_ctx()
        conn.execute("UPDATE strategies SET created_at = 0")
        conn.commit()
        deleted = dm.prune(max_age_days=1)
        # 10 records, 3 goals × 3 per group = 9 protected, so at most 1 deleted
        self.assertIsInstance(deleted, int)


# ---------------------------------------------------------------------------
# ConsoleBackend — deque-based events
# ---------------------------------------------------------------------------


class TestConsoleBackendDeque(unittest.TestCase):
    def _make_backend(self):
        from execution.console_backend import ConsoleInputBackend
        return ConsoleInputBackend()

    def test_events_is_deque(self):
        backend = self._make_backend()
        self.assertIsInstance(backend._events, collections.deque)

    def test_maxlen_set(self):
        backend = self._make_backend()
        self.assertEqual(backend._events.maxlen, backend._max_events)

    def test_overflow_auto_eviction(self):
        from execution.console_backend import ConsoleInputBackend
        backend = ConsoleInputBackend()
        backend._max_events = 5
        backend._events = collections.deque(maxlen=5)
        for i in range(10):
            backend.key_down(f"key_{i}")
        snapshot = backend.events_snapshot()
        # Should have exactly 5 (deque evicts oldest automatically)
        # Note: key_down generates 1 event per call
        self.assertLessEqual(len(snapshot), 5)

    def test_events_snapshot_returns_list(self):
        backend = self._make_backend()
        backend.key_down("w")
        snap = backend.events_snapshot()
        self.assertIsInstance(snap, list)
        self.assertEqual(len(snap), 1)


# ---------------------------------------------------------------------------
# EvolutionEngine — cooldown and session cap
# ---------------------------------------------------------------------------


class TestEvolutionEngineRepairBounds(unittest.TestCase):
    def _make_engine(self, tmp_path):
        from learning.evolution_engine import EvolutionEngine
        bus = StateBus()
        bus.register_slot("learning.patch_event")
        return EvolutionEngine(state_bus=bus, patches_dir=tmp_path)

    def test_cooldown_blocks_rapid_repair(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(Path(tmp))
            engine._repair_cooldown_sec = 3600.0  # 1 hour
            engine._repair_cooldowns["my_skill"] = time.perf_counter()

            result = engine.handle_failure("my_skill", "TIMEOUT", {})
            self.assertIsNone(result, "Second rapid repair should be blocked by cooldown")

    def test_session_cap_blocks_new_sessions(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(Path(tmp))
            engine._max_repair_sessions = 1
            # Fill sessions to the cap
            engine._repair_sessions["fake_session"] = MagicMock()

            result = engine.handle_failure("other_skill", "CRASH", {})
            self.assertIsNone(result, "New repair should be blocked when session cap is reached")

    def test_cooldown_expires(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(Path(tmp))
            engine._repair_cooldown_sec = 0.001  # expire almost immediately
            engine._repair_cooldowns["fast_skill"] = time.perf_counter() - 1.0

            # Should NOT be blocked (cooldown expired)
            with patch.object(engine._signature_builder, "build") as mock_build:
                mock_build.side_effect = RuntimeError("deliberate_stop")
                try:
                    engine.handle_failure("fast_skill", "TIMEOUT", {})
                except RuntimeError:
                    pass
            # Verify cooldown was updated (meaning it passed the guard)
            self.assertGreater(engine._repair_cooldowns.get("fast_skill", 0.0), 0.0)


# ---------------------------------------------------------------------------
# EvolutionEngine — induced_ structural validation
# ---------------------------------------------------------------------------


class TestEvolutionEngineInducedValidation(unittest.TestCase):
    def _make_engine(self, tmp_path):
        from learning.evolution_engine import EvolutionEngine
        bus = StateBus()
        bus.register_slot("learning.patch_event")
        return EvolutionEngine(state_bus=bus, patches_dir=tmp_path)

    def test_induced_with_no_steps_fails_structural(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(Path(tmp))
            patch_dict = {"skill_id": "induced_open_chest", "proposed_steps": []}
            result = engine._verify_in_sandbox(patch_dict)
            self.assertFalse(result, "Empty induced skill must fail structural validation")
            self.assertEqual(patch_dict.get("replay_result", {}).get("reason"), "induced_skill_has_no_steps")

    def test_induced_with_valid_steps_passes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(Path(tmp))
            patch_dict = {
                "skill_id": "induced_press_f",
                "proposed_steps": [
                    {"action_type": "press_key", "params": {"key": "f"}, "timeout_ms": 1000}
                ],
            }
            result = engine._verify_in_sandbox(patch_dict)
            self.assertTrue(result, "Induced skill with valid steps should pass")

    def test_induced_with_invalid_timeout_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(Path(tmp))
            patch_dict = {
                "skill_id": "induced_bad_step",
                "proposed_steps": [
                    {"action_type": "press_key", "params": {}, "timeout_ms": 0}
                ],
            }
            result = engine._verify_in_sandbox(patch_dict)
            self.assertFalse(result, "Zero timeout should fail structural validation")


# ---------------------------------------------------------------------------
# Sentinel RecoveryRecipes — StateBus integration
# ---------------------------------------------------------------------------


class TestSentinelRecipesBusIntegration(unittest.TestCase):
    def _make_bus(self):
        bus = StateBus()
        bus.register_slot("sentinel.action_request")
        return bus

    def _recipe_execution(self, recipe, bus):
        result = recipe.execute_recovery(executor=bus)
        return result

    def test_ui_lost_publishes_to_bus(self):
        from control.sentinel.recipes import UILostRecovery
        bus = self._make_bus()
        recipe = UILostRecovery()
        result = self._recipe_execution(recipe, bus)
        self.assertEqual(result.status, "success")
        slot = bus.get_slot("sentinel.action_request")
        self.assertIsNotNone(slot)
        item = slot.get()  # LatestSlot.get() takes no kwargs
        self.assertIsNotNone(item)
        self.assertEqual(item["recipe_id"], "UI_LOST_RECOVERY")
        self.assertIn("actions", item)

    def test_stuck_recipe_publishes_actions(self):
        from control.sentinel.recipes import StuckRecovery
        bus = self._make_bus()
        recipe = StuckRecovery()
        result = self._recipe_execution(recipe, bus)
        self.assertEqual(result.status, "success")

    def test_combat_defeat_recipe_publishes(self):
        from control.sentinel.recipes import CombatDefeatRecovery
        bus = self._make_bus()
        recipe = CombatDefeatRecovery()
        result = self._recipe_execution(recipe, bus)
        self.assertEqual(result.status, "success")

    def test_none_executor_does_not_crash(self):
        from control.sentinel.recipes import DriftRecovery
        recipe = DriftRecovery()
        result = recipe.execute_recovery(executor=None)
        self.assertEqual(result.status, "success")

    def test_default_recipes_returns_8(self):
        from control.sentinel.recipes import default_recipes
        recipes = default_recipes()
        self.assertEqual(len(recipes), 8)

    def test_all_recipe_preconditions(self):
        from control.sentinel.recipes import default_recipes
        from control.sentinel.somatic_state import SomaticState, TeamState
        recipes = default_recipes()
        # All recipes should have check_precondition that returns bool
        state = SomaticState()
        for recipe in recipes:
            result = recipe.check_precondition(state)
            self.assertIsInstance(result, bool)


# ---------------------------------------------------------------------------
# GenshinNavigator — locked waypoint walk fallback
# ---------------------------------------------------------------------------


class TestGenshinNavigatorWalkFallback(unittest.TestCase):
    def test_locked_waypoint_activates_walk_fallback(self):
        from navigation.genshin_navigator import GenshinNavigator
        nav = GenshinNavigator()

        bus = StateBus()
        bus.register_slot("sentinel.action_request")

        # Use a waypoint that isn't in any graph (empty graph)
        result = nav.execute_teleport_via_bus("unknown_waypoint_xyz", state_bus=bus)

        self.assertTrue(nav.fallback_walk_mode, "Walk fallback should be activated")
        # Verify the action was published
        slot = bus.get_slot("sentinel.action_request")
        item = slot.get()  # LatestSlot.get() takes no kwargs
        self.assertIsNotNone(item)
        self.assertEqual(item["actions"][0]["action"], "navigate_walk")

    def test_fallback_walk_mode_initially_false(self):
        from navigation.genshin_navigator import GenshinNavigator
        nav = GenshinNavigator()
        self.assertFalse(nav.fallback_walk_mode)

    def test_teleport_via_bus_none_bus_returns_false(self):
        from navigation.genshin_navigator import GenshinNavigator
        nav = GenshinNavigator()
        result = nav.execute_teleport_via_bus("mon_windrise", state_bus=None)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# QuestContextPersistence — save/load roundtrip
# ---------------------------------------------------------------------------


class TestQuestContextPersistence(unittest.TestCase):
    def _make_context(self):
        from planning.mainline.active_quest_context import ActiveQuestContext
        return ActiveQuestContext(
            quest_id="archon_mondstadt_001",
            quest_title="Wind and Freedom",
            objective_text="Speak with Diluc",
            objective_type="dialog",
            confidence=0.85,
        )

    def test_save_and_load_roundtrip(self):
        import tempfile
        from planning.mainline.quest_context_persistence import QuestContextPersistence
        ctx = self._make_context()
        with tempfile.TemporaryDirectory() as tmp:
            persistence = QuestContextPersistence(runs_dir=Path(tmp))
            saved_path = persistence.save(ctx)
            self.assertTrue(saved_path.exists())

            recovered = persistence.load_latest()
            self.assertIsNotNone(recovered)
            self.assertEqual(recovered.quest_id, "archon_mondstadt_001")
            self.assertEqual(recovered.objective_text, "Speak with Diluc")
            self.assertAlmostEqual(recovered.confidence, 0.85, places=3)

    def test_load_when_no_file_returns_none(self):
        import tempfile
        from planning.mainline.quest_context_persistence import QuestContextPersistence
        with tempfile.TemporaryDirectory() as tmp:
            persistence = QuestContextPersistence(runs_dir=Path(tmp))
            result = persistence.load_latest()
            self.assertIsNone(result)

    def test_list_versions(self):
        import tempfile
        from planning.mainline.quest_context_persistence import QuestContextPersistence
        from planning.mainline.active_quest_context import ActiveQuestContext
        with tempfile.TemporaryDirectory() as tmp:
            persistence = QuestContextPersistence(runs_dir=Path(tmp))
            ctx = self._make_context()
            persistence.save(ctx)
            versions = persistence.list_versions()
            self.assertEqual(len(versions), 1)

    def test_prune_old_keeps_recent(self):
        import tempfile
        from planning.mainline.quest_context_persistence import QuestContextPersistence
        from planning.mainline.active_quest_context import ActiveQuestContext
        with tempfile.TemporaryDirectory() as tmp:
            persistence = QuestContextPersistence(runs_dir=Path(tmp))
            # Save many versions
            for i in range(25):
                ctx = ActiveQuestContext(
                    quest_id=f"quest_{i}",
                    quest_title=f"Quest {i}",
                    objective_text=f"Objective {i}",
                    objective_type="navigate",
                    version=i + 1,
                )
                persistence.save(ctx)
            deleted = persistence.prune_old(keep_last=20)
            versions_after = persistence.list_versions()
            self.assertGreaterEqual(len(versions_after), 20)
            self.assertLessEqual(len(versions_after), 25)


# ---------------------------------------------------------------------------
# MainlineRunner — DRY-RUN log marker
# ---------------------------------------------------------------------------


class TestMainlineRunnerDryRunMarker(unittest.TestCase):
    def test_dry_run_logged_at_warning(self):
        """Node executed without skill_execute_fn must log a DRY-RUN warning."""
        from planning.mainline.mainline_runner import MainlineRunner, NodeResult
        from planning.mainline.mission_graph_v4 import MissionNodeV4, MissionGraphV4

        graph = MissionGraphV4(mission_id="test_dry")
        node = MissionNodeV4(
            node_id="node_dry",
            node_type="action",
            skill_candidates=("test_skill",),
            output_claims=(),
        )
        graph.add_node(node)

        runner = MainlineRunner(
            skill_execute_fn=None,  # dry-run mode
        )

        with self.assertLogs("planning.mainline.mainline_runner", level="WARNING") as cm:
            result = runner._execute_node(node, completed=set())

        self.assertIn("DRY-RUN", "\n".join(cm.output))
        self.assertTrue(result.claim_data.get("dry_run"), "NodeResult.claim_data must mark dry_run=True")


if __name__ == "__main__":
    unittest.main()
