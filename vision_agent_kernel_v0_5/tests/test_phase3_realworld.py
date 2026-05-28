"""Tests for Phase 3 real-world deployment components."""
from __future__ import annotations

import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock


class TestAutoCalibrator(unittest.TestCase):
    def test_aspect_ratio_perfect_match(self):
        import numpy as np
        from perception.auto_calibrator import AutoCalibrator, REFERENCE_WIDTH, REFERENCE_HEIGHT

        cal = AutoCalibrator()
        # Create a black frame at reference resolution
        frame = np.zeros((REFERENCE_HEIGHT, REFERENCE_WIDTH, 3), dtype=np.uint8)
        snap = cal.calibrate(frame)
        self.assertTrue(snap.valid)
        self.assertAlmostEqual(snap.scale.scale_x, 1.0)
        self.assertAlmostEqual(snap.scale.scale_y, 1.0)

    def test_aspect_ratio_wide(self):
        import numpy as np
        from perception.auto_calibrator import AutoCalibrator, REFERENCE_WIDTH

        cal = AutoCalibrator()
        # 2560x1080 — ultrawide, should have horizontal letterboxing
        frame = np.zeros((1080, 2560, 3), dtype=np.uint8)
        snap = cal.calibrate(frame)
        self.assertTrue(snap.valid)
        self.assertGreater(snap.scale.offset_x, 0)

    def test_aspect_ratio_tall(self):
        import numpy as np
        from perception.auto_calibrator import AutoCalibrator, REFERENCE_HEIGHT

        cal = AutoCalibrator()
        # 1080x1920 — portrait, should have vertical letterboxing
        frame = np.zeros((1920, 1080, 3), dtype=np.uint8)
        snap = cal.calibrate(frame)
        self.assertTrue(snap.valid)
        self.assertGreater(snap.scale.offset_y, 0)

    def test_to_screen_and_back(self):
        import numpy as np
        from perception.auto_calibrator import AutoCalibrator

        cal = AutoCalibrator()
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        snap = cal.calibrate(frame)
        scale = snap.scale

        # Reference point (960, 540) — center at 1920x1080
        sx, sy = scale.to_screen(960, 540)
        rx, ry = scale.to_reference(sx, sy)
        self.assertAlmostEqual(rx, 960, delta=1.0)
        self.assertAlmostEqual(ry, 540, delta=1.0)


class TestDualChamberScheduler(unittest.TestCase):
    def test_token_budget_tracking(self):
        from perception.dual_chamber_scheduler import TokenBudget

        budget = TokenBudget(budget_limit=1000)
        self.assertTrue(budget.can_invoke(500))
        budget.record(500)
        self.assertTrue(budget.can_invoke(500))
        budget.record(500)
        self.assertFalse(budget.can_invoke(1))

    def test_wake_triggers_cognitive(self):
        from perception.dual_chamber_scheduler import (
            DualChamberScheduler, DualChamberConfig, ReflexResult, CognitiveResult,
        )

        cognitive_results = [CognitiveResult(
            timestamp=time.perf_counter(),
            scene_description="test scene",
            action_recommendation="proceed",
            tokens_used=100,
            wake_reason="test",
        )]

        def reflex_fn():
            return ReflexResult(
                timestamp=time.perf_counter(),
                threats_detected=0,
                hp_ratio=1.0,
                target_direction=-1,
                screen_state="dialogue",
                frame_id=1,
            )

        def cognitive_fn(reason):
            return cognitive_results[0]

        config = DualChamberConfig(
            reflex_hz=100.0,  # fast for testing
            cognitive_min_interval=0.0,  # no cooldown for testing
            token_budget=10000,
        )
        scheduler = DualChamberScheduler(
            config=config,
            reflex_fn=reflex_fn,
            cognitive_fn=cognitive_fn,
        )
        scheduler.start()
        time.sleep(0.1)
        scheduler.stop()

        # Should have fired at least once due to dialogue wake
        self.assertGreater(scheduler.budget.wake_count, 0)

    def test_ocr_stall_detection(self):
        from perception.dual_chamber_scheduler import DualChamberScheduler

        scheduler = DualChamberScheduler()
        scheduler.update_ocr("same text")
        # First update sets the baseline
        scheduler.update_ocr("same text")
        # Second identical update — no stall yet (needs timeout)
        self.assertEqual(len(scheduler._pending_wake_reasons), 0)


class TestMinimapFlowTracker(unittest.TestCase):
    def test_phase_correlation_static(self):
        import numpy as np
        from perception.minimap_flow_tracker import MinimapFlowTracker

        tracker = MinimapFlowTracker()
        # Two identical frames — should report zero displacement
        frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        result = tracker.update(frame)
        self.assertIsNone(result)  # First frame returns None

        result = tracker.update(frame)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.magnitude, 0.0, delta=2.0)

    def test_phase_correlation_shifted(self):
        import numpy as np
        from perception.minimap_flow_tracker import MinimapFlowTracker

        tracker = MinimapFlowTracker()
        # Create a frame with distinct features
        base = np.zeros((720, 1280), dtype=np.float32)
        base[100:150, 100:200] = 255.0  # white rectangle

        frame1 = np.stack([base] * 3, axis=-1).astype(np.uint8)
        # Shift the rectangle by 10 pixels right
        base2 = np.zeros_like(base)
        base2[100:150, 110:210] = 255.0
        frame2 = np.stack([base2] * 3, axis=-1).astype(np.uint8)

        tracker.update(frame1)
        result = tracker.update(frame2)
        self.assertIsNotNone(result)
        # Should detect some horizontal displacement
        self.assertGreater(abs(result.dx), 0.5)

    def test_stuck_assessment(self):
        import numpy as np
        from perception.minimap_flow_tracker import MinimapFlowTracker

        tracker = MinimapFlowTracker(stuck_window_sec=0.3, history_size=50)
        tracker.set_walking(True)

        # Feed static frames with enough samples and time to exceed window
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        for _ in range(10):
            tracker.update(frame)
            time.sleep(0.05)

        assessment = tracker.assess_stuck()
        # Should detect stuck since all frames are identical (zero flow)
        # and walking is active for longer than stuck_window_sec
        self.assertTrue(assessment.stuck or assessment.reason == "no_recent_data")


class TestLoadingTransitionProtector(unittest.TestCase):
    def test_enter_exit_loading(self):
        import tempfile
        from perception.loading_transition_protector import (
            LoadingTransitionProtector, LoadingProtectionConfig,
        )
        from planning.mainline.quest_context_persistence import QuestContextPersistence
        from planning.mainline.active_quest_context import ActiveQuestContext

        with tempfile.TemporaryDirectory() as tmp:
            persistence = QuestContextPersistence(runs_dir=Path(tmp))
            config = LoadingProtectionConfig(context_backup_enabled=True)
            protector = LoadingTransitionProtector(persistence=persistence, config=config)

            context = ActiveQuestContext(
                quest_id="test_quest",
                quest_title="Test Quest",
                objective_text="Talk to NPC",
                objective_type="dialogue",
                version=1,
            )

            # Enter loading
            protector.notify_screen_state("loading", context)
            self.assertTrue(protector.loading_active)
            self.assertTrue(protector.is_protected())

            # Exit loading
            transition = protector.notify_screen_state("world_viewport", None)
            self.assertIsNotNone(transition)
            self.assertFalse(protector.loading_active)
            self.assertTrue(transition.completed)

    def test_extended_timeout(self):
        from perception.loading_transition_protector import (
            LoadingTransitionProtector, LoadingProtectionConfig,
        )
        from planning.mainline.active_quest_context import ActiveQuestContext

        protector = LoadingTransitionProtector(config=LoadingProtectionConfig(
            sentinel_timeout_extension_sec=30.0,
        ))

        # Normal mode
        self.assertAlmostEqual(protector.get_extended_timeout(10.0), 10.0)

        # Enter loading
        protector.notify_screen_state("loading", ActiveQuestContext(
            quest_id="q", quest_title="", objective_text="", objective_type="unknown",
        ))
        self.assertAlmostEqual(protector.get_extended_timeout(10.0), 40.0)

    def test_stats(self):
        from perception.loading_transition_protector import LoadingTransitionProtector
        from planning.mainline.active_quest_context import ActiveQuestContext

        protector = LoadingTransitionProtector()
        ctx = ActiveQuestContext(
            quest_id="q", quest_title="", objective_text="", objective_type="unknown",
        )

        protector.notify_screen_state("loading", ctx)
        protector.notify_screen_state("world_viewport", None)

        stats = protector.stats()
        self.assertEqual(stats["total_transitions"], 1)
        self.assertEqual(stats["completed"], 1)


if __name__ == "__main__":
    unittest.main()
