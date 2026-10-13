"""Verify a completed product run and its distinct-source count."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from product_eval.contracts import ContractError
from product_eval.execution import verify_runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", type=Path, nargs="+")
    parser.add_argument("--min-unique", type=int, default=2000)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.min_unique < 0:
        parser.error("--min-unique must be non-negative")
    try:
        report = verify_runs(args.run_dirs, min_unique=args.min_unique)
    except (ContractError, OSError, ValueError) as exc:
        parser.error(str(exc))
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
