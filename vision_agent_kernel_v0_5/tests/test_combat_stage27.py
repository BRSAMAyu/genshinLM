from __future__ import annotations

from pathlib import Path

from app_service.agent_controller import AgentController
from combat.combat_context import CombatContext
from combat.danger_detector import DangerDetector
from combat.playbook_runtime import CombatPlaybookRuntime
from combat.reflex_evasion import ReflexEvasion


def test_hybrid_danger_components_and_score() -> None:
    danger = DangerDetector().evaluate(
        {
            "generic_warning_area": 1.0,
            "projectile_approaching": 1.0,
            "target_bbox_fast_expand": 0.8,
            "enemy_facing_player": 0.5,
            "hp_drop_signal": 0.4,
            "scripted_testbed_danger": 1.0,
        },
        context_priority=0.2,
    )

    assert danger.level == "HIGH"
    assert danger.score >= 0.8
    assert "projectile_threat_score" in danger.components
    assert "distance_closing_score" in danger.components
    assert danger.dominant_signal in danger.components


def test_reflex_evasion_interrupt_payload_and_cooldown() -> None:
    reflex = ReflexEvasion()
    signals = {"generic_warning_area": 1.0, "projectile_approaching": 1.0, "scripted_testbed_danger": 1.0}
    interrupt, dodge = reflex.evaluate(signals, context_priority=0.1, checkpoint="target_visible_checkpoint")
    assert interrupt is not None
    assert interrupt.code == "DODGE_REFLEX"
    assert interrupt.payload["checkpoint"] == "target_visible_checkpoint"
    assert dodge is not None
    assert dodge["ok"] is True

    interrupt2, dodge2 = reflex.evaluate(signals, context_priority=0.1, checkpoint="target_visible_checkpoint")
    assert interrupt2 is not None
    assert dodge2 is not None
    assert dodge2["ok"] is False
    assert dodge2["reason"] == "cooldown"


def test_playbook_runtime_behavior_tree_tick(tmp_path: Path) -> None:
    controller = AgentController(root=tmp_path)
    playbook = controller.create_combat_playbook("safe sandbox combat", provider="mock")["playbook"]
    runtime = CombatPlaybookRuntime()

    validation = runtime.validate(playbook)
    high = runtime.tick(playbook, CombatContext(target_visible=True, hp_ratio=0.8), danger_score=0.92, checkpoint="target_visible_checkpoint")
    low_hp = runtime.tick(playbook, CombatContext(target_visible=True, hp_ratio=0.2), danger_score=0.2)
    safe = runtime.tick(playbook, CombatContext(target_visible=True, hp_ratio=0.8), danger_score=0.2)

    assert validation["ok"] is True
    assert high["node"] == "dodge_if_danger"
    assert high["interrupted"] is True
    assert low_hp["node"] == "heal_if_low_hp"
    assert safe["node"] == "burst_if_safe"


def test_combat_api_response_exposes_explainable_fields(tmp_path: Path) -> None:
    controller = AgentController(root=tmp_path)
    response = controller.evaluate_danger(
        {"generic_warning_area": 1.0, "projectile_approaching": 1.0, "scripted_testbed_danger": 1.0},
        context_priority=0.1,
    )

    assert response["level"] == "HIGH"
    assert response["interrupt"]["code"] == "DODGE_REFLEX"
    assert response["components"]["generic_warning_score"] > 0
    assert response["dodge_policy"]["cooldown_ms"] >= 0
    assert response["companion_message"]
