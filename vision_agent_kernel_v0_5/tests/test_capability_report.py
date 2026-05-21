"""Tests for the CapabilityReport and CapabilityReportBuilder."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from benchmarks.capability_report import CapabilityReport, CapabilityReportBuilder
from capsules.capsule_protocol import CapsuleManifest, load_manifest_from_yaml
from capsules.capsule_registry import CapsuleRegistry
from planning.skill_capability_catalog import SkillCatalogEntry, SkillCapabilityCatalog


@pytest.fixture
def temp_report_dir(tmp_path: Path) -> Path:
    return tmp_path / "reports"


def test_capability_report_contains_two_capsules(temp_report_dir: Path) -> None:
    """Verify that CapabilityReportBuilder aggregates metrics correctly for multiple registered capsules."""
    # 1. Load manifests from workspace
    project_root = Path(__file__).resolve().parents[1]
    genshin_yaml = project_root / "capsules" / "genshin" / "capsule.yaml"
    hsr_yaml = project_root / "capsules" / "hsr" / "capsule.yaml"

    genshin_manifest = load_manifest_from_yaml(str(genshin_yaml))
    hsr_manifest = load_manifest_from_yaml(str(hsr_yaml))

    # 2. Setup mock registry
    registry = CapsuleRegistry()
    
    # We cheat registration without invoking install by manually adding them to Registry
    registry._manifests["genshin"] = genshin_manifest
    registry._capsules["genshin"] = MagicMock()
    
    registry._manifests["hsr"] = hsr_manifest
    registry._capsules["hsr"] = MagicMock()

    # 3. Create merged catalog
    catalog = SkillCapabilityCatalog.from_sources(manifests=[genshin_manifest, hsr_manifest])

    # 4. Generate report
    builder = CapabilityReportBuilder(output_dir=temp_report_dir)
    report = builder.generate_report(registry, catalog)

    # 5. Assert report metrics
    assert "genshin" in report.installed_capsules
    assert "hsr" in report.installed_capsules
    
    # Check capability counts and unique keys
    assert report.capability_count > 0
    assert "hsr_turn_based_combat" in report.skills_per_capability
    assert "combat_playbook_execution" in report.skills_per_capability
    
    # Check rates are float values between 0.0 and 1.0
    assert 0.0 <= report.verifier_coverage_rate <= 1.0
    assert 0.0 <= report.resources_available_rate <= 1.0
    assert 0.0 <= report.strict_mode_executable_rate <= 1.0

    # 6. Verify save capability report formats
    json_path, md_path = builder.save_report(report, filename_prefix="two_games_report")
    assert json_path.exists()
    assert md_path.exists()

    # Verify JSON content is valid
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
        assert data["capability_count"] == report.capability_count
        assert "genshin" in data["installed_capsules"]

    # Verify MD content is valid
    md_content = md_path.read_text(encoding="utf-8")
    assert "# AuroraBench Capability Report" in md_content
    assert "genshin" in md_content
    assert "hsr" in md_content
