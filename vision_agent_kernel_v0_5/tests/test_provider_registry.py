"""Tests for the dynamic ProviderRegistry and dynamic loading of providers."""

from __future__ import annotations

import pytest

from capsules.domain_protocols import ProviderHealth
from capsules.provider_registry import ProviderRegistry, provider_registry


class MockHealthProvider:
    def health(self) -> ProviderHealth:
        return ProviderHealth(status="ok", message="Mock OK")


class MockDegradedProvider:
    def health(self) -> ProviderHealth:
        return ProviderHealth(status="degraded", message="Mock degraded")


class MockCrashProvider:
    def health(self) -> ProviderHealth:
        raise ValueError("Crash")


class MockSimpleProvider:
    pass


def test_provider_registry_lifecycle() -> None:
    """Test standard register, get, list, and unregister flows in isolation."""
    registry = ProviderRegistry()

    # 1. Register
    registry.register_providers(
        "test_capsule",
        {
            "screen_classifier": "tests.test_provider_registry:MockHealthProvider",
            "combat_planner": "tests.test_provider_registry:MockSimpleProvider",
        },
    )

    assert "test_capsule" in registry.list_capsules()
    assert type(registry.get_provider("test_capsule", "screen_classifier")).__name__ == "MockHealthProvider"
    assert type(registry.get_provider("test_capsule", "combat_planner")).__name__ == "MockSimpleProvider"

    # 2. Re-register (should warn/overwrite)
    registry.register_providers(
        "test_capsule",
        {
            "screen_classifier": "tests.test_provider_registry:MockDegradedProvider",
        },
    )
    assert type(registry.get_provider("test_capsule", "screen_classifier")).__name__ == "MockDegradedProvider"

    assert registry.get_provider("test_capsule", "combat_planner") is None

    # 3. Unregister
    registry.unregister_providers("test_capsule")
    assert "test_capsule" not in registry.list_capsules()
    assert registry.get_provider("test_capsule", "screen_classifier") is None


def test_provider_registry_rollback_on_failure() -> None:
    """Test that registration rolls back and cleans up if one class fails to load."""
    registry = ProviderRegistry()

    with pytest.raises(ImportError):
        registry.register_providers(
            "failed_capsule",
            {
                "screen_classifier": "tests.test_provider_registry:MockHealthProvider",
                "combat_planner": "nonexistent_module:NonexistentClass",  # Should fail
            },
        )

    # Verify rollback: no provider for failed_capsule was registered
    assert "failed_capsule" not in registry.list_capsules()
    assert registry.get_provider("failed_capsule", "screen_classifier") is None


def test_provider_registry_health_checks() -> None:
    """Test dynamic query of provider health statuses."""
    registry = ProviderRegistry()

    registry.register_providers(
        "health_capsule",
        {
            "ok_prov": "tests.test_provider_registry:MockHealthProvider",
            "degraded_prov": "tests.test_provider_registry:MockDegradedProvider",
            "simple_prov": "tests.test_provider_registry:MockSimpleProvider",
            "crash_prov": "tests.test_provider_registry:MockCrashProvider",
        },
    )

    health_states = registry.health("health_capsule")
    assert health_states["ok_prov"].status == "ok"
    assert health_states["ok_prov"].message == "Mock OK"

    assert health_states["degraded_prov"].status == "degraded"
    assert health_states["degraded_prov"].message == "Mock degraded"

    assert health_states["simple_prov"].status == "ok"  # defaults to ok if no health()
    assert "No health check method found" in health_states["simple_prov"].message

    assert health_states["crash_prov"].status == "error"
    assert "Crash" in health_states["crash_prov"].message


def test_genshin_providers_load_from_manifest() -> None:
    """Verify that Genshin providers specified in the manifest load successfully."""
    from capsules.capsule_protocol import load_manifest_from_yaml
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "capsules" / "genshin" / "capsule.yaml"
    manifest = load_manifest_from_yaml(str(manifest_path))

    registry = ProviderRegistry()
    registry.register_providers(manifest.capsule_id, manifest.providers)

    # Check that all loaded providers are healthy and instantiated
    for p_type in manifest.providers:
        provider = registry.get_provider(manifest.capsule_id, p_type)
        assert provider is not None
        health = provider.health()
        assert health.status == "ok"
