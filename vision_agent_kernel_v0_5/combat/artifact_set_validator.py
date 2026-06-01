"""R-32: Artifact set matching validator — pre-combat gear check.

Validates that equipped artifact sets match the recommended build for a character.
Uses F2P_BUILDS as the reference data source for recommended artifact sets.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from knowledge.genshin_f2p_builds import F2P_BUILDS

log = logging.getLogger(__name__)

# Regex patterns for extracting set name and piece count from build strings.
# e.g. "Emblem of Severed Fate 4pc" → ("Emblem of Severed Fate", 4)
# e.g. "Noblesse Oblige 2pc + Crimson Witch 2pc" → two 2pc sets
_PIECE_PATTERN = re.compile(r"^(.+?)\s*(\d)pc$")
_SPLIT_PATTERN = re.compile(r"\s*\+\s*")


@dataclass(frozen=True, slots=True)
class ArtifactSetResult:
    character_id: str
    recommended_set: str
    detected_sets: tuple[str, ...]
    match_score: float  # 0.0-1.0
    warnings: tuple[str, ...] = ()
    matched: bool = False


def _parse_set_spec(spec: str) -> list[tuple[str, int]]:
    """Parse artifact set specification into (name, piece_count) pairs.

    Handles formats like:
    - "Emblem of Severed Fate 4pc"
    - "Noblesse Oblige 2pc + Crimson Witch 2pc"
    - "Thundering Fury 4pc / Noblesse Oblige 4pc" (alt separated by /)
    """
    parts = _SPLIT_PATTERN.split(spec)
    results: list[tuple[str, int]] = []
    for part in parts:
        m = _PIECE_PATTERN.match(part.strip())
        if m:
            results.append((m.group(1).strip(), int(m.group(2))))
    return results


def _normalize_set_name(name: str) -> str:
    """Normalize artifact set name for fuzzy matching."""
    return name.lower().strip().replace("'", "").replace("-", " ").replace("’", "")


class ArtifactSetValidator:
    """Validate artifact set matching for a character build."""

    def validate(
        self,
        character_id: str,
        detected_sets: list[str] | tuple[str, ...],
    ) -> ArtifactSetResult:
        """Validate detected artifact sets against recommended build.

        Args:
            character_id: Character identifier (e.g., "xiangling").
            detected_sets: List of detected artifact set names from OCR/perception.

        Returns:
            ArtifactSetResult with match assessment.
        """
        warnings: list[str] = []
        cid = character_id.lower().strip()

        build = F2P_BUILDS.get(cid)
        if build is None:
            return ArtifactSetResult(
                character_id=character_id,
                recommended_set="unknown",
                detected_sets=tuple(detected_sets),
                match_score=0.0,
                warnings=(f"Unknown character '{character_id}' — no build data",),
                matched=False,
            )

        recommended_primary = self._parse_primary_sets(build.artifact_set)
        recommended_alt = self._parse_primary_sets(build.artifact_alt)

        if not detected_sets:
            return ArtifactSetResult(
                character_id=character_id,
                recommended_set=build.artifact_set,
                detected_sets=(),
                match_score=0.0,
                warnings=("No artifact sets detected — cannot validate",),
                matched=False,
            )

        detected_norm = [_normalize_set_name(s) for s in detected_sets]

        # Check primary set match
        score, matched_primary = self._score_match(
            detected_norm, recommended_primary, build.artifact_set,
        )

        # If primary didn't match well, check alt
        if score < 0.5 and recommended_alt:
            alt_score, matched_alt = self._score_match(
                detected_norm, recommended_alt, build.artifact_alt,
            )
            if alt_score > score:
                score = alt_score
                if matched_alt and not matched_primary:
                    warnings.append(
                        f"Using alt set — recommended: {build.artifact_set}, "
                        f"alt: {build.artifact_alt}"
                    )

        if score < 0.5 and not warnings:
            warnings.append(
                f"Artifact sets don't match recommended build: {build.artifact_set}"
            )

        return ArtifactSetResult(
            character_id=character_id,
            recommended_set=build.artifact_set,
            detected_sets=tuple(detected_sets),
            match_score=score,
            warnings=tuple(warnings),
            matched=score >= 0.5,
        )

    def validate_team(
        self,
        character_ids: list[str],
        detected_sets_per_char: list[list[str]],
    ) -> list[ArtifactSetResult]:
        """Validate artifact sets for an entire team.

        Args:
            character_ids: List of character IDs.
            detected_sets_per_char: Parallel list of detected sets per character.

        Returns:
            List of ArtifactSetResult, one per character.
        """
        results: list[ArtifactSetResult] = []
        for cid, sets in zip(character_ids, detected_sets_per_char):
            results.append(self.validate(cid, sets))
        return results

    @staticmethod
    def _parse_primary_sets(spec: str) -> list[tuple[str, int]]:
        """Parse the primary option from a spec (before '/' separator)."""
        primary = spec.split("/")[0].strip()
        return _parse_set_spec(primary)

    @staticmethod
    def _score_match(
        detected_norm: list[str],
        recommended: list[tuple[str, int]],
        spec_label: str,
    ) -> tuple[float, bool]:
        """Score how well detected sets match recommended sets.

        Returns (score, matched_primary_recommendation).
        """
        if not recommended:
            return 0.5, False

        total_pieces_needed = sum(pieces for _, pieces in recommended)
        matched_pieces = 0

        for rec_name, rec_pieces in recommended:
            rec_norm = _normalize_set_name(rec_name)
            # Check if any detected set contains the recommended name
            for det in detected_norm:
                # Fuzzy: check if recommended name is a substring of detected or vice versa
                if rec_norm in det or det in rec_norm:
                    matched_pieces += rec_pieces
                    break

        if total_pieces_needed == 0:
            return 0.5, False

        score = matched_pieces / total_pieces_needed
        return score, score >= 0.5
