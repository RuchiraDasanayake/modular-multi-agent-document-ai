"""Build the CORD v2 validation holdout pack: records of the 100-record sample that cord_pack_50 does not use.

Run the derived-pack builder first so both samples exist (same split and seed):

  python scripts/build_cord_benchmark_pack.py --split validation --limit 50 --seed 17
  python scripts/build_cord_benchmark_pack.py --split validation --limit 100 --seed 17
  python scripts/build_cord_holdout_pack.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DERIVED_ROOT = REPO_ROOT / "datasets" / "derived"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_holdout(used_dir: Path, pool_dir: Path, template_path: Path) -> dict:
    used_indices = {item["source_index"] for item in _read_json(used_dir / "manifest.json")["items"]}
    pool_manifest = _read_json(pool_dir / "manifest.json")
    holdout_ids = {item["case_id"] for item in pool_manifest["items"] if item["source_index"] not in used_indices}
    cases = [case for case in _read_json(pool_dir / "pack.json")["cases"] if case["case_id"] in holdout_ids]
    for case in cases:
        case["case_id"] = case["case_id"].replace("cord_validation_", "cord_holdout_")

    pack = {key: value for key, value in _read_json(template_path).items() if key != "cases"}
    pack["name"] = f"cord_validation_holdout_{len(cases)}"
    pack["description"] = (
        f"CORD v2 validation records in {pool_dir.name} that {used_dir.name} does not use; untouched during tuning."
    )
    pack["cases"] = cases
    return pack


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--used", default="cord_validation_50_seed17", help="derived sample used for development")
    parser.add_argument("--pool", default="cord_validation_100_seed17", help="larger derived sample to draw from")
    parser.add_argument("--template", default="datasets/cord_pack_50.json", help="pack whose settings are copied")
    parser.add_argument("--out", default="datasets/cord_holdout_50.json")
    args = parser.parse_args()

    pack = build_holdout(DERIVED_ROOT / args.used, DERIVED_ROOT / args.pool, REPO_ROOT / args.template)
    out = REPO_ROOT / args.out
    out.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    print(f"Wrote {len(pack['cases'])} holdout cases to {args.out}")


if __name__ == "__main__":
    main()
