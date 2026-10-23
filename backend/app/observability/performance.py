"""Lightweight local performance metrics for RepoMind pipeline stages."""
from __future__ import annotations
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Iterator

class PerformanceMetrics:
    def __init__(self, max_samples: int = 200) -> None:
        self.max_samples = max_samples
        self.samples: dict[str, list[float]] = defaultdict(list)

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            values = self.samples[stage]
            values.append((time.perf_counter() - started) * 1000)
            del values[:-self.max_samples]

    def report(self) -> dict[str, dict[str, float | int]]:
        def percentile(values: list[float], fraction: float) -> float:
            return sorted(values)[min(len(values) - 1, int((len(values) - 1) * fraction))]
        return {stage: {"count": len(values), "avg_ms": round(sum(values) / len(values), 2), "p95_ms": round(percentile(values, .95), 2)} for stage, values in self.samples.items() if values}

metrics = PerformanceMetrics()
