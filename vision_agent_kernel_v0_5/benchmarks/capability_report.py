"""Capability report: generates and saves detailed reports on registered capsule capabilities."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from capsules.capsule_protocol import CapsuleManifest
from capsules.capsule_registry import CapsuleRegistry
from planning.skill_capability_catalog import SkillCatalogEntry, SkillCapabilityCatalog

logger = logging.getLogger("capability_report")


@dataclass
class CapabilityReport:
    """Dataclass holding all aggregated capability and coverage metrics."""
    installed_capsules: List[str]
    capability_count: int
    skills_per_capability: Dict[str, int]
    verifier_coverage_rate: float
    resources_available_rate: float
    strict_mode_executable_rate: float
    missing_capabilities: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert CapabilityReport to a dictionary suitable for JSON serialization."""
        return {
            "installed_capsules": self.installed_capsules,
            "capability_count": self.capability_count,
            "skills_per_capability": self.skills_per_capability,
            "verifier_coverage_rate": self.verifier_coverage_rate,
            "resources_available_rate": self.resources_available_rate,
            "strict_mode_executable_rate": self.strict_mode_executable_rate,
            "missing_capabilities": self.missing_capabilities,
            "metadata": self.metadata,
        }


class CapabilityReportBuilder:
    """Helper to build, render, and persist capability reports."""

    def __init__(self, output_dir: str | Path = "benchmark_reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        registry: CapsuleRegistry,
        catalog: SkillCapabilityCatalog,
        metadata: Dict[str, Any] | None = None,
    ) -> CapabilityReport:
        """Analyze capsule and skill catalog states to compile a CapabilityReport."""
        installed_capsules = registry.list_registered()

        # Gather all entries belonging to the registered capsules
        entries = [entry for entry in catalog.entries() if entry.capsule_id in installed_capsules]

        # 1. Total unique capabilities provided by skills
        provided_caps = set()
        for entry in entries:
            # We look at both capabilities and capabilities_provided to be fully comprehensive
            caps_set = set(entry.capabilities_provided) | set(entry.capabilities)
            provided_caps.update(caps_set)
        capability_count = len(provided_caps)

        # 2. Skills per capability
        skills_per_cap: Dict[str, int] = {}
        for entry in entries:
            caps_set = set(entry.capabilities_provided) | set(entry.capabilities)
            for cap in caps_set:
                skills_per_cap[cap] = skills_per_cap.get(cap, 0) + 1

        # 3. Verifier coverage rate
        if not entries:
            verifier_coverage_rate = 1.0
        else:
            verified_count = sum(1 for entry in entries if len(entry.verifiers) > 0)
            verifier_coverage_rate = verified_count / len(entries)

        # 4. Resources available rate
        total_non_optional = 0
        available_non_optional = 0
        for cid in installed_capsules:
            manifest = registry.manifest(cid)
            if not manifest:
                continue
            manifest_path = registry._manifest_paths.get(cid) if hasattr(registry, "_manifest_paths") else None
            
            paths_dict = {}
            if manifest_path:
                try:
                    paths_dict = manifest.resource_paths(manifest_path)
                except Exception:
                    pass

            for res in manifest.resources:
                if not res.optional:
                    total_non_optional += 1
                    path = paths_dict.get(res.resource_id)
                    if not path:
                        path = Path(res.path)
                    if path.exists():
                        available_non_optional += 1

        resources_available_rate = (
            available_non_optional / total_non_optional if total_non_optional > 0 else 1.0
        )

        # 5. Strict mode executable rate
        if not entries:
            strict_mode_executable_rate = 1.0
        else:
            executable_count = 0
            for entry in entries:
                is_high_risk = entry.risk_level in ("high", "human_confirm")
                has_verifiers = len(entry.verifiers) > 0
                if is_high_risk and not has_verifiers:
                    continue
                executable_count += 1
            strict_mode_executable_rate = executable_count / len(entries)

        # 6. Missing capabilities (declared in manifest.capabilities but not provided by any skill in that capsule)
        missing_capabilities: List[str] = []
        for cid in installed_capsules:
            manifest = registry.manifest(cid)
            if not manifest:
                continue
            declared_caps = manifest.capabilities
            caps_for_cid = set()
            for entry in entries:
                if entry.capsule_id == cid:
                    caps_for_cid.update(entry.capabilities_provided)
                    caps_for_cid.update(entry.capabilities)
            for cap in declared_caps:
                if cap not in caps_for_cid:
                    missing_capabilities.append(cap)

        return CapabilityReport(
            installed_capsules=installed_capsules,
            capability_count=capability_count,
            skills_per_capability=skills_per_cap,
            verifier_coverage_rate=verifier_coverage_rate,
            resources_available_rate=resources_available_rate,
            strict_mode_executable_rate=strict_mode_executable_rate,
            missing_capabilities=missing_capabilities,
            metadata=metadata or {},
        )

    def render_markdown(self, report: CapabilityReport) -> str:
        """Render CapabilityReport as a markdown string."""
        lines = [
            "# AuroraBench Capability Report",
            "",
            "## Summary",
            "",
            f"- **Installed Capsules**: {', '.join(report.installed_capsules) if report.installed_capsules else 'None'}",
            f"- **Unique Capabilities Count**: {report.capability_count}",
            f"- **Verifier Coverage Rate**: {report.verifier_coverage_rate:.2%}",
            f"- **Non-Optional Resources Available Rate**: {report.resources_available_rate:.2%}",
            f"- **Strict-Mode Executable Rate**: {report.strict_mode_executable_rate:.2%}",
            "",
            "## Skills Per Capability",
            "",
            "| Capability | Skills Count |",
            "| :--- | :--- |",
        ]
        
        for cap, count in sorted(report.skills_per_capability.items()):
            lines.append(f"| `{cap}` | {count} |")
        
        if not report.skills_per_capability:
            lines.append("| *No Capabilities Found* | - |")

        lines.extend([
            "",
            "## Missing Capabilities",
            "",
            "> [!NOTE]",
            "> Missing capabilities are declared in the `capsule.yaml` but do not currently map to any skill.",
            "",
        ])

        if report.missing_capabilities:
            for cap in sorted(report.missing_capabilities):
                lines.append(f"- [ ] `{cap}`")
        else:
            lines.append("*None! All declared capabilities are fully backed by capsule skills.*")

        lines.append("")
        return "\n".join(lines)

    def save_report(
        self,
        report: CapabilityReport,
        filename_prefix: str = "capability_report",
    ) -> Tuple[Path, Path]:
        """Save CapabilityReport as JSON and Markdown. Returns (json_path, md_path)."""
        json_path = self.output_dir / f"{filename_prefix}.json"
        md_path = self.output_dir / f"{filename_prefix}.md"

        # Save JSON
        json_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Save MD
        md = self.render_markdown(report)
        md_path.write_text(md, encoding="utf-8")

        logger.info("Capability report successfully written to %s and %s", json_path, md_path)
        return json_path, md_path
