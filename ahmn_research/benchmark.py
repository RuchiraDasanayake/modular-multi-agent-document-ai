"""
AHMN Policy Selection Benchmark
═══════════════════════════════════════════════════════════════════════════════

Runs the test_dataset.json through the live AHMN service via /api/dashboard/...
endpoints (or directly to the AHMN /advice endpoint via the gateway proxy)
and computes routing-quality metrics:

    - Policy selection accuracy (per regime: seen / near_neighbor / cold_start)
    - RABI activation rate (proportion of decisions that used neighbour priors)
    - Confidence calibration (high for seen, moderate for neighbours, low for cold-start)
    - Latency
    - Determinism check (same input → same policy across repeated calls)

Designed to demonstrate AHMN's three core claims:
    1. Recovers seeded policies exactly
    2. Generalises to unseen-but-similar contexts via vector kNN (RABI)
    3. Falls back to a safe default for cold-start contexts

Usage:
    docker compose up -d
    python3 ahmn_research/benchmark.py

Optional:
    python3 ahmn_research/benchmark.py --gateway http://<ec2-ip>:8000

Author: Pathirana M.M. and team
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
DATASET_PATH = SCRIPT_DIR / "test_dataset.json"
RESULTS_JSON = SCRIPT_DIR / "results.json"


# ─── Data models ──────────────────────────────────────────────────────

@dataclass
class CaseResult:
    cid: str
    regime: str
    doc_type: str
    vendor: str
    content_profile: str
    expected_policy: str
    selected_policy: str
    confidence: float
    latency_seconds: float
    rabi_used: bool
    n_neighbors: int | None
    retrieval_source: str
    policy_correct: bool
    confidence_calibrated: bool
    deterministic: bool   # same policy on repeated call?
    error: str | None = None


@dataclass
class RegimeMetrics:
    total: int = 0
    correct: int = 0
    rabi_count: int = 0
    avg_latency: float = 0.0
    avg_confidence: float = 0.0
    confidence_calibrated_count: int = 0
    deterministic_count: int = 0


# ─── Auth & API helpers ───────────────────────────────────────────────

def login(gateway_url: str, username: str, password: str) -> str:
    resp = requests.post(
        f"{gateway_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def call_ahmn_advice(gateway_url: str, token: str, case: dict, timeout: int = 30) -> tuple[dict, float]:
    """Call the AHMN advice endpoint via the gateway. Returns (response_json, latency)."""
    payload = {
        "doc_type": case["doc_type"],
        "vendor": case.get("vendor"),
        "content_profile": case.get("content_profile"),
    }
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    # The gateway proxies AHMN /advice as /api/advice — fall back to direct
    # AHMN port 8001 if not exposed. Try both.
    urls = [f"{gateway_url}/api/advice", "http://localhost:8001/advice"]
    last_err = None
    for url in urls:
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json(), time.time() - start
            last_err = f"{url} returned HTTP {resp.status_code}"
        except Exception as e:
            last_err = f"{url}: {e}"
    raise RuntimeError(f"All advice endpoints failed: {last_err}")


# ─── Scoring ──────────────────────────────────────────────────────────

def confidence_calibrated(case: dict, confidence: float) -> bool:
    min_c = case.get("min_confidence", 0.0)
    max_c = case.get("max_confidence", 1.0)
    return min_c <= confidence <= max_c


# ─── Benchmark runner ─────────────────────────────────────────────────

def run_benchmark(gateway_url: str, token: str, dataset: dict, timeout: int = 30,
                  determinism_repeats: int = 1) -> list[CaseResult]:
    results: list[CaseResult] = []
    cases = dataset["cases"]

    print(f"\n{'='*80}")
    print(f"Running {len(cases)} cases against AHMN /advice (via {gateway_url})")
    print(f"{'='*80}\n")

    for i, c in enumerate(cases, start=1):
        print(f"[{i:>2}/{len(cases)}] {c['id']} ({c['regime']:<14}) "
              f"{c['doc_type']:<25} → expect '{c['expected_policy']}'", end=" ", flush=True)

        try:
            data, latency = call_ahmn_advice(gateway_url, token, c, timeout)
            selected = data.get("policy_id", "")
            confidence = float(data.get("confidence", 0.0))
            rabi_used = bool(data.get("rabi_used", False))
            n_neighbors = data.get("n_neighbors")
            retrieval = data.get("retrieval_source", "UNKNOWN")
            error = None
        except Exception as exc:
            latency = 0.0
            selected = ""
            confidence = -1.0
            rabi_used = False
            n_neighbors = None
            retrieval = "ERROR"
            error = str(exc)

        # Determinism check: call once more, same answer?
        deterministic = True
        if determinism_repeats and not error:
            try:
                data2, _ = call_ahmn_advice(gateway_url, token, c, timeout)
                if data2.get("policy_id") != selected:
                    deterministic = False
            except Exception:
                deterministic = False

        result = CaseResult(
            cid=c["id"],
            regime=c["regime"],
            doc_type=c["doc_type"],
            vendor=c.get("vendor", ""),
            content_profile=c.get("content_profile", ""),
            expected_policy=c["expected_policy"],
            selected_policy=selected,
            confidence=round(confidence, 3),
            latency_seconds=round(latency, 3),
            rabi_used=rabi_used,
            n_neighbors=n_neighbors,
            retrieval_source=retrieval,
            policy_correct=(selected == c["expected_policy"]),
            confidence_calibrated=confidence_calibrated(c, confidence),
            deterministic=deterministic,
            error=error,
        )
        results.append(result)

        marker = "✓" if result.policy_correct else "✗"
        rabi_marker = "[RABI]" if rabi_used else "[----]"
        print(f"{marker} got '{selected}' conf={confidence:.2f} {rabi_marker} ({latency*1000:.0f}ms)")

    return results


def aggregate(results: list[CaseResult]) -> dict[str, RegimeMetrics]:
    by_regime: dict[str, RegimeMetrics] = {}
    for r in results:
        m = by_regime.setdefault(r.regime, RegimeMetrics())
        m.total += 1
        if r.policy_correct:
            m.correct += 1
        if r.rabi_used:
            m.rabi_count += 1
        m.avg_latency += r.latency_seconds
        if r.confidence >= 0:
            m.avg_confidence += r.confidence
        if r.confidence_calibrated:
            m.confidence_calibrated_count += 1
        if r.deterministic:
            m.deterministic_count += 1
    for m in by_regime.values():
        if m.total:
            m.avg_latency = round(m.avg_latency / m.total, 3)
            m.avg_confidence = round(m.avg_confidence / m.total, 3)
    return by_regime


def print_summary(metrics: dict[str, RegimeMetrics], results: list[CaseResult]) -> None:
    overall_total = sum(m.total for m in metrics.values())
    overall_correct = sum(m.correct for m in metrics.values())
    overall_acc = (overall_correct / overall_total * 100) if overall_total else 0
    avg_latency_ms = sum(r.latency_seconds for r in results) / len(results) * 1000 if results else 0
    rabi_total = sum(m.rabi_count for m in metrics.values())
    determ_total = sum(m.deterministic_count for m in metrics.values())

    print(f"\n{'='*80}")
    print("AHMN BENCHMARK SUMMARY")
    print(f"{'='*80}\n")
    print(f"Overall routing accuracy:  {overall_correct}/{overall_total}  ({overall_acc:.1f}%)")
    print(f"Avg latency:               {avg_latency_ms:.0f} ms per call")
    print(f"RABI activation rate:      {rabi_total}/{overall_total}  ({rabi_total/overall_total*100:.0f}%)")
    print(f"Determinism rate:          {determ_total}/{overall_total}  ({determ_total/overall_total*100:.0f}%)")
    print()
    print(f"Per-regime breakdown:")
    print(f"{'Regime':<16} {'Acc':<14} {'AvgConf':<10} {'Calibrated':<12} {'AvgLatency':<12}")
    print("-" * 70)
    for regime, m in sorted(metrics.items()):
        acc = f"{m.correct}/{m.total} ({m.correct/m.total*100:.0f}%)"
        cal = f"{m.confidence_calibrated_count}/{m.total}"
        lat = f"{m.avg_latency*1000:.0f}ms"
        print(f"{regime:<16} {acc:<14} {m.avg_confidence:<10.3f} {cal:<12} {lat:<12}")

    print(f"\nFailed cases (selected ≠ expected):")
    failures = [r for r in results if not r.policy_correct]
    if not failures:
        print("  (none — all cases routed correctly)")
    else:
        for f in failures:
            print(f"  {f.cid} ({f.regime}): {f.doc_type:<25} "
                  f"expected '{f.expected_policy}', got '{f.selected_policy}' (conf={f.confidence:.2f})")


def save_results(results: list[CaseResult], metrics: dict[str, RegimeMetrics],
                 gateway_url: str) -> None:
    payload = {
        "run_timestamp": datetime.now().isoformat(),
        "gateway_url": gateway_url,
        "overall": {
            "total": sum(m.total for m in metrics.values()),
            "correct": sum(m.correct for m in metrics.values()),
            "accuracy_pct": round(
                sum(m.correct for m in metrics.values())
                / max(1, sum(m.total for m in metrics.values())) * 100, 2),
            "rabi_activation_pct": round(
                sum(m.rabi_count for m in metrics.values())
                / max(1, sum(m.total for m in metrics.values())) * 100, 2),
            "determinism_pct": round(
                sum(m.deterministic_count for m in metrics.values())
                / max(1, sum(m.total for m in metrics.values())) * 100, 2),
            "avg_latency_ms": round(
                sum(r.latency_seconds for r in results) / max(1, len(results)) * 1000, 2),
        },
        "per_regime": {regime: asdict(m) for regime, m in metrics.items()},
        "per_case": [asdict(r) for r in results],
    }
    RESULTS_JSON.write_text(json.dumps(payload, indent=2))
    print(f"\nRaw results written to: {RESULTS_JSON}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="http://localhost:8000",
                        help="Gateway URL (default: http://localhost:8000)")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    if not DATASET_PATH.exists():
        print(f"ERROR: dataset not found at {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)
    dataset = json.loads(DATASET_PATH.read_text())

    # Health check
    try:
        h = requests.get(f"{args.gateway}/health", timeout=5)
        if h.status_code != 200:
            print(f"WARNING: gateway health returned {h.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: gateway not reachable at {args.gateway}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Authenticating as {args.username}...")
    try:
        token = login(args.gateway, args.username, args.password)
    except Exception as e:
        print(f"ERROR: login failed: {e}", file=sys.stderr)
        sys.exit(1)

    results = run_benchmark(args.gateway, token, dataset, args.timeout)
    metrics = aggregate(results)
    print_summary(metrics, results)
    save_results(results, metrics, args.gateway)


if __name__ == "__main__":
    main()
