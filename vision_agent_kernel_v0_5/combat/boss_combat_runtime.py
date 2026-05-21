from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from combat.boss_schema import BossProfile, BossSignal, boss_signal_from_observation, conservative_unknown_boss
from combat.checkpoint_runtime import CheckpointRuntime
from combat.genshin_combat_planner import CombatAction, CombatPlaybook, FallbackStrategy
from combat.genshin_playbook_executor import PlaybookExecutor, PlaybookState
from combat.survival_runtime import SurvivalDecision, SurvivalPolicyEngine, SurvivalState
from combat.team_capability import TeamCombatPlan, TeamProfile
from core.types import InputLease
from reflex.scheduler import PreemptionToken, ReflexScheduler, ResumeContract


class BossCombatState(Enum):
    INIT = "init"
    ACQUIRE_TARGET = "acquire_target"
    IDENTIFY_PHASE = "identify_phase"
    EXECUTE_TACTIC = "execute_tactic"
    REFLEX_PREEMPTED = "reflex_preempted"
    SURVIVAL_RECOVERY = "survival_recovery"
    TARGET_REACQUIRE = "target_reacquire"
    VERIFY_PROGRESS = "verify_progress"
    FINISHED = "finished"
    FAILED_SAFE = "failed_safe"


@dataclass(frozen=True, slots=True)
class BossCombatInput:
    frame_id: int
    boss_hp_ratio: float
    danger_score: float
    telegraph_type: str = ""
    target_visible: bool = True
    cooldown_states: dict[str, bool] = field(default_factory=dict)
    hp_ratios: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])
    survival_state: SurvivalState | None = None
    combo_broken: bool = False
    combat_ended: bool = False
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BossCombatDecision:
    state: str
    action: str
    reason: str
    interrupt: bool = False
    lease: InputLease | None = None
    boss_signal: BossSignal | None = None
    survival_decision: SurvivalDecision | None = None
    resume_contract: ResumeContract | None = None
    evidence_ids: list[str] = field(default_factory=list)
    failure_code: str = ""


class BossCombatRuntime:
    """Closed-loop synthetic/testbed boss combat runtime.

    It owns state transitions and returns deterministic decisions. Physical
    input translation remains outside this runtime and must keep InputLease
    boundaries.
    """

    def __init__(
        self,
        boss_profile: BossProfile | None,
        team_profile: TeamProfile,
        team_plan: TeamCombatPlan,
        survival_engine: SurvivalPolicyEngine | None = None,
        reflex: ReflexScheduler | None = None,
    ) -> None:
        self.boss_profile = boss_profile or conservative_unknown_boss()
        self.team_profile = team_profile
        self.team_plan = team_plan
        self.survival_engine = survival_engine or SurvivalPolicyEngine()
        self.reflex = reflex or ReflexScheduler(danger_threshold=0.7, cooldown_frames=3)
        self.checkpoints = CheckpointRuntime()
        self.executor = PlaybookExecutor()
        self.state = BossCombatState.INIT
        self._target_lost_count = 0
        self._combo_break_count = 0
        self._active_token: PreemptionToken | None = None
        self.executor.start(self._build_playbook())

    def tick(self, sample: BossCombatInput, now: float) -> BossCombatDecision:
        if sample.combat_ended or sample.boss_hp_ratio <= 0.05:
            self.state = BossCombatState.FINISHED
            return BossCombatDecision(self.state.value, "finish", "combat_verified_complete", evidence_ids=sample.evidence_ids)

        boss_signal = boss_signal_from_observation(
            self.boss_profile,
            hp_ratio=sample.boss_hp_ratio,
            telegraph_type=sample.telegraph_type or "generic_warning_area",
            frame_id=sample.frame_id,
            roi_id="boss",
            confidence=0.8,
        )

        if not sample.target_visible:
            self._target_lost_count += 1
            if self._target_lost_count <= 2:
                self.state = BossCombatState.TARGET_REACQUIRE
                return BossCombatDecision(self.state.value, "re_acquire_target", "target_lost", True, evidence_ids=sample.evidence_ids, boss_signal=boss_signal)
            return self._safe_abort("TARGET_LOST_REACQUIRE_FAILED", sample.evidence_ids, boss_signal)
        self._target_lost_count = 0

        token = self.reflex.evaluate(sample.danger_score, boss_signal.attack_pattern_id, sample.frame_id)
        if token is not None:
            self._active_token = token
            self.checkpoints.save("boss_reflex_checkpoint", self.executor.snapshot().state, "target_visible")
            self.state = BossCombatState.REFLEX_PREEMPTED
            return BossCombatDecision(
                self.state.value,
                boss_signal.safe_response if boss_signal.safe_response else "dodge_reflex",
                "danger_preempted",
                True,
                evidence_ids=[*sample.evidence_ids, boss_signal.evidence_id],
                boss_signal=boss_signal,
            )

        if self._active_token is not None:
            contract = self.reflex.verify_danger_cleared(self._active_token, sample.danger_score, [*sample.evidence_ids, boss_signal.evidence_id])
            if contract is None:
                self.state = BossCombatState.REFLEX_PREEMPTED
                return BossCombatDecision(self.state.value, "hold_safe", "waiting_danger_clear", True, evidence_ids=sample.evidence_ids, boss_signal=boss_signal)
            self._active_token = None
            self.state = BossCombatState.EXECUTE_TACTIC
            return BossCombatDecision(self.state.value, "resume_checkpoint", "danger_cleared", False, resume_contract=contract, evidence_ids=contract.evidence_ids, boss_signal=boss_signal)

        survival_state = sample.survival_state or SurvivalState(
            active_hp=sample.hp_ratios[0] if sample.hp_ratios else 1.0,
            team_hp=sample.hp_ratios,
            healer_available=self.team_profile.has_healer,
            shielder_available=self.team_profile.has_shielder,
            shield_active=False,
            danger_score=sample.danger_score,
        )
        survival_decision = self.survival_engine.decide(survival_state)
        if survival_decision.kind != "none":
            if survival_decision.kind == "safe_abort":
                return self._safe_abort(survival_decision.failure_code or "SURVIVAL_SAFE_ABORT", sample.evidence_ids, boss_signal, survival_decision)
            self.state = BossCombatState.SURVIVAL_RECOVERY
            self.checkpoints.save("boss_survival_checkpoint", self.executor.snapshot().state, "target_visible")
            return BossCombatDecision(
                self.state.value,
                survival_decision.action,
                survival_decision.reason,
                survival_decision.interrupt,
                evidence_ids=[*sample.evidence_ids, boss_signal.evidence_id],
                boss_signal=boss_signal,
                survival_decision=survival_decision,
            )

        if sample.combo_broken:
            self._combo_break_count += 1
            if self._combo_break_count > 3:
                return self._safe_abort("COMBO_BREAK_REPEATED", sample.evidence_ids, boss_signal)
            self.executor.restore(self.executor.snapshot())
            self.state = BossCombatState.EXECUTE_TACTIC
            return BossCombatDecision(self.state.value, "reset_tactic", "combo_break", False, evidence_ids=sample.evidence_ids, boss_signal=boss_signal)

        action = self.executor.tick(100.0, {"overall_danger": sample.danger_score}, sample.cooldown_states, sample.hp_ratios)
        self.state = BossCombatState.EXECUTE_TACTIC
        if self.executor.state == PlaybookState.FAILED:
            return self._safe_abort("PLAYBOOK_FAILED", sample.evidence_ids, boss_signal)
        if action is None:
            return BossCombatDecision(
                self.state.value,
                "wait_tactic",
                "no_ready_rotation_action",
                False,
                evidence_ids=[*sample.evidence_ids, boss_signal.evidence_id],
                boss_signal=boss_signal,
            )
        lease = self._lease_for_action(action, now)
        return BossCombatDecision(
            self.state.value,
            action.action,
            "execute_rotation",
            False,
            lease=lease,
            evidence_ids=[*sample.evidence_ids, boss_signal.evidence_id],
            boss_signal=boss_signal,
        )

    def _build_playbook(self) -> CombatPlaybook:
        rotation: list[CombatAction] = []
        primary = self.team_profile.primary_dps_slot
        if self.team_plan.conservative_level >= 2:
            rotation.extend([
                CombatAction("normal_attack", primary, repeat=2, priority=55),
                CombatAction("e_skill", primary, condition="skill_e_ready", priority=45),
            ])
        else:
            rotation.extend([
                CombatAction("e_skill", primary, condition="skill_e_ready", priority=40),
                CombatAction("normal_attack", primary, repeat=3, priority=50),
                CombatAction("q_burst", primary, condition="energy_full", priority=30),
            ])
        return CombatPlaybook(
            playbook_id=f"boss_runtime_{self.boss_profile.boss_id}",
            team=[c.character_id for c in self.team_profile.characters],
            enemy=self.boss_profile.boss_id,
            default_rotation=rotation,
            priority_triggers=[],
            fallback=FallbackStrategy("re_acquire_target", "reset_tactic", "safe_abort", "safe_abort"),
            elemental_chain=self.team_plan.main_chain,
        )

    def _lease_for_action(self, action: CombatAction, now: float) -> InputLease:
        key = {
            "normal_attack": "mouse_left",
            "e_skill": "E",
            "q_burst": "Q",
            "switch": str(action.character),
            "dodge": "Shift",
            "heal": "Q",
            "shield": "E",
        }.get(action.action, "mouse_left")
        return InputLease(
            lease_id=f"boss:{self.boss_profile.boss_id}:{action.action}:{int(now * 1000)}",
            owner="boss_combat_runtime",
            priority=40 if action.action != "normal_attack" else 20,
            key_states={key: "DOWN"},
            mouse_delta=None,
            created_at=now,
            expires_at=now + 0.18,
            reason=f"boss_action:{action.action}",
        )

    def _safe_abort(
        self,
        failure_code: str,
        evidence_ids: list[str],
        boss_signal: BossSignal | None,
        survival_decision: SurvivalDecision | None = None,
    ) -> BossCombatDecision:
        self.state = BossCombatState.FAILED_SAFE
        ids = list(evidence_ids)
        if boss_signal is not None:
            ids.append(boss_signal.evidence_id)
        return BossCombatDecision(
            self.state.value,
            "release_all",
            "safe_abort",
            True,
            boss_signal=boss_signal,
            survival_decision=survival_decision,
            evidence_ids=ids,
            failure_code=failure_code,
        )
