"""Tests for reusable recovery strategies."""
from __future__ import annotations

import pytest

from control.recovery_strategies import ArcGoAroundRecovery
from core.types import PoseEstimate


def _pose() -> PoseEstimate:
    return PoseEstimate(frame_id=1, timestamp=0.0, position=(0.0, 0.0), heading_deg=0.0)


def test_arc_goaround_strafes_with_forward_bias() -> None:
    rec = ArcGoAroundRecovery(strafe=0.9, forward_bias=0.2)
    out = rec.recover("stuck", _pose(), target=None)
    assert out.movement is not None
    assert out.movement.move_right == pytest.approx(0.9)   # side +1 first
    assert out.movement.move_forward == pytest.approx(0.2)  # arc, not pure backstep
    assert not out.resolved


def test_arc_goaround_commits_then_flips_side() -> None:
    rec = ArcGoAroundRecovery(strafe=1.0, flip_after=3)
    sides = [rec.recover("s", _pose(), None).movement.move_right for _ in range(6)]
    # first 2 same side, 3rd call flips, then holds the new side
    assert sides[0] == sides[1] == 1.0
    assert sides[2] == -1.0  # flip on the 3rd call (calls % flip_after == 0)
    assert sides[3] == sides[4] == -1.0
    assert sides[5] == 1.0   # flips back on the 6th


def test_arc_goaround_reset() -> None:
    rec = ArcGoAroundRecovery(flip_after=2)
    rec.recover("s", _pose(), None)
    rec.recover("s", _pose(), None)  # would flip
    rec.reset()
    out = rec.recover("s", _pose(), None)
    assert out.movement.move_right > 0  # back to initial side after reset
