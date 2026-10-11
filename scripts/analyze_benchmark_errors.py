"""Per-field error breakdown and label-free reward vs exact accuracy for static vs adaptive_safe benchmark evidence.

Usage:
  python scripts/analyze_benchmark_errors.py [--imperfect] LABEL=path[,path...] [LABEL=path ...]

Each path is a paper_evidence.json written by scripts/run_idpo_benchmark.py. Paths given to one label are pooled.
Every document is scored with the current scorer from its saved validation/normalized.json, so the counts match
scripts/aggregate_benchmark_evidence.py --rescore.

For each condition the script prints, per field, how many labelled values were correct, wrong or missed and how many
values were returned for fields the document does not label. It then prints the Pearson correlation between the
label-free reward and exact document F1, and how many documents the reward counted as a success (reward >= 0.5, the
threshold of the Bernoulli posterior update) although they had a wrong or missing value. --imperfect also lists every
document with document F1 below 1.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ("static", "adaptive_safe")
OUTCOMES = ("correct", "wrong", "missed", "unlabelled_value")
SUCCESS_REWARD = 0.5

sys.path.insert(0, str(REPO_ROOT))
import scripts.run_idpo_benchmark as benchmark  # noqa: E402


def field_outcome(key: str, expected: object, extracted: object) -> str:
    if not benchmark._normalize_exact_value(key, extracted):
        return "missed"
    tp, _, _ = benchmark._case_metrics({key: expected}, {key: extracted})
    return "correct" if tp else "wrong"


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    spread_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    spread_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if not spread_x or not spread_y:
        return float("nan")
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / (spread_x * spread_y)


def condition_breakdown(docs: list[dict], condition: str) -> dict:
    fields: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    rewards: list[float] = []
    doc_f1s: list[float] = []
    has_labelled_error: list[bool] = []
    imperfect: list[str] = []
    for doc in docs:
        row = doc.get(condition)
        if not row:
            continue
        expected = doc.get("expected") or {}
        extracted = benchmark._exact_scoring_field_values(row["doc"])
        outcomes = {key: field_outcome(key, value, extracted.get(key, "")) for key, value in expected.items()}
        for key, outcome in outcomes.items():
            fields[key]["labelled"] += 1
            fields[key][outcome] += 1
        for key, value in extracted.items():
            if key not in expected and benchmark._normalize_exact_value(key, value):
                fields[key]["unlabelled_value"] += 1
        tp, fp, fn = benchmark._case_metrics(expected, extracted)
        doc_f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        reward = float(row["doc"].get("reward") or 0.0)
        errors = {key: outcome for key, outcome in outcomes.items() if outcome != "correct"}
        doc_f1s.append(doc_f1)
        rewards.append(reward)
        has_labelled_error.append(bool(errors))
        if doc_f1 < 1.0:
            imperfect.append(f"{doc.get('case_id')}: doc F1 {doc_f1:.2f}, reward {reward:.2f}, {errors}")
    return {
        "fields": {key: dict(counts) for key, counts in sorted(fields.items())},
        "documents": len(doc_f1s),
        "reward_f1_pearson": pearson(rewards, doc_f1s),
        "mean_reward": sum(rewards) / len(rewards) if rewards else 0.0,
        "mean_doc_f1": sum(doc_f1s) / len(doc_f1s) if doc_f1s else 0.0,
        "reward_successes": sum(1 for reward in rewards if reward >= SUCCESS_REWARD),
        "imperfect_successes": sum(1 for reward, f1 in zip(rewards, doc_f1s) if reward >= SUCCESS_REWARD and f1 < 1.0),
        "labelled_error_successes": sum(
            1 for reward, error in zip(rewards, has_labelled_error) if reward >= SUCCESS_REWARD and error
        ),
        "imperfect": imperfect,
    }


def summarize(label: str, paths: list[str], list_imperfect: bool) -> None:
    docs = []
    for path in paths:
        docs.extend(json.loads(Path(path).read_text(encoding="utf-8"))["documents"])
    print(f"\n## {label}  (n={len(docs)} docs from {len(paths)} file(s))")
    for condition in CONDITIONS:
        result = condition_breakdown(docs, condition)
        if not result["documents"]:
            continue
        print(f"\n### {condition}")
        print("| field | labelled | correct | wrong | missed | value for unlabelled field |")
        print("|---|---|---|---|---|---|")
        totals = defaultdict(int)
        for key, counts in result["fields"].items():
            for name in ("labelled", *OUTCOMES):
                totals[name] += counts.get(name, 0)
            print(
                f"| {key} | {counts.get('labelled', 0)} | {counts.get('correct', 0)} | {counts.get('wrong', 0)} "
                f"| {counts.get('missed', 0)} | {counts.get('unlabelled_value', 0)} |"
            )
        print(
            f"| all | {totals['labelled']} | {totals['correct']} | {totals['wrong']} | {totals['missed']} "
            f"| {totals['unlabelled_value']} |"
        )
        print(
            f"\nlabel-free reward vs exact document F1: Pearson r = {result['reward_f1_pearson']:.2f} "
            f"(mean reward {result['mean_reward']:.3f}, mean document F1 {result['mean_doc_f1']:.3f})"
        )
        print(
            f"reward counted as a success on {result['reward_successes']}/{result['documents']} documents: "
            f"{result['imperfect_successes']} of them with document F1 below 1, "
            f"{result['labelled_error_successes']} with a wrong or missing labelled value"
        )
        if list_imperfect:
            for line in result["imperfect"]:
                print(f"  {line}")


def main() -> None:
    arguments = [argument for argument in sys.argv[1:] if argument != "--imperfect"]
    if not arguments:
        print(__doc__)
        raise SystemExit(2)
    for argument in arguments:
        label, _, joined = argument.partition("=")
        summarize(label, joined.split(","), list_imperfect="--imperfect" in sys.argv[1:])


if __name__ == "__main__":
    main()
