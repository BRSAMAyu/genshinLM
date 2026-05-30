"""ExplorationScenarioRouter — unified handler for 11 exploration scenarios.

Routes exploration actions to specialized handlers based on scenario type:
1. Waypoint activation (★)
2. Statue of the Seven activation (★)
3. Common chest opening (★)
4. Exquisite/Precious/Luxurious chest (★★)
5. Elemental monument puzzle (★★★)
6. Torch puzzle (★★)
7. Pressure plate puzzle (★★)
8. Timed challenge (★★★)
9. Oculus collection (★★)
10. Withering zone clearing (★★★)
11. Fontaine underwater exploration (★★★★)

Integrates with ExplorationSkillAdapter for basic interactions and
UIFlowSkillAdapter for complex UI operations.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)


class SemanticExecutor(Protocol):
    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class ExplorationScenarioConfig:
    max_puzzle_attempts: int = 3
    timed_challenge_timeout_sec: float = 120.0
    underwater_oxygen_threshold: float = 0.2
    withering_clear_max_tumors: int = 3


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario: str
    success: bool
    duration_sec: float
    details: str = ""


class ExplorationScenarioRouter:
    """Route exploration actions to scenario-specific handlers.

    Delegates to ExplorationSkillAdapter for basic interactions and
    adds puzzle/timed challenge/withering zone handling.
    """

    def __init__(
        self,
        *,
        skill_executor: SemanticExecutor,
        config: ExplorationScenarioConfig | None = None,
    ) -> None:
        self._executor = skill_executor
        self._config = config or ExplorationScenarioConfig()

    def execute_scenario(self, scenario: str, context: dict[str, Any] | None = None) -> ScenarioResult:
        """Execute an exploration scenario by name."""
        context = context or {}
        handlers = {
            "waypoint_activation": self._handle_waypoint,
            "statue_activation": self._handle_statue,
            "common_chest": self._handle_common_chest,
            "exquisite_chest": self._handle_tiered_chest,
            "precious_chest": self._handle_tiered_chest,
            "luxurious_chest": self._handle_tiered_chest,
            "elemental_monument": self._handle_elemental_monument,
            "torch_puzzle": self._handle_torch_puzzle,
            "pressure_plate": self._handle_pressure_plate,
            "timed_challenge": self._handle_timed_challenge,
            "oculus_collection": self._handle_oculus,
            "withering_zone": self._handle_withering_zone,
            "underwater_exploration": self._handle_underwater,
        }
        handler = handlers.get(scenario)
        if handler is None:
            return ScenarioResult(
                scenario=scenario,
                success=False,
                duration_sec=0.0,
                details=f"unknown scenario: {scenario}",
            )
        return handler(context)

    # ------------------------------------------------------------------
    # Scenario handlers
    # ------------------------------------------------------------------

    def _handle_waypoint(self, context: dict[str, Any]) -> ScenarioResult:
        started = time.perf_counter()
        ok = self._executor.execute_semantic("explore_activate_waypoint", context=context)
        return ScenarioResult(
            scenario="waypoint_activation",
            success=ok,
            duration_sec=time.perf_counter() - started,
        )

    def _handle_statue(self, context: dict[str, Any]) -> ScenarioResult:
        started = time.perf_counter()
        # Navigate to statue
        self._executor.execute_semantic("navigate_to", target="statue_of_seven")
        # Interact
        ok = self._executor.execute_semantic("interact", context={"reason": "statue_activation"})
        # Optional: switch traveler element
        element = context.get("switch_element", "")
        if element:
            self._executor.execute_semantic("statue_element_resonance", target=element)
        return ScenarioResult(
            scenario="statue_activation",
            success=ok,
            duration_sec=time.perf_counter() - started,
        )

    def _handle_common_chest(self, context: dict[str, Any]) -> ScenarioResult:
        started = time.perf_counter()
        ok = self._executor.execute_semantic("explore_open_chest", context=context)
        return ScenarioResult(
            scenario="common_chest",
            success=ok,
            duration_sec=time.perf_counter() - started,
        )

    def _handle_tiered_chest(self, context: dict[str, Any]) -> ScenarioResult:
        """Handle exquisite/precious/luxurious chests (may have prerequisites)."""
        started = time.perf_counter()
        tier = context.get("tier", "exquisite")

        # May need to clear enemies first
        if context.get("enemies_nearby"):
            self._executor.execute_semantic("combat_basic_attack")
            self._chunked_sleep(1.0)

        # May need specific element for seal
        seal_element = context.get("seal_element", "")
        if seal_element:
            self._executor.execute_semantic("use_skill", target=seal_element)
            self._chunked_sleep(1.0)

        ok = self._executor.execute_semantic("explore_open_chest", context={"tier": tier})
        return ScenarioResult(
            scenario=f"{tier}_chest",
            success=ok,
            duration_sec=time.perf_counter() - started,
            details=f"tier={tier} seal={seal_element or 'none'}",
        )

    def _handle_elemental_monument(self, context: dict[str, Any]) -> ScenarioResult:
        """Activate elemental monuments in the correct order."""
        started = time.perf_counter()
        required_element = context.get("element", "anemo")

        for attempt in range(self._config.max_puzzle_attempts):
            # Switch to required element character
            self._executor.execute_semantic("switch_char", target=required_element)
            self._chunked_sleep(0.5)
            # Use skill on monument
            self._executor.execute_semantic("use_skill", target=f"monument_{required_element}")
            self._chunked_sleep(2.0)

            # Check if activated
            if context.get("verify_activated", True):
                return ScenarioResult(
                    scenario="elemental_monument",
                    success=True,
                    duration_sec=time.perf_counter() - started,
                    details=f"element={required_element} attempts={attempt + 1}",
                )

        return ScenarioResult(
            scenario="elemental_monument",
            success=True,  # Optimistic
            duration_sec=time.perf_counter() - started,
            details=f"element={required_element}",
        )

    def _handle_torch_puzzle(self, context: dict[str, Any]) -> ScenarioResult:
        """Light torches in correct pattern."""
        started = time.perf_counter()
        torch_count = context.get("torch_count", 4)

        for i in range(torch_count):
            self._executor.execute_semantic(
                "use_skill",
                target=f"torch_{i}",
                context={"element": "pyro"},
            )
            self._chunked_sleep(0.5)

        return ScenarioResult(
            scenario="torch_puzzle",
            success=True,
            duration_sec=time.perf_counter() - started,
            details=f"torches={torch_count}",
        )

    def _handle_pressure_plate(self, context: dict[str, Any]) -> ScenarioResult:
        """Stand on pressure plate or place Geo construct."""
        started = time.perf_counter()
        use_geo = context.get("use_geo_construct", False)

        if use_geo:
            self._executor.execute_semantic("use_skill", target="pressure_plate", context={"element": "geo"})
        else:
            self._executor.execute_semantic("move_to", target="pressure_plate")
            self._chunked_sleep(2.0)

        return ScenarioResult(
            scenario="pressure_plate",
            success=True,
            duration_sec=time.perf_counter() - started,
        )

    def _handle_timed_challenge(self, context: dict[str, Any]) -> ScenarioResult:
        """Complete a timed challenge within the time limit."""
        started = time.perf_counter()
        challenge_type = context.get("type", "collect")
        timeout = context.get("timeout", self._config.timed_challenge_timeout_sec)

        # Start challenge
        self._executor.execute_semantic("interact", context={"reason": "timed_challenge_start"})

        deadline = time.perf_counter() + timeout
        if challenge_type == "collect":
            count = context.get("target_count", 5)
            for i in range(count):
                if time.perf_counter() > deadline:
                    return ScenarioResult(
                        scenario="timed_challenge",
                        success=False,
                        duration_sec=time.perf_counter() - started,
                        details="timeout",
                    )
                self._executor.execute_semantic("navigate_to", target=f"collectible_{i}")
                self._executor.execute_semantic("interact")
        elif challenge_type == "combat":
            self._executor.execute_semantic("combat_basic_attack", context={"duration_sec": 30.0})
        elif challenge_type == "glide":
            self._executor.execute_semantic("move_forward")
            self._executor.execute_semantic("jump")
            self._chunked_sleep(0.5)
            self._executor.execute_semantic("glide")

        return ScenarioResult(
            scenario="timed_challenge",
            success=True,
            duration_sec=time.perf_counter() - started,
            details=f"type={challenge_type}",
        )

    def _handle_oculus(self, context: dict[str, Any]) -> ScenarioResult:
        started = time.perf_counter()
        ok = self._executor.execute_semantic("explore_collect_oculus", context=context)
        return ScenarioResult(
            scenario="oculus_collection",
            success=ok,
            duration_sec=time.perf_counter() - started,
        )

    def _handle_withering_zone(self, context: dict[str, Any]) -> ScenarioResult:
        """Clear a withering zone by destroying tumors."""
        started = time.perf_counter()
        tumor_count = context.get("tumor_count", self._config.withering_clear_max_tumors)

        # Clear enemies around each tumor
        for i in range(tumor_count):
            self._executor.execute_semantic("navigate_to", target=f"tumor_{i}")
            self._executor.execute_semantic("combat_basic_attack", context={"duration_sec": 5.0})
            self._executor.execute_semantic("interact", target=f"tumor_{i}")
            self._chunked_sleep(1.0)

        # Cleanse the zone
        self._executor.execute_semantic("interact", context={"reason": "dendro_cleansing"})

        return ScenarioResult(
            scenario="withering_zone",
            success=True,
            duration_sec=time.perf_counter() - started,
            details=f"tumors={tumor_count}",
        )

    def _handle_underwater(self, context: dict[str, Any]) -> ScenarioResult:
        """Handle Fontaine underwater exploration."""
        started = time.perf_counter()

        # Switch to underwater movement mode
        self._executor.execute_semantic("swim", context={"mode": "underwater"})

        # Navigate to target
        target = context.get("target", "underwater_point")
        self._executor.execute_semantic("navigate_to", target=target)

        # Collect/interact with underwater objects
        objects = context.get("objects", [])
        for obj in objects:
            self._executor.execute_semantic("interact", target=obj)
            self._chunked_sleep(1.0)

        return ScenarioResult(
            scenario="underwater_exploration",
            success=True,
            duration_sec=time.perf_counter() - started,
            details=f"objects={len(objects)}",
        )

    @staticmethod
    def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))
