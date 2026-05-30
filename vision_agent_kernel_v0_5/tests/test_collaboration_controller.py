"""Tests for runtime/collaboration_controller.py: autonomy levels, permissions, handover."""
from __future__ import annotations

from runtime.collaboration_controller import (
    AutonomyLevel,
    CollaborationController,
    HandoverChecklist,
    HandoverResult,
    HandoverStatus,
    classify_action_risk,
    is_action_allowed,
    ActionRisk,
)


class TestClassifyActionRisk:
    def test_low_risk_actions(self):
        for action in ("teleport", "walk_to", "open_inventory", "basic_attack",
                       "collect_material", "claim_mail", "navigate_menu"):
            assert classify_action_risk(action) == ActionRisk.LOW, f"{action}"

    def test_high_risk_actions(self):
        for action in ("wish", "enter_boss_fight", "advance_main_quest",
                       "enhance_artifact", "shop_buy", "level_up_character"):
            assert classify_action_risk(action) == ActionRisk.HIGH, f"{action}"

    def test_forbidden_actions(self):
        for action in ("delete_character", "destroy_artifact_5star",
                       "spend_real_money", "link_account"):
            assert classify_action_risk(action) == ActionRisk.FORBIDDEN, f"{action}"

    def test_unknown_action_defaults_high(self):
        assert classify_action_risk("unknown_custom_action") == ActionRisk.HIGH


class TestIsActionAllowed:
    def test_l0_nothing_allowed(self):
        ok, reason = is_action_allowed(AutonomyLevel.MANUAL, "teleport")
        assert not ok
        assert "L0" in reason

    def test_l1_low_risk_allowed(self):
        ok, _ = is_action_allowed(AutonomyLevel.ASSISTED, "teleport")
        assert ok

    def test_l1_high_risk_blocked(self):
        ok, reason = is_action_allowed(AutonomyLevel.ASSISTED, "wish")
        assert not ok
        assert "confirmation" in reason.lower()

    def test_l2_all_allowed(self):
        for action in ("teleport", "wish", "enter_boss_fight"):
            ok, _ = is_action_allowed(AutonomyLevel.SUPERVISED, action)
            assert ok, f"{action} should be allowed at L2"

    def test_l3_all_allowed(self):
        ok, _ = is_action_allowed(AutonomyLevel.AUTONOMOUS, "advance_main_quest")
        assert ok

    def test_forbidden_at_all_levels(self):
        for level in AutonomyLevel:
            ok, _ = is_action_allowed(level, "delete_character")
            assert not ok, f"forbidden action should be blocked at {level}"


class TestHandoverChecklist:
    def test_all_pass(self):
        cl = HandoverChecklist(
            game_focused=True, game_operable=True, perception_healthy=True,
            scene_recognized=True, task_defined=True, resource_budget_set=True,
            backend_ready=True,
        )
        assert cl.is_ready
        assert len(cl.failed_items) == 0

    def test_partial_fail(self):
        cl = HandoverChecklist(game_focused=True, game_operable=True, perception_healthy=False)
        assert not cl.is_ready
        assert "perception_healthy" in cl.failed_items
        assert "task_defined" in cl.failed_items

    def test_defaults_all_false(self):
        cl = HandoverChecklist()
        assert not cl.is_ready
        assert len(cl.failed_items) == 7


class TestCollaborationController:
    def test_starts_manual(self):
        ctrl = CollaborationController()
        assert ctrl.level == AutonomyLevel.MANUAL

    def test_upgrade_requires_confirmation(self):
        ctrl = CollaborationController()
        result = ctrl.set_level(AutonomyLevel.ASSISTED, user_confirmed=False)
        assert result.status == HandoverStatus.REJECTED
        assert ctrl.level == AutonomyLevel.MANUAL

    def test_upgrade_with_confirmation(self):
        ctrl = CollaborationController()
        result = ctrl.set_level(AutonomyLevel.ASSISTED, user_confirmed=True)
        assert result.status == HandoverStatus.ACCEPTED
        assert ctrl.level == AutonomyLevel.ASSISTED

    def test_downgrade_always_allowed(self):
        ctrl = CollaborationController()
        ctrl.level = AutonomyLevel.SUPERVISED
        result = ctrl.set_level(AutonomyLevel.ASSISTED, user_confirmed=False)
        assert result.status == HandoverStatus.ACCEPTED
        assert ctrl.level == AutonomyLevel.ASSISTED

    def test_check_permission_l0(self):
        ctrl = CollaborationController()
        ok, _ = ctrl.check_permission("teleport")
        assert not ok

    def test_check_permission_l1_low(self):
        ctrl = CollaborationController()
        ctrl.level = AutonomyLevel.ASSISTED
        ok, _ = ctrl.check_permission("teleport")
        assert ok

    def test_check_permission_l1_high_blocked(self):
        ctrl = CollaborationController()
        ctrl.level = AutonomyLevel.ASSISTED
        ok, _ = ctrl.check_permission("wish")
        assert not ok

    def test_check_permission_l1_high_with_callback(self):
        confirmed = []

        def on_confirm(action: str, ctx: dict) -> bool:
            confirmed.append(action)
            return True

        ctrl = CollaborationController(
            level=AutonomyLevel.ASSISTED,
            confirmation_callback=on_confirm,
        )
        ok, reason = ctrl.check_permission("wish")
        assert ok
        assert confirmed == ["wish"]

    def test_auto_downgrade_on_consecutive_failures(self):
        ctrl = CollaborationController()
        ctrl.level = AutonomyLevel.SUPERVISED
        for _ in range(3):
            ctrl.report_failure("teleport")
        assert ctrl.level == AutonomyLevel.ASSISTED

    def test_auto_downgrade_on_perception_low(self):
        ctrl = CollaborationController()
        ctrl.level = AutonomyLevel.AUTONOMOUS
        ctrl.update_perception_confidence(0.3)
        assert ctrl.level == AutonomyLevel.ASSISTED

    def test_auto_downgrade_on_user_input(self):
        ctrl = CollaborationController()
        ctrl.level = AutonomyLevel.SUPERVISED
        ctrl.report_user_input()
        assert ctrl.level == AutonomyLevel.MANUAL

    def test_report_success_resets_failures(self):
        ctrl = CollaborationController()
        ctrl.level = AutonomyLevel.SUPERVISED
        ctrl.report_failure("teleport")
        ctrl.report_failure("teleport")
        ctrl.report_success("teleport")
        ctrl.report_failure("teleport")
        ctrl.report_failure("teleport")
        # Only 2 consecutive failures, not 3
        assert ctrl.level == AutonomyLevel.SUPERVISED

    def test_attempt_handover_with_checklist(self):
        ctrl = CollaborationController()
        good_checklist = HandoverChecklist(
            game_focused=True, game_operable=True, perception_healthy=True,
            scene_recognized=True, task_defined=True, resource_budget_set=True,
            backend_ready=True,
        )
        result = ctrl.attempt_handover(AutonomyLevel.AUTONOMOUS, good_checklist)
        assert result.status == HandoverStatus.ACCEPTED
        assert ctrl.level == AutonomyLevel.AUTONOMOUS

    def test_attempt_handover_fails_checklist(self):
        ctrl = CollaborationController()
        bad_checklist = HandoverChecklist(game_focused=False)
        result = ctrl.attempt_handover(AutonomyLevel.AUTONOMOUS, bad_checklist)
        assert result.status == HandoverStatus.REJECTED
        assert ctrl.level == AutonomyLevel.MANUAL

    def test_safety_limit_primogem_budget(self):
        ctrl = CollaborationController(primogem_budget=100, primogem_spent=100)
        ok, reason = ctrl.check_safety_limit()
        assert not ok
        assert "primogem" in reason.lower()

    def test_safety_limit_ok(self):
        ctrl = CollaborationController(primogem_budget=1000, primogem_spent=50)
        ok, _ = ctrl.check_safety_limit()
        assert ok

    def test_handover_history(self):
        ctrl = CollaborationController()
        ctrl.set_level(AutonomyLevel.ASSISTED, user_confirmed=True)
        ctrl.set_level(AutonomyLevel.SUPERVISED, user_confirmed=True)
        assert len(ctrl.handover_history) == 2

    def test_status_summary(self):
        ctrl = CollaborationController(level=AutonomyLevel.ASSISTED, primogem_budget=500)
        summary = ctrl.status_summary()
        assert summary["level"] == "ASSISTED"
        assert summary["primogem_budget"] == 500

    def test_window_defocus_downgrades_l3_to_l2(self):
        ctrl = CollaborationController()
        ctrl.level = AutonomyLevel.AUTONOMOUS
        ctrl.report_window_defocus_restored()
        assert ctrl.level == AutonomyLevel.SUPERVISED

    def test_puzzle_detected_downgrades_l2_to_l1(self):
        ctrl = CollaborationController()
        ctrl.level = AutonomyLevel.SUPERVISED
        ctrl.report_puzzle_detected()
        assert ctrl.level == AutonomyLevel.ASSISTED
