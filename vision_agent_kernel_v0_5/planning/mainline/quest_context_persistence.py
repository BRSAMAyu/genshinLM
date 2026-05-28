"""QuestContextPersistence — serialize/deserialize ActiveQuestContext to disk.

Writes a versioned JSON snapshot at each checkpoint so that a crash or restart
can restore the agent to its last known quest state rather than starting blind.

Usage:
    persistence = QuestContextPersistence(runs_dir=Path("runs"))
    persistence.save(context)
    recovered = persistence.load_latest()
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from planning.mainline.active_quest_context import (
    ActiveQuestContext,
    DialogueTurn,
    InventoryFact,
    MapMarker,
    QuestBlocker,
    ResourceFact,
    TeamFact,
    ClaimSummaryFact,
    classify_objective,
    quest_id_from_text,
)

log = logging.getLogger(__name__)

_DEFAULT_RUNS_DIR = Path("runs")


class QuestContextPersistence:
    """Saves and loads ActiveQuestContext snapshots to/from disk.

    Each save writes ``runs/quest_context_v{version}.json``.
    A symlink (or overwrite) ``runs/quest_context_latest.json`` always points
    to the most recent snapshot for fast recovery on startup.
    """

    def __init__(self, runs_dir: Path | None = None) -> None:
        self._runs_dir = runs_dir or _DEFAULT_RUNS_DIR
        self._runs_dir.mkdir(parents=True, exist_ok=True)

    def save(self, context: ActiveQuestContext) -> Path:
        """Serialize context to JSON and write to disk.

        Returns the path of the file written.
        """
        payload = _context_to_dict(context)
        versioned = self._runs_dir / f"quest_context_v{context.version:06d}.json"
        latest = self._runs_dir / "quest_context_latest.json"

        try:
            data = json.dumps(payload, indent=2, ensure_ascii=False)
            versioned.write_text(data, encoding="utf-8")
            latest.write_text(data, encoding="utf-8")
            log.debug(
                "[QuestPersistence] Saved context v%d quest=%r to %s",
                context.version, context.quest_id, versioned,
            )
        except OSError as exc:
            log.warning("[QuestPersistence] Failed to save context: %s", exc)

        # Auto-prune old snapshots
        self.prune_old()

        return versioned

    def load_latest(self) -> ActiveQuestContext | None:
        """Load the most recent context snapshot, or None if none exists."""
        latest = self._runs_dir / "quest_context_latest.json"
        if not latest.exists():
            return None
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            context = _context_from_dict(data)
            log.info(
                "[QuestPersistence] Recovered context v%d quest=%r from disk",
                context.version, context.quest_id,
            )
            return context
        except Exception as exc:
            log.warning("[QuestPersistence] Failed to load latest context: %s", exc)
            return None

    def load_version(self, version: int) -> ActiveQuestContext | None:
        """Load a specific context version by number."""
        path = self._runs_dir / f"quest_context_v{version:06d}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return _context_from_dict(data)
        except Exception as exc:
            log.warning("[QuestPersistence] Failed to load version %d: %s", version, exc)
            return None

    def list_versions(self) -> list[int]:
        """Return sorted list of all saved context version numbers."""
        versions: list[int] = []
        for path in self._runs_dir.glob("quest_context_v*.json"):
            stem = path.stem  # e.g. "quest_context_v000042"
            try:
                version_str = stem.split("_v")[-1]
                versions.append(int(version_str))
            except (ValueError, IndexError):
                pass
        return sorted(versions)

    def prune_old(self, keep_last: int = 20) -> int:
        """Delete all but the most recent *keep_last* versioned snapshots.

        Never deletes quest_context_latest.json.
        Returns count of files deleted.
        """
        versions = self.list_versions()
        to_delete = versions[:-keep_last] if len(versions) > keep_last else []
        deleted = 0
        for v in to_delete:
            path = self._runs_dir / f"quest_context_v{v:06d}.json"
            try:
                path.unlink()
                deleted += 1
            except OSError:
                pass
        return deleted


# -- Serialization helpers -----------------------------------------------


def _context_to_dict(ctx: ActiveQuestContext) -> dict[str, Any]:
    return {
        "quest_id": ctx.quest_id,
        "quest_title": ctx.quest_title,
        "objective_text": ctx.objective_text,
        "objective_type": ctx.objective_type,
        "evidence_refs": list(ctx.evidence_refs),
        "last_dialogue_turns": [
            {
                "speaker": t.speaker,
                "text": t.text,
                "turn_index": t.turn_index,
                "is_player_choice": t.is_player_choice,
            }
            for t in ctx.last_dialogue_turns
        ],
        "map_marker": (
            {
                "marker_id": ctx.map_marker.marker_id,
                "name": ctx.map_marker.name,
                "marker_type": ctx.map_marker.marker_type,
                "region": ctx.map_marker.region,
                "distance_estimate": ctx.map_marker.distance_estimate,
                "is_tracked": ctx.map_marker.is_tracked,
            }
            if ctx.map_marker is not None else None
        ),
        "screen_state": ctx.screen_state,
        "inventory_facts": [
            {"item_id": f.item_id, "quantity": f.quantity, "evidence_ref": f.evidence_ref}
            for f in ctx.inventory_facts
        ],
        "team_facts": [
            {"member_id": f.member_id, "level": f.level, "role": f.role, "evidence_ref": f.evidence_ref}
            for f in ctx.team_facts
        ],
        "resource_facts": [
            {"resource_id": f.resource_id, "value": f.value, "evidence_ref": f.evidence_ref}
            for f in ctx.resource_facts
        ],
        "completed_claims": [
            {"claim_id": f.claim_id, "claim_type": f.claim_type, "status": f.status, "target": f.target}
            for f in ctx.completed_claims
        ],
        "blocked_claims": [
            {"claim_id": f.claim_id, "claim_type": f.claim_type, "status": f.status, "target": f.target}
            for f in ctx.blocked_claims
        ],
        "known_blockers": [
            {
                "blocker_id": b.blocker_id,
                "blocker_type": b.blocker_type,
                "description": b.description,
                "resolution_hint": b.resolution_hint,
            }
            for b in ctx.known_blockers
        ],
        "confidence": ctx.confidence,
        "version": ctx.version,
        "created_at": ctx.created_at,
        "updated_at": ctx.updated_at,
        "metadata": dict(ctx.metadata),
        "_saved_at": time.time(),
    }


def _context_from_dict(data: dict[str, Any]) -> ActiveQuestContext:
    map_marker: MapMarker | None = None
    if data.get("map_marker"):
        mm = data["map_marker"]
        map_marker = MapMarker(
            marker_id=str(mm.get("marker_id", "")),
            name=str(mm.get("name", "")),
            marker_type=str(mm.get("marker_type", "unknown")),
            region=str(mm.get("region", "")),
            distance_estimate=float(mm.get("distance_estimate", -1.0)),
            is_tracked=bool(mm.get("is_tracked", False)),
        )

    return ActiveQuestContext(
        quest_id=str(data.get("quest_id", "unknown")),
        quest_title=str(data.get("quest_title", "")),
        objective_text=str(data.get("objective_text", "")),
        objective_type=data.get("objective_type", "unknown"),  # type: ignore[arg-type]
        evidence_refs=tuple(data.get("evidence_refs", [])),
        last_dialogue_turns=tuple(
            DialogueTurn(
                speaker=str(t.get("speaker", "")),
                text=str(t.get("text", "")),
                turn_index=int(t.get("turn_index", 0)),
                is_player_choice=bool(t.get("is_player_choice", False)),
            )
            for t in data.get("last_dialogue_turns", [])
        ),
        map_marker=map_marker,
        screen_state=str(data.get("screen_state", "unknown")),
        inventory_facts=tuple(
            InventoryFact(
                item_id=str(f.get("item_id", "")),
                quantity=int(f.get("quantity", 0)),
                evidence_ref=str(f.get("evidence_ref", "")),
            )
            for f in data.get("inventory_facts", [])
        ),
        team_facts=tuple(
            TeamFact(
                member_id=str(f.get("member_id", "")),
                level=int(f.get("level", 0)),
                role=str(f.get("role", "")),
                evidence_ref=str(f.get("evidence_ref", "")),
            )
            for f in data.get("team_facts", [])
        ),
        resource_facts=tuple(
            ResourceFact(
                resource_id=str(f.get("resource_id", "")),
                value=float(f.get("value", 0.0)),
                evidence_ref=str(f.get("evidence_ref", "")),
            )
            for f in data.get("resource_facts", [])
        ),
        completed_claims=tuple(
            ClaimSummaryFact(
                claim_id=str(f.get("claim_id", "")),
                claim_type=str(f.get("claim_type", "")),
                status=str(f.get("status", "verified")),
                target=str(f.get("target", "")),
            )
            for f in data.get("completed_claims", [])
        ),
        blocked_claims=tuple(
            ClaimSummaryFact(
                claim_id=str(f.get("claim_id", "")),
                claim_type=str(f.get("claim_type", "")),
                status=str(f.get("status", "blocked")),
                target=str(f.get("target", "")),
            )
            for f in data.get("blocked_claims", [])
        ),
        known_blockers=tuple(
            QuestBlocker(
                blocker_id=str(b.get("blocker_id", "")),
                blocker_type=str(b.get("blocker_type", "unknown")),
                description=str(b.get("description", "")),
                resolution_hint=str(b.get("resolution_hint", "")),
            )
            for b in data.get("known_blockers", [])
        ),
        confidence=float(data.get("confidence", 0.5)),
        version=int(data.get("version", 1)),
        created_at=float(data.get("created_at", 0.0)),
        updated_at=float(data.get("updated_at", 0.0)),
        metadata=dict(data.get("metadata", {})),
    )
