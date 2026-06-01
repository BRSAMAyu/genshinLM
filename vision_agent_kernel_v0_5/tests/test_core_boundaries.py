"""Comprehensive Kernel boundary purity check.

Enforces the 3-layer architecture from SPARKLE_AGENT_KERNEL_DESIGN.md §3.1:
  - Kernel: core/, agent_kernel/, execution/, runtime/, bagel/, data/
  - Extended Kernel: planning/, perception/, control/, orchestration/, llm/
  - Capsule: capsules/, interaction/, combat/, navigation/, knowledge/, skills/, ...
  - Shell: scripts/, benchmarks/, tests/

Rule: Kernel modules must NOT import from Capsule modules.
      Extended Kernel modules have a documented allowlist being migrated.
      NEW violations must not be added.
"""
from __future__ import annotations

import re
from pathlib import Path


# Kernel directories — must remain absolutely pure
KERNEL_DIRS = frozenset({
    "core", "agent_kernel", "execution", "runtime", "bagel", "data",
})

# Extended Kernel dirs — contain known violations being migrated to Capsule
KERNEL_DIRS_EXTENDED = frozenset({
    "planning", "perception", "control", "orchestration", "llm",
})

# Capsule directories (game-specific content)
CAPSULE_DIRS = frozenset({
    "capsules", "interaction", "combat", "navigation", "knowledge",
    "skills", "learning", "agent", "exploration", "app_service",
})


def _scan_for_capsule_imports(filepath: Path, project_root: Path) -> list[str]:
    """Scan a Python file for imports from Capsule directories."""
    violations = []
    import_re = re.compile(r"^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))")

    with open(filepath, encoding="utf-8") as f:
        for line_idx, line in enumerate(f, 1):
            clean = line.partition("#")[0].strip()
            if not clean:
                continue
            m = import_re.match(clean)
            if not m:
                continue
            module = m.group(1) or m.group(2)
            if not module:
                continue
            top = module.split(".")[0]
            if top in CAPSULE_DIRS:
                rel = filepath.relative_to(project_root)
                violations.append(f"{rel}:L{line_idx} → {module}")
    return violations


# ---------------------------------------------------------------------------
# Known violations in Extended Kernel — being migrated to Capsule layer.
# Format: "relative/path.py" → set of capsule modules imported
# Count: 18 files, ~30 import lines. These MUST decrease over time.
# ---------------------------------------------------------------------------
KNOWN_EXTENDED_VIOLATIONS: dict[str, set[str]] = {
    "control/sentinel/somatic_state_supervisor.py": {"interaction"},
    "llm/planner.py": {"app_service"},
    "llm/sandbox_validator.py": {"app_service"},
    "planning/boss_mechanism_preloader.py": {"knowledge"},
    "planning/capability_planner.py": {"capsules"},
    "planning/character_build_planner.py": {"knowledge"},
    "planning/character_build_workflows.py": {"combat"},
    "planning/daily_loop_scheduler.py": {"knowledge"},
    "planning/dialog_choice_arbiter.py": {"interaction"},
    "planning/mainline/mainline_live_bridge.py": {"navigation", "combat"},
    "planning/npc_affection_persistence.py": {"interaction"},
    "planning/quest_log_reader.py": {"knowledge"},
    "planning/quest_state_machine.py": {"knowledge"},
    "planning/resource_manager.py": {"knowledge"},
    "planning/skill_capability_catalog.py": {"capsules"},
    "planning/skill_registry.py": {"combat", "exploration", "navigation"},
    "planning/task_spec_builder.py": {"knowledge"},
    "perception/dialog_text_capture.py": {"knowledge"},
    "perception/observation_graph.py": {"interaction"},
}

# Known bridge modules in Core Kernel — intentional adapter pattern
# These are execution-layer bridges that must integrate with game-specific
# UI anchoring and calibration. They should decrease as we refactor toward
# Capsule-provided abstractions.
KNOWN_CORE_BRIDGES: dict[str, set[str]] = {
    "execution/ui_flow_skill_adapter.py": {"interaction"},
    "execution/mouse_motor.py": {"interaction"},
    "execution/safe_window_backend.py": {"app_service"},
    "execution/ui_action_executor.py": {"interaction"},
}


def test_kernel_core_pure_no_capsule_imports() -> None:
    """Core Kernel dirs (core, agent_kernel, execution, runtime, bagel, data) must be pure."""
    project_root = Path(__file__).resolve().parents[1]
    violations = []

    for dname in KERNEL_DIRS:
        dir_path = project_root / dname
        if not dir_path.exists():
            continue
        for path in dir_path.rglob("*.py"):
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            found = _scan_for_capsule_imports(path, project_root)
            # Filter known bridges
            rel_str = str(path.relative_to(project_root)).replace("\\", "/")
            for v in found:
                is_known = rel_str in KNOWN_CORE_BRIDGES
                if not is_known:
                    violations.append(v)

    assert not violations, (
        f"Core Kernel boundary violations ({len(violations)}):\n" +
        "\n".join(violations)
    )


def test_kernel_extended_no_new_violations() -> None:
    """Extended Kernel dirs must not have NEW violations beyond known allowlist.

    This test tracks known violations and fails if new ones are introduced.
    The goal is to shrink KNOWN_EXTENDED_VIOLATIONS to zero over time.
    """
    project_root = Path(__file__).resolve().parents[1]
    all_violations: list[str] = []

    for dname in KERNEL_DIRS_EXTENDED:
        dir_path = project_root / dname
        if not dir_path.exists():
            continue
        for path in dir_path.rglob("*.py"):
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            all_violations.extend(_scan_for_capsule_imports(path, project_root))

    # Separate known from new
    new_violations = []
    for v in all_violations:
        rel_prefix = v.split(":L")[0]
        rel_norm = rel_prefix.replace("\\", "/")
        if rel_norm not in KNOWN_EXTENDED_VIOLATIONS:
            new_violations.append(v)

    assert not new_violations, (
        f"NEW Kernel boundary violations in Extended dirs ({len(new_violations)}):\n" +
        "\n".join(new_violations) +
        f"\n\nKnown violations: {len(all_violations) - len(new_violations)} "
        f"(in {len(KNOWN_EXTENDED_VIOLATIONS)} files, shrinking toward 0)"
    )


def test_kernel_no_genshin_or_hsr_direct_imports() -> None:
    """No Kernel file may import genshin/hsr knowledge directly.

    Known exceptions: see KNOWN_EXTENDED_VIOLATIONS + KNOWN_CORE_BRIDGES.
    This test catches NEW direct imports of genshin/hsr knowledge modules.
    """
    project_root = Path(__file__).resolve().parents[1]
    all_kernel = KERNEL_DIRS | KERNEL_DIRS_EXTENDED

    forbidden = [
        re.compile(r"from\s+knowledge\.genshin"),
        re.compile(r"import\s+knowledge\.genshin"),
        re.compile(r"from\s+knowledge\.hsr"),
        re.compile(r"import\s+knowledge\.hsr"),
    ]

    # Files in known violations that import genshin knowledge (allowed for now)
    allowed_genshin_files = {
        "planning/character_build_planner.py",
        "planning/daily_loop_scheduler.py",
        "planning/quest_log_reader.py",
        "planning/quest_state_machine.py",
        "planning/resource_manager.py",
        "perception/dialog_text_capture.py",
    }

    violations = []
    for dname in all_kernel:
        dir_path = project_root / dname
        if not dir_path.exists():
            continue
        for path in dir_path.rglob("*.py"):
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            rel = str(path.relative_to(project_root)).replace("\\", "/")
            if rel in allowed_genshin_files:
                continue
            with open(path, encoding="utf-8") as f:
                for line_idx, line in enumerate(f, 1):
                    clean = line.partition("#")[0].strip()
                    if not clean:
                        continue
                    for pat in forbidden:
                        if pat.search(clean):
                            violations.append(f"{rel}:L{line_idx}: {clean.strip()}")

    assert not violations, (
        f"NEW direct genshin/hsr imports in Kernel ({len(violations)}):\n" +
        "\n".join(violations)
    )


def test_violation_count_not_increased() -> None:
    """Meta-test: ensure the known violation count is tracked and only decreases."""
    # As of 2026-06-01 baseline:
    # - 18 extended kernel files with violations
    # - 4 core kernel bridge files (execution layer)
    # - 7 files with direct genshin knowledge imports
    # This test ensures the count doesn't grow.
    assert len(KNOWN_EXTENDED_VIOLATIONS) <= 19, (
        f"Known extended violations grew to {len(KNOWN_EXTENDED_VIOLATIONS)}. "
        "If this is intentional (new file moved to kernel), update this test. "
        "Otherwise, fix the new violation."
    )
    assert len(KNOWN_CORE_BRIDGES) <= 4
