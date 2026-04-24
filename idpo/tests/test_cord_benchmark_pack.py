from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

import scripts.build_cord_benchmark_pack as cord_pack


def _png_bytes(color: str) -> bytes:
    image = Image.new("RGB", (8, 8), color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_extract_expected_fields_from_cord_ground_truth() -> None:
    payload = {
        "gt_parse": {
            "total": {
                "total_price": "45,500",
                "cashprice": "50,000",
                "changeprice": "4,500",
            },
            "sub_total": {
                "subtotal_price": "41,364",
                "tax_price": "4,136",
            },
        }
    }

    expected = cord_pack._extract_expected_fields(payload)

    assert expected == {
        "total_amount": "45,500",
        "cash_amount": "50,000",
        "change_amount": "4,500",
        "subtotal_amount": "41,364",
        "tax_amount": "4,136",
    }


def test_select_indices_is_deterministic() -> None:
    first = cord_pack._select_indices(10, 4, seed=17)
    second = cord_pack._select_indices(10, 4, seed=17)

    assert first == second
    assert first == sorted(first)
    assert len(first) == 4


def test_build_benchmark_pack_writes_images_labels_and_pack(tmp_path: Path) -> None:
    repo_root = tmp_path
    out_dir = repo_root / "datasets" / "derived" / "cord_validation_2_seed17"
    records = [
        {
            "image": {"bytes": _png_bytes("red"), "path": None},
            "ground_truth": json.dumps(
                {
                    "meta": {"image_id": 11},
                    "gt_parse": {
                        "total": {"total_price": "1000", "cashprice": "1000"},
                    },
                }
            ),
        },
        {
            "image": {"bytes": _png_bytes("blue"), "path": None},
            "ground_truth": json.dumps(
                {
                    "meta": {"image_id": 12},
                    "gt_parse": {
                        "total": {"total_price": "2200", "changeprice": "300"},
                        "sub_total": {"subtotal_price": "2000", "tax_price": "200"},
                    },
                }
            ),
        },
    ]

    payload = cord_pack.build_benchmark_pack(
        records,
        out_dir,
        repo_root=repo_root,
        split="validation",
        seed=17,
        limit=2,
    )

    pack_path = out_dir / "pack.json"
    manifest_path = out_dir / "manifest.json"

    assert pack_path.exists()
    assert manifest_path.exists()
    assert payload["pack"]["field_mapping_version"] == cord_pack.FIELD_MAPPING_VERSION
    assert len(payload["pack"]["cases"]) == 2

    first_case = payload["pack"]["cases"][0]
    first_image = repo_root / first_case["path"]
    assert first_image.exists()
    assert first_image.suffix == ".png"
    assert first_case["fields"]["total_amount"] == "Receipt total amount paid"

    second_item = payload["manifest"]["items"][1]
    second_label = repo_root / second_item["label_path"]
    assert second_label.exists()
    assert "with_subtotal" in payload["pack"]["cases"][1]["tags"]
