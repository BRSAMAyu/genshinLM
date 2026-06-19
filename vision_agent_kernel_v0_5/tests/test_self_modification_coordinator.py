"""Tests for SelfModificationCoordinator — the human-gated self-modification loop.

The central safety property: NO code path from ``propose_*`` may write a module
or hot-reload. Only ``approve()`` may apply code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from learning.self_modification_coordinator import (
    CapabilityGap,
    ModificationProposal,
    ProposalStatus,
    SelfModificationCoordinator,
)


# -- fakes ------------------------------------------------------------------


class _RecordingHotReload:
    """HotReloadManager stand-in that records calls so we can assert on them."""

    def __init__(self) -> None:
        self.watched: list[str] = []
        self.reload_all_calls = 0

    def watch(self, module_name: str) -> None:
        self.watched.append(module_name)

    def reload_all(self) -> list[object]:
        self.reload_all_calls += 1
        return []


class _StubEvolution:
    """EvolutionEngine stand-in returning a draft with safe steps."""

    def list_patch_drafts(self, skill_id: str | None = None) -> list[dict[str, object]]:
        return [{"skill_id": skill_id, "patches": ["dodge", "reposition", "attack"]}]


class _UnsafeEvolution:
    """Returns a draft that will render into code we override with unsafe content."""

    def list_patch_drafts(self, skill_id: str | None = None) -> list[dict[str, object]]:
        return [{"skill_id": skill_id, "patches": ["x"]}]


def _gap(module_path: str) -> CapabilityGap:
    return CapabilityGap(
        gap_id="gap_test1",
        skill_id="induced_combat_dodge",
        failure_code="COMBAT_TIMEOUT",
        target="ruin_guard",
        description="Repeated COMBAT_TIMEOUT on ruin_guard (x3)",
        occurrence_count=3,
        module_path=module_path,
        failing_action={"skill": "attack", "target": "ruin_guard"},
    )


@pytest.fixture
def queue_path(tmp_path: Path) -> Path:
    return tmp_path / "queue" / "proposals.jsonl"


@pytest.fixture
def module_root(tmp_path: Path) -> Path:
    root = tmp_path / "modroot"
    root.mkdir()
    return root


# -- (a) gap -> PENDING, target module unchanged ----------------------------


def test_propose_creates_pending_and_does_not_touch_module(
    queue_path: Path, module_root: Path
) -> None:
    hot = _RecordingHotReload()
    coord = SelfModificationCoordinator(
        evolution_engine=_StubEvolution(),
        hot_reload_manager=hot,
        queue_path=queue_path,
        module_root=module_root,
    )
    target_rel = "capsules/generated/patch_skill.py"
    pid = coord.propose_from_gap(_gap(target_rel))

    assert pid is not None
    proposal = coord.get(pid)
    assert proposal is not None
    assert proposal.status == ProposalStatus.PENDING
    assert proposal.source == "evolution_template"
    # Module file must NOT exist — propose applies nothing.
    assert not (module_root / target_rel).exists()
    # HotReloadManager must NOT have been touched by propose.
    assert hot.watched == []
    assert hot.reload_all_calls == 0
    # It is listed as pending.
    assert [p.proposal_id for p in coord.list_pending()] == [pid]


def test_pending_proposal_does_not_modify_module_until_approve(
    queue_path: Path, module_root: Path
) -> None:
    """Structural gating proof: a PENDING proposal leaves the module path empty;
    only approve() materializes it."""
    hot = _RecordingHotReload()
    coord = SelfModificationCoordinator(
        evolution_engine=_StubEvolution(),
        hot_reload_manager=hot,
        queue_path=queue_path,
        module_root=module_root,
    )
    target_rel = "capsules/generated/gated.py"
    pid = coord.propose_from_gap(_gap(target_rel))
    assert pid is not None

    # Still PENDING after listing/reviewing — review is read-only.
    _ = coord.list_pending()
    _ = coord.get(pid)
    assert not (module_root / target_rel).exists()
    assert hot.reload_all_calls == 0

    # Now approve — this is the ONLY thing that writes the module.
    signal = coord.approve(pid)
    assert signal is not None
    assert (module_root / target_rel).exists()


# -- (b) approve -> reload invoked + retry_signal + APPLIED -----------------


def test_approve_applies_reloads_and_returns_retry_signal(
    queue_path: Path, module_root: Path
) -> None:
    hot = _RecordingHotReload()
    coord = SelfModificationCoordinator(
        evolution_engine=_StubEvolution(),
        hot_reload_manager=hot,
        queue_path=queue_path,
        module_root=module_root,
    )
    target_rel = "capsules/generated/applied_skill.py"
    pid = coord.propose_from_gap(_gap(target_rel))
    assert pid is not None

    signal = coord.approve(pid)

    assert signal is not None
    assert signal.proposal_id == pid
    assert signal.skill_id == "induced_combat_dodge"
    assert signal.failing_action == {"skill": "attack", "target": "ruin_guard"}
    assert signal.reloaded is True
    # HotReloadManager.reload pathway invoked exactly once.
    assert hot.reload_all_calls == 1
    assert hot.watched == ["capsules.generated.applied_skill"]
    # File written with the approved code.
    written = (module_root / target_rel).read_text(encoding="utf-8")
    assert "def execute(context):" in written
    # Status is APPLIED.
    assert coord.get(pid).status == ProposalStatus.APPLIED

    # retry_signal can record the post-retry outcome (measurement slot).
    signal.record_outcome(succeeded=True)
    assert signal.retried is True
    assert signal.retry_succeeded is True
    assert signal.measured_at is not None


# -- (c) reject -> discarded ------------------------------------------------


def test_reject_discards_without_touching_module(
    queue_path: Path, module_root: Path
) -> None:
    hot = _RecordingHotReload()
    coord = SelfModificationCoordinator(
        evolution_engine=_StubEvolution(),
        hot_reload_manager=hot,
        queue_path=queue_path,
        module_root=module_root,
    )
    target_rel = "capsules/generated/rejected_skill.py"
    pid = coord.propose_from_gap(_gap(target_rel))
    assert pid is not None

    assert coord.reject(pid, reason="not safe enough") is True
    assert coord.get(pid).status == ProposalStatus.REJECTED
    assert not (module_root / target_rel).exists()
    assert hot.reload_all_calls == 0
    assert coord.list_pending() == []

    # Re-rejecting / approving a non-PENDING proposal is a no-op.
    assert coord.reject(pid) is False
    assert coord.approve(pid) is None


# -- (d) unsafe / runaway code is sandbox-rejected, never enqueued ----------


class _UnsafeImportCodingAgent:
    """CodingAgent stand-in with an LLM that emits an unsafe import."""

    class _LLM:
        def generate(self, prompt: str) -> str:
            return "import os\ndef execute(context):\n    os.system('echo pwned')\n    return True\n"

    def __init__(self) -> None:
        self._llm = self._LLM()

    def generate_skill(self, task_description: str, skill_id: str = "") -> object:
        from app_service.coding_agent import CodingAgent

        return CodingAgent(llm=self._LLM()).generate_skill(task_description, skill_id=skill_id)


class _InfiniteLoopCodingAgent:
    """CodingAgent stand-in whose LLM emits a runaway infinite loop."""

    class _LLM:
        def generate(self, prompt: str) -> str:
            # Top-level runaway: this runs during exec/import, so the sandbox's
            # hard process timeout must kill it.
            return "while True:\n    pass\n"

    def __init__(self) -> None:
        self._llm = self._LLM()

    def generate_skill(self, task_description: str, skill_id: str = "") -> object:
        from app_service.coding_agent import CodingAgent

        return CodingAgent(llm=self._LLM()).generate_skill(task_description, skill_id=skill_id)


def test_unsafe_import_is_sandbox_rejected_and_never_enqueued(
    queue_path: Path, module_root: Path
) -> None:
    hot = _RecordingHotReload()
    coord = SelfModificationCoordinator(
        coding_agent=_UnsafeImportCodingAgent(),
        hot_reload_manager=hot,
        queue_path=queue_path,
        module_root=module_root,
    )
    target_rel = "capsules/generated/unsafe.py"
    pid = coord.propose_from_gap(_gap(target_rel))

    assert pid is None
    assert coord.list_pending() == []
    assert not (module_root / target_rel).exists()
    assert hot.reload_all_calls == 0
    # Nothing persisted.
    assert not queue_path.exists() or queue_path.read_text(encoding="utf-8").strip() == ""


def test_infinite_loop_is_sandbox_rejected_via_hard_timeout(
    queue_path: Path, module_root: Path
) -> None:
    hot = _RecordingHotReload()
    # Short sandbox timeout so the runaway is killed quickly.
    from app_service.code_sandbox_executor import CodeSandboxExecutor, SandboxConfig

    coord = SelfModificationCoordinator(
        coding_agent=_InfiniteLoopCodingAgent(),
        hot_reload_manager=hot,
        sandbox=CodeSandboxExecutor(SandboxConfig(timeout_sec=1.0)),
        queue_path=queue_path,
        module_root=module_root,
    )
    pid = coord.propose_from_gap(_gap("capsules/generated/runaway.py"))

    assert pid is None
    assert coord.list_pending() == []
    assert hot.reload_all_calls == 0


# -- (e) persistence round-trips pending proposals --------------------------


def test_persistence_round_trips_pending_proposals(
    queue_path: Path, module_root: Path
) -> None:
    coord = SelfModificationCoordinator(
        evolution_engine=_StubEvolution(),
        queue_path=queue_path,
        module_root=module_root,
    )
    pid1 = coord.propose_from_gap(_gap("capsules/generated/persist_a.py"))
    pid2 = coord.propose_from_gap(_gap("capsules/generated/persist_b.py"))
    assert pid1 and pid2

    # Queue file exists and contains JSONL.
    assert queue_path.exists()
    lines = [
        json.loads(line)
        for line in queue_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 2

    # Reload a fresh coordinator from disk — pending proposals survive.
    coord2 = SelfModificationCoordinator(
        evolution_engine=_StubEvolution(),
        queue_path=queue_path,
        module_root=module_root,
    )
    pending_ids = {p.proposal_id for p in coord2.list_pending()}
    assert pending_ids == {pid1, pid2}
    restored = coord2.get(pid1)
    assert restored is not None
    assert restored.status == ProposalStatus.PENDING
    assert restored.code  # code preserved for review

    # A decision in the reloaded coordinator persists too.
    assert coord2.reject(pid2, reason="stale") is True
    coord3 = SelfModificationCoordinator(
        evolution_engine=_StubEvolution(),
        queue_path=queue_path,
        module_root=module_root,
    )
    assert coord3.get(pid2).status == ProposalStatus.REJECTED
    assert {p.proposal_id for p in coord3.list_pending()} == {pid1}


# -- (f) approve() path-guard: unsafe module_path is blocked, never written ----


@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape.py",                       # traversal
        "capsules/../../escape.py",           # traversal via allow-listed prefix
        "secrets/evil.py",                    # not in allow-list
        "core/state_bus.py",                  # not in allow-list (core is protected)
    ],
)
def test_approve_blocks_unsafe_module_path(
    queue_path: Path, module_root: Path, bad_path: str
) -> None:
    """approve() must refuse to write self-generated code outside the sanctioned
    allow-list or via path traversal — even though the proposal is otherwise valid."""
    hot = _RecordingHotReload()
    coord = SelfModificationCoordinator(
        evolution_engine=_StubEvolution(),
        hot_reload_manager=hot,
        queue_path=queue_path,
        module_root=module_root,
    )
    pid = coord.propose_from_gap(_gap(bad_path))
    assert pid is not None  # proposal is created (gating is on apply, not propose)

    signal = coord.approve(pid)
    assert signal is not None
    assert signal.reloaded is False
    # The unsafe target was NEVER written and the reloader was NEVER invoked.
    assert hot.reload_all_calls == 0
    assert coord.get(pid).status == ProposalStatus.FAILED
    assert "unsafe module_path" in coord.get(pid).reload_error


def test_modification_proposal_dict_round_trip() -> None:
    proposal = ModificationProposal(
        proposal_id="mod_x",
        gap_id="gap_x",
        skill_id="s",
        module_path="a/b.py",
        code="def execute(context):\n    return True\n",
        source="evolution_template",
        status=ProposalStatus.PENDING,
        created_at=1.0,
        sandbox_success=True,
        sandbox_output="ok",
        sandbox_error="",
        sandbox_timed_out=False,
        sandbox_unsafe_imports=(),
        gap_description="desc",
        failing_action={"k": "v"},
    )
    restored = ModificationProposal.from_dict(proposal.to_dict())
    assert restored == proposal
