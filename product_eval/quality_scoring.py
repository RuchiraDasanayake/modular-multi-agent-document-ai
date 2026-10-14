"""Post-seal quality240 scoring assembly. No inference, OCR, or reference repair."""

from __future__ import annotations

import argparse
import gzip
import json
import platform
from collections import Counter
from pathlib import Path

from product_eval import quality_scoring_verification as verification
from product_eval.contracts import load_jsonl
from product_eval.datasets import vrdu
from product_eval.final_gate_freeze import digest_file, write_new, write_new_bytes
from product_eval.linked_rows import linked_row_counts
from product_eval.paired_uncertainty import PairedCount, stratified_paired_recall
from product_eval.scoped_assessment import assess_records, pages_sha256
from product_eval.scorer import _typed_equal


def load_references(sources: dict, vrdu_root: Path, cord_gold: Path, output: Path) -> tuple[dict, dict]:
    """Called only after the durable prediction-verification receipt is written."""
    verification.require((output / "verified-before-labels.json").is_file(), "Verification receipt required before labels")
    paths = [cord_gold]
    for family in ("registration-form", "ad-buy-form"):
        paths += [vrdu_root / family / "main" / name for name in ("meta.json", "dataset.jsonl.gz")]
    before = {str(path.resolve()): digest_file(path) for path in paths}
    write_new(output / "reference-inputs.json", {"sha256": before, "opened_after_prediction_verification": True})
    gold, stats = {}, {}
    for family in ("registration-form", "ad-buy-form"):
        selected = {Path(row["source_path"]).name: doc_id for doc_id, row in sources.items() if row["family"] == family}
        verification.require(len(selected) == sum(row["family"] == family for row in sources.values()),
                             "Ambiguous creator filename")
        matchers, line_items = vrdu._load_meta(vrdu_root, family)
        seen, found, counts = set(), set(), Counter()
        with gzip.open(vrdu_root / family / "main" / "dataset.jsonl.gz", "rt", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                name = record["filename"]
                verification.require(isinstance(name, str) and Path(name).name == name and name not in seen,
                                     "Invalid or duplicate creator filename")
                seen.add(name)
                if name in selected:
                    verification.require(record["file_path"] == f"./pdfs/{name}", "Creator PDF path differs")
                    doc_id = selected[name]
                    gold[doc_id], item_stats = vrdu._gold_record(record, doc_id, matchers, line_items)
                    found.add(name)
                    counts.update(item_stats)
        verification.require(found == set(selected), "Selected original lacks creator reference; no exclusions permitted")
        stats[family] = dict(counts)
    cord = load_jsonl(cord_gold, kind="gold")
    receipt_ids = {key for key, row in sources.items() if row["family"] == "receipt"}
    verification.require(receipt_ids <= set(cord), "CORD references lack selected originals; no exclusions permitted")
    gold.update({key: cord[key] for key in receipt_ids})
    stats["receipt"] = {"reference_documents_total": len(cord), "reference_documents_selected": len(receipt_ids),
                        "reference_documents_unused": len(cord) - len(receipt_ids)}
    verification.require(set(gold) == set(sources), "Every frozen source needs its full reference")
    verification.require(before == {str(path.resolve()): digest_file(path) for path in paths}, "Reference inputs changed")
    raw = b"".join((json.dumps(gold[key], ensure_ascii=False, allow_nan=False) + "\n").encode() for key in sorted(gold))
    converted_sha = write_new_bytes(output / "creator-derived-gold.jsonl", raw)
    receipt = {"inputs_sha256": before, "converted_gold_sha256": converted_sha, "documents": len(gold),
               "converter_stats": stats, "reference_repairs": [], "independent_visual_adjudication": False}
    write_new(output / "reference-conversion.json", receipt)
    return gold, receipt


def _counts(matched=0, reference=0) -> dict:
    return {"matched": matched, "reference": reference, "recall": matched / reference if reference else None}


def _sum_counts(rows: list[dict], name: str) -> dict:
    return _counts(sum(row[name]["matched"] for row in rows), sum(row[name]["reference"] for row in rows))


def _usage(items: list[dict]) -> dict:
    attempts = [attempt for item in items for attempt in item["attempts"]]
    result = {"request_begun_attempts": len(attempts), "originals_with_attempts": sum(bool(item["attempts"]) for item in items),
              "uncertain_attempts": sum(row["state"] != "replied" for row in attempts),
              "valid_strict_replies": sum(item["valid_strict_replies"] for item in items),
              "request_kind_counts": dict(Counter(kind for item in items for kind in item["request_kinds"])),
              "actual_source_route_counts": dict(Counter(
                  "visual" if "visual" in item["request_kinds"] else "text" if item["request_kinds"] else "unexecuted"
                  for item in items)),
              "source_states": dict(Counter(item["state"] for item in items)),
              "reason_counts": dict(Counter(item["reason"] for item in items)),
              "finish_reason_counts": dict(Counter(row["finish_reason"] or "unknown" for row in attempts)),
              "usd_cost": None, "true_exact_document_accuracy": None, "cost_per_truly_correct_document": None}
    for key in ("prompt_tokens", "completion_tokens", "sdk_attempts", "latency_ms"):
        result[f"known_{key}"] = sum(row[key] for row in attempts if row[key] is not None)
        result[f"attempts_with_unknown_{key}"] = sum(row[key] is None for row in attempts)
    result["known_product_duration_ms"] = sum(item["duration_ms"] for item in items if item["duration_ms"] is not None)
    result["originals_without_duration"] = sum(item["duration_ms"] is None for item in items)
    return result


def _operational(item: dict) -> dict:
    metrics = item["metrics"] or {}
    trusted = item["state"] == "sealed"
    return {"eligible_prediction": item["eligible"], "state": item["state"], "reason": item["reason"],
            "strict_parsed": bool(trusted and metrics.get("strict_parsed")),
            "valid_full_coverage": item["eligible"],
            "source_coverage": bool(trusted and (metrics.get("full_text_coverage") or metrics.get("full_visual_coverage"))),
            "coverage_scope": metrics.get("coverage_scope"),
            "source_pages": metrics.get("page_count"), "source_text_chars": metrics.get("source_text_chars"),
            "non_null_fields": metrics.get("non_null_fields"), "all_null": metrics.get("all_null"),
            "scalar_conflict": metrics.get("scalar_conflict"), "requires_human_review": metrics.get("requires_human_review"),
            "long_document_coverage": metrics.get("long_document_coverage"),
            "visual_coverage": item["visual_coverage"], "request_kinds": item["request_kinds"],
            "valid_strict_replies": item["valid_strict_replies"]}


def assemble_scores(bundle: dict, gold: dict) -> dict:
    """Use historical metrics unchanged, with explicit failure and annotation scope."""
    sources, arms = bundle["sources"], bundle["arms"]
    verification.require(set(gold) == set(sources), "Every original requires a reference")
    reports, per_source = {}, {key: {"doc_id": key, "family": row["family"]} for key, row in sources.items()}
    for arm, items in arms.items():
        reports[arm] = {}
        for family in sorted({row["family"] for row in sources.values()}):
            ids = sorted(key for key, row in sources.items() if row["family"] == family)
            candidates = {key: (items[key]["candidate"] if items[key]["eligible"] else
                               {**items[key]["candidate"], "extracted_values": []}) for key in ids}
            pages = {key: items[key]["pages"] for key in ids if items[key]["pages"] is not None}
            contexts = {key: {"label_scope": "positive_only" if family == "receipt" else "target_fields",
                              "gold_pages_sha256": pages_sha256(gold[key]["pages"]),
                              "candidate_pages_sha256": pages_sha256(pages[key]) if key in pages else None} for key in ids}
            scoped = assess_records({key: gold[key] for key in ids}, candidates, contexts, pages)
            scoped_by_id = {row["doc_id"]: row for row in scoped["per_document"]}
            rows, outcomes = [], []
            for key in ids:
                expected = {field["field_id"]: field for field in gold[key]["gold_values"]}
                target_schema = {field["field_id"]: field for field in gold[key]["gold_schema"]}
                predicted = {field["field_id"]: field for field in candidates[key]["extracted_values"]}
                candidate_schema = {field["field_id"]: field for field in candidates[key]["proposed_schema"]}
                types, nulls, incompatible = {}, 0, 0
                for field_id, value in expected.items():
                    if target_schema[field_id]["type"] == "array[object]":
                        continue
                    if value["value"] is None:
                        nulls += 1
                        continue
                    actual = predicted.get(field_id, {})
                    matched = int(_typed_equal(value["value"], actual.get("value")))
                    kind = type(value["value"]).__name__
                    types.setdefault(kind, Counter()).update(matched=matched, reference=1)
                    mismatch = kind == "list" and candidate_schema.get(field_id, {}).get("type") != "array[string]"
                    incompatible += mismatch
                    outcomes.append({"doc_id": key, "field_id": field_id, "matched": bool(matched),
                                     "reference_value_type": kind, "candidate_value_type": type(actual.get("value")).__name__,
                                     "ordered_list_schema_incompatible": mismatch, "candidate_status": actual.get("status")})
                linked = linked_row_counts(target_schema, expected, candidate_schema, predicted)
                cell = linked["proposed_cells"]
                ordered_cells = {**_counts(cell["tp"], cell["tp"] + cell["fn"]),
                                 "predicted": cell["tp"] + cell["fp"], "unmatched_predictions": cell["fp"],
                                 "false_positive": None if family == "receipt" else cell["fp"],
                                 "interpretation": "ordinal diagnostic; unmatched positive-only predictions are unassessed"}
                scalar = _counts(sum(x["matched"] for x in types.values()), sum(x["reference"] for x in types.values()))
                row = {"doc_id": key, "proposed_scalar_positive": scalar,
                       "scalar_strings": _counts(**dict(types.get("str", Counter(matched=0, reference=0)))),
                       "historical_ordered_lists": _counts(**dict(types.get("list", Counter(matched=0, reference=0)))),
                       "scalar_reference_types": {name: _counts(**dict(counts)) for name, counts in types.items()},
                       "null_scalar_reference_targets": nulls, "ordered_list_schema_incompatibilities": incompatible,
                       "accepted_scalar_values": scoped_by_id[key]["accepted_scalar_values"],
                       "proposed_annotated_rows": scoped_by_id[key]["proposed_annotated_rows"],
                       "accepted_annotated_rows": scoped_by_id[key]["accepted_annotated_rows"],
                       "ordinal_proposed_cells": ordered_cells, "operational": _operational(items[key])}
                row["all_assessed_positive_targets_match"] = bool(items[key]["eligible"]
                    and scalar["reference"] + row["proposed_annotated_rows"]["reference"] > 0
                    and scalar["matched"] == scalar["reference"]
                    and row["proposed_annotated_rows"]["matched"] == row["proposed_annotated_rows"]["reference"])
                rows.append(row)
                per_source[key][arm] = row
            reports[arm][family] = {"documents": len(ids), "label_scope": contexts[ids[0]]["label_scope"],
                **{name: _sum_counts(rows, name) for name in (
                    "proposed_scalar_positive", "scalar_strings", "historical_ordered_lists", "ordinal_proposed_cells")},
                **{name: scoped[name] for name in ("accepted_scalar_values", "proposed_annotated_rows", "accepted_annotated_rows", "evidence", "unassessed")},
                "null_scalar_reference_targets": sum(row["null_scalar_reference_targets"] for row in rows),
                "ordered_list_schema_incompatibilities": sum(row["ordered_list_schema_incompatibilities"] for row in rows),
                "operational_usage": _usage([items[key] for key in ids]), "scope_aware": scoped,
                "per_document": rows, "scalar_field_outcomes": outcomes}
    families = {key: row["family"] for key, row in sources.items()}
    uncertainty = {}
    for metric in ("proposed_scalar_positive", "scalar_strings", "historical_ordered_lists",
                   "accepted_scalar_values", "proposed_annotated_rows", "accepted_annotated_rows", "ordinal_proposed_cells"):
        counts = []
        for key, pair in per_source.items():
            text, candidate = pair["text"][metric], pair["candidate"][metric]
            verification.require(text["reference"] == candidate["reference"], "Paired reference denominator differs")
            counts.append(PairedCount(key, text["reference"], text["matched"], candidate["matched"]))
        macro = (["ad-buy-form", "receipt"] if "rows" in metric or "cells" in metric else
                 ["registration-form", "ad-buy-form", "receipt"])
        uncertainty[metric] = stratified_paired_recall(counts, families, macro_families=macro)
    for metric in ("strict_parsed", "valid_full_coverage", "source_coverage"):
        counts = [PairedCount(key, 1, int(pair["text"]["operational"][metric]), int(pair["candidate"]["operational"][metric]))
                  for key, pair in per_source.items()]
        result = stratified_paired_recall(counts, families, macro_families=["registration-form", "ad-buy-form", "receipt"])
        result["discordance"] = dict(Counter(
            "both" if row.text_matched and row.candidate_matched else "text_only" if row.text_matched else
            "candidate_only" if row.candidate_matched else "neither" for row in counts))
        uncertainty[metric] = result
    return {"families": reports, "paired_sources": [per_source[key] for key in sorted(per_source)],
            "paired_uncertainty": uncertainty, "all_sources_retained": True, "usd_cost": None,
            "execution_amendments": {"transport": bundle.get("transport_amendment"),
                                     "http408_stop_resolutions": bundle.get("http408_execution_resolutions", [])},
            "human_release_measured": False,
            "accepted_status_interpretation": "Inherited accepted_* metrics refer to machine field status; no human review or release was measured",
            "whole_document_visual_truth_established": False, "quality_threshold_release_pass": None,
            "interpretation": "Creator-derived agreement on a source-only split; comparative research validation, not release certification"}


def run_analysis(run: Path, seal_sha256: str, output: Path, *, vrdu_root: Path, cord_gold: Path,
                 transport_amendment_sha256: str | None = None,
                 http408_resolution_sha256: list[str] | tuple[str, ...] = ()) -> dict:
    verification.require(not output.exists() and not output.resolve().is_relative_to(run.resolve()), "New external analysis directory required")
    bundle = verification.verify_campaign(run, seal_sha256, transport_amendment_sha256=transport_amendment_sha256,
                                         http408_resolution_sha256=http408_resolution_sha256)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "verified-before-labels.json", bundle["receipt"])
    gold, reference_receipt = load_references(bundle["sources"], vrdu_root, cord_gold, output)
    result = assemble_scores(bundle, gold)
    # Reject changes during analysis; never bless scores over moving inputs.
    verification.verify_files(run.resolve(), seal_sha256)
    verification.quality.verify_sources(list(bundle["sources"].values()))
    verification.require(reference_receipt["inputs_sha256"] == {
        path: digest_file(Path(path)) for path in reference_receipt["inputs_sha256"]}, "References changed during scoring")
    write_new(output / "quality-results.json", result)
    code_root = Path(__file__).resolve().parents[1]
    receipt = {**bundle["receipt"], "reference_conversion": reference_receipt,
               "analysis_modules_sha256": {name: digest_file(code_root / "product_eval" / name) for name in (
                   "quality_scoring.py", "quality_scoring_verification.py", "quality_http408_resolution.py", "paired_uncertainty.py")},
               "python_version": platform.python_version(), "files": {path.name: digest_file(path) for path in sorted(output.iterdir())},
               "no_inference_or_ocr": True, "no_reference_repairs": True}
    sha = write_new(output / "scoring-receipt.json", receipt)
    return {"scoring_receipt_sha256": sha, "selected_originals": len(bundle["sources"]), "api_cost_usd": None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "output", "vrdu-root", "cord-gold"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--prediction-seal-sha256", required=True)
    parser.add_argument("--transport-amendment-sha256")
    parser.add_argument("--http408-resolution-sha256", action="append", default=[])
    args = parser.parse_args()
    result = run_analysis(args.run, args.prediction_seal_sha256, args.output, vrdu_root=args.vrdu_root, cord_gold=args.cord_gold,
                          transport_amendment_sha256=args.transport_amendment_sha256,
                          http408_resolution_sha256=args.http408_resolution_sha256)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
