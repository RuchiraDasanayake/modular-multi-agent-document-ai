"""Summarise static vs adaptive_safe benchmark evidence: micro P/R/F1, perfect documents, validation pass, latency,
and paired adaptive-minus-static deltas with 95% bootstrap intervals (10,000 resamples, seed 17).

Usage:
  python scripts/aggregate_benchmark_evidence.py [--rescore] LABEL=path[,path...] [LABEL=path ...]

Each path is a paper_evidence.json written by scripts/run_idpo_benchmark.py. Paths given to one label are pooled,
e.g. CORD-100=<cord_pack_50 evidence>,<cord_holdout_50 evidence>.

--rescore recomputes every document's tp/fp/fn with the current scorer in scripts/run_idpo_benchmark.py, reading the
saved validation/normalized.json of each run, so evidence written by an older scorer can be compared like for like.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ("static", "adaptive_safe")
BOOTSTRAP_RESAMPLES = 10_000


def rescore(docs: list[dict]) -> int:
    sys.path.insert(0, str(REPO_ROOT))
    import scripts.run_idpo_benchmark as benchmark

    changed = 0
    for doc in docs:
        for condition in CONDITIONS:
            row = doc.get(condition)
            if not row:
                continue
            normalized_path = str(row["doc"].get("validation_normalized_path") or "")
            if normalized_path and not Path(normalized_path).exists():
                raise SystemExit(f"--rescore needs the saved run artifacts; missing {normalized_path}")
            tp, fp, fn = benchmark._case_metrics(doc.get("expected") or {}, benchmark._exact_scoring_field_values(row["doc"]))
            old = row.get("exact_metrics") or {}
            if (tp, fp, fn) != (old.get("tp", 0), old.get("fp", 0), old.get("fn", 0)):
                changed += 1
            row["exact_metrics"] = {**old, "tp": tp, "fp": fp, "fn": fn}
    return changed


def doc_f1(metrics: dict) -> float:
    tp, fp, fn = metrics.get("tp", 0), metrics.get("fp", 0), metrics.get("fn", 0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def bootstrap_mean_ci(values: list[float], seed: int = 17) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(BOOTSTRAP_RESAMPLES))
    return sum(values) / n, means[int(0.025 * BOOTSTRAP_RESAMPLES)], means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]


def summarize(label: str, paths: list[str], rescored: bool) -> None:
    docs = []
    for path in paths:
        docs.extend(json.loads(Path(path).read_text(encoding="utf-8"))["documents"])
    print(f"\n## {label}  (n={len(docs)} docs from {len(paths)} file(s))")
    if rescored:
        print(f"rescored with the current scorer: {rescore(docs)} document result(s) changed")
    print("| condition | micro P | micro R | micro F1 | mean doc F1 | perfect docs | valid. pass | mean latency s |")
    print("|---|---|---|---|---|---|---|---|")
    per_condition: dict[str, list[dict]] = {}
    for condition in CONDITIONS:
        rows = [doc[condition] for doc in docs if condition in doc]
        per_condition[condition] = rows
        tp = sum(row["exact_metrics"].get("tp", 0) for row in rows)
        fp = sum(row["exact_metrics"].get("fp", 0) for row in rows)
        fn = sum(row["exact_metrics"].get("fn", 0) for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        doc_f1s = [doc_f1(row["exact_metrics"]) for row in rows]
        perfect = sum(1 for value in doc_f1s if value >= 0.9999)
        valid = sum(1 for row in rows if int(row["doc"].get("validation_issue_count", 0) or 0) == 0)
        latencies = [float(row["doc"].get("latency_ms", 0.0) or 0.0) / 1000 for row in rows]
        print(
            f"| {condition} | {precision:.3f} | {recall:.3f} | {f1:.3f} | {sum(doc_f1s) / len(doc_f1s):.3f} "
            f"| {perfect}/{len(rows)} ({perfect / len(rows):.0%}) | {valid / len(rows):.2f} "
            f"| {sum(latencies) / len(latencies):.1f} |"
        )

    f1_deltas, latency_deltas, better, worse = [], [], 0, 0
    for doc in docs:
        static, adaptive = doc.get("static"), doc.get("adaptive_safe")
        if not static or not adaptive:
            continue
        delta = doc_f1(adaptive["exact_metrics"]) - doc_f1(static["exact_metrics"])
        f1_deltas.append(delta)
        latency_deltas.append(
            (float(adaptive["doc"].get("latency_ms", 0) or 0) - float(static["doc"].get("latency_ms", 0) or 0)) / 1000
        )
        better += delta > 1e-9
        worse += delta < -1e-9
    mean, low, high = bootstrap_mean_ci(f1_deltas)
    latency_mean, latency_low, latency_high = bootstrap_mean_ci(latency_deltas)
    print(
        f"\npaired doc F1 delta (adaptive - static): mean {mean:+.4f}, 95% CI [{low:+.4f}, {high:+.4f}]; "
        f"adaptive better on {better}, worse on {worse}, tied on {len(f1_deltas) - better - worse}"
    )
    print(f"paired latency delta: mean {latency_mean:+.2f}s, 95% CI [{latency_low:+.2f}, {latency_high:+.2f}]")
    distribution = Counter(row["doc"].get("policy_id", "?") for row in per_condition["adaptive_safe"])
    print(f"adaptive policy distribution: {dict(distribution.most_common())}")


def main() -> None:
    arguments = [argument for argument in sys.argv[1:] if argument != "--rescore"]
    if not arguments:
        print(__doc__)
        raise SystemExit(2)
    for argument in arguments:
        label, _, joined = argument.partition("=")
        summarize(label, joined.split(","), rescored="--rescore" in sys.argv[1:])


if __name__ == "__main__":
    main()
