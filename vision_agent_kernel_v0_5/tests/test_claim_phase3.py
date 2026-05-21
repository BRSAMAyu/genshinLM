from __future__ import annotations

import json
import os
import tempfile
import time

import pytest

from runtime.audit_scheduler import (
    AuditCompletion,
    AuditRecord,
    AuditScheduleConfig,
    DelayedAuditScheduler,
)
from runtime.claim_runtime import AuditSnapshot


class TestAuditRecord:
    def test_create(self):
        r = AuditRecord(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="post_node", due_at=1.0, deadline_at=2.0,
            snapshot_ref="snap_1", expected_delta={"item": "test", "delta": 1},
        )
        assert r.status == "pending"
        assert r.audit_type == "post_node"


class TestDelayedAuditScheduler:
    def test_schedule_post_node(self):
        scheduler = DelayedAuditScheduler()
        snapshot = AuditSnapshot(screen_state_before="overworld")
        record = scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="inventory_delta",
            audit_type="post_node", snapshot=snapshot, expected_delta={"item": "x", "delta": 1},
        )
        assert record.status == "pending"
        assert record.audit_type == "post_node"
        assert scheduler.pending_count() == 1

    def test_schedule_mission_terminal(self):
        scheduler = DelayedAuditScheduler()
        snapshot = AuditSnapshot()
        record = scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="reward",
            audit_type="mission_terminal", snapshot=snapshot, expected_delta={},
        )
        assert record.audit_type == "mission_terminal"

    def test_schedule_low_activity(self):
        scheduler = DelayedAuditScheduler()
        snapshot = AuditSnapshot()
        record = scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="low_activity", snapshot=snapshot, expected_delta={},
        )
        assert record.audit_type == "low_activity"
        assert len(scheduler.get_low_activity_pending()) == 1

    def test_check_due_not_yet(self):
        scheduler = DelayedAuditScheduler()
        snapshot = AuditSnapshot()
        now = time.time()
        scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="post_node", snapshot=snapshot, expected_delta={},
        )
        due = scheduler.check_due(current_time=now)
        assert len(due) == 0

    def test_check_due_after_delay(self):
        config = AuditScheduleConfig(post_node_delay_ms=100)
        scheduler = DelayedAuditScheduler(config=config)
        snapshot = AuditSnapshot()
        scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="post_node", snapshot=snapshot, expected_delta={},
        )
        future = time.time() + 5.0
        due = scheduler.check_due(current_time=future)
        assert len(due) == 1
        assert due[0].audit_id == "a1"

    def test_complete_matched(self):
        scheduler = DelayedAuditScheduler(config=AuditScheduleConfig(post_node_delay_ms=0))
        snapshot = AuditSnapshot()
        scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="post_node", snapshot=snapshot, expected_delta={"item": "x", "delta": 1},
        )
        result = scheduler.complete("a1", {"item": "x", "delta": 1})
        assert result.matched
        assert not result.contaminated
        assert scheduler.pending_count() == 0
        assert scheduler.completed_count() == 1

    def test_complete_mismatch(self):
        scheduler = DelayedAuditScheduler(config=AuditScheduleConfig(post_node_delay_ms=0))
        snapshot = AuditSnapshot()
        scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="post_node", snapshot=snapshot, expected_delta={"delta": 1},
        )
        result = scheduler.complete("a1", {"delta": 0})
        assert not result.matched
        assert not result.contaminated

    def test_complete_contaminated(self):
        scheduler = DelayedAuditScheduler(config=AuditScheduleConfig(post_node_delay_ms=0))
        snapshot = AuditSnapshot()
        scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="post_node", snapshot=snapshot, expected_delta={},
        )
        result = scheduler.complete("a1", {}, contamination_reasons=["user_consumed_items"])
        assert result.contaminated
        assert not result.matched

    def test_mark_unverifiable(self):
        scheduler = DelayedAuditScheduler(config=AuditScheduleConfig(post_node_delay_ms=0))
        snapshot = AuditSnapshot()
        scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="post_node", snapshot=snapshot, expected_delta={},
        )
        result = scheduler.mark_unverifiable("a1", "game_closed")
        assert result.unverifiable
        assert scheduler.completed_count() == 1

    def test_expire_overdue(self):
        config = AuditScheduleConfig(post_node_delay_ms=0, deadline_extension_ms=100)
        scheduler = DelayedAuditScheduler(config=config)
        snapshot = AuditSnapshot()
        scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="post_node", snapshot=snapshot, expected_delta={},
        )
        far_future = time.time() + 1000.0
        due = scheduler.check_due(current_time=far_future)
        assert len(due) == 0
        assert scheduler.pending_count() == 0
        completed = scheduler.get_completed()
        assert any(c.status == "expired" for c in completed)

    def test_retry_within_limit(self):
        scheduler = DelayedAuditScheduler(config=AuditScheduleConfig(post_node_delay_ms=0, max_retries=2))
        snapshot = AuditSnapshot()
        scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="post_node", snapshot=snapshot, expected_delta={},
        )
        record = scheduler.retry("a1")
        assert record is not None
        assert record.retry_count == 1
        record2 = scheduler.retry("a1")
        assert record2 is not None
        assert record2.retry_count == 2

    def test_retry_exceeds_limit(self):
        scheduler = DelayedAuditScheduler(config=AuditScheduleConfig(post_node_delay_ms=0, max_retries=1))
        snapshot = AuditSnapshot()
        scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
            audit_type="post_node", snapshot=snapshot, expected_delta={},
        )
        scheduler.retry("a1")
        record = scheduler.retry("a1")
        assert record is None
        assert scheduler.completed_count() == 1

    def test_retry_nonexistent(self):
        scheduler = DelayedAuditScheduler()
        assert scheduler.retry("nonexistent") is None

    def test_complete_nonexistent(self):
        scheduler = DelayedAuditScheduler()
        result = scheduler.complete("nonexistent", {})
        assert result.unverifiable

    def test_jsonl_persistence(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            scheduler = DelayedAuditScheduler(
                config=AuditScheduleConfig(post_node_delay_ms=0),
                persistence_path=path,
            )
            snapshot = AuditSnapshot(screen_state_before="overworld")
            scheduler.schedule(
                audit_id="a1", claim_id="c1", skill_id="s1", claim_type="inv_delta",
                audit_type="post_node", snapshot=snapshot,
                expected_delta={"item": "x", "delta": 1},
            )
            scheduler.complete("a1", {"item": "x", "delta": 1})

            with open(path) as f:
                lines = [l.strip() for l in f if l.strip()]
            assert len(lines) == 2
            events = [json.loads(l) for l in lines]
            assert events[0]["event"] == "scheduled"
            assert events[1]["event"] == "completed"
            assert events[1]["result"] == "matched"

            scheduler2 = DelayedAuditScheduler(
                config=AuditScheduleConfig(post_node_delay_ms=0),
                persistence_path=path,
            )
            assert scheduler2.completed_count() == 1
            assert scheduler2.pending_count() == 0
        finally:
            os.unlink(path)

    def test_jsonl_persistence_pending_resume(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            scheduler = DelayedAuditScheduler(
                config=AuditScheduleConfig(post_node_delay_ms=50000),
                persistence_path=path,
            )
            snapshot = AuditSnapshot()
            scheduler.schedule(
                audit_id="a1", claim_id="c1", skill_id="s1", claim_type="test",
                audit_type="post_node", snapshot=snapshot, expected_delta={},
            )
            assert scheduler.pending_count() == 1

            scheduler2 = DelayedAuditScheduler(
                config=AuditScheduleConfig(post_node_delay_ms=50000),
                persistence_path=path,
            )
            assert scheduler2.pending_count() == 1
        finally:
            os.unlink(path)

    def test_stabilization_window_respected(self):
        config = AuditScheduleConfig(post_node_delay_ms=100)
        scheduler = DelayedAuditScheduler(config=config)
        snapshot = AuditSnapshot()
        now = time.time()
        record = scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="s1", claim_type="collection_pickup",
            audit_type="post_node", snapshot=snapshot,
            expected_delta={}, stabilization_window_ms=2000,
        )
        assert record.due_at >= now + 2.0

    def test_full_lifecycle(self):
        config = AuditScheduleConfig(post_node_delay_ms=0)
        scheduler = DelayedAuditScheduler(config=config)
        snapshot = AuditSnapshot(inventory_before={"item_a": 5})

        record = scheduler.schedule(
            audit_id="a1", claim_id="c1", skill_id="collect", claim_type="inventory_delta",
            audit_type="post_node", snapshot=snapshot,
            expected_delta={"item": "item_a", "delta": 1},
        )
        assert record.status == "pending"

        due = scheduler.check_due(current_time=time.time() + 10.0)
        assert len(due) == 1

        result = scheduler.complete("a1", {"item": "item_a", "delta": 1})
        assert result.matched
        assert scheduler.pending_count() == 0
        assert scheduler.completed_count() == 1
