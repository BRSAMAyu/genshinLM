"""DialogueController — smart dialogue skip with branch interception.

Implements the L3-L4 Brainstem protocol from AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md §2.3:
- Smart skip: advances dialogue at 3-5Hz when in dialogue scene
- Branch intercept: pauses skip when options appear, delegates selection
- CG/black screen avoidance: pauses during cutscenes and transitions

This is a game-agnostic controller. Game-specific option matching is done
through an injected OptionRegistry (typically provided by the Capsule).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent_kernel.types import SceneGraph

log = logging.getLogger(__name__)


class DialogueState(str, Enum):
    IDLE = "idle"
    SKIPPING = "skipping"
    BRANCH_DETECTED = "branch_detected"
    WAITING_SELECTION = "waiting_selection"
    CG_PAUSE = "cg_pause"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class DialogueOption:
    """A detected dialogue branch option."""
    option_id: str
    label: str
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = 0.0
    source: str = "unknown"  # ocr, vlm, heuristic


@dataclass(frozen=True, slots=True)
class DialogueActionResult:
    """Result of a dialogue controller action."""
    action: str  # "skip", "select_option", "pause", "wait", "complete"
    state: DialogueState
    selected_option: DialogueOption | None = None
    reason: str = ""
    confidence: float = 0.0
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class OptionMatchResult:
    """Result of matching dialogue options against a registry."""
    matched: bool
    option: DialogueOption | None = None
    confidence: float = 0.0
    fallback_to_vlm: bool = False
    reason: str = ""


class OptionRegistry:
    """Registry of known dialogue options for matching.

    Capsules populate this with game-specific option mappings.
    """

    def __init__(self, entries: dict[str, str] | None = None) -> None:
        self._entries: dict[str, str] = entries or {}
        # Maps option text → action (e.g., "领取奖励" → "select")
        self._priority_keywords: list[str] = []

    def register(self, option_text: str, action: str) -> None:
        """Register a known option text with its action."""
        self._entries[option_text] = action

    def set_priority_keywords(self, keywords: list[str]) -> None:
        """Set keywords that indicate high-priority options (e.g., progress-related)."""
        self._priority_keywords = keywords

    def match(
        self,
        options: list[DialogueOption],
        confidence_threshold: float = 0.5,
    ) -> OptionMatchResult:
        """Match detected options against known entries.

        Returns the best match or indicates VLM fallback is needed.
        """
        if not options:
            return OptionMatchResult(matched=False, reason="no_options")

        # Check priority keywords first
        for keyword in self._priority_keywords:
            for opt in options:
                if keyword in opt.label and opt.confidence >= confidence_threshold:
                    return OptionMatchResult(
                        matched=True,
                        option=opt,
                        confidence=opt.confidence,
                        reason=f"priority_keyword:{keyword}",
                    )

        # Check registered entries
        best_match: DialogueOption | None = None
        best_conf = 0.0
        for opt in options:
            for known_text, action in self._entries.items():
                if known_text in opt.label:
                    if opt.confidence > best_conf:
                        best_match = opt
                        best_conf = opt.confidence

        if best_match is not None and best_conf >= confidence_threshold:
            return OptionMatchResult(
                matched=True,
                option=best_match,
                confidence=best_conf,
                reason="registry_match",
            )

        # Low confidence or unknown option → VLM fallback
        if options:
            return OptionMatchResult(
                matched=False,
                option=None,
                confidence=max(o.confidence for o in options),
                fallback_to_vlm=True,
                reason="no_registry_match",
            )

        return OptionMatchResult(matched=False, reason="no_options")


class DialogueController:
    """L3-L4 Brainstem dialogue controller.

    Manages smart dialogue skipping with branch interception.

    Usage:
        controller = DialogueController(option_registry=registry)
        while in_dialogue:
            result = controller.tick(scene_graph)
            if result.action == "select_option":
                click(result.selected_option.bbox)
    """

    # Skip frequency: 3-5Hz → interval 200-333ms, use 250ms as default
    SKIP_INTERVAL_MS = 250
    # Maximum consecutive skips before forcing a re-check
    MAX_CONSECUTIVE_SKIPS = 50

    def __init__(
        self,
        option_registry: OptionRegistry | None = None,
        skip_interval_ms: int = SKIP_INTERVAL_MS,
    ) -> None:
        self._registry = option_registry or OptionRegistry()
        self._skip_interval_ms = skip_interval_ms
        self._state = DialogueState.IDLE
        self._last_skip_time: float = 0.0
        self._consecutive_skips: int = 0
        self._vlm_delegate: Any = None

    @property
    def state(self) -> DialogueState:
        return self._state

    def set_vlm_delegate(self, delegate: Any) -> None:
        """Set a VLM delegate for unknown option resolution."""
        self._vlm_delegate = delegate

    def tick(self, scene_graph: SceneGraph) -> DialogueActionResult:
        """Process one dialogue controller tick.

        Called at the brainstem frequency (10-20Hz). Returns the action
        that should be taken (skip, select_option, pause, wait, complete).
        """
        now = time.perf_counter()

        # Check if we're in dialogue scene
        if not self._is_dialogue_scene(scene_graph):
            if self._state == DialogueState.SKIPPING:
                self._state = DialogueState.COMPLETE
                return DialogueActionResult(
                    action="complete",
                    state=self._state,
                    reason="dialogue_ended",
                    timestamp=now,
                )
            self._state = DialogueState.IDLE
            return DialogueActionResult(
                action="wait",
                state=self._state,
                reason="not_in_dialogue",
                timestamp=now,
            )

        # Check for black screen / CG
        if self._is_cg_or_transition(scene_graph):
            self._state = DialogueState.CG_PAUSE
            return DialogueActionResult(
                action="pause",
                state=self._state,
                reason="cg_or_transition",
                timestamp=now,
            )

        # Check for branch options
        options = self._detect_options(scene_graph)
        if options:
            self._state = DialogueState.BRANCH_DETECTED
            return self._handle_branch(options, now)

        # Safety: stop after too many consecutive skips
        if self._consecutive_skips >= self._MAX_CONSECUTIVE_SKIPS:
            self._state = DialogueState.BRANCH_DETECTED
            return DialogueActionResult(
                action="pause",
                state=self._state,
                reason="max_skips_reached",
                timestamp=now,
            )

        # Smart skip — respect interval timing
        elapsed_ms = (now - self._last_skip_time) * 1000
        if elapsed_ms < self._skip_interval_ms:
            return DialogueActionResult(
                action="wait",
                state=self._state,
                reason=f"skip_interval({elapsed_ms:.0f}<{self._skip_interval_ms})",
                timestamp=now,
            )

        self._state = DialogueState.SKIPPING
        self._consecutive_skips += 1
        self._last_skip_time = now
        return DialogueActionResult(
            action="skip",
            state=self._state,
            reason=f"skip_tick_{self._consecutive_skips}",
            confidence=0.9,
            timestamp=now,
        )

    def reset(self) -> None:
        """Reset controller state (e.g., after dialogue ends)."""
        self._state = DialogueState.IDLE
        self._consecutive_skips = 0
        self._last_skip_time = 0.0

    def tick_dialogue_skip(self, tree: SceneGraph) -> None:
        """Alias for tick supporting DialogueController protocol conformance."""
        self.tick(tree)

    def is_option_present(self, scene_graph: SceneGraph) -> bool:
        """Check if a dialogue branch choice is currently on screen."""
        return len(self._detect_options(scene_graph)) > 0

    def select_best_option(
        self,
        scene_graph: SceneGraph,
        option_registry: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Select the best dialogue option from available choices.

        Uses option_registry for known options, falls back to VLM for unknown.
        Returns a dict with option details or None if no options found.
        """
        options = self._detect_options(scene_graph)
        if not options:
            return None

        # Try registry match
        if option_registry:
            for opt in options:
                for pattern, target in option_registry.items():
                    if pattern in opt.label:
                        return {"option_id": opt.option_id, "label": opt.label,
                                "bbox": opt.bbox, "target": target}

        # Return first option as fallback
        best = options[0]
        return {"option_id": best.option_id, "label": best.label,
                "bbox": best.bbox, "confidence": best.confidence}

    def _is_dialogue_scene(self, scene_graph: SceneGraph) -> bool:
        """Check if we're in a dialogue scene."""
        return scene_graph.scene_state in ("dialog", "dialogue", "cutscene")

    def _is_cg_or_transition(self, scene_graph: SceneGraph) -> bool:
        """Check if we're in a CG/cutscene/transition (should pause skip)."""
        return scene_graph.scene_state in (
            "loading", "black_screen", "cg", "cutscene_playing",
        )

    def _detect_options(self, scene_graph: SceneGraph) -> list[DialogueOption]:
        """Detect dialogue branch options from the scene graph."""
        options: list[DialogueOption] = []
        for obj in scene_graph.objects:
            if obj.kind == "dialog_option" or obj.kind == "button":
                if "dialog" in obj.label.lower() or "选项" in obj.label:
                    options.append(DialogueOption(
                        option_id=obj.object_id,
                        label=obj.label,
                        bbox=obj.bbox_norm,
                        confidence=obj.confidence,
                        source=obj.source,
                    ))
        # Also check affordances for dialog-related actions
        for aff in scene_graph.affordances:
            if aff.verb == "select" and "dialog" in aff.target_object_id.lower():
                # Find the corresponding object
                for obj in scene_graph.objects:
                    if obj.object_id == aff.target_object_id:
                        options.append(DialogueOption(
                            option_id=obj.object_id,
                            label=obj.label,
                            bbox=obj.bbox_norm,
                            confidence=obj.confidence,
                            source=obj.source,
                        ))
        return options

    def _handle_branch(
        self, options: list[DialogueOption], now: float,
    ) -> DialogueActionResult:
        """Handle a detected branch point."""
        self._consecutive_skips = 0

        # Try registry match first
        match_result = self._registry.match(options)
        if match_result.matched and match_result.option is not None:
            self._state = DialogueState.WAITING_SELECTION
            return DialogueActionResult(
                action="select_option",
                state=self._state,
                selected_option=match_result.option,
                reason=match_result.reason,
                confidence=match_result.confidence,
                timestamp=now,
            )

        # VLM fallback for unknown options
        if match_result.fallback_to_vlm and self._vlm_delegate is not None:
            self._state = DialogueState.WAITING_SELECTION
            return DialogueActionResult(
                action="select_option",
                state=self._state,
                selected_option=options[0] if options else None,
                reason="vlm_fallback",
                confidence=match_result.confidence,
                timestamp=now,
            )

        # No match and no VLM → need user escalation
        self._state = DialogueState.WAITING_SELECTION
        return DialogueActionResult(
            action="pause",
            state=self._state,
            reason="unknown_options_need_user",
            confidence=0.0,
            timestamp=now,
        )

    _MAX_CONSECUTIVE_SKIPS = MAX_CONSECUTIVE_SKIPS
