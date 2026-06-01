"""File-based MemoryStore — JSONL persistence for agent experiences."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from agent_kernel.types import Experience

log = logging.getLogger(__name__)


class FileMemoryStore:
    """Store and retrieve experiences from a JSONL file.

    Each line is a JSON object representing one Experience.
    Recall uses simple keyword matching against goal/scene/action text.
    """

    def __init__(self, path: Path | str = "memory/experiences.jsonl") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("", encoding="utf-8")

    def record(self, experience: Experience) -> None:
        data = {
            "goal": experience.goal_description,
            "scene": experience.scene_description,
            "action": experience.action_taken,
            "outcome": experience.outcome,
            "failure_reason": experience.failure_reason,
            "duration": experience.duration_sec,
            "timestamp": experience.timestamp or time.perf_counter(),
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def recall(self, situation: str, limit: int = 5) -> list[Experience]:
        return self._search(keywords=situation.split(), limit=limit)

    def recall_failures(self, goal_type: str) -> list[Experience]:
        return self._search(keywords=goal_type.split(), outcome_filter="failed", limit=10)

    def _search(
        self,
        keywords: list[str],
        outcome_filter: str = "",
        limit: int = 5,
    ) -> list[Experience]:
        results: list[tuple[int, Experience]] = []
        kw_lower = [k.lower() for k in keywords]

        try:
            lines = self._path.read_text(encoding="utf-8").strip().split("\n")
        except Exception:
            return []

        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if outcome_filter and data.get("outcome") != outcome_filter:
                continue

            # Score by keyword match count
            text = f"{data.get('goal', '')} {data.get('scene', '')} {data.get('action', '')}".lower()
            score = sum(1 for kw in kw_lower if kw in text)
            if score == 0:
                continue

            exp = Experience(
                goal_description=data.get("goal", ""),
                scene_description=data.get("scene", ""),
                action_taken=data.get("action", ""),
                outcome=data.get("outcome", ""),
                failure_reason=data.get("failure_reason", ""),
                duration_sec=data.get("duration", 0.0),
                timestamp=data.get("timestamp", 0.0),
            )
            results.append((score, exp))

        # Sort by relevance (most keywords matched) and return top N
        results.sort(key=lambda x: x[0], reverse=True)
        return [exp for _, exp in results[:limit]]
