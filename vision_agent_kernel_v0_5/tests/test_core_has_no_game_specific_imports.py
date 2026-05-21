"""Test to enforce core static import purity and prevent game-specific bleed."""

from __future__ import annotations

import re
from pathlib import Path


def test_core_has_no_game_specific_imports() -> None:
    """Scan core directories to ensure no files contain static imports pointing to capsules.genshin or capsules.hsr."""
    project_root = Path(__file__).resolve().parents[1]
    
    # Core directories to inspect
    target_dirs = ["core", "planning", "perception", "execution", "recording"]

    forbidden_patterns = [
        re.compile(r"^\s*import\s+(capsules\.)?genshin"),
        re.compile(r"^\s*from\s+(capsules\.)?genshin\s+import"),
        re.compile(r"^\s*import\s+(capsules\.)?hsr"),
        re.compile(r"^\s*from\s+(capsules\.)?hsr\s+import"),
    ]

    violations = []

    for dname in target_dirs:
        dir_path = project_root / dname
        if not dir_path.exists():
            continue
            
        for path in dir_path.rglob("*.py"):
            # Skip python caching directories or virtual environments
            if ".venv" in path.parts or "__pycache__" in path.parts:
                continue

            with open(path, encoding="utf-8") as f:
                for line_idx, line in enumerate(f, 1):
                    # Strip comments to ignore commented out code or docs
                    clean_line, _, _ = line.partition("#")
                    clean_line = clean_line.strip()
                    
                    if not clean_line:
                        continue

                    for pattern in forbidden_patterns:
                        if pattern.search(clean_line):
                            violations.append(
                                f"{path.relative_to(project_root)}:L{line_idx} - '{clean_line}'"
                            )

    assert not violations, (
        f"Core static import purity violated! Forbidden imports found:\n" +
        "\n".join(violations)
    )
