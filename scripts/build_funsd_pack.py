"""Build a benchmark pack from FUNSD testing_data annotations."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ANN_DIR = REPO_ROOT / "datasets/FUNSD/testing_data/annotations"
IMG_DIR = REPO_ROOT / "datasets/FUNSD/testing_data/images"
OUT_PATH = REPO_ROOT / "datasets/funsd_pack_20.json"

TARGET_FIELDS = ["DATE", "TO", "FROM"]

FIELD_DESCRIPTIONS = {
    "date": "The date on the form (as written). Extract exactly as it appears.",
    "recipient": "The recipient name or department in the TO field.",
    "sender": "The sender name or department in the FROM field.",
}

FIELD_MAP = {"DATE": "date", "TO": "recipient", "FROM": "sender"}


def extract_qa(form_data: list) -> dict[str, str]:
    id_map = {item["id"]: item for item in form_data}
    qa: dict[str, list[str]] = defaultdict(list)
    for item in form_data:
        if item.get("label") != "question":
            continue
        q_raw = item.get("text", "").strip().upper().rstrip(":").rstrip("?").strip()
        if q_raw not in TARGET_FIELDS:
            continue
        for pair in item.get("linking", []):
            other_id = pair[1] if pair[0] == item["id"] else pair[0]
            other = id_map.get(other_id)
            if other and other.get("label") == "answer":
                text = other.get("text", "").strip()
                if text:
                    qa[q_raw].append(text)
    return {FIELD_MAP[k]: " ".join(v) for k, v in qa.items() if v}


def find_image(stem: str) -> Path | None:
    for ext in [".png", ".jpg", ".jpeg"]:
        candidate = IMG_DIR / (stem + ext)
        if candidate.exists():
            return candidate
    return None


def main() -> None:
    cases = []
    for ann_file in sorted(ANN_DIR.glob("*.json")):
        data = json.loads(ann_file.read_text(encoding="utf-8", errors="replace"))
        found = extract_qa(data["form"])
        if len(found) < 2:
            continue
        img = find_image(ann_file.stem)
        if not img:
            continue
        rel_path = img.relative_to(REPO_ROOT).as_posix()
        cases.append({
            "case_id": f"funsd_{ann_file.stem}",
            "tags": ["form", "scanned", "business_form"],
            "path": rel_path,
            "fields": {k: FIELD_DESCRIPTIONS[k] for k in found},
            "expected": found,
        })

    cases = cases[:20]  # cap at 20 for first run
    pack = {
        "name": "funsd_labeled_20",
        "description": "FUNSD testing forms — 20 samples with DATE, TO, FROM fields.",
        "batch_mode": "single_run_per_condition",
        "shared_fields": FIELD_DESCRIPTIONS,
        "cases": cases,
    }
    OUT_PATH.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {OUT_PATH}")
    for c in cases[:5]:
        print(f"  {c['case_id']}: {c['expected']}")


if __name__ == "__main__":
    main()
