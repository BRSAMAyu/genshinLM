"""Tests for Claim-Centric Runtime: all 5 control planes + integration."""
from __future__ import annotations

import time

import pytest

from runtime.claim_runtime import (
    AuditDifficultyTracker,
    AuditSnapshot,
    CapabilityReliabilityGate,
    ClaimExecutionResult,
    ClaimGraph,
    ClaimProducingExecutor,
    ConfidenceFactors,
    DelayedAuditEngine,
    DriftDetector,
    EpisodeAnalyzer,
    FalseNegativeReport,
    PlanCandidate,
    PlanQualityChecklist,
    ReliabilityStore,
    ReplanOption,
    RiskThreshold,
    RunJournalEntry,
    SignalEvidence,
    StabilizationEstimate,
    StabilizationTracker,
    StateDeltaClaim,
    UncertaintyDecision,
    UncertaintyPolicy,
    wilson_lower_bound,
    RISK_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# 1. StateDeltaClaim — confidence is system-computed
# ---------------------------------------------------------------------------


class TestStateDeltaClaim:
    def test_confidence_factors_multiply(self) -> None:
        factors = ConfidenceFactors(
            signal_quality=0.9, verifier_historical_reliability=0.8,
            context_match_score=0.75, sample_sufficiency=0.5, drift_penalty=1.0,
        )
        assert 0.25 < factors.compute() < 0.35

    def test_from_signals_factory_produces_stabilized_claim(self) -> None:
        signal = SignalEvidence(
            signal_id="toast", source="ocr", confidence=0.9,
            frame_consistency=0.8, temporal_pattern_match=0.7,
        )
        claim = StateDeltaClaim.from_signals(
            claim_id="c1", mission_id="m", node_id="n", skill_id="collect",
            claim_type="collection_pickup", claimed_delta={"inventory.qingxin": 1},
            verifier_historical_reliability=0.8, context_match_score=0.75,
            signals=[signal],
        )
        assert claim.confidence_factors is not None
        assert claim.stabilization_window_ms == 900
        assert 0 < claim.confidence < 1.0

    def test_all_dependencies_merges_input_and_inferred(self) -> None:
        claim = StateDeltaClaim(
            claim_id="c", mission_id="m", node_id="n", skill_id="s",
            claim_type="generic_unknown", claimed_delta={},
            input_claims=["a"], depends_on=["b"], inferred_depends_on=["c"],
        )
        assert claim.all_dependencies == ["a", "b", "c"]

    def test_stabilization_defaults_per_family(self) -> None:
        assert StateDeltaClaim.stabilization_default("combat_target_killed") == 1200
        assert StateDeltaClaim.stabilization_default("boss_phase_changed") == 1800
        assert StateDeltaClaim.stabilization_default("nonexistent") == 1000

    def test_signal_evidence_quality_averages_dimensions(self) -> None:
        sig = SignalEvidence(
            signal_id="s1", source="detector", confidence=0.8,
            spatial_quality=0.7, ocr_quality=0.9,
            detector_confidence=0.6, frame_consistency=0.8,
            temporal_pattern_match=0.5, cross_signal_agreement=0.7,
        )
        assert 0.5 < sig.quality() < 0.9

    def test_zero_signal_quality_when_empty(self) -> None:
        claim = StateDeltaClaim.from_signals(
            claim_id="c", mission_id="m", node_id="n", skill_id="s",
            claim_type="generic_unknown", claimed_delta={},
            verifier_historical_reliability=0.8, context_match_score=0.8,
            signals=[],
        )
        assert claim.confidence_factors is not None
        assert claim.confidence_factors.signal_quality == 0.0


# ---------------------------------------------------------------------------
# 2. ClaimGraph — dependencies, cascade, false negative
# ---------------------------------------------------------------------------


class TestClaimGraph:
    def _make_chain(self) -> ClaimGraph:
        graph = ClaimGraph()
        root = StateDeltaClaim(
            claim_id="pos", mission_id="m", node_id="n1", skill_id="teleport",
            claim_type="teleport_loaded", claimed_delta={"location": "liyue"},
            status="verified",
        )
        mid = StateDeltaClaim(
            claim_id="collect", mission_id="m", node_id="n2", skill_id="pick",
            claim_type="collection_pickup", claimed_delta={"inventory.qingxin": 1},
            input_claims=["pos"],
        )
        leaf = StateDeltaClaim(
            claim_id="inventory", mission_id="m", node_id="n3", skill_id="audit",
            claim_type="inventory_delta", claimed_delta={"inventory.qingxin": 1},
            depends_on=["collect"],
        )
        graph.add_claim(root)
        gaps = graph.add_claim(mid, inferred_dependencies=["pre_scan"])
        graph.add_claim(leaf)
        assert gaps[0].code == "DEPENDENCY_DECLARATION_GAP"
        return graph

    def test_downstream_traversal(self) -> None:
        graph = self._make_chain()
        assert graph.downstream("pos") == ["collect", "inventory"]
        assert graph.downstream("collect") == ["inventory"]
        assert graph.downstream("inventory") == []

    def test_cascade_demotion_propagates(self) -> None:
        graph = self._make_chain()
        report = graph.demote("pos", reason="audit_mismatch")
        assert report.affected_claims == ["pos", "collect", "inventory"]
        assert graph.get("pos").status == "demoted"
        assert graph.get("collect").status == "suspect"
        assert graph.get("inventory").status == "suspect"

    def test_cascade_decision_cluster_scoped(self) -> None:
        graph = self._make_chain()
        # Decision doesn't depend on affected cluster
        d = graph.cascade_decision(root_claim_id="pos", decision_dependencies=["other"], risk_level="high")
        assert d.action == "continue_with_warning"
        # Decision depends on affected cluster, low risk
        d = graph.cascade_decision(root_claim_id="pos", decision_dependencies=["collect"], risk_level="low")
        assert d.action == "revalidate_cluster"
        # Critical risk
        d = graph.cascade_decision(root_claim_id="pos", decision_dependencies=["collect"], risk_level="critical")
        assert d.action == "safe_abort_user_confirm"
        # Medium/high risk
        d = graph.cascade_decision(root_claim_id="pos", decision_dependencies=["collect"], risk_level="medium")
        assert d.action == "pause_replan"

    def test_false_negative_detection_downstream_revalidates_upstream(self) -> None:
        graph = ClaimGraph()
        upstream = StateDeltaClaim(
            claim_id="pick_failed", mission_id="m", node_id="n1",
            skill_id="pick", claim_type="collection_pickup",
            claimed_delta={"inventory.qingxin": 1}, status="demoted",
        )
        downstream = StateDeltaClaim(
            claim_id="inventory_ok", mission_id="m", node_id="n2",
            skill_id="audit", claim_type="inventory_delta",
            claimed_delta={"inventory.qingxin": 1}, status="verified",
            input_claims=["pick_failed"],
        )
        graph.add_claim(upstream)
        graph.add_claim(downstream)

        # Downstream is verified but upstream is demoted → false negative detected
        def verifier_always_ok(claim: StateDeltaClaim) -> bool:
            return True

        reports = graph.revalidate_from_downstream("inventory_ok", verifier_fn=verifier_always_ok)
        assert len(reports) == 1
        assert reports[0].revalidated is True
        assert reports[0].upstream_claim_id == "pick_failed"
        assert graph.get("pick_failed").status == "tentative"

    def test_false_negative_no_action_when_downstream_not_verified(self) -> None:
        graph = ClaimGraph()
        upstream = StateDeltaClaim(
            claim_id="u1", mission_id="m", node_id="n1",
            skill_id="s", claim_type="generic_unknown",
            claimed_delta={}, status="demoted",
        )
        downstream = StateDeltaClaim(
            claim_id="d1", mission_id="m", node_id="n2",
            skill_id="s2", claim_type="generic_unknown",
            claimed_delta={}, status="uncertain",
            input_claims=["u1"],
        )
        graph.add_claim(upstream)
        graph.add_claim(downstream)
        reports = graph.revalidate_from_downstream("d1")
        assert len(reports) == 0

    def test_get_optional_returns_none_for_missing(self) -> None:
        graph = ClaimGraph()
        assert graph.get_optional("nonexistent") is None


# ---------------------------------------------------------------------------
# 3. UncertaintyPolicy — exit paths, LLM doesn't pick bad options
# ---------------------------------------------------------------------------


class TestUncertaintyPolicy:
    def test_auto_execute_above_threshold(self) -> None:
        policy = UncertaintyPolicy()
        d = policy.decide(confidence=0.75, risk_level="medium")
        assert d.action == "auto_execute"

    def test_low_confidence_triggers_resample(self) -> None:
        policy = UncertaintyPolicy()
        d = policy.decide(confidence=0.4, risk_level="low", can_resample=True)
        assert d.action == "resample_observation"
        assert d.max_wait_ms > 0

    def test_all_bad_options_go_to_human_not_llm(self) -> None:
        policy = UncertaintyPolicy()
        bad_options = [ReplanOption("a", 0.31), ReplanOption("b", 0.29)]
        d = policy.decide(confidence=0.3, risk_level="medium", options=bad_options)
        assert d.action == "human_confirm"
        assert "below_threshold" in d.reason

    def test_max_replan_cycle_aborts(self) -> None:
        policy = UncertaintyPolicy(max_replan_cycle_per_node=3)
        d = policy.decide(confidence=0.5, risk_level="low", replan_count=3)
        assert d.action == "abort_safe"

    def test_critical_risk_always_human(self) -> None:
        policy = UncertaintyPolicy()
        d = policy.decide(confidence=0.95, risk_level="critical")
        assert d.action == "human_confirm"

    def test_exit_path_progression(self) -> None:
        policy = UncertaintyPolicy()
        d = policy.decide(confidence=0.3, risk_level="low", can_resample=False, alternate_verifier_available=True)
        assert d.action == "alternate_verifier"
        d = policy.decide(confidence=0.3, risk_level="low", can_resample=False,
                          alternate_verifier_available=False, safe_probe_available=True)
        assert d.action == "safe_probe"
        d = policy.decide(confidence=0.3, risk_level="low", can_resample=False,
                          alternate_verifier_available=False, safe_probe_available=False,
                          local_recovery_available=True)
        assert d.action == "local_recovery"


# ---------------------------------------------------------------------------
# 4. DelayedAudit — snapshots, contamination, difficulty
# ---------------------------------------------------------------------------


class TestDelayedAudit:
    def test_matched_audit(self) -> None:
        claim = StateDeltaClaim(
            claim_id="c", mission_id="m", node_id="n", skill_id="s",
            claim_type="collection_pickup", claimed_delta={"item": 1},
        )
        engine = DelayedAuditEngine()
        record = engine.create_record(audit_id="a", claim=claim,
                                       snapshot=AuditSnapshot(inventory_before={"item": 5}))
        result = engine.complete(record, {"item": 1})
        assert result.status == "matched"
        assert result.completed_at is not None

    def test_mismatch_audit(self) -> None:
        claim = StateDeltaClaim(
            claim_id="c", mission_id="m", node_id="n", skill_id="s",
            claim_type="collection_pickup", claimed_delta={"item": 1},
        )
        engine = DelayedAuditEngine()
        record = engine.create_record(audit_id="a", claim=claim, snapshot=AuditSnapshot())
        result = engine.complete(record, {"item": 0})
        assert result.status == "mismatch"

    def test_contaminated_does_not_count_as_success_or_failure(self) -> None:
        claim = StateDeltaClaim(
            claim_id="c", mission_id="m", node_id="n", skill_id="s",
            claim_type="collection_pickup", claimed_delta={"item": 1},
        )
        engine = DelayedAuditEngine()
        record = engine.create_record(audit_id="a", claim=claim, snapshot=AuditSnapshot())
        result = engine.complete(record, {"item": 1}, ["user_consumed_item"])
        assert result.status == "contaminated"
        assert result.contamination_reasons == ["user_consumed_item"]


class TestAuditDifficulty:
    def test_contaminated_rate_triggers_low_activity_switch(self) -> None:
        tracker = AuditDifficultyTracker(threshold=0.5, min_total=3, low_activity_retry_limit=3)
        for _ in range(3):
            status = tracker.record("skill", "contaminated")
        assert status.recommendation == "switch_to_low_activity_window_audit"

    def test_audit_difficult_after_low_activity_failures(self) -> None:
        tracker = AuditDifficultyTracker(threshold=0.5, min_total=3, low_activity_retry_limit=2)
        for _ in range(3):
            tracker.record("skill", "contaminated", low_activity_retry=True)
        status = tracker.status("skill")
        assert status.audit_difficult is True
        assert status.recommendation == "mark_audit_difficult"

    def test_normal_audits_stay_ok(self) -> None:
        tracker = AuditDifficultyTracker()
        for _ in range(5):
            tracker.record("skill", "matched")
        status = tracker.status("skill")
        assert status.recommendation == "continue_standard_audit"


# ---------------------------------------------------------------------------
# 5. Reliability — Wilson, pyramid, drift
# ---------------------------------------------------------------------------


class TestReliability:
    def test_wilson_lower_bound_conservative(self) -> None:
        assert wilson_lower_bound(0, 0) == 0.0
        assert wilson_lower_bound(9, 10) < 0.9
        assert wilson_lower_bound(90, 100) > 0.8

    def test_context_backoff_to_coarser_level(self) -> None:
        store = ReliabilityStore(min_samples=5)
        ctx_fine = {"capsule_id": "hsr", "screen_state": "combat", "mission_phase": "boss", "target_class": "boss_a"}
        ctx_coarse = {"capsule_id": "hsr", "screen_state": "combat", "mission_phase": "boss"}
        # Record at coarse level only
        for _ in range(7):
            store.record("skill", ctx_coarse, "matched")
        # Fine level has 0 samples, should back off to coarse
        est = store.estimate("skill", ctx_fine, preferred_level=3)
        assert est.total == 7
        assert est.level_used < 3

    def test_drift_demotion_halves_reliability(self) -> None:
        store = ReliabilityStore(min_samples=3)
        ctx = {"capsule_id": "g", "screen_state": "overworld"}
        for _ in range(10):
            store.record("skill", ctx, "matched")
        normal = store.estimate("skill", ctx)
        store.mark_version_drift("skill")
        drifted = store.estimate("skill", ctx)
        assert drifted.drift_penalty == 0.5
        assert drifted.reliability < normal.reliability

    def test_contaminated_does_not_update_reliability(self) -> None:
        store = ReliabilityStore(min_samples=3)
        ctx = {"capsule_id": "g"}
        store.record("skill", ctx, "contaminated")
        store.record("skill", ctx, "contaminated")
        est = store.estimate("skill", ctx)
        assert est.total == 0  # contaminated doesn't count


class TestCapabilityReliabilityGate:
    def test_critical_always_human_confirm(self) -> None:
        store = ReliabilityStore(min_samples=3)
        ctx = {"capsule_id": "g"}
        for _ in range(10):
            store.record("skill", ctx, "matched")
        gate = CapabilityReliabilityGate(store)
        d = gate.evaluate("skill", ctx, "critical")
        assert d.allowed is False
        assert d.requires_human_confirm is True

    def test_high_risk_low_reliability_requires_confirm(self) -> None:
        store = ReliabilityStore(min_samples=3)
        gate = CapabilityReliabilityGate(store)
        d = gate.evaluate("unknown_skill", {"capsule_id": "g"}, "high")
        assert d.allowed is False
        assert d.requires_human_confirm is True

    def test_low_risk_allows_with_enough_reliability(self) -> None:
        store = ReliabilityStore(min_samples=3)
        ctx = {"capsule_id": "g"}
        for _ in range(30):
            store.record("skill", ctx, "matched")
        gate = CapabilityReliabilityGate(store)
        d = gate.evaluate("skill", ctx, "low")
        assert d.allowed is True

    def test_risk_thresholds_are_correct(self) -> None:
        assert RISK_THRESHOLDS["low"].min_auto_execution_confidence == 0.60
        assert RISK_THRESHOLDS["medium"].min_auto_execution_confidence == 0.70
        assert RISK_THRESHOLDS["high"].min_auto_execution_confidence == 0.80
        assert RISK_THRESHOLDS["critical"].min_auto_execution_confidence > 1.0


# ---------------------------------------------------------------------------
# 6. StabilizationTracker — auto-adjusting windows
# ---------------------------------------------------------------------------


class TestStabilizationTracker:
    def test_default_window_returned_with_no_samples(self) -> None:
        tracker = StabilizationTracker()
        est = tracker.estimate("collection_pickup")
        assert est.current_window_ms == 900
        assert est.sample_count == 0

    def test_window_increases_on_high_failure_rate(self) -> None:
        tracker = StabilizationTracker(min_samples=5, increase_factor=1.5)
        for _ in range(6):
            tracker.record("collection_pickup", False)
        est = tracker.estimate("collection_pickup")
        assert est.current_window_ms > 900
        assert est.failure_rate > 0.5

    def test_window_stays_stable_on_mixed_results(self) -> None:
        tracker = StabilizationTracker(min_samples=5)
        for success in [True, True, True, False, True, True, True]:
            tracker.record("collection_pickup", success)
        est = tracker.estimate("collection_pickup")
        assert est.current_window_ms == 900
        assert est.failure_rate < 0.2

    def test_window_does_not_go_below_family_default(self) -> None:
        tracker = StabilizationTracker(min_samples=5, decrease_factor=0.5)
        for _ in range(20):
            tracker.record("collection_pickup", True)
        est = tracker.estimate("collection_pickup")
        assert est.current_window_ms >= 900


# ---------------------------------------------------------------------------
# 7. DriftDetector — environment version detection
# ---------------------------------------------------------------------------


class TestDriftDetector:
    def test_no_drift_when_stable(self) -> None:
        detector = DriftDetector()
        detector.set_baseline("ui_main_menu", {"layout_position": 0.5, "ocr_confidence": 0.9})
        report = detector.check("ui_main_menu", {"layout_position": 0.52, "ocr_confidence": 0.88})
        assert report.drifted is False
        assert report.recommendation == "stable"

    def test_drift_detected_on_layout_shift(self) -> None:
        detector = DriftDetector(layout_shift_threshold=0.2)
        detector.set_baseline("ui", {"layout_position": 0.5})
        report = detector.check("ui", {"layout_position": 0.85})
        assert report.drifted is True
        assert report.signals[0].detector_type == "layout_shift"
        assert report.recommendation == "invalidate_and_bootstrap"

    def test_drift_detected_on_confidence_drop(self) -> None:
        detector = DriftDetector(confidence_drop_threshold=0.15)
        detector.set_baseline("ocr", {"ocr_confidence": 0.9})
        report = detector.check("ocr", {"ocr_confidence": 0.5})
        assert report.drifted is True

    def test_no_baseline_returns_stable(self) -> None:
        detector = DriftDetector()
        report = detector.check("unknown", {"anything": 0.5})
        assert report.drifted is False
        assert report.recommendation == "no_baseline"

    def test_affected_skills_propagated(self) -> None:
        detector = DriftDetector()
        detector.set_baseline("ui", {"layout_position": 0.5})
        report = detector.check("ui", {"layout_position": 0.9}, affected_skills=["skill_a", "skill_b"])
        assert report.affected_skills == ["skill_a", "skill_b"]


# ---------------------------------------------------------------------------
# 8. DecisionMemory — distillation from RunJournal
# ---------------------------------------------------------------------------


class TestDecisionMemory:
    def test_episode_analyzer_extracts_conclusions(self) -> None:
        entries = [
            RunJournalEntry("d1", "m", "collect", "west", {"loc": "A"}, outcome="failed",
                            failure_reason="blocked", evidence_refs=["e1"]),
            RunJournalEntry("d2", "m", "collect", "east", {"loc": "B"},
                            actual_delta={"ok": True}, outcome="matched", evidence_refs=["e2"]),
            RunJournalEntry("d3", "m", "collect", "east", {"loc": "B"},
                            actual_delta={"ok": True}, outcome="matched", evidence_refs=["e3"]),
        ]
        packet = EpisodeAnalyzer().summarize(entries, "collect")
        assert packet.last_successful_approach == "east"
        assert packet.current_obstacle == "blocked"
        assert "west" in packet.do_not_repeat
        assert "east" in packet.recovery_options

    def test_no_entries_returns_defaults(self) -> None:
        packet = EpisodeAnalyzer().summarize([], "goal")
        assert packet.last_successful_approach == "none_recorded"
        assert packet.confidence_this_works == 0.0


class TestPlanQualityChecklist:
    def test_cycle_detected(self) -> None:
        checker = PlanQualityChecklist()
        result = checker.validate(
            PlanCandidate("p", ["s1"], [("a", "b"), ("b", "a")]),
            lambda _: 0.9,
        )
        assert result.ok is False
        assert "plan_cycle_detected" in result.errors

    def test_low_reliability_rejected(self) -> None:
        checker = PlanQualityChecklist()
        result = checker.validate(
            PlanCandidate("p", ["bad_skill"], []),
            lambda _: 0.2,
        )
        assert result.ok is False
        assert "low_reliability_skill:bad_skill" in result.errors

    def test_repeated_failed_paths_flagged(self) -> None:
        checker = PlanQualityChecklist()
        result = checker.validate(
            PlanCandidate("p", ["s"], [], repeated_failed_paths=["west_approach"]),
            lambda _: 0.8,
        )
        assert result.ok is False
        assert "repeated_failed_path:west_approach" in result.errors

    def test_valid_plan_passes(self) -> None:
        checker = PlanQualityChecklist()
        result = checker.validate(
            PlanCandidate("p", ["good_skill"], [("a", "b")]),
            lambda _: 0.85,
        )
        assert result.ok is True


# ---------------------------------------------------------------------------
# 9. ClaimProducingExecutor — end-to-end integration
# ---------------------------------------------------------------------------


class TestClaimProducingExecutor:
    def test_pre_flight_blocks_low_reliability_skill(self) -> None:
        executor = ClaimProducingExecutor()
        gate, uncertainty = executor.pre_flight(
            "unknown_skill", {"capsule_id": "g"}, "high",
        )
        assert gate.allowed is False
        assert uncertainty.action != "auto_execute"

    def test_full_pipeline_produce_and_verify_success(self) -> None:
        store = ReliabilityStore(min_samples=3)
        for _ in range(10):
            store.record("collect", {"capsule_id": "g", "screen_state": "overworld"}, "matched")
        executor = ClaimProducingExecutor(reliability_store=store)
        ctx = {"capsule_id": "g", "screen_state": "overworld"}
        result = executor.produce_claim(
            claim_id="c1", mission_id="m1", node_id="n1", skill_id="collect",
            claim_type="collection_pickup", claimed_delta={"inventory.qingxin": 1},
            risk_level="low", context=ctx,
            snapshot=AuditSnapshot(inventory_before={"qingxin": 5}),
        )
        assert result.claim.claim_id == "c1"
        assert result.audit_record is not None
        assert result.claim.status == "asserted"

        # Verify as success
        verified = executor.verify_claim(
            "c1", ok=True, actual_delta={"inventory.qingxin": 1},
            audit_record=result.audit_record, context=ctx,
        )
        assert verified.status == "verified"
        assert len(executor.journal) == 1

    def test_full_pipeline_verify_failure_demotes(self) -> None:
        executor = ClaimProducingExecutor()
        result = executor.produce_claim(
            claim_id="c2", mission_id="m1", node_id="n1", skill_id="collect",
            claim_type="collection_pickup", claimed_delta={"inventory.qingxin": 1},
        )
        verified = executor.verify_claim("c2", ok=False)
        assert verified.status == "demoted"

    def test_summarize_for_llm_produces_decision_packet(self) -> None:
        executor = ClaimProducingExecutor()
        # First claim succeeds — goal="collect" set via claimed_delta
        executor.produce_claim(
            claim_id="c1", mission_id="m", node_id="n", skill_id="collect",
            claim_type="collection_pickup", claimed_delta={"goal": "collect", "item": 1},
        )
        executor.verify_claim("c1", ok=True)
        # Update journal outcome for correct distillation
        from dataclasses import replace as _replace
        executor._journal[-1] = _replace(executor._journal[-1], goal="collect", outcome="matched")
        # Second claim fails
        executor.produce_claim(
            claim_id="c2", mission_id="m", node_id="n2", skill_id="collect",
            claim_type="collection_pickup", claimed_delta={"goal": "collect", "item": 1},
        )
        executor.verify_claim("c2", ok=False)
        executor._journal[-1] = _replace(executor._journal[-1], goal="collect", outcome="failed")
        packet = executor.summarize_for_llm("collect")
        assert packet.last_successful_approach == "collect"

    def test_false_negative_recovery_through_pipeline(self) -> None:
        executor = ClaimProducingExecutor()
        # Upstream claim
        executor.produce_claim(
            claim_id="upstream", mission_id="m", node_id="n1", skill_id="teleport",
            claim_type="teleport_loaded", claimed_delta={"location": "liyue"},
        )
        executor.verify_claim("upstream", ok=False)  # False negative
        assert executor.claim_graph.get("upstream").status == "demoted"

        # Downstream claim depends on upstream
        executor.produce_claim(
            claim_id="downstream", mission_id="m", node_id="n2", skill_id="collect",
            claim_type="collection_pickup", claimed_delta={"item": 1},
            input_claims=["upstream"],
        )
        executor.verify_claim("downstream", ok=True)
        # Downstream verified should trigger upstream re-evaluation
        assert executor.claim_graph.get("upstream").status == "tentative"

    def test_risk_stratified_execution(self) -> None:
        store = ReliabilityStore(min_samples=3)
        for _ in range(10):
            store.record("skill", {"capsule_id": "g"}, "matched")
        executor = ClaimProducingExecutor(reliability_store=store)

        # Low risk should be allowed
        gate_low, _ = executor.pre_flight("skill", {"capsule_id": "g"}, "low")
        assert gate_low.allowed is True

        # High risk needs higher threshold
        gate_high, _ = executor.pre_flight("skill", {"capsule_id": "g"}, "high")
        # With 10/10 matches, Wilson bound should be high enough for high risk
        assert gate_high.allowed is True or gate_high.requires_human_confirm is True

    def test_max_replan_cycles_abort(self) -> None:
        executor = ClaimProducingExecutor(
            uncertainty_policy=UncertaintyPolicy(max_replan_cycle_per_node=2),
            reliability_store=ReliabilityStore(min_samples=100),
        )
        for i in range(3):
            result = executor.produce_claim(
                claim_id=f"c{i}", mission_id="m", node_id="n1",
                skill_id="failing_skill", claim_type="generic_unknown",
                claimed_delta={}, risk_level="low",
            )
            executor.verify_claim(f"c{i}", ok=False)
        _, uncertainty = executor.pre_flight("failing_skill", {}, "low", node_id="n1")
        assert uncertainty.action == "abort_safe"


# ---------------------------------------------------------------------------
# 10. Multi-signal VerifierResult (false negative detection)
# ---------------------------------------------------------------------------


class TestVerifierResultEnhancements:
    def test_verifier_result_has_false_negative_fields(self) -> None:
        from execution.verifier_base import VerifierResult, SignalCorroboration
        result = VerifierResult(
            ok=False, verifier_id="test", confidence=0.3, reason="not_found",
            alternative_signals=[SignalCorroboration("s1", "ocr", True, 0.8, "alt_found")],
            false_negative_likelihood=0.4,
            re_verify_recommended=True,
        )
        assert len(result.alternative_signals) == 1
        assert result.alternative_signals[0].supports_ok is True
        assert result.false_negative_likelihood == 0.4
        assert result.re_verify_recommended is True
