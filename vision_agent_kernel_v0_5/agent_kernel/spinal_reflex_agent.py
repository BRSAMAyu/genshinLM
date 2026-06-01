"""SpinalReflexAgentImpl — concrete L1-L2 SpinalReflexAgent.

Wraps the threat evaluation and reflex command pipeline.
L1-L2 runs at 50Hz, providing:
- Threat evaluation from frame data
- Reflex command generation (dodge, heal, combo, switch)
- Combo state tracking
"""
from __future__ import annotations

import logging
import time

from agent_kernel.protocols import SpinalReflexAgent as SpinalReflexAgentProtocol
from agent_kernel.types import CombatCommand, ThreatSignal

log = logging.getLogger(__name__)


class SpinalReflexAgentImpl(SpinalReflexAgentProtocol):
    """Concrete L1-L2 SpinalReflexAgent.

    Provides rule-based threat evaluation and reflex command generation.
    In production, uses YOLO detection for real-time threat assessment.

    Usage:
        agent = SpinalReflexAgentImpl()
        threats = agent.evaluate_threats(frame)
        cmd = agent.tick_combat_reflex(threats, combo_step)
    """

    # Threat severity thresholds
    _DODGE_THRESHOLD: float = 0.7
    _HEAL_HP_RATIO: float = 0.3
    _DANGER_TO_REFLEX: dict[str, str] = {
        "projectile": "dodge",
        "telegraph_aoe": "dash",
        "boss_animation_charge": "dodge",
        "low_hp": "heal_emergency",
    }

    def __init__(
        self,
        combo_length: int = 5,
        dodge_cooldown_sec: float = 0.5,
    ) -> None:
        self._combo_step: int = 0
        self._combo_length = combo_length
        self._last_dodge_time: float = 0.0
        self._dodge_cooldown = dodge_cooldown_sec
        self._character_index: int = 1

    def evaluate_threats(self, latest_frame: object) -> list[ThreatSignal]:
        """Evaluate current frame for threats.

        In production, uses YOLO detection. This fallback extracts
        threat signals from frame metadata or returns empty.
        """
        if latest_frame is None:
            return []

        # If frame is a dict with threat info, extract it
        if isinstance(latest_frame, dict):
            threats: list[ThreatSignal] = []
            danger = latest_frame.get("danger_score", 0.0)
            if danger > self._DODGE_THRESHOLD:
                threats.append(ThreatSignal(
                    threat_type=latest_frame.get("threat_type", "projectile"),
                    severity=danger,
                    direction_degrees=latest_frame.get("direction", 0.0),
                    time_to_impact_ms=latest_frame.get("time_to_impact_ms", 500),
                ))
            hp_ratios = latest_frame.get("hp_ratios", [])
            if hp_ratios and min(hp_ratios) < self._HEAL_HP_RATIO:
                threats.append(ThreatSignal(
                    threat_type="low_hp",
                    severity=1.0 - min(hp_ratios),
                    source="hp_monitor",
                ))
            return threats

        return []

    def tick_combat_reflex(
        self,
        threats: list[ThreatSignal],
        current_combo_step: int,
    ) -> CombatCommand | None:
        """Generate a combat reflex command based on threats and combo state."""
        self._combo_step = current_combo_step
        now = time.perf_counter()

        # Priority 1: React to critical threats
        for threat in threats:
            if threat.severity >= self._DODGE_THRESHOLD:
                reflex = self._DANGER_TO_REFLEX.get(threat.threat_type, "dodge")
                if reflex == "dodge" and (now - self._last_dodge_time) < self._dodge_cooldown:
                    continue
                if reflex == "dodge":
                    self._last_dodge_time = now
                log.info("[L1-L2] Reflex: %s due to %s (severity=%.2f)",
                         reflex, threat.threat_type, threat.severity)
                return CombatCommand(
                    reflex_action=reflex,
                    target_character_index=self._character_index,
                    reason=f"Threat: {threat.threat_type} severity={threat.severity:.2f}",
                )

        # Priority 2: Continue combo
        if self._combo_step < self._combo_length:
            self._combo_step += 1
            return CombatCommand(
                reflex_action="combo_normal_attack",
                target_character_index=self._character_index,
                reason=f"Combo step {self._combo_step}/{self._combo_length}",
            )

        # Priority 3: Use skill if combo exhausted
        self._combo_step = 0
        return CombatCommand(
            reflex_action="cast_skill_e",
            target_character_index=self._character_index,
            reason="Combo reset — cast skill",
        )

    @property
    def combo_step(self) -> int:
        return self._combo_step

    def set_character(self, index: int) -> None:
        self._character_index = index
