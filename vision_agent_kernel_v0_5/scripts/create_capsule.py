#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def create_capsule(root: Path, capsule_id: str, display_name: str | None = None, force: bool = False) -> list[Path]:
    capsule_dir = root / "capsules" / capsule_id
    if capsule_dir.exists() and not force:
        raise FileExistsError(f"capsule already exists: {capsule_dir}")
    (capsule_dir / "resources").mkdir(parents=True, exist_ok=True)
    (capsule_dir / "skills").mkdir(parents=True, exist_ok=True)

    files: dict[Path, str] = {
        capsule_dir / "__init__.py": "",
        capsule_dir / "capsule_entry.py": _entrypoint(capsule_id),
        capsule_dir / "providers.py": _providers(),
        capsule_dir / "capsule.yaml": _manifest(capsule_id, display_name or f"{capsule_id.title()} Capability Pack"),
        capsule_dir / "resources" / "ui_anchors.yaml": "anchors: []\n",
        capsule_dir / "resources" / "screen_states.yaml": "screen_states: []\n",
        capsule_dir / "resources" / "keymap.yaml": "keymaps: {}\n",
        capsule_dir / "skills" / f"{capsule_id}_basic_skills.yaml": "skills: []\n",
    }
    written: list[Path] = []
    for path, content in files.items():
        if path.exists() and not force:
            continue
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def _manifest(capsule_id: str, display_name: str) -> str:
    return f"""capsule_id: {capsule_id}
version: "0.1.0"
display_name: "{display_name}"
description: "Generated Aurora capsule scaffold."
runtime_package: "capsules.{capsule_id}"
entrypoint: "capsule_entry:{capsule_id.title().replace('_', '')}Capsule"
capabilities:
  - desktop_ui
providers: {{}}
slots:
  - {capsule_id}.screen_state
skills: []
resources:
  - resource_id: ui_anchors
    kind: yaml
    path: resources/ui_anchors.yaml
    description: UI anchor declarations.
  - resource_id: screen_states
    kind: yaml
    path: resources/screen_states.yaml
    description: Screen state declarations.
  - resource_id: keymap
    kind: yaml
    path: resources/keymap.yaml
    description: Key mapping declarations.
profiles: []
benchmark_tasks: []
"""


def _entrypoint(capsule_id: str) -> str:
    class_name = f"{capsule_id.title().replace('_', '')}Capsule"
    return f"""from __future__ import annotations


class {class_name}:
    capsule_id = "{capsule_id}"

    def install(self, context) -> None:
        return None

    def uninstall(self, context) -> None:
        return None
"""


def _providers() -> str:
    return '"""Generated provider module. Add game-specific providers here."""\n'


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an Aurora capsule scaffold")
    parser.add_argument("capsule_id")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    written = create_capsule(Path(args.root), args.capsule_id, args.display_name, args.force)
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
