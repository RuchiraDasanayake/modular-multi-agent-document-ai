"""Opt-in annotation-aware assessment; historical v1 scores remain unchanged."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, deque
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError, load_jsonl, validate_record
from product_eval.scorer import _has_complete_evidence, _typed_equal, _valid_evidence

LABEL_SCOPES = {"complete_document", "target_fields", "positive_only"}
METRICS = ("schema", "accepted_scalar_values", "proposed_annotated_rows", "accepted_annotated_rows")


def pages_sha256(pages: list[dict[str, Any]]) -> str:
    """Identify exact numbered text, independent of page-list order and JSON spacing."""
    if not isinstance(pages, list):
        raise ContractError("pages must be an array")
    seen = set()
    normalized = []
    for page in pages:
        if (not isinstance(page, dict) or type(page.get("page")) is not int
                or page["page"] < 1 or page["page"] in seen or not isinstance(page.get("text"), str)):
            raise ContractError("pages require unique positive page numbers and text")
        seen.add(page["page"])
        normalized.append({"page": page["page"], "text": page["text"]})
    raw = json.dumps(sorted(normalized, key=lambda p: p["page"]), ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _rows(schema: dict, values: dict, included: set[str], *, accepted: bool) -> list[dict[str, str]]:
    grouped: dict[tuple[str | None, int], dict[str, str]] = {}
    for field_id in included:
        record = values.get(field_id, {})
        if accepted and record.get("status") != "accepted":
            continue
        entries = record.get("value")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or type(entry.get("row")) is not int:
                continue
            if accepted and entry.get("status", record.get("status")) != "accepted":
                continue
            key = (schema.get(field_id, {}).get("group"), entry["row"])
            grouped.setdefault(key, {})[field_id] = entry["value"]
    return list(grouped.values())


def _match_rows(reference: list[dict], predicted: list[dict], *, partial: bool) -> int:
    if not partial:
        # Counters preserve duplicate rows; every prediction can earn at most one match.
        gold = Counter(tuple(sorted(row.items())) for row in reference)
        actual = Counter(tuple(sorted(row.items())) for row in predicted)
        return sum((gold & actual).values())
    # Sparse gold can omit cells. Maximum bipartite matching avoids a greedy
    # sparse row consuming the sole prediction that supports a more specific row.
    edges = [[j for j, pred in enumerate(predicted) if row.items() <= pred.items()] for row in reference]
    owner: dict[int, int] = {}
    for start in range(len(reference)):
        queue = deque([start])
        visited_gold = {start}
        predecessors: dict[int, int] = {}
        free = None
        while queue and free is None:
            gold_index = queue.popleft()
            for candidate_index in edges[gold_index]:
                if candidate_index in predecessors:
                    continue
                predecessors[candidate_index] = gold_index
                if candidate_index not in owner:
                    free = candidate_index
                    break
                previous = owner[candidate_index]
                if previous not in visited_gold:
                    visited_gold.add(previous)
                    queue.append(previous)
        if free is not None:
            reverse = {gold_index: candidate_index for candidate_index, gold_index in owner.items()}
            while True:
                gold_index = predecessors[free]
                owner[free] = gold_index
                if gold_index == start:
                    break
                free = reverse[gold_index]
    return len(owner)


def _metric(counts: Counter, *, partial: bool) -> dict:
    matched, reference, predicted = (counts[key] for key in ("matched", "reference", "predicted"))
    return {
        "matched": matched, "reference": reference, "predicted_in_scope": predicted,
        "missed_reference": reference - matched,
        "unmatched_predictions": predicted - matched,
        "false_positive": None if partial else predicted - matched,
        "precision": matched / predicted if predicted and not partial else None,
        "recall": matched / reference if reference else None,
        "f1": 2 * matched / (predicted + reference) if predicted + reference and not partial else None,
    }


def _linked_ids(schema: dict, values: dict) -> set[str]:
    return {key for key, value in schema.items() if value["type"] == "array[object]"} | {
        key for key, value in values.items() if isinstance(value.get("value"), list)
        and value["value"] and all(isinstance(entry, dict) and "row" in entry for entry in value["value"])
    }


def assess_records(gold: dict[str, dict], candidates: dict[str, dict], contexts: dict[str, dict],
                   candidate_pages: dict[str, list[dict]] | None = None) -> dict:
    """Assess declared annotation scope and exact evidence coordinate compatibility.

    Contexts are evaluator-owned, fixed before inspecting outputs. Candidate pages
    must come from source-verified product receipts; hashing here proves text
    compatibility, not their authenticity against original files.
    """
    candidate_pages = {} if candidate_pages is None else candidate_pages
    if not all(isinstance(value, dict) for value in (gold, candidates, contexts, candidate_pages)):
        raise ContractError("gold, candidates, contexts and candidate pages must be document mappings")
    if not gold or set(contexts) != set(gold):
        raise ContractError("contexts must cover every gold document exactly once")
    if set(candidates) - set(gold) or set(candidate_pages) - set(gold):
        raise ContractError("candidate or candidate pages contain unknown documents")
    for kind, records in (("gold", gold), ("candidate", candidates)):
        for doc_id, record in records.items():
            validate_record(record, kind=kind)
            if record["doc_id"] != doc_id:
                raise ContractError("document mapping key disagrees with doc_id")
    totals: dict[str, Counter] = {name: Counter() for name in (*METRICS, "unassessed", "evidence")}
    scope_counts = Counter()
    documents = []
    for doc_id, reference in sorted(gold.items()):
        context = contexts[doc_id]
        if not isinstance(context, dict) or context.get("label_scope") not in LABEL_SCOPES:
            raise ContractError("every context requires an explicit label_scope")
        scope = context["label_scope"]
        scope_counts[scope] += 1
        if context.get("gold_pages_sha256") != pages_sha256(reference["pages"]):
            raise ContractError("gold text identity differs from context")
        actual_pages = candidate_pages.get(doc_id)
        actual_hash = pages_sha256(actual_pages) if actual_pages is not None else None
        if context.get("candidate_pages_sha256") != actual_hash:
            raise ContractError("candidate text identity differs from context")
        compatibility = ("unknown" if actual_hash is None else
                         "compatible" if actual_hash == context["gold_pages_sha256"] else "incompatible")
        candidate = candidates.get(doc_id, {})
        gold_schema = {f["field_id"]: f for f in reference["gold_schema"]}
        gold_values = {f["field_id"]: f for f in reference["gold_values"]}
        if scope == "positive_only" and any(f["value"] is None for f in gold_values.values()):
            raise ContractError("positive_only gold cannot assert absent null values")
        schema = {f["field_id"]: f for f in candidate.get("proposed_schema", [])}
        values = {f["field_id"]: f for f in candidate.get("extracted_values", [])}
        extra_ids = (schema.keys() | values.keys()) - gold_schema.keys()
        excluded = extra_ids if scope != "complete_document" else set()
        unassessed = Counter({"schema_fields": len(schema.keys() & excluded),
                              "accepted_fields": sum(values.get(key, {}).get("status") == "accepted" for key in excluded)})
        doc_metrics: dict[str, Counter] = {
            "schema": Counter(matched=len(schema.keys() & gold_schema.keys()), reference=len(gold_schema),
                              predicted=len(schema.keys() - excluded))}
        gold_linked = _linked_ids(gold_schema, gold_values)
        candidate_linked = _linked_ids(schema, values)
        scalar_gold = gold_schema.keys() - gold_linked
        scalar_predicted = values.keys() - excluded - gold_linked - (candidate_linked - gold_schema.keys())
        scalar_matches = sum(values.get(key, {}).get("status") == "accepted"
                             and gold_values[key]["value"] is not None
                             and _typed_equal(gold_values[key]["value"], values[key].get("value"))
                             for key in scalar_gold)
        doc_metrics["accepted_scalar_values"] = Counter(
            matched=scalar_matches, reference=sum(gold_values[key]["value"] is not None for key in scalar_gold),
            predicted=sum(values[key]["status"] == "accepted" for key in scalar_predicted))
        gold_rows = _rows(gold_schema, gold_values, gold_linked, accepted=False)
        for name, accepted in (("proposed_annotated_rows", False), ("accepted_annotated_rows", True)):
            rows = _rows(schema, values, candidate_linked - excluded, accepted=accepted)
            doc_metrics[name] = Counter(matched=_match_rows(gold_rows, rows, partial=scope == "positive_only"),
                                        reference=len(gold_rows), predicted=len(rows))
        evidence = Counter()
        field_outcomes = []
        page_map = {page["page"]: page["text"] for page in actual_pages or []}
        gold_page_map = {page["page"]: page["text"] for page in reference["pages"]}
        for field_id, expected in gold_values.items():
            predicted = values.get(field_id, {})
            if predicted.get("status") != "accepted" or expected.get("evidence") is None:
                continue
            evidence["accepted_with_gold_span"] += 1
            evidence["coordinates_" + compatibility] += 1
            quoted = predicted.get("evidence")
            complete = _has_complete_evidence(quoted)
            evidence["complete_references"] += complete
            authentic = None
            if actual_pages is not None:
                evidence["quote_evaluable"] += 1
                authentic = bool(complete and quoted["page"] in page_map
                                 and quoted["end"] <= len(page_map[quoted["page"]])
                                 and page_map[quoted["page"]][quoted["start"]:quoted["end"]] == quoted["quote"])
                evidence["authentic_quotes"] += authentic
            supported = None
            if compatibility == "compatible":
                supported = _valid_evidence(quoted, expected["evidence"], gold_page_map,
                                            value_matches=_typed_equal(expected["value"], predicted.get("value")))
                evidence["supported_exact_values"] += supported
            field_outcomes.append({"field_id": field_id, "quote_authentic": authentic,
                                   "value_and_span_supported": supported,
                                   "coordinate_compatibility": compatibility})
        for name, counts in doc_metrics.items():
            totals[name].update(counts)
        totals["unassessed"].update(unassessed)
        totals["evidence"].update(evidence)
        documents.append({"doc_id": doc_id, "label_scope": scope, "candidate_missing": not candidate,
                          "unassessed_extra_field_ids": sorted(excluded), "unassessed": dict(unassessed),
                          "coordinate_compatibility": compatibility, "evidence_fields": field_outcomes,
                          **{name: _metric(counts, partial=scope == "positive_only") for name, counts in doc_metrics.items()}})
    evidence = totals["evidence"]
    return {
        "metric_profile": "scope_aware_v1", "historical_scorer_unchanged": True,
        "documents": len(gold), "missing_candidates": len(gold.keys() - candidates.keys()),
        "label_scope_counts": dict(scope_counts),
        "row_matching": "One-to-one within whole row records; order independent; duplicate multiplicity preserved. "
                        "Positive-only rows require all annotated cells, not unannotated row completeness.",
        **{name: _metric(totals[name], partial=bool(scope_counts["positive_only"])) for name in METRICS},
        "unassessed": dict(totals["unassessed"]),
        "evidence": {**{name: evidence[name] for name in (
            "accepted_with_gold_span", "complete_references", "coordinates_compatible", "coordinates_incompatible",
            "coordinates_unknown", "quote_evaluable", "authentic_quotes", "supported_exact_values")},
            "quote_authenticity_rate": evidence["authentic_quotes"] / evidence["quote_evaluable"] if evidence["quote_evaluable"] else None,
            "support_validity_rate": evidence["supported_exact_values"] / evidence["coordinates_compatible"] if evidence["coordinates_compatible"] else None},
        "per_document": documents,
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_number(value: str) -> None:
    raise ContractError(f"non-finite JSON number: {value}")


def _read_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_number)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--contexts", type=Path, required=True, help="Evaluator-owned document ID to scope/text hashes JSON")
    parser.add_argument("--candidate-pages", type=Path, help="Document ID to source-verified numbered text pages JSON")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    inputs = {name: path for name, path in (
        ("gold", args.gold), ("candidate", args.candidate), ("contexts", args.contexts),
        ("candidate_pages", args.candidate_pages)) if path is not None}
    try:
        before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in inputs.items()}
        contexts = _read_manifest(args.contexts)
        pages = _read_manifest(args.candidate_pages) if args.candidate_pages else None
        report = assess_records(load_jsonl(args.gold, kind="gold"), load_jsonl(args.candidate, kind="candidate"), contexts, pages)
        after = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in inputs.items()}
        if before != after:
            raise ContractError("assessment inputs changed during scoring")
        report["input_sha256"] = before
        with args.report.open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
            output.write("\n")
    except (ContractError, OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
