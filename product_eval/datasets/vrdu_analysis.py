"""Break down unchanged product_eval v1 scores by frozen VRDU family."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError, load_jsonl
from product_eval.execution import verify_runs
from product_eval.scorer import score_records


class AnalysisError(ValueError):
    """Cohort, labels, candidates, or supplied scorer report do not join safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cohort_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    source_hashes: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AnalysisError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise AnalysisError(f"{path}:{line_number}: expected object")
            doc_id = row.get("doc_id")
            family = row.get("family")
            source_sha256 = row.get("source_sha256")
            if not isinstance(doc_id, str) or not doc_id or doc_id in rows:
                raise AnalysisError(f"{path}:{line_number}: invalid or duplicate doc_id")
            if not isinstance(family, str) or not family:
                raise AnalysisError(f"{path}:{line_number}: missing family")
            if not isinstance(source_sha256, str) or len(source_sha256) != 64:
                raise AnalysisError(f"{path}:{line_number}: invalid source_sha256")
            try:
                int(source_sha256, 16)
            except ValueError as exc:
                raise AnalysisError(f"{path}:{line_number}: invalid source_sha256") from exc
            if source_sha256 in source_hashes:
                raise AnalysisError(f"{path}:{line_number}: duplicate raw source SHA256")
            rows[doc_id] = row
            source_hashes.add(source_sha256)
    if not rows:
        raise AnalysisError(f"{path}: empty cohort")
    return rows


def _load_candidates(paths: list[Path]) -> dict[str, dict[str, Any]]:
    if not paths:
        raise AnalysisError("At least one candidate JSONL is required")
    candidates: dict[str, dict[str, Any]] = {}
    for path in paths:
        records = load_jsonl(path, kind="candidate")
        duplicate = set(candidates) & set(records)
        if duplicate:
            raise AnalysisError(f"Duplicate candidate doc_id across shards: {sorted(duplicate)[:5]}")
        candidates.update(records)
    return candidates


def _slim_score(score: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in score.items() if key not in {"per_document", "per_field"}}


def _outcomes(score: dict[str, Any], gold: dict[str, dict[str, Any]]) -> dict[str, Any]:
    field_rows = score["per_field"]
    document_rows = score["per_document"]
    gold_fields_by_doc = {
        doc_id: {field["field_id"] for field in record["gold_schema"]}
        for doc_id, record in gold.items()
    }
    gold_rows = [row for row in field_rows if row["field_id"] in gold_fields_by_doc[row["doc_id"]]]
    value_outcomes = Counter(row["value_outcome"] for row in gold_rows)
    present_gold_outcomes = {
        "correct_accepted",
        "wrong_accepted",
        "abstained",
        "missing",
    }
    per_gold_field: dict[str, Counter[str]] = defaultdict(Counter)
    for row in gold_rows:
        per_gold_field[row["field_id"]][row["value_outcome"]] += 1
        per_gold_field[row["field_id"]][f"schema_{row['schema_outcome']}"] += 1
    return {
        "document_status": dict(sorted(Counter(row["document_status"] for row in document_rows).items())),
        "schema_outcome": dict(sorted(Counter(row["schema_outcome"] for row in field_rows).items())),
        "value_outcome": dict(sorted(Counter(row["value_outcome"] for row in field_rows).items())),
        "candidate_field_status": dict(sorted(Counter(row["candidate_status"] for row in field_rows).items())),
        "evidence_outcome": dict(sorted(Counter(row["evidence_outcome"] for row in field_rows).items())),
        "present_gold_fields": sum(value_outcomes[key] for key in present_gold_outcomes),
        "abstained_present_gold_fields": value_outcomes["abstained"],
        "missing_present_gold_fields": value_outcomes["missing"],
        "wrong_accepted_present_gold_fields": value_outcomes["wrong_accepted"],
        "per_published_gold_field": {
            name: dict(sorted(counts.items())) for name, counts in sorted(per_gold_field.items())
        },
    }


def _diagnostics(
    score: dict[str, Any],
    gold: dict[str, dict[str, Any]],
    candidates: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    gold_schema = {
        doc_id: {field["field_id"]: field for field in record["gold_schema"]}
        for doc_id, record in gold.items()
    }
    shape_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    missed_gold_ids: Counter[str] = Counter()
    spurious_candidate_ids: Counter[str] = Counter()
    for field in score["per_field"]:
        doc_id = field["doc_id"]
        field_id = field["field_id"]
        expected = gold_schema[doc_id].get(field_id)
        if expected:
            shape_outcomes[expected["type"]][field["value_outcome"]] += 1
            if field["schema_outcome"] == "missed":
                missed_gold_ids[field_id] += 1
        elif field["schema_outcome"] == "spurious":
            spurious_candidate_ids[field_id] += 1

    evidence_text = Counter()
    for doc_id, candidate in candidates.items():
        gold_record = gold[doc_id]
        pages = {page["page"]: page["text"] for page in gold_record["pages"]}
        gold_values = {item["field_id"]: item for item in gold_record["gold_values"]}
        for prediction in candidate["extracted_values"]:
            if prediction["status"] != "accepted":
                continue
            expected = gold_values.get(prediction["field_id"])
            if expected is None or expected.get("evidence") is None:
                continue
            evidence_text["accepted_with_gold_span"] += 1
            evidence = prediction.get("evidence")
            if not isinstance(evidence, dict) or not all(
                type(evidence.get(name)) is int for name in ("page", "start", "end")
            ) or not isinstance(evidence.get("quote"), str):
                evidence_text["candidate_span_incomplete"] += 1
                continue
            page = pages.get(evidence["page"])
            start, end = evidence["start"], evidence["end"]
            if page is None or not 0 <= start < end <= len(page):
                evidence_text["candidate_page_or_range_invalid_against_official_ocr"] += 1
            elif page[start:end] == evidence["quote"]:
                evidence_text["quote_matches_official_ocr_at_candidate_span"] += 1
            else:
                evidence_text["quote_differs_from_official_ocr_at_candidate_span"] += 1
    return {
        "value_outcome_by_published_gold_type": {
            kind: dict(sorted(outcomes.items())) for kind, outcomes in sorted(shape_outcomes.items())
        },
        "missed_published_gold_field_ids": dict(sorted(missed_gold_ids.items())),
        "distinct_spurious_candidate_field_ids": len(spurious_candidate_ids),
        "top_spurious_candidate_field_ids": dict(sorted(spurious_candidate_ids.items(), key=lambda item: (-item[1], item[0]))[:20]),
        "evidence_text_comparison": dict(sorted(evidence_text.items())),
        "notes": [
            "Missed and spurious field IDs may reflect canonicalization gaps; semantic aliases are not inferred.",
            "array[object] is a complete linked-row exact match, not a per-row alignment metric.",
            "A quote differing from official OCR at a candidate span is ambiguous across independent OCR outputs; it is not proof of model grounding failure.",
        ],
    }


def analyze_vrdu(
    cohort_path: str | Path,
    gold_path: str | Path,
    candidate_paths: list[str | Path],
    *,
    full_report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run the existing scorer on exact family subsets, then count its outcomes."""
    cohort_file = Path(cohort_path).resolve()
    gold_file = Path(gold_path).resolve()
    candidate_files = [Path(path).resolve() for path in candidate_paths]
    cohort = _cohort_rows(cohort_file)
    gold = load_jsonl(gold_file, kind="gold")
    if set(gold) != set(cohort):
        raise AnalysisError(
            f"Gold/cohort doc_id mismatch: missing gold={len(set(cohort) - set(gold))}, "
            f"extra gold={len(set(gold) - set(cohort))}"
        )
    candidates = _load_candidates(candidate_files)
    unknown_candidates = set(candidates) - set(cohort)
    if unknown_candidates:
        raise AnalysisError(f"Candidate doc_id outside cohort: {sorted(unknown_candidates)[:5]}")

    overall = score_records(gold, candidates)
    report_file = Path(full_report_path).resolve() if full_report_path is not None else None
    if report_file is not None:
        try:
            supplied_report = json.loads(report_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AnalysisError(f"Cannot read scorer report: {report_file}") from exc
        if supplied_report != overall:
            raise AnalysisError("Supplied product_eval report does not match these gold/candidate inputs")

    families = sorted({row["family"] for row in cohort.values()})
    family_reports: dict[str, dict[str, Any]] = {}
    for family in families:
        ids = {doc_id for doc_id, row in cohort.items() if row["family"] == family}
        family_gold = {doc_id: gold[doc_id] for doc_id in ids}
        family_candidates = {doc_id: record for doc_id, record in candidates.items() if doc_id in ids}
        scored = score_records(family_gold, family_candidates)
        family_reports[family] = {
            "score": _slim_score(scored),
            "outcomes": _outcomes(scored, family_gold),
            "diagnostics": _diagnostics(scored, family_gold, family_candidates),
        }

    return {
        "analysis_version": 1,
        "source_sha256": {
            "cohort": _sha256(cohort_file),
            "gold": _sha256(gold_file),
            "candidates": {str(path): _sha256(path) for path in candidate_files},
            "full_report": _sha256(report_file) if report_file else None,
        },
        "cohort_documents": len(cohort),
        "candidate_documents": len(candidates),
        "overall": {
            "score": _slim_score(overall),
            "outcomes": _outcomes(overall, gold),
            "diagnostics": _diagnostics(overall, gold, candidates),
        },
        "by_family": family_reports,
        "interpretation_limits": [
            "Metrics are product_eval v1 strict exact-value scores on derived VRDU gold, not official VRDU benchmark scores.",
            "VRDU OCR-surface dates, prices and names are not normalized with the creator's match functions.",
            "Gold evidence offsets index VRDU OCR; PDF re-OCR text may differ, so offset-validity requires alignment before causal interpretation.",
            "VRDU has no criticality labels; correct-auto-release and critical-field metrics have no meaningful denominator here.",
        ],
    }


def analyze_vrdu_runs(
    cohort_path: str | Path,
    gold_path: str | Path,
    run_dirs: list[str | Path],
    *,
    full_report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Verify completed source-backed run shards before family scoring."""
    if not run_dirs:
        raise AnalysisError("At least one product run directory is required")
    resolved_runs = [Path(path).resolve() for path in run_dirs]
    cohort = _cohort_rows(Path(cohort_path).resolve())
    verified = verify_runs(resolved_runs, min_unique=len(cohort))
    seen: set[str] = set()
    for run_dir in resolved_runs:
        with (run_dir / "manifest.jsonl").open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                receipt = json.loads(line)
                doc_id = receipt["doc_id"]
                if doc_id not in cohort or receipt["source_sha256"] != cohort[doc_id]["source_sha256"]:
                    raise AnalysisError(f"Run source does not match frozen VRDU cohort: {doc_id}")
                seen.add(doc_id)
    if seen != set(cohort):
        raise AnalysisError(f"Run/cohort coverage differs: missing={len(set(cohort) - seen)}")
    result = analyze_vrdu(
        cohort_path,
        gold_path,
        [run_dir / "candidates.jsonl" for run_dir in resolved_runs],
        full_report_path=full_report_path,
    )
    result["run_verification"] = verified
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, type=Path, help="Frozen VRDU cohort.jsonl")
    parser.add_argument("--gold", required=True, type=Path, help="Derived VRDU gold.jsonl")
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--candidate", action="append", type=Path, help="One candidate JSONL shard; repeat as needed")
    sources.add_argument("--run-dir", action="append", type=Path, help="One completed product run directory; repeat as needed")
    parser.add_argument("--full-report", type=Path, help="Optional product_eval report to verify against the supplied inputs")
    parser.add_argument("--output", type=Path, help="Write family report here; default: stdout")
    args = parser.parse_args()
    try:
        if args.run_dir:
            result = analyze_vrdu_runs(args.cohort, args.gold, args.run_dir, full_report_path=args.full_report)
        else:
            result = analyze_vrdu(args.cohort, args.gold, args.candidate, full_report_path=args.full_report)
    except (AnalysisError, ContractError, OSError) as exc:
        parser.error(str(exc))
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
