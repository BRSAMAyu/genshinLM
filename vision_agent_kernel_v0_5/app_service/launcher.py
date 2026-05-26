"""GenesisAgent Launcher: One-Click setup and orchestration for the backend & desktop GUI."""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "launcher.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("Launcher")

@dataclass
class DiagnosticReport:
    python_ok: bool
    node_ok: bool
    requirements_ok: bool
    gui_built: bool
    port_available: bool
    errors: list[str] = field(default_factory=list)

class GenesisLauncher:
    """Orchestrates setup, diagnostics, and running processes for GenesisAgent."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, debug: bool = False) -> None:
        self.host = host
        self.port = port
        self.debug = debug
        self.backend_proc: subprocess.Popen | None = None
        self.frontend_proc: subprocess.Popen | None = None
        self._shutdown_event = threading.Event()

    def run_diagnostics(self) -> DiagnosticReport:
        """Evaluate system health before boot."""
        log.info("Running system diagnostics...")
        report = DiagnosticReport(
            python_ok=sys.version_info >= (3, 10),
            node_ok=shutil.which("node") is not None,
            requirements_ok=True,
            gui_built=(ROOT / "desktop" / "dist" / "index.html").exists(),
            port_available=self._check_port(self.port),
        )

        if not report.python_ok:
            report.errors.append(f"Python 3.10+ required. Current version is {sys.version.split()[0]}")

        if not report.node_ok:
            report.errors.append("Node.js was not found on your system PATH. Node is required for desktop GUI.")

        # Check critical Python modules
        critical_modules = ["fastapi", "uvicorn", "numpy", "Pillow"]
        for mod in critical_modules:
            try:
                __import__(mod)
            except ImportError:
                report.requirements_ok = False
                report.errors.append(f"Missing required Python dependency: {mod}")

        return report

    def auto_repair(self, report: DiagnosticReport) -> bool:
        """Attempt to repair missing dependencies automatically."""
        log.info("Attempting automatic environment repair...")
        
        # 1. Repair python packages
        if not report.requirements_ok:
            req_file = ROOT / "requirements.txt"
            if req_file.exists():
                log.info("Installing backend dependencies via pip...")
                try:
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
                        check=True,
                        cwd=str(ROOT)
                    )
                    report.requirements_ok = True
                    log.info("Backend dependencies installed successfully!")
                except subprocess.SubprocessError as e:
                    log.error("Failed to install Python requirements: %s", e)
                    return False
            else:
                log.warning("requirements.txt not found, skipping pip installation")

        # 2. Repair Node.js / frontend dependencies
        desktop_dir = ROOT / "desktop"
        node_modules = desktop_dir / "node_modules"
        if report.node_ok and not node_modules.exists():
            log.info("Running npm install in desktop directory...")
            npm = shutil.which("npm")
            if npm is None:
                log.error("npm disappeared from PATH during repair")
                return False
            try:
                subprocess.run(
                    [npm, "install"],
                    check=True,
                    cwd=str(desktop_dir)
                )
                log.info("Frontend Node packages installed successfully!")
            except subprocess.SubprocessError as e:
                log.error("Failed to run npm install: %s", e)
                return False

        # 3. Build frontend if missing and Node is available
        if report.node_ok and not report.gui_built:
            log.info("Building frontend production distribution...")
            npm = shutil.which("npm")
            if npm is None:
                log.error("npm disappeared from PATH during frontend build")
                return False
            try:
                subprocess.run(
                    [npm, "run", "build"],
                    check=True,
                    cwd=str(desktop_dir)
                )
                report.gui_built = True
                log.info("Frontend successfully compiled!")
            except subprocess.SubprocessError as e:
                log.error("Failed to compile frontend build: %s", e)
                return False

        return True

    def start_backend(self) -> bool:
        """Start the FastAPI backend service."""
        log.info("Starting GenesisAgent backend FastAPI service on http://%s:%d...", self.host, self.port)
        cmd = [
            sys.executable, "-m", "uvicorn", "app_service.main:app",
            "--host", self.host, "--port", str(self.port)
        ]
        
        log_file = LOG_DIR / "backend.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self.backend_proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=open(log_file, "w", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            )
            # Verify endpoint health
            time.sleep(1.5)
            if self._verify_health():
                log.info("Backend service is HEALTHY!")
                return True
            else:
                log.error("Backend started but failed health checks. Check logs/backend.log")
                return False
        except Exception as e:
            log.error("Failed to spawn backend process: %s", e)
            return False

    def start_frontend(self, mode: str = "dev") -> bool:
        """Start the Vite / Tauri desktop application."""
        desktop_dir = ROOT / "desktop"
        if not shutil.which("npm"):
            log.warning("npm not available, cannot launch frontend server")
            return False

        log.info("Launching desktop frontend in '%s' mode...", mode)
        npm = shutil.which("npm")
        if npm is None:
            log.warning("npm not available, cannot launch frontend server")
            return False
        cmd = [npm, "run", "dev"] if mode == "dev" else [npm, "run", "tauri", "dev"]
        log_file = LOG_DIR / "frontend.log"
        
        try:
            self.frontend_proc = subprocess.Popen(
                cmd,
                cwd=str(desktop_dir),
                stdout=open(log_file, "w", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            )
            log.info("Frontend process spawned! GUI active at http://127.0.0.1:5173")
            return True
        except Exception as e:
            log.error("Failed to spawn frontend: %s", e)
            return False

    def monitor(self) -> None:
        """Block and monitor child processes until shutdown is triggered."""
        log.info("GenesisAgent pipeline successfully initialized! Press Ctrl+C to terminate.")
        try:
            while not self._shutdown_event.is_set():
                # Process checks
                if self.backend_proc and self.backend_proc.poll() is not None:
                    log.error("Backend process exited unexpectedly! code=%s", self.backend_proc.returncode)
                    break
                if self.frontend_proc and self.frontend_proc.poll() is not None:
                    log.warning("Frontend server closed. code=%s", self.frontend_proc.returncode)
                    break
                time.sleep(1.0)
        except KeyboardInterrupt:
            log.info("KeyboardInterrupt caught, initiating shutdown procedure...")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Clean up and release all active service processes."""
        self._shutdown_event.set()
        log.info("Shutting down processes cleanly...")
        
        if self.frontend_proc:
            log.info("Terminating frontend process...")
            self._kill_process_tree(self.frontend_proc)
            
        if self.backend_proc:
            log.info("Terminating backend process...")
            self._kill_process_tree(self.backend_proc)

        log.info("All services shut down successfully.")

    def _check_port(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("127.0.0.1", port)) != 0

    def _verify_health(self) -> bool:
        try:
            import urllib.request
            url = f"http://{self.host}:{self.port}/health"
            with urllib.request.urlopen(url, timeout=2.0) as response:
                return response.status == 200
        except Exception:
            return False

    def _kill_process_tree(self, proc: subprocess.Popen) -> None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                proc.terminate()
                proc.wait(timeout=3.0)
        except Exception as e:
            log.warning("Error when cleaning process tree pid=%d: %s", proc.pid, e)

def main() -> None:
    parser = argparse.ArgumentParser(description="GenesisAgent Launcher Utility")
    parser.add_argument("--host", default="127.0.0.1", help="Backend host interface")
    parser.add_argument("--port", type=int, default=8765, help="Backend port")
    parser.add_argument("--mode", choices=["dev", "tauri", "headless"], default="dev", help="Frontend running mode")
    parser.add_argument("--repair", action="store_true", help="Allow launcher to install missing Python/Node dependencies")
    parser.add_argument("--no-repair", action="store_true", help="Disable automatic environment repair")
    args = parser.parse_args()

    launcher = GenesisLauncher(args.host, args.port)
    report = launcher.run_diagnostics()

    if report.errors:
        log.warning("Diagnostics found outstanding issues: %s", report.errors)
        if args.repair and not args.no_repair:
            ok = launcher.auto_repair(report)
            if not ok:
                log.error("Failed to complete automatic repairs. Manual environment setup required.")
                sys.exit(1)
        else:
            log.error("Boot aborted due to missing dependencies. Re-run with --repair if you want Aurora to install them.")
            sys.exit(1)

    if not launcher.start_backend():
        log.error("Aborting boot due to backend startup failure.")
        sys.exit(1)

    if args.mode != "headless":
        launcher.start_frontend(args.mode)

    launcher.monitor()

if __name__ == "__main__":
    main()
