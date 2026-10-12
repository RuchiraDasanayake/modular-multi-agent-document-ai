"""Source-locked, capped public-development ICORE process-auto diagnostic.

The freeze command reads source receipts and existing OCR sidecars only.
The run command is deliberately added after the lock is committed, so model
inference cannot influence document selection or model assignment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError

LOCK_VERSION = 1
LOCK_PATH = Path(__file__).with_name("fixtures") / "icore_real_dev_six_sources.json"
VRDU_TWELVE_LOCK = Path(__file__).with_name("fixtures") / "adr0005_qwen_twelve_sources.json"
GRAPH_LOCK = Path(__file__).with_name("fixtures") / "docling_graph_v1_dev_sources.json"
VRDU_COHORT_SHA256 = "98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90"
VRDU_GOLD_SHA256 = "8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf"
CORD_COHORT_SHA256 = "48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a"
CORD_GOLD_SHA256 = "84a097116eaad75fb66265447d1b831f5a2ffa98792e10e9ad7edb517cb8e318"
MODELS = ("innobot-luna-6", "innobot-sonnet-5")
MAX_REQUESTS = 18
MAX_OUTPUT_TOKENS = 1536
MAX_PROMPT_CHARS = 12000
MAX_PROMPT_UTF8_BYTES = 14000
MAX_REPORTED_TOTAL_TOKENS = 100000
TIMEOUT_SECONDS = 60


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _verified_dataset(path: Path, expected_hash: str) -> list[dict[str, Any]]:
    if not path.is_file() or sha256_file(path) != expected_hash:
        raise ContractError(f"pinned dataset file changed: {path.name}")
    return load_jsonl(path)


def _verify_hash_only(path: Path, expected_hash: str) -> None:
    if not path.is_file() or sha256_file(path) != expected_hash:
        raise ContractError(f"pinned gold file changed: {path.name}")


def selected_sources(vrdu: list[dict[str, Any]], cord: list[dict[str, Any]],
                     reserved_cord: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vrdu_by_id = {item["doc_id"]: item for item in vrdu}
    cord_by_id = {item["doc_id"]: item for item in cord}
    reserved_hashes = {item["source_sha256"] for item in reserved_cord}
    prior_vrdu = json.loads(VRDU_TWELVE_LOCK.read_text(encoding="utf-8"))["sources"]
    prior_graph = json.loads(GRAPH_LOCK.read_text(encoding="utf-8"))["sources"]
    selected: list[dict[str, Any]] = []
    for family in ("registration-form", "ad-buy-form"):
        rows = sorted((item for item in prior_vrdu if item["family"] == family),
                      key=lambda item: item["source_sha256"])[4:6]
        if len(rows) != 2:
            raise ContractError(f"pinned VRDU twelve lacks two source ranks 5-6 for {family}")
        for rank, prior in enumerate(rows, 5):
            source = vrdu_by_id[prior["doc_id"]]
            if source["family"] != family or source["source_sha256"] != prior["source_sha256"]:
                raise ContractError("VRDU source receipts differ from the earlier source-only lock")
            selected.append({"family": family, "selection_rank": rank, "doc_id": source["doc_id"],
                             "source_sha256": source["source_sha256"], "run_id": prior["v5_run_id"],
                             "prior_sidecar_sha256": prior["sidecar_sha256"]})
    receipt_rows = [item for item in prior_graph if item["family"] == "receipt" and item["role"] == "scored"]
    if len(receipt_rows) != 2:
        raise ContractError("Graph development lock lacks two scored CORD sources")
    for rank, prior in enumerate(receipt_rows, 3):
        source = cord_by_id[prior["doc_id"]]
        if (source.get("evaluation_split") != "development"
                or source["source_sha256"] != prior["source_sha256"]
                or source["source_sha256"] in reserved_hashes):
            raise ContractError("CORD source is not in the reserved-disjoint development split")
        selected.append({"family": "receipt", "selection_rank": rank, "doc_id": source["doc_id"],
                         "source_sha256": source["source_sha256"], "run_id": prior["run_id"],
                         "prior_sidecar_sha256": prior["sidecar_sha256"]})
    if len(selected) != 6 or len({item["source_sha256"] for item in selected}) != 6:
        raise ContractError("pilot must select six distinct raw source hashes")
    for item in selected:
        item["model_arms"] = list(MODELS) if item["selection_rank"] in {3, 5} else [MODELS[0]]
    if sum(len(item["model_arms"]) for item in selected) != 9:
        raise ContractError("model assignment must contain nine document-model cells")
    return selected


def freeze_lock(*, vrdu_cohort: Path, vrdu_gold: Path, cord_cohort: Path, cord_gold: Path,
                cord_reserved: Path, runs_root: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    vrdu = _verified_dataset(vrdu_cohort, VRDU_COHORT_SHA256)
    _verify_hash_only(vrdu_gold, VRDU_GOLD_SHA256)
    cord = _verified_dataset(cord_cohort, CORD_COHORT_SHA256)
    _verify_hash_only(cord_gold, CORD_GOLD_SHA256)
    reserved = load_jsonl(cord_reserved)
    if len(cord) != 60 or len(reserved) != 40:
        raise ContractError("CORD split must contain 60 development and 40 reserved receipts")
    by_id = {item["doc_id"]: item for item in vrdu + cord}
    sources = selected_sources(vrdu, cord, reserved)
    for item in sources:
        cohort_row = by_id[item["doc_id"]]
        source = Path(cohort_row["source_path"])
        sidecar_path = runs_root / item["run_id"] / "docs" / item["doc_id"] / "result.json"
        if not source.is_file() or sha256_file(source) != item["source_sha256"]:
            raise ContractError("raw public source differs from the pinned receipt")
        if not sidecar_path.is_file() or sha256_file(sidecar_path) != item["prior_sidecar_sha256"]:
            raise ContractError("completed OCR sidecar differs from the earlier source-only lock")
        if not (runs_root / item["run_id"] / "run.json").is_file():
            raise ContractError("prior OCR run lacks completion marker")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        pages = sidecar.get("pages", [])
        if sidecar.get("source_sha256") != item["source_sha256"] or not pages:
            raise ContractError("prior OCR sidecar does not match the raw source")
        if any(type(page.get("page")) is not int or not isinstance(page.get("text"), str) for page in pages):
            raise ContractError("prior OCR page shape is invalid")
        item["source_size_bytes"] = source.stat().st_size
        item["source_file"] = source.name
        item["ocr_sidecar_sha256"] = item.pop("prior_sidecar_sha256")
        item["ocr_pages_sha256"] = sha256_text(json.dumps(pages, sort_keys=True, ensure_ascii=False))
        item["ocr_page_count"] = len(pages)
        item["ocr_chars"] = sum(len(page["text"]) for page in pages)
    result = {
        "version": LOCK_VERSION,
        "selection": "VRDU ranks 5-6 by raw source SHA in each frozen twelve; two pre-scored, OCR-eligible CORD development sources from the prior Graph lock. Selection precedes ICORE inference and does not read labels.",
        "model_assignment": "Luna 6 all six; Sonnet 5 the lower selected source hash in each family. Same raw input and product process-auto route per model.",
        "dataset_sha256": {"vrdu_cohort": VRDU_COHORT_SHA256, "vrdu_gold": VRDU_GOLD_SHA256,
                           "cord_development_cohort": CORD_COHORT_SHA256, "cord_development_gold": CORD_GOLD_SHA256,
                           "cord_reserved_cohort": sha256_file(cord_reserved)},
        "prior_selection_sha256": {"vrdu_twelve": sha256_file(VRDU_TWELVE_LOCK),
                                   "docling_graph_twelve": sha256_file(GRAPH_LOCK)},
        "call_budget": {"max_attempts": MAX_REQUESTS, "max_output_tokens_per_call": MAX_OUTPUT_TOKENS,
                        "max_prompt_chars": MAX_PROMPT_CHARS, "max_prompt_utf8_bytes": MAX_PROMPT_UTF8_BYTES,
                        "max_reported_total_tokens": MAX_REPORTED_TOTAL_TOKENS,
                        "timeout_seconds": TIMEOUT_SECONDS, "sdk_retries": 0, "concurrency": 1},
        "sources": sources,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true", required=True)
    parser.add_argument("--vrdu-cohort", type=Path, required=True)
    parser.add_argument("--vrdu-gold", type=Path, required=True)
    parser.add_argument("--cord-cohort", type=Path, required=True)
    parser.add_argument("--cord-gold", type=Path, required=True)
    parser.add_argument("--cord-reserved", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=LOCK_PATH)
    args = parser.parse_args()
    result = freeze_lock(vrdu_cohort=args.vrdu_cohort, vrdu_gold=args.vrdu_gold,
                         cord_cohort=args.cord_cohort, cord_gold=args.cord_gold,
                         cord_reserved=args.cord_reserved, runs_root=args.runs_root,
                         output=args.output)
    print(f"Frozen {len(result['sources'])} source hashes before model inference")


if __name__ == "__main__":
    main()
