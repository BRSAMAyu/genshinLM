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
