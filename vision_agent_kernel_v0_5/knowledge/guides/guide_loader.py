from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class GuideTip:
    tip_id: str
    title: str
    content: str
    tags: tuple[str, ...]
    applicable_characters: tuple[str, ...]
    difficulty: str
    section_title: str
    game: str


class GuideKnowledgeBase:
    """Load and query game guide tips from YAML."""

    def __init__(self, guides_dir: Path | None = None) -> None:
        self._dir = guides_dir or Path(__file__).resolve().parent
        self._tips: dict[str, GuideTip] | None = None
        self._tag_index: dict[str, list[str]] | None = None

    @property
    def tips(self) -> dict[str, GuideTip]:
        if self._tips is None:
            self._tips, self._tag_index = self._load()
        return self._tips

    def get(self, tip_id: str) -> GuideTip | None:
        return self.tips.get(tip_id)

    def search_by_tags(self, tags: list[str], game: str = "") -> list[GuideTip]:
        """Return tips matching any of the given tags, sorted by priority."""
        results: list[GuideTip] = []
        for tip in self.tips.values():
            if game and tip.game != game:
                continue
            if any(t in tip.tags for t in tags):
                results.append(tip)
        return results

    def search_for_character(self, character_id: str) -> list[GuideTip]:
        """Return tips relevant to a specific character."""
        return [t for t in self.tips.values() if character_id in t.applicable_characters]

    def search_by_difficulty(self, difficulty: str, game: str = "") -> list[GuideTip]:
        return [
            t for t in self.tips.values()
            if t.difficulty == difficulty and (not game or t.game == game)
        ]

    def get_relevant_context(
        self,
        tags: list[str],
        game: str = "",
        max_tips: int = 5,
        max_chars: int = 3000,
    ) -> str:
        """Build a context string from relevant tips, respecting budget."""
        tips = self.search_by_tags(tags, game)
        if not tips:
            return ""

        selected: list[str] = []
        total_chars = 0
        for tip in tips[:max_tips * 2]:
            entry = f"### {tip.title}\n{tip.content.strip()}"
            if total_chars + len(entry) > max_chars:
                break
            selected.append(entry)
            total_chars += len(entry)
            if len(selected) >= max_tips:
                break

        return "\n\n".join(selected)

    def _load(self) -> tuple[dict[str, GuideTip], dict[str, list[str]]]:
        tips: dict[str, GuideTip] = {}
        tag_index: dict[str, list[str]] = {}
        if not self._dir.exists():
            return tips, tag_index

        for path in self._dir.glob("*.yaml"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception:
                continue

            game = data.get("game", "")
            for section in data.get("sections", []):
                section_title = section.get("title", "")
                section_tags = section.get("tags", [])
                for entry in section.get("tips", []):
                    all_tags = tuple(set(section_tags + entry.get("tags", [])))
                    tip = GuideTip(
                        tip_id=entry.get("tip_id", ""),
                        title=entry.get("title", ""),
                        content=entry.get("content", ""),
                        tags=all_tags,
                        applicable_characters=tuple(entry.get("applicable_characters", [])),
                        difficulty=entry.get("difficulty", ""),
                        section_title=section_title,
                        game=game,
                    )
                    if tip.tip_id:
                        tips[tip.tip_id] = tip
                    for tag in all_tags:
                        tag_index.setdefault(tag, []).append(tip.tip_id)

        return tips, tag_index
