"""Tests for CodeSandboxExecutor."""
from __future__ import annotations

from app_service.code_sandbox_executor import CodeSandboxExecutor, SandboxConfig


class TestCodeSandboxExecutor:
    def test_simple_math(self) -> None:
        sandbox = CodeSandboxExecutor()
        result = sandbox.execute("x = 2 + 3\nprint(x)")
        assert result.success
        assert "5" in result.output

    def test_syntax_error(self) -> None:
        sandbox = CodeSandboxExecutor()
        result = sandbox.execute("if True\n  print('bad')")
        assert not result.success
        assert "SyntaxError" in result.error

    def test_runtime_error(self) -> None:
        sandbox = CodeSandboxExecutor()
        result = sandbox.execute("x = 1 / 0")
        assert not result.success
        assert "ZeroDivisionError" in result.error

    def test_forbidden_import_blocked(self) -> None:
        sandbox = CodeSandboxExecutor()
        result = sandbox.execute("import os\nos.system('echo bad')")
        assert not result.success
        assert "os" in result.error

    def test_safe_import_allowed(self) -> None:
        sandbox = CodeSandboxExecutor()
        result = sandbox.execute("import math\nprint(math.sqrt(4))")
        assert result.success
        assert "2.0" in result.output

    def test_exec_builtin_blocked(self) -> None:
        sandbox = CodeSandboxExecutor()
        result = sandbox.execute("exec('print(1)')")
        assert not result.success

    def test_context_passed(self) -> None:
        sandbox = CodeSandboxExecutor()
        result = sandbox.execute("print(value)", context={"value": 42})
        assert result.success
        assert "42" in result.output

    def test_output_truncation(self) -> None:
        sandbox = CodeSandboxExecutor(config=SandboxConfig(max_output_chars=50))
        result = sandbox.execute("print('A' * 1000)")
        assert result.success
        assert len(result.output) <= 100  # 50 + truncation suffix

    def test_timing(self) -> None:
        sandbox = CodeSandboxExecutor()
        result = sandbox.execute("x = 1 + 1")
        assert result.execution_time_ms >= 0

    def test_infinite_loop_killed_within_timeout(self) -> None:
        import time as _time

        timeout = 1.0
        sandbox = CodeSandboxExecutor(config=SandboxConfig(timeout_sec=timeout))
        start = _time.perf_counter()
        result = sandbox.execute("while True:\n    pass")
        wall = _time.perf_counter() - start
        # Must actually return (not hang) and report a timeout.
        assert not result.success
        assert result.timed_out
        # Proven not to hang: returns well under 3x the configured timeout.
        assert wall < timeout * 3, f"sandbox hung for {wall:.2f}s (timeout={timeout}s)"

    def test_timeout_does_not_fire_for_fast_code(self) -> None:
        sandbox = CodeSandboxExecutor(config=SandboxConfig(timeout_sec=5.0))
        result = sandbox.execute("print('quick')")
        assert result.success
        assert not result.timed_out
        assert "quick" in result.output
