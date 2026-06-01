"""Session-persistent NPC affection tracking.

Saves/loads AffectionDialogManager state to a JSON checkpoint file so that
NPC relationship progress survives across game sessions.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from interaction.dialog_driver import AffectionDialogManager, NpcRelationship

log = logging.getLogger(__name__)


class NpcAffectionPersistence:
    """Persist NPC affection data to disk as JSON."""

    def __init__(
        self,
        manager: AffectionDialogManager,
        checkpoint_dir: str | Path = "checkpoints",
        filename: str = "npc_affection.json",
    ) -> None:
        self._manager = manager
        self._dir = Path(checkpoint_dir)
        self._path = self._dir / filename

    def save(self) -> None:
        """Write current affection state to the checkpoint file."""
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            "saved_at": time.perf_counter(),
            "relationships": {
                name: {
                    "npc_name": rel.npc_name,
                    "affection": rel.affection,
                    "dialog_count": rel.dialog_count,
                    "quests_completed": rel.quests_completed,
                    "gifts_given": rel.gifts_given,
                }
                for name, rel in self._manager.get_all_relationships().items()
            },
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)
        log.info("[Affection] Saved %d NPC relationships to %s", len(data["relationships"]), self._path)

    def load(self) -> bool:
        """Load affection state from checkpoint file into the manager.

        Returns True if a valid checkpoint was loaded, False otherwise.
        """
        if not self._path.exists():
            log.info("[Affection] No checkpoint found at %s", self._path)
            return False

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("[Affection] Failed to load checkpoint: %s", exc)
            return False

        relationships = raw.get("relationships", {})
        for name, entry in relationships.items():
            rel = self._manager.get_or_create(name)
            rel.affection = int(entry.get("affection", 0))
            rel.dialog_count = int(entry.get("dialog_count", 0))
            rel.quests_completed = int(entry.get("quests_completed", 0))
            rel.gifts_given = int(entry.get("gifts_given", 0))

        log.info("[Affection] Loaded %d NPC relationships from %s", len(relationships), self._path)
        return True

    def reset(self, npc_name: str | None = None) -> None:
        """Reset affection for a specific NPC or all NPCs."""
        if npc_name is not None:
            rels = self._manager.get_all_relationships()
            if npc_name in rels:
                rel = self._manager.get_or_create(npc_name)
                rel.affection = 0
                rel.dialog_count = 0
                rel.quests_completed = 0
                rel.gifts_given = 0
                log.info("[Affection] Reset relationship for %s", npc_name)
        else:
            for name in list(self._manager.get_all_relationships()):
                self.reset(name)
            log.info("[Affection] Reset all relationships")

    @property
    def checkpoint_path(self) -> Path:
        return self._path
