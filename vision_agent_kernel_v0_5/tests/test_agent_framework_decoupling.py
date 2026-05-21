from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from app_service.skill_manager import SkillRecorder, SkillStore, SkillValidationError
from capsules.capsule_protocol import CapsuleContext, load_manifest_from_yaml
from capsules.capsule_registry import CapsuleRegistry
from capsules.genshin.capsule_entry import GenshinCapsule
from core.state_bus import StateBus
from orchestration.orchestrator import Orchestrator
from perception.pipeline import PerceptionPipeline
from planning.skill_capability_catalog import SkillCapabilityCatalog


def _make_context(state_bus: StateBus | None = None) -> CapsuleContext:
    return CapsuleContext(
        state_bus=state_bus or StateBus(),
        pipeline=MagicMock(),
        orchestrator=MagicMock(),
        mode_arbiter=MagicMock(),
    )


def _write_profile(root: Path, profile_id: str = "default_1920x1080") -> None:
    profiles = root / "configs" / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / f"{profile_id}.json").write_text(
        '{"profile_id":"default_1920x1080","window_title":"unit","source_resolution":[1920,1080],"normalized_resolution":[1280,720],"rois":{}}',
        encoding="utf-8",
    )


def test_recorded_skill_is_saved_as_framework_contract(tmp_path: Path) -> None:
    _write_profile(tmp_path)
    recorder = SkillRecorder()
    recorder.start(backend_name="mock", focus_state="FOCUSED", target_state="TRACKED")
    draft = recorder.stop()
    payload = recorder.draft_to_skill_payload(draft, skill_id="recorded_contract", name="Recorded Contract")

    skill = SkillStore(tmp_path).save_skill(payload)

    assert skill.capsule_id == "core"
    assert "recorded_replay" in skill.capabilities
    assert skill.resources[0]["kind"] == "recording"
    assert skill.verifier_contracts[0]["verifier_id"] == "visual_checkpoint"
    assert skill.planner["cost"] == "low"


def test_skill_contract_requires_resource_shape(tmp_path: Path) -> None:
    _write_profile(tmp_path)
    recorder = SkillRecorder()
    recorder.start(backend_name="mock")
    payload = recorder.draft_to_skill_payload(recorder.stop(), skill_id="bad_contract", name="Bad Contract")
    payload["resources"] = [{"kind": "recording"}]

    try:
        SkillStore(tmp_path).save_skill(payload)
    except SkillValidationError as exc:
        assert "resources[0].uri is required" in str(exc)
    else:
        raise AssertionError("expected invalid resource contract to be rejected")


def test_genshin_capsule_manifest_declares_optional_game_package_boundary() -> None:
    manifest_path = Path(__file__).resolve().parent.parent / "capsules" / "genshin" / "capsule.yaml"
    manifest = load_manifest_from_yaml(str(manifest_path))

    assert manifest.capsule_id == "genshin"
    assert manifest.entrypoint == "capsule_entry:GenshinCapsule"
    assert "arpg_combat" in manifest.capabilities
    assert "genshin.screen_state" in manifest.slots
    assert {skill.skill_id for skill in manifest.skills} >= {"genshin_combat", "genshin_dodge"}
    assert manifest.resource_paths(manifest_path)["genshin_profile"].exists()


def test_registry_validates_capsule_resources_and_exposes_catalog() -> None:
    manifest_path = Path(__file__).resolve().parent.parent / "capsules" / "genshin" / "capsule.yaml"
    manifest = load_manifest_from_yaml(str(manifest_path))
    registry = CapsuleRegistry()
    ctx = _make_context(StateBus())

    registry.register(GenshinCapsule(), manifest, ctx, manifest_path=manifest_path)

    catalog = registry.skill_catalog()
    assert any(row["skill_id"] == "genshin_combat" for row in catalog)
    assert any(row["capsule_id"] == "genshin" for row in catalog)
    assert "genshin" in registry.list_registered()


def test_registry_unregister_cleans_genshin_runtime_artifacts() -> None:
    manifest_path = Path(__file__).resolve().parent.parent / "capsules" / "genshin" / "capsule.yaml"
    manifest = load_manifest_from_yaml(str(manifest_path))
    bus = StateBus()
    pipeline = PerceptionPipeline(capturer=MagicMock(), state_bus=bus)
    orchestrator = Orchestrator(state_bus=bus, skills={})
    ctx = CapsuleContext(
        state_bus=bus,
        pipeline=pipeline,
        orchestrator=orchestrator,
        mode_arbiter=MagicMock(),
    )
    registry = CapsuleRegistry()

    registry.register(GenshinCapsule(), manifest, ctx, manifest_path=manifest_path)
    assert "genshin.screen_state" in bus.registered_slot_names()
    assert "genshin_combat" in orchestrator.skill_names()
    assert orchestrator.custom_transitions_snapshot()
    assert pipeline.post_processors_snapshot()

    assert registry.unregister("genshin") is True

    assert not any(name.startswith("genshin.") for name in bus.registered_slot_names())
    assert "genshin_combat" not in orchestrator.skill_names()
    assert "genshin_dodge" not in orchestrator.skill_names()
    assert orchestrator.custom_transitions_snapshot() == []
    assert pipeline.post_processors_snapshot() == []
    assert bus.subscription_ids() == []


def test_registry_rejects_missing_required_capsule_resource(tmp_path: Path) -> None:
    manifest_data = {
        "capsule_id": "missing_resource",
        "version": "1.0.0",
        "display_name": "Missing Resource",
        "description": "Should fail validation",
        "resources": [{"resource_id": "missing", "kind": "yaml", "path": "missing.yaml"}],
    }
    manifest_path = tmp_path / "capsule.yaml"
    manifest_path.write_text(yaml.dump(manifest_data), encoding="utf-8")
    manifest = load_manifest_from_yaml(str(manifest_path))

    class MissingResourceCapsule:
        capsule_id = "missing_resource"

        def install(self, context) -> None:
            pass

        def activate(self) -> None:
            pass

        def deactivate(self) -> None:
            pass

        @property
        def is_active(self) -> bool:
            return False

        def uninstall(self, context) -> None:
            pass

    try:
        CapsuleRegistry().register(
            MissingResourceCapsule(),
            manifest,
            _make_context(StateBus()),
            manifest_path=manifest_path,
        )
    except FileNotFoundError as exc:
        assert "resource 'missing' not found" in str(exc)
    else:
        raise AssertionError("expected missing required resource to be rejected")


def test_capsule_manifest_supports_package_resource_uri(tmp_path: Path) -> None:
    manifest_data = {
        "capsule_id": "pkg_resource",
        "version": "1.0.0",
        "display_name": "Package Resource",
        "description": "Package URI support",
        "resources": [
            {
                "resource_id": "manifest",
                "kind": "yaml",
                "path": "pkg://capsules.genshin/capsule.yaml",
            }
        ],
    }
    manifest_path = tmp_path / "capsule.yaml"
    manifest_path.write_text(yaml.dump(manifest_data), encoding="utf-8")
    manifest = load_manifest_from_yaml(str(manifest_path))

    assert manifest.resource_paths(manifest_path)["manifest"].exists()


def test_skill_capability_catalog_merges_saved_skills_and_capsules(tmp_path: Path) -> None:
    _write_profile(tmp_path)
    recorder = SkillRecorder()
    recorder.start(backend_name="mock")
    payload = recorder.draft_to_skill_payload(recorder.stop(), skill_id="recorded_contract", name="Recorded Contract")
    saved = SkillStore(tmp_path).save_skill(payload)
    manifest = load_manifest_from_yaml(
        str(Path(__file__).resolve().parent.parent / "capsules" / "genshin" / "capsule.yaml")
    )

    catalog = SkillCapabilityCatalog.from_sources(skills=[saved], manifests=[manifest])

    assert catalog.by_capability("recorded_replay")[0].source == "skill_store"
    assert catalog.by_capability("combat_playbook_execution")[0].capsule_id == "genshin"
    assert catalog.missing_capabilities(["recorded_replay", "nonexistent"]) == ["nonexistent"]


def test_skill_capability_catalog_dedupes_with_capsule_manifest_precedence(tmp_path: Path) -> None:
    _write_profile(tmp_path)
    recorder = SkillRecorder()
    recorder.start(backend_name="mock")
    payload = recorder.draft_to_skill_payload(recorder.stop(), skill_id="genshin_combat", name="Local Shadow")
    saved = SkillStore(tmp_path).save_skill(payload)
    manifest = load_manifest_from_yaml(
        str(Path(__file__).resolve().parent.parent / "capsules" / "genshin" / "capsule.yaml")
    )

    catalog = SkillCapabilityCatalog.from_sources(skills=[saved], manifests=[manifest])
    entries = [entry for entry in catalog.entries() if entry.skill_id == "genshin_combat"]

    assert len(entries) == 1
    assert entries[0].source == "capsule_manifest"
    assert "combat_playbook_execution" in entries[0].capabilities
