from __future__ import annotations

import pytest

from planning.applicability_gate import SkillApplicabilityGate
from planning.screen_state_claim import ScreenStateClaim, UIElementClaim
from planning.skill_capability_catalog import SkillCatalogEntry, SkillCapabilityCatalog
from runtime.claim_runtime import ReliabilityStore


class TestSkillApplicabilityGate:
    @pytest.fixture
    def store(self) -> ReliabilityStore:
        return ReliabilityStore(min_samples=2)

    @pytest.fixture
    def catalog(self) -> SkillCapabilityCatalog:
        entries = [
            SkillCatalogEntry(
                skill_id="claim_reward_fast",
                capsule_id="hsr",
                source="skill_store",
                kind="ui",
                capabilities=["claim_reward"],
                verifiers=["领取奖励", "确定"],
                risk_level="medium",
            ),
            SkillCatalogEntry(
                skill_id="buy_item_critical",
                capsule_id="hsr",
                source="skill_store",
                kind="ui",
                capabilities=["buy_item"],
                risk_level="critical",
            ),
            SkillCatalogEntry(
                skill_id="open_menu_low",
                capsule_id="hsr",
                source="skill_store",
                kind="ui",
                capabilities=["open_menu"],
                risk_level="low",
            ),
        ]
        return SkillCapabilityCatalog(entries)

    def test_evaluate_skills_empty_matched(self, catalog, store):
        gate = SkillApplicabilityGate(catalog, store)
        state = ScreenStateClaim(game_id="hsr", screen_state="menu", confidence=0.9, source="vlm")
        scores = gate.evaluate_skills("unknown_goal", state)
        assert len(scores) == 0

    def test_evaluate_skills_anchor_coverage(self, catalog, store):
        gate = SkillApplicabilityGate(catalog, store)
        # Match "claim_reward", verifiers are "领取奖励", "确定"
        # Screen has "领取奖励" but not "确定" -> anchor coverage is 0.5
        state = ScreenStateClaim(
            game_id="hsr",
            screen_state="menu",
            confidence=0.9,
            source="vlm",
            ui_elements=(
                UIElementClaim("el1", "button", "领取奖励", (0.1, 0.2, 0.3, 0.1), 0.95, "ocr"),
            ),
        )
        scores = gate.evaluate_skills("claim_reward", state)
        assert len(scores) == 1
        score_record = scores[0]
        assert score_record.skill_entry.skill_id == "claim_reward_fast"
        # Anchor coverage is 0.5. reliability is 0.0 (Wilson bound for 0/0 is 0.0)
        # score = goal .25 + precondition .20 + reliability 0 + anchor .125 + verifier .05 = .625
        assert abs(score_record.score - 0.625) < 0.01

    def test_evaluate_skills_reliability_safeguard(self, catalog, store):
        # We record some outcomes for open_menu_low to increase/decrease its reliability
        context = {
            "capsule_id": "hsr",
            "screen_state": "menu",
            "mission_phase": "open_menu",
            "target_class": "open_menu",
        }
        # Low reliability: 2 failures
        store.record("open_menu_low", context, "mismatch")
        store.record("open_menu_low", context, "mismatch")

        gate = SkillApplicabilityGate(catalog, store)
        state = ScreenStateClaim(game_id="hsr", screen_state="menu", confidence=0.9, source="vlm")
        scores = gate.evaluate_skills("open_menu", state, risk_policy="medium")
        assert len(scores) == 1
        score_record = scores[0]
        # Since reliability is extremely low, it must not be allowed
        assert not score_record.allowed
        assert "reliability" in score_record.reason

    def test_evaluate_skills_critical_risk_blocked(self, catalog, store):
        gate = SkillApplicabilityGate(catalog, store)
        state = ScreenStateClaim(game_id="hsr", screen_state="menu", confidence=0.9, source="vlm")
        scores = gate.evaluate_skills("buy_item", state)
        assert len(scores) == 1
        score_record = scores[0]
        # Critical risk is always disallowed
        assert not score_record.allowed
        assert "critical_risk" in score_record.reason

    def test_evaluate_skills_high_reliability_allowed(self, catalog, store):
        context = {
            "capsule_id": "hsr",
            "screen_state": "menu",
            "mission_phase": "open_menu",
            "target_class": "open_menu",
        }
        # High reliability: 30 successes
        for _ in range(30):
            store.record("open_menu_low", context, "matched")

        gate = SkillApplicabilityGate(catalog, store)
        state = ScreenStateClaim(game_id="hsr", screen_state="menu", confidence=0.9, source="vlm")
        scores = gate.evaluate_skills("open_menu", state)
        assert len(scores) == 1
        score_record = scores[0]
        assert score_record.allowed
        assert score_record.reason == "reliability_above_threshold"
