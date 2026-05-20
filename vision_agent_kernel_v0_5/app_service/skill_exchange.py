from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class SkillManifest:
    skill_id: str
    name: str
    version: str
    author: str
    description: str
    created_at: str
    game_version: str
    tags: list[str]
    content_hash: str


@dataclass(frozen=True, slots=True)
class ExportBundle:
    manifest: SkillManifest
    skill_data: dict
    knowledge_deps: list[str]
    profile_requirements: list[str]


_REQUIRED_MANIFEST_FIELDS = (
    "skill_id",
    "name",
    "version",
    "author",
    "description",
    "created_at",
    "game_version",
    "tags",
)

_CURRENT_GAME_VERSION = "5.0"
_VERSION_COMPAT_MARGIN = 1


class SkillExchange:
    """Import/export community skills with validation and versioning."""

    def __init__(self, exchange_dir: Path | None = None) -> None:
        self._dir = exchange_dir or Path("data/skill_exchange")
        self._dir.mkdir(parents=True, exist_ok=True)

    def export_skill(self, skill_id: str, skills_dir: Path) -> Path:
        """Export a skill to a shareable JSON bundle."""
        for yaml_path in skills_dir.glob("genshin_*.yaml"):
            if yaml_path.name == "genshin_skill_index.yaml":
                continue
            with yaml_path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not data or "skills" not in data:
                continue
            for skill_key, skill_data in data["skills"].items():
                if skill_key != skill_id:
                    continue
                content_hash = self._compute_hash(skill_data)
                tags = skill_data.get("tags", [skill_data.get("type", "general")])
                if isinstance(tags, str):
                    tags = [tags]
                manifest = SkillManifest(
                    skill_id=skill_id,
                    name=skill_data.get("name", skill_id),
                    version=skill_data.get("version", "1.0.0"),
                    author=skill_data.get("author", "unknown"),
                    description=skill_data.get("description", ""),
                    created_at=skill_data.get("created_at", ""),
                    game_version=skill_data.get("game_version", _CURRENT_GAME_VERSION),
                    tags=tags,
                    content_hash=content_hash,
                )
                bundle = ExportBundle(
                    manifest=manifest,
                    skill_data=skill_data,
                    knowledge_deps=skill_data.get("knowledge_deps", []),
                    profile_requirements=skill_data.get("profile_requirements", []),
                )
                out_path = self._dir / f"{skill_id}.genshin_skill.json"
                out_path.write_text(self._serialize_bundle(bundle), encoding="utf-8")
                return out_path

        raise FileNotFoundError(f"Skill not found: {skill_id}")

    def import_skill(self, bundle_path: Path, skills_dir: Path) -> str:
        """Import a skill bundle from the community."""
        json_str = bundle_path.read_text(encoding="utf-8")
        bundle = self._deserialize_bundle(json_str)

        is_valid, issues = self._validate_bundle_internal(bundle)
        if not is_valid:
            raise ValueError(f"Invalid bundle: {issues}")

        skill_id = bundle.manifest.skill_id
        target_file = skills_dir / f"genshin_{skill_id}.yaml"

        existing_data: dict = {}
        if target_file.exists():
            with target_file.open(encoding="utf-8") as fh:
                existing_data = yaml.safe_load(fh) or {}

        skills_map: dict = existing_data.get("skills", {})
        skills_map[skill_id] = bundle.skill_data
        existing_data["skills"] = skills_map

        target_file.parent.mkdir(parents=True, exist_ok=True)
        with target_file.open("w", encoding="utf-8") as fh:
            yaml.dump(existing_data, fh, allow_unicode=True, default_flow_style=False)

        return skill_id

    def validate_bundle(self, bundle_path: Path) -> tuple[bool, list[str]]:
        """Validate a skill bundle without installing."""
        json_str = bundle_path.read_text(encoding="utf-8")
        bundle = self._deserialize_bundle(json_str)
        return self._validate_bundle_internal(bundle)

    def list_available(self) -> list[SkillManifest]:
        """List all skills in the exchange directory."""
        manifests: list[SkillManifest] = []
        for path in sorted(self._dir.glob("*.genshin_skill.json")):
            try:
                json_str = path.read_text(encoding="utf-8")
                bundle = self._deserialize_bundle(json_str)
                manifests.append(bundle.manifest)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return manifests

    def _compute_hash(self, data: dict) -> str:
        """Compute SHA256 hash of skill content."""
        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _check_version_compat(self, game_version: str) -> tuple[bool, str]:
        """Check if skill's game version is compatible with current version."""
        try:
            skill_major = int(game_version.split(".")[0])
            current_major = int(_CURRENT_GAME_VERSION.split(".")[0])
        except (ValueError, IndexError):
            return False, f"Cannot parse game version: {game_version}"
        if abs(skill_major - current_major) <= _VERSION_COMPAT_MARGIN:
            return True, ""
        return (
            False,
            f"Game version {game_version} not compatible with {_CURRENT_GAME_VERSION}",
        )

    def _serialize_bundle(self, bundle: ExportBundle) -> str:
        """Serialize export bundle to JSON string."""
        obj = {
            "manifest": {
                "skill_id": bundle.manifest.skill_id,
                "name": bundle.manifest.name,
                "version": bundle.manifest.version,
                "author": bundle.manifest.author,
                "description": bundle.manifest.description,
                "created_at": bundle.manifest.created_at,
                "game_version": bundle.manifest.game_version,
                "tags": bundle.manifest.tags,
                "content_hash": bundle.manifest.content_hash,
            },
            "skill_data": bundle.skill_data,
            "knowledge_deps": bundle.knowledge_deps,
            "profile_requirements": bundle.profile_requirements,
        }
        return json.dumps(obj, indent=2, ensure_ascii=False)

    def _deserialize_bundle(self, json_str: str) -> ExportBundle:
        """Deserialize JSON string to export bundle."""
        obj = json.loads(json_str)
        m = obj["manifest"]
        manifest = SkillManifest(
            skill_id=m["skill_id"],
            name=m["name"],
            version=m["version"],
            author=m["author"],
            description=m["description"],
            created_at=m["created_at"],
            game_version=m["game_version"],
            tags=list(m["tags"]),
            content_hash=m["content_hash"],
        )
        return ExportBundle(
            manifest=manifest,
            skill_data=obj["skill_data"],
            knowledge_deps=list(obj.get("knowledge_deps", [])),
            profile_requirements=list(obj.get("profile_requirements", [])),
        )

    def _validate_bundle_internal(self, bundle: ExportBundle) -> tuple[bool, list[str]]:
        """Validate bundle contents."""
        issues: list[str] = []
        manifest = bundle.manifest
        for field in _REQUIRED_MANIFEST_FIELDS:
            val = getattr(manifest, field, None)
            if not val:
                issues.append(f"Missing or empty manifest field: {field}")

        expected_hash = self._compute_hash(bundle.skill_data)
        if manifest.content_hash != expected_hash:
            issues.append(
                f"Content hash mismatch: expected {expected_hash}, "
                f"got {manifest.content_hash}"
            )

        compat_ok, compat_msg = self._check_version_compat(manifest.game_version)
        if not compat_ok:
            issues.append(compat_msg)

        return (len(issues) == 0, issues)
