"""Shared runtime storage paths for IDPO-managed writable data."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

DATA_ROOT_ENV = "IDPO_DATA_DIR"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_data_root() -> Path:
    return repo_root().parent / "idpo-data"


def data_root() -> Path:
    raw = os.getenv(DATA_ROOT_ENV, "").strip()
    if not raw:
        return default_data_root().resolve()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def runs_root() -> Path:
    return data_root() / "runs"


def benchmark_reports_dir() -> Path:
    return runs_root() / "benchmarks"


def inputs_root() -> Path:
    return data_root() / "inputs"


def inbox_dir() -> Path:
    return inputs_root() / "inbox"


def processed_dir() -> Path:
    return inputs_root() / "processed"


def failed_dir() -> Path:
    return inputs_root() / "failed"


def ensure_runtime_dirs() -> dict[str, Path]:
    paths = {
        "data_root": data_root(),
        "runs_root": runs_root(),
        "benchmark_reports_dir": benchmark_reports_dir(),
        "inputs_root": inputs_root(),
        "inbox_dir": inbox_dir(),
        "processed_dir": processed_dir(),
        "failed_dir": failed_dir(),
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def resolve_default_run_dir(run_id: str) -> Path:
    return runs_root() / run_id


def migrate_legacy_runtime_data(
    *,
    source_repo_root: str | Path | None = None,
    target_data_root: str | Path | None = None,
) -> dict[str, object]:
    repo = Path(source_repo_root) if source_repo_root else repo_root()
    target_root = Path(target_data_root) if target_data_root else data_root()
    target_root = target_root.resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    source_runs = repo / "runs"
    target_runs = target_root / "runs"
    target_runs.mkdir(parents=True, exist_ok=True)

    source_inputs = repo / "inputs"
    target_inputs = target_root / "inputs"
    target_inputs.mkdir(parents=True, exist_ok=True)

    moved_runs: list[str] = []
    moved_inputs: list[str] = []
    skipped: list[str] = []

    if source_runs.exists():
        for entry in sorted(source_runs.iterdir()):
            dest = target_runs / entry.name
            if dest.exists():
                raise RuntimeError(f"Run ID collision while migrating '{entry.name}' to {dest}")
            shutil.move(str(entry), str(dest))
            moved_runs.append(entry.name)

    for name in ("processed", "failed"):
        source_dir = source_inputs / name
        dest_dir = target_inputs / name
        if not source_dir.exists():
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        for entry in sorted(source_dir.iterdir()):
            dest = dest_dir / entry.name
            if dest.exists():
                raise RuntimeError(f"Input collision while migrating '{entry.name}' to {dest}")
            shutil.move(str(entry), str(dest))
            moved_inputs.append(f"{name}/{entry.name}")

    legacy_inbox = source_inputs / "inbox"
    if legacy_inbox.exists():
        skipped.append(str(legacy_inbox))

    return {
        "data_root": str(target_root),
        "moved_runs": moved_runs,
        "moved_inputs": moved_inputs,
        "skipped": skipped,
    }
