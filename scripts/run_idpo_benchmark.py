"""Run a fixed IDPO extraction benchmark pack and write regression metrics."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from idpo.pipeline.inbox import process_inbox


def _norm(value: object) -> str:
    text = str(value or "").strip().lower()
    return " ".join(text.split())


def _case_metrics(expected: dict[str, str], extracted: dict[str, object]) -> tuple[int, int, int]:
    tp = 0
    fp = 0
    fn = 0
    for key, expected_value in expected.items():
        got = _norm(extracted.get(key, ""))
        exp = _norm(expected_value)
        if got and got == exp:
            tp += 1
        elif got and got != exp:
            fp += 1
            fn += 1
        else:
            fn += 1
    return tp, fp, fn


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.json")
    parser.add_argument("--pack", default="idpo/benchmark/benchmark_pack.json")
    args = parser.parse_args()

    repo_root = REPO_ROOT
    pack_path = (repo_root / args.pack).resolve()
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    cases = pack.get("cases", [])
    if not cases:
        raise SystemExit("Benchmark pack has no cases")

    started = time.time()
    total_tp = total_fp = total_fn = 0
    total_duration_ms = 0.0
    total_cost = 0.0
    results: list[dict[str, object]] = []

    for case in cases:
        case_id = str(case.get("case_id", "")).strip() or f"case_{len(results)+1}"
        source_path = (repo_root / str(case.get("path", ""))).resolve()
        fields = [
            {"name": key, "description": str(desc)}
            for key, desc in (case.get("fields", {}) or {}).items()
        ]
        expected = {str(k): str(v) for k, v in (case.get("expected", {}) or {}).items()}
        if not source_path.exists():
            results.append({"case_id": case_id, "status": "failed", "error": f"missing_file:{source_path}"})
            continue

        with tempfile.TemporaryDirectory(prefix=f"idpo_bench_{case_id}_") as tmp_dir:
            temp_path = Path(tmp_dir) / source_path.name
            shutil.copy2(source_path, temp_path)
            run_id = f"bench_{case_id}_{int(time.time()*1000)}"
            run = process_inbox(
                root=repo_root,
                config_path=args.config,
                extraction_fields=fields,
                run_id=run_id,
                file_paths=[str(temp_path)],
            )

        docs = run.get("doc_records", [])
        if not docs:
            results.append({"case_id": case_id, "status": "failed", "error": "no_doc_records"})
            continue
        doc = docs[0]
        structured = doc.get("structured_fields", {})
        if not isinstance(structured, dict):
            structured = {}
        tp, fp, fn = _case_metrics(expected, structured)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        llm_diag = doc.get("llm_diagnostics", {})
        cloud_usage = llm_diag.get("cloud_usage", {}) if isinstance(llm_diag, dict) else {}
        case_cost = float((cloud_usage or {}).get("estimated_cost_usd", 0.0) or 0.0)
        case_duration = float(run.get("metrics", {}).get("duration_ms", 0.0) or 0.0)

        total_tp += tp
        total_fp += fp
        total_fn += fn
        total_duration_ms += case_duration
        total_cost += case_cost

        results.append(
            {
                "case_id": case_id,
                "status": "ok",
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "duration_ms": round(case_duration, 2),
                "estimated_cost_usd": round(case_cost, 8),
            }
        )

    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    overall_f1 = (
        2 * overall_precision * overall_recall / (overall_precision + overall_recall)
        if (overall_precision + overall_recall)
        else 0.0
    )
    report = {
        "pack": pack.get("name", "benchmark_pack"),
        "generated_at": time.time(),
        "elapsed_ms": round((time.time() - started) * 1000, 2),
        "summary": {
            "cases": len(cases),
            "precision": round(overall_precision, 4),
            "recall": round(overall_recall, 4),
            "f1": round(overall_f1, 4),
            "total_duration_ms": round(total_duration_ms, 2),
            "total_estimated_cost_usd": round(total_cost, 8),
        },
        "results": results,
    }
    out_dir = repo_root / "runs" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"idpo_benchmark_{int(time.time())}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"report_path={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
