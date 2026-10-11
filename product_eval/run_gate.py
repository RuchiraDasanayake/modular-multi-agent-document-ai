"""Run disjoint, no-model product shards and verify the complete quality gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError, load_jsonl
from product_eval.execution import verify_runs
from product_eval.scorer import score_records

_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(*args: str, repository_root: Path) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=repository_root, capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _run_shard(shard: Path, run_id: str, data_dir: Path, report_dir: Path, repository_root: Path) -> int:
    environment = os.environ.copy()
    environment["IDPO_DATA_DIR"] = str(data_dir)
    # This gate never configures a model, so provider secrets have no purpose in a child.
    for name in ("ICORE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        environment.pop(name, None)
    command = [
        sys.executable, "-m", "idpo.cli", "process-auto", "--input", str(shard), "--run-id", run_id,
    ]
    with (report_dir / f"{run_id}.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(
            command, cwd=repository_root, env=environment, stdout=log, stderr=subprocess.STDOUT,
            check=False, text=True,
        )
    return result.returncode


def run_gate(
    shard_dirs: list[Path],
    *,
    gold_path: Path,
    data_dir: Path,
    report_dir: Path,
    gate_id: str,
    min_unique: int = 2000,
    max_workers: int = 4,
    repository_root: Path = _REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Return reports only after actual subprocess runs, source checks and scoring pass.

    Run IDs and the report directory are new for each gate. A partial shard is never
    silently reused; it needs an explicit new gate ID or a future resumable worker.
    """
    if not _SAFE_ID.fullmatch(gate_id) or not shard_dirs:
        raise ValueError("gate_id must be safe and at least one shard directory is required")
    if type(min_unique) is not int or min_unique < 1 or type(max_workers) is not int or max_workers < 1:
        raise ValueError("min_unique and max_workers must be positive integers")
    shards = [path.resolve() for path in shard_dirs]
    if len(set(shards)) != len(shards) or len({path.name for path in shards}) != len(shards):
        raise ValueError("shard directories and names must be distinct")
    if any(not path.is_dir() or not any(child.is_file() for child in path.iterdir()) for path in shards):
        raise ValueError("every shard must exist and contain files")
    run_ids = [f"{gate_id}_{shard.name}" for shard in shards]
    if any(not _SAFE_ID.fullmatch(run_id) for run_id in run_ids):
        raise ValueError("gate and shard names must form safe run IDs of at most 64 characters")
    data_dir = data_dir.resolve()
    report_dir = report_dir.resolve()
    gold_path = gold_path.resolve()
    repository_root = repository_root.resolve()
    if not gold_path.is_file():
        raise ValueError("gold JSONL does not exist")
    run_dirs = [data_dir / "product_runs" / run_id for run_id in run_ids]
    if any(path.exists() for path in run_dirs) or report_dir.exists():
        raise ValueError("gate report directory and run IDs must be new; no partial run is reused")

    report_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    provenance = {
        "gate_id": gate_id,
        "git_commit": _git_value("rev-parse", "HEAD", repository_root=repository_root),
        "working_tree_dirty": bool(_git_value("status", "--porcelain", repository_root=repository_root)),
        "python": sys.version,
        "platform": platform.platform(),
        "gold_path": str(gold_path),
        "gold_sha256": _sha256_file(gold_path),
        "shard_dirs": [str(shard) for shard in shards],
        "run_ids": run_ids,
        "model_configured": False,
        "min_unique": min_unique,
        "max_workers": max_workers,
    }
    _write_json(report_dir / "provenance.json", provenance)

    exit_codes: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(shards))) as executor:
        futures = {
            executor.submit(_run_shard, shard, run_id, data_dir, report_dir, repository_root): run_id
            for shard, run_id in zip(shards, run_ids)
        }
        for future in as_completed(futures):
            run_id = futures[future]
            exit_codes[run_id] = future.result()
            print(f"{run_id}: exit {exit_codes[run_id]}", flush=True)
    _write_json(report_dir / "exit-codes.json", exit_codes)
    if any(code != 0 for code in exit_codes.values()):
        raise RuntimeError("a shard failed; inspect the per-shard logs and use a new gate ID")

    execution = verify_runs(run_dirs, min_unique=min_unique)
    _write_json(report_dir / "execution-report.json", execution)
    candidate_path = report_dir / "candidates.jsonl"
    with candidate_path.open("w", encoding="utf-8", newline="\n") as output:
        for run_dir in run_dirs:
            with (run_dir / "candidates.jsonl").open("r", encoding="utf-8") as source:
                for line in source:
                    if line.strip():
                        output.write(line.rstrip("\r\n") + "\n")
    gold = load_jsonl(gold_path, kind="gold")
    candidates = load_jsonl(candidate_path, kind="candidate")
    if set(gold) != set(candidates):
        raise ContractError(
            f"gold/candidate IDs differ: missing={len(set(gold) - set(candidates))}, "
            f"unexpected={len(set(candidates) - set(gold))}"
        )
    quality = score_records(gold, candidates)
    _write_json(report_dir / "quality-report.json", quality)
    provenance["candidate_sha256"] = _sha256_file(candidate_path)
    provenance["execution_report_sha256"] = _sha256_file(report_dir / "execution-report.json")
    provenance["quality_report_sha256"] = _sha256_file(report_dir / "quality-report.json")
    _write_json(report_dir / "provenance.json", provenance)
    return {"execution": execution, "quality": quality, "provenance": provenance}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shard_dirs", type=Path, nargs="+")
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--gate-id", required=True)
    parser.add_argument("--min-unique", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    try:
        result = run_gate(
            args.shard_dirs, gold_path=args.gold, data_dir=args.data_dir,
            report_dir=args.report_dir, gate_id=args.gate_id,
            min_unique=args.min_unique, max_workers=args.workers,
        )
    except (ContractError, OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "report_dir": str(args.report_dir.resolve()),
        "documents": result["execution"]["documents"],
        "distinct_sources": result["execution"]["distinct_sources"],
    }, indent=2))


if __name__ == "__main__":
    main()
