"""Run the endpoint amendment while importing the original frozen product."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "resume"))
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--stop-sha256")
    parser.add_argument("--access-receipt", type=Path)
    parser.add_argument("--amendment-sha256")
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--batches", type=int, default=1)
    args = parser.parse_args()
    sys.path.insert(0, str(args.frozen_root.resolve(strict=True)))
    path = Path(__file__).resolve().parents[1] / "product_eval" / "quality_transport.py"
    spec = importlib.util.spec_from_file_location("quality_transport_amendment", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if args.action == "prepare":
        if not args.stop_sha256 or not args.access_receipt:
            parser.error("prepare requires --stop-sha256 and --access-receipt")
        sha = module.prepare(args.output, args.protocol_sha256,
                             stop_sha=args.stop_sha256, access_receipt=args.access_receipt)
        print(json.dumps({"amendment_sha256": sha, "model_calls": 0, "labels_opened": False}))
        return
    if not args.amendment_sha256 or not args.api_key_file:
        parser.error("resume requires --amendment-sha256 and --api-key-file")
    key = args.api_key_file.read_text(encoding="utf-8").strip()
    if not key.startswith("ibp_") or len(key) < 32 or any(char.isspace() for char in key):
        parser.error("A plain project API key file is required")
    name = "DOCAI_QUALITY_PROJECT_KEY"
    previous = os.environ.get(name)
    os.environ[name] = key
    try:
        result = module.run(args.output, args.protocol_sha256, args.amendment_sha256,
                            api_key_env=name, batches=args.batches, acknowledge=args.stop_sha256)
        report = result.get("summary", result)
        keys = ("source_states", "request_begun_attempts", "uncertain_attempts",
                "valid_full_coverage_originals", "known_tokens", "stop_reason")
        print(json.dumps({"prediction_seal_sha256": result.get("prediction_seal_sha256"),
            "stop_receipt_sha256": report.get("stop_receipt_sha256"),
            "arms": {arm: {key: value.get(key) for key in keys} for arm, value in report["arms"].items()},
            "labels_opened": False, "usd_cost": None}, indent=2))
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


if __name__ == "__main__":
    main()
