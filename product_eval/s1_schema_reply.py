"""Fail-closed S1 naming of source-enumerated schema candidates.

This research contract never accepts generated values, row links or source
locators. A model may name and type only candidates enumerated by a separately
verified source graph. All outputs remain pending human review.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

MAX_FIELDS = 24
MAX_REPLY_BYTES = 16_384
FIELD_ID = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
FIELD_TYPES = {"string", "integer", "decimal", "boolean", "date", "array[object]"}
CandidateKind = Literal["scalar", "column"]


class SchemaReplyError(ValueError):
    """Invalid or ungrounded schema reply; fail the entire source call."""


@dataclass(frozen=True)
class CandidateRef:
    candidate_id: str
    kind: CandidateKind
    source_node_ids: tuple[str, ...]
    source_group_id: str | None = None

    def __post_init__(self) -> None:
        if (not re.fullmatch(r"[a-z][a-z0-9_]{2,79}", self.candidate_id)
                or self.kind not in {"scalar", "column"}
                or not self.source_node_ids
                or any(not node_id for node_id in self.source_node_ids)
                or len(set(self.source_node_ids)) != len(self.source_node_ids)):
            raise SchemaReplyError("invalid_enumerated_candidate")
        if self.kind == "column" and not self.source_group_id:
            raise SchemaReplyError("column_requires_source_group")
        if self.kind == "scalar" and self.source_group_id is not None:
            raise SchemaReplyError("scalar_cannot_claim_source_row_group")


def _reject_nonfinite(value: str) -> None:
    raise SchemaReplyError(f"nonfinite_json_constant_{value}")


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SchemaReplyError("duplicate_json_key")
        result[key] = value
    return result


def parse_reply(raw: str, catalog: tuple[CandidateRef, ...]) -> list[dict[str, object]]:
    """Return review-only fields with source-owned group and node references.

    Exactly one reply entry per enumerated candidate prevents a model from
    silently dropping difficult source nodes. An entry may explicitly abstain.
    """
    if not catalog or len(catalog) > MAX_FIELDS:
        raise SchemaReplyError("candidate_budget_or_empty")
    ids = {item.candidate_id for item in catalog}
    if len(ids) != len(catalog):
        raise SchemaReplyError("duplicate_enumerated_candidate")
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_REPLY_BYTES:
        raise SchemaReplyError("reply_size_limit")
    try:
        payload = json.loads(raw, parse_constant=_reject_nonfinite,
                             object_pairs_hook=_pairs_no_duplicates)
    except (TypeError, UnicodeError, ValueError) as exc:
        raise SchemaReplyError("invalid_json") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "fields"}:
        raise SchemaReplyError("invalid_reply_shape")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise SchemaReplyError("invalid_schema_version")
    rows = payload["fields"]
    if not isinstance(rows, list) or len(rows) != len(catalog):
        raise SchemaReplyError("candidate_coverage_mismatch")
    by_id = {item.candidate_id: item for item in catalog}
    seen: set[str] = set()
    used_field_ids: set[str] = set()
    result: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"candidate_id", "field_id", "type", "decision"}:
            raise SchemaReplyError("invalid_field_shape")
        candidate_id = row["candidate_id"]
        if not isinstance(candidate_id, str) or candidate_id not in by_id or candidate_id in seen:
            raise SchemaReplyError("unknown_or_duplicate_candidate")
        seen.add(candidate_id)
        candidate = by_id[candidate_id]
        decision = row["decision"]
        if decision == "abstain":
            if row["field_id"] is not None or row["type"] is not None:
                raise SchemaReplyError("abstention_claims_field")
            continue
        if decision != "propose":
            raise SchemaReplyError("invalid_decision")
        field_id, field_type = row["field_id"], row["type"]
        if (not isinstance(field_id, str) or not FIELD_ID.fullmatch(field_id)
                or "__" in field_id or field_id.endswith("_")
                or field_id in used_field_ids):
            raise SchemaReplyError("invalid_or_duplicate_field_id")
        if not isinstance(field_type, str) or field_type not in FIELD_TYPES or (
            (candidate.kind == "column") != (field_type == "array[object]")
        ):
            raise SchemaReplyError("field_type_mismatch")
        used_field_ids.add(field_id)
        result.append({
            "candidate_id": candidate_id,
            "field_id": field_id,
            "type": field_type,
            "group": candidate.source_group_id,
            "source_node_ids": list(candidate.source_node_ids),
            "status": "needs_review",
            "review_state": "pending",
        })
    if seen != ids:
        raise SchemaReplyError("candidate_coverage_mismatch")
    return result


def response_schema(catalog: tuple[CandidateRef, ...]) -> dict[str, object]:
    """Describe allowed JSON shape for a source-free grammar compatibility probe.

    Caller must still run ``parse_reply``: JSON Schema support and semantic
    constraints vary across model servers.
    """
    ids = [item.candidate_id for item in catalog]
    if not ids or len(ids) != len(set(ids)) or len(ids) > MAX_FIELDS:
        raise SchemaReplyError("candidate_budget_or_empty")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "fields"],
        "properties": {
            "schema_version": {"type": "integer", "enum": [1]},
            "fields": {
                "type": "array", "minItems": len(ids), "maxItems": len(ids),
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["candidate_id", "field_id", "type", "decision"],
                    "properties": {
                        "candidate_id": {"type": "string", "enum": ids},
                        "field_id": {"type": ["string", "null"]},
                        "type": {"type": ["string", "null"]},
                        "decision": {"type": "string", "enum": ["propose", "abstain"]},
                    },
                },
            },
        },
    }
