"""Offline checks for the source-pinned PP-StructureV3 configuration builder."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from product_eval import prepare_ppstructure_config as prep
from product_eval.contracts import ContractError
from product_eval.ppstructure_table_diagnostic import ROOT_FLAGS, active_model_dirs


def test_pinned_template_and_model_manifest_match_fixed_profile(tmp_path: Path) -> None:
    template, manifest = prep.load_sources()
    assert len(manifest["models"]) == 11
    assert sum(model["size_bytes"] for model in manifest["models"]) == 1_088_173_633
    assert all(len(model["revision"]) == 40 for model in manifest["models"])
    model_dirs = {}
    for model in manifest["models"]:
        folder = tmp_path / model["model_name"]
        folder.mkdir()
        model_dirs[model["model_name"]] = folder
    config = prep.local_config(template, model_dirs)
    assert all(config[name] is expected for name, expected in ROOT_FLAGS.items())
    assert len(active_model_dirs(config)) == 11
    assert template["use_formula_recognition"] is True  # builder leaves the source fixture intact


def test_git_blob_digest_and_missing_model_root(tmp_path: Path) -> None:
    file = tmp_path / "small.txt"
    file.write_bytes(b"example")
    assert prep.file_digest(file, "sha1", git_blob=True) == hashlib.sha1(b"blob 7\0example").hexdigest()
    _, manifest = prep.load_sources()
    with pytest.raises(ContractError, match="model root"):
        prep.verify_model_files(tmp_path / "missing", manifest)
