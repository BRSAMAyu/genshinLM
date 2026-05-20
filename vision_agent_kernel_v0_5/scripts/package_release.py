from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


INCLUDE_DIRS = [
    "app_service",
    "core",
    "execution",
    "perception",
    "control",
    "orchestration",
    "planning",
    "knowledge",
    "collection",
    "combat",
    "agentic",
    "learning",
    "persistence",
    "persona",
    "llm",
    "open_beta",
    "configs",
    "scripts",
    "testbed",
    "docs",
]

INCLUDE_FILES = [
    "README.md",
    "SAFETY.md",
    "ARCHITECTURE.md",
    "QUICKSTART.md",
    "INSTALL.md",
    "DEVELOPER_GUIDE.md",
    "FAQ.md",
    "pyproject.toml",
    "requirements.txt",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an open-alpha release zip without logs or private run artifacts.")
    parser.add_argument("--out", default=str(ROOT / "dist" / "aurora_open_alpha.zip"))
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "aurora_open_alpha"
        staging.mkdir()
        for directory in INCLUDE_DIRS:
            src = ROOT / directory
            if src.exists():
                shutil.copytree(src, staging / directory, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "runs", "*.log"))
        for filename in INCLUDE_FILES:
            src = ROOT / filename
            if src.exists():
                shutil.copy2(src, staging / filename)
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in staging.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(staging.parent))
    print(f"release_zip={out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
