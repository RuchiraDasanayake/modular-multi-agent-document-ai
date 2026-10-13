"""Validate the pinned, user-confirmed schema consumed by product extraction."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_SNAPSHOT_BYTES = 64 * 1024
_BRIEF_ID = re.compile(r"brief_[a-f0-9]{32}\Z")
_HEX32 = re.compile(r"[a-f0-9]{32}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_FIELD_ID = re.compile(r"[^\W\d][\w]{0,63}\Z", re.UNICODE)
_FIELD_TYPES = {"string", "integer", "decimal", "boolean", "date", "array[object]"}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate confirmed schema property")
        result[key] = value
    return result


def _bounded_text(value: object, limit: int) -> bool:
    return (isinstance(value, str) and value == value.strip() and len(value) <= limit
            and not any(ord(char) < 9 or char in "\x0b\x0c" or 14 <= ord(char) <= 31
                        or ord(char) == 127 for char in value))


@dataclass(frozen=True)
class ConfirmedSchema:
    brief_id: str
    revision: int
    audit_event_id: str
    owner_user_id: str
    job_id: str
    intent: str
    fields: tuple[dict[str, object], ...]
    sample_sources: tuple[dict[str, str], ...]
    payload_sha256: str
    snapshot_sha256: str

    @property
    def receipt(self) -> dict[str, object]:
        return {
            "brief_id": self.brief_id,
            "revision": self.revision,
            "audit_event_id": self.audit_event_id,
            "payload_sha256": self.payload_sha256,
            "snapshot_sha256": self.snapshot_sha256,
        }

    @property
    def candidate_fields(self) -> list[dict[str, object]]:
        return [{key: field[key] for key in ("field_id", "type", "group") if key in field}
                for field in self.fields]


def load_confirmed_schema(path: Path, expected_sha256: str) -> ConfirmedSchema:
    """Fail closed before any model call or output directory is created."""
    if not _SHA256.fullmatch(expected_sha256):
        raise ValueError("Invalid confirmed schema digest")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise ValueError("Invalid confirmed schema snapshot file")
    raw = path.read_bytes()
    if len(raw) > MAX_SNAPSHOT_BYTES or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Confirmed schema snapshot digest mismatch")
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Invalid confirmed schema JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "contract_version", "brief_id", "revision", "audit_event_id", "state", "owner_user_id",
        "job_id", "intent", "fields", "sample_sources", "payload_sha256",
    }:
        raise ValueError("Invalid confirmed schema snapshot")
    if (type(payload["contract_version"]) is not int or payload["contract_version"] != 1
            or not isinstance(payload["brief_id"], str) or not _BRIEF_ID.fullmatch(payload["brief_id"])
            or type(payload["revision"]) is not int or payload["revision"] < 2
            or not isinstance(payload["audit_event_id"], str) or not _HEX32.fullmatch(payload["audit_event_id"])
            or payload["state"] != "confirmed"
            or not isinstance(payload["owner_user_id"], str) or not 0 < len(payload["owner_user_id"]) <= 256
            or not isinstance(payload["job_id"], str) or not _HEX32.fullmatch(payload["job_id"])
            or not _bounded_text(payload["intent"], 4000)
            or not isinstance(payload["payload_sha256"], str)
            or not _SHA256.fullmatch(payload["payload_sha256"])):
        raise ValueError("Invalid confirmed schema identity")
    fields = payload["fields"]
    if not isinstance(fields, list) or not 1 <= len(fields) <= 24:
        raise ValueError("Invalid confirmed schema fields")
    seen: set[str] = set()
    for field in fields:
        if not isinstance(field, dict) or set(field) not in (
            {"field_id", "type", "description", "example_values"},
            {"field_id", "type", "group", "description", "example_values"},
        ):
            raise ValueError("Invalid confirmed schema field")
        field_id, field_type = field["field_id"], field["type"]
        if (not isinstance(field_id, str) or not _FIELD_ID.fullmatch(field_id) or not field_id[0].isalpha()
                or field_id.endswith("_") or unicodedata.normalize("NFKC", field_id).lower() != field_id
                or field_id in seen or not isinstance(field_type, str) or field_type not in _FIELD_TYPES
                or not _bounded_text(field["description"], 1000)):
            raise ValueError("Invalid confirmed schema field")
        seen.add(field_id)
        group = field.get("group")
        if "group" in field and (not isinstance(group, str) or not group or len(group) > 64
                                 or group != group.strip() or any(ord(char) < 32 or ord(char) == 127 for char in group)):
            raise ValueError("Invalid confirmed schema group")
        if field_type == "array[object]" and group is None:
            raise ValueError("Repeated confirmed schema fields require a group")
        examples = field["example_values"]
        if (not isinstance(examples, list) or len(examples) > 3 or
                any(not _bounded_text(example, 200) or not example for example in examples)):
            raise ValueError("Invalid confirmed schema examples")
    samples = payload["sample_sources"]
    if (not isinstance(samples, list) or not 1 <= len(samples) <= 5 or
            any(not isinstance(sample, dict) or set(sample) != {"file_id", "source_sha256"} or
                not isinstance(sample["file_id"], str) or not _HEX32.fullmatch(sample["file_id"]) or
                not isinstance(sample["source_sha256"], str) or not _SHA256.fullmatch(sample["source_sha256"])
                for sample in samples) or len({sample["file_id"] for sample in samples}) != len(samples)):
        raise ValueError("Invalid confirmed schema sample sources")
    return ConfirmedSchema(
        payload["brief_id"], payload["revision"], payload["audit_event_id"],
        payload["owner_user_id"], payload["job_id"], payload["intent"],
        tuple(fields), tuple(samples), payload["payload_sha256"], expected_sha256,
    )
