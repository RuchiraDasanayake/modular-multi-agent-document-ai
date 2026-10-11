"""Run the standalone product extraction scorer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from product_eval.contracts import ContractError, load_jsonl
from product_eval.scorer import score_records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True, help="Adjudicated gold JSONL")
    parser.add_argument("--candidate", type=Path, required=True, help="Candidate output JSONL")
    parser.add_argument("--report", type=Path, help="Write JSON report here; default: stdout")
    parser.add_argument("--min-documents", type=int, default=0, help="Minimum unique gold and candidate document IDs")
    args = parser.parse_args()
    if args.min_documents < 0:
        parser.error("--min-documents must be non-negative")
    try:
        gold = load_jsonl(args.gold, kind="gold")
        candidate = load_jsonl(args.candidate, kind="candidate")
        if len(gold) < args.min_documents or len(candidate) < args.min_documents:
            parser.error(
                f"--min-documents requires at least {args.min_documents} unique IDs in both files; "
                f"got gold={len(gold)}, candidate={len(candidate)}"
            )
        report = score_records(
            gold,
            candidate,
        )
    except (ContractError, OSError) as exc:
        parser.error(str(exc))
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
