"""Run static vs adaptive IDPO benchmarks and emit a canonical evidence bundle."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from idpo.core.storage import benchmark_reports_dir
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


def _precision_recall_f1(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _load_config_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_condition_config(base_config: Path, condition: str, temp_dir: Path) -> Path:
    payload = _load_config_payload(base_config)
    ahmn = payload.setdefault("ahmn", {})
    ahmn["policy_mode"] = condition
    if condition == "static":
        ahmn["enabled"] = False
    else:
        ahmn["enabled"] = True
        if str(ahmn.get("mode", "")).strip().lower() in {"", "mock"}:
            ahmn["mode"] = "auto"
    out_path = temp_dir / f"{condition}_config.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def _condition_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    doc_count = len(results)
    total_latency = sum(float(item["doc"].get("latency_ms", 0.0) or 0.0) for item in results)
    total_reward = sum(float(item["doc"].get("reward", 0.0) or 0.0) for item in results)
    validation_passes = sum(1 for item in results if int(item["doc"].get("validation_issue_count", 0) or 0) == 0)
    recovery_hits = sum(1 for item in results if int(item["doc"].get("recovered_fields_count", 0) or 0) > 0)
    escalation_hits = sum(
        1
        for item in results
        if str(item["doc"].get("escalation_status", "not_needed")).strip() != "not_needed"
    )
    policy_distribution = Counter(str(item["doc"].get("policy_id", "")).strip() for item in results)
    operator_counts = Counter()
    reward_types = Counter()
    advice_sources = Counter()
    exact_tp = exact_fp = exact_fn = 0
    for item in results:
        operator_counts.update(str(op).strip() for op in item["doc"].get("operator_stack", []) or [])
        reward_types.update([str(item["doc"].get("reward_type", "proxy")).strip() or "proxy"])
        advice_sources.update([str(item["doc"].get("advice_source", "unknown")).strip() or "unknown"])
        exact = item.get("exact_metrics", {})
        exact_tp += int(exact.get("tp", 0) or 0)
        exact_fp += int(exact.get("fp", 0) or 0)
        exact_fn += int(exact.get("fn", 0) or 0)
    exact_metrics = {
        "tp": exact_tp,
        "fp": exact_fp,
        "fn": exact_fn,
        **_precision_recall_f1(exact_tp, exact_fp, exact_fn),
    }
    summary = {
        "doc_count": doc_count,
        "run_ids": [str(item.get("run_id", "")) for item in results if item.get("run_id")],
        "run_dirs": [str(item.get("run_dir", "")) for item in results if item.get("run_dir")],
        "avg_latency_ms": round(total_latency / doc_count, 2) if doc_count else 0.0,
        "avg_reward": round(total_reward / doc_count, 4) if doc_count else 0.0,
        "validation_pass_rate": round(validation_passes / doc_count, 4) if doc_count else 0.0,
        "recovery_rate": round(recovery_hits / doc_count, 4) if doc_count else 0.0,
        "escalation_rate": round(escalation_hits / doc_count, 4) if doc_count else 0.0,
        "policy_distribution": dict(sorted(policy_distribution.items())),
        "operator_counts": dict(sorted(operator_counts.items())),
        "reward_type_counts": dict(sorted(reward_types.items())),
        "advice_source_counts": dict(sorted(advice_sources.items())),
        "exact_field_metrics": exact_metrics,
    }
    return summary


def run_benchmark(config_path: str = "configs/config.json", pack_path: str = "idpo/benchmark/benchmark_pack.json") -> dict[str, Any]:
    repo_root = REPO_ROOT
    pack_file = (repo_root / pack_path).resolve()
    base_config_path = (repo_root / config_path).resolve()
    pack = json.loads(pack_file.read_text(encoding="utf-8"))
    cases = pack.get("cases", [])
    if not cases:
        raise SystemExit("Benchmark pack has no cases")

    benchmark_run_id = f"benchmark_{int(time.time())}"
    out_dir = benchmark_reports_dir() / benchmark_run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    conditions: dict[str, list[dict[str, Any]]] = {"static": [], "adaptive": []}
    started = time.time()

    with tempfile.TemporaryDirectory(prefix="idpo_benchmark_cfg_") as cfg_dir:
        cfg_root = Path(cfg_dir)
        condition_configs = {
            "static": _write_condition_config(base_config_path, "static", cfg_root),
            "adaptive": _write_condition_config(base_config_path, "adaptive", cfg_root),
        }
        condition_settings = {
            name: _load_config_payload(path).get("ahmn", {}) for name, path in condition_configs.items()
        }
        if not bool(condition_settings["adaptive"].get("enabled")):
            raise SystemExit("Adaptive benchmark configuration must enable AHMN")
        for case in cases:
            case_id = str(case.get("case_id", "")).strip() or f"case_{sum(len(v) for v in conditions.values()) + 1}"
            source_path = (repo_root / str(case.get("path", ""))).resolve()
            fields = [
                {"name": key, "description": str(desc)}
                for key, desc in (case.get("fields", {}) or {}).items()
            ]
            expected = {str(k): str(v) for k, v in (case.get("expected", {}) or {}).items()}
            if not source_path.exists():
                for condition in conditions:
                    conditions[condition].append(
                        {"case_id": case_id, "status": "failed", "error": f"missing_file:{source_path}"}
                    )
                continue

            for condition in ("static", "adaptive"):
                with tempfile.TemporaryDirectory(prefix=f"idpo_bench_{condition}_{case_id}_") as tmp_dir:
                    temp_path = Path(tmp_dir) / source_path.name
                    shutil.copy2(source_path, temp_path)
                    run = process_inbox(
                        root=repo_root,
                        config_path=str(condition_configs[condition]),
                        extraction_fields=fields,
                        run_id=f"{condition}_{case_id}_{int(time.time() * 1000)}",
                        file_paths=[str(temp_path)],
                    )

                docs = run.get("doc_records", [])
                if not docs:
                    conditions[condition].append({"case_id": case_id, "status": "failed", "error": "no_doc_records"})
                    continue
                doc = docs[0]
                structured = doc.get("structured_fields", {})
                if not isinstance(structured, dict):
                    structured = {}
                tp, fp, fn = _case_metrics(expected, structured)
                conditions[condition].append(
                    {
                        "case_id": case_id,
                        "status": "ok",
                        "doc": doc,
                        "run_id": run.get("run_id", ""),
                        "run_dir": run.get("run_dir", ""),
                        "expected": expected,
                        "exact_metrics": {
                            "tp": tp,
                            "fp": fp,
                            "fn": fn,
                            **_precision_recall_f1(tp, fp, fn),
                        },
                    }
                )

    condition_summaries = {key: _condition_summary(value) for key, value in conditions.items()}
    documents = []
    static_by_case = {item["case_id"]: item for item in conditions["static"] if item.get("status") == "ok"}
    adaptive_by_case = {item["case_id"]: item for item in conditions["adaptive"] if item.get("status") == "ok"}
    for case in cases:
        case_id = str(case.get("case_id", "")).strip()
        static_item = static_by_case.get(case_id, {})
        adaptive_item = adaptive_by_case.get(case_id, {})
        static_doc = static_item.get("doc", {})
        adaptive_doc = adaptive_item.get("doc", {})
        documents.append(
            {
                "case_id": case_id,
                "static": {
                    "run_id": static_item.get("run_id", ""),
                    "run_dir": static_item.get("run_dir", ""),
                    "doc": static_doc,
                    "exact_metrics": static_item.get("exact_metrics", {}),
                },
                "adaptive": {
                    "run_id": adaptive_item.get("run_id", ""),
                    "run_dir": adaptive_item.get("run_dir", ""),
                    "doc": adaptive_doc,
                    "exact_metrics": adaptive_item.get("exact_metrics", {}),
                },
                "deltas": {
                    "latency_ms": round(float(adaptive_doc.get("latency_ms", 0.0) or 0.0) - float(static_doc.get("latency_ms", 0.0) or 0.0), 2),
                    "reward": round(float(adaptive_doc.get("reward", 0.0) or 0.0) - float(static_doc.get("reward", 0.0) or 0.0), 4),
                    "policy_changed": str(adaptive_doc.get("policy_id", "")) != str(static_doc.get("policy_id", "")),
                    "recovery_delta": int(adaptive_doc.get("recovered_fields_count", 0) or 0) - int(static_doc.get("recovered_fields_count", 0) or 0),
                    "escalation_changed": str(adaptive_doc.get("escalation_status", "")) != str(static_doc.get("escalation_status", "")),
                    "exact_f1_delta": round(
                        float((adaptive_item.get("exact_metrics") or {}).get("f1", 0.0) or 0.0)
                        - float((static_item.get("exact_metrics") or {}).get("f1", 0.0) or 0.0),
                        4,
                    ),
                },
            }
        )

    evidence = {
        "experiment": {
            "benchmark_run_id": benchmark_run_id,
            "pack_name": pack.get("name", "benchmark_pack"),
            "pack_path": str(pack_file),
            "config_path": str(base_config_path),
            "condition_configs": {
                name: {
                    "path": str(path),
                    "ahmn_enabled": bool(condition_settings[name].get("enabled")),
                    "ahmn_mode": str(condition_settings[name].get("mode", "")).strip() or None,
                    "policy_mode": str(condition_settings[name].get("policy_mode", name)).strip() or name,
                }
                for name, path in condition_configs.items()
            },
            "generated_at": time.time(),
            "elapsed_ms": round((time.time() - started) * 1000, 2),
            "doc_count": len(cases),
            "generation_version": 1,
        },
        "conditions": condition_summaries,
        "comparison": {
            "doc_count": len(cases),
            "static": condition_summaries["static"],
            "adaptive": condition_summaries["adaptive"],
            "table": {
                "doc_count": len(cases),
                "avg_latency_ms": {
                    "static": condition_summaries["static"]["avg_latency_ms"],
                    "adaptive": condition_summaries["adaptive"]["avg_latency_ms"],
                },
                "avg_reward": {
                    "static": condition_summaries["static"]["avg_reward"],
                    "adaptive": condition_summaries["adaptive"]["avg_reward"],
                },
                "exact_precision": {
                    "static": condition_summaries["static"]["exact_field_metrics"]["precision"],
                    "adaptive": condition_summaries["adaptive"]["exact_field_metrics"]["precision"],
                },
                "exact_recall": {
                    "static": condition_summaries["static"]["exact_field_metrics"]["recall"],
                    "adaptive": condition_summaries["adaptive"]["exact_field_metrics"]["recall"],
                },
                "exact_f1": {
                    "static": condition_summaries["static"]["exact_field_metrics"]["f1"],
                    "adaptive": condition_summaries["adaptive"]["exact_field_metrics"]["f1"],
                },
                "validation_pass_rate": {
                    "static": condition_summaries["static"]["validation_pass_rate"],
                    "adaptive": condition_summaries["adaptive"]["validation_pass_rate"],
                },
                "recovery_rate": {
                    "static": condition_summaries["static"]["recovery_rate"],
                    "adaptive": condition_summaries["adaptive"]["recovery_rate"],
                },
                "escalation_rate": {
                    "static": condition_summaries["static"]["escalation_rate"],
                    "adaptive": condition_summaries["adaptive"]["escalation_rate"],
                },
                "policy_distribution": {
                    "static": condition_summaries["static"]["policy_distribution"],
                    "adaptive": condition_summaries["adaptive"]["policy_distribution"],
                },
                "advice_source_counts": {
                    "static": condition_summaries["static"]["advice_source_counts"],
                    "adaptive": condition_summaries["adaptive"]["advice_source_counts"],
                },
                "operator_counts": {
                    "static": condition_summaries["static"]["operator_counts"],
                    "adaptive": condition_summaries["adaptive"]["operator_counts"],
                },
            },
        },
        "documents": documents,
    }

    (out_dir / "paper_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (out_dir / "paper_table.md").write_text(_table_markdown(evidence), encoding="utf-8")
    (out_dir / "paper_table.csv").write_text(_table_csv(evidence), encoding="utf-8")
    return evidence


def _table_markdown(evidence: dict[str, Any]) -> str:
    table = evidence["comparison"]["table"]
    rows = [
        "| Metric | Static | Adaptive |",
        "| --- | ---: | ---: |",
        f"| Doc Count | {table['doc_count']} | {table['doc_count']} |",
        f"| Avg Latency (ms) | {table['avg_latency_ms']['static']} | {table['avg_latency_ms']['adaptive']} |",
        f"| Avg Reward | {table['avg_reward']['static']} | {table['avg_reward']['adaptive']} |",
        f"| Exact Precision | {table['exact_precision']['static']} | {table['exact_precision']['adaptive']} |",
        f"| Exact Recall | {table['exact_recall']['static']} | {table['exact_recall']['adaptive']} |",
        f"| Exact F1 | {table['exact_f1']['static']} | {table['exact_f1']['adaptive']} |",
        f"| Validation Pass Rate | {table['validation_pass_rate']['static']} | {table['validation_pass_rate']['adaptive']} |",
        f"| Recovery Rate | {table['recovery_rate']['static']} | {table['recovery_rate']['adaptive']} |",
        f"| Escalation Rate | {table['escalation_rate']['static']} | {table['escalation_rate']['adaptive']} |",
        f"| Policy Distribution | `{json.dumps(table['policy_distribution']['static'], sort_keys=True)}` | `{json.dumps(table['policy_distribution']['adaptive'], sort_keys=True)}` |",
        f"| Advice Sources | `{json.dumps(table['advice_source_counts']['static'], sort_keys=True)}` | `{json.dumps(table['advice_source_counts']['adaptive'], sort_keys=True)}` |",
        f"| Operator Counts | `{json.dumps(table['operator_counts']['static'], sort_keys=True)}` | `{json.dumps(table['operator_counts']['adaptive'], sort_keys=True)}` |",
    ]
    return "\n".join(rows) + "\n"


def _table_csv(evidence: dict[str, Any]) -> str:
    table = evidence["comparison"]["table"]
    rows = [
        "metric,static,adaptive",
        f"doc_count,{table['doc_count']},{table['doc_count']}",
        f"avg_latency_ms,{table['avg_latency_ms']['static']},{table['avg_latency_ms']['adaptive']}",
        f"avg_reward,{table['avg_reward']['static']},{table['avg_reward']['adaptive']}",
        f"exact_precision,{table['exact_precision']['static']},{table['exact_precision']['adaptive']}",
        f"exact_recall,{table['exact_recall']['static']},{table['exact_recall']['adaptive']}",
        f"exact_f1,{table['exact_f1']['static']},{table['exact_f1']['adaptive']}",
        f"validation_pass_rate,{table['validation_pass_rate']['static']},{table['validation_pass_rate']['adaptive']}",
        f"recovery_rate,{table['recovery_rate']['static']},{table['recovery_rate']['adaptive']}",
        f"escalation_rate,{table['escalation_rate']['static']},{table['escalation_rate']['adaptive']}",
        f"policy_distribution,\"{json.dumps(table['policy_distribution']['static'], sort_keys=True)}\",\"{json.dumps(table['policy_distribution']['adaptive'], sort_keys=True)}\"",
        f"advice_source_counts,\"{json.dumps(table['advice_source_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['advice_source_counts']['adaptive'], sort_keys=True)}\"",
        f"operator_counts,\"{json.dumps(table['operator_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['operator_counts']['adaptive'], sort_keys=True)}\"",
    ]
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.json")
    parser.add_argument("--pack", default="idpo/benchmark/benchmark_pack.json")
    args = parser.parse_args()
    evidence = run_benchmark(config_path=args.config, pack_path=args.pack)
    print(json.dumps(evidence["comparison"]["table"], indent=2))
    print(f"report_path={benchmark_reports_dir() / evidence['experiment']['benchmark_run_id'] / 'paper_evidence.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
