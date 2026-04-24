"""Build a benchmark pack from the pre-derived CORD labeled datasets.

Reads images + labels from datasets/derived/cord_validation_N_seed17/
and writes a benchmark pack JSON compatible with run_idpo_benchmark.py.

Usage:
  python scripts/build_cord_pack_from_derived.py --size 5  --out datasets/cord_pack_5.json
  python scripts/build_cord_pack_from_derived.py --size 20 --out datasets/cord_pack_20.json
  python scripts/build_cord_pack_from_derived.py --size 50 --out datasets/cord_pack_50.json
  python scripts/build_cord_pack_from_derived.py --size 10 --offset 5 --source-dir cord_validation_20_seed17 --out datasets/cord_pack_10_holdout.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DERIVED_ROOT = REPO_ROOT / "datasets" / "derived"

FIELD_DESCRIPTIONS = {
    "total_amount": "Final total numeric amount on the receipt. Number only, no currency symbol.",
    "subtotal_amount": "Subtotal before tax. Number only.",
    "tax_amount": "Tax amount. Number only.",
    "cash_amount": "Cash paid by customer. Number only.",
    "change_amount": "Change returned to customer. Number only.",
}

TAGS = ["noisy_ocr", "table", "scanned", "receipt"]


def _extract_expected(gt_parse: dict) -> dict[str, str]:
    total = gt_parse.get("total", {}) or {}
    sub = gt_parse.get("sub_total", {}) or {}
    result: dict[str, str] = {}

    def _clean(value: object) -> str:
        text = str(value or "").strip()
        return re.sub(r"^[^\d\-\.]+", "", text).strip()

    if total.get("total_price"):
        result["total_amount"] = _clean(total["total_price"])
    if total.get("cashprice"):
        result["cash_amount"] = _clean(total["cashprice"])
    if total.get("changeprice"):
        result["change_amount"] = _clean(total["changeprice"])
    if sub.get("subtotal_price"):
        result["subtotal_amount"] = _clean(sub["subtotal_price"])
    if sub.get("tax_price"):
        result["tax_amount"] = _clean(sub["tax_price"])

    return {key: value for key, value in result.items() if value and value not in {"0", "0.0", "0,0"}}


def build_pack(size: int, out_path: Path, *, offset: int = 0, source_dir: str | None = None) -> None:
    dir_name = source_dir or f"cord_validation_{size}_seed17"
    data_dir = DERIVED_ROOT / dir_name
    if not data_dir.exists():
        data_dir = DERIVED_ROOT / "cord_validation_100_seed17"
        print(f"[warn] {dir_name} not found, using cord_validation_100_seed17 (offset {offset}, first {size} samples)")

    images_dir = data_dir / "images"
    labels_dir = data_dir / "labels"

    image_files = sorted(images_dir.glob("*.png"))[offset:offset + size]
    if not image_files:
        sys.exit(f"No images found in {images_dir}")

    cases: list[dict[str, object]] = []
    skipped = 0
    for img_path in image_files:
        stem = img_path.stem
        label_path = labels_dir / f"{stem}.json"
        if not label_path.exists():
            skipped += 1
            continue

        gt = json.loads(label_path.read_text(encoding="utf-8"))
        expected = _extract_expected(gt.get("gt_parse", {}))
        if not expected:
            skipped += 1
            continue

        cases.append(
            {
                "case_id": stem,
                "tags": TAGS,
                "path": str(img_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "fields": {key: FIELD_DESCRIPTIONS[key] for key in expected},
                "expected": expected,
            }
        )

    pack = {
        "name": f"cord_v2_labeled_{size}_offset_{offset}",
        "description": f"CORD v2 receipts - {len(cases)} labeled samples (seed17, offset {offset}).",
        "batch_mode": "single_run_per_condition",
        "shared_fields": FIELD_DESCRIPTIONS,
        "cases": cases,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written {len(cases)} cases to {out_path}  (skipped {skipped})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--source-dir", type=str, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or (REPO_ROOT / "datasets" / f"cord_pack_{args.size}.json")
    build_pack(args.size, out, offset=max(args.offset, 0), source_dir=args.source_dir)


if __name__ == "__main__":
    main()
