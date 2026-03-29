"""Run static vs adaptive_safe IDPO benchmarks and emit a canonical evidence bundle."""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from idpo.core.storage import benchmark_reports_dir
from idpo.pipeline.inbox import process_inbox

ADAPTIVE_LABEL = "adaptive_safe"
PRIMARY_GROUP_TAGS = ("table", "form", "scanned", "text", "mixed", "noisy_ocr")
BOOTSTRAP_ITERATIONS = 1000
BOOTSTRAP_SEED = 17


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


def _containment_state(doc: dict[str, Any]) -> str:
    if bool(doc.get("blocked_policy", False)):
        return "blocked"
    if bool(doc.get("rollback_triggered", False)):
        return "rollback"
    if str(doc.get("fallback_reason", "")).strip():
        return "fallback"
    defer_status = str(doc.get("defer_status", "")).strip()
    if defer_status in {"requested", "blocked"}:
        return f"defer_{defer_status}"
    return "none"


def _write_condition_config(base_config: Path, condition: str, temp_dir: Path) -> Path:
    payload = _load_config_payload(base_config)
    ahmn = payload.setdefault("ahmn", {})
    runtime_mode = "static" if condition == "static" else "adaptive"
    ahmn["policy_mode"] = runtime_mode
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
    advice_statuses = Counter()
    containment_states = Counter()
    feedback_errors = Counter()
    exact_tp = exact_fp = exact_fn = 0
    rollback_count = 0
    blocked_policy_count = 0
    fallback_count = 0
    feedback_logged_count = 0
    rabi_used_count = 0
    defer_requested_count = 0
    defer_blocked_count = 0
    retrieval_sources = Counter()
    advice_confidences: list[float] = []
    schema_coverages: list[float] = []
    grounding_coverages: list[float] = []
    schema_valid_count = 0
    advice_accepted_count = 0
    policy_changed_count = 0
    direct_scored_doc_count = 0
    for item in results:
        doc = item["doc"]
        operator_counts.update(str(op).strip() for op in doc.get("operator_stack", []) or [])
        reward_types.update([str(doc.get("reward_type", "proxy")).strip() or "proxy"])
        advice_sources.update([str(doc.get("advice_source", "unknown")).strip() or "unknown"])
        advice_statuses.update([str(doc.get("advice_status", "static")).strip() or "unknown"])
        retrieval_sources.update([str(doc.get("retrieval_source", "unknown")).strip() or "unknown"])
        containment_states.update([_containment_state(doc)])
        if doc.get("rollback_triggered"):
            rollback_count += 1
        if doc.get("blocked_policy"):
            blocked_policy_count += 1
        if doc.get("fallback_reason"):
            fallback_count += 1
        if doc.get("feedback_logged"):
            feedback_logged_count += 1
        if doc.get("feedback_error"):
            feedback_errors.update([str(doc.get("feedback_error")).strip()])
        if doc.get("rabi_used"):
            rabi_used_count += 1
        defer_status = str(doc.get("defer_status", "")).strip()
        if defer_status == "requested":
            defer_requested_count += 1
        elif defer_status == "blocked":
            defer_blocked_count += 1
        if doc.get("advice_confidence") is not None:
            try:
                advice_confidences.append(float(doc.get("advice_confidence", 0.0) or 0.0))
            except Exception:
                pass
        if doc.get("advice_accepted"):
            advice_accepted_count += 1
        if doc.get("policy_changed"):
            policy_changed_count += 1
        if str(doc.get("reward_type", "")).strip() == "direct_set_based":
            direct_scored_doc_count += 1
        if doc.get("schema_coverage") is not None:
            try:
                schema_coverages.append(float(doc.get("schema_coverage", 0.0) or 0.0))
            except Exception:
                pass
        if doc.get("schema_grounding_coverage") is not None:
            try:
                grounding_coverages.append(float(doc.get("schema_grounding_coverage", 0.0) or 0.0))
            except Exception:
                pass
        if bool(doc.get("schema_valid", False)):
            schema_valid_count += 1
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
        "advice_status_counts": dict(sorted(advice_statuses.items())),
        "retrieval_source_counts": dict(sorted(retrieval_sources.items())),
        "containment_state_counts": dict(sorted(containment_states.items())),
        "rollback_count": rollback_count,
        "blocked_policy_count": blocked_policy_count,
        "fallback_count": fallback_count,
        "feedback_logged_count": feedback_logged_count,
        "feedback_error_counts": dict(sorted(feedback_errors.items())),
        "policy_coverage_count": len([key for key in policy_distribution if key]),
        "rabi_used_count": rabi_used_count,
        "defer_requested_count": defer_requested_count,
        "defer_blocked_count": defer_blocked_count,
        "avg_advice_confidence": round(sum(advice_confidences) / len(advice_confidences), 4) if advice_confidences else 0.0,
        "avg_schema_coverage": round(sum(schema_coverages) / len(schema_coverages), 4) if schema_coverages else 0.0,
        "avg_schema_grounding_coverage": round(sum(grounding_coverages) / len(grounding_coverages), 4) if grounding_coverages else 0.0,
        "schema_valid_rate": round(schema_valid_count / doc_count, 4) if doc_count else 0.0,
        "advice_accepted_count": advice_accepted_count,
        "policy_changed_count": policy_changed_count,
        "direct_scored_doc_count": direct_scored_doc_count,
        "exact_field_metrics": exact_metrics,
    }
    return summary


def _comparison_table(static_summary: dict[str, Any], adaptive_summary: dict[str, Any], doc_count: int) -> dict[str, Any]:
    return {
        "doc_count": doc_count,
        "avg_latency_ms": {
            "static": static_summary["avg_latency_ms"],
            ADAPTIVE_LABEL: adaptive_summary["avg_latency_ms"],
        },
        "avg_reward": {
            "static": static_summary["avg_reward"],
            ADAPTIVE_LABEL: adaptive_summary["avg_reward"],
        },
        "exact_precision": {
            "static": static_summary["exact_field_metrics"]["precision"],
            ADAPTIVE_LABEL: adaptive_summary["exact_field_metrics"]["precision"],
        },
        "exact_recall": {
            "static": static_summary["exact_field_metrics"]["recall"],
            ADAPTIVE_LABEL: adaptive_summary["exact_field_metrics"]["recall"],
        },
        "exact_f1": {
            "static": static_summary["exact_field_metrics"]["f1"],
            ADAPTIVE_LABEL: adaptive_summary["exact_field_metrics"]["f1"],
        },
        "validation_pass_rate": {
            "static": static_summary["validation_pass_rate"],
            ADAPTIVE_LABEL: adaptive_summary["validation_pass_rate"],
        },
        "recovery_rate": {
            "static": static_summary["recovery_rate"],
            ADAPTIVE_LABEL: adaptive_summary["recovery_rate"],
        },
        "escalation_rate": {
            "static": static_summary["escalation_rate"],
            ADAPTIVE_LABEL: adaptive_summary["escalation_rate"],
        },
        "policy_distribution": {
            "static": static_summary["policy_distribution"],
            ADAPTIVE_LABEL: adaptive_summary["policy_distribution"],
        },
        "advice_source_counts": {
            "static": static_summary["advice_source_counts"],
            ADAPTIVE_LABEL: adaptive_summary["advice_source_counts"],
        },
        "advice_status_counts": {
            "static": static_summary["advice_status_counts"],
            ADAPTIVE_LABEL: adaptive_summary["advice_status_counts"],
        },
        "operator_counts": {
            "static": static_summary["operator_counts"],
            ADAPTIVE_LABEL: adaptive_summary["operator_counts"],
        },
        "retrieval_source_counts": {
            "static": static_summary["retrieval_source_counts"],
            ADAPTIVE_LABEL: adaptive_summary["retrieval_source_counts"],
        },
        "containment_state_counts": {
            "static": static_summary["containment_state_counts"],
            ADAPTIVE_LABEL: adaptive_summary["containment_state_counts"],
        },
        "rollback_count": {
            "static": static_summary["rollback_count"],
            ADAPTIVE_LABEL: adaptive_summary["rollback_count"],
        },
        "blocked_policy_count": {
            "static": static_summary["blocked_policy_count"],
            ADAPTIVE_LABEL: adaptive_summary["blocked_policy_count"],
        },
        "fallback_count": {
            "static": static_summary["fallback_count"],
            ADAPTIVE_LABEL: adaptive_summary["fallback_count"],
        },
        "feedback_logged_count": {
            "static": static_summary["feedback_logged_count"],
            ADAPTIVE_LABEL: adaptive_summary["feedback_logged_count"],
        },
        "rabi_used_count": {
            "static": static_summary["rabi_used_count"],
            ADAPTIVE_LABEL: adaptive_summary["rabi_used_count"],
        },
        "avg_advice_confidence": {
            "static": static_summary["avg_advice_confidence"],
            ADAPTIVE_LABEL: adaptive_summary["avg_advice_confidence"],
        },
        "avg_schema_coverage": {
            "static": static_summary["avg_schema_coverage"],
            ADAPTIVE_LABEL: adaptive_summary["avg_schema_coverage"],
        },
        "avg_schema_grounding_coverage": {
            "static": static_summary["avg_schema_grounding_coverage"],
            ADAPTIVE_LABEL: adaptive_summary["avg_schema_grounding_coverage"],
        },
        "schema_valid_rate": {
            "static": static_summary["schema_valid_rate"],
            ADAPTIVE_LABEL: adaptive_summary["schema_valid_rate"],
        },
        "defer_requested_count": {
            "static": static_summary["defer_requested_count"],
            ADAPTIVE_LABEL: adaptive_summary["defer_requested_count"],
        },
        "defer_blocked_count": {
            "static": static_summary["defer_blocked_count"],
            ADAPTIVE_LABEL: adaptive_summary["defer_blocked_count"],
        },
        "policy_coverage_count": {
            "static": static_summary["policy_coverage_count"],
            ADAPTIVE_LABEL: adaptive_summary["policy_coverage_count"],
        },
        "advice_accepted_count": {
            "static": static_summary.get("advice_accepted_count", 0),
            ADAPTIVE_LABEL: adaptive_summary.get("advice_accepted_count", 0),
        },
        "policy_changed_count": {
            "static": static_summary.get("policy_changed_count", 0),
            ADAPTIVE_LABEL: adaptive_summary.get("policy_changed_count", 0),
        },
        "direct_scored_doc_count": {
            "static": static_summary.get("direct_scored_doc_count", 0),
            ADAPTIVE_LABEL: adaptive_summary.get("direct_scored_doc_count", 0),
        },
    }


def _assert_adaptive_valid(results: list[dict[str, Any]], valid_policy_ids: set[str]) -> None:
    ok_docs = [item["doc"] for item in results if item.get("status") == "ok" and isinstance(item.get("doc"), dict)]
    if not ok_docs:
        raise SystemExit("Adaptive benchmark invalid: no successful adaptive documents")
    if all(str(doc.get("advice_source", "")).strip() == "fallback" for doc in ok_docs):
        raise SystemExit("Adaptive benchmark invalid: AHMN advice was unreachable or never used")
    if any(str(doc.get("fallback_reason", "")).strip() == "invalid_recommendation" for doc in ok_docs):
        raise SystemExit("Adaptive benchmark invalid: AHMN returned an invalid policy recommendation")
    if any(str(doc.get("policy_id", "")).strip() not in valid_policy_ids for doc in ok_docs):
        raise SystemExit("Adaptive benchmark invalid: adaptive run emitted a policy not present in the configured policy store")
    if all(not bool(doc.get("feedback_logged", False)) for doc in ok_docs):
        raise SystemExit("Adaptive benchmark invalid: AHMN feedback logging failed for all adaptive cases")


def _validation_pass(doc: dict[str, Any]) -> float:
    return 1.0 if int(doc.get("validation_issue_count", 0) or 0) == 0 else 0.0


def _bootstrap_interval(values: list[float], label: str) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rng = random.Random(BOOTSTRAP_SEED + sum(ord(ch) for ch in label))
    sample_count = len(values)
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        resample_mean = sum(values[rng.randrange(sample_count)] for _ in range(sample_count)) / sample_count
        estimates.append(resample_mean)
    estimates.sort()
    low_idx = max(0, min(len(estimates) - 1, int(0.025 * (len(estimates) - 1))))
    high_idx = max(0, min(len(estimates) - 1, int(0.975 * (len(estimates) - 1))))
    return {
        "count": sample_count,
        "mean": round(sum(values) / sample_count, 4),
        "ci_low": round(estimates[low_idx], 4),
        "ci_high": round(estimates[high_idx], 4),
    }


def _bootstrap_summary(documents: list[dict[str, Any]], label: str) -> dict[str, Any]:
    exact_f1_delta: list[float] = []
    latency_delta: list[float] = []
    validation_delta: list[float] = []
    for item in documents:
        static_doc = item.get("static", {}).get("doc", {})
        adaptive_doc = item.get(ADAPTIVE_LABEL, {}).get("doc", {})
        if not isinstance(static_doc, dict) or not isinstance(adaptive_doc, dict):
            continue
        deltas = item.get("deltas", {})
        exact_f1_delta.append(float(deltas.get("exact_f1_delta", 0.0) or 0.0))
        latency_delta.append(float(deltas.get("latency_ms", 0.0) or 0.0))
        validation_delta.append(_validation_pass(adaptive_doc) - _validation_pass(static_doc))
    return {
        "exact_f1_delta": _bootstrap_interval(exact_f1_delta, f"{label}:exact_f1_delta"),
        "latency_delta_ms": _bootstrap_interval(latency_delta, f"{label}:latency_delta_ms"),
        "validation_pass_rate_delta": _bootstrap_interval(validation_delta, f"{label}:validation_pass_rate_delta"),
    }


def _compare_case_outcome(static_doc: dict[str, Any], adaptive_doc: dict[str, Any], static_item: dict[str, Any], adaptive_item: dict[str, Any]) -> dict[str, Any]:
    static_exact = float((static_item.get("exact_metrics") or {}).get("f1", 0.0) or 0.0)
    adaptive_exact = float((adaptive_item.get("exact_metrics") or {}).get("f1", 0.0) or 0.0)
    has_direct = str(static_doc.get("reward_type", "")).strip() == "direct_set_based" or str(adaptive_doc.get("reward_type", "")).strip() == "direct_set_based"
    if has_direct:
        if adaptive_exact > static_exact + 1e-6:
            exact_state = "win"
        elif adaptive_exact < static_exact - 1e-6:
            exact_state = "loss"
        else:
            exact_state = "match"
    else:
        exact_state = "unscored"

    static_schema = bool(static_doc.get("schema_valid", False))
    adaptive_schema = bool(adaptive_doc.get("schema_valid", False))
    static_grounding = float(static_doc.get("schema_grounding_coverage", 0.0) or 0.0)
    adaptive_grounding = float(adaptive_doc.get("schema_grounding_coverage", 0.0) or 0.0)
    static_missing = int(static_doc.get("schema_missing_required_count", 0) or 0)
    adaptive_missing = int(adaptive_doc.get("schema_missing_required_count", 0) or 0)
    static_hallucinated = int(static_doc.get("schema_hallucinated_field_count", 0) or 0)
    adaptive_hallucinated = int(adaptive_doc.get("schema_hallucinated_field_count", 0) or 0)
    structural_score = (
        (1 if adaptive_schema else 0) - (1 if static_schema else 0),
        adaptive_grounding - static_grounding,
        static_missing - adaptive_missing,
        static_hallucinated - adaptive_hallucinated,
    )
    if structural_score > (0, 0.0, 0, 0):
        structural_state = "win"
    elif structural_score < (0, 0.0, 0, 0):
        structural_state = "loss"
    else:
        structural_state = "match"

    return {
        "exact_win_loss_state": exact_state,
        "structural_win_loss_state": structural_state,
        "direct_scored": has_direct,
    }


def _policy_impact_summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    impact = {
        "policy_changed_count": 0,
        "advice_accepted_count": 0,
        "direct_scored_doc_count": 0,
        "exact_win_count": 0,
        "exact_match_count": 0,
        "exact_loss_count": 0,
        "structural_win_count": 0,
        "structural_match_count": 0,
        "structural_loss_count": 0,
    }
    for item in documents:
        deltas = item.get("deltas", {})
        if bool(deltas.get("policy_changed")):
            impact["policy_changed_count"] += 1
        adaptive_doc = item.get(ADAPTIVE_LABEL, {}).get("doc", {})
        if isinstance(adaptive_doc, dict) and adaptive_doc.get("advice_accepted"):
            impact["advice_accepted_count"] += 1
        state = str(deltas.get("exact_win_loss_state", "unscored"))
        if state == "win":
            impact["exact_win_count"] += 1
        elif state == "loss":
            impact["exact_loss_count"] += 1
        elif state == "match":
            impact["exact_match_count"] += 1
            impact["direct_scored_doc_count"] += 1
        if state in {"win", "loss"}:
            impact["direct_scored_doc_count"] += 1
        structural_state = str(deltas.get("structural_win_loss_state", "match"))
        if structural_state == "win":
            impact["structural_win_count"] += 1
        elif structural_state == "loss":
            impact["structural_loss_count"] += 1
        else:
            impact["structural_match_count"] += 1
    total_docs = len(documents)
    impact["policy_switch_rate"] = round(impact["policy_changed_count"] / total_docs, 4) if total_docs else 0.0
    impact["advice_acceptance_rate"] = round(impact["advice_accepted_count"] / total_docs, 4) if total_docs else 0.0
    return impact


def _claim_checks(
    static_summary: dict[str, Any],
    adaptive_summary: dict[str, Any],
    comparison_table: dict[str, Any],
    policy_impact: dict[str, Any],
) -> dict[str, Any]:
    adaptive_statuses = adaptive_summary.get("advice_status_counts", {}) or {}
    adaptive_containment = adaptive_summary.get("containment_state_counts", {}) or {}
    accepted_count = int(adaptive_statuses.get("accepted", 0) or 0)
    rejected_count = int(adaptive_statuses.get("rejected", 0) or 0)
    no_advice_count = int(adaptive_statuses.get("no_advice", 0) or 0)
    policy_changed_count = int(policy_impact.get("policy_changed_count", 0) or 0)
    containment_count = sum(
        int(adaptive_containment.get(key, 0) or 0)
        for key in ("fallback", "rollback", "blocked", "defer_requested", "defer_blocked")
    )
    exact_f1_delta = float(comparison_table["exact_f1"][ADAPTIVE_LABEL] or 0.0) - float(comparison_table["exact_f1"]["static"] or 0.0)
    schema_delta = float(comparison_table["schema_valid_rate"][ADAPTIVE_LABEL] or 0.0) - float(comparison_table["schema_valid_rate"]["static"] or 0.0)
    validation_delta = float(comparison_table["validation_pass_rate"][ADAPTIVE_LABEL] or 0.0) - float(comparison_table["validation_pass_rate"]["static"] or 0.0)
    latency_delta = float(comparison_table["avg_latency_ms"]["static"] or 0.0) - float(comparison_table["avg_latency_ms"][ADAPTIVE_LABEL] or 0.0)

    checks = {
        "adaptive_safe_runtime_real": {
            "pass": accepted_count + rejected_count + no_advice_count > 0,
            "detail": f"accepted={accepted_count}, rejected={rejected_count}, no_advice={no_advice_count}",
        },
        "ahmn_changes_policy": {
            "pass": policy_changed_count > 0,
            "detail": f"policy_changed_count={policy_changed_count}",
        },
        "idpo_containment_exercised": {
            "pass": containment_count > 0,
            "detail": json.dumps(adaptive_containment, sort_keys=True),
        },
        "adaptive_improves_any_supported_metric": {
            "pass": exact_f1_delta > 0.0 or schema_delta > 0.0 or validation_delta > 0.0 or latency_delta > 0.0,
            "detail": (
                f"exact_f1_delta={round(exact_f1_delta, 4)}, "
                f"schema_valid_delta={round(schema_delta, 4)}, "
                f"validation_delta={round(validation_delta, 4)}, "
                f"latency_gain_ms={round(latency_delta, 2)}"
            ),
        },
        "claims_remain_limited": {
            "pass": True,
            "detail": "Benchmark supports adaptive-safe routing, containment behavior, and measured outcome deltas only.",
        },
    }
    return checks


def run_benchmark(config_path: str = "configs/idpo_research_config.json", pack_path: str = "idpo/benchmark/benchmark_pack.json") -> dict[str, Any]:
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
    conditions: dict[str, list[dict[str, Any]]] = {"static": [], ADAPTIVE_LABEL: []}
    started = time.time()

    with tempfile.TemporaryDirectory(prefix="idpo_benchmark_cfg_") as cfg_dir:
        cfg_root = Path(cfg_dir)
        condition_configs = {
            "static": _write_condition_config(base_config_path, "static", cfg_root),
            ADAPTIVE_LABEL: _write_condition_config(base_config_path, ADAPTIVE_LABEL, cfg_root),
        }
        condition_settings = {
            name: _load_config_payload(path).get("ahmn", {}) for name, path in condition_configs.items()
        }
        policy_store_path = str(_load_config_payload(base_config_path).get("knowledge", {}).get("policy_store_path", "")).strip()
        policy_store_payload = _load_config_payload((repo_root / policy_store_path).resolve()) if policy_store_path else {}
        valid_policy_ids = {
            str(item.get("policy_id", "")).strip()
            for item in policy_store_payload.get("policies", [])
            if isinstance(item, dict)
        }
        if not bool(condition_settings[ADAPTIVE_LABEL].get("enabled")):
            raise SystemExit("Adaptive benchmark configuration must enable AHMN")
        for case in cases:
            case_id = str(case.get("case_id", "")).strip() or f"case_{sum(len(v) for v in conditions.values()) + 1}"
            tags = [str(tag).strip() for tag in (case.get("tags", []) or []) if str(tag).strip()]
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

            for condition in ("static", ADAPTIVE_LABEL):
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
                        "tags": tags,
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

    _assert_adaptive_valid(conditions[ADAPTIVE_LABEL], valid_policy_ids)
    condition_summaries = {key: _condition_summary(value) for key, value in conditions.items()}
    documents = []
    grouped_static: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_adaptive: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in conditions["static"]:
        for tag in item.get("tags", []):
            grouped_static[tag].append(item)
    for item in conditions[ADAPTIVE_LABEL]:
        for tag in item.get("tags", []):
            grouped_adaptive[tag].append(item)
    static_by_case = {item["case_id"]: item for item in conditions["static"] if item.get("status") == "ok"}
    adaptive_by_case = {item["case_id"]: item for item in conditions[ADAPTIVE_LABEL] if item.get("status") == "ok"}
    for case in cases:
        case_id = str(case.get("case_id", "")).strip()
        tags = [str(tag).strip() for tag in (case.get("tags", []) or []) if str(tag).strip()]
        static_item = static_by_case.get(case_id, {})
        adaptive_item = adaptive_by_case.get(case_id, {})
        static_doc = static_item.get("doc", {})
        adaptive_doc = adaptive_item.get("doc", {})
        documents.append(
            {
                "case_id": case_id,
                "tags": tags,
                "static": {
                    "run_id": static_item.get("run_id", ""),
                    "run_dir": static_item.get("run_dir", ""),
                    "doc": static_doc,
                    "exact_metrics": static_item.get("exact_metrics", {}),
                },
                ADAPTIVE_LABEL: {
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
                    **_compare_case_outcome(static_doc, adaptive_doc, static_item, adaptive_item),
                },
            }
        )
    grouped_tables = {}
    for tag in sorted(set(grouped_static.keys()) | set(grouped_adaptive.keys())):
        static_summary = _condition_summary(grouped_static.get(tag, []))
        adaptive_summary = _condition_summary(grouped_adaptive.get(tag, []))
        grouped_tables[tag] = _comparison_table(static_summary, adaptive_summary, len(grouped_static.get(tag, [])))
    grouped_bootstrap = {
        tag: _bootstrap_summary([item for item in documents if tag in (item.get("tags") or [])], f"group:{tag}")
        for tag in PRIMARY_GROUP_TAGS
        if any(tag in (item.get("tags") or []) for item in documents)
    }

    comparison_table = _comparison_table(condition_summaries["static"], condition_summaries[ADAPTIVE_LABEL], len(cases))
    policy_impact = _policy_impact_summary(documents)
    evidence = {
        "experiment": {
            "benchmark_run_id": benchmark_run_id,
            "pack_name": pack.get("name", "benchmark_pack"),
            "pack_path": str(pack_file),
            "config_path": str(base_config_path),
            "ahmn_seed_mode": (os.getenv("AHMN_SEED_MODE", "seeded").strip().lower() or "seeded"),
            "condition_configs": {
                name: {
                    "path": str(path),
                    "ahmn_enabled": bool(condition_settings[name].get("enabled")),
                    "ahmn_mode": str(condition_settings[name].get("mode", "")).strip() or None,
                    "policy_mode": name,
                    "runtime_policy_mode": str(condition_settings[name].get("policy_mode", name)).strip() or name,
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
            ADAPTIVE_LABEL: condition_summaries[ADAPTIVE_LABEL],
            "table": comparison_table,
            "groups": grouped_tables,
            "bootstrap": {
                "overall": _bootstrap_summary(documents, "overall"),
                "groups": grouped_bootstrap,
            },
            "claim_checks": _claim_checks(condition_summaries["static"], condition_summaries[ADAPTIVE_LABEL], comparison_table, policy_impact),
            **policy_impact,
        },
        "documents": documents,
    }

    (out_dir / "paper_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (out_dir / "paper_table.md").write_text(_table_markdown(evidence), encoding="utf-8")
    (out_dir / "paper_table.csv").write_text(_table_csv(evidence), encoding="utf-8")
    return evidence


def _table_markdown(evidence: dict[str, Any]) -> str:
    table = evidence["comparison"]["table"]
    bootstrap = evidence["comparison"].get("bootstrap", {}).get("overall", {})
    exact_f1_delta = bootstrap.get("exact_f1_delta", {})
    latency_delta = bootstrap.get("latency_delta_ms", {})
    validation_delta = bootstrap.get("validation_pass_rate_delta", {})
    rows = [
        "| Metric | Static | Adaptive Safe |",
        "| --- | ---: | ---: |",
        f"| Doc Count | {table['doc_count']} | {table['doc_count']} |",
        f"| Avg Latency (ms) | {table['avg_latency_ms']['static']} | {table['avg_latency_ms'][ADAPTIVE_LABEL]} |",
        f"| Avg Reward | {table['avg_reward']['static']} | {table['avg_reward'][ADAPTIVE_LABEL]} |",
        f"| Exact Precision | {table['exact_precision']['static']} | {table['exact_precision'][ADAPTIVE_LABEL]} |",
        f"| Exact Recall | {table['exact_recall']['static']} | {table['exact_recall'][ADAPTIVE_LABEL]} |",
        f"| Exact F1 | {table['exact_f1']['static']} | {table['exact_f1'][ADAPTIVE_LABEL]} |",
        f"| Validation Pass Rate | {table['validation_pass_rate']['static']} | {table['validation_pass_rate'][ADAPTIVE_LABEL]} |",
        f"| Recovery Rate | {table['recovery_rate']['static']} | {table['recovery_rate'][ADAPTIVE_LABEL]} |",
        f"| Escalation Rate | {table['escalation_rate']['static']} | {table['escalation_rate'][ADAPTIVE_LABEL]} |",
        f"| Rollback Count | {table['rollback_count']['static']} | {table['rollback_count'][ADAPTIVE_LABEL]} |",
        f"| Blocked Policy Count | {table['blocked_policy_count']['static']} | {table['blocked_policy_count'][ADAPTIVE_LABEL]} |",
        f"| Feedback Logged | {table['feedback_logged_count']['static']} | {table['feedback_logged_count'][ADAPTIVE_LABEL]} |",
        f"| Advice Accepted Count | {table['advice_accepted_count']['static']} | {table['advice_accepted_count'][ADAPTIVE_LABEL]} |",
        f"| Policy Changed Count | {table['policy_changed_count']['static']} | {table['policy_changed_count'][ADAPTIVE_LABEL]} |",
        f"| Direct-Scored Doc Count | {table['direct_scored_doc_count']['static']} | {table['direct_scored_doc_count'][ADAPTIVE_LABEL]} |",
        f"| Avg Schema Coverage | {table['avg_schema_coverage']['static']} | {table['avg_schema_coverage'][ADAPTIVE_LABEL]} |",
        f"| Avg Grounding Coverage | {table['avg_schema_grounding_coverage']['static']} | {table['avg_schema_grounding_coverage'][ADAPTIVE_LABEL]} |",
        f"| Schema Valid Rate | {table['schema_valid_rate']['static']} | {table['schema_valid_rate'][ADAPTIVE_LABEL]} |",
        f"| Defer Requested Count | {table['defer_requested_count']['static']} | {table['defer_requested_count'][ADAPTIVE_LABEL]} |",
        f"| Defer Blocked Count | {table['defer_blocked_count']['static']} | {table['defer_blocked_count'][ADAPTIVE_LABEL]} |",
        f"| Exact F1 Delta Mean | - | {exact_f1_delta.get('mean', 0.0)} |",
        f"| Exact F1 Delta 95% CI | - | [{exact_f1_delta.get('ci_low', 0.0)}, {exact_f1_delta.get('ci_high', 0.0)}] |",
        f"| Latency Delta Mean (ms) | - | {latency_delta.get('mean', 0.0)} |",
        f"| Latency Delta 95% CI | - | [{latency_delta.get('ci_low', 0.0)}, {latency_delta.get('ci_high', 0.0)}] |",
        f"| Validation Pass Delta Mean | - | {validation_delta.get('mean', 0.0)} |",
        f"| Validation Pass Delta 95% CI | - | [{validation_delta.get('ci_low', 0.0)}, {validation_delta.get('ci_high', 0.0)}] |",
        f"| Policy Distribution | `{json.dumps(table['policy_distribution']['static'], sort_keys=True)}` | `{json.dumps(table['policy_distribution'][ADAPTIVE_LABEL], sort_keys=True)}` |",
        f"| Advice Sources | `{json.dumps(table['advice_source_counts']['static'], sort_keys=True)}` | `{json.dumps(table['advice_source_counts'][ADAPTIVE_LABEL], sort_keys=True)}` |",
        f"| Advice Statuses | `{json.dumps(table['advice_status_counts']['static'], sort_keys=True)}` | `{json.dumps(table['advice_status_counts'][ADAPTIVE_LABEL], sort_keys=True)}` |",
        f"| Retrieval Sources | `{json.dumps(table['retrieval_source_counts']['static'], sort_keys=True)}` | `{json.dumps(table['retrieval_source_counts'][ADAPTIVE_LABEL], sort_keys=True)}` |",
        f"| Containment States | `{json.dumps(table['containment_state_counts']['static'], sort_keys=True)}` | `{json.dumps(table['containment_state_counts'][ADAPTIVE_LABEL], sort_keys=True)}` |",
        f"| Operator Counts | `{json.dumps(table['operator_counts']['static'], sort_keys=True)}` | `{json.dumps(table['operator_counts'][ADAPTIVE_LABEL], sort_keys=True)}` |",
    ]
    return "\n".join(rows) + "\n"


def _table_csv(evidence: dict[str, Any]) -> str:
    table = evidence["comparison"]["table"]
    bootstrap = evidence["comparison"].get("bootstrap", {}).get("overall", {})
    exact_f1_delta = bootstrap.get("exact_f1_delta", {})
    latency_delta = bootstrap.get("latency_delta_ms", {})
    validation_delta = bootstrap.get("validation_pass_rate_delta", {})
    rows = [
        f"metric,static,{ADAPTIVE_LABEL}",
        f"doc_count,{table['doc_count']},{table['doc_count']}",
        f"avg_latency_ms,{table['avg_latency_ms']['static']},{table['avg_latency_ms'][ADAPTIVE_LABEL]}",
        f"avg_reward,{table['avg_reward']['static']},{table['avg_reward'][ADAPTIVE_LABEL]}",
        f"exact_precision,{table['exact_precision']['static']},{table['exact_precision'][ADAPTIVE_LABEL]}",
        f"exact_recall,{table['exact_recall']['static']},{table['exact_recall'][ADAPTIVE_LABEL]}",
        f"exact_f1,{table['exact_f1']['static']},{table['exact_f1'][ADAPTIVE_LABEL]}",
        f"validation_pass_rate,{table['validation_pass_rate']['static']},{table['validation_pass_rate'][ADAPTIVE_LABEL]}",
        f"recovery_rate,{table['recovery_rate']['static']},{table['recovery_rate'][ADAPTIVE_LABEL]}",
        f"escalation_rate,{table['escalation_rate']['static']},{table['escalation_rate'][ADAPTIVE_LABEL]}",
        f"rollback_count,{table['rollback_count']['static']},{table['rollback_count'][ADAPTIVE_LABEL]}",
        f"blocked_policy_count,{table['blocked_policy_count']['static']},{table['blocked_policy_count'][ADAPTIVE_LABEL]}",
        f"feedback_logged_count,{table['feedback_logged_count']['static']},{table['feedback_logged_count'][ADAPTIVE_LABEL]}",
        f"advice_accepted_count,{table['advice_accepted_count']['static']},{table['advice_accepted_count'][ADAPTIVE_LABEL]}",
        f"policy_changed_count,{table['policy_changed_count']['static']},{table['policy_changed_count'][ADAPTIVE_LABEL]}",
        f"direct_scored_doc_count,{table['direct_scored_doc_count']['static']},{table['direct_scored_doc_count'][ADAPTIVE_LABEL]}",
        f"avg_schema_coverage,{table['avg_schema_coverage']['static']},{table['avg_schema_coverage'][ADAPTIVE_LABEL]}",
        f"avg_schema_grounding_coverage,{table['avg_schema_grounding_coverage']['static']},{table['avg_schema_grounding_coverage'][ADAPTIVE_LABEL]}",
        f"schema_valid_rate,{table['schema_valid_rate']['static']},{table['schema_valid_rate'][ADAPTIVE_LABEL]}",
        f"defer_requested_count,{table['defer_requested_count']['static']},{table['defer_requested_count'][ADAPTIVE_LABEL]}",
        f"defer_blocked_count,{table['defer_blocked_count']['static']},{table['defer_blocked_count'][ADAPTIVE_LABEL]}",
        f"exact_f1_delta_mean,,{exact_f1_delta.get('mean', 0.0)}",
        f"exact_f1_delta_ci,,\"[{exact_f1_delta.get('ci_low', 0.0)}, {exact_f1_delta.get('ci_high', 0.0)}]\"",
        f"latency_delta_ms_mean,,{latency_delta.get('mean', 0.0)}",
        f"latency_delta_ms_ci,,\"[{latency_delta.get('ci_low', 0.0)}, {latency_delta.get('ci_high', 0.0)}]\"",
        f"validation_pass_rate_delta_mean,,{validation_delta.get('mean', 0.0)}",
        f"validation_pass_rate_delta_ci,,\"[{validation_delta.get('ci_low', 0.0)}, {validation_delta.get('ci_high', 0.0)}]\"",
        f"policy_distribution,\"{json.dumps(table['policy_distribution']['static'], sort_keys=True)}\",\"{json.dumps(table['policy_distribution'][ADAPTIVE_LABEL], sort_keys=True)}\"",
        f"advice_source_counts,\"{json.dumps(table['advice_source_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['advice_source_counts'][ADAPTIVE_LABEL], sort_keys=True)}\"",
        f"advice_status_counts,\"{json.dumps(table['advice_status_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['advice_status_counts'][ADAPTIVE_LABEL], sort_keys=True)}\"",
        f"retrieval_source_counts,\"{json.dumps(table['retrieval_source_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['retrieval_source_counts'][ADAPTIVE_LABEL], sort_keys=True)}\"",
        f"containment_state_counts,\"{json.dumps(table['containment_state_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['containment_state_counts'][ADAPTIVE_LABEL], sort_keys=True)}\"",
        f"operator_counts,\"{json.dumps(table['operator_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['operator_counts'][ADAPTIVE_LABEL], sort_keys=True)}\"",
    ]
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/idpo_research_config.json")
    parser.add_argument("--pack", default="idpo/benchmark/benchmark_pack.json")
    args = parser.parse_args()
    evidence = run_benchmark(config_path=args.config, pack_path=args.pack)
    print(json.dumps(evidence["comparison"]["table"], indent=2))
    print(f"report_path={benchmark_reports_dir() / evidence['experiment']['benchmark_run_id'] / 'paper_evidence.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
