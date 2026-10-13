"""Source-free contract tests; never load the Granite model or benchmark data."""

from __future__ import annotations

import json

import pytest

from product_eval import granite_source_free_smoke as smoke


def _assets(tmp_path, monkeypatch):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    names = ["model.safetensors", *(f"asset-{index}.json" for index in range(12))]
    rows = []
    for index, name in enumerate(names):
        content = f"asset-{index}".encode()
        path = model_dir / name
        path.write_bytes(content)
        rows.append({"path": name, "size_bytes": len(content),
                     "sha256": smoke.sha256_file(path)})
    monkeypatch.setattr(smoke, "MODEL_SHA256", rows[0]["sha256"])
    acquisition = tmp_path / "acquisition.json"
    acquisition.write_text(json.dumps({
        "status": "assets_verified_no_inference",
        "revision": smoke.MODEL_REVISION,
        "model_id": "ibm-granite/granite-docling-258M",
        "inference_performed": False,
        "file_receipts": rows,
    }), encoding="utf-8")
    monkeypatch.setattr(smoke, "ACQUISITION_SHA256", smoke.sha256_file(acquisition))
    return model_dir, acquisition


def test_asset_hash_and_inventory_are_required(tmp_path, monkeypatch):
    model_dir, acquisition = _assets(tmp_path, monkeypatch)
    result = smoke.verify_assets(model_dir, acquisition)
    assert result["asset_count"] == 13
    (model_dir / "asset-1.json").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="model asset differs"):
        smoke.verify_assets(model_dir, acquisition)


def test_extra_asset_and_wrong_revision_fail_closed(tmp_path, monkeypatch):
    model_dir, acquisition = _assets(tmp_path, monkeypatch)
    (model_dir / "untracked.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory differs"):
        smoke.verify_assets(model_dir, acquisition)
    (model_dir / "untracked.json").unlink()
    receipt = json.loads(acquisition.read_text(encoding="utf-8"))
    receipt["revision"] = "other"
    acquisition.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="receipt hash differs"):
        smoke.verify_assets(model_dir, acquisition)


def test_synthetic_table_is_source_free():
    image = smoke.synthetic_table()
    assert image.size == (900, 300)
    assert image.mode == "RGB"
