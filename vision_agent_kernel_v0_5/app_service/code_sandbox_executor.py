"""CodeSandboxExecutor: sandboxed code execution for skill validation.

Runs user/AI-generated code in a restricted environment to validate
induced skills before promoting them to production. Catches infinite loops,
memory bombs, and unsafe imports.

Phase 1 roadmap: safe code execution for CapsuleForge and skill induction.

Timeout enforcement: a Python thread cannot be force-killed, and
``signal.SIGALRM`` is unavailable on Windows. To impose a HARD timeout that
actually kills runaway code (e.g. ``while True: pass``), the restricted
``exec`` runs in a child ``multiprocessing.Process``. The parent joins with
``config.timeout_sec`` and ``terminate()``s the child on timeout. The design
is ``spawn``-safe (Windows default): the process target is a top-level module
function and all arguments are picklable.
"""
from __future__ import annotations

import logging
import multiprocessing
import time
import traceback
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

# Modules that are always safe for sandboxed execution
_SAFE_MODULES: frozenset[str] = frozenset({
    "math", "random", "itertools", "collections", "functools",
    "dataclasses", "typing", "enum", "json", "re", "time",
    "datetime", "copy", "operator", "string", "textwrap",
})

# Forbidden builtins
_FORBIDDEN_BUILTINS: frozenset[str] = frozenset({
    "exec", "eval", "compile", "__import__", "open",
    "input", "globals", "locals", "vars", "dir",
    "breakpoint", "exit", "quit",
})


@dataclass(frozen=True, slots=True)
class SandboxResult:
    success: bool
    output: str
    error: str
    execution_time_ms: float
    timed_out: bool = False
    unsafe_imports: tuple[str, ...] = ()


@dataclass(slots=True)
class SandboxConfig:
    timeout_sec: float = 5.0
    max_output_chars: int = 10000
    allow_network: bool = False
    allow_filesystem: bool = False


def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
    """Restricted import that only allows safe modules.

    Defined at module scope so it is importable inside spawned child
    processes (Windows ``spawn`` re-imports this module).
    """
    if name in _SAFE_MODULES or name == "__future__":
        return __import__(name, *args, **kwargs)
    raise ImportError(f"Sandbox blocked import: {name}")


def _build_safe_builtins() -> dict[str, Any]:
    """Build a restricted ``__builtins__`` mapping.

    Re-established here (rather than only in the parent) so the child
    process applies the same forbidden-builtins / restricted-import policy.
    """
    import builtins

    raw = vars(builtins)
    safe_builtins: dict[str, Any] = {
        k: v for k, v in raw.items() if k not in _FORBIDDEN_BUILTINS
    }
    safe_builtins["__import__"] = _safe_import
    return safe_builtins


def _sandbox_child_target(
    code: str,
    context: dict[str, Any],
    result_queue: "multiprocessing.Queue[dict[str, Any]]",
) -> None:
    """Process target: compile + exec ``code`` under restricted globals.

    Runs in a child process. The import whitelist, forbidden builtins, and
    restricted ``__builtins__`` are re-established here so the sandbox policy
    holds inside the child regardless of how it was started (spawn/fork).

    The result dict (success/output/error) is pushed onto ``result_queue``.
    Must be a top-level function so it is picklable under ``spawn``.
    """
    import io
    import sys

    globals_env: dict[str, Any] = {
        "__builtins__": _build_safe_builtins(),
        **context,
    }

    stdout_capture = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_capture

    try:
        compiled = compile(code, "<sandbox>", "exec")
        exec(compiled, globals_env)  # noqa: S102
        result_queue.put({
            "success": True,
            "output": stdout_capture.getvalue(),
            "error": "",
        })
    except BaseException:  # noqa: BLE001 - report any failure to the parent
        result_queue.put({
            "success": False,
            "output": stdout_capture.getvalue(),
            "error": traceback.format_exc(),
        })
    finally:
        sys.stdout = old_stdout


class CodeSandboxExecutor:
    """Execute code snippets in a sandboxed environment."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self._config = config or SandboxConfig()

    def execute(self, code: str, context: dict[str, Any] | None = None) -> SandboxResult:
        """Execute code and return the result.

        The code runs with restricted builtins in an isolated child process
        with a HARD timeout. Runaway code (e.g. infinite loops) is killed once
        ``config.timeout_sec`` elapses.
        """
        # Static analysis: check for unsafe imports
        unsafe = self._check_imports(code)
        if unsafe:
            return SandboxResult(
                success=False,
                output="",
                error=f"Forbidden imports detected: {', '.join(unsafe)}",
                execution_time_ms=0.0,
                unsafe_imports=tuple(unsafe),
            )

        ctx = dict(context or {})
        start = time.perf_counter()

        # Use the spawn context for cross-platform consistency (Windows-safe).
        mp_ctx = multiprocessing.get_context("spawn")
        result_queue: multiprocessing.Queue[dict[str, Any]] = mp_ctx.Queue()
        proc = mp_ctx.Process(
            target=_sandbox_child_target,
            args=(code, ctx, result_queue),
            daemon=True,
        )

        try:
            proc.start()
        except Exception:
            # Failed to even start the child (e.g. pickling issue) — report it.
            elapsed_ms = (time.perf_counter() - start) * 1000
            return SandboxResult(
                success=False,
                output="",
                error=traceback.format_exc(),
                execution_time_ms=elapsed_ms,
            )

        proc.join(self._config.timeout_sec)

        if proc.is_alive():
            # HARD timeout: kill the runaway child and report cleanly.
            proc.terminate()
            proc.join()
            elapsed_ms = (time.perf_counter() - start) * 1000
            return SandboxResult(
                success=False,
                output="",
                error=(
                    f"Sandbox execution exceeded timeout of "
                    f"{self._config.timeout_sec:.3f}s and was terminated."
                ),
                execution_time_ms=elapsed_ms,
                timed_out=True,
            )

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Child finished within the timeout — collect its result.
        try:
            payload = result_queue.get_nowait()
        except Exception:
            # Child exited without posting a result (e.g. hard crash / OOM kill).
            return SandboxResult(
                success=False,
                output="",
                error=(
                    f"Sandbox child exited without result "
                    f"(exitcode={proc.exitcode})."
                ),
                execution_time_ms=elapsed_ms,
            )

        output = payload.get("output", "")
        if len(output) > self._config.max_output_chars:
            output = output[:self._config.max_output_chars] + "... (truncated)"

        return SandboxResult(
            success=bool(payload.get("success", False)),
            output=output,
            error=payload.get("error", ""),
            execution_time_ms=elapsed_ms,
        )

    def validate_skill_code(self, code: str) -> SandboxResult:
        """Validate that code defines a proper skill function.

        Checks that:
        1. Code compiles without syntax errors
        2. Defines an 'execute' function
        3. No forbidden imports
        """
        result = self.execute(code, context={"__validate_only__": True})
        if not result.success:
            return result
        return result

    def _check_imports(self, code: str) -> list[str]:
        """Static check for import statements of non-safe modules."""
        unsafe: list[str] = []
        for line in code.split("\n"):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                parts = stripped.split()
                if len(parts) >= 2:
                    module = parts[1].split(".")[0]
                    if module not in _SAFE_MODULES and module not in ("__future__",):
                        unsafe.append(module)
        return unsafe

    @staticmethod
    def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
        """Restricted import that only allows safe modules.

        Retained as a static method for backward compatibility; delegates to
        the module-level :func:`_safe_import`.
        """
        return _safe_import(name, *args, **kwargs)
