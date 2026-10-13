"""Freeze the FUNSD test forms outside the historical FUNSD-20 pack.

Only published DATE/TO/FROM question-to-answer links become positive gold.
The selection is made from filenames before any annotations are inspected.
FUNSD's creator terms restrict this slice to non-commercial research/education.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from product_eval.contracts import validate_record

ADAPTER_VERSION = 1
FIELD_MAP = {"DATE": "date", "TO": "recipient", "FROM": "sender"}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LICENSE_URL = "https://guillaumejaume.github.io/FUNSD/work/"


class FunsdSliceError(ValueError):
    """The local images, annotations, or frozen source lock cannot be trusted."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise FunsdSliceError(f"Invalid JSON: {path}") from exc


def _historic_ids(pack: Any) -> set[str]:
    if not isinstance(pack, dict) or not isinstance(pack.get("cases"), list):
        raise FunsdSliceError("Historical FUNSD pack has no cases array")
    ids: set[str] = set()
    for case in pack["cases"]:
        case_id = case.get("case_id") if isinstance(case, dict) else None
        if not isinstance(case_id, str) or not case_id.startswith("funsd_"):
            raise FunsdSliceError("Historical pack has an invalid case ID")
        stem = case_id.removeprefix("funsd_")
        if not stem or stem in ids or Path(stem).name != stem:
            raise FunsdSliceError("Historical pack has duplicate or unsafe case IDs")
        ids.add(stem)
    return ids


def _linked_answers(annotation: Any) -> dict[str, str]:
    if not isinstance(annotation, dict) or not isinstance(annotation.get("form"), list):
        raise FunsdSliceError("FUNSD annotation must contain a form array")
    entries = annotation["form"]
    ids: dict[int, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or type(entry.get("id")) is not int or entry["id"] in ids:
            raise FunsdSliceError("FUNSD form has an invalid or duplicate entity ID")
        ids[entry["id"]] = entry
    answers: dict[str, list[str]] = {field: [] for field in FIELD_MAP.values()}
    for entry in entries:
        if entry.get("label") != "question":
            continue
        raw = entry.get("text")
        if not isinstance(raw, str):
            raise FunsdSliceError("FUNSD question text must be a string")
        question = raw.strip().upper().rstrip(":").rstrip("?").strip()
        field = FIELD_MAP.get(question)
        if field is None:
            continue
        links = entry.get("linking")
        if not isinstance(links, list):
            raise FunsdSliceError("FUNSD question links must be an array")
        for link in links:
            if not isinstance(link, list) or len(link) != 2 or any(type(value) is not int for value in link):
                raise FunsdSliceError("FUNSD question has a malformed link")
            if entry["id"] not in link:
                raise FunsdSliceError("FUNSD question link does not include its entity ID")
            other = ids.get(link[1] if link[0] == entry["id"] else link[0])
            if other is None or other.get("label") != "answer":
                continue
            value = other.get("text")
            if not isinstance(value, str):
                raise FunsdSliceError("FUNSD answer text must be a string")
            if value.strip():
                answers[field].append(value.strip())
    return {field: " ".join(values) for field, values in answers.items() if values}


def _doc_id(filename: str, source_sha256: str) -> str:
    # Match idpo.product_auto.workflow._doc_id(filename, source_hash, index=0).
    return hashlib.sha256(f"{filename}\0{source_sha256}\0{0}".encode()).hexdigest()[:32]


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build_funsd_remainder(
    image_root: Path,
    annotation_root: Path,
    historical_pack: Path,
    source_lock: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Stage all previously excluded test images and derive sparse positive gold."""
    image_root = image_root.resolve()
    annotation_root = annotation_root.resolve()
    historical_pack = historical_pack.resolve()
    source_lock = source_lock.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FunsdSliceError(f"Output directory already exists: {output_dir}")
    if not image_root.is_dir() or not annotation_root.is_dir():
        raise FunsdSliceError("FUNSD image and annotation directories are required")
    lock = _json(source_lock)
    if not isinstance(lock, dict) or lock.get("adapter_version") != ADAPTER_VERSION:
        raise FunsdSliceError("Unexpected FUNSD source lock version")
    historic_hash = _sha256(historical_pack)
    if lock.get("historical_pack_sha256") != historic_hash:
        raise FunsdSliceError("Historical FUNSD-20 pack differs from the frozen lock")
    images = {path.stem: path for path in image_root.glob("*.png") if path.is_file()}
    annotations = {path.stem: path for path in annotation_root.glob("*.json") if path.is_file()}
    if len(images) != lock.get("source_test_count") or set(images) != set(annotations):
        raise FunsdSliceError("FUNSD test split count or image/annotation pairing differs from the lock")
    excluded = _historic_ids(_json(historical_pack))
    if not excluded <= set(images) or len(excluded) != lock.get("historical_count"):
        raise FunsdSliceError("Historical FUNSD-20 IDs do not match the test split")
    selected = sorted(set(images) - excluded)
    locked_entries = lock.get("entries")
    if not isinstance(locked_entries, list) or len(locked_entries) != len(selected):
        raise FunsdSliceError("FUNSD lock has the wrong number of selected sources")
    locked_by_stem = {
        item.get("stem"): item for item in locked_entries if isinstance(item, dict)
    }
    if set(locked_by_stem) != set(selected) or len(locked_by_stem) != len(locked_entries):
        raise FunsdSliceError("FUNSD source lock does not match the selected filenames")

    verified: list[tuple[str, Path, str, int, dict[str, str]]] = []
    source_hashes: set[str] = set()
    coverage: Counter[str] = Counter()
    for stem in selected:
        image = images[stem]
        annotation = annotations[stem]
        image_hash = _sha256(image)
        annotation_hash = _sha256(annotation)
        locked = locked_by_stem[stem]
        if image_hash != locked.get("image_sha256") or annotation_hash != locked.get("annotation_sha256"):
            raise FunsdSliceError(f"Pinned FUNSD source bytes differ: {stem}")
        if image_hash in source_hashes:
            raise FunsdSliceError(f"Duplicate FUNSD image content: {stem}")
        source_hashes.add(image_hash)
        found = _linked_answers(_json(annotation))
        coverage.update(found.keys())
        verified.append((stem, image, image_hash, image.stat().st_size, found))

    output_dir.mkdir(parents=True)
    input_dir = output_dir / "input"
    input_dir.mkdir()
    cohort: list[dict[str, Any]] = []
    gold: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for stem, image, source_hash, size, found in verified:
        staged = input_dir / image.name
        shutil.copyfile(image, staged)
        if _sha256(staged) != source_hash:
            raise FunsdSliceError(f"Staged FUNSD image differs from source: {stem}")
        doc_id = _doc_id(image.name, source_hash)
        cohort.append({
            "dataset_id": "funsd_test_remainder",
            "source_id": f"FUNSD/testing_data/{image.name}",
            "family": "noisy-scanned-form",
            "source_path": str(staged),
            "source_sha256": source_hash,
            "source_size_bytes": size,
            "doc_id": doc_id,
        })
        if not found:
            exclusions.append({
                "doc_id": doc_id,
                "source_id": f"FUNSD/testing_data/{image.name}",
                "reason": "no_linked_DATE_TO_FROM_answer",
            })
            continue
        record = {
            "contract_version": 1,
            "doc_id": doc_id,
            "pages": [{"page": 1, "text": ""}],
            "gold_schema": [
                {"field_id": field, "type": "string", "critical": False}
                for field in FIELD_MAP.values() if field in found
            ],
            "gold_values": [
                {"field_id": field, "value": found[field]}
                for field in FIELD_MAP.values() if field in found
            ],
        }
        validate_record(record, kind="gold")
        gold.append(record)
    cohort_path = output_dir / "cohort.jsonl"
    gold_path = output_dir / "gold.jsonl"
    exclusions_path = output_dir / "exclusions.jsonl"
    _write_jsonl(cohort_path, cohort)
    _write_jsonl(gold_path, gold)
    _write_jsonl(exclusions_path, exclusions)
    metadata = {
        "adapter_version": ADAPTER_VERSION,
        "dataset_id": "funsd_test_remainder",
        "source_dataset": "FUNSD testing_data",
        "license_url": LICENSE_URL,
        "permitted_use": "Non-commercial research and education only under the creator's terms; image rights require separate review.",
        "source_verification": "Raw image and checked-in annotation SHA256 match the committed local lock; original creator archive was not available for byte comparison.",
        "historical_pack_sha256": historic_hash,
        "source_lock_sha256": _sha256(source_lock),
        "selection": "All 50 local test image filenames minus the 20 case IDs in datasets/funsd_pack_20.json; selection before reading annotations.",
        "cohort_count": len(cohort),
        "distinct_source_sha256_count": len(source_hashes),
        "gold_count": len(gold),
        "gold_exclusion_count": len(exclusions),
        "gold_positive_field_count": sum(coverage.values()),
        "gold_positive_field_coverage": dict(sorted(coverage.items())),
        "gold_scope": "Only positive published DATE/TO/FROM question-answer links. Missing links are unknown, not absent fields. This is partial-label research gold and must not support global precision, schema F1, or auto-release claims.",
        "evidence_scope": "FUNSD provides image boxes, not OCR character spans; no gold evidence spans are asserted. Gold pages intentionally contain no OCR transcript.",
        "leakage_scope": "The historical FUNSD-20 cases are excluded, but other historical experiments may have inspected these forms; this is not an untouched holdout.",
        "files_sha256": {
            path.name: _sha256(path)
            for path in (cohort_path, gold_path, exclusions_path)
        },
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-root", type=Path, required=True, help="Local FUNSD testing_data/images directory")
    parser.add_argument(
        "--annotation-root", type=Path,
        default=REPOSITORY_ROOT / "datasets" / "FUNSD" / "testing_data" / "annotations",
    )
    parser.add_argument(
        "--historical-pack", type=Path, default=REPOSITORY_ROOT / "datasets" / "funsd_pack_20.json"
    )
    parser.add_argument(
        "--source-lock", type=Path, default=Path(__file__).with_name("funsd_test_remainder_lock.json")
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_funsd_remainder(
        args.image_root, args.annotation_root, args.historical_pack, args.source_lock, args.output_dir
    )
    print(json.dumps({
        "cohort_count": result["cohort_count"],
        "gold_count": result["gold_count"],
        "gold_exclusion_count": result["gold_exclusion_count"],
        "gold_positive_field_count": result["gold_positive_field_count"],
        "output_dir": str(args.output_dir.resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
