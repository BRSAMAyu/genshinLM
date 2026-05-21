from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
from pathlib import Path


BANNED_GAME_TERMS = (
    "genshin",
    "yuan_shen",
    "yuanshen",
    "hsr",
    "honkai",
    "star_rail",
    "starrail",
)


@dataclass(frozen=True, slots=True)
class BoundaryViolation:
    path: str
    line: int
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class BoundaryScanReport:
    ok: bool
    violations: list[BoundaryViolation] = field(default_factory=list)


def scan_core_boundaries(root: str | Path, banned_terms: tuple[str, ...] = BANNED_GAME_TERMS) -> BoundaryScanReport:
    root_path = Path(root)
    core_dir = root_path / "core"
    violations: list[BoundaryViolation] = []
    if not core_dir.exists():
        return BoundaryScanReport(True, [])
    for path in core_dir.rglob("*.py"):
        rel = path.relative_to(root_path).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            violations.append(BoundaryViolation(rel, exc.lineno or 0, "syntax_error", str(exc)))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _check_module(violations, rel, node.lineno, alias.name, banned_terms)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if any(alias.name == "*" for alias in node.names):
                    violations.append(BoundaryViolation(rel, node.lineno, "wildcard_import", module))
                _check_module(violations, rel, node.lineno, module, banned_terms)
            elif isinstance(node, ast.Call):
                _check_dynamic_import(violations, rel, node, banned_terms)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                for term in banned_terms:
                    if term in lowered:
                        violations.append(BoundaryViolation(rel, node.lineno, "game_string_literal", term))
    return BoundaryScanReport(not violations, violations)


def _check_module(
    violations: list[BoundaryViolation],
    rel: str,
    line: int,
    module: str,
    banned_terms: tuple[str, ...],
) -> None:
    lowered = module.lower()
    for term in banned_terms:
        if term in lowered:
            violations.append(BoundaryViolation(rel, line, "game_specific_import", module))


def _check_dynamic_import(
    violations: list[BoundaryViolation],
    rel: str,
    node: ast.Call,
    banned_terms: tuple[str, ...],
) -> None:
    func = node.func
    is_import = isinstance(func, ast.Name) and func.id == "__import__"
    is_importlib = (
        isinstance(func, ast.Attribute)
        and func.attr == "import_module"
        and isinstance(func.value, ast.Name)
        and func.value.id == "importlib"
    )
    if not (is_import or is_importlib) or not node.args:
        return
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        _check_module(violations, rel, node.lineno, first.value, banned_terms)
    else:
        violations.append(BoundaryViolation(rel, node.lineno, "dynamic_import_nonliteral", ast.unparse(first)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan core/ for game-specific imports and dynamic boundary leaks.")
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()
    report = scan_core_boundaries(args.root)
    if report.ok:
        print("core boundary scan passed")
        return 0
    for violation in report.violations:
        print(f"{violation.path}:{violation.line}: {violation.code}: {violation.detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
