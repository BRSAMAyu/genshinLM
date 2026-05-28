"""Tests for QuestStateTrackerV2 and ActiveQuestContext."""
from __future__ import annotations

import pytest

from planning.mainline.active_quest_context import (
    ActiveQuestContext,
    DialogueTurn,
    MapMarker,
    QuestBlocker,
    classify_objective,
    quest_id_from_text,
)
from planning.mainline.quest_state_tracker_v2 import QuestStateTrackerV2
from planning.screen_state_claim import ScreenStateClaim, UIElementClaim


def _claim(
    screen_state: str = "overworld",
    ocr_texts: tuple[str, ...] = (),
    ui_elements: tuple[UIElementClaim, ...] = (),
    scene_desc: str = "",
) -> ScreenStateClaim:
    return ScreenStateClaim(
        game_id="test",
        screen_state=screen_state,
        confidence=0.8,
        source="vlm",
        ui_elements=ui_elements,
        scene_description=scene_desc,
        raw_ocr_texts=ocr_texts,
    )


class TestObjectiveClassification:
    def test_dialog_objective(self) -> None:
        assert classify_objective("与凯瑟琳交谈") == "dialog"
        assert classify_objective("Talk to Katheryne") == "dialog"

    def test_combat_objective(self) -> None:
        assert classify_objective("击败史莱姆") == "combat"
        assert classify_objective("Defeat the enemies") == "combat"

    def test_collect_objective(self) -> None:
        assert classify_objective("收集清心x3") == "collect"
        assert classify_objective("Collect 3 Qingxin") == "collect"

    def test_navigation_objective(self) -> None:
        assert classify_objective("前往冒险家协会") == "go_to_marker"
        assert classify_objective("Reach the destination") == "go_to_marker"

    def test_domain_objective(self) -> None:
        assert classify_objective("完成秘境挑战") == "domain"

    def test_unknown_objective(self) -> None:
        assert classify_objective("Something random") == "unknown"


class TestActiveQuestContext:
    def test_initial_context(self) -> None:
        ctx = ActiveQuestContext(
            quest_id="q1",
            quest_title="Test Quest",
            objective_text="Talk to NPC",
            objective_type="dialog",
        )
        assert ctx.version == 1
        assert not ctx.is_blocked
        assert ctx.has_objective

    def test_evolve_increments_version(self) -> None:
        ctx = ActiveQuestContext(
            quest_id="q1", quest_title="T", objective_text="O", objective_type="dialog",
        )
        v2 = ctx.evolve(objective_text="New objective")
        assert v2.version == 2
        assert v2.objective_text == "New objective"
        assert ctx.version == 1  # Original immutable

    def test_blocked_context(self) -> None:
        ctx = ActiveQuestContext(
            quest_id="q1", quest_title="T", objective_text="O", objective_type="dialog",
            known_blockers=(QuestBlocker("b1", "prerequisite", "Need AR 25"),),
        )
        assert ctx.is_blocked


class TestQuestStateTrackerV2:
    def test_extract_quest_from_ocr(self) -> None:
        tracker = QuestStateTrackerV2()
        claim = _claim(ocr_texts=("任务：与派蒙交谈",))
        ctx, delta = tracker.update(claim)
        assert ctx.objective_text == "与派蒙交谈"
        assert ctx.objective_type == "dialog"
        assert ctx.confidence > 0.5

    def test_extract_quest_from_vlm(self) -> None:
        tracker = QuestStateTrackerV2()
        claim = _claim(scene_desc="The objective is to talk to the NPC")
        ctx, delta = tracker.update(claim)
        assert "talk to the npc" in ctx.objective_text.lower()

    def test_objective_change_detected(self) -> None:
        tracker = QuestStateTrackerV2()
        claim1 = _claim(ocr_texts=("任务：与派蒙交谈",))
        ctx1, _ = tracker.update(claim1)

        claim2 = _claim(ocr_texts=("任务：击败史莱姆",))
        ctx2, delta = tracker.update(claim2)
        assert delta is not None
        assert delta.objective_changed
        assert ctx2.objective_type == "combat"

    def test_screen_change_without_objective_change(self) -> None:
        tracker = QuestStateTrackerV2()
        claim1 = _claim(screen_state="overworld", ocr_texts=("任务：与派蒙交谈",))
        ctx1, _ = tracker.update(claim1)

        # Screen changed but objective is same
        claim2 = _claim(screen_state="dialog", ocr_texts=("任务：与派蒙交谈",))
        ctx2, delta = tracker.update(claim2)
        assert ctx2.screen_state == "dialog"
        if delta is not None:
            assert not delta.objective_changed

    def test_confidence_decay_when_ocr_missing(self) -> None:
        tracker = QuestStateTrackerV2()
        claim1 = _claim(ocr_texts=("任务：与派蒙交谈",))
        ctx1, _ = tracker.update(claim1)
        assert ctx1.confidence > 0.5

        # No quest text in this frame
        claim2 = _claim(ocr_texts=("Some random text",))
        ctx2, _ = tracker.update(claim2)
        assert ctx2.confidence < ctx1.confidence

    def test_confidence_recovery(self) -> None:
        tracker = QuestStateTrackerV2()
        # First: establish quest
        claim1 = _claim(ocr_texts=("任务：与派蒙交谈",))
        ctx1, _ = tracker.update(claim1)
        # Second: lose OCR
        claim2 = _claim(ocr_texts=("random text",))
        ctx2, _ = tracker.update(claim2)
        assert ctx2.confidence < ctx1.confidence
        # Third: recover OCR
        claim3 = _claim(ocr_texts=("任务：与派蒙交谈",))
        ctx3, _ = tracker.update(claim3)
        assert ctx3.confidence > ctx2.confidence

    def test_blocker_detection(self) -> None:
        tracker = QuestStateTrackerV2()
        claim = _claim(ocr_texts=("任务：完成挑战", "需要冒险等阶25解锁 — 当前卡住"))
        ctx, delta = tracker.update(claim)
        assert ctx.is_blocked
        if delta is not None:
            assert delta.blocker_added

    def test_dialogue_turn_extraction(self) -> None:
        tracker = QuestStateTrackerV2()
        elements = (
            UIElementClaim("d1", "dialogue_text", "派蒙：我们去看看吧", (0.1, 0.2, 0.5, 0.3), 0.9, "ocr"),
            UIElementClaim("d2", "dialogue_text", "旅行者：好的", (0.1, 0.4, 0.5, 0.5), 0.9, "ocr"),
        )
        claim = _claim(ui_elements=elements)
        ctx, delta = tracker.update(claim)
        assert len(ctx.last_dialogue_turns) >= 1

    def test_map_marker_integration(self) -> None:
        tracker = QuestStateTrackerV2()
        marker = MapMarker("m1", "冒险家协会", "quest", is_tracked=True)
        claim = _claim(ocr_texts=("任务：前往冒险家协会",))
        ctx, delta = tracker.update(claim, map_marker=marker)
        assert ctx.map_marker is not None
        assert ctx.map_marker.is_tracked

    def test_deterministic_quest_id(self) -> None:
        tracker = QuestStateTrackerV2()
        claim = _claim(ocr_texts=("任务：与派蒙交谈",))
        ctx1, _ = tracker.update(claim)
        tracker2 = QuestStateTrackerV2()
        ctx2, _ = tracker2.update(claim)
        assert ctx1.quest_id == ctx2.quest_id

    def test_preserves_objective_on_empty_ocr(self) -> None:
        tracker = QuestStateTrackerV2()
        claim1 = _claim(ocr_texts=("任务：与派蒙交谈",))
        ctx1, _ = tracker.update(claim1)

        # Empty OCR — should preserve previous objective
        claim2 = _claim(ocr_texts=())
        ctx2, _ = tracker.update(claim2)
        assert ctx2.objective_text == ctx1.objective_text

    def test_claim_graph_summary_fallback(self) -> None:
        tracker = QuestStateTrackerV2()
        claim = _claim(ocr_texts=(), scene_desc="")
        ctx, _ = tracker.update(
            claim,
            claim_graph_summary={
                "objective_text": "前往冒险家协会",
                "evidence_refs": ["claim_quest_text"],
            },
        )
        assert ctx.objective_text == "前往冒险家协会"
        assert ctx.objective_type == "go_to_marker"
        assert "claim_quest_text" in ctx.evidence_refs

    def test_blocker_detection_does_not_flag_lock_on_enemy(self) -> None:
        tracker = QuestStateTrackerV2()
        claim = _claim(ocr_texts=("任务：击败敌人", "锁定敌人并攻击"))
        ctx, _ = tracker.update(claim)
        assert not ctx.is_blocked
