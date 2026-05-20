from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class CheckResult:
    key: str
    label: str
    status: str
    detail: str


def main() -> int:
    checks = [
        _python_version(),
        _command("node", ["node", "--version"], required=False),
        _command("npm", ["npm", "--version"], required=False),
        _command("tauri", ["npm", "run", "tauri", "--", "--version"], required=False, cwd=ROOT / "desktop"),
        _module("fastapi", required=True),
        _module("uvicorn", required=True),
        _module("numpy", required=True),
        _module("dxcam", required=False),
        _module("mss", required=False),
        _module("ultralytics", required=False),
        _module("torch", required=False, label="CUDA / torch"),
        _path("configs/model.yaml", required=True),
        _path("configs/profiles/index.json", required=True),
        _path("data/skills/index.json", required=False),
        _port(8765),
        _writable("logs"),
        _gui_build(),
    ]
    for check in checks:
        icon = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}[check.status]
        print(f"[{icon}] {check.label}: {check.detail}")
    payload = {"ok": all(item.status != "fail" for item in checks), "checks": [asdict(item) for item in checks]}
    output = ROOT / "logs" / "doctor_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[doctor] report={output}")
    return 0 if payload["ok"] else 1


def _python_version() -> CheckResult:
    ok = sys.version_info >= (3, 10)
    return CheckResult("python", "Python version", "ok" if ok else "fail", sys.version.split()[0])


def _command(key: str, command: list[str], required: bool, cwd: Path | None = None) -> CheckResult:
    if shutil.which(command[0]) is None:
        return CheckResult(key, key, "fail" if required else "warn", f"{command[0]} not found")
    try:
        result = subprocess.run(" ".join(command) if os.name == "nt" else command, cwd=cwd, capture_output=True, text=True, timeout=8, check=False, shell=(os.name == "nt"))
        detail = (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr).strip() else "available"
        return CheckResult(key, key, "ok" if result.returncode == 0 else "warn", detail)
    except Exception as exc:
        return CheckResult(key, key, "fail" if required else "warn", str(exc))


def _module(name: str, required: bool, label: str | None = None) -> CheckResult:
    spec = importlib.util.find_spec(name)
    return CheckResult(name, label or name, "ok" if spec else ("fail" if required else "warn"), "available" if spec else "not installed")


def _path(relative: str, required: bool) -> CheckResult:
    path = ROOT / relative
    return CheckResult(relative, relative, "ok" if path.exists() else ("fail" if required else "warn"), "exists" if path.exists() else "missing")


def _port(port: int) -> CheckResult:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        busy = sock.connect_ex(("127.0.0.1", port)) == 0
    return CheckResult("port", f"Port {port}", "warn" if busy else "ok", "already in use" if busy else "available")


def _writable(relative: str) -> CheckResult:
    path = ROOT / relative
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".doctor_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return CheckResult("writable", f"{relative} writable", "ok", "writable")
    except OSError as exc:
        return CheckResult("writable", f"{relative} writable", "fail", str(exc))


def _gui_build() -> CheckResult:
    dist = ROOT / "desktop" / "dist" / "index.html"
    return CheckResult("gui_build", "GUI build", "ok" if dist.exists() else "warn", "built" if dist.exists() else "run npm install && npm run build")


if __name__ == "__main__":
    raise SystemExit(main())
