from __future__ import annotations

from product_eval.paddleocr_vl_pilot import (
    MAX_PROCESS_TREE_RSS_BYTES,
    MIN_AVAILABLE_MEMORY_BYTES,
    MIN_C_FREE_BYTES,
    MIN_E_FREE_BYTES,
    MIN_GPU_FREE_MIB,
    _resource_error,
)


def test_resource_floor_rejects_unknown_gpu_and_low_disk() -> None:
    healthy = {
        "process_tree_rss_bytes": MAX_PROCESS_TREE_RSS_BYTES,
        "host_available_bytes": MIN_AVAILABLE_MEMORY_BYTES,
        "gpu_free_mib": MIN_GPU_FREE_MIB,
        "c_free_bytes": MIN_C_FREE_BYTES,
        "e_free_bytes": MIN_E_FREE_BYTES,
    }
    assert _resource_error(healthy) is None
    assert _resource_error({**healthy, "gpu_free_mib": None}) == "gpu_vram_floor"
    assert _resource_error({**healthy, "e_free_bytes": MIN_E_FREE_BYTES - 1}) == "disk_floor"
    assert _resource_error({**healthy, "process_tree_rss_bytes": MAX_PROCESS_TREE_RSS_BYTES + 1}) == (
        "process_tree_rss_limit"
    )
