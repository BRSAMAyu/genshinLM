"""Universal navigation protocol — game-agnostic interface for in-game navigation.

Defines the Navigator protocol that all game-specific navigators must satisfy
via structural subtyping (PEP 544). The kernel's orchestration layer depends
only on this protocol; game-specific implementations live in capsules.

Public types:
    Waypoint          — a 3-D point of interest with metadata
    NavigationResult  — outcome of any navigation attempt
    Navigator         — structural protocol (duck-typed) for navigation backends
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Waypoint:
    """A named 3-D point of interest in the game world.

    Coordinates use the game's native world-space convention (typically
    centimeters from the world origin). ``region`` groups waypoints that
    share the same map / loading screen.
    """

    x: float
    y: float
    z: float
    name: str = ""
    region: str = ""


@dataclass(frozen=True, slots=True)
class NavigationResult:
    """Outcome of a navigation attempt.

    Attributes
    ----------
    success : bool
        True when the navigator considers the destination reached.
    arrival_distance : float
        Estimated remaining distance to the destination in game units.
        ``0.0`` when *success* is True.
    time_elapsed : float
        Wall-clock seconds consumed by the navigation attempt.
    method_used : str
        Human-readable tag describing the strategy that was used,
        e.g. ``"teleport"``, ``"walk"``, ``"minimap_follow"``.
    """

    success: bool
    arrival_distance: float
    time_elapsed: float
    method_used: str


# ---------------------------------------------------------------------------
# Navigator protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Navigator(Protocol):
    """Game-agnostic navigation interface.

    Every game-specific navigator (GenshinNavigator, HsrNavigator, …)
    must expose *at least* these methods so that the orchestration layer
    can drive navigation without knowing which game is active.

    Compliance is checked via structural subtyping — no base-class
    inheritance required.  The ``@runtime_checkable`` decorator allows
    ``isinstance(obj, Navigator)`` checks in tests and factories.
    """

    # -- waypoints -----------------------------------------------------------

    def navigate_to_waypoint(
        self,
        waypoint: Waypoint,
        **kwargs: Any,
    ) -> NavigationResult:
        """Move the character to *waypoint* and return the result.

        The implementation chooses the best method (teleport + walk,
        direct walk, etc.) based on internal state and game knowledge.
        """
        ...

    # -- quest markers -------------------------------------------------------

    def navigate_to_quest_marker(
        self,
        frame_source: Any,
        max_steps: int = 300,
        **kwargs: Any,
    ) -> NavigationResult:
        """Follow the on-screen quest marker until arrival.

        Parameters
        ----------
        frame_source : callable
            ``() -> np.ndarray | None`` — provides fresh screen frames.
        max_steps : int
            Upper bound on navigation steps before giving up.
        """
        ...

    # -- teleportation -------------------------------------------------------

    def teleport_to(
        self,
        waypoint: Waypoint,
        **kwargs: Any,
    ) -> NavigationResult:
        """Attempt to teleport directly to *waypoint* via the in-game map.

        Returns ``NavigationResult.success=False`` if the waypoint is
        locked / unreachable or the teleport UI flow fails.
        """
        ...

    # -- arrival check -------------------------------------------------------

    def check_arrival(
        self,
        frame: Any,
        **kwargs: Any,
    ) -> bool:
        """Return True when the current screen frame indicates arrival.

        *frame* is typically a ``np.ndarray`` screen capture; the exact
        interpretation is left to the game-specific implementation.
        """
        ...

    # -- lost recovery -------------------------------------------------------

    def recover_lost_position(
        self,
        current_region: str,
        **kwargs: Any,
    ) -> NavigationResult:
        """Attempt to recover when the agent is lost.

        Strategies include nearest waypoint, last safe point, minimap
        search, or teleport home — chosen by the implementation.
        """
        ...
