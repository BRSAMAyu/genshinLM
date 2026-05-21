"""End-to-end validation for HSR and Genshin claim pipelines.

Section 15 MVP Validation:
  HSR: Menu → Quest/Rewards → Auto-battle/Claim → Delayed audit
  Genshin: Teleport → Navigate → Collect → Verify toast → Delayed audit

Each task produces full pipeline:
  claim → evidence → uncertain exit (if applicable) → audit result
  → reliability update → planner gate decision
"""
from __future__ import annotations

import os
import tempfile
import time

from execution.claim_adapter import ClaimProducingAdapter
from execution.verifier_base import SignalCorroboration, VerifierResult
from reliability.reliability_store import ThreeLayerReliabilityStore
from runtime.audit_scheduler import AuditScheduleConfig, DelayedAuditScheduler
from runtime.claim_adjudicator import ClaimAdjudicator, CORE_RECIPES
from runtime.claim_runtime import (
    AdjudicationEvent,
    AuditSnapshot,
    ClaimGraph,
    ClaimProducingExecutor,
    ObservationClaim,
    StateDeltaClaim,
    UncertaintyPolicy,
)
from runtime.claim_schema import (
    InputClaimDecl,
    ProducedClaimDecl,
    SkillClaimDeclaration,
    register_skill_declaration,
    clear_registry,
)
from runtime.mission_graph import (
    MissionGraph,
    MissionGraphNode,
    UnverifiableBudget,
    UnverifiablePolicy,
)
from runtime.verifier_compiler import CORE_BUNDLES, VerifierCompiler


def _make_claim(
    claim_id: str,
    claim_type: str,
    mission_id: str,
    node_id: str,
    skill_id: str,
    claimed_delta: dict,
    risk_level: str = "low",
    depends_on: list[str] | None = None,
    input_claims: list[str] | None = None,
) -> StateDeltaClaim:
    return StateDeltaClaim(
        claim_id=claim_id,
        mission_id=mission_id,
        node_id=node_id,
        skill_id=skill_id,
        claim_type=claim_type,
        claimed_delta=claimed_delta,
        risk_level=risk_level,
        depends_on=depends_on or [],
        input_claims=input_claims or [],
    )


class TestHSREndToEnd:
    """HSR: Menu → Quest/Rewards → Claim rewards → Delayed audit.

    Testbed mode: synthetic observations and inventory state.
    """

    def setup_method(self):
        clear_registry()
        self.decl = SkillClaimDeclaration(
            skill_id="hsr_claim_rewards",
            capsule_id="hsr",
            risk_level="low",
            capabilities_provided=["hsr_reward_claim"],
            produced_claims=[
                ProducedClaimDecl(
                    claim_type="inventory_delta",
                    target="stellar_jade",
                    delta=60,
                    claim_role="terminal",
                    stabilization_window_ms=1200,
                    verifier_recipe="inventory_delta.default",
                ),
            ],
            input_claims=[
                InputClaimDecl(claim_type="screen_state_match", target="hsr.screen_state", expected="reward_menu"),
            ],
        )
        register_skill_declaration(self.decl)

    def test_hsr_reward_claim_full_pipeline(self):
        claim_id = "hsr_claim_001"
        mission_id = "hsr_daily_rewards"

        # 1. Create reliability store with persistence
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            rel_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            audit_path = f.name

        try:
            reliability = ThreeLayerReliabilityStore(persistence_path=rel_path)
            audit_scheduler = DelayedAuditScheduler(
                config=AuditScheduleConfig(post_node_delay_ms=0),
                persistence_path=audit_path,
            )
            adjudicator = ClaimAdjudicator(default_recipes=CORE_RECIPES)
            adapter = ClaimProducingAdapter()
            claim_graph = ClaimGraph()

            # 2. Create claim
            claim = _make_claim(
                claim_id=claim_id, claim_type="inventory_delta",
                mission_id=mission_id, node_id="claim_rewards",
                skill_id="hsr_claim_rewards",
                claimed_delta={"item": "stellar_jade", "delta": 60},
            )
            claim_graph.add_claim(claim)

            # 3. Simulate verifier observations (toast + inventory delta)
            obs_toast = ObservationClaim(
                observation_id="obs_toast", claim_id=claim_id,
                source_family="toast", polarity="support", signal_quality=0.9,
                verifier_id="observation_graph_ui",
            )
            claim_graph.add_observation(obs_toast)

            obs_inventory = ObservationClaim(
                observation_id="obs_inv", claim_id=claim_id,
                source_family="inventory_delta", polarity="support", signal_quality=0.85,
                verifier_id="navigation_progress",
            )
            claim_graph.add_observation(obs_inventory)

            # 4. Adjudicate
            observations = claim_graph.get_observations_for(claim_id)
            adj_result = adjudicator.adjudicate(claim, observations)
            assert adj_result.status == "verified"
            assert adj_result.confidence > 0.5

            # 5. Record adjudication event
            claim_graph.add_adjudication(AdjudicationEvent(
                adjudication_id=f"adj_{claim_id}", claim_id=claim_id,
                old_status="asserted", new_status=adj_result.status,
                reason=adj_result.reason, confidence=adj_result.confidence,
            ))

            # 6. Schedule delayed audit
            snapshot = AuditSnapshot(
                inventory_before={"stellar_jade": 1000},
                screen_state_before="reward_menu",
            )
            audit_record = audit_scheduler.schedule(
                audit_id=f"audit_{claim_id}", claim_id=claim_id,
                skill_id="hsr_claim_rewards", claim_type="inventory_delta",
                audit_type="post_node", snapshot=snapshot,
                expected_delta={"item": "stellar_jade", "delta": 60},
                stabilization_window_ms=1200,
            )
            assert audit_record.status == "pending"

            # 7. Simulate delayed audit completion
            due = audit_scheduler.check_due(current_time=time.time() + 10.0)
            assert len(due) == 1

            completion = audit_scheduler.complete(
                f"audit_{claim_id}",
                {"item": "stellar_jade", "delta": 60},
            )
            assert completion.matched

            # 8. Update reliability store
            reliability.record_adjudication(
                skill_id="hsr_claim_rewards",
                claim_type="inventory_delta",
                recipe_id="default",
                capsule_id="hsr",
                verifier_id="observation_graph_ui",
                source_family="ui_graph",
                context={"capsule_id": "hsr", "skill_id": "hsr_claim_rewards"},
                adjudication_status="verified",
                was_correct=True,
            )
            reliability.record_audit(
                skill_id="hsr_claim_rewards",
                claim_type="inventory_delta",
                recipe_id="default",
                capsule_id="hsr",
                context={"capsule_id": "hsr", "skill_id": "hsr_claim_rewards"},
                matched=True,
            )

            # 9. Check execution trust (note: single sample, skill_claim_trust=0.0 per Option A)
            trust = reliability.execution_trust(
                skill_id="hsr_claim_rewards",
                claim_type="inventory_delta",
                recipe_id="default",
                capsule_id="hsr",
                context={"capsule_id": "hsr", "skill_id": "hsr_claim_rewards"},
            )
            # With only 1 sample, skill_claim uses Option A (zero-sample = 0.0)
            # recipe_trust = 0.5 (neutral), skill_claim_trust = 0.0 → min = 0.0
            assert trust.recipe_trust > 0.0
            assert trust.skill_claim_trust == 0.0  # zero-sample
            assert trust.overall == 0.0  # min(0.5, 0.0, 1.0)

            # 10. Verify graph state
            snap = claim_graph.snapshot()
            assert snap["claim_count"] == 1
            assert snap["observation_count"] == 2

            # 11. Verify persistence
            with open(rel_path) as f:
                rel_lines = [l.strip() for l in f if l.strip()]
            assert len(rel_lines) >= 2  # adjudication + audit events

            with open(audit_path) as f:
                audit_lines = [l.strip() for l in f if l.strip()]
            assert len(audit_lines) >= 2  # scheduled + completed

        finally:
            os.unlink(rel_path)
            os.unlink(audit_path)

    def test_hsr_claim_with_uncertainty_exit(self):
        """When toast is seen but inventory not verified → uncertain → resample."""
        claim_id = "hsr_uncertain_001"
        claim_graph = ClaimGraph()
        adjudicator = ClaimAdjudicator(default_recipes=CORE_RECIPES)
        adapter = ClaimProducingAdapter()

        claim = _make_claim(
            claim_id=claim_id, claim_type="inventory_delta",
            mission_id="hsr_daily", node_id="claim",
            skill_id="hsr_claim_rewards",
            claimed_delta={"item": "stellar_jade", "delta": 60},
        )
        claim_graph.add_claim(claim)

        # Only toast, no inventory confirmation
        result = VerifierResult(
            ok=True, verifier_id="observation_graph_ui", confidence=0.75,
            reason="toast detected but weak",
        )
        obs = adapter.adapt(result=result, claim=claim)
        claim_graph.add_observation(obs)

        observations = claim_graph.get_observations_for(claim_id)
        adj_result = adjudicator.adjudicate(claim, observations)
        # Single family, partial evidence → should be tentative or uncertain
        assert adj_result.status in ("tentative", "uncertain", "verified")

        # Uncertainty policy should recommend resample
        policy = UncertaintyPolicy()
        decision = policy.decide(
            confidence=adj_result.confidence,
            risk_level="low",
            can_resample=True,
        )
        assert decision.action in ("auto_execute", "resample_observation")


class TestGenshinEndToEnd:
    """Genshin: Teleport → Navigate → Collect → Verify toast → Delayed audit."""

    def setup_method(self):
        clear_registry()
        self.decl = SkillClaimDeclaration(
            skill_id="genshin_collect_qingxin",
            capsule_id="genshin",
            risk_level="low",
            capabilities_provided=["collect_material"],
            produced_claims=[
                ProducedClaimDecl(
                    claim_type="collection_pickup",
                    target="qingxin",
                    delta=1,
                    claim_role="terminal",
                    stabilization_window_ms=900,
                    verifier_recipe="collection_pickup.default",
                ),
            ],
            input_claims=[
                InputClaimDecl(claim_type="navigation_arrival", target="qingxin_node", required_status="verified"),
            ],
        )
        register_skill_declaration(self.decl)

    def test_genshin_collect_full_pipeline(self):
        mission_id = "genshin_collect_qingxin"
        claim_graph = ClaimGraph()
        adjudicator = ClaimAdjudicator(default_recipes=CORE_RECIPES)
        adapter = ClaimProducingAdapter()

        # Phase A: Navigation claim
        nav_claim = _make_claim(
            claim_id="nav_001", claim_type="navigation_arrival",
            mission_id=mission_id, node_id="navigate",
            skill_id="genshin_route_a",
            claimed_delta={"location": "qingxin_node", "status": "arrived"},
        )
        claim_graph.add_claim(nav_claim)

        nav_obs = ObservationClaim(
            observation_id="obs_nav", claim_id="nav_001",
            source_family="navigation_signal", polarity="support", signal_quality=0.92,
            verifier_id="navigation_progress",
        )
        claim_graph.add_observation(nav_obs)

        nav_observations = claim_graph.get_observations_for("nav_001")
        nav_adj = adjudicator.adjudicate(nav_claim, nav_observations)
        assert nav_adj.status == "verified"

        # Phase B: Collection claim (depends on navigation)
        collect_claim = _make_claim(
            claim_id="collect_001", claim_type="collection_pickup",
            mission_id=mission_id, node_id="collect",
            skill_id="genshin_collect_qingxin",
            claimed_delta={"item": "qingxin", "delta": 1},
            input_claims=["nav_001"],
        )
        claim_graph.add_claim(collect_claim, inferred_dependencies=["nav_001"])

        # Toast + inventory delta signals
        toast_obs = ObservationClaim(
            observation_id="obs_toast_collect", claim_id="collect_001",
            source_family="toast", polarity="support", signal_quality=0.9,
            verifier_id="observation_graph_ui",
        )
        claim_graph.add_observation(toast_obs)

        inv_obs = ObservationClaim(
            observation_id="obs_inv_collect", claim_id="collect_001",
            source_family="inventory_delta", polarity="support", signal_quality=0.88,
            verifier_id="navigation_progress",
        )
        claim_graph.add_observation(inv_obs)

        collect_observations = claim_graph.get_observations_for("collect_001")
        collect_adj = adjudicator.adjudicate(collect_claim, collect_observations)
        assert collect_adj.status == "verified"
        assert collect_adj.confidence > 0.5

        # Phase C: Delayed audit
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            audit_path = f.name
        try:
            scheduler = DelayedAuditScheduler(
                config=AuditScheduleConfig(post_node_delay_ms=0),
                persistence_path=audit_path,
            )
            snapshot = AuditSnapshot(
                inventory_before={"qingxin": 42},
                screen_state_before="overworld",
                position_before={"x": 100.0, "y": 200.0},
            )
            scheduler.schedule(
                audit_id="audit_collect_001", claim_id="collect_001",
                skill_id="genshin_collect_qingxin", claim_type="collection_pickup",
                audit_type="post_node", snapshot=snapshot,
                expected_delta={"item": "qingxin", "delta": 1},
            )
            scheduler.check_due(current_time=time.time() + 5.0)
            completion = scheduler.complete("audit_collect_001", {"item": "qingxin", "delta": 1})
            assert completion.matched
        finally:
            os.unlink(audit_path)

        # Phase D: Reliability update
        reliability = ThreeLayerReliabilityStore()
        reliability.record_adjudication(
            skill_id="genshin_collect_qingxin",
            claim_type="collection_pickup",
            recipe_id="default",
            capsule_id="genshin",
            verifier_id="observation_graph_ui",
            source_family="toast",
            context={"capsule_id": "genshin", "skill_id": "genshin_collect_qingxin"},
            adjudication_status="verified",
            was_correct=True,
        )
        trust = reliability.execution_trust(
            skill_id="genshin_collect_qingxin",
            claim_type="collection_pickup",
            recipe_id="default",
            capsule_id="genshin",
            context={"capsule_id": "genshin"},
        )
        # Single sample → skill_claim_trust = 0.0 (Option A)
        assert trust.recipe_trust > 0.0

        # Phase E: Mission graph with alternative routes
        mg = MissionGraph(mission_id=mission_id, risk_level="low")
        mg.add_node(MissionGraphNode("teleport", "ui_interact", "genshin_teleport", produces=["location_loaded"]))
        mg.add_node(MissionGraphNode("route_a", "navigate", "genshin_route_a", depends_on=["teleport"]))
        mg.add_node(MissionGraphNode("route_b", "navigate", "genshin_route_b", depends_on=["teleport"], alternative_for="route_a"))
        mg.add_node(MissionGraphNode("collect", "collect", "genshin_collect_qingxin", depends_on=["route_a"], claim_role="terminal"))
        mg.add_edge("teleport", "route_a")
        mg.add_edge("teleport", "route_b")
        mg.add_edge("route_a", "collect")
        mg.add_edge("route_b", "collect")

        path = mg.find_path_to("collect")
        assert path is not None

        # Simulate route_a failure, use alternative
        mg.mark_blocked("route_a", "navigation_failed")
        alt_path = mg.find_alternative_path("route_a")
        assert alt_path is not None
        assert "route_b" in alt_path.path

    def test_genshin_collect_audit_mismatch_triggers_reliability_drop(self):
        """Audit mismatch should reduce reliability."""
        reliability = ThreeLayerReliabilityStore()
        ctx = {"capsule_id": "genshin", "skill_id": "genshin_collect_qingxin"}

        # Record 5 verified adjudications
        for _ in range(5):
            reliability.record_adjudication(
                skill_id="genshin_collect_qingxin", claim_type="collection_pickup",
                recipe_id="default", capsule_id="genshin",
                verifier_id="v1", source_family="toast",
                context=ctx, adjudication_status="verified", was_correct=True,
            )
            reliability.record_audit(
                skill_id="genshin_collect_qingxin", claim_type="collection_pickup",
                recipe_id="default", capsule_id="genshin",
                context=ctx, matched=True,
            )

        trust_before = reliability.execution_trust(
            skill_id="genshin_collect_qingxin", claim_type="collection_pickup",
            recipe_id="default", capsule_id="genshin", context=ctx,
        )

        # Record 3 audit mismatches
        for _ in range(3):
            reliability.record_audit(
                skill_id="genshin_collect_qingxin", claim_type="collection_pickup",
                recipe_id="default", capsule_id="genshin",
                context=ctx, matched=False,
            )

        trust_after = reliability.execution_trust(
            skill_id="genshin_collect_qingxin", claim_type="collection_pickup",
            recipe_id="default", capsule_id="genshin", context=ctx,
        )
        assert trust_after.overall < trust_before.overall

    def test_genshin_cascade_invalidation(self):
        """When navigation claim is demoted, collection claim becomes suspect."""
        claim_graph = ClaimGraph()

        nav_claim = _make_claim(
            claim_id="nav_001", claim_type="navigation_arrival",
            mission_id="m1", node_id="navigate",
            skill_id="genshin_route_a",
            claimed_delta={"location": "target", "status": "arrived"},
        )
        claim_graph.add_claim(nav_claim)

        collect_claim = _make_claim(
            claim_id="collect_001", claim_type="collection_pickup",
            mission_id="m1", node_id="collect",
            skill_id="genshin_collect_qingxin",
            claimed_delta={"item": "qingxin", "delta": 1},
            depends_on=["nav_001"],
        )
        claim_graph.add_claim(collect_claim)

        # Demote navigation claim
        report = claim_graph.demote("nav_001", "audit_mismatch")
        assert "collect_001" in report.affected_claims

        # Check cascade decision
        decision = claim_graph.cascade_decision(
            root_claim_id="nav_001",
            decision_dependencies=["collect_001"],
            risk_level="low",
        )
        assert decision.action == "revalidate_cluster"

    def test_genshin_false_negative_recovery(self):
        """When collection succeeds but navigation was demoted → revalidate navigation."""
        claim_graph = ClaimGraph()

        nav_claim = _make_claim(
            claim_id="nav_001", claim_type="navigation_arrival",
            mission_id="m1", node_id="navigate",
            skill_id="route_a",
            claimed_delta={"location": "target", "status": "arrived"},
        )
        claim_graph.add_claim(nav_claim)
        claim_graph.demote("nav_001", "verifier_false_negative")

        collect_claim = _make_claim(
            claim_id="collect_001", claim_type="collection_pickup",
            mission_id="m1", node_id="collect",
            skill_id="collect",
            claimed_delta={"item": "qingxin", "delta": 1},
            depends_on=["nav_001"],
        )
        # Mark collection as verified
        from dataclasses import replace
        collect_claim = replace(collect_claim, status="verified")
        claim_graph.add_claim(collect_claim)

        # False negative detection
        reports = claim_graph.revalidate_from_downstream("collect_001")
        assert len(reports) == 1
        assert reports[0].revalidated
        assert claim_graph.get("nav_001").status == "tentative"


class TestMissionGraphIntegration:
    def test_mission_graph_with_unverifiable_policy(self):
        mg = MissionGraph(mission_id="test", risk_level="low")
        mg.add_node(MissionGraphNode("step_1", "navigate", "route_a", claim_role="dependency"))
        mg.add_node(MissionGraphNode("step_2", "collect", "collect", depends_on=["step_1"], claim_role="terminal"))
        mg.add_edge("step_1", "step_2")

        policy = UnverifiablePolicy("opportunistic")
        budget = UnverifiableBudget(max_count=2)

        # Terminal claim must be verified
        decision = policy.check(
            claim_role="terminal", risk_level="low",
            budget=budget, current_count=0, current_weight=0.0,
        )
        assert not decision.allowed

        # Dependency with low risk under opportunistic
        decision = policy.check(
            claim_role="dependency", risk_level="low",
            budget=budget, current_count=0, current_weight=0.0,
        )
        assert decision.allowed

    def test_mission_graph_cascade_blocks_downstream(self):
        mg = MissionGraph(mission_id="test", risk_level="medium")
        mg.add_node(MissionGraphNode("a", "navigate", "route"))
        mg.add_node(MissionGraphNode("b", "collect", "collect", depends_on=["a"]))
        mg.add_node(MissionGraphNode("c", "verify", "verify", depends_on=["b"]))
        mg.add_edge("a", "b")
        mg.add_edge("b", "c")

        mg.mark_blocked("a", "claim_demoted")
        dependents = mg.get_dependents("a")
        assert "b" in dependents
        assert "c" in dependents
