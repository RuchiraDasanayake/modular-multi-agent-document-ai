"""Offline tests for the separate pinned Hub/Xet acquisition arm."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from product_eval import gliner25_hub_acquisition as arm


class XetDownloadError(Exception):
    pass


class AcquisitionTests(TestCase):
    def test_original_model_lock_remains_exact(self) -> None:
        model = arm.model_lock()
        self.assertEqual(model["id"], arm.MODEL_ID)
        self.assertEqual(model["revision"], arm.REVISION)
        self.assertEqual(model["files"][arm.WEIGHT]["sha256"], arm.WEIGHT_SHA256)
        self.assertEqual(set(model["files"]), {*arm.SMALL_FILES, arm.WEIGHT})

    def test_copies_only_four_rehashed_small_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, stage = root / "source", root / "stage"
            source.mkdir()
            stage.mkdir()
            files = {}
            for name in arm.SMALL_FILES:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                data = name.encode()
                path.write_bytes(data)
                files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            (source / "model.safetensors.invalid").write_bytes(b"first-attempt partial")
            copied = arm.copy_small_files(stage, source, {"files": files})
            self.assertEqual(set(copied), set(arm.SMALL_FILES))
            self.assertFalse((stage / "model" / arm.WEIGHT).exists())
            self.assertEqual((source / "model.safetensors.invalid").read_bytes(),
                             b"first-attempt partial")
            (source / "config.json").write_bytes(b"tampered")
            with self.assertRaises(arm.HashMismatchError):
                arm.copy_small_files(root / "different-stage", source, {"files": files})

    def test_one_official_call_requires_xet_and_full_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "stage"
            cached = stage / "hf-home" / "hub" / "snapshot" / arm.WEIGHT
            cached.parent.mkdir(parents=True)
            (stage / "model").mkdir()
            data = b"synthetic small weight"
            cached.write_bytes(data)
            model = {"files": {arm.WEIGHT: {
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}}}
            calls = []

            def fake_hub_download(**kwargs):
                calls.append(kwargs)
                return str(cached)

            with self.assertRaises(arm.XetOnlyError):
                arm.download_once(stage, model, fake_hub_download, [0])
            self.assertFalse((stage / "model" / arm.WEIGHT).exists())
            result = arm.download_once(stage, model, fake_hub_download, [1])
            self.assertEqual(len(calls), 2)  # One call in each independent test invocation.
            self.assertEqual(calls[-1]["repo_id"], arm.MODEL_ID)
            self.assertEqual(calls[-1]["revision"], arm.REVISION)
            self.assertIs(calls[-1]["token"], False)
            self.assertIs(calls[-1]["force_download"], True)
            self.assertTrue(Path(calls[-1]["cache_dir"]).is_relative_to(stage))
            self.assertEqual(result["weight_sha256"], model["files"][arm.WEIGHT]["sha256"])
            self.assertEqual((stage / "model" / arm.WEIGHT).read_bytes(), data)

    def test_wrong_weight_digest_rejected_before_model_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "stage"
            cached = stage / "hf-home" / "hub" / arm.WEIGHT
            cached.parent.mkdir(parents=True)
            (stage / "model").mkdir()
            cached.write_bytes(b"wrong")
            model = {"files": {arm.WEIGHT: {"bytes": 5, "sha256": "0" * 64}}}
            with self.assertRaises(arm.HashMismatchError):
                arm.download_once(stage, model, lambda **_: str(cached), [1])
            self.assertFalse((stage / "model" / arm.WEIGHT).exists())

    def test_guard_and_exception_sanitization(self) -> None:
        self.assertEqual(arm.guard_reason(now=901, deadline=900, free_c=10**12,
                                          available_ram=10**12, tree_rss=0,
                                          stage_bytes=0), "wall_deadline")
        self.assertEqual(arm.guard_reason(now=0, deadline=900, free_c=0,
                                          available_ram=10**12, tree_rss=0,
                                          stage_bytes=0), "disk_floor")
        self.assertEqual(arm.guard_reason(now=0, deadline=900, free_c=10**12,
                                          available_ram=10**12, tree_rss=0,
                                          stage_bytes=arm.MAX_STAGE_BYTES + 1), "stage_size_cap")
        exc = XetDownloadError("https://signed.invalid/?token=secret")
        receipt = arm.safe_error(exc)
        self.assertEqual(receipt["error_class"], "XetDownloadError")
        self.assertNotIn("signed.invalid", json.dumps(receipt))

    def test_worker_environment_discards_ambient_hf_credentials(self) -> None:
        with patch.dict("os.environ", {"HF_TOKEN": "secret", "HF_DEBUG": "1",
                                    "HF_HUB_DISABLE_XET": "1"}):
            env = arm.worker_environment(Path("C:/fresh-gliner-stage"))
        self.assertNotIn("HF_TOKEN", env)
        self.assertNotIn("HF_DEBUG", env)
        self.assertNotIn("HF_HUB_DISABLE_XET", env)
        self.assertEqual(env["HF_XET_FIXED_DOWNLOAD_CONCURRENCY"], "2")
        self.assertEqual(env["HF_XET_CLIENT_RETRY_MAX_ATTEMPTS"], "2")
        self.assertEqual(env["HF_HUB_DISABLE_IMPLICIT_TOKEN"], "1")
        self.assertEqual(env["HF_HOME"], str(Path("C:/fresh-gliner-stage/hf-home")))

    def test_hub_22_dispatch_respects_xet_and_http_fallback_hooks(self) -> None:
        if importlib.metadata.version("huggingface-hub") != arm.HUB_VERSION:
            self.skipTest("dispatch hook test requires the pinned Paddle Hub 2.2.0 runtime")
        from huggingface_hub import file_download

        calls = {"xet": 0, "http": 0}

        def fake_xet_get(*, incomplete_path, **_):
            calls["xet"] += 1
            incomplete_path.write_bytes(b"synthetic weight")

        def forbid_http(*args, **kwargs):
            calls["http"] += 1
            raise arm.XetOnlyError("HTTP fallback blocked")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kwargs = {
                "incomplete_path": root / "weight.incomplete",
                "destination_path": root / "weight",
                "url_to_download": "https://example.invalid/unused",
                "headers": {}, "expected_size": None, "filename": arm.WEIGHT,
                "force_download": True, "etag": None, "xet_file_data": object(),
            }
            with (patch.object(file_download, "xet_get", fake_xet_get),
                  patch.object(file_download, "http_get", forbid_http),
                  patch.object(file_download, "is_xet_available", return_value=True)):
                file_download._download_to_tmp_and_move(**kwargs)
                self.assertEqual((root / "weight").read_bytes(), b"synthetic weight")
                kwargs["destination_path"] = root / "raw-weight"
                kwargs["xet_file_data"] = None
                with self.assertRaises(arm.XetOnlyError):
                    file_download._download_to_tmp_and_move(**kwargs)
        self.assertEqual(calls, {"xet": 1, "http": 1})
