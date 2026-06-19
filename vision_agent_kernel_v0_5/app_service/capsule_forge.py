"""CapsuleForge — auto-generate game capsule skeletons with LLM-driven code generation.

Generates:
- capsule.yaml manifest
- keymap.yaml (default WASD layout)
- skills/index.json
- detectors/<game_id>_screen_classifier.py (template)
- detectors/<game_id>_combat_detector.py (template)
- providers/<game_id>_provider.py (template)

When an LLM backend is available, generates richer code from a game description.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ForgeResult:
    game_id: str
    capsule_dir: Path
    files_created: list[str] = field(default_factory=list)


class LlmBackend(Protocol):
    """Protocol for LLM code generation backend."""
    def generate(self, prompt: str) -> str: ...


class StubLlmBackend:
    """No-op LLM backend — generates template code only."""

    def generate(self, prompt: str) -> str:
        return ""


class CapsuleForge:
    _GAME_ID_RE = re.compile(r"^[a-zA-Z0-9_]+$")

    def __init__(self, llm: LlmBackend | None = None) -> None:
        self._llm = llm

    def forge(
        self,
        game_name: str,
        game_description: str = "",
        output_dir: str | None = None,
    ) -> ForgeResult:
        game_id = self._sanitize(game_name)
        if not game_id:
            raise ValueError("game_name must be non-empty and contain only alphanumeric characters and underscores")
        if not self._GAME_ID_RE.match(game_id):
            raise ValueError("game_name must be non-empty and contain only alphanumeric characters and underscores")

        capsule_dir = Path(output_dir).resolve() if output_dir else (Path("capsules") / game_id).resolve()
        files_created: list[str] = []

        # Create directory structure
        for subdir in ("", "detectors", "providers", "skills"):
            (capsule_dir / subdir).mkdir(parents=True, exist_ok=True)

        # 1. capsule.yaml
        manifest_path = capsule_dir / "capsule.yaml"
        self._write_manifest(manifest_path, game_id, game_name, game_description)
        files_created.append(str(manifest_path))

        # 2. keymap.yaml
        keymap_path = capsule_dir / "keymap.yaml"
        self._write_keymap(keymap_path)
        files_created.append(str(keymap_path))

        # 3. skills/index.json
        index_path = capsule_dir / "skills" / "index.json"
        self._write_skill_index(index_path, game_id)
        files_created.append(str(index_path))

        # 4. Screen classifier detector
        classifier_path = capsule_dir / "detectors" / f"{game_id}_screen_classifier.py"
        self._write_screen_classifier(classifier_path, game_id, game_description)
        files_created.append(str(classifier_path))

        # 5. Combat detector
        combat_path = capsule_dir / "detectors" / f"{game_id}_combat_detector.py"
        self._write_combat_detector(combat_path, game_id)
        files_created.append(str(combat_path))

        # 6. Provider
        provider_path = capsule_dir / "providers" / f"{game_id}_provider.py"
        self._write_provider(provider_path, game_id, game_name)
        files_created.append(str(provider_path))

        log.info("[CapsuleForge] Created capsule for %s (%d files)", game_id, len(files_created))
        return ForgeResult(game_id=game_id, capsule_dir=capsule_dir, files_created=files_created)

    @staticmethod
    def _sanitize(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", name.strip()).strip("_")

    @staticmethod
    def _write_manifest(
        path: Path, game_id: str, display_name: str, description: str = "",
    ) -> None:
        manifest: dict[str, Any] = {
            "capsule_id": game_id,
            "version": "0.1.0",
            "display_name": display_name,
            "description": description or f"Auto-generated capsule for {display_name}.",
            "keymap_file": "keymap.yaml",
            "detectors": [
                {"id": f"{game_id}_screen_classifier", "class": f"{game_id}_screen_classifier.{_pascal(game_id)}ScreenClassifier"},
                {"id": f"{game_id}_combat_detector", "class": f"{game_id}_combat_detector.{_pascal(game_id)}CombatDetector"},
            ],
            "providers": [
                {"id": f"{game_id}_provider", "class": f"{game_id}_provider.{_pascal(game_id)}CapsuleProvider"},
            ],
            "skills_file": "skills/index.json",
            "frame_processors": [
                {"id": "screen_state", "detector": f"{game_id}_screen_classifier"},
            ],
            "state_bus_slots": [
                {"name": "screen_state", "type": "LatestSlot"},
                {"name": "combat_state", "type": "LatestSlot"},
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    @staticmethod
    def _write_keymap(path: Path) -> None:
        keymap = {
            "move_forward": "W",
            "move_backward": "S",
            "move_left": "A",
            "move_right": "D",
            "jump": "Space",
            "sprint": "LeftShift",
            "interact": "E",
            "attack": "LeftButton",
            "skill": "E",
            "burst": "Q",
            "menu": "Escape",
            "map": "Tab",
            "inventory": "B",
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(keymap, f, default_flow_style=False, sort_keys=False)

    @staticmethod
    def _write_skill_index(path: Path, game_id: str) -> None:
        skills = {
            "skills": [
                {
                    "id": f"{game_id}_basic_attack",
                    "name": "Basic Attack",
                    "type": "combat",
                    "key": "LeftButton",
                    "description": f"Basic attack for {game_id}",
                },
                {
                    "id": f"{game_id}_interact",
                    "name": "Interact",
                    "type": "navigation",
                    "key": "E",
                    "description": f"Interact with objects in {game_id}",
                },
                {
                    "id": f"{game_id}_open_menu",
                    "name": "Open Menu",
                    "type": "ui",
                    "key": "Escape",
                    "description": "Open the game menu",
                },
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(skills, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def _write_screen_classifier(
        self, path: Path, game_id: str, game_description: str = "",
    ) -> None:
        pascal = _pascal(game_id)
        llm_code = ""
        if self._llm is not None:
            try:
                llm_code = self._llm.generate(
                    f"Generate a Python screen classifier class for the game '{game_id}'. "
                    f"Game description: {game_description}. "
                    "The class should have a `classify(self, frame)` method that returns a "
                    "ScreenStateKind or string. Import from perception.screen_state_kind."
                )
            except Exception as exc:
                log.warning("[CapsuleForge] LLM generation failed: %s", exc)

        if llm_code and len(llm_code) > 50:
            path.write_text(llm_code, encoding="utf-8")
        else:
            path.write_text(_SCREEN_CLASSIFIER_TEMPLATE.format(
                game_id=game_id, Pascal=pascal, desc=game_description or f"{pascal} game",
            ), encoding="utf-8")

    def _write_combat_detector(self, path: Path, game_id: str) -> None:
        pascal = _pascal(game_id)
        path.write_text(_COMBAT_DETECTOR_TEMPLATE.format(
            game_id=game_id, Pascal=pascal,
        ), encoding="utf-8")

    def _write_provider(self, path: Path, game_id: str, display_name: str) -> None:
        pascal = _pascal(game_id)
        path.write_text(_PROVIDER_TEMPLATE.format(
            game_id=game_id, Pascal=pascal, display_name=display_name,
        ), encoding="utf-8")


def _pascal(game_id: str) -> str:
    return "".join(word.capitalize() for word in game_id.split("_"))


# -- Code templates --------------------------------------------------------

_SCREEN_CLASSIFIER_TEMPLATE = '''"""{{Pascal}} screen state classifier."""
from __future__ import annotations

from typing import Any


class {Pascal}ScreenClassifier:
    """Classify screen states for {desc}."""

    # Known states for this game
    STATES = (
        "loading_screen", "overworld", "dialog", "menu",
        "combat", "map", "black_screen", "unknown",
    )

    def classify(self, frame: Any) -> str:
        """Classify the current screen state from a frame.

        Override this method with game-specific logic.
        For MVP, returns 'unknown' — replace with VLM or heuristic classification.
        """
        return "unknown"

    def classify_batch(self, frames: list[Any]) -> list[str]:
        return [self.classify(f) for f in frames]
'''

_COMBAT_DETECTOR_TEMPLATE = '''"""{{Pascal}} combat detector."""
from __future__ import annotations

from typing import Any
from dataclasses import dataclass


@dataclass(slots=True)
class CombatDetection:
    in_combat: bool = False
    enemy_count: int = 0
    threat_level: str = "none"  # none, low, medium, high


class {Pascal}CombatDetector:
    """Detect combat state for {game_id}."""

    def detect(self, frame: Any) -> CombatDetection:
        """Detect combat from frame.

        Override with game-specific detection logic.
        """
        return CombatDetection()
'''

_PROVIDER_TEMPLATE = '''"""{{Pascal}} capsule provider."""
from __future__ import annotations

from typing import Any


class {Pascal}CapsuleProvider:
    """Capsule provider for {display_name}."""

    def __init__(self) -> None:
        self._classifier = None
        self._detector = None

    def activate(self) -> None:
        from {game_id}_screen_classifier import {Pascal}ScreenClassifier
        from {game_id}_combat_detector import {Pascal}CombatDetector
        self._classifier = {Pascal}ScreenClassifier()
        self._detector = {Pascal}CombatDetector()

    def deactivate(self) -> None:
        self._classifier = None
        self._detector = None

    @property
    def screen_classifier(self) -> Any:
        return self._classifier

    @property
    def combat_detector(self) -> Any:
        return self._detector
'''
