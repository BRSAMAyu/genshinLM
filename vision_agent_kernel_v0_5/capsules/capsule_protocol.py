from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources as importlib_resources
from pathlib import Path
from typing import Any, Protocol

from core.state_bus import StateBus


@dataclass(slots=True)
class CapsuleContext:
    """Context provided to a capsule during install."""

    state_bus: StateBus
    pipeline: Any  # PerceptionPipeline
    orchestrator: Any  # Orchestrator
    mode_arbiter: Any  # ModeArbiter


class Capsule(Protocol):
    """Protocol for app capsules. Zero core/ pollution."""

    capsule_id: str

    def install(self, context: CapsuleContext) -> None:
        """Register slots, post-processors, skills, transitions."""
        ...

    def activate(self) -> None:
        """Start the capsule."""
        ...

    def deactivate(self) -> None:
        """Stop the capsule."""
        ...

    @property
    def is_active(self) -> bool:
        ...

    def uninstall(self, context: CapsuleContext) -> None:
        """Clean up: remove subscriptions, clear slots."""
        ...


@dataclass(slots=True)
class CapsuleResource:
    """A resource supplied by a capsule without making it part of core runtime."""

    resource_id: str
    kind: str
    path: str
    optional: bool = False
    description: str = ""


@dataclass(slots=True)
class CapsuleSkillSpec:
    """Planner-facing declaration for a capsule skill."""

    skill_id: str
    kind: str = "skill"
    capabilities: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    verifiers: list[str] = field(default_factory=list)
    planner_tags: list[str] = field(default_factory=list)
    capabilities_required: list[str] = field(default_factory=list)
    capabilities_provided: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    failure_modes: list[dict] = field(default_factory=list)
    recovery_policy: dict = field(default_factory=dict)


@dataclass(slots=True)
class CapsuleManifest:
    """Declares what a capsule provides/needs. Loaded from capsule.yaml."""

    capsule_id: str
    version: str
    display_name: str
    description: str
    runtime_package: str = ""
    entrypoint: str = ""
    capabilities: list[str] = field(default_factory=list)
    frame_processors: list[str] = field(default_factory=list)
    slots: list[str] = field(default_factory=list)
    skills: list[CapsuleSkillSpec] = field(default_factory=list)
    transitions: list[dict[str, str]] = field(default_factory=list)
    verifiers: list[str] = field(default_factory=list)
    detectors: list[str] = field(default_factory=list)
    keymaps: dict[str, str] = field(default_factory=dict)
    resources: list[CapsuleResource] = field(default_factory=list)
    profiles: list[str] = field(default_factory=list)
    failure_bridge: str | None = None
    persona_bridge: str | None = None
    benchmark_tasks: list[str] = field(default_factory=list)
    providers: dict[str, str] = field(default_factory=dict)
    ui_anchors: list[dict[str, Any]] = field(default_factory=list)

    def resource_paths(self, manifest_path: str | Path) -> dict[str, Path]:
        base = Path(manifest_path).resolve().parent
        return {res.resource_id: _resolve_resource_path(base, res.path) for res in self.resources}


def _resolve_resource_path(base: Path, path: str) -> Path:
    if path.startswith("pkg://"):
        package_and_resource = path.removeprefix("pkg://")
        package, _, resource = package_and_resource.partition("/")
        if not package or not resource:
            raise ValueError(f"invalid package resource URI: {path}")
        return Path(str(importlib_resources.files(package).joinpath(resource))).resolve()
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base / candidate).resolve()


def load_manifest_from_yaml(path: str) -> CapsuleManifest:
    """Load a CapsuleManifest from a capsule.yaml file."""
    import yaml

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    def _skill(value: object) -> CapsuleSkillSpec:
        if isinstance(value, str):
            return CapsuleSkillSpec(
                skill_id=value,
                capabilities_provided=[value],
            )
        item = dict(value or {})
        caps = list(item.get("capabilities", []))
        caps_prov = list(item.get("capabilities_provided", []))
        if not caps_prov:
            caps_prov = caps
        return CapsuleSkillSpec(
            skill_id=str(item["skill_id"]),
            kind=str(item.get("kind", "skill")),
            capabilities=caps,
            resources=list(item.get("resources", [])),
            verifiers=list(item.get("verifiers", [])),
            planner_tags=list(item.get("planner_tags", [])),
            capabilities_required=list(item.get("capabilities_required", [])),
            capabilities_provided=caps_prov,
            risk_level=str(item.get("risk_level", "medium")),
            failure_modes=list(item.get("failure_modes", [])),
            recovery_policy=dict(item.get("recovery_policy", {})),
        )

    def _resource(value: object) -> CapsuleResource:
        if isinstance(value, str):
            return CapsuleResource(resource_id=value, kind="file", path=value)
        item = dict(value or {})
        return CapsuleResource(
            resource_id=str(item["resource_id"]),
            kind=str(item.get("kind", "file")),
            path=str(item["path"]),
            optional=bool(item.get("optional", False)),
            description=str(item.get("description", "")),
        )

    return CapsuleManifest(
        capsule_id=data["capsule_id"],
        version=data["version"],
        display_name=data["display_name"],
        description=data["description"],
        runtime_package=str(data.get("runtime_package", "")),
        entrypoint=str(data.get("entrypoint", "")),
        capabilities=list(data.get("capabilities", [])),
        frame_processors=data.get("frame_processors", []),
        slots=data.get("slots", []),
        skills=[_skill(item) for item in data.get("skills", [])],
        transitions=data.get("transitions", []),
        verifiers=data.get("verifiers", []),
        detectors=data.get("detectors", []),
        keymaps=dict(data.get("keymaps", {})),
        resources=[_resource(item) for item in data.get("resources", [])],
        profiles=list(data.get("profiles", [])),
        failure_bridge=data.get("failure_bridge"),
        persona_bridge=data.get("persona_bridge"),
        benchmark_tasks=data.get("benchmark_tasks", []),
        providers=dict(data.get("providers", {})),
        ui_anchors=list(data.get("ui_anchors", [])),
    )
