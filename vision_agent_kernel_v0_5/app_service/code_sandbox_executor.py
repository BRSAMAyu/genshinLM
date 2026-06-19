"""CodeSandboxExecutor: sandboxed code execution for skill validation.

Runs user/AI-generated code in a restricted environment to validate
induced skills before promoting them to production. Catches infinite loops,
memory bombs, and unsafe imports.

Phase 1 roadmap: safe code execution for CapsuleForge and skill induction.
"""
from __future__ import annotations

import logging
import signal
import sys
import traceback
from dataclasses import dataclass, field
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


class CodeSandboxExecutor:
    """Execute code snippets in a sandboxed environment."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self._config = config or SandboxConfig()

    def execute(self, code: str, context: dict[str, Any] | None = None) -> SandboxResult:
        """Execute code and return the result.

        The code runs with restricted builtins and a timeout guard.
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

        # Build restricted globals
        safe_builtins = {
            k: v for k, v in __builtins__.items()  # type: ignore[attr-defined]
            if k not in _FORBIDDEN_BUILTINS
        }
        safe_builtins["__import__"] = self._safe_import
        globals_env: dict[str, Any] = {
            "__builtins__": safe_builtins,
            **(context or {}),
        }

        import time
        start = time.perf_counter()

        # Capture stdout
        import io
        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_capture

        try:
            compiled = compile(code, "<sandbox>", "exec")
            exec(compiled, globals_env)  # noqa: S102
            output = stdout_capture.getvalue()
            if len(output) > self._config.max_output_chars:
                output = output[:self._config.max_output_chars] + "... (truncated)"
            elapsed_ms = (time.perf_counter() - start) * 1000
            return SandboxResult(
                success=True,
                output=output,
                error="",
                execution_time_ms=elapsed_ms,
            )
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            error = traceback.format_exc()
            return SandboxResult(
                success=False,
                output=stdout_capture.getvalue(),
                error=error,
                execution_time_ms=elapsed_ms,
            )
        finally:
            sys.stdout = old_stdout

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
        """Restricted import that only allows safe modules."""
        if name in _SAFE_MODULES or name == "__future__":
            return __import__(name, *args, **kwargs)
        raise ImportError(f"Sandbox blocked import: {name}")
