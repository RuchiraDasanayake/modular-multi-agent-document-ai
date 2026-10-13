"""Best-effort, process-scoped resource snapshots for product run receipts."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResourceSnapshot:
    process_cpu_ns: int
    worker_rss_bytes: int | None


class ResourceProbe:
    def __init__(self) -> None:
        try:
            import psutil

            self._process: Any | None = psutil.Process()
        except Exception:  # noqa: BLE001 - monitoring is optional, extraction is not
            self._process = None

    def snapshot(self) -> ResourceSnapshot:
        rss: int | None = None
        if self._process is not None:
            try:
                measured = self._process.memory_info().rss
                if type(measured) is int and measured >= 0:
                    rss = measured
            except Exception:  # noqa: BLE001 - telemetry must not fail extraction
                pass
        return ResourceSnapshot(process_cpu_ns=time.process_time_ns(), worker_rss_bytes=rss)


def elapsed_cpu_ms(start: ResourceSnapshot, end: ResourceSnapshot) -> float:
    return max(0, end.process_cpu_ns - start.process_cpu_ns) / 1_000_000
