#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from capsules.capsule_protocol import load_manifest_from_yaml
from interaction.capsule_anchors import anchors_from_manifest


@dataclass(frozen=True, slots=True)
class CapsuleValidationReport:
    capsule_id: str
    ok: bool
    issues: list[str] = field(default_factory=list)
    resources_checked: int = 0
    anchors_checked: int = 0


def validate_capsule(root: Path, capsule_id: str) -> CapsuleValidationReport:
    manifest_path = root / "capsules" / capsule_id / "capsule.yaml"
    issues: list[str] = []
    if not manifest_path.exists():
        return CapsuleValidationReport(capsule_id, False, [f"missing_manifest:{manifest_path}"])
    manifest = load_manifest_from_yaml(str(manifest_path))
    if manifest.capsule_id != capsule_id:
        issues.append(f"capsule_id_mismatch:{manifest.capsule_id}!={capsule_id}")
    resources = manifest.resource_paths(manifest_path)
    for resource_id, path in resources.items():
        spec = next((r for r in manifest.resources if r.resource_id == resource_id), None)
        if spec is not None and not spec.optional and not path.exists():
            issues.append(f"missing_required_resource:{resource_id}:{path}")
    for anchor in anchors_from_manifest(manifest):
        if not anchor.anchor_id:
            issues.append("anchor_missing_id")
        if not anchor.matchers:
            issues.append(f"anchor_missing_matchers:{anchor.anchor_id}")
        if not anchor.post_action_verifier:
            issues.append(f"anchor_missing_post_verifier:{anchor.anchor_id}")
    return CapsuleValidationReport(
        capsule_id,
        ok=not issues,
        issues=issues,
        resources_checked=len(resources),
        anchors_checked=len(anchors_from_manifest(manifest)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an Aurora capsule manifest and resources")
    parser.add_argument("capsule_id")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    report = validate_capsule(Path(args.root), args.capsule_id)
    print(f"capsule={report.capsule_id} ok={report.ok} resources={report.resources_checked} anchors={report.anchors_checked}")
    for issue in report.issues:
        print(f"ISSUE {issue}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
