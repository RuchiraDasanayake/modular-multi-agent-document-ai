"""Build a benchmark pack from the pre-derived CORD labeled datasets.

Reads images + labels from datasets/derived/cord_validation_N_seed17/
and writes a benchmark pack JSON compatible with run_idpo_benchmark.py.

Usage:
  python scripts/build_cord_pack_from_derived.py --size 5  --out datasets/cord_pack_5.json
  python scripts/build_cord_pack_from_derived.py --size 20 --out datasets/cord_pack_20.json
  python scripts/build_cord_pack_from_derived.py --size 50 --out datasets/cord_pack_50.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DERIVED_ROOT = REPO_ROOT / "datasets" / "derived"

FIELD_DESCRIPTIONS = {
    "total_amount":    "Final total numeric amount on the receipt. Number only, no currency symbol.",
    "subtotal_amount": "Subtotal before tax. Number only.",
    "tax_amount":      "Tax amount. Number only.",
    "cash_amount":     "Cash paid by customer. Number only.",
    "change_amount":   "Change returned to customer. Number only.",
}

TAGS = ["noisy_ocr", "table", "scanned", "receipt"]


def _extract_expected(gt_parse: dict) -> dict[str, str]:
    total = gt_parse.get("total", {}) or {}
    sub = gt_parse.get("sub_total", {}) or {}
    result: dict[str, str] = {}

    def _clean(v: object) -> str:
        s = str(v or "").strip()
        # Strip currency prefix and whitespace
        import re
        s = re.sub(r"^[^\d\-\.]+", "", s).strip()
        return s

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

    # Drop zero-value fields (not worth scoring against "0")
    return {k: v for k, v in result.items() if v and v not in {"0", "0.0", "0,0"}}


def build_pack(size: int, out_path: Path) -> None:
    dir_name = f"cord_validation_{size}_seed17"
    data_dir = DERIVED_ROOT / dir_name
    if not data_dir.exists():
        # Fall back to the 100-sample set and take first N
        data_dir = DERIVED_ROOT / "cord_validation_100_seed17"
        print(f"[warn] {dir_name} not found, using cord_validation_100_seed17 (first {size} samples)")

    images_dir = data_dir / "images"
    labels_dir = data_dir / "labels"

    image_files = sorted(images_dir.glob("*.png"))[:size]
    if not image_files:
        sys.exit(f"No images found in {images_dir}")

    cases = []
    skipped = 0
    for img_path in image_files:
        stem = img_path.stem  # e.g. cord_validation_0000
        label_path = labels_dir / f"{stem}.json"
        if not label_path.exists():
            skipped += 1
            continue

        gt = json.loads(label_path.read_text(encoding="utf-8"))
        gt_parse = gt.get("gt_parse", {})
        expected = _extract_expected(gt_parse)
        if not expected:
            skipped += 1
            continue

        cases.append({
            "case_id": stem,
            "tags": TAGS,
            "path": str(img_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "fields": {k: FIELD_DESCRIPTIONS[k] for k in expected},
            "expected": expected,
        })

    pack = {
        "name": f"cord_v2_labeled_{size}",
        "description": f"CORD v2 receipts — {len(cases)} labeled samples (seed17).",
        "cases": cases,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written {len(cases)} cases to {out_path}  (skipped {skipped})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=20)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or (REPO_ROOT / "datasets" / f"cord_pack_{args.size}.json")
    build_pack(args.size, out)


if __name__ == "__main__":
    main()
