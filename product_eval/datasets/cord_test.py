"""Freeze creator-hosted CORD v2 test receipts as positive-only product gold.

Selection and the visual near-duplicate split use source image bytes alone.
Ground-truth JSON is read only after the split has been fixed in memory.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from product_eval.contracts import validate_record

ADAPTER_VERSION = 1
DATASET_REPO = "naver-clova-ix/cord-v2"
DATASET_REVISION = "7f0115a4b758a71d6473b8d085751692da2fef98"
PARQUET_NAME = "test-00000-of-00001-9c204eb3f4e11791.parquet"
PARQUET_SHA256 = "51c65f1788faff392abe2a0b55b023eb23e9be551c509138eaa3a832514224e7"
DATASET_URL = f"https://huggingface.co/datasets/{DATASET_REPO}/tree/{DATASET_REVISION}/data"
EXPECTED_TEST_ROWS = 100
SPLIT_SEED = "cord-v2-product-test-visual-block-v1"
RESERVED_TARGET = 40
DHASH_DISTANCE = 12
ASPECT_DISTANCE = 0.05
SCALAR_FIELDS = {
    "total_amount": ("total", "total_price"),
    "cash_amount": ("total", "cashprice"),
    "change_amount": ("total", "changeprice"),
    "subtotal_amount": ("sub_total", "subtotal_price"),
    "tax_amount": ("sub_total", "tax_price"),
}
ROW_FIELDS = {
    "item_name": "nm",
    "item_quantity": "cnt",
    "item_price": "price",
}


class CordSliceError(ValueError):
    """The pinned creator source or annotation structure cannot be scored."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _doc_id(filename: str, source_hash: str) -> str:
    # Match idpo.product_auto.workflow._doc_id(filename, source_hash, index=0).
    return hashlib.sha256(f"{filename}\0{source_hash}\0{0}".encode()).hexdigest()[:32]


def _dhash_and_aspect(raw: bytes) -> tuple[int, float]:
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG":
                raise CordSliceError("Pinned CORD image is not PNG")
            image = ImageOps.exif_transpose(image).convert("L")
            width, height = image.size
            if width < 1 or height < 1:
                raise CordSliceError("Pinned CORD image has invalid dimensions")
            resized = image.resize((9, 8), Image.Resampling.LANCZOS)
            pixels = list(resized.get_flattened_data())
    except (OSError, ValueError) as exc:
        raise CordSliceError("Cannot decode pinned CORD image") from exc
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return bits, width / height


def _visual_components(sources: list[dict[str, Any]]) -> list[list[int]]:
    parent = list(range(len(sources)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left in range(len(sources)):
        for right in range(left + 1, len(sources)):
            if (
                abs(sources[left]["aspect"] - sources[right]["aspect"]) <= ASPECT_DISTANCE
                and (sources[left]["dhash"] ^ sources[right]["dhash"]).bit_count() <= DHASH_DISTANCE
            ):
                parent[root(right)] = root(left)
    groups: dict[int, list[int]] = {}
    for index in range(len(sources)):
        groups.setdefault(root(index), []).append(index)
    return list(groups.values())


def _assign_splits(sources: list[dict[str, Any]]) -> tuple[dict[int, str], dict[str, int]]:
    components = _visual_components(sources)
    groups = sorted(
        components,
        key=lambda group: hashlib.sha256(
            (SPLIT_SEED + "\0" + "|".join(sorted(sources[index]["sha256"] for index in group))).encode()
        ).hexdigest(),
    )
    splits: dict[int, str] = {}
    reserved = 0
    for group in groups:
        destination = "reserved" if reserved < RESERVED_TARGET else "development"
        for index in group:
            splits[index] = destination
        if destination == "reserved":
            reserved += len(group)
    return splits, {
        "component_count": len(components),
        "multi_image_component_count": sum(len(group) > 1 for group in components),
        "largest_component_size": max(map(len, components)),
        "development_count": len(sources) - reserved,
        "reserved_count": reserved,
    }


def _annotation(row: Any, source_index: int, *, expected_split: str = "test") -> dict[str, Any]:
    if not isinstance(row, str):
        raise CordSliceError(f"CORD row {source_index} lacks ground_truth JSON")
    try:
        payload = json.loads(row)
    except ValueError as exc:
        raise CordSliceError(f"CORD row {source_index} has invalid ground_truth JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("gt_parse"), dict):
        raise CordSliceError(f"CORD row {source_index} lacks gt_parse")
    meta = payload.get("meta")
    if not isinstance(meta, dict) or meta.get("split") != expected_split or meta.get("version") != "2.0.0":
        raise CordSliceError(f"CORD row {source_index} has unexpected split/version")
    return payload


def _gold_record(doc_id: str, annotation: dict[str, Any]) -> tuple[dict[str, Any], Counter[str]]:
    gt_parse = annotation["gt_parse"]
    values: dict[str, Any] = {}
    stats: Counter[str] = Counter()
    for field, (section_name, source_name) in SCALAR_FIELDS.items():
        section = gt_parse.get(section_name)
        if section is None:
            continue
        if not isinstance(section, dict):
            raise CordSliceError(f"CORD {section_name} parse must be an object")
        raw = section.get(source_name)
        if raw is None:
            continue
        if not isinstance(raw, str):
            stats["non_scalar_summary_labels_excluded"] += 1
            continue
        if raw.strip():
            values[field] = raw.strip()
            stats["scalar_positive_values"] += 1

    menu = gt_parse.get("menu")
    if menu is None:
        menu_rows: list[Any] = []
    elif isinstance(menu, dict):
        menu_rows = [menu]
    elif isinstance(menu, list):
        menu_rows = menu
    else:
        raise CordSliceError("CORD menu parse must be an object or array")
    linked: dict[str, list[dict[str, Any]]] = {field: [] for field in ROW_FIELDS}
    for row_index, item in enumerate(menu_rows):
        if not isinstance(item, dict):
            raise CordSliceError("CORD menu row must be an object")
        for field, source_name in ROW_FIELDS.items():
            raw = item.get(source_name)
            if raw is None:
                continue
            if not isinstance(raw, str):
                stats["non_string_menu_cells_excluded"] += 1
                continue
            if raw.strip():
                linked[field].append({"row": row_index, "value": raw.strip()})
                stats["linked_positive_cells"] += 1
    stats["published_menu_rows"] += len(menu_rows)
    for field, entries in linked.items():
        if entries:
            values[field] = entries
    schema = [
        {"field_id": field, "type": "array[object]" if field in ROW_FIELDS else "string", "critical": False}
        for field in (*SCALAR_FIELDS, *ROW_FIELDS) if field in values
    ]
    gold_values = [
        {"field_id": field["field_id"], "value": values[field["field_id"]]}
        for field in schema
    ]
    record = {
        "contract_version": 1,
        "doc_id": doc_id,
        "pages": [{"page": 1, "text": ""}],
        "gold_schema": schema,
        "gold_values": gold_values,
    }
    validate_record(record, kind="gold")
    return record, stats


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def build_cord_test_cohort(parquet_path: Path, output_dir: Path) -> dict[str, Any]:
    """Stage 100 pinned test PNGs, a source-only split, and separate gold."""
    parquet_path = parquet_path.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise CordSliceError(f"Output directory already exists: {output_dir}")
    if not parquet_path.is_file() or parquet_path.name != PARQUET_NAME:
        raise CordSliceError(f"Pinned CORD test parquet missing: {parquet_path}")
    if _sha256_file(parquet_path) != PARQUET_SHA256:
        raise CordSliceError("CORD test parquet SHA256 differs from creator-hosted pinned file")
    try:
        import pyarrow
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise CordSliceError("Install pyarrow to read the pinned CORD parquet") from exc
    parquet = pq.ParquetFile(parquet_path)
    if parquet.metadata.num_rows != EXPECTED_TEST_ROWS or set(parquet.schema_arrow.names) != {"image", "ground_truth"}:
        raise CordSliceError("CORD test parquet schema or row count differs from the pinned dataset")
    image_rows = parquet.read(columns=["image"]).column("image").to_pylist()
    sources: list[dict[str, Any]] = []
    source_hashes: set[str] = set()
    for index, payload in enumerate(image_rows):
        raw = payload.get("bytes") if isinstance(payload, dict) else None
        if not isinstance(raw, bytes) or not raw:
            raise CordSliceError(f"CORD row {index} has no embedded image bytes")
        source_hash = _sha256_bytes(raw)
        if source_hash in source_hashes:
            raise CordSliceError(f"Duplicate CORD source image content at row {index}")
        source_hashes.add(source_hash)
        image_hash, aspect = _dhash_and_aspect(raw)
        sources.append({"raw": raw, "sha256": source_hash, "dhash": image_hash, "aspect": aspect})
    splits, split_stats = _assign_splits(sources)

    # Label parsing starts here; all 100 sources and their split are already fixed.
    annotations = parquet.read(columns=["ground_truth"]).column("ground_truth").to_pylist()
    gold: list[dict[str, Any]] = []
    gold_by_split: dict[str, list[dict[str, Any]]] = {"development": [], "reserved": []}
    stats: Counter[str] = Counter()
    for index, annotation_raw in enumerate(annotations):
        filename = f"cord_test_{index:04d}.png"
        doc_id = _doc_id(filename, sources[index]["sha256"])
        annotation = _annotation(annotation_raw, index)
        record, record_stats = _gold_record(doc_id, annotation)
        stats.update(record_stats)
        gold.append(record)
        gold_by_split[splits[index]].append(record)

    output_dir.mkdir(parents=True)
    cohort: list[dict[str, Any]] = []
    by_split: dict[str, list[dict[str, Any]]] = {"development": [], "reserved": []}
    for index, source in enumerate(sources):
        filename = f"cord_test_{index:04d}.png"
        split = splits[index]
        input_dir = output_dir / ("input_development" if split == "development" else "input_reserved")
        input_dir.mkdir(exist_ok=True)
        image_path = input_dir / filename
        image_path.write_bytes(source["raw"])
        if _sha256_file(image_path) != source["sha256"]:
            raise CordSliceError(f"Staged CORD image differs from embedded image: {index}")
        item = {
            "dataset_id": "cord_v2_test",
            "source_id": f"cord-v2/test/{index:04d}",
            "family": "receipt",
            "evaluation_split": split,
            "source_path": str(image_path),
            "source_sha256": source["sha256"],
            "source_size_bytes": len(source["raw"]),
            "doc_id": _doc_id(filename, source["sha256"]),
        }
        cohort.append(item)
        by_split[split].append(item)
    files = {
        "cohort.jsonl": cohort,
        "gold.jsonl": gold,
        "cohort_development.jsonl": by_split["development"],
        "gold_development.jsonl": gold_by_split["development"],
        "cohort_reserved.jsonl": by_split["reserved"],
        "gold_reserved.jsonl": gold_by_split["reserved"],
    }
    for filename, records in files.items():
        _write_jsonl(output_dir / filename, records)
    metadata = {
        "adapter_version": ADAPTER_VERSION,
        "dataset_id": "cord_v2_test",
        "creator_dataset_url": DATASET_URL,
        "creator_dataset_revision": DATASET_REVISION,
        "creator_file": f"data/{PARQUET_NAME}",
        "creator_file_sha256": PARQUET_SHA256,
        "creator_file_bytes": parquet_path.stat().st_size,
        "dataset_license": "CC BY 4.0; attribute NAVER CLOVA and the CORD creators",
        "source_selection": "All 100 test parquet rows in pinned file order; selected before ground_truth is read.",
        "split_method": "Source-only 64-bit difference hash connected components with Hamming <=12 and aspect-ratio difference <=0.05; component SHA rank under a fixed seed assigns about 40 images to reserved. This blocks near-duplicate images, not vendors or all layout variants.",
        "split_seed": SPLIT_SEED,
        "split_stats": split_stats,
        "cohort_count": len(cohort),
        "distinct_source_sha256_count": len(source_hashes),
        "gold_count": len(gold),
        "annotation_stats": dict(sorted(stats.items())),
        "gold_scope": "Positive raw-string gt_parse summary fields and ordered menu nm/cnt/price cells only. Absent or non-scalar summary labels are unscored, not false values. Nested menu sub-items and other CORD classes are not mapped.",
        "evidence_scope": "CORD annotations have image/word boxes, not product OCR character spans; gold pages have no OCR transcript or evidence spans.",
        "holdout_scope": "Reserved test images must not be used for prompt or policy tuning. Vendor IDs are unavailable, and historical exposure cannot be ruled out; this is not a proven untouched or vendor-disjoint holdout.",
        "reader_versions": {"pyarrow": pyarrow.__version__, "pillow": Image.__version__},
        "files_sha256": {filename: _sha256_file(output_dir / filename) for filename in files},
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_cord_test_cohort(args.parquet, args.output_dir)
    print(json.dumps({
        "cohort_count": result["cohort_count"],
        "split_stats": result["split_stats"],
        "annotation_stats": result["annotation_stats"],
        "output_dir": str(args.output_dir.resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
