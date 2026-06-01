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

Prerequisite auto-detection: Before executing tiered chests, the router
auto-detects enemies nearby (combat state) and elemental seals (via
ElementalChestDetector + combat perception) to populate context.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import numpy as np

log = logging.getLogger(__name__)


class SemanticExecutor(Protocol):
    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool: ...


FrameSupplier = Callable[[], np.ndarray | None]


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

    Supports optional frame supplier for prerequisite auto-detection
    (enemies nearby, elemental seals on chests).
    """

    def __init__(
        self,
        *,
        skill_executor: SemanticExecutor,
        config: ExplorationScenarioConfig | None = None,
        frame_supplier: FrameSupplier | None = None,
        elemental_chest_detector: Any | None = None,
        combat_detector: Any | None = None,
        puzzle_handler: Any | None = None,
    ) -> None:
        self._executor = skill_executor
        self._config = config or ExplorationScenarioConfig()
        self._frame_supplier = frame_supplier
        self._elemental_detector = elemental_chest_detector
        self._combat_detector = combat_detector
        self._puzzle_handler = puzzle_handler

    def execute_scenario(self, scenario: str, context: dict[str, Any] | None = None) -> ScenarioResult:
        """Execute an exploration scenario by name with auto prerequisite detection."""
        context = dict(context or {})

        # Auto-detect prerequisites for tiered chests
        if scenario in ("exquisite_chest", "precious_chest", "luxurious_chest"):
            context = self._auto_detect_prerequisites(context)

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
    # Prerequisite auto-detection
    # ------------------------------------------------------------------

    def _auto_detect_prerequisites(self, context: dict[str, Any]) -> dict[str, Any]:
        """Auto-detect combat enemies and elemental seals near chest.

        Only populates MISSING keys — preserves explicitly-passed context values.
        Called automatically before tiered chest handlers.
        """
        frame = self._get_frame()
        if frame is None:
            return context

        # 1. Combat enemy detection (only if not already specified)
        if "enemies_nearby" not in context:
            if self._combat_detector is not None:
                try:
                    in_combat = self._combat_detector.is_in_combat(frame)
                    context["enemies_nearby"] = in_combat
                except Exception as exc:
                    log.debug("[ScenarioRouter] combat detection failed: %s", exc)

        # 2. Elemental seal detection (only if not already specified)
        if "seal_element" not in context:
            if self._elemental_detector is not None:
                try:
                    result = self._elemental_detector.detect(frame)
                    if result.elemental_barrier and result.required_elements:
                        elem = result.required_elements[0]
                        elem_name = elem.name.lower() if hasattr(elem, "name") else str(elem)
                        context["seal_element"] = elem_name
                        context["seal_confidence"] = result.confidence
                        log.info("[ScenarioRouter] detected seal: %s (conf=%.2f)",
                                 elem_name, result.confidence)
                except Exception as exc:
                    log.debug("[ScenarioRouter] elemental detection failed: %s", exc)
        elif "seal_confidence" not in context:
            # User provided seal_element explicitly — set high confidence
            context["seal_confidence"] = 0.95

        return context

    def _get_frame(self) -> np.ndarray | None:
        """Grab current frame if frame_supplier is available."""
        if self._frame_supplier is None:
            return None
        try:
            frame = self._frame_supplier()
            return frame
        except Exception:
            return None

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
        self._executor.execute_semantic("navigate_to", target="statue_of_seven")
        ok = self._executor.execute_semantic("interact", context={"reason": "statue_activation"})
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
        """Handle exquisite/precious/luxurious chests with auto-detected prerequisites."""
        started = time.perf_counter()
        tier = context.get("tier", "exquisite")
        seal_element = context.get("seal_element", "")
        seal_confidence = context.get("seal_confidence", 0.0)

        # Clear enemies first if detected
        if context.get("enemies_nearby"):
            self._executor.execute_semantic("combat_basic_attack")
            self._chunked_sleep(2.0)

        # Apply elemental seal if detected (with minimum confidence threshold)
        if seal_element and seal_confidence >= 0.5:
            self._executor.execute_semantic("use_skill", target=seal_element)
            self._chunked_sleep(1.0)

        ok = self._executor.execute_semantic("explore_open_chest", context={"tier": tier})
        return ScenarioResult(
            scenario=f"{tier}_chest",
            success=ok,
            duration_sec=time.perf_counter() - started,
            details=f"tier={tier} seal={seal_element or 'none'} enemies={context.get('enemies_nearby')}",
        )

    def _handle_elemental_monument(self, context: dict[str, Any]) -> ScenarioResult:
        """Activate elemental monuments using PuzzleHandler for VLM-guided planning."""
        started = time.perf_counter()
        required_element = context.get("element", "anemo")

        # Use PuzzleHandler if available for VLM-guided element detection
        if self._puzzle_handler is not None and self._get_frame() is not None:
            from interaction.puzzle_handler import PuzzleType

            frame = self._get_frame()
            solution = self._puzzle_handler.plan_solution(PuzzleType.ELEMENTAL_MONUMENT, frame)
            if solution.actions:
                state = self._puzzle_handler.execute_solution(solution)
                return ScenarioResult(
                    scenario="elemental_monument",
                    success=state.completed,
                    duration_sec=time.perf_counter() - started,
                    details=f"element={required_element} confidence={solution.confidence:.2f}",
                )

        # Fallback: manual sequence
        for attempt in range(self._config.max_puzzle_attempts):
            self._executor.execute_semantic("switch_char", target=required_element)
            self._chunked_sleep(0.5)
            self._executor.execute_semantic("use_skill", target=f"monument_{required_element}")
            self._chunked_sleep(2.0)

            if context.get("verify_activated", True):
                return ScenarioResult(
                    scenario="elemental_monument",
                    success=True,
                    duration_sec=time.perf_counter() - started,
                    details=f"element={required_element} attempts={attempt + 1}",
                )

        return ScenarioResult(
            scenario="elemental_monument",
            success=True,
            duration_sec=time.perf_counter() - started,
            details=f"element={required_element}",
        )

    def _handle_torch_puzzle(self, context: dict[str, Any]) -> ScenarioResult:
        """Light torches using PuzzleHandler for pattern recognition."""
        started = time.perf_counter()
        torch_count = context.get("torch_count", 4)

        if self._puzzle_handler is not None and self._get_frame() is not None:
            from interaction.puzzle_handler import PuzzleType

            frame = self._get_frame()
            solution = self._puzzle_handler.plan_solution(PuzzleType.TORCH, frame)
            if solution.actions:
                state = self._puzzle_handler.execute_solution(solution)
                return ScenarioResult(
                    scenario="torch_puzzle",
                    success=state.completed,
                    duration_sec=time.perf_counter() - started,
                    details=f"torches={torch_count} confidence={solution.confidence:.2f}",
                )

        # Fallback: hardcoded pyro sequence
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
        """Handle pressure plate using PuzzleHandler for multi-plate coordination."""
        started = time.perf_counter()
        use_geo = context.get("use_geo_construct", False)

        if self._puzzle_handler is not None and self._get_frame() is not None:
            from interaction.puzzle_handler import PuzzleType

            frame = self._get_frame()
            solution = self._puzzle_handler.plan_solution(PuzzleType.PRESSURE_PLATE, frame)
            if solution.actions:
                state = self._puzzle_handler.execute_solution(solution)
                return ScenarioResult(
                    scenario="pressure_plate",
                    success=state.completed,
                    duration_sec=time.perf_counter() - started,
                    details=f"confidence={solution.confidence:.2f}",
                )

        # Fallback
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
        """Complete a timed challenge using PuzzleHandler for path optimization."""
        started = time.perf_counter()
        challenge_type = context.get("type", "collect")
        timeout = context.get("timeout", self._config.timed_challenge_timeout_sec)

        # Use PuzzleHandler if available for optimized solution
        if self._puzzle_handler is not None and self._get_frame() is not None:
            from interaction.puzzle_handler import PuzzleType

            frame = self._get_frame()
            solution = self._puzzle_handler.plan_solution(PuzzleType.TIMED_CHALLENGE, frame)
            if solution.actions:
                state = self._puzzle_handler.execute_solution(solution)
                return ScenarioResult(
                    scenario="timed_challenge",
                    success=state.completed,
                    duration_sec=time.perf_counter() - started,
                    details=f"type={challenge_type} confidence={solution.confidence:.2f}",
                )

        # Fallback: basic timed challenge sequence
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

        if self._puzzle_handler is not None and self._get_frame() is not None:
            from interaction.puzzle_handler import PuzzleType

            frame = self._get_frame()
            solution = self._puzzle_handler.plan_solution(PuzzleType.WITHERING_ZONE, frame)
            if solution.actions:
                state = self._puzzle_handler.execute_solution(solution)
                return ScenarioResult(
                    scenario="withering_zone",
                    success=state.completed,
                    duration_sec=time.perf_counter() - started,
                    details=f"tumors={tumor_count} confidence={solution.confidence:.2f}",
                )

        # Fallback: manual tumor destruction sequence
        for i in range(tumor_count):
            self._executor.execute_semantic("navigate_to", target=f"tumor_{i}")
            self._executor.execute_semantic("combat_basic_attack", context={"duration_sec": 5.0})
            self._executor.execute_semantic("interact", target=f"tumor_{i}")
            self._chunked_sleep(1.0)

        self._executor.execute_semantic("interact", context={"reason": "dendro_cleansing"})

        return ScenarioResult(
            scenario="withering_zone",
            success=True,
            duration_sec=time.perf_counter() - started,
            details=f"tumors={tumor_count}",
        )

    def _handle_underwater(self, context: dict[str, Any]) -> ScenarioResult:
        """Handle Fontaine underwater exploration with oxygen management."""
        started = time.perf_counter()
        config = self._config

        self._executor.execute_semantic("swim", context={"mode": "underwater"})

        oxygen_ratio = 1.0
        objects_collected = 0
        oxygen_refills = 0
        targets = context.get("objects", [])

        for obj in targets:
            if oxygen_ratio < config.underwater_oxygen_threshold:
                self._executor.execute_semantic("surface", context={"reason": "oxygen_low"})
                self._executor.execute_semantic("dive", context={"reason": "resume_underwater"})
                oxygen_ratio = 1.0
                oxygen_refills += 1

            depth = context.get("depth", 0.0)
            self._executor.execute_semantic(
                "navigate_to", target=obj,
                context={"depth": depth, "underwater": True},
            )

            ok = self._executor.execute_semantic("interact", target=obj)
            if ok:
                objects_collected += 1

            oxygen_ratio = max(0.0, oxygen_ratio - 0.15)

        if not targets:
            target = context.get("target", "underwater_point")
            self._executor.execute_semantic("navigate_to", target=target)

        return ScenarioResult(
            scenario="underwater_exploration",
            success=True,
            duration_sec=time.perf_counter() - started,
            details=f"objects={objects_collected} refills={oxygen_refills}",
        )

    @staticmethod
    def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))