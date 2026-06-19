"""Universal navigator — game-agnostic facade that delegates to capsule navigators.

Provides ``UniversalNavigator`` which:
* Looks up the correct game-specific ``Navigator`` via the capsule registry.
* Falls back to ``NullNavigator`` when no capsule is loaded.
* Exposes the same ``Navigator`` protocol so callers never need to know
  which concrete backend is active.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from navigation.navigation_protocol import NavigationResult, Navigator, Waypoint

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# NullNavigator — safe no-op fallback
# ---------------------------------------------------------------------------

class NullNavigator:
    """Fallback navigator used when no capsule is loaded.

    Every method returns a failed ``NavigationResult`` so that callers
    can handle the "no game loaded" case gracefully without null-checks.
    """

    def navigate_to_waypoint(self, waypoint: Waypoint, **kwargs: Any) -> NavigationResult:
        return self._fail("navigate_to_waypoint")

    def navigate_to_quest_marker(
        self, frame_source: Any = None, max_steps: int = 300, **kwargs: Any
    ) -> NavigationResult:
        return self._fail("navigate_to_quest_marker")

    def teleport_to(self, waypoint: Waypoint, **kwargs: Any) -> NavigationResult:
        return self._fail("teleport_to")

    def check_arrival(self, frame: Any = None, **kwargs: Any) -> bool:
        return False

    def recover_lost_position(self, current_region: str = "", **kwargs: Any) -> NavigationResult:
        return self._fail("recover_lost_position")

    @staticmethod
    def _fail(method: str) -> NavigationResult:
        return NavigationResult(
            success=False,
            arrival_distance=float("inf"),
            time_elapsed=0.0,
            method_used=f"null:{method}",
        )


# ---------------------------------------------------------------------------
# Adapter: GenshinNavigator → Navigator protocol
# ---------------------------------------------------------------------------

class GenshinNavigatorAdapter:
    """Wraps :class:`GenshinNavigator` to satisfy the ``Navigator`` protocol."""

    def __init__(self, nav: Any) -> None:
        self._nav = nav

    def navigate_to_waypoint(self, waypoint: Waypoint, **kwargs: Any) -> NavigationResult:
        started = time.perf_counter()
        route = self._nav.plan_route(
            kwargs.get("from_id", ""), waypoint.name,
        )
        if not route:
            return NavigationResult(
                success=False,
                arrival_distance=float("inf"),
                time_elapsed=time.perf_counter() - started,
                method_used="genshin:plan_route_failed",
            )
        return NavigationResult(
            success=True,
            arrival_distance=0.0,
            time_elapsed=time.perf_counter() - started,
            method_used="genshin:route_planned",
        )

    def navigate_to_quest_marker(
        self, frame_source: Any = None, max_steps: int = 300, **kwargs: Any
    ) -> NavigationResult:
        # GenshinNavigator itself does not have a high-level quest follow;
        # QuestMarkerFollower handles that.  Return a not-implemented result
        # so callers can fall back to the dedicated follower.
        return NavigationResult(
            success=False,
            arrival_distance=float("inf"),
            time_elapsed=0.0,
            method_used="genshin:use_quest_marker_follower",
        )

    def teleport_to(self, waypoint: Waypoint, **kwargs: Any) -> NavigationResult:
        started = time.perf_counter()
        state_bus = kwargs.get("state_bus")
        if state_bus is not None:
            ok = self._nav.execute_teleport_via_bus(waypoint.name, state_bus)
        else:
            self._nav.execute_teleport_sequence(waypoint.name)
            ok = True  # sequence generated; execution is async
        return NavigationResult(
            success=ok,
            arrival_distance=0.0 if ok else float("inf"),
            time_elapsed=time.perf_counter() - started,
            method_used="genshin:teleport",
        )

    def check_arrival(self, frame: Any = None, **kwargs: Any) -> bool:
        if frame is None:
            return False
        return self._nav.check_arrival(frame)

    def recover_lost_position(self, current_region: str = "", **kwargs: Any) -> NavigationResult:
        started = time.perf_counter()
        # GenshinNavigator does not embed LostRecovery internally;
        # delegate via LostRecovery is the caller's responsibility.
        return NavigationResult(
            success=False,
            arrival_distance=float("inf"),
            time_elapsed=time.perf_counter() - started,
            method_used="genshin:use_lost_recovery",
        )


# ---------------------------------------------------------------------------
# Adapter: HsrNavigator → Navigator protocol
# ---------------------------------------------------------------------------

class HsrNavigatorAdapter:
    """Wraps :class:`HsrNavigator` to satisfy the ``Navigator`` protocol."""

    def __init__(self, nav: Any) -> None:
        self._nav = nav

    def navigate_to_waypoint(self, waypoint: Waypoint, **kwargs: Any) -> NavigationResult:
        started = time.perf_counter()
        from_location = kwargs.get("from_location", "")
        plan = self._nav.plan_teleport(from_location, waypoint.name)
        if not plan.steps:
            return NavigationResult(
                success=False,
                arrival_distance=float("inf"),
                time_elapsed=time.perf_counter() - started,
                method_used="hsr:plan_failed",
            )
        return NavigationResult(
            success=True,
            arrival_distance=0.0,
            time_elapsed=time.perf_counter() - started,
            method_used="hsr:teleport",
        )

    def navigate_to_quest_marker(
        self, frame_source: Any = None, max_steps: int = 300, **kwargs: Any
    ) -> NavigationResult:
        return NavigationResult(
            success=False,
            arrival_distance=float("inf"),
            time_elapsed=0.0,
            method_used="hsr:unsupported",
        )

    def teleport_to(self, waypoint: Waypoint, **kwargs: Any) -> NavigationResult:
        started = time.perf_counter()
        from_location = kwargs.get("from_location", "")
        plan = self._nav.plan_teleport(from_location, waypoint.name)
        return NavigationResult(
            success=plan.requires_teleport,
            arrival_distance=0.0 if plan.requires_teleport else float("inf"),
            time_elapsed=time.perf_counter() - started,
            method_used="hsr:teleport",
        )

    def check_arrival(self, frame: Any = None, **kwargs: Any) -> bool:
        # HsrNavigator does not implement frame-based arrival checks.
        return False

    def recover_lost_position(self, current_region: str = "", **kwargs: Any) -> NavigationResult:
        return NavigationResult(
            success=False,
            arrival_distance=float("inf"),
            time_elapsed=0.0,
            method_used="hsr:unsupported",
        )


# ---------------------------------------------------------------------------
# Capsule-ID → adapter mapping
# ---------------------------------------------------------------------------

_ADAPTER_MAP: dict[str, type] = {
    "genshin": GenshinNavigatorAdapter,
    "hsr": HsrNavigatorAdapter,
}


# ---------------------------------------------------------------------------
# UniversalNavigator
# ---------------------------------------------------------------------------

class UniversalNavigator:
    """Game-agnostic navigation facade.

    Delegates to the appropriate game-specific ``Navigator`` based on the
    currently active capsule.  Falls back to ``NullNavigator`` when no
    capsule is loaded.
    """

    def __init__(self, backend: Navigator | None = None) -> None:
        self._backend: Navigator = backend if backend is not None else NullNavigator()

    # -- factory -------------------------------------------------------------

    @classmethod
    def from_capsule(
        cls,
        capsule_id: str,
        *,
        navigator: Any | None = None,
        registry: Any | None = None,
    ) -> UniversalNavigator:
        """Create a ``UniversalNavigator`` for *capsule_id*.

        Parameters
        ----------
        capsule_id : str
            Capsule identifier, e.g. ``"genshin"`` or ``"hsr"``.
        navigator : object, optional
            Raw game-specific navigator instance.  If *None*, the factory
            will attempt to instantiate one from the capsule's runtime
            package.
        registry : CapsuleRegistry, optional
            If provided, used to discover the active capsule and obtain
            its navigator.  When *None* or when *capsule_id* is not
            registered, the factory falls back to ``NullNavigator``.

        Returns
        -------
        UniversalNavigator
            Ready-to-use navigator backed by the correct adapter.
        """
        # If registry is provided, check that the capsule is registered.
        if registry is not None:
            caps = registry.get(capsule_id)
            if caps is None:
                log.info("[UniversalNav] capsule %r not found in registry — using NullNavigator", capsule_id)
                return cls()

        adapter_cls = _ADAPTER_MAP.get(capsule_id)

        if adapter_cls is None:
            log.info("[UniversalNav] no adapter for capsule %r — using NullNavigator", capsule_id)
            return cls()

        # Build the raw navigator if the caller didn't provide one.
        if navigator is None:
            navigator = _instantiate_raw_navigator(capsule_id)

        backend = adapter_cls(navigator)
        return cls(backend=backend)

    # -- Navigator protocol delegation ---------------------------------------

    def navigate_to_waypoint(self, waypoint: Waypoint, **kwargs: Any) -> NavigationResult:
        return self._backend.navigate_to_waypoint(waypoint, **kwargs)

    def navigate_to_quest_marker(
        self, frame_source: Any = None, max_steps: int = 300, **kwargs: Any
    ) -> NavigationResult:
        return self._backend.navigate_to_quest_marker(frame_source, max_steps, **kwargs)

    def teleport_to(self, waypoint: Waypoint, **kwargs: Any) -> NavigationResult:
        return self._backend.teleport_to(waypoint, **kwargs)

    def check_arrival(self, frame: Any = None, **kwargs: Any) -> bool:
        return self._backend.check_arrival(frame, **kwargs)

    def recover_lost_position(self, current_region: str = "", **kwargs: Any) -> NavigationResult:
        return self._backend.recover_lost_position(current_region, **kwargs)

    @property
    def backend(self) -> Navigator:
        """The underlying game-specific navigator."""
        return self._backend


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _instantiate_raw_navigator(capsule_id: str) -> Any:
    """Best-effort instantiation of a raw game navigator.

    Returns ``None`` when the module is not importable (e.g. missing
    dependencies like numpy/cv2 in a test-only environment).
    """
    try:
        if capsule_id == "genshin":
            from navigation.genshin_navigator import GenshinNavigator
            return GenshinNavigator()
        if capsule_id == "hsr":
            from navigation.hsr_navigator import HSRNavigator
            return HSRNavigator()
    except Exception as exc:
        log.debug("[UniversalNav] could not instantiate raw navigator for %r: %s", capsule_id, exc)
    return None
