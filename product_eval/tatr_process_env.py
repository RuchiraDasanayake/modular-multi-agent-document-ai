"""Minimal Windows child environment for the isolated TATR research trial."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def isolated_worker_env(python: Path, repo_root: Path) -> dict[str, str]:
    """Pass runtime paths and offline settings without host API credentials."""
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if not system_root:
        raise ValueError("Windows system root is unavailable")
    root = Path(system_root).resolve(strict=True)
    environment = {
        "SystemRoot": str(root),
        "WINDIR": str(root),
        "PATH": os.pathsep.join((str(python.resolve(strict=True).parent),
                                   str(root / "System32"), str(root))),
        "PYTHONPATH": str(repo_root.resolve(strict=True)),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "HF_HUB_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "OMP_NUM_THREADS": "4",
        "OPENBLAS_NUM_THREADS": "4",
        "MKL_NUM_THREADS": "4",
    }
    for key in ("TEMP", "TMP", "USERPROFILE", "USERNAME", "APPDATA",
                "LOCALAPPDATA", "PROGRAMDATA"):
        if value := os.environ.get(key):
            environment[key] = value
    return environment


def environment_sha256(environment: dict[str, str]) -> str:
    encoded = json.dumps(environment, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
