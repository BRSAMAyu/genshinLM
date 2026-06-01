"""Dry-run 3D open-world embodied autonomy runtime.

The runtime compiles visual cues into semantic navigation, combat, interaction,
dialogue, puzzle, loot, and reward actions. It does not call physical input.
Execution remains behind the existing safe-window/input-lease layers.
"""
from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from agent_kernel.types import StateDeltaClaim, ThreatSignal


NavigationCueSource = Literal["target_visible", "native_guide", "minimap", "landmark", "scan", "none"]
EmbodiedActionKind = Literal["navigation", "combat", "interaction", "dialogue", "puzzle", "loot", "reward", "system"]
CommissionObjectiveType = Literal["combat", "interaction", "dialogue", "puzzle"]


@dataclass(frozen=True, slots=True)
class NavigationFrame:
    """Compressed 3D world snapshot used by the navigation brainstem."""
    screen_state: str = "overworld"
    target_label: str = ""
    target_bbox_norm: tuple[float, float, float, float] | None = None
    target_confidence: float = 0.0
    target_kind: str = "unknown"
    distance_m: float | None = None
    native_guide_bearing_deg: float | None = None
    minimap_bearing_deg: float | None = None
    landmark_bearing_deg: float | None = None
    interaction_prompt: str = ""
    progress_delta_m: float = 0.0
    scan_coverage_deg: float = 0.0
    stuck_score: float = 0.0
    threats: tuple[ThreatSignal, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmbodiedAction:
    """Coordinate-independent action intent produced by the embodied runtime."""
    kind: EmbodiedActionKind
    intent: str
    params: tuple[tuple[str, str], ...] = ()
    reason: str = ""
    priority: int = 50
    expected_claim_type: str = "generic_unknown"

    def param(self, key: str, default: str = "") -> str:
        return dict(self.params).get(key, default)


@dataclass(frozen=True, slots=True)
class TeamMemberRuntime:
    slot: int
    role: Literal["driver", "sub_dps", "support", "healer", "shielder"]
    hp_pct: float = 1.0
    skill_ready: bool = True
    burst_ready: bool = False
    energy_pct: float = 0.0
    cooldown_ms: int = 0
    summary: str = ""


@dataclass(frozen=True, slots=True)
class TeamCombatRuntime:
    active_slot: int
    members: tuple[TeamMemberRuntime, ...]
    food_available: bool = True
    preferred_rotation: tuple[int, ...] = ()

    def active_member(self) -> TeamMemberRuntime:
        return self.member(self.active_slot)

    def member(self, slot: int) -> TeamMemberRuntime:
        for member in self.members:
            if member.slot == slot:
                return member
        raise KeyError(f"unknown team slot: {slot}")

    def healer(self) -> TeamMemberRuntime | None:
        return next((m for m in self.members if m.role == "healer"), None)


@dataclass(frozen=True, slots=True)
class DailyCommissionObjective:
    objective_id: str
    objective_type: CommissionObjectiveType
    target_region: str
    waypoint_id: str
    target_label: str = ""
    puzzle_hint: str = ""


@dataclass(frozen=True, slots=True)
class DailyCommissionTrace:
    actions: tuple[EmbodiedAction, ...]
    claims: tuple[StateDeltaClaim, ...]
    completed: bool
    final_phase: str

    def intents(self) -> tuple[str, ...]:
        return tuple(action.intent for action in self.actions)


class HybridOpenWorldNavigator:
    """Hybrid navigation policy: visible target > native guide > minimap > scan."""

    def decide(self, frame: NavigationFrame, *, interact_range_m: float = 3.0) -> EmbodiedAction:
        if frame.screen_state in {"loading", "black_screen"}:
            return EmbodiedAction("system", "wait_for_world_hud", reason="loading_or_transition", priority=90)

        if frame.stuck_score >= 0.75 and frame.progress_delta_m <= 0.05:
            return EmbodiedAction(
                "navigation",
                "unstuck_micro_routine",
                (("method", "jump_dash_rescan"),),
                reason="stuck_score_high",
                priority=85,
                expected_claim_type="navigation_arrival",
            )

        if frame.interaction_prompt and (frame.distance_m is None or frame.distance_m <= interact_range_m):
            return EmbodiedAction(
                "interaction",
                "interact_with_prompt",
                (("prompt", frame.interaction_prompt),),
                reason="prompt_in_interact_range",
                priority=80,
                expected_claim_type="ui_screen_transition",
            )

        if frame.target_bbox_norm and frame.target_confidence >= 0.45:
            x1, _y1, x2, _y2 = frame.target_bbox_norm
            center_x = (x1 + x2) / 2.0
            error = center_x - 0.5
            if abs(error) > 0.06:
                return EmbodiedAction(
                    "navigation",
                    "turn_towards_target",
                    (("yaw_error_norm", f"{error:.3f}"), ("target", frame.target_label)),
                    reason="target_visible_off_center",
                    priority=78,
                    expected_claim_type="navigation_arrival",
                )
            if frame.distance_m is not None and frame.distance_m <= interact_range_m:
                if frame.target_kind == "enemy":
                    return EmbodiedAction(
                        "combat",
                        "enter_combat",
                        (("target", frame.target_label),),
                        reason="enemy_in_engagement_range",
                        priority=82,
                        expected_claim_type="combat_target_killed",
                    )
                return EmbodiedAction(
                    "interaction",
                    "interact_with_target",
                    (("target", frame.target_label),),
                    reason="target_centered_in_range",
                    priority=76,
                    expected_claim_type="ui_screen_transition",
                )
            return EmbodiedAction(
                "navigation",
                "approach_visible_target",
                (("target", frame.target_label),),
                reason="target_centered_not_in_range",
                priority=72,
                expected_claim_type="navigation_arrival",
            )

        bearing = _pick_bearing(frame.native_guide_bearing_deg)
        if bearing is not None:
            return EmbodiedAction(
                "navigation",
                "follow_native_guide",
                (("bearing_deg", f"{bearing:.1f}"),),
                reason="native_world_guide_available",
                priority=70,
                expected_claim_type="navigation_arrival",
            )

        bearing = _pick_bearing(frame.minimap_bearing_deg)
        if bearing is not None:
            return EmbodiedAction(
                "navigation",
                "steer_by_minimap",
                (("bearing_deg", f"{bearing:.1f}"),),
                reason="target_not_visible_minimap_marker_available",
                priority=65,
                expected_claim_type="navigation_arrival",
            )

        bearing = _pick_bearing(frame.landmark_bearing_deg)
        if bearing is not None:
            return EmbodiedAction(
                "navigation",
                "navigate_by_landmark",
                (("bearing_deg", f"{bearing:.1f}"),),
                reason="landmark_hint_available",
                priority=55,
                expected_claim_type="navigation_arrival",
            )

        sweep_deg = max(45.0, min(180.0, 360.0 - frame.scan_coverage_deg))
        return EmbodiedAction(
            "navigation",
            "scan_environment",
            (("sweep_deg", f"{sweep_deg:.1f}"),),
            reason="no_target_or_guide_visible",
            priority=45,
            expected_claim_type="generic_unknown",
        )


class CombatModeDetector:
    """Classifies whether the current scene should be handled as combat."""

    def detect(self, frame: NavigationFrame) -> str:
        if frame.screen_state in {"combat", "boss_fight"}:
            return "combat"
        if frame.threats:
            return "combat"
        if frame.target_kind == "enemy" and frame.target_confidence >= 0.4:
            return "combat_ready"
        if frame.screen_state in {"dialog", "dialogue", "cutscene"}:
            return "dialogue"
        return "exploration"


class RealTimeCombatPolicy:
    """Low-latency combat policy that keeps survival above rotation damage."""

    dodge_threshold = 0.62
    low_hp_threshold = 0.30

    def decide(
        self,
        threats: tuple[ThreatSignal, ...],
        team: TeamCombatRuntime,
        *,
        enemy_visible: bool = True,
    ) -> EmbodiedAction:
        severe = sorted(
            (t for t in threats if t.threat_type != "low_hp"),
            key=lambda item: (item.time_to_impact_ms or 9999, -item.severity),
        )
        for threat in severe:
            if threat.severity >= self.dodge_threshold:
                return EmbodiedAction(
                    "combat",
                    "dodge_reflex",
                    (
                        ("threat_type", threat.threat_type),
                        ("time_to_impact_ms", str(threat.time_to_impact_ms)),
                        ("direction_degrees", f"{threat.direction_degrees:.1f}"),
                    ),
                    reason="severe_visual_threat_preempts_rotation",
                    priority=100,
                    expected_claim_type="danger_cleared",
                )

        active = team.active_member()
        if active.hp_pct <= self.low_hp_threshold:
            healer = team.healer()
            if healer is not None and healer.skill_ready:
                return EmbodiedAction(
                    "combat",
                    "switch_and_cast_healer_skill",
                    (("slot", str(healer.slot)),),
                    reason="active_hp_low_healer_skill_ready",
                    priority=95,
                    expected_claim_type="hp_level_match",
                )
            if healer is not None and healer.burst_ready:
                return EmbodiedAction(
                    "combat",
                    "switch_and_cast_healer_burst",
                    (("slot", str(healer.slot)),),
                    reason="active_hp_low_healer_burst_ready",
                    priority=94,
                    expected_claim_type="hp_level_match",
                )
            if team.food_available:
                return EmbodiedAction(
                    "combat",
                    "use_emergency_food",
                    (("slot", str(active.slot)),),
                    reason="active_hp_low_no_healer_cooldown_available",
                    priority=93,
                    expected_claim_type="hp_level_match",
                )
            return EmbodiedAction(
                "combat",
                "retreat_and_reacquire",
                reason="active_hp_low_no_recovery_available",
                priority=92,
                expected_claim_type="generic_unknown",
            )

        if not enemy_visible:
            return EmbodiedAction(
                "combat",
                "reacquire_combat_target",
                reason="combat_mode_without_visible_enemy",
                priority=68,
                expected_claim_type="generic_unknown",
            )

        if active.burst_ready:
            return EmbodiedAction(
                "combat",
                "cast_active_burst",
                (("slot", str(active.slot)),),
                reason="active_burst_ready",
                priority=62,
                expected_claim_type="combat_target_killed",
            )
        if active.skill_ready:
            return EmbodiedAction(
                "combat",
                "cast_active_skill",
                (("slot", str(active.slot)),),
                reason="active_skill_ready",
                priority=58,
                expected_claim_type="combat_target_killed",
            )
        return EmbodiedAction(
            "combat",
            "combo_normal_attack",
            (("slot", str(active.slot)),),
            reason="maintain_damage_while_waiting_cooldowns",
            priority=52,
            expected_claim_type="combat_target_killed",
        )


class DailyCommissionDryRunRuntime:
    """End-to-end dry-run state machine for open-world daily tasks."""

    def __init__(
        self,
        navigator: HybridOpenWorldNavigator | None = None,
        combat_policy: RealTimeCombatPolicy | None = None,
    ) -> None:
        self.navigator = navigator or HybridOpenWorldNavigator()
        self.combat_policy = combat_policy or RealTimeCombatPolicy()
        self.mode_detector = CombatModeDetector()

    def tick_embodied(self, obs: Any) -> EmbodiedAction | None:
        """Integration hook for AgentLoop: produce one EmbodiedAction from a SemanticObservation.

        Returns None if the observation is not suitable for embodied handling
        (e.g., dialogue, menus, loading screens).
        """
        screen_state = getattr(obs, "screen_state", "unknown")
        if screen_state in ("loading", "black_screen", "dialog", "dialogue", "menu", "inventory"):
            return None

        frame = self._obs_to_nav_frame(obs)
        action = self.navigator.decide(frame)
        mode = self.mode_detector.detect(frame)
        if mode == "combat":
            threats = frame.threats
            team = TeamCombatRuntime(
                active_slot=1,
                members=(TeamMemberRuntime(slot=1, role="driver"),),
            )
            return self.combat_policy.decide(threats, team, enemy_visible=frame.target_kind == "enemy")
        return action

    def _obs_to_nav_frame(self, obs: Any) -> NavigationFrame:
        """Convert a SemanticObservation into a NavigationFrame."""
        dt = getattr(obs, "desktop_tree", None)
        ws = getattr(obs, "world_state", None)
        target_label = ""
        target_bbox = None
        target_conf = 0.0
        target_kind = "unknown"
        distance = None

        if dt is not None:
            for node in getattr(dt, "nodes", ()):
                if node.role in ("button", "icon") and node.confidence > target_conf:
                    target_label = node.label
                    target_bbox = node.bbox
                    target_conf = node.confidence

        if ws is not None:
            targets = getattr(ws, "targets", ())
            if targets:
                t = targets[0]
                target_label = target_label or t.label
                target_kind = t.kind
                if t.bbox_norm is not None:
                    # Estimate distance from bbox size: larger bbox = closer
                    bw = abs(t.bbox_norm[2] - t.bbox_norm[0])
                    bh = abs(t.bbox_norm[3] - t.bbox_norm[1])
                    area = bw * bh
                    distance = max(1.0, min(100.0, 25.0 / max(area, 0.001)))

        return NavigationFrame(
            screen_state=getattr(obs, "screen_state", "overworld"),
            target_label=target_label,
            target_bbox_norm=target_bbox,
            target_confidence=target_conf,
            target_kind=target_kind,
            distance_m=distance,
        )

    def run(
        self,
        objectives: tuple[DailyCommissionObjective, ...],
        frames_by_objective: dict[str, tuple[NavigationFrame, ...]],
        team: TeamCombatRuntime,
    ) -> DailyCommissionTrace:
        actions: list[EmbodiedAction] = []
        claims: list[StateDeltaClaim] = []

        self._append(actions, claims, EmbodiedAction("system", "prepare_daily_session", reason="session_start", priority=80))
        self._append(actions, claims, EmbodiedAction("system", "open_quest_list", reason="select_daily_commissions", priority=75))

        for objective in objectives:
            self._append(actions, claims, EmbodiedAction(
                "system",
                "select_daily_commission",
                (("objective_id", objective.objective_id),),
                reason="activate_objective_tracking",
                priority=74,
                expected_claim_type="ui_screen_transition",
            ))
            self._append(actions, claims, EmbodiedAction(
                "navigation",
                "teleport_to_waypoint",
                (("waypoint_id", objective.waypoint_id), ("region", objective.target_region)),
                reason="coarse_reposition_to_commission_area",
                priority=80,
                expected_claim_type="teleport_loaded",
            ))

            frames = frames_by_objective.get(objective.objective_id, ())
            if not frames:
                frames = self._default_frames_for(objective)
            for frame in frames:
                nav_action = self.navigator.decide(frame)
                self._append(actions, claims, nav_action)
                mode = self.mode_detector.detect(frame)
                if mode == "combat" or nav_action.intent == "enter_combat":
                    combat_action = self.combat_policy.decide(
                        frame.threats,
                        team,
                        enemy_visible=frame.target_kind == "enemy" or bool(frame.target_bbox_norm),
                    )
                    self._append(actions, claims, combat_action)

            self._append(actions, claims, self._resolve_objective(objective))
            self._append(actions, claims, EmbodiedAction(
                "loot",
                "collect_commission_rewards",
                (("objective_id", objective.objective_id),),
                reason="post_objective_loot_sweep",
                priority=62,
                expected_claim_type="collection_pickup",
            ))

        self._append(actions, claims, EmbodiedAction(
            "navigation",
            "teleport_to_adventure_guild",
            reason="all_commissions_done_claim_daily_reward",
            priority=80,
            expected_claim_type="teleport_loaded",
        ))
        self._append(actions, claims, EmbodiedAction(
            "dialogue",
            "claim_adventure_guild_daily_reward",
            reason="handle_katheryne_dialog_options_by_text",
            priority=78,
            expected_claim_type="inventory_delta",
        ))
        self._append(actions, claims, EmbodiedAction(
            "reward",
            "refresh_expeditions",
            reason="daily_reward_flow_tail",
            priority=55,
            expected_claim_type="inventory_delta",
        ))
        return DailyCommissionTrace(tuple(actions), tuple(claims), True, "complete")

    def _append(
        self,
        actions: list[EmbodiedAction],
        claims: list[StateDeltaClaim],
        action: EmbodiedAction,
    ) -> None:
        actions.append(action)
        claims.append(_claim_for_action(action))

    def _resolve_objective(self, objective: DailyCommissionObjective) -> EmbodiedAction:
        if objective.objective_type == "combat":
            return EmbodiedAction("combat", "verify_combat_commission_complete", reason="enemy_group_cleared", priority=70, expected_claim_type="combat_target_killed")
        if objective.objective_type == "dialogue":
            return EmbodiedAction("dialogue", "advance_dialogue_and_select_branch", reason="commission_dialogue_flow", priority=66, expected_claim_type="dialogue_advance")
        if objective.objective_type == "puzzle":
            return EmbodiedAction("puzzle", "solve_visual_puzzle_or_escalate", (("hint", objective.puzzle_hint),), reason="puzzle_objective", priority=64, expected_claim_type="generic_unknown")
        return EmbodiedAction("interaction", "complete_world_interaction", reason="noncombat_commission_interaction", priority=64, expected_claim_type="ui_screen_transition")

    def _default_frames_for(self, objective: DailyCommissionObjective) -> tuple[NavigationFrame, ...]:
        if objective.objective_type == "combat":
            return (
                NavigationFrame(target_label=objective.target_label, minimap_bearing_deg=35.0, distance_m=90.0),
                NavigationFrame(target_label=objective.target_label, target_bbox_norm=(0.18, 0.40, 0.28, 0.65), target_confidence=0.72, target_kind="enemy", distance_m=18.0),
                NavigationFrame(
                    target_label=objective.target_label,
                    target_bbox_norm=(0.45, 0.35, 0.55, 0.70),
                    target_confidence=0.82,
                    target_kind="enemy",
                    distance_m=2.5,
                    threats=(ThreatSignal("projectile", 0.82, 10.0, 280, "dry_run_fixture"),),
                ),
            )
        return (
            NavigationFrame(target_label=objective.target_label, minimap_bearing_deg=20.0, distance_m=80.0),
            NavigationFrame(target_label=objective.target_label, target_bbox_norm=(0.46, 0.35, 0.54, 0.70), target_confidence=0.80, distance_m=2.0, interaction_prompt="F"),
        )


def _claim_for_action(action: EmbodiedAction) -> StateDeltaClaim:
    claim_id = f"embodied_{uuid.uuid4().hex[:10]}"
    return StateDeltaClaim(
        claim_id=claim_id,
        delta_description=action.intent,
        expected_state=action.expected_claim_type,
        observed_state=action.expected_claim_type,
        verified=True,
        confidence=0.9 if action.kind != "puzzle" else 0.65,
        attributions=(f"action:{action.intent}",),
        timestamp=time.perf_counter(),
    )


def _pick_bearing(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return value % 360.0
