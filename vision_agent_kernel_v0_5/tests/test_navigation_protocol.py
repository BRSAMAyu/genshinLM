"""Tests for navigation_protocol and universal_navigator.

Verifies:
- Navigator protocol structural compliance (GenshinNavigator, HsrNavigator)
- UniversalNavigator factory and fallback behaviour
- NavigationResult / Waypoint value types
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from navigation.navigation_protocol import NavigationResult, Navigator, Waypoint
from navigation.universal_navigator import (
    GenshinNavigatorAdapter,
    HsrNavigatorAdapter,
    NullNavigator,
    UniversalNavigator,
)


# ===================================================================
# Waypoint
# ===================================================================

class TestWaypoint:
    def test_waypoint_creation(self) -> None:
        wp = Waypoint(x=100.0, y=200.0, z=50.0, name="mondstadt", region="mondstadt_region")
        assert wp.x == 100.0
        assert wp.y == 200.0
        assert wp.z == 50.0
        assert wp.name == "mondstadt"
        assert wp.region == "mondstadt_region"

    def test_waypoint_defaults(self) -> None:
        wp = Waypoint(x=0.0, y=0.0, z=0.0)
        assert wp.name == ""
        assert wp.region == ""

    def test_waypoint_frozen(self) -> None:
        wp = Waypoint(x=1.0, y=2.0, z=3.0, name="test")
        with pytest.raises(AttributeError):
            wp.x = 99.0  # type: ignore[misc]

    def test_waypoint_equality(self) -> None:
        a = Waypoint(x=1.0, y=2.0, z=3.0, name="a", region="r")
        b = Waypoint(x=1.0, y=2.0, z=3.0, name="a", region="r")
        assert a == b

    def test_waypoint_slots(self) -> None:
        wp = Waypoint(x=0.0, y=0.0, z=0.0)
        assert hasattr(wp, "__slots__")


# ===================================================================
# NavigationResult
# ===================================================================

class TestNavigationResult:
    def test_navigation_result_fields(self) -> None:
        r = NavigationResult(success=True, arrival_distance=0.0, time_elapsed=1.5, method_used="teleport")
        assert r.success is True
        assert r.arrival_distance == 0.0
        assert r.time_elapsed == 1.5
        assert r.method_used == "teleport"

    def test_navigation_result_failure(self) -> None:
        r = NavigationResult(success=False, arrival_distance=100.0, time_elapsed=5.0, method_used="walk")
        assert r.success is False
        assert r.arrival_distance > 0.0

    def test_navigation_result_frozen(self) -> None:
        r = NavigationResult(success=False, arrival_distance=0.0, time_elapsed=0.0, method_used="")
        with pytest.raises(AttributeError):
            r.success = True  # type: ignore[misc]

    def test_navigation_result_slots(self) -> None:
        r = NavigationResult(success=False, arrival_distance=0.0, time_elapsed=0.0, method_used="")
        assert hasattr(r, "__slots__")


# ===================================================================
# Protocol compliance — GenshinNavigator
# ===================================================================

class TestProtocolComplianceGenshin:
    """Verify that GenshinNavigatorAdapter satisfies the Navigator protocol."""

    def test_protocol_compliance_genshin(self) -> None:
        mock_nav = MagicMock()
        adapter = GenshinNavigatorAdapter(mock_nav)
        assert isinstance(adapter, Navigator)

    def test_navigate_to_waypoint(self) -> None:
        mock_nav = MagicMock()
        mock_nav.plan_route.return_value = ["wp_a", "wp_b"]
        adapter = GenshinNavigatorAdapter(mock_nav)
        wp = Waypoint(x=1.0, y=2.0, z=3.0, name="wp_b")
        result = adapter.navigate_to_waypoint(wp)
        assert result.success is True
        assert result.method_used == "genshin:route_planned"
        mock_nav.plan_route.assert_called_once_with("", "wp_b")

    def test_navigate_to_waypoint_empty_route(self) -> None:
        mock_nav = MagicMock()
        mock_nav.plan_route.return_value = []
        adapter = GenshinNavigatorAdapter(mock_nav)
        result = adapter.navigate_to_waypoint(Waypoint(x=0.0, y=0.0, z=0.0, name="missing"))
        assert result.success is False
        assert result.arrival_distance == float("inf")

    def test_teleport_to_with_bus(self) -> None:
        mock_nav = MagicMock()
        mock_nav.execute_teleport_via_bus.return_value = True
        adapter = GenshinNavigatorAdapter(mock_nav)
        wp = Waypoint(x=0.0, y=0.0, z=0.0, name="teleport_target")
        mock_bus = MagicMock()
        result = adapter.teleport_to(wp, state_bus=mock_bus)
        assert result.success is True
        assert result.method_used == "genshin:teleport"

    def test_check_arrival_with_frame(self) -> None:
        mock_nav = MagicMock()
        mock_nav.check_arrival.return_value = True
        adapter = GenshinNavigatorAdapter(mock_nav)
        frame = MagicMock(name="frame")
        assert adapter.check_arrival(frame) is True
        mock_nav.check_arrival.assert_called_once_with(frame)

    def test_check_arrival_none_frame(self) -> None:
        adapter = GenshinNavigatorAdapter(MagicMock())
        assert adapter.check_arrival(None) is False

    def test_recover_lost_position(self) -> None:
        adapter = GenshinNavigatorAdapter(MagicMock())
        result = adapter.recover_lost_position("mondstadt")
        assert result.success is False
        assert result.method_used == "genshin:use_lost_recovery"


# ===================================================================
# Protocol compliance — HSR
# ===================================================================

class TestProtocolComplianceHSR:
    """Verify that HsrNavigatorAdapter satisfies the Navigator protocol."""

    def test_protocol_compliance_hsr(self) -> None:
        mock_nav = MagicMock()
        adapter = HsrNavigatorAdapter(mock_nav)
        assert isinstance(adapter, Navigator)

    def test_navigate_to_waypoint(self) -> None:
        mock_nav = MagicMock()
        mock_plan = MagicMock()
        mock_plan.steps = ["step1", "step2"]
        mock_plan.requires_teleport = True
        mock_nav.plan_teleport.return_value = mock_plan
        adapter = HsrNavigatorAdapter(mock_nav)
        wp = Waypoint(x=0.0, y=0.0, z=0.0, name="jarilo_station")
        result = adapter.navigate_to_waypoint(wp)
        assert result.success is True
        assert result.method_used == "hsr:teleport"

    def test_navigate_to_waypoint_empty_plan(self) -> None:
        mock_nav = MagicMock()
        mock_plan = MagicMock()
        mock_plan.steps = []
        mock_nav.plan_teleport.return_value = mock_plan
        adapter = HsrNavigatorAdapter(mock_nav)
        result = adapter.navigate_to_waypoint(Waypoint(x=0.0, y=0.0, z=0.0, name="nowhere"))
        assert result.success is False

    def test_teleport_to(self) -> None:
        mock_nav = MagicMock()
        mock_plan = MagicMock()
        mock_plan.requires_teleport = True
        mock_nav.plan_teleport.return_value = mock_plan
        adapter = HsrNavigatorAdapter(mock_nav)
        result = adapter.teleport_to(Waypoint(x=0.0, y=0.0, z=0.0, name="target"))
        assert result.success is True
        assert result.method_used == "hsr:teleport"

    def test_check_arrival_unsupported(self) -> None:
        adapter = HsrNavigatorAdapter(MagicMock())
        assert adapter.check_arrival(MagicMock()) is False

    def test_recover_lost_position_unsupported(self) -> None:
        adapter = HsrNavigatorAdapter(MagicMock())
        result = adapter.recover_lost_position("jarilo")
        assert result.success is False
        assert result.method_used == "hsr:unsupported"

    def test_navigate_to_quest_marker_unsupported(self) -> None:
        adapter = HsrNavigatorAdapter(MagicMock())
        result = adapter.navigate_to_quest_marker()
        assert result.success is False


# ===================================================================
# NullNavigator
# ===================================================================

class TestNullNavigator:
    def test_null_navigator_is_navigator(self) -> None:
        assert isinstance(NullNavigator(), Navigator)

    def test_null_navigate_to_waypoint(self) -> None:
        nav = NullNavigator()
        result = nav.navigate_to_waypoint(Waypoint(x=0.0, y=0.0, z=0.0))
        assert result.success is False
        assert "null:" in result.method_used

    def test_null_navigate_to_quest_marker(self) -> None:
        nav = NullNavigator()
        result = nav.navigate_to_quest_marker()
        assert result.success is False

    def test_null_teleport_to(self) -> None:
        nav = NullNavigator()
        result = nav.teleport_to(Waypoint(x=0.0, y=0.0, z=0.0))
        assert result.success is False

    def test_null_check_arrival(self) -> None:
        nav = NullNavigator()
        assert nav.check_arrival() is False

    def test_null_recover_lost_position(self) -> None:
        nav = NullNavigator()
        result = nav.recover_lost_position()
        assert result.success is False


# ===================================================================
# UniversalNavigator
# ===================================================================

class TestUniversalNavigator:
    def test_default_uses_null_navigator(self) -> None:
        un = UniversalNavigator()
        assert isinstance(un.backend, NullNavigator)

    def test_explicit_backend(self) -> None:
        mock = MagicMock(spec=Navigator)
        un = UniversalNavigator(backend=mock)
        assert un.backend is mock

    def test_from_capsule_unknown_returns_null(self) -> None:
        un = UniversalNavigator.from_capsule("unknown_game")
        assert isinstance(un.backend, NullNavigator)

    def test_from_capsule_with_registry_not_registered(self) -> None:
        registry = MagicMock()
        registry.get.return_value = None
        un = UniversalNavigator.from_capsule("genshin", registry=registry)
        assert isinstance(un.backend, NullNavigator)

    def test_from_capsule_genshin_with_mock(self) -> None:
        mock_nav = MagicMock()
        un = UniversalNavigator.from_capsule("genshin", navigator=mock_nav)
        assert isinstance(un.backend, GenshinNavigatorAdapter)
        assert isinstance(un, Navigator)  # UniversalNavigator also satisfies Navigator

    def test_from_capsule_hsr_with_mock(self) -> None:
        mock_nav = MagicMock()
        un = UniversalNavigator.from_capsule("hsr", navigator=mock_nav)
        assert isinstance(un.backend, HsrNavigatorAdapter)

    def test_delegates_navigate_to_waypoint(self) -> None:
        mock = MagicMock()
        mock.navigate_to_waypoint.return_value = NavigationResult(
            success=True, arrival_distance=0.0, time_elapsed=0.1, method_used="test",
        )
        un = UniversalNavigator(backend=mock)
        wp = Waypoint(x=1.0, y=2.0, z=3.0, name="wp")
        result = un.navigate_to_waypoint(wp)
        assert result.success is True
        mock.navigate_to_waypoint.assert_called_once_with(wp)

    def test_delegates_teleport_to(self) -> None:
        mock = MagicMock()
        mock.teleport_to.return_value = NavigationResult(
            success=True, arrival_distance=0.0, time_elapsed=5.0, method_used="teleport",
        )
        un = UniversalNavigator(backend=mock)
        result = un.teleport_to(Waypoint(x=0.0, y=0.0, z=0.0))
        assert result.success is True

    def test_delegates_check_arrival(self) -> None:
        mock = MagicMock()
        mock.check_arrival.return_value = True
        un = UniversalNavigator(backend=mock)
        assert un.check_arrival("fake_frame") is True

    def test_delegates_recover_lost_position(self) -> None:
        mock = MagicMock()
        mock.recover_lost_position.return_value = NavigationResult(
            success=True, arrival_distance=0.0, time_elapsed=2.0, method_used="recovered",
        )
        un = UniversalNavigator(backend=mock)
        result = un.recover_lost_position("mondstadt")
        assert result.success is True

    def test_universal_navigator_is_navigator(self) -> None:
        assert isinstance(UniversalNavigator(), Navigator)

    def test_from_capsule_with_registry_registered(self) -> None:
        """When registry has the capsule but no navigator is given, factory
        tries to instantiate the raw navigator (may fall back to NullNavigator
        in test env without numpy/cv2)."""
        registry = MagicMock()
        registry.get.return_value = MagicMock()  # capsule exists
        un = UniversalNavigator.from_capsule("genshin", registry=registry)
        # Either adapter or NullNavigator depending on import availability
        assert isinstance(un.backend, Navigator)
