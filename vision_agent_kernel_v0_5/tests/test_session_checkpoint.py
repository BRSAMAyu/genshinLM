"""Tests for runtime/session_checkpoint.py: checkpoint creation, save/load, rolling window."""
from __future__ import annotations

import shutil
from pathlib import Path

from runtime.session_checkpoint import Checkpoint, CheckpointStore, CheckpointMetadata


class TestCheckpoint:
    def test_compute_checksum(self):
        meta = CheckpointMetadata(
            checkpoint_id="ck_001", checkpoint_type="incremental",
            session_id="s1", triggered_by="test",
        )
        cp = Checkpoint(metadata=meta, account_snapshot={"ar": 35})
        checksum = cp.compute_checksum()
        assert len(checksum) == 64  # SHA256 hex

    def test_checksum_changes_with_content(self):
        meta = CheckpointMetadata(
            checkpoint_id="ck_002", checkpoint_type="full",
            session_id="s1", triggered_by="test",
        )
        cp1 = Checkpoint(metadata=meta, account_snapshot={"ar": 35})
        cp2 = Checkpoint(metadata=meta, account_snapshot={"ar": 40})
        assert cp1.compute_checksum() != cp2.compute_checksum()

    def test_verify_valid_checksum(self):
        meta = CheckpointMetadata(
            checkpoint_id="ck_003", checkpoint_type="incremental",
            session_id="s1", triggered_by="test",
        )
        cp = Checkpoint(metadata=meta, account_snapshot={"ar": 35}, checksum="")
        correct = cp.compute_checksum()
        cp_valid = Checkpoint(
            metadata=meta, account_snapshot={"ar": 35}, checksum=correct,
        )
        assert cp_valid.verify() is True

    def test_verify_invalid_checksum(self):
        meta = CheckpointMetadata(
            checkpoint_id="ck_004", checkpoint_type="full",
            session_id="s1", triggered_by="test",
        )
        cp = Checkpoint(metadata=meta, checksum="bad_checksum")
        assert cp.verify() is False

    def test_to_dict(self):
        meta = CheckpointMetadata(
            checkpoint_id="ck_005", checkpoint_type="full",
            session_id="s1", triggered_by="quest_complete",
        )
        cp = Checkpoint(
            metadata=meta,
            account_snapshot={"ar": 45},
            task_state={"mission": "m1"},
        )
        d = cp.to_dict()
        assert d["metadata"]["checkpoint_id"] == "ck_005"
        assert d["account_snapshot"]["ar"] == 45
        assert d["task_state"]["mission"] == "m1"


class TestCheckpointStore:
    def _make_store(self, name: str = "test_checkpoints") -> CheckpointStore:
        d = Path(name)
        if d.exists():
            shutil.rmtree(d)
        return CheckpointStore(checkpoint_dir=d)

    def test_create_checkpoint(self):
        store = self._make_store()
        cp = store.create_checkpoint(
            session_id="s1",
            triggered_by="quest_step_complete",
            account_snapshot={"ar": 35},
        )
        assert cp.metadata.session_id == "s1"
        assert cp.metadata.triggered_by == "quest_step_complete"
        assert cp.metadata.checkpoint_type == "incremental"
        assert cp.checksum != ""
        assert cp.verify() is True
        shutil.rmtree("test_checkpoints")

    def test_save_and_load_latest(self):
        store = self._make_store()
        cp = store.create_checkpoint(
            session_id="s1",
            triggered_by="test",
            account_snapshot={"ar": 35, "resin": 80},
        )
        store.save(cp)

        loaded = store.load_latest()
        assert loaded is not None
        assert loaded.metadata.session_id == "s1"
        assert loaded.account_snapshot["ar"] == 35
        assert loaded.verify() is True
        shutil.rmtree("test_checkpoints")

    def test_save_and_load_by_id(self):
        store = self._make_store()
        cp = store.create_checkpoint(
            session_id="s1", triggered_by="test",
        )
        store.save(cp)
        cp_id = cp.metadata.checkpoint_id

        loaded = store.load(cp_id)
        assert loaded is not None
        assert loaded.metadata.checkpoint_id == cp_id
        shutil.rmtree("test_checkpoints")

    def test_list_checkpoints(self):
        store = self._make_store()
        for i in range(5):
            cp = store.create_checkpoint(
                session_id="s1", triggered_by=f"trigger_{i}",
            )
            store.save(cp)

        ids = store.list_checkpoints()
        assert len(ids) >= 5
        shutil.rmtree("test_checkpoints")

    def test_rolling_window_prunes(self):
        store = self._make_store()
        store.max_checkpoints = 5

        for i in range(10):
            cp = store.create_checkpoint(
                session_id="s1", triggered_by=f"trigger_{i}",
            )
            store.save(cp)

        ids = store.list_checkpoints()
        assert len(ids) <= 5
        shutil.rmtree("test_checkpoints")

    def test_full_checkpoint_type(self):
        store = self._make_store()
        cp = store.create_checkpoint(
            session_id="s1",
            triggered_by="timed_interval",
            checkpoint_type="full",
            account_snapshot={"ar": 35},
        )
        assert cp.metadata.checkpoint_type == "full"
        store.save(cp)

        loaded = store.load_latest()
        assert loaded.metadata.checkpoint_type == "full"
        shutil.rmtree("test_checkpoints")

    def test_load_missing_returns_none(self):
        store = self._make_store()
        assert store.load_latest() is None
        assert store.load("nonexistent") is None
        shutil.rmtree("test_checkpoints")

    def test_checkpoint_integrity_across_save_load(self):
        store = self._make_store()
        cp = store.create_checkpoint(
            session_id="s1",
            triggered_by="quest_complete",
            account_snapshot={"ar": 45, "resin": 60},
            task_state={"mission": "mainline", "node": "ch3_act2"},
            location_snapshot={"region": "sumeru"},
            resource_snapshot={"resin": 60, "mora": 1500000},
        )
        store.save(cp)

        loaded = store.load_latest()
        assert loaded is not None
        assert loaded.verify() is True
        assert loaded.account_snapshot["ar"] == 45
        assert loaded.task_state["mission"] == "mainline"
        assert loaded.location_snapshot["region"] == "sumeru"
        assert loaded.resource_snapshot["mora"] == 1500000
        shutil.rmtree("test_checkpoints")
