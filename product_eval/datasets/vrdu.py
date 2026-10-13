"""Build a PDF execution cohort and conservative scalar gold from pinned VRDU.

The cohort is selected by filename before annotations are inspected. The gold
adapter uses only the dataset's own OCR and labels; it never reads predictions.
Linked rows are represented as ordered, row-indexed values of VRDU's published
field IDs. This derived representation is not the official VRDU scoring format.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError, validate_record

DATASET_COMMIT = "04a4df7ac5cc694e51c48115c03fe428f0e240cc"
ADAPTER_VERSION = 1
FAMILY_QUOTAS = {"registration-form": 1500, "ad-buy-form": 500}
SELECTION_SEED = "vrdu-v1-cohort"


class DatasetError(ValueError):
    """The source tree or annotations are unsuitable for a frozen cohort."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _doc_id(filename: str, source_sha256: str) -> str:
    # Keep in sync with idpo.product_auto.workflow._doc_id(..., index=0).
    return hashlib.sha256(f"{filename}\0{source_sha256}\0{0}".encode()).hexdigest()[:32]


def _selection_key(family: str, filename: str) -> tuple[str, str]:
    rank = hashlib.sha256(f"{SELECTION_SEED}\0{family}/{filename}".encode()).hexdigest()
    return rank, filename


def _verify_commit(root: Path) -> None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise DatasetError(f"Cannot verify VRDU Git commit at {root}") from exc
    found = result.stdout.strip().lower()
    if found != DATASET_COMMIT:
        raise DatasetError(f"VRDU commit must be {DATASET_COMMIT}, found {found}")


def _verify_source_archive(root: Path, source_archive: Path) -> dict[str, str]:
    """Check every extracted source byte against the pinned codeload ZIP."""
    archive_path = source_archive.resolve()
    if not archive_path.is_file():
        raise DatasetError(f"VRDU source archive missing: {archive_path}")
    prefix = f"vrdu-{DATASET_COMMIT}/"
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = {
                info.filename[len(prefix) :]: info
                for info in archive.infolist()
                if not info.is_dir() and info.filename.startswith(prefix)
            }
            if not members or len(members) != len([info for info in archive.infolist() if not info.is_dir()]):
                raise DatasetError("VRDU archive does not contain only the pinned commit prefix")
            extracted = {
                path.relative_to(root).as_posix(): path
                for path in root.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(root).parts
            }
            if set(members) != set(extracted):
                raise DatasetError(
                    "VRDU archive/extracted tree mismatch: "
                    f"archive-only={len(set(members) - set(extracted))}, "
                    f"extracted-only={len(set(extracted) - set(members))}"
                )
            for name, info in members.items():
                digest_archive = hashlib.sha256()
                digest_extracted = hashlib.sha256()
                with archive.open(info) as archived, extracted[name].open("rb") as local:
                    while True:
                        archive_chunk = archived.read(1024 * 1024)
                        local_chunk = local.read(1024 * 1024)
                        if not archive_chunk and not local_chunk:
                            break
                        digest_archive.update(archive_chunk)
                        digest_extracted.update(local_chunk)
                if digest_archive.digest() != digest_extracted.digest():
                    raise DatasetError(f"VRDU extracted file differs from pinned archive: {name}")
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise DatasetError(f"Cannot verify VRDU source archive: {archive_path}") from exc
    return {"method": "pinned_codeload_archive", "archive_path": str(archive_path), "archive_sha256": _sha256_file(archive_path)}


def _pdf_files(root: Path, family: str) -> dict[str, Path]:
    directory = root / family / "main" / "pdfs"
    if not directory.is_dir():
        raise DatasetError(f"VRDU PDF directory missing: {directory}")
    files = {path.name: path.resolve() for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"}
    if not files:
        raise DatasetError(f"No PDFs in {directory}")
    return files


def _load_meta(root: Path, family: str) -> tuple[dict[str, str], set[str]]:
    path = root / family / "main" / "meta.json"
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        matchers = meta["entity_name_to_match_func"]
        appearance = meta.get("entity_appearance_pattern", {})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DatasetError(f"Invalid VRDU metadata: {path}") from exc
    if not isinstance(matchers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in matchers.items()):
        raise DatasetError(f"Invalid VRDU entity map: {path}")
    if not isinstance(appearance, dict):
        raise DatasetError(f"Invalid VRDU appearance map: {path}")
    unknown = set(appearance) - set(matchers)
    if unknown:
        raise DatasetError(f"VRDU appearance map has unknown fields: {sorted(unknown)}")
    line_items = {name for name, pattern in appearance.items() if pattern == "line_item"}
    if any(pattern not in {"line_item", "unrepeated"} for pattern in appearance.values()):
        raise DatasetError(f"Unsupported VRDU appearance pattern: {path}")
    return matchers, line_items


def _pages(ocr: Any) -> tuple[str, list[dict[str, Any]], list[tuple[int, int]]]:
    if not isinstance(ocr, dict) or not isinstance(ocr.get("text"), str) or not isinstance(ocr.get("pages"), list):
        raise DatasetError("missing_ocr_text_or_pages")
    text = ocr["text"]
    pages: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []
    previous_end = 0
    for index, item in enumerate(ocr["pages"]):
        if not isinstance(item, dict) or item.get("page_id") != index:
            raise DatasetError("invalid_page_id")
        segment = item.get("segment")
        if (
            not isinstance(segment, list)
            or len(segment) != 2
            or any(type(offset) is not int for offset in segment)
            or not previous_end <= segment[0] < segment[1] <= len(text)
        ):
            raise DatasetError("invalid_page_segment")
        start, end = segment
        pages.append({"page": index + 1, "text": text[start:end]})
        spans.append((start, end))
        previous_end = end
    if not pages:
        raise DatasetError("no_ocr_pages")
    return text, pages, spans


def _evidence(
    value_entry: Any, ocr_text: str, page_spans: list[tuple[int, int]]
) -> dict[str, Any] | None:
    if not isinstance(value_entry, list) or len(value_entry) < 3 or not isinstance(value_entry[0], str):
        return None
    raw_text = value_entry[0]
    segments = value_entry[2]
    if not isinstance(segments, list) or len(segments) != 1:
        return None
    segment = segments[0]
    if (
        not isinstance(segment, list)
        or len(segment) != 2
        or any(type(offset) is not int for offset in segment)
    ):
        return None
    start, end = segment
    if not 0 <= start < end <= len(ocr_text) or ocr_text[start:end] != raw_text:
        return None
    for index, (page_start, page_end) in enumerate(page_spans):
        if page_start <= start < end <= page_end:
            return {
                "page": index + 1,
                "start": start - page_start,
                "end": end - page_start,
                "quote": raw_text,
            }
    return None


def _gold_record(
    row: dict[str, Any],
    doc_id: str,
    matchers: dict[str, str],
    line_items: set[str],
) -> tuple[dict[str, Any], Counter[str]]:
    ocr_text, pages, page_spans = _pages(row.get("ocr"))
    scalar_fields = [name for name in matchers if name not in line_items]
    raw_values: dict[str, list[Any]] = {}
    linked_rows: list[dict[str, str]] = []
    stats: Counter[str] = Counter()
    annotations = row.get("annotations")
    if not isinstance(annotations, list):
        raise DatasetError("missing_annotations")
    for annotation in annotations:
        if not isinstance(annotation, list) or len(annotation) != 2:
            raise DatasetError("malformed_annotation")
        name, entries = annotation
        if isinstance(name, list):
            if not name or len(name) != len(set(name)) or any(field not in line_items for field in name):
                raise DatasetError("unexpected_nested_annotation")
            if not isinstance(entries, list) or not entries:
                raise DatasetError("malformed_linked_rows")
            for group in entries:
                if not isinstance(group, list) or len(group) != len(name):
                    raise DatasetError("linked_row_field_count_mismatch")
                linked_row: dict[str, str] = {}
                for field, value_entry in zip(name, group):
                    if not isinstance(value_entry, list) or len(value_entry) < 3 or not isinstance(value_entry[0], str):
                        raise DatasetError("malformed_linked_value")
                    value = value_entry[0].strip()
                    if not value:
                        raise DatasetError("empty_linked_value")
                    linked_row[field] = value
                linked_rows.append(linked_row)
                stats["linked_rows"] += 1
            continue
        if not isinstance(name, str) or name not in scalar_fields:
            raise DatasetError("unknown_or_nested_scalar_annotation")
        if name in raw_values or not isinstance(entries, list) or not entries:
            raise DatasetError(f"duplicate_or_empty_annotation:{name}")
        raw_values[name] = entries

    gold_schema: list[dict[str, Any]] = []
    gold_values: list[dict[str, Any]] = []
    for name, matcher in matchers.items():
        field_schema: dict[str, Any] = {
            "field_id": name,
            "type": "array[object]" if name in line_items else "string",
            "critical": False,  # VRDU does not publish business criticality.
            "source_match_func": matcher,
        }
        if name in line_items:
            # Row indices preserve the linking published in nested annotations.
            occurrences = [
                {"row": row_index, "value": row[name]}
                for row_index, row in enumerate(linked_rows)
                if name in row
            ]
            gold_schema.append(field_schema)
            gold_values.append({"field_id": name, "value": occurrences or None})
            continue
        gold_schema.append(field_schema)
        entries = raw_values.get(name)
        if entries is None:
            gold_values.append({"field_id": name, "value": None})
            continue
        values: list[str] = []
        for entry in entries:
            if not isinstance(entry, list) or len(entry) < 3 or not isinstance(entry[0], str):
                raise DatasetError(f"malformed_scalar_value:{name}")
            normalized = entry[0].strip()
            if not normalized:
                raise DatasetError(f"empty_scalar_value:{name}")
            values.append(normalized)
        distinct = set(values)
        if len(distinct) > 1:
            field_schema["type"] = "array[string]"
            value_record: dict[str, Any] = {"field_id": name, "value": values}
            stats["divergent_scalar_fields_as_ordered_lists"] += 1
        else:
            value_record = {"field_id": name, "value": values[0]}
            for entry in entries:
                evidence = _evidence(entry, ocr_text, page_spans)
                if evidence is not None:
                    value_record["evidence"] = evidence
                    break
            if "evidence" not in value_record:
                stats["scalar_gold_values_without_single_span_evidence"] += 1
        if len(entries) > 1:
            stats["fields_with_duplicate_surface_values"] += 1
        gold_values.append(value_record)
    record = {
        "contract_version": 1,
        "doc_id": doc_id,
        "pages": pages,
        "gold_schema": gold_schema,
        "gold_values": gold_values,
    }
    validate_record(record, kind="gold", label=f"VRDU {row.get('filename')!r}")
    return record, stats


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")


def build_vrdu_cohort(
    dataset_root: str | Path,
    output_dir: str | Path,
    *,
    quotas: dict[str, int] | None = None,
    verify_commit: bool = True,
    source_archive: str | Path | None = None,
) -> dict[str, Any]:
    """Freeze a label-independent PDF cohort and derive supported scalar gold.

    The output directory must be new. `verify_commit=False` is only for small,
    synthetic tests; production CLI verifies Git HEAD or a pinned ZIP snapshot.
    """
    root = Path(dataset_root).resolve()
    source_verification: dict[str, str] = {"method": "synthetic_test_fixture"}
    if verify_commit:
        if source_archive is None:
            _verify_commit(root)
            source_verification = {"method": "git_head", "commit": DATASET_COMMIT}
        else:
            source_verification = _verify_source_archive(root, Path(source_archive))
    selected_quotas = dict(FAMILY_QUOTAS if quotas is None else quotas)
    if set(selected_quotas) != set(FAMILY_QUOTAS) or any(type(n) is not int or n < 0 for n in selected_quotas.values()):
        raise DatasetError("quotas must specify non-negative counts for both VRDU families")
    output = Path(output_dir).resolve()
    if output.exists():
        raise DatasetError(f"Output directory already exists: {output}")

    cohort: list[dict[str, Any]] = []
    gold: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    family_counts: dict[str, dict[str, int]] = {}
    stats: Counter[str] = Counter()
    source_hashes: set[str] = set()
    doc_ids: set[str] = set()
    for family in FAMILY_QUOTAS:
        pdfs = _pdf_files(root, family)
        quota = selected_quotas[family]
        if len(pdfs) < quota:
            raise DatasetError(f"{family}: only {len(pdfs)} PDFs for quota {quota}")
        selected_names = sorted(pdfs, key=lambda name: _selection_key(family, name))[:quota]
        selected = {name: pdfs[name] for name in selected_names}
        matchers, line_items = _load_meta(root, family)
        dataset_path = root / family / "main" / "dataset.jsonl.gz"
        if not dataset_path.is_file():
            raise DatasetError(f"VRDU annotations missing: {dataset_path}")
        seen: set[str] = set()
        selected_rows: dict[str, dict[str, Any]] = {}
        try:
            with gzip.open(dataset_path, "rt", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    row = json.loads(line)
                    if not isinstance(row, dict) or not isinstance(row.get("filename"), str):
                        raise DatasetError(f"{dataset_path}:{line_number}: invalid row/filename")
                    filename = row["filename"]
                    if filename != Path(filename).name or filename in seen:
                        raise DatasetError(f"{dataset_path}:{line_number}: unsafe or duplicate filename")
                    if row.get("file_path") != f"./pdfs/{filename}":
                        raise DatasetError(f"{dataset_path}:{line_number}: PDF path differs from filename")
                    seen.add(filename)
                    if filename in selected:
                        selected_rows[filename] = row
        except (OSError, EOFError, UnicodeError, json.JSONDecodeError) as exc:
            raise DatasetError(f"Cannot read VRDU annotations: {dataset_path}") from exc
        if seen != set(pdfs):
            raise DatasetError(
                f"{family}: row/PDF pairing differs; missing PDF rows={len(set(pdfs) - seen)}, "
                f"missing PDF files={len(seen - set(pdfs))}"
            )
        gold_before_family = len(gold)
        for filename in sorted(selected):
            pdf = selected[filename]
            source_sha256 = _sha256_file(pdf)
            doc_id = _doc_id(filename, source_sha256)
            if source_sha256 in source_hashes or doc_id in doc_ids:
                raise DatasetError(f"Duplicate PDF content or doc_id in selected cohort: {family}/{filename}")
            source_hashes.add(source_sha256)
            doc_ids.add(doc_id)
            source_id = f"{family}/{filename}"
            cohort.append({
                "dataset_id": "vrdu",
                "source_id": source_id,
                "family": family,
                "source_path": str(pdf),
                "source_sha256": source_sha256,
                "source_size_bytes": pdf.stat().st_size,
                "doc_id": doc_id,
            })
            try:
                gold_record, record_stats = _gold_record(selected_rows[filename], doc_id, matchers, line_items)
            except (DatasetError, ContractError) as exc:
                exclusions.append({"dataset_id": "vrdu", "source_id": source_id, "doc_id": doc_id, "reason": str(exc)})
                continue
            gold.append(gold_record)
            stats.update(record_stats)
        family_counts[family] = {
            "creator_pdf_count": len(pdfs),
            "creator_annotation_rows": len(seen),
            "cohort_count": quota,
            "gold_count": len(gold) - gold_before_family,
        }

    output.mkdir(parents=True)
    cohort_path = output / "cohort.jsonl"
    gold_path = output / "gold.jsonl"
    exclusions_path = output / "exclusions.jsonl"
    _write_jsonl(cohort_path, cohort)
    _write_jsonl(gold_path, gold)
    _write_jsonl(exclusions_path, exclusions)
    metadata = {
        "adapter_version": ADAPTER_VERSION,
        "dataset_id": "vrdu",
        "dataset_repository": "https://github.com/google-research-datasets/vrdu",
        "dataset_commit": DATASET_COMMIT,
        "source_verification": source_verification,
        "selection": "Lowest SHA256 ranks of 'vrdu-v1-cohort\\0<family>/<filename>' per family; output sorted by filename. Annotations never influence selection.",
        "selection_seed": SELECTION_SEED,
        "families": family_counts,
        "cohort_count": len(cohort),
        "distinct_source_sha256_count": len(source_hashes),
        "gold_count": len(gold),
        "gold_exclusion_count": len(exclusions),
        "gold_exclusion_reasons": dict(sorted(Counter(item["reason"] for item in exclusions).items())),
        "derived_linked_row_representation": "Each published line-item field ID has an ordered array of {row, value}; row is its zero-based ordinal in the document's linked annotations. v1 cannot score per-row evidence or official VRDU matching.",
        "gold_value_normalization": "Only leading and trailing whitespace is stripped from each published OCR surface value. Identical repeated scalar values collapse to one; divergent repeats stay in published order as an array.",
        "gold_field_type": "Raw OCR surface strings, ordered string arrays for divergent scalar repeats, and row-indexed arrays for linked fields; published matcher retained as source_match_func but not applied by v1 scorer",
        "gold_criticality": "All false because VRDU provides no business criticality labels; do not use correct-auto-release metrics for this cohort.",
        "evidence_limitation": "Gold spans index official VRDU OCR. A candidate re-OCR of the PDF may use different text and offsets; evidence validity requires alignment before interpretation.",
        "annotation_stats": dict(sorted(stats.items())),
        "files_sha256": {
            path.name: _sha256_file(path)
            for path in (cohort_path, gold_path, exclusions_path)
        },
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze a pinned VRDU 2,000-PDF cohort and conservative scalar gold")
    parser.add_argument("--dataset-root", required=True, type=Path, help="Checkout of google-research-datasets/vrdu")
    parser.add_argument("--source-archive", type=Path, help="Pinned codeload ZIP when using an extracted archive instead of Git checkout")
    parser.add_argument("--output-dir", required=True, type=Path, help="New directory for cohort, gold and metadata")
    args = parser.parse_args()
    metadata = build_vrdu_cohort(args.dataset_root, args.output_dir, source_archive=args.source_archive)
    print(json.dumps({
        "cohort_count": metadata["cohort_count"],
        "distinct_source_sha256_count": metadata["distinct_source_sha256_count"],
        "gold_count": metadata["gold_count"],
        "gold_exclusion_count": metadata["gold_exclusion_count"],
        "output_dir": str(args.output_dir.resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
