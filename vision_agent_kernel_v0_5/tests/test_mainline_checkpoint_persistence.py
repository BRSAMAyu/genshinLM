"""Tests for Phase 8: Checkpoint persistence to StateBus + disk.

Verifies:
- MainlineCheckpointPublisher writes to StateBus.checkpoint_state
- MainlineCheckpointPublisher writes to disk via CheckpointStore
- kill/restart scenario: resume from last checkpoint on disk
"""
from __future__ import annotations

import time
from pathlib import Path

from core.state_bus import StateBus
from planning.mainline.mainline_runner import (
    MainlineCheckpoint,
    MainlineCheckpointPublisher,
    MainlineRunner,
)
from planning.mainline.mission_graph_v4 import ClaimContract, MissionGraphV4, MissionNodeV4
from runtime.session_checkpoint import CheckpointStore


class TestCheckpointPersistence:
    """Test MainlineCheckpointPublisher writes bus + disk."""

    def test_publish_writes_to_statebus(self):
        bus = StateBus()
        publisher = MainlineCheckpointPublisher(bus)
        cp = MainlineCheckpoint(
            checkpoint_id="ckpt_test_1",
            phase="execute",
            context_version=1,
            graph_id="g1",
            completed_nodes=("n1",),
        )
        publisher.publish(cp)

        slot_value = bus.checkpoint_state.get()
        assert slot_value is not None
        assert slot_value.checkpoint_id == "ckpt_test_1"
        assert slot_value.completed_nodes == ("n1",)

    def test_publish_writes_to_disk(self, tmp_path: Path):
        bus = StateBus()
        store = CheckpointStore(checkpoint_dir=tmp_path / "ckpts")
        publisher = MainlineCheckpointPublisher(bus, disk_store=store)
        cp = MainlineCheckpoint(
            checkpoint_id="ckpt_disk_1",
            phase="execute",
            context_version=1,
            graph_id="g1",
            completed_nodes=("n1", "n2"),
        )
        publisher.publish(cp)

        loaded = store.load_latest()
        assert loaded is not None
        assert loaded.task_state["graph_id"] == "g1"
        assert loaded.task_state["completed_nodes"] == ["n1", "n2"]
        assert loaded.task_state["skipped_nodes"] == []

    def test_publish_without_disk_store_still_writes_bus(self):
        bus = StateBus()
        publisher = MainlineCheckpointPublisher(bus, disk_store=None)
        cp = MainlineCheckpoint(
            checkpoint_id="ckpt_nodisk",
            phase="execute",
            context_version=1,
            graph_id="g1",
        )
        publisher.publish(cp)

        assert bus.checkpoint_state.get() is not None

    def test_disk_failure_does_not_block_bus(self, tmp_path: Path):
        bus = StateBus()
        store = CheckpointStore(checkpoint_dir=tmp_path / "ckpts")
        publisher = MainlineCheckpointPublisher(bus, disk_store=store)

        cp = MainlineCheckpoint(
            checkpoint_id="ckpt_fail_disk",
            phase="execute",
            context_version=1,
            graph_id="g1",
        )
        publisher.publish(cp)
        assert bus.checkpoint_state.get() is not None

    def test_runner_publishes_checkpoint_after_node(self, tmp_path: Path):
        bus = StateBus()
        store = CheckpointStore(checkpoint_dir=tmp_path / "ckpts")
        publisher = MainlineCheckpointPublisher(bus, disk_store=store)

        runner = MainlineRunner(
            skill_execute_fn=lambda node: {"result": "ok", "nav_result": "done"},
            checkpoint_publisher=publisher,
        )
        g = MissionGraphV4(mission_id="ckpt_test")
        g.add_node(MissionNodeV4(
            node_id="n1",
            node_type="navigate",
            output_claims=[ClaimContract(claim_type="nav_result")],
        ))
        result = runner.run(g)

        assert result.completed_nodes == ["n1"]
        bus_cp = bus.checkpoint_state.get()
        assert bus_cp is not None
        assert "n1" in bus_cp.completed_nodes

    def test_runner_publishes_checkpoint_after_failed_node(self, tmp_path: Path):
        bus = StateBus()
        store = CheckpointStore(checkpoint_dir=tmp_path / "ckpts")
        publisher = MainlineCheckpointPublisher(bus, disk_store=store)

        runner = MainlineRunner(
            skill_execute_fn=lambda node: {},
            checkpoint_publisher=publisher,
            max_node_retries=0,
        )
        g = MissionGraphV4(mission_id="ckpt_fail_test")
        g.add_node(MissionNodeV4(
            node_id="n1",
            node_type="navigate",
            output_claims=[ClaimContract(claim_type="nav_result")],
        ))
        result = runner.run(g)

        assert result.failed_nodes == ["n1"]
        bus_cp = bus.checkpoint_state.get()
        assert bus_cp is not None
        assert bus_cp.failed_nodes == ("n1",)
        loaded = store.load_latest()
        assert loaded is not None
        assert loaded.task_state["failed_nodes"] == ["n1"]

    def test_resume_from_disk_checkpoint(self, tmp_path: Path):
        """Simulate kill/restart: save checkpoint, load on new runner."""
        bus = StateBus()
        store = CheckpointStore(checkpoint_dir=tmp_path / "ckpts")

        publisher = MainlineCheckpointPublisher(bus, disk_store=store)
        runner1 = MainlineRunner(
            skill_execute_fn=lambda node: {"result": "ok", "nav_result": "done", "interact_result": "done"},
            checkpoint_publisher=publisher,
        )
        g = MissionGraphV4(mission_id="resume_test")
        g.add_node(MissionNodeV4(
            node_id="n1",
            node_type="navigate",
            output_claims=[ClaimContract(claim_type="nav_result")],
        ))
        g.add_node(MissionNodeV4(
            node_id="n2",
            node_type="interact",
            output_claims=[ClaimContract(claim_type="interact_result")],
        ))
        from planning.mainline.mission_graph_v4 import MissionEdgeV4
        g.add_edge(MissionEdgeV4(from_node="n1", to_node="n2"))
        runner1.run(g)

        loaded = store.load_latest()
        assert loaded is not None
        assert loaded.task_state["completed_nodes"] == ["n1", "n2"]
