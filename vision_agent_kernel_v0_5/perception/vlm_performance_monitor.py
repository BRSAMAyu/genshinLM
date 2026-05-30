"""VLM performance monitor for Genshin Impact visual language model analysis.

P-40~P-42: Monitors VLM response latency, P95 timeout thresholds,
and implements automatic degradation strategies.

Features:
- Response time tracking with percentile analysis
- P95 latency threshold monitoring
- Automatic quality degradation on timeout
- Performance history and trend analysis
"""
from __future__ import annotations

import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PerformanceMetric:
    """Single VLM call performance metric."""
    call_id: str
    latency_ms: float
    timestamp: float
    success: bool
    error_type: str | None = None
    quality_level: int = 3  # 1=low, 2=medium, 3=high


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    """Summary of VLM performance over time window."""
    total_calls: int
    success_rate: float
    mean_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    timeout_count: int
    current_quality_level: int
    recommended_quality_level: int
    is_healthy: bool


@dataclass(frozen=True, slots=True)
class DegradationEvent:
    """Record of quality degradation action."""
    timestamp: float
    from_quality: int
    to_quality: int
    reason: str
    latency_ms: float


class VLMPerformanceMonitor:
    """Monitor VLM performance and manage quality degradation.

    Features:
    - Tracks latency of all VLM calls
    - Computes percentile statistics (P50, P95, P99)
    - Detects performance degradation trends
    - Automatically reduces quality when timeouts occur
    - Provides performance summaries

    Quality levels:
    - 1: Low (fast, less detail)
    - 2: Medium (balanced)
    - 3: High (slow, maximum detail)
    """

    # Default thresholds
    DEFAULT_P95_THRESHOLD_MS = 5000  # 5 seconds
    DEFAULT_P99_THRESHOLD_MS = 10000  # 10 seconds
    DEFAULT_TIMEOUT_MS = 15000  # 15 seconds for hard timeout

    # Degradation triggers
    DEGRADE_TIMEOUT_COUNT = 3      # Degrade after 3 timeouts in window
    DEGRADE_P95_EXCEED_COUNT = 5   # Degrade after 5 P95 exceedances
    RECOVERY_CALL_COUNT = 10       # Calls needed before quality recovery

    def __init__(
        self,
        now_fn=None,
        p95_threshold_ms: float = DEFAULT_P95_THRESHOLD_MS,
        timeout_ms: float = DEFAULT_TIMEOUT_MS,
        max_history: int = 100,
    ) -> None:
        """Initialize VLM performance monitor.

        Args:
            now_fn: Time function (default: time.perf_counter)
            p95_threshold_ms: P95 latency threshold before warning
            timeout_ms: Hard timeout threshold
            max_history: Maximum number of calls to keep in history
        """
        self._now_fn = now_fn or time.perf_counter
        self._p95_threshold = p95_threshold_ms
        self._timeout_ms = timeout_ms
        self._max_history = max_history

        self._call_history: deque[PerformanceMetric] = deque(maxlen=max_history)
        self._degradation_events: deque[DegradationEvent] = deque(maxlen=50)

        self._current_quality: int = 3  # Start at high quality
        self._calls_since_degrade: int = 0
        self._timeout_count_in_window: int = 0
        self._p95_exceed_count: int = 0

        self._last_summary: PerformanceSummary | None = None

    @property
    def current_quality(self) -> int:
        """Get current quality level (1=low, 3=high)."""
        return self._current_quality

    @property
    def p95_threshold(self) -> float:
        """Get P95 threshold in ms."""
        return self._p95_threshold

    def record_call(
        self,
        call_id: str,
        latency_ms: float,
        success: bool,
        error_type: str | None = None,
        quality_level: int | None = None,
    ) -> None:
        """Record a VLM call performance.

        Args:
            call_id: Unique identifier for this call
            latency_ms: Actual latency in milliseconds
            success: Whether the call succeeded
            error_type: Type of error if failed
            quality_level: Quality level used (default: current)
        """
        now = self._now_fn()

        metric = PerformanceMetric(
            call_id=call_id,
            latency_ms=latency_ms,
            timestamp=now,
            success=success,
            error_type=error_type,
            quality_level=quality_level or self._current_quality,
        )

        self._call_history.append(metric)
        self._calls_since_degrade += 1

        # Check for timeout
        if latency_ms >= self._timeout_ms or not success:
            self._timeout_count_in_window += 1

            # Check if we need to degrade
            if self._timeout_count_in_window >= self.DEGRADE_TIMEOUT_COUNT:
                self._degrade_quality(f"timeout_count:{self._timeout_count_in_window}", latency_ms)
                self._timeout_count_in_window = 0

        # Check P95 threshold
        if latency_ms > self._p95_threshold:
            self._p95_exceed_count += 1

            if self._p95_exceed_count >= self.DEGRADE_P95_EXCEED_COUNT:
                self._degrade_quality(f"p95_exceed:{self._p95_exceed_count}", latency_ms)
                self._p95_exceed_count = 0

        # Check for recovery opportunity
        self._check_recovery()

    def _degrade_quality(self, reason: str, latency_ms: float) -> None:
        """Degrade quality level."""
        if self._current_quality <= 1:
            return  # Already at minimum

        old_quality = self._current_quality
        self._current_quality -= 1
        self._calls_since_degrade = 0

        event = DegradationEvent(
            timestamp=self._now_fn(),
            from_quality=old_quality,
            to_quality=self._current_quality,
            reason=reason,
            latency_ms=latency_ms,
        )
        self._degradation_events.append(event)

        log.warning(
            "[VLMPerfMonitor] Degraded quality %d -> %d: %s (latency=%.1fms)",
            old_quality, self._current_quality, reason, latency_ms,
        )

    def _check_recovery(self) -> None:
        """Check if we can recover to higher quality."""
        if self._current_quality >= 3:
            return  # Already at max

        if self._calls_since_degrade < self.RECOVERY_CALL_COUNT:
            return  # Not enough calls since degrade

        # Check recent performance
        recent_calls = list(self._call_history)[-self.RECOVERY_CALL_COUNT:]
        recent_success_rate = sum(1 for c in recent_calls if c.success) / len(recent_calls)
        recent_avg_latency = statistics.mean(c.latency_ms for c in recent_calls)

        # Recover if performance is good
        if recent_success_rate >= 0.95 and recent_avg_latency < self._p95_threshold * 0.8:
            old_quality = self._current_quality
            self._current_quality += 1
            self._calls_since_degrade = 0

            event = DegradationEvent(
                timestamp=self._now_fn(),
                from_quality=old_quality,
                to_quality=self._current_quality,
                reason="recovery",
                latency_ms=recent_avg_latency,
            )
            self._degradation_events.append(event)

            log.info(
                "[VLMPerfMonitor] Recovered quality %d -> %d",
                old_quality, self._current_quality,
            )

    def get_summary(self, window_size: int = 50) -> PerformanceSummary:
        """Get performance summary over recent calls.

        Args:
            window_size: Number of recent calls to consider

        Returns:
            PerformanceSummary with statistics
        """
        if len(self._call_history) == 0:
            return PerformanceSummary(
                total_calls=0,
                success_rate=0.0,
                mean_latency_ms=0.0,
                p50_latency_ms=0.0,
                p95_latency_ms=0.0,
                p99_latency_ms=0.0,
                timeout_count=0,
                current_quality_level=self._current_quality,
                recommended_quality_level=self._current_quality,
                is_healthy=True,
            )

        # Get recent calls
        recent = list(self._call_history)[-window_size:]

        latencies = [c.latency_ms for c in recent]
        success_count = sum(1 for c in recent if c.success)

        # Calculate percentiles
        sorted_latencies = sorted(latencies)
        p50_idx = int(len(sorted_latencies) * 0.50)
        p95_idx = int(len(sorted_latencies) * 0.95)
        p99_idx = int(len(sorted_latencies) * 0.99)

        p50 = sorted_latencies[p50_idx] if sorted_latencies else 0.0
        p95 = sorted_latencies[p95_idx] if sorted_latencies else 0.0
        p99 = sorted_latencies[p99_idx] if sorted_latencies else 0.0

        timeout_count = sum(1 for c in recent if c.latency_ms >= self._timeout_ms or not c.success)

        # Determine health status
        is_healthy = (
            p95 < self._p95_threshold and
            timeout_count < window_size * 0.1  # Less than 10% timeout rate
        )

        # Calculate recommended quality based on current performance
        recommended = self._current_quality
        if p95 > self._p95_threshold * 1.5:
            recommended = max(1, self._current_quality - 1)
        elif p95 < self._p95_threshold * 0.7 and self._current_quality < 3:
            recommended = min(3, self._current_quality + 1)

        self._last_summary = PerformanceSummary(
            total_calls=len(recent),
            success_rate=success_count / len(recent) if recent else 0.0,
            mean_latency_ms=statistics.mean(latencies) if latencies else 0.0,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            timeout_count=timeout_count,
            current_quality_level=self._current_quality,
            recommended_quality_level=recommended,
            is_healthy=is_healthy,
        )

        return self._last_summary

    def should_degrade(self) -> tuple[bool, str]:
        """Check if quality should be degraded now.

        Returns:
            Tuple of (should_degrade, reason)
        """
        if self._current_quality <= 1:
            return False, "already_minimum"

        summary = self.get_summary()

        if summary.timeout_count >= 2:
            return True, "multiple_timeouts"

        if summary.p95_latency_ms > self._p95_threshold * 1.5:
            return True, "high_p95_latency"

        return False, "performance_ok"

    def get_recommended_quality(self) -> int:
        """Get recommended quality level based on current performance."""
        summary = self.get_summary()
        return summary.recommended_quality_level

    def force_quality(self, level: int) -> None:
        """Force quality level (e.g., for testing or manual override)."""
        self._current_quality = max(1, min(3, level))
        self._calls_since_degrade = 0

    def reset(self) -> None:
        """Reset monitor state."""
        self._call_history.clear()
        self._degradation_events.clear()
        self._current_quality = 3
        self._calls_since_degrade = 0
        self._timeout_count_in_window = 0
        self._p95_exceed_count = 0
        self._last_summary = None

    def get_degradation_history(self) -> tuple[DegradationEvent, ...]:
        """Get history of quality degradation events."""
        return tuple(self._degradation_events)