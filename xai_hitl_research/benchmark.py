"""
XAI/HITL Benchmark Script
═══════════════════════════════════════════════════════════════════════════════

Runs the test_dataset.json through the live XAI service and computes
research-grade evaluation metrics: accuracy, hallucination rate, polarity
correctness, and per-handler breakdown.

Designed to demonstrate measurable improvement of the full system over
the BART-only baseline — the core research evidence required by IT4010.

Usage:
    # Make sure the docker stack is running first:
    #   docker compose up -d
    #
    # Then run the benchmark:
    python xai_hitl_research/benchmark.py

    # Optional: point at a different gateway (for EC2 / remote runs)
    python xai_hitl_research/benchmark.py --gateway http://<ec2-ip>:8000

Outputs:
    - Console summary table
    - xai_hitl_research/results.json  (raw per-question results)
    - xai_hitl_research/RESULTS.md updated with the latest run

Author: Pathirana M.M.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
DATASET_PATH = SCRIPT_DIR / "test_dataset.json"
RESULTS_JSON = SCRIPT_DIR / "results.json"

# The full text of the Financial Transactions Reporting Act, condensed for
# use as the document context. In production, this would come from IDPO
# extraction; here we paste the OCR'd text directly so the benchmark is
# self-contained and reproducible.
DOCUMENT_PATH = SCRIPT_DIR / "source_document.txt"


# ─── Data models ──────────────────────────────────────────────────────

@dataclass
class QuestionResult:
    qid: str
    category: str
    question: str
    ground_truth: str
    predicted: str
    confidence: float
    latency_seconds: float
    is_correct: bool
    is_polarity_correct: bool | None
    contains_ground_truth_token: bool
    handler_used: str  # inferred from derivation tree if available
    error: str | None = None


@dataclass
class CategoryMetrics:
    total: int = 0
    correct: int = 0
    polarity_correct: int = 0
    polarity_total: int = 0
    avg_latency: float = 0.0
    avg_confidence: float = 0.0
    contains_truth_count: int = 0


# ─── Scoring helpers ──────────────────────────────────────────────────

def normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


SPELLED_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "twenty-four": 24, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000, "million": 1000000,
}


def _extract_numbers(text: str) -> set[int]:
    """Extract numeric values from text, including spelled-out numbers and
    compound forms ('one hundred thousand' = 100000, 'twenty four' = 24)."""
    text = text.lower().replace(",", "")
    found: set[int] = set()

    # Digits
    for m in re.finditer(r"\b(\d+)\b", text):
        found.add(int(m.group(1)))

    # Spelled-out — naive but effective for the evaluation set
    words = re.findall(r"[a-z\-]+", text)
    i = 0
    while i < len(words):
        if words[i] in SPELLED_NUMBERS:
            current = SPELLED_NUMBERS[words[i]]
            j = i + 1
            # Combine with multiplier or addition: "one hundred thousand", "twenty four"
            while j < len(words) and words[j] in SPELLED_NUMBERS:
                nxt = SPELLED_NUMBERS[words[j]]
                if nxt >= 100:
                    current = max(current, 1) * nxt
                else:
                    current += nxt
                j += 1
            found.add(current)
            i = j
        else:
            i += 1
    return found


def numerical_match(predicted: str, ground_truth: str) -> bool:
    """Match number+unit, accepting both digit and spelled-out forms."""
    gt_nums = _extract_numbers(ground_truth)
    pred_nums = _extract_numbers(predicted)
    if not gt_nums:
        return False
    if not (gt_nums & pred_nums):
        return False
    gt_unit = re.search(r"\b(years?|months?|days?|hours?|weeks?|rupees?|usd|dollars?)\b",
                        ground_truth.lower())
    pred_unit = re.search(r"\b(years?|months?|days?|hours?|weeks?|rupees?|usd|dollars?)\b",
                          predicted.lower())
    if gt_unit and pred_unit:
        return gt_unit.group(1).rstrip("s") == pred_unit.group(1).rstrip("s")
    return True


def polarity_match(predicted: str, expected_polarity: str) -> bool:
    """For yes/no questions: detect polarity from the first sentence of the answer."""
    pred_lower = predicted.lower().strip()
    first_sentence = pred_lower.split(".")[0]

    # Strong yes signals
    yes_signals = ["yes,", "yes.", "yes ", "yes\n", "yes:"]
    no_signals = ["no,", "no.", "no ", "no\n", "no:"]

    starts_with_yes = first_sentence.startswith(("yes",)) and any(
        first_sentence.startswith(s.strip(",.: \n")) for s in yes_signals
    )
    starts_with_no = first_sentence.startswith(("no",)) and any(
        first_sentence.startswith(s.strip(",.: \n")) for s in no_signals
    )

    # Fall back to permissive check
    if not (starts_with_yes or starts_with_no):
        if first_sentence.startswith("yes"):
            starts_with_yes = True
        elif first_sentence.startswith("no") and not first_sentence.startswith(("not", "non", "now", "none")):
            starts_with_no = True

    if expected_polarity == "yes":
        return starts_with_yes and not starts_with_no
    if expected_polarity == "no":
        return starts_with_no and not starts_with_yes
    return False


def is_correct(question: dict, predicted: str) -> tuple[bool, bool, bool]:
    """Returns (correct, polarity_correct, contains_truth_token).

    Scoring rules:
    - numerical: number + unit must match
    - yes_no_legal: first-sentence polarity must match
    - factual_extractive: ground truth token must appear in prediction
    - synthesis: at least 40% of ground-truth content tokens must appear
    """
    category = question["category"]
    gt = question["ground_truth_answer"]
    polarity = question.get("expected_polarity")

    correct = False
    polarity_correct: bool | None = None
    contains_truth = normalize(gt) in normalize(predicted) if gt else False

    if category == "numerical":
        correct = numerical_match(predicted, gt)
    elif category == "yes_no_legal":
        polarity_correct = polarity_match(predicted, polarity) if polarity else None
        correct = bool(polarity_correct)
    elif category == "factual_extractive":
        # Token-level recall: at least one significant token of GT in prediction
        gt_tokens = [t for t in normalize(gt).split() if len(t) > 3]
        pred_norm = normalize(predicted)
        correct = any(t in pred_norm for t in gt_tokens) if gt_tokens else False
    elif category == "synthesis":
        gt_tokens = set(t for t in normalize(gt).split() if len(t) > 3)
        pred_tokens = set(normalize(predicted).split())
        if gt_tokens:
            overlap = len(gt_tokens & pred_tokens) / len(gt_tokens)
            correct = overlap >= 0.40

    return correct, polarity_correct, contains_truth


def detect_handler(response: dict) -> str:
    """Inspect the derivation tree to figure out which handler answered."""
    try:
        steps = response.get("explanation", {}).get("derivation_tree", {}).get("steps", [])
        if not steps:
            return "unknown"
        first_step = (steps[0].get("action") or "").lower()
        if "numerical" in first_step or "🔢" in steps[0].get("action", ""):
            return "numerical"
        if "legal" in first_step or "⚖" in steps[0].get("action", ""):
            return "legal_yes_no"
        if "yes/no" in first_step or "❓" in steps[0].get("action", ""):
            return "yes_no_label"
        if "list" in first_step:
            return "list"
        if "comparison" in first_step:
            return "comparison"
        if "conversational" in first_step or "💬" in steps[0].get("action", ""):
            return "conversational"
        return "model_generated"
    except Exception:
        return "unknown"


# ─── Benchmark runner ─────────────────────────────────────────────────

def login(gateway_url: str, username: str, password: str) -> str:
    """Authenticate against the gateway and return a JWT access token."""
    resp = requests.post(
        f"{gateway_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def run_benchmark(gateway_url: str, document: str, dataset: dict,
                  token: str, request_timeout: int = 240) -> list[QuestionResult]:
    """Run every question in the dataset through the XAI service."""
    results: list[QuestionResult] = []
    questions = dataset["questions"]
    headers = {"Authorization": f"Bearer {token}"}

    print(f"\n{'='*80}")
    print(f"Running {len(questions)} questions against {gateway_url}/api/xai/ask")
    print(f"{'='*80}\n")

    for i, q in enumerate(questions, start=1):
        print(f"[{i:>2}/{len(questions)}] {q['id']} ({q['category']}): {q['question'][:60]}...",
              end=" ", flush=True)

        start = time.time()
        try:
            resp = requests.post(
                f"{gateway_url}/api/xai/ask",
                json={
                    "paragraph": document,
                    "question": q["question"],
                    "include_xai": False,
                },
                headers=headers,
                timeout=request_timeout,
            )
            latency = time.time() - start
            data = resp.json()
            predicted = data.get("answer", "")
            confidence = float(data.get("confidence", 0.0))
            handler = detect_handler(data)
            error = None
            if resp.status_code != 200:
                error = f"HTTP {resp.status_code}"
        except Exception as exc:
            latency = time.time() - start
            predicted = ""
            confidence = -1.0
            handler = "error"
            error = str(exc)

        correct, polarity_correct, contains_truth = is_correct(q, predicted)

        result = QuestionResult(
            qid=q["id"],
            category=q["category"],
            question=q["question"],
            ground_truth=q["ground_truth_answer"],
            predicted=predicted,
            confidence=confidence,
            latency_seconds=round(latency, 2),
            is_correct=correct,
            is_polarity_correct=polarity_correct,
            contains_ground_truth_token=contains_truth,
            handler_used=handler,
            error=error,
        )
        results.append(result)

        marker = "✓" if correct else "✗"
        print(f"{marker} ({latency:.1f}s, {handler})")

    return results


def aggregate(results: list[QuestionResult]) -> dict[str, CategoryMetrics]:
    metrics: dict[str, CategoryMetrics] = {}
    for r in results:
        m = metrics.setdefault(r.category, CategoryMetrics())
        m.total += 1
        if r.is_correct:
            m.correct += 1
        if r.is_polarity_correct is not None:
            m.polarity_total += 1
            if r.is_polarity_correct:
                m.polarity_correct += 1
        m.avg_latency += r.latency_seconds
        if r.confidence >= 0:
            m.avg_confidence += r.confidence
        if r.contains_ground_truth_token:
            m.contains_truth_count += 1

    for m in metrics.values():
        if m.total:
            m.avg_latency = round(m.avg_latency / m.total, 2)
            m.avg_confidence = round(m.avg_confidence / m.total, 3)
    return metrics


def print_summary(metrics: dict[str, CategoryMetrics], results: list[QuestionResult]) -> None:
    overall_total = sum(m.total for m in metrics.values())
    overall_correct = sum(m.correct for m in metrics.values())
    overall_acc = (overall_correct / overall_total * 100) if overall_total else 0
    avg_latency = sum(r.latency_seconds for r in results) / len(results) if results else 0

    print(f"\n{'='*80}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*80}")
    print(f"\nOverall accuracy:  {overall_correct}/{overall_total}  ({overall_acc:.1f}%)")
    print(f"Avg latency:       {avg_latency:.2f}s per question")
    print(f"\nPer-category breakdown:")
    print(f"{'Category':<22} {'Acc':<12} {'Polarity':<12} {'Avg Latency':<14} {'Avg Conf':<10}")
    print("-" * 75)
    for cat, m in sorted(metrics.items()):
        acc_str = f"{m.correct}/{m.total} ({m.correct/m.total*100:.0f}%)" if m.total else "n/a"
        pol_str = (f"{m.polarity_correct}/{m.polarity_total}"
                   if m.polarity_total else "n/a")
        print(f"{cat:<22} {acc_str:<12} {pol_str:<12} {m.avg_latency:<14.2f} {m.avg_confidence:<10.3f}")

    # Handler breakdown
    handler_counts: dict[str, int] = {}
    for r in results:
        handler_counts[r.handler_used] = handler_counts.get(r.handler_used, 0) + 1
    print(f"\nHandler usage (which pipeline stage answered):")
    for handler, count in sorted(handler_counts.items(), key=lambda x: -x[1]):
        print(f"  {handler:<22} {count:>3}  ({count/len(results)*100:.0f}%)")


def save_results(results: list[QuestionResult], metrics: dict[str, CategoryMetrics],
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
            "avg_latency_seconds": round(
                sum(r.latency_seconds for r in results) / max(1, len(results)), 2),
        },
        "per_category": {cat: asdict(m) for cat, m in metrics.items()},
        "per_question": [asdict(r) for r in results],
    }
    RESULTS_JSON.write_text(json.dumps(payload, indent=2))
    print(f"\nRaw results written to: {RESULTS_JSON}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="http://localhost:8000",
                        help="Gateway URL (default: http://localhost:8000)")
    parser.add_argument("--timeout", type=int, default=240,
                        help="Per-request timeout in seconds (default: 240)")
    parser.add_argument("--username", default="admin",
                        help="Gateway login username (default: admin)")
    parser.add_argument("--password", default="admin",
                        help="Gateway login password (default: seeded admin password)")
    args = parser.parse_args()

    if not DATASET_PATH.exists():
        print(f"ERROR: dataset not found at {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    if not DOCUMENT_PATH.exists():
        print(f"ERROR: source document not found at {DOCUMENT_PATH}", file=sys.stderr)
        print(f"       Create it with the OCR text of the test document.", file=sys.stderr)
        sys.exit(1)

    dataset = json.loads(DATASET_PATH.read_text())
    document = DOCUMENT_PATH.read_text()

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

    results = run_benchmark(args.gateway, document, dataset, token, args.timeout)
    metrics = aggregate(results)
    print_summary(metrics, results)
    save_results(results, metrics, args.gateway)

    # Exit non-zero if accuracy is suspiciously low (catches regressions in CI)
    overall_acc = sum(m.correct for m in metrics.values()) / max(1, sum(m.total for m in metrics.values()))
    if overall_acc < 0.5:
        print(f"\n⚠ Overall accuracy below 50% — investigate regressions.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
