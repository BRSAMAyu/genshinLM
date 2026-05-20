from __future__ import annotations

from dataclasses import dataclass, field
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
class CapsuleManifest:
    """Declares what a capsule provides/needs. Loaded from capsule.yaml."""

    capsule_id: str
    version: str
    display_name: str
    description: str
    frame_processors: list[str] = field(default_factory=list)
    slots: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    transitions: list[dict[str, str]] = field(default_factory=list)
    verifiers: list[str] = field(default_factory=list)
    failure_bridge: str | None = None
    persona_bridge: str | None = None
    benchmark_tasks: list[str] = field(default_factory=list)


def load_manifest_from_yaml(path: str) -> CapsuleManifest:
    """Load a CapsuleManifest from a capsule.yaml file."""
    import yaml

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return CapsuleManifest(
        capsule_id=data["capsule_id"],
        version=data["version"],
        display_name=data["display_name"],
        description=data["description"],
        frame_processors=data.get("frame_processors", []),
        slots=data.get("slots", []),
        skills=data.get("skills", []),
        transitions=data.get("transitions", []),
        verifiers=data.get("verifiers", []),
        failure_bridge=data.get("failure_bridge"),
        persona_bridge=data.get("persona_bridge"),
        benchmark_tasks=data.get("benchmark_tasks", []),
    )
