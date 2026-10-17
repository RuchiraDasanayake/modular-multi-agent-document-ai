"""Predeclare and score a single operational regression only after seal verification.

No inference or annotation repair. Existing typed equality and scoped row matching
are reused; failed and uncertain originals retain their complete denominators.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from product_eval.final_gate_freeze import ROOT, digest_file, read_json, write_new
from product_eval.final_operational_verification import verify_completed
from product_eval.quality_scoring import load_references
from product_eval.quality_scoring_verification import require
from product_eval.scoped_assessment import assess_records, pages_sha256
from product_eval.scorer import _typed_equal

SCORER_FILES = (
    "product_eval/operational_recall.py", "product_eval/scoped_assessment.py",
    "product_eval/scorer.py", "product_eval/contracts.py", "product_eval/quality_scoring.py",
    "product_eval/datasets/vrdu.py", "product_eval/final_operational_verification.py",
    "product_eval/quality_scoring_verification.py", "product_eval/final_model_gate.py",
    "product_eval/final_gate_freeze.py",
)
SCOPES = {"registration-form": "target_fields", "ad-buy-form": "target_fields", "receipt": "positive_only"}
REFERENCE_SHA256 = {
    "cord_gold": "72f07d25d27cc2fc077f3cf19bd47a0b9aecc1d6f6a959b5cd532969c401cb6b",
    "registration-form/main/meta.json": "248e2c1f9a127397f73c20e0b546ba29779a4a66f15acedd06b5d1d507c513da",
    "registration-form/main/dataset.jsonl.gz": "9dd5f711e34861bdf9a98e05415355b522439e8658fcef763ef8d9b6b50cdc49",
    "ad-buy-form/main/meta.json": "312a229850651e982c995533fed5443e2073b2c50d50c32b9e95c0a50fd8911f",
    "ad-buy-form/main/dataset.jsonl.gz": "5fbf579a023e1068433f3115006da109145307cdd3e1b64346b92c959384ef36",
}


def make_plan(cohort: Path) -> dict:
    """Hash code and source inventory only; never read annotations."""
    return _plan(digest_file(cohort))


def _plan(cohort_sha: str) -> dict:
    return {
        "version": 1, "kind": "single_operational_positive_recall",
        "cohort_sha256": cohort_sha, "scorer_sha256": {name: digest_file(ROOT / name) for name in SCORER_FILES},
        "label_scopes": SCOPES,
        "reference_sha256": REFERENCE_SHA256,
        "scalar_metric": "Non-null reference targets matched by unchanged _typed_equal, regardless of proposal status",
        "row_metric": "Unchanged scoped_assessment.proposed_annotated_rows; one-to-one whole annotated rows",
        "failure_policy": "Every invalid, failed or uncertain original receives empty predictions; no exclusions",
        "macro_scalar_families": list(SCOPES), "macro_row_families": ["ad-buy-form", "receipt"],
        "uncertainty": "No inferential interval or significance claim; descriptive reused-cohort regression",
        "reference_mapping": "VRDU creator filename; CORD train exact existing cohort doc_id; no label repair",
        "precision_f1": "Not reported: partial positive references cannot establish full extraction precision/F1",
        "evidence": "Source-coordinate compatibility assessed separately; mismatch is unassessed, not supported",
        "labels_opened": False,
    }


def validate_plan(plan: dict, cohort_sha: str) -> None:
    require(plan == _plan(cohort_sha), "Preregistered recall plan, source inventory or scorer code differs")


def counts(matched: int, reference: int) -> dict:
    return {"matched": matched, "reference": reference, "recall": matched / reference if reference else None}


def verify_reference_bytes(vrdu_root: Path, cord_gold: Path) -> None:
    for name, expected in REFERENCE_SHA256.items():
        require(digest_file(cord_gold if name == "cord_gold" else vrdu_root / name) == expected,
                "Predeclared reference bytes differ; no annotation replacement permitted")


def score_records(sources: dict, gold: dict, candidates: dict, pages: dict, eligible: set[str]) -> dict:
    require(set(gold) == set(sources) and eligible <= set(sources), "Every selected source requires a reference")
    require(set(candidates) <= set(sources) and set(pages) <= set(sources), "Unknown prediction source")
    families = {}
    for family in sorted({row["family"] for row in sources.values()}):
        require(family in SCOPES, "Unknown source family")
        ids = sorted(key for key, row in sources.items() if row["family"] == family)
        predictions = {key: candidates[key] for key in ids if key in eligible and key in candidates}
        # Missing predictions are intentionally represented as absent records:
        # the unchanged scorer still traverses every gold document and row.
        actual_pages = {key: pages[key] for key in ids if key in pages}
        contexts = {key: {"label_scope": SCOPES[family],
                         "gold_pages_sha256": pages_sha256(gold[key]["pages"]),
                         "candidate_pages_sha256": pages_sha256(actual_pages[key]) if key in actual_pages else None}
                    for key in ids}
        scoped = assess_records({key: gold[key] for key in ids}, predictions, contexts, actual_pages)
        scalar_matched = scalar_reference = incompatible = 0
        per_source = []
        row_by_id = {row["doc_id"]: row for row in scoped["per_document"]}
        for key in ids:
            target_schema = {field["field_id"]: field for field in gold[key]["gold_schema"]}
            predicted = {field["field_id"]: field for field in predictions.get(key, {}).get("extracted_values", [])}
            schema = {field["field_id"]: field for field in predictions.get(key, {}).get("proposed_schema", [])}
            matched = reference = mismatch = 0
            for field in gold[key]["gold_values"]:
                field_id, value = field["field_id"], field["value"]
                if target_schema[field_id]["type"] == "array[object]" or value is None:
                    continue
                reference += 1
                matched += int(_typed_equal(value, predicted.get(field_id, {}).get("value")))
                mismatch += int(isinstance(value, list) and schema.get(field_id, {}).get("type") != "array[string]")
            scalar_matched += matched
            scalar_reference += reference
            incompatible += mismatch
            row = row_by_id[key]["proposed_annotated_rows"]
            per_source.append({"doc_id": key, "eligible": key in predictions,
                               "positive_scalar_targets": counts(matched, reference),
                               "annotated_rows": counts(row["matched"], row["reference"]),
                               "ordered_list_schema_incompatibilities": mismatch})
        rows = scoped["proposed_annotated_rows"]
        families[family] = {"documents": len(ids), "eligible_documents": len(predictions),
                            "label_scope": SCOPES[family], "positive_scalar_targets": counts(scalar_matched, scalar_reference),
                            "annotated_rows": counts(rows["matched"], rows["reference"]),
                            "ordered_list_schema_incompatibilities": incompatible,
                            "evidence": scoped["evidence"], "unassessed": scoped["unassessed"],
                            "per_source": per_source}
    def macro(metric, names):
        values = [families[name][metric]["recall"] for name in names if name in families]
        return sum(values) / len(values) if len(values) == len(names) and None not in values else None
    return {"selected_originals": len(sources), "families": families,
            "scalar_equal_family_macro_recall": macro("positive_scalar_targets", list(SCOPES)),
            "row_equal_family_macro_recall": macro("annotated_rows", ["ad-buy-form", "receipt"]),
            "precision": None, "f1": None, "unseen_holdout": False, "human_release_measured": False,
            "interpretation": "Descriptive positive-reference recall on reused operational sources; no full-document correctness claim"}


def run_analysis(run: Path, protocol_sha: str, seal: str, seal_sha: str, output: Path,
                 vrdu_root: Path, cord_gold: Path) -> dict:
    run, output = run.resolve(), output.resolve()
    require(not output.exists() and run not in output.parents and output not in run.parents,
            "Output must be new and outside the campaign")
    protocol_bytes = (run / "protocol.json").read_bytes()
    require(hashlib.sha256(protocol_bytes).hexdigest() == protocol_sha, "Protocol bytes differ from supplied SHA")
    protocol = json.loads(protocol_bytes)
    validate_plan(protocol.get("analysis_plan", {}), protocol["cohort_sha256"])
    # The independently verified final seal is mandatory before any label read.
    verified = verify_completed(run, protocol_sha, seal, seal_sha)
    require(verified["verified_artifact_hashes"].get("protocol.json") == protocol_sha,
            "Verifier protocol receipt differs")
    identity = lambda row: (row["doc_id"], row["source_sha256"], row["family"])
    require([identity(row) for row in protocol["sources"]] ==
            [identity(row) for row in verified["documents"]], "Verifier source inventory differs")
    sources = {row["doc_id"]: row for row in protocol["sources"]}
    output.mkdir(parents=True)
    write_new(output / "verified-before-labels.json", verified)
    candidates, pages, eligible = {}, {}, set()
    for item in verified["documents"]:
        key = item["doc_id"]
        if not item["valid_full_coverage"]:
            continue
        prefix = f"product_runs/model2000_{key}/docs/{key}/result.json"
        require(prefix in verified["verified_artifact_hashes"] and
                digest_file(run / prefix) == verified["verified_artifact_hashes"][prefix], "Prediction changed after verification")
        sidecar = read_json(run / prefix)
        candidates[key], pages[key] = sidecar["candidate"], sidecar["pages"]
        eligible.add(key)
    verify_reference_bytes(vrdu_root, cord_gold)
    gold, reference_receipt = load_references(sources, vrdu_root, cord_gold, output)
    result = score_records(sources, gold, candidates, pages, eligible)
    result.update(protocol_sha256=protocol_sha, seal_sha256=seal_sha, reference_receipt=reference_receipt)
    return {"result_sha256": write_new(output / "positive-recall.json", result), "selected_originals": len(sources)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--cohort", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    score = commands.add_parser("score")
    for flag in ("run", "output", "vrdu-root", "cord-gold"):
        score.add_argument("--" + flag, type=Path, required=True)
    for flag in ("protocol-sha256", "seal", "seal-sha256"):
        score.add_argument("--" + flag, required=True)
    args = parser.parse_args()
    result = ({"plan_sha256": write_new(args.output, make_plan(args.cohort))} if args.command == "plan" else
              run_analysis(args.run, args.protocol_sha256, args.seal, args.seal_sha256, args.output,
                           args.vrdu_root, args.cord_gold))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
