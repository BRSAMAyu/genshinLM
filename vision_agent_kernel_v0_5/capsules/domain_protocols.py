from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from core.types import LocalizationReading


def _default_empty_dict() -> Dict[str, Any]:
    return {}


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """Represents the health status of a domain provider."""
    status: str  # "ok", "error", "degraded"
    message: str = ""


@dataclass(frozen=True, slots=True)
class ScreenState:
    """Game-agnostic screen classification state."""
    state: str  # "unknown", "overworld", "combat", "dialog", "menu", "map", etc.
    confidence: float = 1.0
    active_regions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CombatContext:
    """Context state passed to the combat planner."""
    character_hp: Dict[str, float] = field(default_factory=dict)
    character_max_hp: Dict[str, float] = field(default_factory=dict)
    cooldowns: Dict[str, float] = field(default_factory=dict)
    active_character: str = ""
    danger_level: float = 0.0
    extensions: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CombatPlan:
    """Action plan returned by the combat planner."""
    action_keys: List[str] = field(default_factory=list)
    mouse_clicks: List[tuple[int, int]] = field(default_factory=list)
    thought: str = ""
    should_interrupt: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NavigationGoal:
    """Abstract goal for navigation."""
    goal_type: str  # "marker", "coordinate", "npc"
    target: str  # "quest_marker_1", "1024,768", "Katheryne"
    tolerance: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NavigationPlan:
    """Plan steps produced by the navigator."""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    total_steps: int = 0
    route_valid: bool = True
    thought: str = ""


@dataclass(frozen=True, slots=True)
class DialogState:
    """Dynamic dialog interaction state."""
    in_dialog: bool = False
    dialog_text: str = ""
    options: List[str] = field(default_factory=list)
    option_click_zones: List[tuple[int, int, int, int]] = field(default_factory=list)  # (x1, y1, x2, y2)
    can_skip: bool = False


@dataclass(frozen=True, slots=True)
class KnowledgeQuery:
    """Query sent to the knowledge provider."""
    category: str  # "items", "characters", "quests", "keymaps"
    query_string: str
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeResult:
    """Knowledge result payload."""
    found: bool
    payload: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


class ScreenClassifierProtocol(Protocol):
    """Protocol for screen state classification."""
    def classify(self, frame: Any, state_bus: Any) -> ScreenState:
        ...

    def health(self) -> ProviderHealth:
        ...


class CombatPlannerProtocol(Protocol):
    """Protocol for combat decision planning."""
    def plan(self, context: CombatContext) -> CombatPlan:
        ...

    def health(self) -> ProviderHealth:
        ...


class NavigatorProtocol(Protocol):
    """Protocol for pathfinding and navigation."""
    def plan(self, goal: NavigationGoal, screen_state: ScreenState, knowledge: Any) -> NavigationPlan:
        ...

    def health(self) -> ProviderHealth:
        ...


class DialogHandlerProtocol(Protocol):
    """Protocol for detecting and handling dialog flows."""
    def detect(self, frame: Any, screen_state: ScreenState) -> DialogState:
        ...

    def health(self) -> ProviderHealth:
        ...


class CooldownProviderProtocol(Protocol):
    """Protocol for ability and status cooldowns."""
    def cooldowns(self) -> Dict[str, float]:
        ...

    def health(self) -> ProviderHealth:
        ...


class KnowledgeProviderProtocol(Protocol):
    """Protocol for capsule-scoped static assets and knowledge queries."""
    def query(self, query: KnowledgeQuery) -> KnowledgeResult:
        ...

    def health(self) -> ProviderHealth:
        ...


class VerifierProviderProtocol(Protocol):
    """Protocol for dynamically resolving verifiers by ID."""
    def get(self, verifier_id: str) -> Any:
        ...

    def health(self) -> ProviderHealth:
        ...


class LocalizationProviderProtocol(Protocol):
    """Protocol for reading per-frame localization cues from a game.

    A capsule implements this to convert whatever spatial signals the game
    exposes (minimap optical flow, a compass needle, an opened world map, visual
    odometry, VLM landmark fixes) into a game-agnostic
    :class:`~core.types.LocalizationReading`. The reading is then fused with
    dead-reckoning by :class:`~perception.pose_fusion.PoseFusion`, so a game
    without a minimap supplies the same reading from other sources and the rest
    of the stack is unaffected.

    Implementations must convert sensor-frame quantities (e.g. minimap pixels)
    into the world-unit / clockwise-from-north conventions documented on
    :class:`~core.types.PoseEstimate`.
    """

    def read(self, frame: Any, frame_id: int, timestamp: float) -> LocalizationReading:
        ...

    def health(self) -> ProviderHealth:
        ...
