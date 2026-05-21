from __future__ import annotations

import time

import pytest

from core.types import SkillResult
from execution.claim_adapter import ClaimProducingAdapter
from execution.verifier_base import SignalCorroboration, VerifierResult
from runtime.claim_runtime import (
    AdjudicationEvent,
    AuditSnapshot,
    ClaimGraph,
    DelayedAuditEngine,
    ObservationClaim,
    StateDeltaClaim,
)
from runtime.claim_schema import (
    FailureModeDecl,
    InputClaimDecl,
    ProducedClaimDecl,
    SkillClaimDeclaration,
    all_declarations,
    clear_registry,
    get_skill_declaration,
    register_skill_declaration,
)


class TestObservationClaim:
    def test_create_support(self):
        obs = ObservationClaim(
            observation_id="obs_1",
            claim_id="claim_1",
            source_family="toast",
            polarity="support",
            signal_quality=0.85,
        )
        assert obs.observation_id == "obs_1"
        assert obs.polarity == "support"
        assert obs.signal_quality == 0.85

    def test_create_refute(self):
        obs = ObservationClaim(
            observation_id="obs_2",
            claim_id="claim_1",
            source_family="inventory_check",
            polarity="refute",
            signal_quality=0.9,
        )
        assert obs.polarity == "refute"

    def test_neutral_polarity(self):
        obs = ObservationClaim(
            observation_id="obs_3",
            claim_id="claim_1",
            source_family="screen_state",
            polarity="neutral",
            signal_quality=0.5,
        )
        assert obs.polarity == "neutral"

    def test_frozen(self):
        obs = ObservationClaim(
            observation_id="obs_1", claim_id="c1",
            source_family="t", polarity="support", signal_quality=0.5,
        )
        with pytest.raises(AttributeError):
            obs.polarity = "refute"  # type: ignore[misc]


class TestAdjudicationEvent:
    def test_create(self):
        event = AdjudicationEvent(
            adjudication_id="adj_1",
            claim_id="claim_1",
            old_status="tentative",
            new_status="verified",
            reason="evidence_sufficient",
            confidence=0.85,
        )
        assert event.new_status == "verified"
        assert event.old_status == "tentative"
        assert event.confidence == 0.85

    def test_demotion_event(self):
        event = AdjudicationEvent(
            adjudication_id="adj_2",
            claim_id="claim_1",
            old_status="verified",
            new_status="demoted",
            reason="audit_mismatch",
        )
        assert event.new_status == "demoted"


class TestClaimGraphThreeNodeTypes:
    def test_add_observation_to_claim(self):
        graph = ClaimGraph()
        claim = _make_claim("c1")
        graph.add_claim(claim)

        obs = ObservationClaim(
            observation_id="obs_1", claim_id="c1",
            source_family="toast", polarity="support", signal_quality=0.9,
        )
        graph.add_observation(obs)

        observations = graph.get_observations_for("c1")
        assert len(observations) == 1
        assert observations[0].source_family == "toast"

    def test_multiple_observations(self):
        graph = ClaimGraph()
        claim = _make_claim("c1")
        graph.add_claim(claim)

        for i in range(3):
            obs = ObservationClaim(
                observation_id=f"obs_{i}", claim_id="c1",
                source_family=f"family_{i}", polarity="support", signal_quality=0.8,
            )
            graph.add_observation(obs)

        observations = graph.get_observations_for("c1")
        assert len(observations) == 3

    def test_add_adjudication(self):
        graph = ClaimGraph()
        claim = _make_claim("c1")
        graph.add_claim(claim)

        event = AdjudicationEvent(
            adjudication_id="adj_1", claim_id="c1",
            old_status="asserted", new_status="verified", reason="ok",
        )
        graph.add_adjudication(event)

        events = graph.get_adjudications_for("c1")
        assert len(events) == 1
        assert events[0].new_status == "verified"

    def test_snapshot(self):
        graph = ClaimGraph()
        graph.add_claim(_make_claim("c1"))
        graph.add_claim(_make_claim("c2"))
        graph.add_observation(ObservationClaim(
            observation_id="obs_1", claim_id="c1",
            source_family="t", polarity="support", signal_quality=0.8,
        ))
        snap = graph.snapshot()
        assert snap["claim_count"] == 2
        assert snap["observation_count"] == 1

    def test_no_observations_for_unknown_claim(self):
        graph = ClaimGraph()
        assert graph.get_observations_for("nonexistent") == []

    def test_claim_and_observation_counts(self):
        graph = ClaimGraph()
        assert graph.claim_count == 0
        assert graph.observation_count == 0
        graph.add_claim(_make_claim("c1"))
        assert graph.claim_count == 1
        graph.add_observation(ObservationClaim(
            observation_id="obs_1", claim_id="c1",
            source_family="t", polarity="support", signal_quality=0.8,
        ))
        assert graph.observation_count == 1

    def test_extended_claim_statuses(self):
        graph = ClaimGraph()
        claim = StateDeltaClaim(
            claim_id="c1", mission_id="m1", node_id="n1", skill_id="s1",
            claim_type="test", claimed_delta={}, status="locked",
        )
        graph.add_claim(claim)
        assert graph.get("c1").status == "locked"


class TestClaimProducingAdapter:
    def test_adapt_support(self):
        adapter = ClaimProducingAdapter()
        result = VerifierResult(ok=True, verifier_id="observation_graph_ui", confidence=0.9, reason="ok")
        claim = _make_claim("c1")
        obs = adapter.adapt(result=result, claim=claim)
        assert obs.polarity == "support"
        assert obs.signal_quality == 0.9
        assert obs.source_family == "ui_graph"

    def test_adapt_refute(self):
        adapter = ClaimProducingAdapter()
        result = VerifierResult(ok=False, verifier_id="navigation_progress", confidence=0.3, reason="fail")
        claim = _make_claim("c1")
        obs = adapter.adapt(result=result, claim=claim)
        assert obs.polarity == "refute"
        assert obs.source_family == "navigation"

    def test_adapt_with_alternative_signals(self):
        adapter = ClaimProducingAdapter()
        alt = SignalCorroboration("s1", "ocr", True, 0.8, "alt supports ok")
        result = VerifierResult(
            ok=False, verifier_id="observation_graph_ui", confidence=0.3,
            reason="fail", alternative_signals=[alt],
        )
        claim = _make_claim("c1")
        obs = adapter.adapt(result=result, claim=claim)
        assert obs.polarity == "support"

    def test_adapt_legacy_unknown_verifier(self):
        adapter = ClaimProducingAdapter()
        result = VerifierResult(ok=True, verifier_id="custom_verifier_xyz", confidence=0.9, reason="ok")
        claim = _make_claim("c1")
        obs = adapter.adapt(result=result, claim=claim)
        assert obs.source_family == "legacy_unknown"
        assert obs.signal_quality == 0.45  # 0.9 * 0.5 cap

    def test_adapt_with_source_family_override(self):
        adapter = ClaimProducingAdapter(source_family_override="custom_family")
        result = VerifierResult(ok=True, verifier_id="observation_graph_ui", confidence=0.9, reason="ok")
        claim = _make_claim("c1")
        obs = adapter.adapt(result=result, claim=claim)
        assert obs.source_family == "custom_family"
        assert obs.signal_quality == 0.9  # no cap for explicit override

    def test_adapt_to_skill_result_update(self):
        adapter = ClaimProducingAdapter()
        claim = _make_claim("c1")
        result = VerifierResult(ok=True, verifier_id="test", confidence=0.9, reason="ok")
        update = adapter.adapt_to_skill_result_update(result=result, claim=claim)
        assert update["claim_id"] == "c1"
        assert update["verifier_ok"] is True


class TestSkillClaimDeclaration:
    def setup_method(self):
        clear_registry()

    def test_create_full_declaration(self):
        decl = SkillClaimDeclaration(
            skill_id="genshin_collect_qingxin",
            capsule_id="genshin",
            risk_level="low",
            capabilities_provided=["collect_material"],
            input_claims=[
                InputClaimDecl(claim_type="navigation_arrival", target="qingxin_node", required_status="verified"),
            ],
            produced_claims=[
                ProducedClaimDecl(
                    claim_type="inventory_delta", target="qingxin", delta=1,
                    claim_role="terminal", stabilization_window_ms=900,
                    verifier_recipe="inventory_delta.default",
                ),
            ],
            failure_modes=[
                FailureModeDecl(code="CLAIM_UNCERTAIN", policy="resample_then_delayed_audit"),
            ],
        )
        assert decl.skill_id == "genshin_collect_qingxin"
        assert decl.produced_claim_types() == ["inventory_delta"]
        assert decl.terminal_claims()[0].target == "qingxin"
        assert decl.dependency_claim_types() == ["navigation_arrival"]

    def test_registry(self):
        decl = SkillClaimDeclaration(skill_id="test_skill", risk_level="low")
        register_skill_declaration(decl)
        assert get_skill_declaration("test_skill") is decl
        assert "test_skill" in all_declarations()

    def test_registry_missing(self):
        assert get_skill_declaration("nonexistent") is None

    def test_registry_clear(self):
        register_skill_declaration(SkillClaimDeclaration(skill_id="a", risk_level="low"))
        register_skill_declaration(SkillClaimDeclaration(skill_id="b", risk_level="medium"))
        assert len(all_declarations()) == 2
        clear_registry()
        assert len(all_declarations()) == 0


class TestSkillResultExtension:
    def test_claim_status_default(self):
        result = SkillResult(
            skill_name="test", status="success", failure_code=None,
            started_at=0.0, finished_at=1.0,
        )
        assert result.claim_id == ""
        assert result.claim_status == ""

    def test_claim_status_set(self):
        result = SkillResult(
            skill_name="test", status="success", failure_code=None,
            started_at=0.0, finished_at=1.0,
            claim_id="c1", claim_status="verified",
        )
        assert result.claim_id == "c1"
        assert result.claim_status == "verified"


class TestAdapterPipelineIntegration:
    def test_full_adapter_pipeline(self):
        graph = ClaimGraph()
        claim = _make_claim("c1")
        graph.add_claim(claim)

        adapter = ClaimProducingAdapter()
        result = VerifierResult(
            ok=True, verifier_id="observation_graph_ui",
            confidence=0.9, reason="toast detected",
            alternative_signals=[
                SignalCorroboration("s1", "ocr", True, 0.85, "ocr matched +1"),
            ],
        )
        obs = adapter.adapt(result=result, claim=claim)
        graph.add_observation(obs)

        adj = AdjudicationEvent(
            adjudication_id="adj_1", claim_id="c1",
            old_status="asserted", new_status="verified", reason="evidence_sufficient",
            confidence=0.9,
        )
        graph.add_adjudication(adj)

        assert graph.get("c1").status == "asserted"  # ClaimGraph doesn't auto-update from adjudication
        observations = graph.get_observations_for("c1")
        assert len(observations) == 1
        assert observations[0].polarity == "support"
        events = graph.get_adjudications_for("c1")
        assert len(events) == 1
        assert events[0].new_status == "verified"


def _make_claim(claim_id: str) -> StateDeltaClaim:
    return StateDeltaClaim(
        claim_id=claim_id,
        mission_id="m1",
        node_id="n1",
        skill_id="s1",
        claim_type="test",
        claimed_delta={"item": "test", "delta": 1},
    )
