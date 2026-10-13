"""Tamper and class-map checks without network or model inference."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from product_eval import tatr_asset_preflight


def _asset(root: Path, name: str, content: bytes) -> tuple[int, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return len(content), hashlib.sha256(content).hexdigest()


def test_preflight_detects_tampering_and_class_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    detection = json.dumps({"id2label": {"0": "table", "1": "table rotated"}}).encode()
    structure = json.dumps({"id2label": {
        "0": "table", "1": "table column", "2": "table row",
        "3": "table column header", "4": "table projected row header", "5": "table spanning cell",
    }}).encode()
    expected = {
        "detection/config.json": _asset(tmp_path, "detection/config.json", detection),
        "structure/config.json": _asset(tmp_path, "structure/config.json", structure),
        "detection/model.safetensors": _asset(tmp_path, "detection/model.safetensors", b"synthetic"),
    }
    monkeypatch.setattr(tatr_asset_preflight, "EXPECTED", expected)
    receipt = tatr_asset_preflight.verify_assets(tmp_path)
    assert receipt["status"] == "assets_verified_only"
    assert receipt["document_inference_permitted"] is False
    (tmp_path / "detection/model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="pinned bytes"):
        tatr_asset_preflight.verify_assets(tmp_path)
    (tmp_path / "detection/model.safetensors").write_bytes(b"synthetic")
    wrong_detection = json.dumps({"id2label": {"0": "table", "1": "picture"}}).encode()
    expected["detection/config.json"] = _asset(tmp_path, "detection/config.json", wrong_detection)
    with pytest.raises(ValueError, match="class map"):
        tatr_asset_preflight.verify_assets(tmp_path)
