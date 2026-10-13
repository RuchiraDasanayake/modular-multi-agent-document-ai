"""Validate an explicit, immutable approved recipe snapshot at the worker boundary."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_SNAPSHOT_BYTES = 16 * 1024
_RECIPE_ID = re.compile(r"recipe_[a-f0-9]{32}\Z")
_HEX32 = re.compile(r"[a-f0-9]{32}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_FIELD_ID = re.compile(r"[^\W\d][\w]{0,63}\Z", re.UNICODE)
_FIELD_TYPES = {"string", "integer", "decimal", "boolean", "date", "array[object]"}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate recipe property")
        result[key] = value
    return result


def _valid_group(value: object) -> bool:
    return (isinstance(value, str) and value and len(value) <= 64 and value == value.strip()
            and not any(ord(char) < 32 or ord(char) == 127 for char in value))


@dataclass(frozen=True)
class ApprovedRecipe:
    recipe_id: str
    revision: int
    audit_event_id: str
    owner_user_id: str
    family_name: str
    fields: tuple[dict[str, object], ...]
    snapshot_sha256: str

    @property
    def receipt(self) -> dict[str, object]:
        return {
            "recipe_id": self.recipe_id,
            "revision": self.revision,
            "audit_event_id": self.audit_event_id,
            "snapshot_sha256": self.snapshot_sha256,
        }


def load_approved_recipe(path: Path, expected_sha256: str) -> ApprovedRecipe:
    """Read one bounded snapshot and reject any byte or schema mismatch."""
    if not _SHA256.fullmatch(expected_sha256):
        raise ValueError("Invalid approved recipe digest")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise ValueError("Invalid approved recipe snapshot file")
    raw = path.read_bytes()
    if len(raw) > MAX_SNAPSHOT_BYTES or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Approved recipe snapshot digest mismatch")
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Invalid approved recipe JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "contract_version", "recipe_id", "revision", "audit_event_id", "state", "owner_user_id",
        "family_name", "source_review_digest_sha256", "fields", "row_groups",
    }:
        raise ValueError("Invalid approved recipe snapshot")
    recipe_id = payload["recipe_id"]
    revision = payload["revision"]
    event_id = payload["audit_event_id"]
    owner = payload["owner_user_id"]
    family = payload["family_name"]
    source_digest = payload["source_review_digest_sha256"]
    if (type(payload["contract_version"]) is not int or payload["contract_version"] != 1
            or not isinstance(recipe_id, str) or not _RECIPE_ID.fullmatch(recipe_id)
            or type(revision) is not int or revision != 2
            or not isinstance(event_id, str) or not _HEX32.fullmatch(event_id)
            or payload["state"] != "approved_shadow"
            or not isinstance(owner, str) or not owner or len(owner) > 256
            or not isinstance(family, str) or len(family) < 2 or len(family) > 100
            or family != family.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in family)
            or not isinstance(source_digest, str) or not _SHA256.fullmatch(source_digest)):
        raise ValueError("Invalid approved recipe identity")
    fields = payload["fields"]
    if not isinstance(fields, list) or not 1 <= len(fields) <= 24:
        raise ValueError("Invalid approved recipe fields")
    seen: set[str] = set()
    linked: dict[str, list[str]] = {}
    scalar_groups: set[str] = set()
    for field in fields:
        if not isinstance(field, dict) or set(field) not in ({"field_id", "type"}, {"field_id", "type", "group"}):
            raise ValueError("Invalid approved recipe field")
        field_id, field_type = field["field_id"], field["type"]
        if (not isinstance(field_id, str) or not _FIELD_ID.fullmatch(field_id) or not field_id[0].isalpha()
                or field_id.endswith("_")
                or unicodedata.normalize("NFKC", field_id).lower() != field_id
                or field_id in seen or not isinstance(field_type, str) or field_type not in _FIELD_TYPES):
            raise ValueError("Invalid approved recipe field")
        seen.add(field_id)
        group = field.get("group")
        if "group" in field and not _valid_group(group):
            raise ValueError("Invalid approved recipe group")
        if field_type == "array[object]":
            if group is None:
                raise ValueError("Linked recipe fields require a group")
            linked.setdefault(group, []).append(field_id)
        elif group is not None:
            scalar_groups.add(group)
    groups = payload["row_groups"]
    if not isinstance(groups, list) or len(groups) != len(linked):
        raise ValueError("Invalid approved recipe row groups")
    expected = {name: sorted(ids) for name, ids in linked.items()}
    if any(name in scalar_groups or len(ids) < 2 for name, ids in expected.items()):
        raise ValueError("Invalid linked recipe group")
    for group in groups:
        if (not isinstance(group, dict) or set(group) != {"group", "field_ids", "alignment"}
                or group["alignment"] != "shared_ordinal" or not isinstance(group["group"], str)
                or group["group"] not in expected or group["field_ids"] != expected.pop(group["group"])):
            raise ValueError("Invalid approved recipe row group")
    if expected:
        raise ValueError("Invalid approved recipe row groups")
    return ApprovedRecipe(recipe_id, revision, event_id, owner, family, tuple(fields), expected_sha256)
