"""Tests for the AppCapsule boundary: protocol, registry, lifecycle, isolation."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from capsules.capsule_protocol import CapsuleContext, CapsuleManifest, load_manifest_from_yaml
from capsules.capsule_registry import CapsuleRegistry
from capsules.demo_arpg.capsule_entry import DemoArpgCapsule
from capsules.desktop_ui.capsule_entry import DesktopUiCapsule
from core.state_bus import StateBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(state_bus: StateBus | None = None) -> CapsuleContext:
    """Build a CapsuleContext with real StateBus and mock dependencies."""
    bus = state_bus or StateBus()
    orchestrator = MagicMock()
    mode_arbiter = MagicMock()
    pipeline = MagicMock()
    return CapsuleContext(
        state_bus=bus,
        pipeline=pipeline,
        orchestrator=orchestrator,
        mode_arbiter=mode_arbiter,
    )


def _make_manifest(**overrides: object) -> CapsuleManifest:
    """Build a minimal CapsuleManifest, with optional field overrides."""
    defaults = dict(
        capsule_id="test_capsule",
        version="0.1.0",
        display_name="Test Capsule",
        description="A test capsule",
    )
    defaults.update(overrides)
    return CapsuleManifest(**defaults)


# ---------------------------------------------------------------------------
# 1. CapsuleRegistry register / unregister
# ---------------------------------------------------------------------------

class TestRegistryRegisterUnregister:
    def test_register_adds_capsule(self) -> None:
        registry = CapsuleRegistry()
        bus = StateBus()
        ctx = _make_context(bus)
        capsule = DemoArpgCapsule()
        manifest = _make_manifest(capsule_id="demo_arpg")

        registry.register(capsule, manifest, ctx)

        assert registry.get("demo_arpg") is capsule
        assert "demo_arpg" in registry.list_registered()

    def test_unregister_removes_capsule(self) -> None:
        registry = CapsuleRegistry()
        bus = StateBus()
        ctx = _make_context(bus)
        capsule = DemoArpgCapsule()
        manifest = _make_manifest(capsule_id="demo_arpg")

        registry.register(capsule, manifest, ctx)
        result = registry.unregister("demo_arpg")

        assert result is True
        assert registry.get("demo_arpg") is None
        assert "demo_arpg" not in registry.list_registered()

    def test_unregister_nonexistent_returns_false(self) -> None:
        registry = CapsuleRegistry()
        assert registry.unregister("nope") is False

    def test_double_register_raises(self) -> None:
        registry = CapsuleRegistry()
        ctx = _make_context()
        capsule = DemoArpgCapsule()
        manifest = _make_manifest(capsule_id="demo_arpg")

        registry.register(capsule, manifest, ctx)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(DemoArpgCapsule(), manifest, ctx)

    def test_register_rejects_manifest_id_mismatch(self) -> None:
        registry = CapsuleRegistry()
        ctx = _make_context()

        with pytest.raises(ValueError, match="does not match"):
            registry.register(
                DemoArpgCapsule(),
                _make_manifest(capsule_id="wrong_id"),
                ctx,
            )

    def test_registry_exposes_skill_catalog(self) -> None:
        registry = CapsuleRegistry()
        bus = StateBus()
        ctx = _make_context(bus)
        manifest = load_manifest_from_yaml(
            str(Path(__file__).resolve().parent.parent / "capsules" / "demo_arpg" / "capsule.yaml")
        )

        registry.register(DemoArpgCapsule(), manifest, ctx)

        catalog = registry.skill_catalog()
        assert catalog[0]["capsule_id"] == "demo_arpg"
        assert catalog[0]["skill_id"] == "dummy_skill"


# ---------------------------------------------------------------------------
# 2. Capsule install registers slots on StateBus
# ---------------------------------------------------------------------------

class TestCapsuleSlots:
    def test_demo_arpg_registers_slots(self) -> None:
        bus = StateBus()
        ctx = _make_context(bus)
        capsule = DemoArpgCapsule()
        capsule.install(ctx)

        slot_names = bus.registered_slot_names()
        assert "demo_arpg.screen_state" in slot_names
        assert "demo_arpg.danger_state" in slot_names

    def test_desktop_ui_registers_slots(self) -> None:
        bus = StateBus()
        ctx = _make_context(bus)
        capsule = DesktopUiCapsule()
        capsule.install(ctx)

        slot_names = bus.registered_slot_names()
        assert "desktop_ui.grounded_elements" in slot_names
        assert "desktop_ui.safety_state" in slot_names

    def test_slot_is_writable(self) -> None:
        bus = StateBus()
        ctx = _make_context(bus)
        capsule = DemoArpgCapsule()
        capsule.install(ctx)

        slot = bus.get_slot("demo_arpg.screen_state")
        assert slot is not None
        version = slot.put({"state": "combat"})
        assert version == 1
        assert slot.get() == {"state": "combat"}


# ---------------------------------------------------------------------------
# 3. Capsule uninstall cleans subscriptions via StateBus.unsubscribe
# ---------------------------------------------------------------------------

class TestCapsuleUnsubscribe:
    def test_uninstall_removes_subscriptions(self) -> None:
        bus = StateBus()
        ctx = _make_context(bus)

        # Create a capsule that subscribes during install.
        class SubCapsule:
            capsule_id: str = "sub_test"

            def __init__(self) -> None:
                self._active = False
                self._sub_ids: list[str] = []

            def install(self, context: CapsuleContext) -> None:
                sid = context.state_bus.subscribe("test_event", lambda d: None)
                self._sub_ids.append(sid)

            def activate(self) -> None:
                self._active = True

            def deactivate(self) -> None:
                self._active = False

            @property
            def is_active(self) -> bool:
                return self._active

            def uninstall(self, context: CapsuleContext) -> None:
                for sid in self._sub_ids:
                    context.state_bus.unsubscribe(sid)
                self._sub_ids.clear()

        capsule = SubCapsule()
        manifest = _make_manifest(capsule_id="sub_test")
        registry = CapsuleRegistry()
        registry.register(capsule, manifest, ctx)

        # Verify subscription exists.
        assert len(bus._sub_ids) >= 1

        registry.unregister("sub_test")

        # Verify subscription was cleaned up.
        assert len(bus._sub_ids) == 0

    def test_registry_cleans_capsule_subscriptions_if_uninstall_forgets(self) -> None:
        bus = StateBus()
        ctx = _make_context(bus)

        class ForgetfulCapsule:
            capsule_id: str = "forgetful"

            def install(self, context: CapsuleContext) -> None:
                context.state_bus.subscribe("test_event", lambda d: None)

            def activate(self) -> None:
                pass

            def deactivate(self) -> None:
                pass

            @property
            def is_active(self) -> bool:
                return False

            def uninstall(self, context: CapsuleContext) -> None:
                pass

        registry = CapsuleRegistry()
        registry.register(ForgetfulCapsule(), _make_manifest(capsule_id="forgetful"), ctx)
        assert len(bus.subscription_ids()) == 1

        registry.unregister("forgetful")

        assert bus.subscription_ids() == []

    def test_register_failure_rolls_back_subscriptions_created_during_install(self) -> None:
        bus = StateBus()
        ctx = _make_context(bus)

        class FailingAfterSubscribeCapsule:
            capsule_id: str = "failing_after_subscribe"

            def install(self, context: CapsuleContext) -> None:
                context.state_bus.subscribe("test_event", lambda d: None)
                raise RuntimeError("install exploded after subscribe")

            def activate(self) -> None:
                pass

            def deactivate(self) -> None:
                pass

            @property
            def is_active(self) -> bool:
                return False

            def uninstall(self, context: CapsuleContext) -> None:
                pass

        registry = CapsuleRegistry()

        with pytest.raises(RuntimeError, match="install exploded after subscribe"):
            registry.register(
                FailingAfterSubscribeCapsule(),
                _make_manifest(capsule_id="failing_after_subscribe"),
                ctx,
            )

        assert bus.subscription_ids() == []


# ---------------------------------------------------------------------------
# 4. No genshin references under capsules/ or core/ (grep test)
# ---------------------------------------------------------------------------

class TestNoGenshinReferences:
    def test_no_genshin_in_non_genshin_capsules(self) -> None:
        capsules_dir = Path(__file__).resolve().parent.parent / "capsules"
        if not capsules_dir.exists():
            pytest.skip("capsules/ directory not found")

        for py_file in capsules_dir.rglob("*.py"):
            if "genshin" in py_file.parts:
                continue
            content = py_file.read_text(encoding="utf-8")
            # Non-Genshin capsules must not couple to Genshin-specific imports.
            for line_no, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert "genshin" not in stripped.lower(), (
                    f"Found 'genshin' reference at {py_file}:{line_no}: {line}"
                )

    def test_no_genshin_imports_in_core(self) -> None:
        """core/ must never import genshin-specific code."""
        core_dir = Path(__file__).resolve().parent.parent / "core"
        for py_file in core_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for line_no, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert "genshin" not in stripped.lower(), (
                    f"Found 'genshin' reference at {py_file}:{line_no}: {line}"
                )


# ---------------------------------------------------------------------------
# 5. Capsule activate / deactivate lifecycle
# ---------------------------------------------------------------------------

class TestCapsuleLifecycle:
    def test_activate_deactivate(self) -> None:
        registry = CapsuleRegistry()
        ctx = _make_context()
        capsule = DemoArpgCapsule()
        manifest = _make_manifest(capsule_id="demo_arpg")

        registry.register(capsule, manifest, ctx)
        assert not capsule.is_active

        registry.activate("demo_arpg")
        assert capsule.is_active
        assert "demo_arpg" in registry.list_active()

        registry.deactivate("demo_arpg")
        assert not capsule.is_active
        assert "demo_arpg" not in registry.list_active()

    def test_deactivate_on_unregister(self) -> None:
        registry = CapsuleRegistry()
        ctx = _make_context()
        capsule = DemoArpgCapsule()
        manifest = _make_manifest(capsule_id="demo_arpg")

        registry.register(capsule, manifest, ctx)
        registry.activate("demo_arpg")
        assert capsule.is_active

        registry.unregister("demo_arpg")
        assert not capsule.is_active

    def test_activate_nonexistent_returns_false(self) -> None:
        registry = CapsuleRegistry()
        assert registry.activate("nope") is False

    def test_deactivate_nonexistent_returns_false(self) -> None:
        registry = CapsuleRegistry()
        assert registry.deactivate("nope") is False


# ---------------------------------------------------------------------------
# 6. Multiple capsules coexist without conflict
# ---------------------------------------------------------------------------

class TestMultipleCapsules:
    def test_two_capsules_coexist(self) -> None:
        registry = CapsuleRegistry()
        bus = StateBus()
        ctx = _make_context(bus)

        demo_capsule = DemoArpgCapsule()
        desktop_capsule = DesktopUiCapsule()

        registry.register(
            demo_capsule,
            _make_manifest(capsule_id="demo_arpg"),
            ctx,
        )
        registry.register(
            desktop_capsule,
            _make_manifest(capsule_id="desktop_ui"),
            ctx,
        )

        # Both registered.
        assert set(registry.list_registered()) == {"demo_arpg", "desktop_ui"}

        # Both can be activated.
        registry.activate("demo_arpg")
        registry.activate("desktop_ui")
        assert demo_capsule.is_active
        assert desktop_capsule.is_active
        assert set(registry.list_active()) == {"demo_arpg", "desktop_ui"}

        # Slots don't clash.
        slot_names = bus.registered_slot_names()
        assert "demo_arpg.screen_state" in slot_names
        assert "desktop_ui.grounded_elements" in slot_names

    def test_unregister_one_keeps_other(self) -> None:
        registry = CapsuleRegistry()
        bus = StateBus()
        ctx = _make_context(bus)

        registry.register(
            DemoArpgCapsule(),
            _make_manifest(capsule_id="demo_arpg"),
            ctx,
        )
        registry.register(
            DesktopUiCapsule(),
            _make_manifest(capsule_id="desktop_ui"),
            ctx,
        )

        registry.unregister("demo_arpg")

        assert registry.get("demo_arpg") is None
        assert registry.get("desktop_ui") is not None
        assert "desktop_ui" in registry.list_registered()
        # desktop_ui slots should still exist on the bus.
        assert "desktop_ui.grounded_elements" in bus.registered_slot_names()


# ---------------------------------------------------------------------------
# 7. Capsule failure doesn't crash kernel
# ---------------------------------------------------------------------------

class TestCapsuleFailureIsolation:
    def test_failing_install_raises_but_registry_stays_consistent(self) -> None:
        registry = CapsuleRegistry()
        ctx = _make_context()

        class FailingCapsule:
            capsule_id: str = "fail_capsule"

            def __init__(self) -> None:
                self._active = False

            def install(self, context: CapsuleContext) -> None:
                raise RuntimeError("install exploded")

            def activate(self) -> None:
                self._active = True

            def deactivate(self) -> None:
                self._active = False

            @property
            def is_active(self) -> bool:
                return self._active

            def uninstall(self, context: CapsuleContext) -> None:
                pass

        capsule = FailingCapsule()
        manifest = _make_manifest(capsule_id="fail_capsule")

        with pytest.raises(RuntimeError, match="install exploded"):
            registry.register(capsule, manifest, ctx)

        # Registry should not contain the failed capsule.
        assert registry.get("fail_capsule") is None
        assert "fail_capsule" not in registry.list_registered()

    def test_failing_uninstall_does_not_crash_unregister(self) -> None:
        registry = CapsuleRegistry()
        ctx = _make_context()

        class BadUninstallCapsule:
            capsule_id: str = "bad_uninstall"

            def __init__(self) -> None:
                self._active = False

            def install(self, context: CapsuleContext) -> None:
                pass

            def activate(self) -> None:
                self._active = True

            def deactivate(self) -> None:
                self._active = False

            @property
            def is_active(self) -> bool:
                return self._active

            def uninstall(self, context: CapsuleContext) -> None:
                raise RuntimeError("uninstall exploded")

        capsule = BadUninstallCapsule()
        manifest = _make_manifest(capsule_id="bad_uninstall")
        registry.register(capsule, manifest, ctx)

        # Should still return True even though uninstall raised.
        result = registry.unregister("bad_uninstall")
        assert result is True
        assert registry.get("bad_uninstall") is None


# ---------------------------------------------------------------------------
# 8. CapsuleManifest loaded from YAML
# ---------------------------------------------------------------------------

class TestCapsuleManifestYaml:
    def test_load_demo_arpg_manifest(self) -> None:
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "capsules"
            / "demo_arpg"
            / "capsule.yaml"
        )
        manifest = load_manifest_from_yaml(str(yaml_path))

        assert manifest.capsule_id == "demo_arpg"
        assert manifest.version == "0.1.0"
        assert manifest.display_name == "Demo ARPG"
        assert "demo_arpg.screen_state" in manifest.slots
        assert "demo_arpg.danger_state" in manifest.slots
        assert [skill.skill_id for skill in manifest.skills] == ["dummy_skill"]
        assert "dummy_processor" in manifest.frame_processors
        assert manifest.transitions == []
        assert manifest.benchmark_tasks == []

    def test_load_desktop_ui_manifest(self) -> None:
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "capsules"
            / "desktop_ui"
            / "capsule.yaml"
        )
        manifest = load_manifest_from_yaml(str(yaml_path))

        assert manifest.capsule_id == "desktop_ui"
        assert manifest.version == "0.1.0"
        assert manifest.display_name == "Desktop UI Automation"
        assert "desktop_ui.grounded_elements" in manifest.slots
        assert "desktop_ui.safety_state" in manifest.slots
        assert [skill.skill_id for skill in manifest.skills] == ["ui_grounding_skill"]
        assert manifest.frame_processors == []

    def test_manifest_roundtrip(self, tmp_path: Path) -> None:
        """Write a manifest to YAML and read it back."""
        data = {
            "capsule_id": "roundtrip_test",
            "version": "1.0.0",
            "display_name": "Roundtrip",
            "description": "Test roundtrip",
            "slots": ["rt.slot_a", "rt.slot_b"],
            "skills": ["rt_skill"],
            "frame_processors": ["fp_one"],
            "transitions": [{"from": "A", "to": "B"}],
            "verifiers": ["v1"],
            "failure_bridge": "bridge_mod",
            "persona_bridge": None,
            "benchmark_tasks": ["task_1"],
        }
        yaml_file = tmp_path / "capsule.yaml"
        yaml_file.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

        manifest = load_manifest_from_yaml(str(yaml_file))

        assert manifest.capsule_id == "roundtrip_test"
        assert manifest.version == "1.0.0"
        assert manifest.slots == ["rt.slot_a", "rt.slot_b"]
        assert [skill.skill_id for skill in manifest.skills] == ["rt_skill"]
        assert manifest.frame_processors == ["fp_one"]
        assert manifest.transitions == [{"from": "A", "to": "B"}]
        assert manifest.verifiers == ["v1"]
        assert manifest.failure_bridge == "bridge_mod"
        assert manifest.benchmark_tasks == ["task_1"]

    def test_manifest_v1_declares_resources_and_planner_skill_specs(self, tmp_path: Path) -> None:
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "skills.yaml").write_text("skills: []", encoding="utf-8")
        data = {
            "capsule_id": "manifest_v1",
            "version": "1.0.0",
            "display_name": "Manifest V1",
            "description": "Resource-aware manifest",
            "runtime_package": "capsules.manifest_v1",
            "entrypoint": "capsule_entry:ManifestV1Capsule",
            "capabilities": ["navigation", "combat"],
            "skills": [
                {
                    "skill_id": "manifest_v1.navigate",
                    "capabilities": ["navigate_to_marker"],
                    "resources": ["skill_pack"],
                    "verifiers": ["marker_visible"],
                    "planner_tags": ["long_horizon"],
                }
            ],
            "resources": [
                {
                    "resource_id": "skill_pack",
                    "kind": "skill_yaml",
                    "path": "data/skills.yaml",
                    "description": "Skill declarations",
                }
            ],
            "profiles": ["manifest_v1_1920x1080"],
            "keymaps": {"interact": "F"},
        }
        yaml_file = tmp_path / "capsule.yaml"
        yaml_file.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

        manifest = load_manifest_from_yaml(str(yaml_file))

        assert manifest.runtime_package == "capsules.manifest_v1"
        assert manifest.entrypoint == "capsule_entry:ManifestV1Capsule"
        assert manifest.capabilities == ["navigation", "combat"]
        assert manifest.skills[0].skill_id == "manifest_v1.navigate"
        assert manifest.skills[0].resources == ["skill_pack"]
        assert manifest.resources[0].resource_id == "skill_pack"
        assert manifest.resource_paths(yaml_file)["skill_pack"].exists()


# ---------------------------------------------------------------------------
# 9. Skills work end-to-end through capsules
# ---------------------------------------------------------------------------

class TestCapsuleSkills:
    def test_dummy_skill_returns_success(self) -> None:
        from capsules.demo_arpg.skills.dummy_skill import DummySkill

        skill = DummySkill()
        result = skill.run()
        assert result.status == "SUCCESS"
        assert result.skill_name == "demo_arpg_dummy"
        assert result.payload == {"demo": True}

    def test_ui_grounding_skill_returns_success(self) -> None:
        from capsules.desktop_ui.skills.ui_grounding_skill import UiGroundingSkill

        skill = UiGroundingSkill()
        result = skill.run()
        assert result.status == "SUCCESS"
        assert result.skill_name == "desktop_ui_grounding"
        assert result.payload["safety_check"] == "pass"

    def test_skill_registered_with_orchestrator(self) -> None:
        bus = StateBus()
        ctx = _make_context(bus)
        capsule = DemoArpgCapsule()
        capsule.install(ctx)

        # The mock orchestrator should have register_skill called.
        ctx.orchestrator.register_skill.assert_called_once()
        call_args = ctx.orchestrator.register_skill.call_args
        assert call_args[0][0] == "demo_arpg_dummy"

        # The registered skill should return SUCCESS.
        registered_skill = call_args[0][1]
        result = registered_skill.run()
        assert result.status == "SUCCESS"
