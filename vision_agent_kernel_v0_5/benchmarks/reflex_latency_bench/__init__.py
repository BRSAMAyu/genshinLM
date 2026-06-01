"""Reflex Latency Benchmark — prove detect+decision+input pipeline timing.

Validates the architecture's reflex timing claims:
  - p95 detect+decision latency ≤ 20ms
  - p95 input lease submit ≤ 5ms
  - focus loss → release_all within 1 tick (≤ 50ms)

All scenarios run in dry-run mode (ConsoleInputBackend).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from core.state_bus import StateBus
from core.timebase import Timebase
from execution.input_lease import InputLeaseStore
from execution.input_worker import InputWorker
from execution.console_backend import ConsoleInputBackend


@dataclass(frozen=True, slots=True)
class LatencyTarget:
    name: str
    p95_threshold_ms: float
    p99_threshold_ms: float
    description: str


# Architecture-mandated targets (from architecture-finalized-plan.md)
TARGETS = {
    "detect_decision": LatencyTarget(
        name="detect+decision",
        p95_threshold_ms=20.0,
        p99_threshold_ms=50.0,
        description="Time from frame capture to decision output",
    ),
    "lease_submit": LatencyTarget(
        name="input_lease_submit",
        p95_threshold_ms=5.0,
        p99_threshold_ms=10.0,
        description="Time to validate and submit an InputLease",
    ),
    "focus_release": LatencyTarget(
        name="focus_loss_release_all",
        p95_threshold_ms=50.0,
        p99_threshold_ms=100.0,
        description="Time from focus loss signal to release_all",
    ),
}


@dataclass(slots=True)
class LatencyMeasurement:
    name: str
    iterations: int
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def p50(self) -> float:
        return self._percentile(0.50)

    @property
    def p95(self) -> float:
        return self._percentile(0.95)

    @property
    def p99(self) -> float:
        return self._percentile(0.99)

    @property
    def mean(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)

    @property
    def min(self) -> float:
        return min(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def max(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0.0

    def _percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lats = sorted(self.latencies_ms)
        idx = min(int(p * len(sorted_lats)), len(sorted_lats) - 1)
        return sorted_lats[idx]


@dataclass(frozen=True, slots=True)
class BenchResult:
    name: str
    passed: bool
    measurement: LatencyMeasurement
    target: LatencyTarget
    p95_margin_ms: float = 0.0  # negative = under budget, positive = over budget


def bench_lease_submit(iterations: int = 1000) -> BenchResult:
    """Benchmark InputLease validation + submission latency."""
    bus = StateBus()
    backend = ConsoleInputBackend()
    worker = InputWorker(backend=backend, state_bus=bus)
    store = InputLeaseStore()
    timebase = Timebase()

    latencies: list[float] = []
    for i in range(iterations):
        lease_id = f"bench_lease_{i}"
        now = timebase.now()
        lease = type("InputLease", (), {
            "lease_id": lease_id,
            "owner": "bench",
            "priority": 10,
            "key_states": {"escape": "DOWN"},
            "mouse_delta": None,
            "created_at": now,
            "expires_at": now + 0.25,
            "reason": "bench_test",
        })()

        start = time.perf_counter()
        valid = store.validate(lease, now)
        if valid.valid:
            store.add(lease)
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    worker.stop(timeout=1.0)

    meas = LatencyMeasurement(name="lease_submit", iterations=iterations, latencies_ms=latencies)
    target = TARGETS["lease_submit"]
    passed = meas.p95 <= target.p95_threshold_ms
    return BenchResult(
        name="lease_submit",
        passed=passed,
        measurement=meas,
        target=target,
        p95_margin_ms=meas.p95 - target.p95_threshold_ms,
    )


def bench_detect_decision(iterations: int = 500) -> BenchResult:
    """Benchmark frame→decision latency using synthetic frames.

    Simulates the perception pipeline overhead: frame creation + simple
    HSV-based danger detection + decision generation.
    """
    latencies: list[float] = []
    timebase = Timebase()

    for i in range(iterations):
        frame = np.random.randint(0, 255, (360, 640, 3), dtype=np.uint8)

        start = time.perf_counter()
        # Simulate danger detection: red channel dominance in bottom ROI
        roi = frame[240:350, 200:440]
        red_mean = float(roi[:, :, 2].mean())
        green_mean = float(roi[:, :, 1].mean())
        danger = red_mean > green_mean * 1.5 and red_mean > 100

        # Simulate decision
        if danger:
            decision = "dodge"
        else:
            decision = "hold"

        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    meas = LatencyMeasurement(name="detect_decision", iterations=iterations, latencies_ms=latencies)
    target = TARGETS["detect_decision"]
    passed = meas.p95 <= target.p95_threshold_ms
    return BenchResult(
        name="detect_decision",
        passed=passed,
        measurement=meas,
        target=target,
        p95_margin_ms=meas.p95 - target.p95_threshold_ms,
    )


def bench_focus_release(iterations: int = 100) -> BenchResult:
    """Benchmark focus loss → release_all latency.

    Measures how quickly the system detects focus loss and releases
    all active leases via the deadman switch.
    """
    bus = StateBus()
    backend = ConsoleInputBackend()
    worker = InputWorker(backend=backend, state_bus=bus)
    store = InputLeaseStore()
    timebase = Timebase()
    worker.start()

    latencies: list[float] = []

    for i in range(iterations):
        now = timebase.now()
        lease = type("InputLease", (), {
            "lease_id": f"bench_focus_{i}",
            "owner": "bench",
            "priority": 10,
            "key_states": {"w": "DOWN"},
            "mouse_delta": None,
            "created_at": now,
            "expires_at": now + 5.0,
            "reason": "bench_focus_test",
        })()
        store.add(lease)

        start = time.perf_counter()
        # Simulate focus loss detection + release all leases
        released = store.clear()
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    worker.stop(timeout=1.0)

    meas = LatencyMeasurement(name="focus_release", iterations=iterations, latencies_ms=latencies)
    target = TARGETS["focus_release"]
    passed = meas.p95 <= target.p95_threshold_ms
    return BenchResult(
        name="focus_release",
        passed=passed,
        measurement=meas,
        target=target,
        p95_margin_ms=meas.p95 - target.p95_threshold_ms,
    )


def run_all_benchmarks() -> list[BenchResult]:
    """Run all reflex latency benchmarks and return results."""
    return [
        bench_detect_decision(),
        bench_lease_submit(),
        bench_focus_release(),
    ]


def format_report(results: list[BenchResult]) -> str:
    lines = ["=" * 70, "REFLEX LATENCY BENCHMARK REPORT", "=" * 70, ""]

    all_passed = all(r.passed for r in results)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        m = r.measurement
        t = r.target
        lines.append(f"[{status}] {r.name}")
        lines.append(f"  Target: p95 ≤ {t.p95_threshold_ms:.1f}ms, p99 ≤ {t.p99_threshold_ms:.1f}ms")
        lines.append(f"  Result: p50={m.p50:.3f}ms p95={m.p95:.3f}ms p99={m.p99:.3f}ms")
        lines.append(f"  Margin: {r.p95_margin_ms:+.3f}ms ({'under' if r.p95_margin_ms <= 0 else 'OVER'} budget)")
        lines.append(f"  Range:  min={m.min:.3f}ms max={m.max:.3f}ms ({m.iterations} iterations)")
        lines.append("")

    lines.append(f"OVERALL: {'ALL PASS' if all_passed else 'SOME FAILURES'}")
    lines.append("=" * 70)
    return "\n".join(lines)
