"""SelfModificationCoordinator — close the self-modification loop UP TO a human gate.

This is the "Claude Code inside the agent" feature: on a genuine capability gap
(repeated failure that skill induction cannot cover), the coordinator synthesizes
a candidate code patch, sandbox-validates it, and — if it passes — enqueues a
``ModificationProposal`` for human review. **Nothing self-generated is ever loaded
or applied without an explicit human ``approve()``.**

The gate is structural, not advisory:
- ``propose_from_gap()`` synthesizes + sandbox-validates + enqueues. It NEVER
  writes a module file and NEVER calls HotReloadManager. There is no code path
  from a ``propose_*`` method to module mutation.
- Only ``approve()`` writes code to disk and calls ``HotReloadManager.reload``.
- A sandbox rejection (unsafe import, runtime error, timeout/runaway) discards the
  candidate before it can ever reach the queue.

Pipeline:

    gap → synthesize (CodingAgent if LLM available, else EvolutionEngine/induced
          template patch) → CodeSandboxExecutor.execute → (PASS) enqueue PENDING
          → human → approve() → write file + HotReloadManager.reload → APPLIED
                              → retry_signal (re-attempt the failing action)
                  → reject() → REJECTED (discarded)

State persists to JSONL so a pending queue survives restart.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from app_service.code_sandbox_executor import CodeSandboxExecutor, SandboxResult

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_QUEUE = _ROOT / "data" / "self_modifications" / "proposals.jsonl"


class ProposalStatus(str, Enum):
    """Lifecycle states of a ModificationProposal.

    Flow::

        (synthesize + sandbox) --PASS--> PENDING --approve--> APPLIED
                                            |                    |
                                            |                    +--(reload fails)--> FAILED
                                            +--reject----------> REJECTED

        (synthesize + sandbox) --FAIL--> SANDBOX_REJECTED  (never enqueued)

    Only PENDING is a queued, reviewable state. SANDBOX_REJECTED candidates are
    never enqueued — they exist only as a discarded return value.
    """

    SANDBOX_REJECTED = "SANDBOX_REJECTED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class CapabilityGap:
    """A genuine capability gap that triggers self-modification.

    Surfaced from MetaLearningBridge induction candidates (3+ repeated identical
    failures) or EvolutionEngine repair when no induced template can cover it.
    """

    gap_id: str
    skill_id: str
    failure_code: str
    target: str
    description: str
    occurrence_count: int
    module_path: str  # repo-relative path the patch would be written to
    failing_action: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_induction_candidate(
        candidate: dict[str, Any],
        skill_id: str,
        module_path: str,
        failing_action: dict[str, Any] | None = None,
    ) -> CapabilityGap:
        """Build a gap from a MetaLearningBridge induction candidate dict.

        Candidate shape (see MetaLearningBridge._check_skill_induction_candidates):
            {"target", "failure_mode", "occurrence_count",
             "has_successful_strategies", "suggested_skill_type"}
        """
        return CapabilityGap(
            gap_id=f"gap_{uuid.uuid4().hex[:8]}",
            skill_id=skill_id,
            failure_code=str(candidate.get("failure_mode", "UNKNOWN")),
            target=str(candidate.get("target", "")),
            description=(
                f"Repeated {candidate.get('failure_mode')} on "
                f"{candidate.get('target')} (x{candidate.get('occurrence_count')})"
            ),
            occurrence_count=int(candidate.get("occurrence_count", 0)),
            module_path=module_path,
            failing_action=dict(failing_action or {}),
            context={"suggested_skill_type": candidate.get("suggested_skill_type", "")},
        )


@dataclass(slots=True)
class RetrySignal:
    """Returned by ``approve()`` — describes the action to re-attempt + a place to
    record the post-retry outcome so the system can MEASURE whether the patch helped.
    """

    proposal_id: str
    skill_id: str
    failing_action: dict[str, Any]
    module_path: str
    reloaded: bool
    # Post-retry measurement slots (filled by whoever re-runs the action):
    retried: bool = False
    retry_succeeded: bool | None = None
    measured_at: float | None = None

    def record_outcome(self, *, succeeded: bool) -> None:
        """Record the result of re-attempting the failing action."""
        self.retried = True
        self.retry_succeeded = succeeded
        self.measured_at = time.perf_counter()


@dataclass(slots=True)
class ModificationProposal:
    """A self-generated code patch awaiting (or past) human review.

    A proposal only ever exists in the human-approval queue in PENDING state.
    It transitions to APPLIED / REJECTED / FAILED solely via the gated methods.
    """

    proposal_id: str
    gap_id: str
    skill_id: str
    module_path: str
    code: str
    source: str  # "coding_agent" | "evolution_template" | "induced_patch"
    status: ProposalStatus
    created_at: float
    # Validation evidence (the sandbox result that allowed enqueue):
    sandbox_success: bool
    sandbox_output: str
    sandbox_error: str
    sandbox_timed_out: bool
    sandbox_unsafe_imports: tuple[str, ...]
    # Trigger context for the reviewer:
    gap_description: str
    failing_action: dict[str, Any] = field(default_factory=dict)
    # Filled on approve/reject:
    decided_at: float | None = None
    decision_reason: str = ""
    reload_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "gap_id": self.gap_id,
            "skill_id": self.skill_id,
            "module_path": self.module_path,
            "code": self.code,
            "source": self.source,
            "status": self.status.value,
            "created_at": self.created_at,
            "sandbox_success": self.sandbox_success,
            "sandbox_output": self.sandbox_output,
            "sandbox_error": self.sandbox_error,
            "sandbox_timed_out": self.sandbox_timed_out,
            "sandbox_unsafe_imports": list(self.sandbox_unsafe_imports),
            "gap_description": self.gap_description,
            "failing_action": self.failing_action,
            "decided_at": self.decided_at,
            "decision_reason": self.decision_reason,
            "reload_error": self.reload_error,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ModificationProposal:
        return ModificationProposal(
            proposal_id=str(data["proposal_id"]),
            gap_id=str(data.get("gap_id", "")),
            skill_id=str(data.get("skill_id", "")),
            module_path=str(data.get("module_path", "")),
            code=str(data.get("code", "")),
            source=str(data.get("source", "")),
            status=ProposalStatus(str(data.get("status", "PENDING"))),
            created_at=float(data.get("created_at", 0.0)),
            sandbox_success=bool(data.get("sandbox_success", False)),
            sandbox_output=str(data.get("sandbox_output", "")),
            sandbox_error=str(data.get("sandbox_error", "")),
            sandbox_timed_out=bool(data.get("sandbox_timed_out", False)),
            sandbox_unsafe_imports=tuple(data.get("sandbox_unsafe_imports", []) or []),
            gap_description=str(data.get("gap_description", "")),
            failing_action=dict(data.get("failing_action", {}) or {}),
            decided_at=data.get("decided_at"),
            decision_reason=str(data.get("decision_reason", "")),
            reload_error=str(data.get("reload_error", "")),
        )


class _LLMProvider(Protocol):
    def generate(self, prompt: str) -> str: ...


class _HotReloader(Protocol):
    """Subset of HotReloadManager used here (duck-typed for testability)."""

    def watch(self, module_name: str) -> None: ...
    def reload_all(self) -> list[Any]: ...


class SelfModificationCoordinator:
    """Coordinate gap → synthesized patch → sandbox → human-gated apply.

    Args:
        coding_agent: optional CodingAgent (used when an LLM is wired in). If it
            cannot produce passing code, we fall back to the induced/template patch.
        evolution_engine: optional EvolutionEngine; its repair drafts (proposed
            steps / template code) are the fallback patch source.
        hot_reload_manager: HotReloadManager-like object. Only invoked from
            ``approve()``.
        sandbox: CodeSandboxExecutor (the now-safe, process-isolated one).
        queue_path: JSONL file the pending queue persists to.
        module_root: filesystem root that ``module_path`` is resolved against.
    """

    def __init__(
        self,
        *,
        coding_agent: Any | None = None,
        evolution_engine: Any | None = None,
        hot_reload_manager: _HotReloader | None = None,
        sandbox: CodeSandboxExecutor | None = None,
        queue_path: Path | str | None = None,
        module_root: Path | str | None = None,
        allowed_module_prefixes: tuple[str, ...] = ("capsules/", "skills/generated/"),
    ) -> None:
        self._coding_agent = coding_agent
        self._evolution = evolution_engine
        self._hot_reload = hot_reload_manager
        self._sandbox = sandbox or CodeSandboxExecutor()
        self._queue_path = Path(queue_path) if queue_path else _DEFAULT_QUEUE
        self._module_root = Path(module_root) if module_root else _ROOT
        # Approval may only ever write into these sanctioned subtrees. Self-generated
        # code is never written outside the allow-list, never via an absolute path,
        # and never via a '..' traversal (enforced in approve()).
        self._allowed_prefixes = tuple(p.replace("\\", "/") for p in allowed_module_prefixes)
        self._proposals: dict[str, ModificationProposal] = {}
        self._queue_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    # -- gate-safe synthesis side (NEVER applies / reloads) ------------------

    def propose_from_gap(self, gap: CapabilityGap) -> str | None:
        """Synthesize a candidate patch for ``gap``, sandbox-validate it, and — only
        if it passes — enqueue a PENDING proposal.

        Returns the proposal id on enqueue, or ``None`` if the candidate was
        sandbox-rejected (unsafe import / runtime error / timeout) or no patch
        could be synthesized. **Applies nothing.** There is no path from here to
        a module write or hot-reload.
        """
        synthesized = self._synthesize(gap)
        if synthesized is None:
            log.info("[SelfMod] No patch could be synthesized for gap %s", gap.gap_id)
            return None
        code, source = synthesized

        result = self._sandbox.execute(code)
        if not result.success:
            # Discarded BEFORE the queue — unsafe import, runtime error, or runaway.
            log.warning(
                "[SelfMod] Candidate for gap %s sandbox-rejected (timed_out=%s, "
                "unsafe=%s): %s",
                gap.gap_id, result.timed_out, result.unsafe_imports,
                (result.error or "")[:200],
            )
            return None

        proposal = ModificationProposal(
            proposal_id=f"mod_{uuid.uuid4().hex[:10]}",
            gap_id=gap.gap_id,
            skill_id=gap.skill_id,
            module_path=gap.module_path,
            code=code,
            source=source,
            status=ProposalStatus.PENDING,
            created_at=time.perf_counter(),
            sandbox_success=result.success,
            sandbox_output=result.output,
            sandbox_error=result.error,
            sandbox_timed_out=result.timed_out,
            sandbox_unsafe_imports=result.unsafe_imports,
            gap_description=gap.description,
            failing_action=dict(gap.failing_action),
        )
        self._proposals[proposal.proposal_id] = proposal
        self._persist()
        log.info(
            "[SelfMod] Enqueued PENDING proposal %s for gap %s (source=%s) — "
            "awaiting human approval",
            proposal.proposal_id, gap.gap_id, source,
        )
        return proposal.proposal_id

    def _synthesize(self, gap: CapabilityGap) -> tuple[str, str] | None:
        """Produce candidate code. Prefer CodingAgent+LLM; fall back to the
        induced/template patch from EvolutionEngine. Returns (code, source)."""
        # 1. CodingAgent path (only meaningful when an LLM provider is wired in).
        if self._coding_agent is not None and getattr(self._coding_agent, "_llm", None):
            try:
                generated = self._coding_agent.generate_skill(
                    task_description=gap.description,
                    skill_id=gap.skill_id,
                )
                code = getattr(generated, "code", "") or ""
                if code.strip() and not code.lstrip().startswith("# No LLM"):
                    return code, "coding_agent"
            except Exception as exc:  # noqa: BLE001 - fall through to template
                log.debug("[SelfMod] CodingAgent synthesis failed: %s", exc)

        # 2. EvolutionEngine fallback: harvest a draft's code/template patch.
        template = self._template_from_evolution(gap)
        if template is not None:
            return template, "evolution_template"

        return None

    def _template_from_evolution(self, gap: CapabilityGap) -> str | None:
        """Derive fallback patch code from EvolutionEngine repair drafts.

        Looks for an existing draft whose induced/template steps we can render
        into a minimal ``execute(context)`` skill body. This is deterministic and
        side-effect free (no apply)."""
        if self._evolution is None:
            return None
        try:
            drafts = self._evolution.list_patch_drafts(skill_id=gap.skill_id)
        except Exception as exc:  # noqa: BLE001
            log.debug("[SelfMod] EvolutionEngine.list_patch_drafts failed: %s", exc)
            drafts = []
        steps: list[Any] = []
        for draft in drafts:
            cand = draft.get("patches") or draft.get("proposed_steps") or []
            if cand:
                steps = cand
                break
        return self._render_template_skill(gap, steps)

    @staticmethod
    def _render_template_skill(gap: CapabilityGap, steps: list[Any]) -> str:
        """Render a minimal, sandbox-safe ``execute(context)`` skill from steps.

        Uses only print/return so it passes the sandbox (no I/O, no imports)."""
        rendered_steps = json.dumps([str(s) for s in steps]) if steps else "[]"
        return (
            f"# Auto-synthesized patch for gap {gap.gap_id}\n"
            f"# Skill: {gap.skill_id} | Failure: {gap.failure_code}\n"
            f"def execute(context):\n"
            f"    steps = {rendered_steps}\n"
            f"    for step in steps:\n"
            f"        print('step:', step)\n"
            f"    return True\n"
        )

    # -- review side (read-only) ---------------------------------------------

    def list_pending(self) -> list[ModificationProposal]:
        return [p for p in self._proposals.values() if p.status == ProposalStatus.PENDING]

    def get(self, proposal_id: str) -> ModificationProposal | None:
        return self._proposals.get(proposal_id)

    # -- gated apply side (the ONLY place code may load) ---------------------

    def approve(self, proposal_id: str) -> RetrySignal | None:
        """Human approval. ONLY here may code be written to disk + hot-reloaded.

        Writes the approved code to its module path, asks HotReloadManager to
        reload that module, marks APPLIED (or FAILED if the reload errored), and
        returns a RetrySignal describing the original failing action to re-attempt
        plus a place to record the post-retry outcome.
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != ProposalStatus.PENDING:
            log.warning("[SelfMod] approve() rejected: %s not PENDING", proposal_id)
            return None

        proposal.status = ProposalStatus.APPROVED
        # Hard path guard: a self-generated patch may only ever land inside the
        # sanctioned subtrees. Reject absolute paths, '..' traversal, and any
        # target that escapes module_root.
        if not self._is_safe_module_path(proposal.module_path):
            proposal.status = ProposalStatus.FAILED
            proposal.reload_error = f"unsafe module_path rejected: {proposal.module_path}"
            proposal.decided_at = time.perf_counter()
            self._persist()
            log.error("[SelfMod] approve() blocked unsafe path for %s: %s",
                      proposal_id, proposal.module_path)
            return RetrySignal(
                proposal_id=proposal.proposal_id, skill_id=proposal.skill_id,
                failing_action=dict(proposal.failing_action),
                module_path=proposal.module_path, reloaded=False,
            )
        target = (self._module_root / proposal.module_path).resolve()
        reloaded = False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(proposal.code, encoding="utf-8")
            if self._hot_reload is not None:
                module_name = self._module_name_for(proposal.module_path)
                self._hot_reload.watch(module_name)
                self._hot_reload.reload_all()
                reloaded = True
            proposal.status = ProposalStatus.APPLIED
            proposal.decided_at = time.perf_counter()
            proposal.decision_reason = "approved"
        except Exception as exc:  # noqa: BLE001 - reload/write failure is reportable
            proposal.status = ProposalStatus.FAILED
            proposal.reload_error = str(exc)
            proposal.decided_at = time.perf_counter()
            log.error("[SelfMod] approve() apply failed for %s: %s", proposal_id, exc)
        self._persist()

        return RetrySignal(
            proposal_id=proposal.proposal_id,
            skill_id=proposal.skill_id,
            failing_action=dict(proposal.failing_action),
            module_path=proposal.module_path,
            reloaded=reloaded,
        )

    def reject(self, proposal_id: str, reason: str = "") -> bool:
        """Discard a pending proposal. Never touches any module."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != ProposalStatus.PENDING:
            return False
        proposal.status = ProposalStatus.REJECTED
        proposal.decided_at = time.perf_counter()
        proposal.decision_reason = reason or "rejected"
        self._persist()
        log.info("[SelfMod] Rejected proposal %s: %s", proposal_id, proposal.decision_reason)
        return True

    def _is_safe_module_path(self, module_path: str) -> bool:
        """True only if module_path is relative, '.py', traversal-free, inside an
        allow-listed subtree, and resolves within module_root."""
        raw = (module_path or "").replace("\\", "/")
        if not raw.endswith(".py") or raw.startswith("/"):
            return False
        p = Path(raw)
        if p.is_absolute() or ".." in p.parts:
            return False
        if self._allowed_prefixes and not any(raw.startswith(pre) for pre in self._allowed_prefixes):
            return False
        root = self._module_root.resolve()
        target = (self._module_root / p).resolve()
        return target == root or root in target.parents

    def reload(self) -> None:
        """Re-read the persisted queue (lets a review backend pick up proposals
        enqueued by another coordinator instance sharing the same queue file)."""
        self._proposals.clear()
        self._load()

    # -- persistence ---------------------------------------------------------

    @staticmethod
    def _module_name_for(module_path: str) -> str:
        """Convert a repo-relative .py path into an importable dotted module name."""
        p = Path(module_path)
        parts = list(p.with_suffix("").parts)
        return ".".join(parts)

    def _persist(self) -> None:
        tmp = self._queue_path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for proposal in self._proposals.values():
                fh.write(json.dumps(proposal.to_dict(), ensure_ascii=False) + "\n")
        tmp.replace(self._queue_path)

    def _load(self) -> None:
        if not self._queue_path.exists():
            return
        try:
            for line in self._queue_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                proposal = ModificationProposal.from_dict(json.loads(line))
                self._proposals[proposal.proposal_id] = proposal
        except Exception as exc:  # noqa: BLE001 - corrupt queue should not crash
            log.error("[SelfMod] Failed to load proposal queue: %s", exc)
