"""Freeze a source-distinct VRDU plus CORD-v2-train product gate cohort.

Selection reads image bytes and source receipts before CORD annotations. This
builds inputs for ``product_eval.run_gate``; it never starts a product run.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

from PIL import Image

from product_eval.contracts import load_jsonl
from product_eval.datasets.cord_test import (
    DATASET_REVISION,
    SCALAR_FIELDS,
    _annotation,
    _doc_id,
    _gold_record,
    _sha256_bytes,
    _sha256_file,
    _write_jsonl,
)
from product_eval.datasets.cord_test import (
    PARQUET_SHA256 as CORD_TEST_PARQUET_SHA256,
)
from product_eval.datasets.vrdu import DATASET_COMMIT as VRDU_COMMIT


@dataclass(frozen=True)
class ParquetPin:
    name: str
    size: int
    sha256: str


TRAIN_FILES = (
    ParquetPin("train-00000-of-00004-b4aaeceff1d90ecb.parquet", 490224630,
               "da3994eee1bf9bd3c57f0d53a72c3a6812c8696c5ba26245987949ddf73483cc"),
    ParquetPin("train-00001-of-00004-7dbbe248962764c5.parquet", 441418432,
               "cce4def16a0d6a6c75f80be712f7494c56c318a8829b712f5c62650155c9e58e"),
    ParquetPin("train-00002-of-00004-688fe1305a55e5cc.parquet", 443802181,
               "591e2db8fe8b1d364b054f46e8c375b7f00e72578914ba46a573b6858162cab2"),
    ParquetPin("train-00003-of-00004-2d0cd200555ed7fd.parquet", 455555434,
               "1ffd9de8d6fbcee7630fd4cdfedff05b9b7fabc0fae4fc17557c5fe7cf178748"),
)
EXPECTED_TRAIN_ROWS = 800
EXPECTED_VRDU_COUNT = 2000
EXPECTED_CORD_TEST_COUNT = 100
EXPECTED_CORD_RESERVED_COUNT = 40
TARGET_COUNT = 2000
DEFAULT_SHARDS = 8
MAX_PRODUCT_SOURCE_BYTES = 20 * 1024 * 1024
VRDU_COHORT_SHA256 = "98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90"
VRDU_GOLD_SHA256 = "8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf"
CORD_TEST_COHORT_SHA256 = "e55bfed44bcba19236f70696092bb7fad96c60f573b947d2ab0c6afbd1e13f31"
SELECTION_SEED = "mixed-vrdu-cord-train-gate-v1"


class MixedGateError(ValueError):
    """A source, pin, split, or cohort cannot support the proposed gate."""


def _require_pinned_file(path: Path, digest: str, *, size: int | None = None) -> None:
    if not path.is_file() or (size is not None and path.stat().st_size != size):
        raise MixedGateError(f"Pinned source missing or size changed: {path}")
    if _sha256_file(path) != digest:
        raise MixedGateError(f"Pinned SHA-256 changed: {path}")


def _read_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MixedGateError(f"Cannot read pinned metadata: {path}") from exc
    if not isinstance(payload, dict):
        raise MixedGateError(f"Pinned metadata is not an object: {path}")
    return payload


def _cohort_rows(path: Path, expected_sha256: str, expected_count: int,
                 dataset_id: str, *, verify_bytes: bool) -> list[dict[str, Any]]:
    _require_pinned_file(path, expected_sha256)
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    hashes: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise MixedGateError(f"Invalid cohort JSON: {path}:{line_number}") from exc
        if not isinstance(row, dict) or row.get("dataset_id") != dataset_id:
            raise MixedGateError(f"Unexpected cohort dataset: {path}:{line_number}")
        source_hash, doc_id, source_path = row.get("source_sha256"), row.get("doc_id"), row.get("source_path")
        if not isinstance(source_hash, str) or len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
            raise MixedGateError(f"Invalid raw source hash: {path}:{line_number}")
        if not isinstance(doc_id, str) or not isinstance(source_path, str) or doc_id in ids or source_hash in hashes:
            raise MixedGateError(f"Duplicate or incomplete source receipt: {path}:{line_number}")
        source = Path(source_path)
        if not source.is_absolute() or _doc_id(source.name, source_hash) != doc_id:
            raise MixedGateError(f"Source path or runtime document ID changed: {path}:{line_number}")
        if verify_bytes:
            _verify_source(row)
        rows.append(row)
        ids.add(doc_id)
        hashes.add(source_hash)
    if len(rows) != expected_count:
        raise MixedGateError(f"Expected {expected_count} source receipts in {path}; found {len(rows)}")
    return rows


def _verify_source(row: dict[str, Any]) -> None:
    source = Path(row["source_path"])
    expected_size = row.get("source_size_bytes")
    if type(expected_size) is not int or expected_size < 1:
        raise MixedGateError(f"Invalid source byte count: {source}")
    _require_pinned_file(source, row["source_sha256"], size=expected_size)


def _verify_inputs(train_root: Path, vrdu_dir: Path, cord_test_dir: Path) -> tuple[
    list[Path], list[dict[str, Any]], Path, set[str],
]:
    data_dir = train_root / "data"
    if not data_dir.is_dir() or {path.name for path in data_dir.iterdir()} != {pin.name for pin in TRAIN_FILES}:
        raise MixedGateError("CORD data directory must contain exactly the four pinned train shards")
    train_paths = []
    for pin in TRAIN_FILES:
        path = data_dir / pin.name
        _require_pinned_file(path, pin.sha256, size=pin.size)
        train_paths.append(path)
    if "license: cc-by-4.0" not in (train_root / "README.md").read_text(encoding="utf-8").lower():
        raise MixedGateError("Pinned CORD checkout lacks its CC-BY-4.0 license card")

    vrdu_meta = _read_metadata(vrdu_dir / "metadata.json")
    vrdu_file_hashes = vrdu_meta.get("files_sha256")
    if (vrdu_meta.get("dataset_commit") != VRDU_COMMIT or not isinstance(vrdu_file_hashes, dict) or
            vrdu_file_hashes.get("cohort.jsonl") != VRDU_COHORT_SHA256 or
            vrdu_file_hashes.get("gold.jsonl") != VRDU_GOLD_SHA256):
        raise MixedGateError("VRDU creator commit or frozen cohort/gold receipt changed")
    vrdu = _cohort_rows(vrdu_dir / "cohort.jsonl", VRDU_COHORT_SHA256, EXPECTED_VRDU_COUNT,
                        "vrdu", verify_bytes=False)
    if any(row.get("family") not in {"registration-form", "ad-buy-form"} or
           Path(row["source_path"]).suffix.lower() != ".pdf" for row in vrdu):
        raise MixedGateError("VRDU source family or PDF format changed")
    _require_pinned_file(vrdu_dir / "gold.jsonl", VRDU_GOLD_SHA256)

    test_meta = _read_metadata(cord_test_dir / "metadata.json")
    test_file_hashes = test_meta.get("files_sha256")
    if (test_meta.get("creator_dataset_revision") != DATASET_REVISION or
            test_meta.get("creator_file_sha256") != CORD_TEST_PARQUET_SHA256 or
            not isinstance(test_file_hashes, dict) or
            test_file_hashes.get("cohort.jsonl") != CORD_TEST_COHORT_SHA256):
        raise MixedGateError("CORD test holdout pin or source receipt changed")
    test = _cohort_rows(cord_test_dir / "cohort.jsonl", CORD_TEST_COHORT_SHA256,
                        EXPECTED_CORD_TEST_COUNT, "cord_v2_test", verify_bytes=True)
    if (Counter(row.get("evaluation_split") for row in test)["reserved"] != EXPECTED_CORD_RESERVED_COUNT or
            any(row.get("evaluation_split") not in {"development", "reserved"} or
                Path(row["source_path"]).suffix.lower() != ".png" for row in test)):
        raise MixedGateError("CORD test/reserved split changed")
    return train_paths, vrdu, vrdu_dir / "gold.jsonl", {row["source_sha256"] for row in test}


def _iter_parquet_column(paths: list[Path], column: str) -> Iterator[tuple[int, Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise MixedGateError("Install pyarrow to read pinned CORD Parquet") from exc
    index = 0
    for path in paths:
        parquet = pq.ParquetFile(path)
        if set(parquet.schema_arrow.names) != {"image", "ground_truth"}:
            raise MixedGateError(f"CORD train Parquet schema changed: {path}")
        for batch in parquet.iter_batches(columns=[column], batch_size=8):
            for payload in batch.column(0).to_pylist():
                yield index, payload
                index += 1
    if index != EXPECTED_TRAIN_ROWS:
        raise MixedGateError(f"CORD train has {index} rows; expected {EXPECTED_TRAIN_ROWS}")


def _image_bytes(payload: Any, index: int) -> bytes:
    raw = payload.get("bytes") if isinstance(payload, dict) else None
    if not isinstance(raw, bytes) or not raw:
        raise MixedGateError(f"CORD train row {index} lacks embedded image bytes")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG" or image.width < 1 or image.height < 1:
                raise MixedGateError(f"CORD train row {index} is not a valid PNG")
            image.verify()
    except (OSError, ValueError) as exc:
        raise MixedGateError(f"Cannot verify CORD train image at row {index}") from exc
    return raw


def _scan_train(paths: list[Path]) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for index, payload in _iter_parquet_column(paths, "image"):
        raw = _image_bytes(payload, index)
        if len(raw) > MAX_PRODUCT_SOURCE_BYTES:
            counts["over_product_byte_limit"] += 1
            continue
        source_hash = _sha256_bytes(raw)
        filename = f"cord_train_{index:04d}.png"
        rows.append({
            "dataset_id": "cord_v2_train", "source_id": f"cord-v2/train/{index:04d}",
            "family": "receipt", "evaluation_split": "train", "source_index": index,
            "filename": filename, "source_sha256": source_hash,
            "source_size_bytes": len(raw), "doc_id": _doc_id(filename, source_hash),
        })
    return rows, counts


def _select_sources(train: list[dict[str, Any]], vrdu: list[dict[str, Any]],
                    test_hashes: set[str], target: int) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], Counter[str],
]:
    if type(target) is not int or target < 2:
        raise MixedGateError("Mixed cohort target must be at least two")
    vrdu_hashes = {row["source_sha256"] for row in vrdu}
    unique_train: dict[str, dict[str, Any]] = {}
    excluded: Counter[str] = Counter()
    for row in train:
        digest = row["source_sha256"]
        if digest in test_hashes:
            excluded["overlap_cord_test"] += 1
        elif digest in vrdu_hashes:
            excluded["overlap_vrdu"] += 1
        elif digest in unique_train:
            excluded["duplicate_train_bytes"] += 1
        else:
            unique_train[digest] = row
    cord = sorted(unique_train.values(), key=lambda row: (row["source_sha256"], row["source_id"]))[:target - 1]
    if not cord:
        raise MixedGateError("No disjoint CORD train source remains for a mixed gate")
    if len(unique_train) > len(cord):
        excluded["cord_above_target"] = len(unique_train) - len(cord)
    needed = target - len(cord)
    available_vrdu = [row for row in vrdu if row["source_sha256"] not in test_hashes and
                      row["source_sha256"] not in unique_train]
    available_vrdu.sort(key=lambda row: (
        hashlib.sha256(f"{SELECTION_SEED}\0{row['source_sha256']}".encode()).hexdigest(), row["doc_id"],
    ))
    if len(available_vrdu) < needed:
        raise MixedGateError(f"Only {len(cord) + len(available_vrdu)} distinct train/VRDU sources; need {target}")
    selected_vrdu = available_vrdu[:needed]
    if len({row["source_sha256"] for row in cord + selected_vrdu}) != target:
        raise MixedGateError("Mixed source selection is not distinct by raw SHA-256")
    return cord, selected_vrdu, excluded


def _assign_shards(rows: list[dict[str, Any]], shard_count: int) -> dict[str, str]:
    if type(shard_count) is not int or shard_count < 1 or shard_count > len(rows):
        raise MixedGateError("Invalid shard count")
    capacity = (len(rows) + shard_count - 1) // shard_count
    names: list[set[str]] = [set() for _ in range(shard_count)]
    counts = [0] * shard_count
    assigned: dict[str, str] = {}
    for offset, row in enumerate(sorted(rows, key=lambda item: (item["source_sha256"], item["doc_id"]))):
        filename = row.get("filename") or Path(row["source_path"]).name
        for step in range(shard_count):
            index = (offset + step) % shard_count
            if counts[index] < capacity and filename not in names[index]:
                assigned[row["doc_id"]] = f"shard_{index:02d}"
                names[index].add(filename)
                counts[index] += 1
                break
        else:
            raise MixedGateError(f"Cannot place source without a shard filename collision: {filename}")
    if any(count == 0 for count in counts):
        raise MixedGateError("An assigned shard is empty")
    return assigned


def _train_gold_record(doc_id: str, annotation: dict[str, Any]) -> tuple[dict[str, Any], Counter[str]]:
    """Project repeated summary sections only where their scalar is unambiguous."""
    parsed = annotation["gt_parse"]
    normalized = dict(parsed)
    exclusions: Counter[str] = Counter()
    for section_name in sorted({section for section, _ in SCALAR_FIELDS.values()}):
        section = parsed.get(section_name)
        if not isinstance(section, list):
            continue
        if any(not isinstance(item, dict) for item in section):
            raise MixedGateError(f"CORD train {section_name} list contains a non-object")
        exclusions["repeated_summary_sections"] += 1
        unique_values: dict[str, Any] = {}
        for owner, source_name in SCALAR_FIELDS.values():
            if owner != section_name:
                continue
            present = [
                raw for item in section
                if (raw := item.get(source_name)) is not None
                and (not isinstance(raw, str) or raw.strip())
            ]
            if len(present) == 1:
                unique_values[source_name] = present[0]
            elif len(present) > 1:
                exclusions["ambiguous_repeated_summary_fields_excluded"] += 1
                exclusions["ambiguous_repeated_summary_values_excluded"] += len(present)
        normalized[section_name] = unique_values
    projected = dict(annotation)
    projected["gt_parse"] = normalized
    record, stats = _gold_record(doc_id, projected)
    stats.update(exclusions)
    return record, stats


def _train_gold(paths: list[Path], selected: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    by_index = {row["source_index"]: row for row in selected}
    gold: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for index, payload in _iter_parquet_column(paths, "ground_truth"):
        if index in by_index:
            annotation = _annotation(payload, index, expected_split="train")
            record, stats = _train_gold_record(by_index[index]["doc_id"], annotation)
            gold.append(record)
            counts.update(stats)
    if len(gold) != len(selected):
        raise MixedGateError("CORD train annotations do not cover selected source rows")
    return gold, counts


def build_mixed_gate(train_root: Path, vrdu_dir: Path, cord_test_dir: Path, output_dir: Path,
                     *, target: int = TARGET_COUNT, shard_count: int = DEFAULT_SHARDS) -> dict[str, Any]:
    """Build an immutable candidate gate bundle; the CLI fixes target at 2,000."""
    train_root, vrdu_dir, cord_test_dir, output_dir = (
        path.resolve() for path in (train_root, vrdu_dir, cord_test_dir, output_dir)
    )
    if output_dir.exists():
        raise MixedGateError(f"Output directory already exists: {output_dir}")
    paths, vrdu, vrdu_gold_path, test_hashes = _verify_inputs(train_root, vrdu_dir, cord_test_dir)
    train, source_counts = _scan_train(paths)
    selected_cord, selected_vrdu, excluded = _select_sources(train, vrdu, test_hashes, target)
    vrdu_gold = load_jsonl(vrdu_gold_path, kind="gold")
    if set(vrdu_gold) != {row["doc_id"] for row in vrdu}:
        raise MixedGateError("VRDU gold does not cover exactly the frozen source cohort")
    assignment = _assign_shards(selected_cord + selected_vrdu, shard_count)
    cord_gold, annotation_counts = _train_gold(paths, selected_cord)
    selected_cord_by_index = {row["source_index"]: row for row in selected_cord}
    vrdu_by_id = {row["doc_id"]: row for row in selected_vrdu}
    selected_gold = {row["doc_id"]: row for row in cord_gold}
    selected_gold.update({doc_id: vrdu_gold[doc_id] for doc_id in vrdu_by_id})
    if len(selected_gold) != target:
        raise MixedGateError("Mixed gold does not cover every selected source")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}.", dir=output_dir.parent) as temporary:
        stage = Path(temporary)
        (stage / "shards").mkdir()
        cohort: list[dict[str, Any]] = []
        for row in selected_cord + selected_vrdu:
            filename = row.get("filename") or Path(row["source_path"]).name
            shard = assignment[row["doc_id"]]
            (stage / "shards" / shard).mkdir(exist_ok=True)
            final_path = output_dir / "shards" / shard / filename
            cohort.append({
                "dataset_id": row["dataset_id"], "source_id": row["source_id"],
                "family": row["family"],
                "evaluation_split": "train" if row["dataset_id"] == "cord_v2_train" else "development",
                "source_path": str(final_path), "source_sha256": row["source_sha256"],
                "source_size_bytes": row["source_size_bytes"], "doc_id": row["doc_id"],
                "gate_shard": shard,
            })
            if row["doc_id"] in vrdu_by_id:
                _verify_source(row)
                shutil.copyfile(row["source_path"], stage / "shards" / shard / filename)
                _require_pinned_file(stage / "shards" / shard / filename,
                                     row["source_sha256"], size=row["source_size_bytes"])
        staged_cord: set[int] = set()
        for index, payload in _iter_parquet_column(paths, "image"):
            row = selected_cord_by_index.get(index)
            if row is None:
                continue
            raw = _image_bytes(payload, index)
            if len(raw) != row["source_size_bytes"] or _sha256_bytes(raw) != row["source_sha256"]:
                raise MixedGateError(f"CORD train image changed between reads: {index}")
            (stage / "shards" / assignment[row["doc_id"]] / row["filename"]).write_bytes(raw)
            staged_cord.add(index)
        if staged_cord != set(selected_cord_by_index):
            raise MixedGateError("Not every selected CORD train image was staged")
        for row in selected_cord:
            _require_pinned_file(stage / "shards" / assignment[row["doc_id"]] / row["filename"],
                                 row["source_sha256"], size=row["source_size_bytes"])

        cohort.sort(key=lambda row: (row["gate_shard"], row["doc_id"]))
        gold = [selected_gold[row["doc_id"]] for row in cohort]
        file_records = {
            "cohort.jsonl": cohort,
            "gold.jsonl": gold,
            "cohort_cord_train.jsonl": [row for row in cohort if row["dataset_id"] == "cord_v2_train"],
            "gold_cord_train.jsonl": [selected_gold[row["doc_id"]] for row in cohort
                                      if row["dataset_id"] == "cord_v2_train"],
        }
        for name, records in file_records.items():
            _write_jsonl(stage / name, records)
        if set(load_jsonl(stage / "gold.jsonl", kind="gold")) != {row["doc_id"] for row in cohort}:
            raise MixedGateError("Staged mixed gold/source IDs differ")
        metadata = {
            "builder_version": 1,
            "reader_versions": {"pyarrow": version("pyarrow"), "pillow": Image.__version__},
            "selection_seed": SELECTION_SEED,
            "dataset_license": "CORD v2 CC-BY-4.0; attribute NAVER CLOVA and the CORD creators",
            "cord_dataset_revision": DATASET_REVISION,
            "cord_train_files": [{"path": f"data/{pin.name}", "size": pin.size, "sha256": pin.sha256}
                                 for pin in TRAIN_FILES],
            "cord_train_rows": EXPECTED_TRAIN_ROWS,
            "cord_test_cohort_sha256": CORD_TEST_COHORT_SHA256,
            "cord_test_reserved_count": EXPECTED_CORD_RESERVED_COUNT,
            "vrdu_dataset_commit": VRDU_COMMIT,
            "vrdu_cohort_sha256": VRDU_COHORT_SHA256,
            "vrdu_gold_sha256": VRDU_GOLD_SHA256,
            "source_selection": "CORD train raw image SHA-256 distinct from local CORD test and VRDU; all eligible train sources (up to target-1), then seeded SHA rank of pinned VRDU receipts. Selection precedes annotation parsing.",
            "cohort_count": len(cohort),
            "distinct_source_sha256_count": len({row["source_sha256"] for row in cohort}),
            "family_counts": dict(sorted(Counter(row["family"] for row in cohort).items())),
            "dataset_counts": dict(sorted(Counter(row["dataset_id"] for row in cohort).items())),
            "train_source_exclusions": dict(sorted((source_counts + excluded).items())),
            "cord_annotation_stats": dict(sorted(annotation_counts.items())),
            "shard_dirs": [str(output_dir / "shards" / f"shard_{index:02d}") for index in range(shard_count)],
            "files_sha256": {name: _sha256_file(stage / name) for name in file_records},
            "interpretation_limits": [
                "CORD train gold maps positive raw-string summary fields and menu nm/cnt/price rows only; absent labels are unscored, so strict combined precision/F1 is not a CORD quality claim.",
                "The mixed gate is an execution-volume regression on three dataset families, not arbitrary-document validation.",
                "Raw SHA exclusion checks all local CORD test images, including the 40 reserved holdout; no visual or vendor-level train/test/validation disjointness is proven.",
                "CORD validation is not read or staged; source duplication against validation cannot be checked without its raw images.",
                "Use the CORD positive-only scorer on CORD-only candidates after the complete product gate; no automatic-release or monetary cost claim follows from this builder.",
            ],
        }
        (stage / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if output_dir.exists():
            raise MixedGateError(f"Output directory appeared while building: {output_dir}")
        stage.rename(output_dir)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cord-train-root", type=Path, required=True)
    parser.add_argument("--vrdu-cohort-dir", type=Path, required=True)
    parser.add_argument("--cord-test-cohort-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_mixed_gate(args.cord_train_root, args.vrdu_cohort_dir,
                                  args.cord_test_cohort_dir, args.output_dir)
    except (MixedGateError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({key: result[key] for key in (
        "cohort_count", "distinct_source_sha256_count", "dataset_counts", "family_counts", "shard_dirs",
    )}, indent=2))


if __name__ == "__main__":
    main()
