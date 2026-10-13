"""Resource telemetry must stay process scoped and nonfatal."""

from __future__ import annotations

import sys
import types

from idpo.product_auto.resource_telemetry import ResourceProbe, ResourceSnapshot, elapsed_cpu_ms


def test_resource_probe_reads_rss_and_survives_monitoring_failure(monkeypatch) -> None:
    class Process:
        def __init__(self) -> None:
            self.fail = False

        def memory_info(self):
            if self.fail:
                raise RuntimeError("monitor unavailable")
            return types.SimpleNamespace(rss=1024)

    process = Process()
    monkeypatch.setitem(sys.modules, "psutil", types.SimpleNamespace(Process=lambda: process))
    probe = ResourceProbe()
    first = probe.snapshot()
    process.fail = True
    second = probe.snapshot()

    assert first.worker_rss_bytes == 1024
    assert second.worker_rss_bytes is None
    assert second.process_cpu_ns >= first.process_cpu_ns


def test_resource_probe_without_psutil_keeps_cpu_time(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "psutil", None)
    snapshot = ResourceProbe().snapshot()

    assert snapshot.worker_rss_bytes is None
    assert snapshot.process_cpu_ns >= 0
    assert elapsed_cpu_ms(ResourceSnapshot(1_000_000, None), ResourceSnapshot(3_500_000, None)) == 2.5
