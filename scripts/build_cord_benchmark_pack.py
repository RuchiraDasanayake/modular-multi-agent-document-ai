"""Build a deterministic CORD v2 subset in the existing IDPO benchmark-pack format."""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from datasets import load_dataset
from PIL import Image

FIELD_DESCRIPTIONS = {
    "total_amount": "The final total numeric amount on the receipt. Extract only the number, not the label.",
    "cash_amount": "The cash amount paid by the customer. Extract only the number.",
    "change_amount": "The change amount returned to the customer. Extract only the number.",
    "subtotal_amount": "The subtotal amount before the final total. Extract only the number.",
    "tax_amount": "The tax amount on the receipt. Extract only the number.",
}
FIELD_MAPPING_VERSION = "cord_totals_v1"


def _load_split_records(dataset_root: Path, split: str) -> list[dict[str, Any]]:
    data_dir = dataset_root / "data"
    files = sorted(str(path) for path in data_dir.glob(f"{split}-*.parquet"))
    if not files:
        raise SystemExit(f"No parquet files found for split '{split}' under {data_dir}")
    dataset = load_dataset("parquet", data_files={split: files})
    return [dataset[split][index] for index in range(len(dataset[split]))]


def _select_indices(count: int, limit: int | None, seed: int) -> list[int]:
    if count <= 0:
        return []
    if limit is None or limit >= count:
        return list(range(count))
    rng = random.Random(seed)
    return sorted(rng.sample(range(count), limit))


def _extract_expected_fields(ground_truth: str | dict[str, Any]) -> dict[str, str]:
    payload = json.loads(ground_truth) if isinstance(ground_truth, str) else ground_truth
    gt_parse = payload.get("gt_parse", {}) if isinstance(payload, dict) else {}
    total = gt_parse.get("total", {}) if isinstance(gt_parse, dict) else {}
    sub_total = gt_parse.get("sub_total", {}) if isinstance(gt_parse, dict) else {}

    expected: dict[str, str] = {}
    _copy_if_present(expected, "total_amount", total.get("total_price"))
    _copy_if_present(expected, "cash_amount", total.get("cashprice"))
    _copy_if_present(expected, "change_amount", total.get("changeprice"))
    _copy_if_present(expected, "subtotal_amount", sub_total.get("subtotal_price"))
    _copy_if_present(expected, "tax_amount", sub_total.get("tax_price"))
    return expected


def _copy_if_present(target: dict[str, str], key: str, value: object) -> None:
    text = str(value or "").strip()
    if text:
        target[key] = text


def _field_descriptions(expected: dict[str, str]) -> dict[str, str]:
    return {key: FIELD_DESCRIPTIONS[key] for key in FIELD_DESCRIPTIONS if key in expected}


def _case_tags(split: str, expected: dict[str, str]) -> list[str]:
    tags = ["cord", "external", "receipt", split, FIELD_MAPPING_VERSION]
    if "subtotal_amount" in expected:
        tags.append("with_subtotal")
    if "cash_amount" in expected:
        tags.append("with_cash")
    if "change_amount" in expected:
        tags.append("with_change")
    return tags


def _save_image(image_payload: dict[str, Any], out_path: Path) -> None:
    image_bytes = image_payload.get("bytes")
    if not image_bytes:
        raise ValueError(f"Missing image bytes for {out_path.name}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(image_bytes)) as image:
        image.save(out_path, format="PNG")


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path.resolve())


def build_benchmark_pack(
    records: list[dict[str, Any]],
    out_dir: Path,
    *,
    repo_root: Path,
    split: str,
    seed: int,
    limit: int | None = None,
) -> dict[str, Any]:
    selected_indices = _select_indices(len(records), limit, seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    manifest_items: list[dict[str, Any]] = []

    for subset_index, source_index in enumerate(selected_indices):
        record = records[source_index]
        expected = _extract_expected_fields(record.get("ground_truth", {}))
        if not expected:
            continue

        case_id = f"cord_{split}_{subset_index:04d}"
        image_path = images_dir / f"{case_id}.png"
        label_path = labels_dir / f"{case_id}.json"
        _save_image(record["image"], image_path)

        ground_truth = json.loads(record["ground_truth"])
        label_path.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
        meta = ground_truth.get("meta", {}) if isinstance(ground_truth, dict) else {}
        case = {
            "case_id": case_id,
            "tags": _case_tags(split, expected),
            "path": _relative_or_absolute(image_path, repo_root),
            "fields": _field_descriptions(expected),
            "expected": expected,
        }
        cases.append(case)
        manifest_items.append(
            {
                "case_id": case_id,
                "source_index": source_index,
                "split": split,
                "image_id": meta.get("image_id"),
                "image_path": case["path"],
                "label_path": _relative_or_absolute(label_path, repo_root),
                "expected": expected,
                "tags": case["tags"],
            }
        )

    pack = {
        "name": f"cord_{split}_{len(cases)}_{FIELD_MAPPING_VERSION}",
        "description": "Deterministic CORD v2 subset staged in the IDPO benchmark-pack format.",
        "source_dataset": "naver-clova-ix/cord-v2",
        "split": split,
        "seed": seed,
        "limit": limit if limit is not None else len(records),
        "field_mapping_version": FIELD_MAPPING_VERSION,
        "cases": cases,
    }
    manifest = {
        "name": pack["name"],
        "source_dataset": pack["source_dataset"],
        "split": split,
        "seed": seed,
        "selected_count": len(cases),
        "field_mapping_version": FIELD_MAPPING_VERSION,
        "items": manifest_items,
    }
    (out_dir / "pack.json").write_text(json.dumps(pack, indent=2), encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"pack": pack, "manifest": manifest, "out_dir": str(out_dir.resolve())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", default="datasets/external/cord-v2")
    parser.add_argument("--split", default="validation", choices=("train", "validation", "test"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    dataset_root = (REPO_ROOT / args.dataset_root).resolve()
    default_out_dir = REPO_ROOT / "datasets" / "derived" / f"cord_{args.split}_{args.limit}_seed{args.seed}"
    out_dir = Path(args.out_dir).resolve() if args.out_dir else default_out_dir.resolve()
    if out_dir.exists():
        if not args.overwrite:
            raise SystemExit(f"Output directory already exists: {out_dir}. Use --overwrite to replace it.")
        shutil.rmtree(out_dir)

    records = _load_split_records(dataset_root, args.split)
    payload = build_benchmark_pack(
        records,
        out_dir,
        repo_root=REPO_ROOT,
        split=args.split,
        seed=args.seed,
        limit=args.limit,
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
