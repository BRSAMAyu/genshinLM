"""Dialog driving with conditional responses and affection-aware choices.

Covers:
- D-01/D-02: Basic dialog advance and selection
- D-03: Conditional dialog responses (choice depends on quest state, items, prior dialog)
- D-04: Affection-based dialog (NPC relationship level affects available options)

Also provides a bridge from the Kernel DialogueController (agent_kernel) to
the Capsule-level DialogDriver, enabling smart skip-rate control and branch
interception with VLM fallback.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from agent_kernel.dialogue_controller import DialogueController, OptionRegistry
from agent_kernel.types import Affordance, SceneGraph, SceneObject
from interaction.dialog_branch_analyzer import ConsequenceTracker, DialogBranchAnalyzer

if TYPE_CHECKING:
    from execution.safe_window_backend import SafeWindowInputBackend
    from perception.genshin_screen_classifier import GenshinScreenClassifier

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# D-03: Conditional dialog responses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DialogCondition:
    """A condition that gates a dialog choice."""
    condition_type: str   # "quest_active", "item_owned", "affection_level", "prior_choice"
    key: str              # Quest ID, item name, NPC name, etc.
    value: Any = None     # Expected value


class ConditionalDialogSelector:
    """Select dialog choices based on game state conditions.

    Some dialog branches are gated by:
    - Whether a quest is active or completed
    - Whether the player has a specific item
    - NPC affection/relationship level
    - Prior dialog choices in this session

    This selector evaluates conditions and picks the best available option.
    """

    def __init__(
        self,
        analyzer: DialogBranchAnalyzer | None = None,
        tracker: ConsequenceTracker | None = None,
    ) -> None:
        self._analyzer = analyzer or DialogBranchAnalyzer(tracker=tracker)
        self._quest_state: dict[str, str] = {}  # quest_id → "active"|"completed"|"none"
        self._inventory: set[str] = set()
        self._affection: dict[str, int] = {}  # npc_name → level

    def update_quest_state(self, quest_id: str, state: str) -> None:
        self._quest_state[quest_id] = state

    def update_inventory(self, items: set[str]) -> None:
        self._inventory = items

    def update_affection(self, npc_name: str, level: int) -> None:
        self._affection[npc_name] = level

    def select_choice(
        self,
        choices: list[str],
        conditions: list[DialogCondition] | None = None,
        context: dict[str, Any] | None = None,
    ) -> int:
        """Select best dialog choice considering conditions.

        If conditions are provided, filters choices to only those whose
        conditions are met, then delegates to DialogBranchAnalyzer.
        """
        if not choices:
            return 0

        if not conditions:
            return self._analyzer.analyze_choices(choices, context)

        # Filter to choices whose conditions are met
        viable_indices: list[int] = []
        for i, cond in enumerate(conditions):
            if i >= len(choices):
                break
            if cond is None or self._evaluate(cond):
                viable_indices.append(i)

        if not viable_indices:
            # No conditions met — fall back to first choice
            return 0

        # Among viable choices, use analyzer preference
        for idx in viable_indices:
            text = choices[idx].lower()
            for kw in ("接受", "同意", "好的", "当然"):
                if kw in text:
                    self._maybe_record(choices, idx, context)
                    return idx

        # Prefer condition-gated options over unconditional ones
        selected = viable_indices[-1]
        self._maybe_record(choices, selected, context)
        return selected

    def _evaluate(self, condition: DialogCondition) -> bool:
        if condition.condition_type == "quest_active":
            return self._quest_state.get(condition.key) in ("active", "completed")
        if condition.condition_type == "item_owned":
            return condition.key in self._inventory
        if condition.condition_type == "affection_level":
            level = self._affection.get(condition.key, 0)
            return level >= (condition.value or 0)
        return True

    def _maybe_record(
        self, choices: list[str], selected: int, context: dict[str, Any] | None,
    ) -> None:
        if context:
            self._analyzer.analyze_choices(choices, context)


# ---------------------------------------------------------------------------
# D-04: Affection-based dialog
# ---------------------------------------------------------------------------

class AffectionLevel(IntEnum):
    STRANGER = 0
    ACQUAINTANCE = 1
    FRIEND = 2
    CLOSE_FRIEND = 3
    TRUSTED = 4


@dataclass(slots=True)
class NpcRelationship:
    """Track NPC relationship state for dialog gating."""
    npc_name: str
    affection: int = 0  # 0-100
    dialog_count: int = 0
    quests_completed: int = 0
    gifts_given: int = 0

    @property
    def level(self) -> AffectionLevel:
        if self.affection >= 80:
            return AffectionLevel.TRUSTED
        if self.affection >= 60:
            return AffectionLevel.CLOSE_FRIEND
        if self.affection >= 40:
            return AffectionLevel.FRIEND
        if self.affection >= 20:
            return AffectionLevel.ACQUAINTANCE
        return AffectionLevel.STRANGER


class AffectionDialogManager:
    """Manage NPC affection and unlock dialog options based on relationship.

    Some dialog choices only appear when the player has sufficient relationship
    with an NPC. This manager tracks affection changes and provides the
    relationship level for dialog gating.
    """

    _AFFECTION_PER_DIALOG = 2
    _AFFECTION_PER_QUEST = 10
    _AFFECTION_PER_GIFT = 5

    def __init__(self) -> None:
        self._relationships: dict[str, NpcRelationship] = {}

    def get_or_create(self, npc_name: str) -> NpcRelationship:
        if npc_name not in self._relationships:
            self._relationships[npc_name] = NpcRelationship(npc_name=npc_name)
        return self._relationships[npc_name]

    def on_dialog(self, npc_name: str) -> None:
        rel = self.get_or_create(npc_name)
        rel.dialog_count += 1
        rel.affection = min(100, rel.affection + self._AFFECTION_PER_DIALOG)

    def on_quest_complete(self, npc_name: str) -> None:
        rel = self.get_or_create(npc_name)
        rel.quests_completed += 1
        rel.affection = min(100, rel.affection + self._AFFECTION_PER_QUEST)

    def on_gift(self, npc_name: str) -> None:
        rel = self.get_or_create(npc_name)
        rel.gifts_given += 1
        rel.affection = min(100, rel.affection + self._AFFECTION_PER_GIFT)

    def get_level(self, npc_name: str) -> AffectionLevel:
        return self.get_or_create(npc_name).level

    def is_unlocked(
        self, npc_name: str, required_level: AffectionLevel = AffectionLevel.ACQUAINTANCE,
    ) -> bool:
        return self.get_or_create(npc_name).level >= required_level

    def get_all_relationships(self) -> dict[str, NpcRelationship]:
        return dict(self._relationships)


# ---------------------------------------------------------------------------
# D-01/D-02: Dialog driver (existing, enhanced)
# ---------------------------------------------------------------------------

class DialogDriver:
    """Drive dialog to completion with auto-advance and choice selection.

    Optionally integrates with the Kernel DialogueController for smart
    skip-rate control and branch interception.
    """

    def __init__(
        self,
        backend: SafeWindowInputBackend,
        classifier: GenshinScreenClassifier,
        analyzer: DialogBranchAnalyzer | None = None,
        conditional_selector: ConditionalDialogSelector | None = None,
        dialogue_controller: DialogueController | None = None,
    ) -> None:
        self._backend = backend
        self._classifier = classifier
        self._analyzer = analyzer or DialogBranchAnalyzer()
        self._conditional = conditional_selector
        self._controller = dialogue_controller

    def drive_dialog_to_completion(
        self,
        frame_source,
        max_clicks: int = 100,
        shutdown_event: threading.Event | None = None,
    ) -> bool:
        """Advance dialog until it ends. Returns True if dialog completed.

        When a DialogueController is provided, uses its tick-based logic for
        skip-rate control and branch interception. Otherwise falls back to
        simple click-to-advance.
        """
        if self._controller is not None:
            return self._drive_with_controller(frame_source, max_clicks, shutdown_event)

        clicks = 0
        consecutive_no_dialog = 0

        while clicks < max_clicks:
            if shutdown_event and shutdown_event.is_set():
                return False

            frame = frame_source()
            if frame is None:
                time.sleep(0.1)
                continue

            state = self._classifier.classify(frame)

            if state.state != "dialog":
                consecutive_no_dialog += 1
                if consecutive_no_dialog >= 3:
                    log.info("[DialogDriver] dialog ended after %d clicks", clicks)
                    return True
                time.sleep(0.1)
                continue

            consecutive_no_dialog = 0
            # Click to advance dialog (bottom center of screen)
            try:
                self._backend.click_at(
                    self._backend.client_rect().center[0],
                    self._backend.client_rect().top + int(self._backend.client_rect().height * 0.85),
                    reason="advance_dialog",
                )
            except Exception as exc:
                log.debug("[DialogDriver] click failed: %s", exc)

            clicks += 1
            time.sleep(0.3)

        log.warning("[DialogDriver] max_clicks (%d) reached", max_clicks)
        return False

    def _drive_with_controller(
        self,
        frame_source,
        max_clicks: int = 100,
        shutdown_event: threading.Event | None = None,
    ) -> bool:
        """Drive dialog using the Kernel DialogueController for tick-based control."""
        from agent_kernel.dialogue_controller import DialogueState

        clicks = 0
        consecutive_complete = 0

        while clicks < max_clicks:
            if shutdown_event and shutdown_event.is_set():
                return False

            frame = frame_source()
            if frame is None:
                time.sleep(0.1)
                continue

            state = self._classifier.classify(frame)

            # Build a lightweight SceneGraph for the DialogueController
            scene_graph = self._build_scene_graph(frame, state.state)
            result = self._controller.tick(scene_graph)

            if result.action == "complete":
                consecutive_complete += 1
                if consecutive_complete >= 2:
                    log.info("[DialogDriver] controller reports dialog complete after %d clicks", clicks)
                    self._controller.reset()
                    return True

            elif result.action == "skip":
                try:
                    self._backend.click_at(
                        self._backend.client_rect().center[0],
                        self._backend.client_rect().top + int(self._backend.client_rect().height * 0.85),
                        reason=f"controller_skip_{result.reason}",
                    )
                except Exception as exc:
                    log.debug("[DialogDriver] controller skip failed: %s", exc)
                clicks += 1

            elif result.action == "select_option" and result.selected_option is not None:
                bbox = result.selected_option.bbox
                if bbox is not None:
                    rect = self._backend.client_rect()
                    nx, ny = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
                    px = rect.left + int(nx * rect.width)
                    py = rect.top + int(ny * rect.height)
                    try:
                        self._backend.click_at(px, py, reason=f"select_option_{result.reason}")
                    except Exception as exc:
                        log.debug("[DialogDriver] option select failed: %s", exc)
                clicks += 1

            elif result.action == "wait":
                time.sleep(0.05)

            elif result.action == "pause":
                log.info("[DialogDriver] controller paused: %s", result.reason)
                if result.state == DialogueState.WAITING_SELECTION:
                    # Need user escalation or VLM fallback — log and wait
                    time.sleep(0.5)

        self._controller.reset()
        log.warning("[DialogDriver] max_clicks (%d) reached (controller mode)", max_clicks)
        return False

    def _build_scene_graph(self, frame: object, screen_state: str) -> SceneGraph:
        """Build a lightweight SceneGraph from current frame for the DialogueController.

        Provides best-effort bbox estimates for dialog regions so the
        DialogueController can attempt option detection. These are coarse
        defaults; VLM/OCR integration will refine them in production.
        """
        objects: list[SceneObject] = []
        if screen_state == "dialog":
            # Dialog text area — bottom center (where text appears)
            objects.append(SceneObject(
                object_id="dialog_text",
                kind="dialog_option",
                label="dialog",
                bbox_norm=(0.15, 0.65, 0.85, 0.85),
                confidence=0.7,
                source="heuristic",
            ))

        return SceneGraph(
            timestamp=time.perf_counter(),
            scene_state=screen_state,
            objects=tuple(objects),
        )
