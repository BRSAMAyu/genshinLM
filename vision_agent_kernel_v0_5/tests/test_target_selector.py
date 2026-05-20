from __future__ import annotations

from core.types import TargetCandidate, TargetTrack
from perception.target_selector import TargetSelector


def test_target_selector_prefers_active_track() -> None:
    selector = TargetSelector()
    tracks = [
        TargetTrack("a", "target", "TRACKED", None, (100.0, 100.0), (0.0, 0.0), 0.9, 0.9, 0.0, None, None, None, 1),
        TargetTrack("b", "target", "TRACKED", None, (640.0, 360.0), (0.0, 0.0), 0.95, 0.95, 0.0, None, None, None, 1),
    ]

    assert selector.select_track([tracks[0]]).track_id == "a"
    assert selector.select_track(tracks).track_id == "a"


def test_target_selector_scores_candidate_center_and_confidence() -> None:
    selector = TargetSelector()
    candidates = [
        TargetCandidate(1, "target", (0, 0, 20, 20), 0.4, (10.0, 10.0), 400.0, 1.0),
        TargetCandidate(1, "target", (600, 330, 680, 390), 0.8, (640.0, 360.0), 6400.0, 1.0),
    ]

    selection = selector.select_candidate(candidates)

    assert selection.candidate is candidates[1]
    assert selection.identity_confidence > 0.8
