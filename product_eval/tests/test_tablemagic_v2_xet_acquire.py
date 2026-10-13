from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from product_eval import tablemagic_v2_xet_acquire as acquire
from product_eval.contracts import ContractError


def test_manifest_still_has_frozen_nine_model_54_file_inventory():
    manifest = acquire._manifest()
    assert len(manifest["profile"]["active_model_names"]) == 9
    assert sum(len(model["files"]) for model in manifest["models"]
               if model["name"] in manifest["profile"]["active_model_names"]) == 54


def test_asset_verification_checks_exact_size_and_content(tmp_path):
    asset = tmp_path / "inference.pdiparams"
    asset.write_bytes(b"weight")
    expected = {"size_bytes": 6, "sha256": hashlib.sha256(b"weight").hexdigest()}
    assert acquire.verify_asset(asset, expected)["digest"] == expected["sha256"]
    with pytest.raises(ContractError, match="size differs"):
        acquire.verify_asset(asset, {**expected, "size_bytes": 7})
    with pytest.raises(ContractError, match="sha256 differs"):
        acquire.verify_asset(asset, {**expected, "sha256": "0" * 64})


def test_git_blob_digest_and_isolated_xet_environment(tmp_path, monkeypatch):
    small = tmp_path / "config.json"
    small.write_bytes(b"abc")
    expected = {"size_bytes": 3,
                "git_blob_sha1": hashlib.sha1(b"blob 3\0abc").hexdigest()}
    assert acquire.verify_asset(small, expected)["digest"] == expected["git_blob_sha1"]
    monkeypatch.setenv("HF_TOKEN", "never-send")
    monkeypatch.setenv("HF_DEBUG", "1")
    env = acquire._worker_env(tmp_path)
    assert "HF_TOKEN" not in env
    assert env["HF_DEBUG"] == "0"
    assert env["HF_HUB_DISABLE_XET"] == "0"
    assert env["HF_XET_FIXED_DOWNLOAD_CONCURRENCY"] == "2"
    assert env["HF_XET_CLIENT_RETRY_MAX_ATTEMPTS"] == "3"
    assert env["HF_HUB_CACHE"] == str(tmp_path / "hub-cache")


def test_resource_guard_covers_ram_disk_root_bytes_and_process_tree():
    okay = {"process_tree_rss_bytes": 1, "host_available_bytes": 4 * 1024**3,
            "c_free_bytes": 5 * 1024**3, "e_free_bytes": 3 * 1024**3,
            "new_root_bytes": 1_000_000}
    assert acquire._resource_error(okay) is None
    assert acquire._resource_error({**okay, "host_available_bytes": 2 * 1024**3}) == "host_ram_floor"
    assert acquire._resource_error({**okay, "new_root_bytes": 4_000_000_000}) == "new_root_byte_limit"
    assert acquire._resource_error({**okay, "process_tree_rss_bytes": 4 * 1024**3}) == "process_tree_rss_limit"


def test_guarded_copy_stops_before_disk_or_byte_floor(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_bytes(b"abc")
    sample = {"process_tree_rss_bytes": 0, "host_available_bytes": 4 * 1024**3,
              "c_free_bytes": 5 * 1024**3, "e_free_bytes": 3 * 1024**3,
              "new_root_bytes": acquire.MAX_NEW_ROOT_BYTES - 2}
    monkeypatch.setattr(acquire, "_sample", lambda _process, _root: sample)
    with pytest.raises(ContractError, match="would exceed byte"):
        acquire._copy_with_guard(source, tmp_path / "blocked", tmp_path)
    assert (tmp_path / "blocked").stat().st_size == 0


def test_weight_download_cannot_fall_back_to_regular_http(tmp_path, monkeypatch):
    import huggingface_hub
    from huggingface_hub import file_download as hub_download

    monkeypatch.setattr(acquire.importlib.metadata, "version", lambda name: {
        "huggingface_hub": "2.2.0", "hf_xet": "1.7.0"}[name])
    monkeypatch.setattr(hub_download.constants, "HF_HUB_DISABLE_XET", False)

    def fake_download(**kwargs):
        assert kwargs["token"] is False
        assert kwargs["endpoint"] == "https://huggingface.co"
        assert kwargs["revision"] == "a" * 40
        hub_download.http_get("unused", None)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)
    args = SimpleNamespace(root=tmp_path, repo="PaddlePaddle/example",
                           filename="inference.pdiparams", revision="a" * 40,
                           result=tmp_path / "result.json", require_xet=True)
    with pytest.raises(ContractError, match="raw HTTP fallback forbidden"):
        acquire._asset_worker(args)
    assert not args.result.exists()
