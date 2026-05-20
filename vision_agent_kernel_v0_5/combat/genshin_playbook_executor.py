from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from combat.genshin_combat_planner import CombatAction, CombatPlaybook, PriorityTrigger


class PlaybookState(Enum):
    IDLE = "idle"
    EXECUTING = "executing"
    WAITING_TRIGGER = "waiting_trigger"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PlaybookSnapshot:
    playbook_id: str
    state: str
    current_step_index: int
    rotation_position: int
    elapsed_ms: float
    interrupts_handled: int


class PlaybookExecutor:
    """Execute a CombatPlaybook step-by-step with interrupt handling."""

    def __init__(self) -> None:
        self._state = PlaybookState.IDLE
        self._current_step = 0
        self._rotation_pos = 0
        self._elapsed_ms = 0.0
        self._interrupts = 0
        self._playbook: CombatPlaybook | None = None

    def start(self, playbook: CombatPlaybook) -> None:
        self._playbook = playbook
        self._state = PlaybookState.EXECUTING
        self._current_step = 0
        self._rotation_pos = 0
        self._elapsed_ms = 0.0
        self._interrupts = 0

    def tick(
        self,
        dt_ms: float,
        danger_signals: dict[str, float] | None = None,
        cooldown_states: dict[str, bool] | None = None,
        hp_ratios: list[float] | None = None,
    ) -> CombatAction | None:
        if self._state not in (PlaybookState.EXECUTING, PlaybookState.WAITING_TRIGGER):
            return None

        self._elapsed_ms += dt_ms

        interrupt_action = self.check_interrupts(
            danger_signals or {},
            hp_ratios or [1.0, 1.0, 1.0, 1.0],
            cooldown_states or {},
        )
        if interrupt_action is not None:
            self._state = PlaybookState.INTERRUPTED
            self._interrupts += 1
            return interrupt_action

        if self._playbook is None:
            self._state = PlaybookState.FAILED
            return None

        rotation = self._playbook.default_rotation
        if not rotation:
            self._state = PlaybookState.COMPLETED
            return None

        while self._current_step < len(rotation):
            action = rotation[self._current_step]
            context = self._build_context(
                danger_signals or {},
                hp_ratios or [1.0, 1.0, 1.0, 1.0],
                cooldown_states or {},
            )
            if action.condition and not self._evaluate_condition(action.condition, context):
                self._current_step += 1
                continue
            self._rotation_pos = self._current_step
            self._current_step += 1
            if self._current_step >= len(rotation):
                self._current_step = 0
            return action

        self._current_step = 0
        return None

    def check_interrupts(
        self,
        danger_signals: dict[str, float],
        hp_ratios: list[float],
        cooldown_states: dict[str, bool],
    ) -> CombatAction | None:
        if self._playbook is None:
            return None

        context = self._build_context(danger_signals, hp_ratios, cooldown_states)
        active_triggers = sorted(
            self._playbook.priority_triggers, key=lambda t: t.priority,
        )
        for trigger in active_triggers:
            if not trigger.interrupt:
                continue
            if self._evaluate_condition(trigger.condition, context):
                char = self._pick_character_for_trigger(trigger, hp_ratios)
                return CombatAction(
                    action=trigger.action,
                    character=char,
                    priority=trigger.priority,
                )
        return None

    def snapshot(self) -> PlaybookSnapshot:
        pb_id = self._playbook.playbook_id if self._playbook else ""
        return PlaybookSnapshot(
            playbook_id=pb_id,
            state=self._state.value,
            current_step_index=self._current_step,
            rotation_position=self._rotation_pos,
            elapsed_ms=self._elapsed_ms,
            interrupts_handled=self._interrupts,
        )

    def restore(self, snapshot: PlaybookSnapshot) -> None:
        self._current_step = snapshot.current_step_index
        self._rotation_pos = snapshot.rotation_position
        self._elapsed_ms = snapshot.elapsed_ms
        self._interrupts = snapshot.interrupts_handled
        self._state = PlaybookState(snapshot.state)

    @property
    def state(self) -> PlaybookState:
        return self._state

    def _evaluate_condition(self, condition: str, context: dict) -> bool:
        if not condition or condition == "always":
            return True

        if condition == "skill_e_ready":
            return context.get("skill_e_ready", False)
        if condition == "energy_full":
            return context.get("energy_full", False)
        if condition == "hp < 0.3":
            return context.get("active_hp", 1.0) < 0.3
        if condition == "danger > 0.7":
            return context.get("danger", 0.0) > 0.7
        if condition == "stamina < 0.2":
            return context.get("stamina", 1.0) < 0.2

        if ">" in condition:
            parts = condition.split(">")
            if len(parts) == 2:
                key = parts[0].strip()
                threshold = float(parts[1].strip())
                return float(context.get(key, 0.0)) > threshold

        if "<" in condition:
            parts = condition.split("<")
            if len(parts) == 2:
                key = parts[0].strip()
                threshold = float(parts[1].strip())
                return float(context.get(key, 0.0)) < threshold

        return False

    @staticmethod
    def _build_context(
        danger_signals: dict[str, float],
        hp_ratios: list[float],
        cooldown_states: dict[str, bool],
    ) -> dict:
        overall_danger = danger_signals.get("overall_danger", 0.0)
        if overall_danger == 0.0:
            overall_danger = max(danger_signals.values()) if danger_signals else 0.0

        active_hp = hp_ratios[0] if hp_ratios else 1.0

        return {
            "danger": overall_danger,
            "active_hp": active_hp,
            "stamina": 1.0,
            "skill_e_ready": cooldown_states.get("skill_e", True),
            "energy_full": cooldown_states.get("q_burst", False),
        }

    @staticmethod
    def _pick_character_for_trigger(
        trigger: PriorityTrigger, hp_ratios: list[float],
    ) -> int:
        if trigger.action == "switch":
            if hp_ratios:
                best_idx = max(range(len(hp_ratios)), key=lambda i: hp_ratios[i])
                return best_idx + 1
            return 2
        return 1
