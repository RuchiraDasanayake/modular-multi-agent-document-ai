"""Frozen, family-independent grouped-leaf scorer for the NuExtract3 follow-on.

This is evaluation code only. It does not repair model output or alter the
original six-source NuExtract3 score.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError
from product_eval.nuextract3_dev_diagnostic import _normalize, _row_multiset, _rows_from_field_values, _typed_equal


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_rule(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        rule = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ContractError(f"invalid grouped-leaf rule: {exc}") from exc
    if not isinstance(rule, dict) or canonical_sha256(rule) != expected_sha256 or rule.get("version") != 1:
        raise ContractError("grouped-leaf rule version or canonical SHA256 differs")
    slots = rule.get("slots")
    if not isinstance(slots, dict) or set(slots) != {
        "description", "quantity", "unit_price", "line_amount", "price_unspecified"
    }:
        raise ContractError("grouped-leaf rule slots differ")
    seen: set[str] = set()
    for aliases in slots.values():
        if not isinstance(aliases, list) or not aliases:
            raise ContractError("grouped-leaf rule alias list is empty")
        for alias in aliases:
            if not isinstance(alias, str) or not alias:
                raise ContractError("grouped-leaf rule alias is invalid")
            normalized = normalize_name(alias)
            if not normalized or normalized in seen:
                raise ContractError(f"grouped-leaf rule alias collision: {alias}")
            seen.add(normalized)
    return rule


def normalize_name(name: str) -> str:
    value = unicodedata.normalize("NFKC", name)
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value).casefold()
    tokens: list[str] = []
    current: list[str] = []
    for char in value:
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return "_".join(tokens)


def _slot(name: str, rule: dict[str, Any]) -> str | None:
    normalized = normalize_name(name)
    if not normalized:
        return None
    for slot, aliases in rule["slots"].items():
        if normalized in aliases:
            return slot
    return f"literal:{normalized}"


def _project_nearest_fields(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Project leaves with the nearest, rather than outermost, repeated parent."""
    models = {model["name"]: model for model in spec["models"]}
    root = spec["root"]
    if root not in models:
        raise ContractError("template projection root is missing")
    result: list[dict[str, Any]] = []

    def walk(model_name: str, path: str, group: str | None, seen: frozenset[str]) -> None:
        if model_name in seen or len(seen) >= 8:
            return
        for field in models[model_name]["fields"]:
            field_path = f"{path}.{field['name']}"
            if field["type"] in models:
                nearest = field_path if field.get("is_list") else group
                walk(field["type"], field_path, nearest, seen | {model_name})
            else:
                result.append({"name": field["name"], "path": field_path,
                               "type": field["type"], "normalizer": field.get("normalizer", "none"),
                               "shape": "linked" if group else "scalar_list" if field.get("is_list") else "scalar",
                               "group": group})

    walk(root, root, None, frozenset())
    return result


def score_grouped_leaf(spec: dict[str, Any] | None, gold_fields: list[dict[str, Any]],
                       rule: dict[str, Any]) -> dict[str, Any]:
    """Match unique leaves; nested aliases are eligible only under a repeated object."""
    predicted = _project_nearest_fields(spec) if spec is not None else []
    predicted_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    gold_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for field in predicted:
        if field["shape"] == "linked" and field["group"]:
            slot = _slot(field["name"], rule)
            if slot is not None:
                predicted_by_key[("linked", slot)].append(field)
        elif field["shape"] != "linked":
            predicted_by_key[("unlinked", field["name"])].append(field)
    for field in gold_fields:
        if field["type"] == "array[object]":
            slot = _slot(field["field_id"], rule)
            if slot is not None:
                gold_by_key[("linked", slot)].append(field)
        else:
            gold_by_key[("unlinked", field["field_id"])].append(field)

    matches: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []
    for key in sorted(set(predicted_by_key) | set(gold_by_key)):
        predictions = predicted_by_key.get(key, [])
        references = gold_by_key.get(key, [])
        if len(predictions) > 1 or len(references) > 1:
            collisions.append({"kind": key[0], "slot": key[1],
                               "predicted_paths": sorted(p["path"] for p in predictions),
                               "reference_ids": sorted(g["field_id"] for g in references)})
            continue
        if len(predictions) == len(references) == 1:
            prediction, reference = predictions[0], references[0]
            expected_shape = ("linked" if reference["type"] == "array[object]" else
                              "scalar_list" if reference["type"] == "array[string]" else "scalar")
            matches.append({"gold_field_id": reference["field_id"], "predicted_name": prediction["name"],
                            "normalized_reference_name": normalize_name(reference["field_id"]),
                            "normalized_predicted_name": normalize_name(prediction["name"]),
                            "predicted_path": prediction["path"], "predicted_group": prediction["group"],
                            "slot": key[1], "gold_type": reference["type"],
                            "predicted_shape": prediction["shape"], "shape_agrees": prediction["shape"] == expected_shape,
                            "predicted_type": prediction["type"]})

    linked_gold = [g for g in gold_fields if g["type"] == "array[object]"]
    explicit_groups = {g.get("row_group", g.get("group")) for g in linked_gold}
    pair_unavailable = None in explicit_groups and len(explicit_groups) > 1
    pairs: list[tuple[str, str]] = []
    if not pair_unavailable:
        by_group: dict[str, list[str]] = defaultdict(list)
        for field in linked_gold:
            by_group[str(field.get("row_group", field.get("group")) or "__implicit_single_group__")].append(field["field_id"])
        pairs = [(a, b) for fields in by_group.values() for a, b in combinations(sorted(fields), 2)]
    matched_by_id = {m["gold_field_id"]: m for m in matches}
    hit_pairs = [(a, b) for a, b in pairs if a in matched_by_id and b in matched_by_id
                 and matched_by_id[a]["predicted_group"] is not None
                 and matched_by_id[a]["predicted_group"] == matched_by_id[b]["predicted_group"]]
    matched_paths = {m["predicted_path"] for m in matches}
    return {
        "gold_fields": len(gold_fields), "matched": len(matches),
        "linked_gold_fields": len(linked_gold),
        "matched_linked_fields": sum(m["gold_type"] == "array[object]" for m in matches),
        "linked_pair_hits": len(hit_pairs),
        "linked_pair_total": None if pair_unavailable else len(pairs),
        "linked_pair_opportunities": len(linked_gold) * (len(linked_gold) - 1) // 2,
        "linked_pair_unavailable": pair_unavailable,
        "hit_pairs": hit_pairs, "matches": matches, "collisions": collisions,
        "shape_hits": sum(m["shape_agrees"] for m in matches),
        "raw_string_type_hits": sum(m["predicted_type"] == "str" for m in matches),
        "unmatched_reference_ids": sorted(g["field_id"] for g in gold_fields if g["field_id"] not in matched_by_id),
        "unmatched_predicted": [{**p, "normalized_name": normalize_name(p["name"]),
                                 "slot": _slot(p["name"], rule) if p["shape"] == "linked" else None}
                                for p in predicted if p["path"] not in matched_paths],
    }


def _get_object_path(root: dict[str, Any], components: list[str]) -> Any:
    value: Any = root
    for component in components:
        if not isinstance(value, dict):
            return None
        value = value.get(component)
    return value


def _group_rows(root: dict[str, Any], components: list[str]) -> list[dict[str, Any]]:
    """Flatten nested declared object arrays in document order to one row set."""
    nodes: list[dict[str, Any]] = [root]
    for position, component in enumerate(components):
        following: list[dict[str, Any]] = []
        for node in nodes:
            value = node.get(component)
            if isinstance(value, dict) and position < len(components) - 1:
                following.append(value)
            elif isinstance(value, list):
                following.extend(item for item in value if isinstance(item, dict))
        nodes = following
    return nodes


def _value_for_match(reply: dict[str, Any], match: dict[str, Any]) -> Any:
    path = match["predicted_path"].split(".")
    if not path or path[0] != "Document":
        return None
    if match["gold_type"] != "array[object]":
        return _get_object_path(reply, path[1:])
    group = match["predicted_group"]
    if not isinstance(group, str):
        return []
    group_parts = group.split(".")
    if path[:len(group_parts)] != group_parts:
        return []
    rows = _group_rows(reply, group_parts[1:])
    suffix = path[len(group_parts):]
    return [{"row": index, "value": value} for index, row in enumerate(rows)
            if isinstance(row, dict) and isinstance(value := _get_object_path(row, suffix), str) and value]


def score_self_template_values(reply: dict[str, Any] | None, gold: dict[str, Any],
                               grouped_score: dict[str, Any]) -> dict[str, Any]:
    """Score values through matched model paths, retaining full-gold row failures."""
    matches = {m["gold_field_id"]: m for m in grouped_score["matches"]}
    schema = gold["gold_schema"]
    expected = {item["field_id"]: item["value"] for item in gold["gold_values"]}
    actual = {field["field_id"]: _value_for_match(reply or {}, matches[field["field_id"]])
              if field["field_id"] in matches else None for field in schema}
    result = Counter()
    for field in schema:
        field_id = field["field_id"]
        if field["type"] == "array[object]":
            continue
        truth, value = expected.get(field_id), actual[field_id]
        bucket = "scalar" if field["type"] == "string" else "scalar_list"
        if truth is not None and truth != []:
            result[f"gold_{bucket}_positive"] += 1
            if _typed_equal(value, truth):
                result[f"exact_{bucket}_positive"] += 1
            elif value is not None and value != []:
                result[f"wrong_nonempty_{bucket}"] += 1
            if isinstance(value, str) and isinstance(truth, str) and _normalize(value) == _normalize(truth):
                result[f"normalized_{bucket}_positive"] += 1
            elif isinstance(value, list) and isinstance(truth, list) and all(
                    isinstance(item, str) for item in value + truth):
                result[f"normalized_{bucket}_positive"] += [
                    _normalize(item) for item in value] == [_normalize(item) for item in truth]
            if isinstance(value, str) and any(value in page["text"] for page in gold["pages"]):
                result[f"ocr_surface_{bucket}"] += 1
        elif value is not None and value != []:
            result[f"predicted_on_gold_null_{bucket}"] += 1

    linked_ids = {field["field_id"] for field in schema if field["type"] == "array[object]"}
    gold_rows = _rows_from_field_values(expected, linked_ids)
    predicted_rows = _rows_from_field_values(actual, linked_ids)
    gold_cells = {(field, index, value) for index, row in gold_rows.items() for field, value in row}
    predicted_cells = {(field, index, value) for index, row in predicted_rows.items() for field, value in row}
    result["gold_linked_cells"] = len(gold_cells)
    result["predicted_linked_cells"] = len(predicted_cells)
    result["ordinal_exact_linked_cells"] = len(gold_cells & predicted_cells)
    result["ordinal_normalized_linked_cells"] = len({
        (field, index, _normalize(value)) for field, index, value in gold_cells
    } & {(field, index, _normalize(value)) for field, index, value in predicted_cells})
    full_gold_rows = {index: row for index, row in gold_rows.items()
                      if {field for field, _ in row} == linked_ids}
    full_predicted_rows = {index: row for index, row in predicted_rows.items()
                           if {field for field, _ in row} == linked_ids}
    result["gold_linked_rows"] = len(gold_rows)
    result["gold_sparse_rows"] = len(gold_rows) - len(full_gold_rows)
    result["gold_complete_rows"] = len(full_gold_rows)
    groups = {matches[field_id]["predicted_group"] for field_id in linked_ids if field_id in matches}
    row_group_complete = bool(linked_ids) and linked_ids <= matches.keys() and len(groups) == 1 and None not in groups
    result["row_group_complete"] = row_group_complete
    if row_group_complete:
        result["predicted_rows"] = len(predicted_rows)
        result["predicted_complete_rows"] = len(full_predicted_rows)
        result["ordinal_exact_complete_rows"] = sum(full_gold_rows.get(i) == row for i, row in full_predicted_rows.items())
        for normalized, label in ((False, "raw"), (True, "normalized")):
            result[f"order_independent_{label}_complete_rows"] = sum(
                (_row_multiset(full_gold_rows, normalized=normalized) &
                 _row_multiset(full_predicted_rows, normalized=normalized)).values())
    else:
        result["predicted_rows"] = 0
        result["predicted_complete_rows"] = 0
        result["ordinal_exact_complete_rows"] = 0
        result["order_independent_raw_complete_rows"] = 0
        result["order_independent_normalized_complete_rows"] = 0
    result["machine_auto_accepted_values"] = 0
    return dict(result)
