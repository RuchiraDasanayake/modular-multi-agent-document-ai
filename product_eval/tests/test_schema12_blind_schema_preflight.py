from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from product_eval import schema12_blind_schema_preflight as preflight


def _write_json(path: Path, value: dict) -> str:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SourceLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("SCHEMA12_TEST_TMP_ROOT"))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "raw").mkdir()
        self.manifest = {"candidate_denominator": 12, "model_inference": False, "sources": []}
        repo_root = Path(__file__).resolve().parents[2]
        self.eligibility = {"source_manifest_sha256": "a" * 64,
                            "parser_code_sha256": {
                                path: preflight.sha256_file(repo_root / path)
                                for path in preflight.PARSER_FILES
                            }, "sources": []}
        for number in range(12):
            source_id = f"doc_{number:02d}"
            relative = f"raw/{source_id}.html"
            content = f"Document {number}".encode()
            (self.root / relative).write_bytes(content)
            source_hash = hashlib.sha256(content).hexdigest()
            self.manifest["sources"].append({"id": source_id, "relative_path": relative,
                                             "sha256": source_hash, "byte_size": len(content), "kind": "html"})
            self.eligibility["sources"].append({"source_id": source_id, "source_sha256": source_hash,
                                                "format": "html", "status": "parsed", "character_count": 10,
                                                "model_context_cap_chars": 24000,
                                                "meets_model_context_limit": True})

    def verify(self) -> dict:
        return preflight._cohort_sources(self.root, self.manifest, self.eligibility, "a" * 64, 24000, 12)

    def test_verifies_twelve_distinct_originals_and_eligibility(self) -> None:
        result = self.verify()
        self.assertEqual(result["unique_source_hashes"], 12)
        self.assertEqual(result["eligible_under_character_cap"], 12)

    def test_detects_changed_source_bytes(self) -> None:
        (self.root / "raw" / "doc_00.html").write_bytes(b"changed")
        with self.assertRaisesRegex(preflight.PreflightError, "source bytes differ"):
            self.verify()

    def test_rejects_stale_parser_code_lock(self) -> None:
        self.eligibility["parser_code_sha256"]["idpo/agents/intake.py"] = "0" * 64
        with self.assertRaisesRegex(preflight.PreflightError, "parser code differs"):
            self.verify()

    def test_rejects_path_outside_raw_even_with_claimed_hash(self) -> None:
        self.manifest["sources"][0]["relative_path"] = "raw/../outside.html"
        with self.assertRaisesRegex(preflight.PreflightError, "escapes raw"):
            self.verify()

    def test_over_limit_source_stays_in_denominator(self) -> None:
        self.eligibility["sources"][0]["character_count"] = 24001
        self.eligibility["sources"][0]["meets_model_context_limit"] = False
        result = self.verify()
        self.assertEqual(result["source_count"], 12)
        self.assertEqual(result["eligible_under_character_cap"], 11)
        self.assertEqual(result["over_limit_source_ids"], ["doc_00"])

    def _scorer_files(self) -> tuple[argparse.Namespace, dict, dict, dict]:
        manifest_path = self.root / "manifest-final.json"
        manifest_sha = _write_json(manifest_path, self.manifest)
        self.eligibility["source_manifest_sha256"] = manifest_sha
        eligibility_sha = _write_json(self.root / "eligibility.json", self.eligibility)
        source_lock = {"contract_version": 1, "sources": [
            {"doc_id": source["id"], "source_sha256": source["sha256"]}
            for source in self.manifest["sources"]
        ]}
        source_lock_path = self.root / "source-lock.json"
        source_lock_sha = _write_json(source_lock_path, source_lock)
        gold = {"contract_version": 1, "source_lock_sha256": source_lock_sha,
                "documents": [{"doc_id": source["id"], "source_sha256": source["sha256"],
                               "gold_complete": True, "groups": [],
                               "fields": [{"field_id": "invoice_number", "type": "identifier", "group": None}]}
                              for source in self.manifest["sources"]]}
        gold_path = self.root / "gold.json"
        gold_sha = _write_json(gold_path, gold)
        aliases = {"contract_version": 1,
                   "entries": [{"field_id": "invoice_number", "aliases": ["invoice_no"]}]}
        aliases_path = self.root / "aliases.json"
        aliases_sha = _write_json(aliases_path, aliases)
        profile_path = Path(__file__).resolve().parents[2] / "docs/evaluations/schema12_blind_schema_ab_profile_v1.json"
        args = argparse.Namespace(
            source_root=self.root, manifest_sha256=manifest_sha, eligibility_sha256=eligibility_sha,
            profile=profile_path, profile_sha256=preflight.sha256_file(profile_path),
            source_lock=source_lock_path, source_lock_sha256=source_lock_sha,
            gold=gold_path, gold_sha256=gold_sha, aliases=aliases_path, aliases_sha256=aliases_sha,
            rights_receipt=None, rights_sha256=None, human_receipt=None, human_sha256=None,
            runtime_receipt=None, runtime_sha256=None, asset_manifest=None,
            asset_manifest_sha256=None, smoke_log=None, smoke_sha256=None,
        )
        return args, source_lock, gold, aliases

    def _inspect(self, args: argparse.Namespace) -> dict:
        with patch.object(preflight.shutil, "disk_usage", return_value=SimpleNamespace(free=8 * 1024**3)):
            return preflight.inspect(args)

    def _runtime_files(self, args: argparse.Namespace) -> tuple[dict, dict, dict]:
        assets_dir = self.root / "assets"
        assets_dir.mkdir()
        files = {
            "nuextract3_q4": [
                ("weight", "NuExtract3-Q4_K_M.gguf"),
                ("vision_projector", "mmproj-NuExtract3-BF16.gguf"),
                ("llama_server", "llama-server.exe"),
            ],
            "qwen35_2b_bf16": [
                ("weight", "model.safetensors-00001-of-00001.safetensors"),
                ("config", "config.json"),
                ("tokenizer", "tokenizer.json"),
                ("processor", "processor_config.json"),
                ("runner", "python.exe"),
            ],
        }
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        arms: dict[str, dict] = {}
        for name, entries in files.items():
            arm_files = []
            for role, filename in entries:
                path = assets_dir / name / filename
                path.parent.mkdir(exist_ok=True)
                data = f"{name}:{role}".encode()
                path.write_bytes(data)
                digest = hashlib.sha256(data).hexdigest()
                arm_files.append({"role": role, "path": str(path), "sha256": digest,
                                  "size_bytes": len(data)})
                key = {"weight": "weight_sha256", "vision_projector": "vision_projector_sha256",
                       "llama_server": "llama_server_sha256"}.get(role)
                if key:
                    profile["model_profiles"][name][key] = digest
                if name == "qwen35_2b_bf16" and role == "weight":
                    profile["model_profiles"][name]["weight_size_bytes"] = len(data)
            arms[name] = {
                "official_repository": profile["model_profiles"][name]["official_repository"],
                "revision": profile["model_profiles"][name]["revision"],
                "files": arm_files,
            }
        args.profile = self.root / "profile-runtime.json"
        args.profile_sha256 = _write_json(args.profile, profile)
        manifest = {"version": 1, "protocol_profile_sha256": args.profile_sha256,
                    "model_arms": arms}
        args.asset_manifest = self.root / "runtime-assets-lock.json"
        args.asset_manifest_sha256 = _write_json(args.asset_manifest, manifest)
        smoke_arms = {}
        for name, arm in arms.items():
            artifacts = {}
            for label in ("runner", "input", "output"):
                if label == "runner":
                    role = "llama_server" if name == "nuextract3_q4" else "runner"
                    entry = next(entry for entry in arm["files"] if entry["role"] == role)
                    artifacts["runner_path"] = entry["path"]
                    artifacts["runner_sha256"] = entry["sha256"]
                else:
                    path = self.root / "smoke" / name / f"{label}.bin"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    data = f"synthetic:{name}:{label}".encode()
                    path.write_bytes(data)
                    artifacts[f"{label}_path"] = str(path)
                    artifacts[f"{label}_sha256"] = hashlib.sha256(data).hexdigest()
            smoke_arms[name] = {
                "input_kind": "synthetic", "loaded": True,
                "source_free_smoke": True, "exit_code": 0,
                "launch_argv": [artifacts["runner_path"], "--smoke"],
            } | artifacts
        smoke = {"version": 1, "status": "source_free_verified",
                 "protocol_profile_sha256": args.profile_sha256,
                 "asset_manifest_sha256": args.asset_manifest_sha256,
                 "model_arms": smoke_arms}
        args.smoke_log = self.root / "source-free-smoke.json"
        args.smoke_sha256 = _write_json(args.smoke_log, smoke)
        runtime = {"version": 1, "status": "source_free_verified",
                   "source_manifest_sha256": args.manifest_sha256,
                   "source_lock_sha256": args.source_lock_sha256,
                   "protocol_profile_sha256": args.profile_sha256,
                   "asset_manifest_sha256": args.asset_manifest_sha256,
                   "smoke_log_sha256": args.smoke_sha256,
                   "reviewed_by": "synthetic reviewer"}
        args.runtime_receipt = self.root / "runtime-receipt.json"
        args.runtime_sha256 = _write_json(args.runtime_receipt, runtime)
        return manifest, smoke, runtime

    def test_accepts_exact_scorer_source_gold_alias_shapes_but_stays_blocked(self) -> None:
        args, _, _, _ = self._scorer_files()
        with patch.object(preflight, "_host_model_resources", return_value=(8 * 1024**3, 7000)):
            report = self._inspect(args)
        self.assertTrue(report["gates"]["source_lock"])
        self.assertTrue(report["gates"]["gold"])
        self.assertTrue(report["gates"]["aliases"])
        self.assertFalse(report["gates"]["asset_manifest"])
        self.assertFalse(report["gates"]["smoke_log"])
        self.assertFalse(report["gates"]["runtime"])
        self.assertFalse(report["gates"]["human_adjudication"])
        self.assertFalse(report["gates"]["rights"])
        self.assertTrue(report["gates"]["model_run_host_ram"])
        self.assertTrue(report["gates"]["model_run_gpu_memory"])
        self.assertFalse(report["ready_for_inference"])
        self.assertEqual(report["model_calls_made"], 0)

    def test_low_or_unavailable_model_resources_fail_closed(self) -> None:
        args, _, _, _ = self._scorer_files()
        for resources in ((5 * 1024**3, 7000), (8 * 1024**3, 6000), (None, None)):
            with self.subTest(resources=resources):
                with patch.object(preflight, "_host_model_resources", return_value=resources):
                    report = self._inspect(args)
                self.assertEqual(report["gates"]["model_run_host_ram"],
                                 resources[0] is not None and resources[0] >= 6 * 1024**3)
                self.assertEqual(report["gates"]["model_run_gpu_memory"],
                                 resources[1] is not None and resources[1] >= 6144)
                self.assertFalse(report["ready_for_inference"])

    def test_bound_asset_smoke_and_runtime_chain_passes_its_own_gates(self) -> None:
        args, _, _, _ = self._scorer_files()
        self._runtime_files(args)
        with patch.object(preflight, "_host_model_resources", return_value=(8 * 1024**3, 7000)):
            report = self._inspect(args)
        self.assertTrue(report["gates"]["asset_manifest"])
        self.assertTrue(report["gates"]["smoke_log"])
        self.assertTrue(report["gates"]["runtime"])
        self.assertFalse(report["ready_for_inference"])
        self.assertEqual(report["model_calls_made"], 0)

    def test_changed_asset_bytes_fail_entire_runtime_chain(self) -> None:
        args, _, _, _ = self._scorer_files()
        manifest, _, _ = self._runtime_files(args)
        Path(manifest["model_arms"]["qwen35_2b_bf16"]["files"][2]["path"]).write_bytes(b"changed")
        with patch.object(preflight, "_host_model_resources", return_value=(8 * 1024**3, 7000)):
            report = self._inspect(args)
        self.assertFalse(report["gates"]["asset_manifest"])
        self.assertFalse(report["gates"]["smoke_log"])
        self.assertFalse(report["gates"]["runtime"])
        self.assertTrue(any("asset bytes differ" in issue for issue in report["blockers"]))

    def test_qwen_config_tokenizer_and_processor_files_are_required(self) -> None:
        args, _, _, _ = self._scorer_files()
        manifest, _, _ = self._runtime_files(args)
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        files = manifest["model_arms"]["qwen35_2b_bf16"]["files"]
        for missing_role in ("config", "tokenizer", "processor"):
            with self.subTest(missing_role=missing_role):
                manifest["model_arms"]["qwen35_2b_bf16"]["files"] = [
                    entry for entry in files if entry["role"] != missing_role
                ]
                with self.assertRaisesRegex(preflight.PreflightError, "required roles"):
                    preflight._validate_asset_manifest(
                        manifest, profile=profile, profile_sha256=args.profile_sha256,
                    )

    def test_nuextract_projector_must_match_pinned_profile_hash(self) -> None:
        args, _, _, _ = self._scorer_files()
        manifest, _, _ = self._runtime_files(args)
        entry = manifest["model_arms"]["nuextract3_q4"]["files"][1]
        data = b"alternate projector"
        Path(entry["path"]).write_bytes(data)
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        entry["size_bytes"] = len(data)
        with self.assertRaisesRegex(preflight.PreflightError, "differs from profile"):
            preflight._validate_asset_manifest(
                manifest, profile=json.loads(args.profile.read_text(encoding="utf-8")),
                profile_sha256=args.profile_sha256,
            )

    def test_smoke_log_must_bind_exact_asset_manifest_and_profile(self) -> None:
        args, _, _, _ = self._scorer_files()
        manifest, smoke, _ = self._runtime_files(args)
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        smoke["asset_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(preflight.PreflightError, "not bound"):
            preflight._validate_smoke_log(
                smoke, profile_sha256=args.profile_sha256,
                asset_manifest_sha256=args.asset_manifest_sha256,
                asset_manifest=manifest,
                model_profiles=profile["model_profiles"],
            )
        smoke["asset_manifest_sha256"] = args.asset_manifest_sha256
        smoke["model_arms"]["nuextract3_q4"]["exit_code"] = 1
        with self.assertRaisesRegex(preflight.PreflightError, "incomplete"):
            preflight._validate_smoke_log(
                smoke, profile_sha256=args.profile_sha256,
                asset_manifest_sha256=args.asset_manifest_sha256,
                asset_manifest=manifest,
                model_profiles=profile["model_profiles"],
            )

    def test_smoke_runner_must_be_the_pinned_launch_asset(self) -> None:
        args, _, _, _ = self._scorer_files()
        manifest, smoke, _ = self._runtime_files(args)
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        other_runner = self.root / "other-runner.exe"
        other_runner.write_bytes(b"another runner")
        arm = smoke["model_arms"]["qwen35_2b_bf16"]
        arm["runner_path"] = str(other_runner)
        arm["runner_sha256"] = hashlib.sha256(other_runner.read_bytes()).hexdigest()
        arm["launch_argv"][0] = str(other_runner)
        with self.assertRaisesRegex(preflight.PreflightError, "asset manifest"):
            preflight._validate_smoke_log(
                smoke, profile_sha256=args.profile_sha256,
                asset_manifest_sha256=args.asset_manifest_sha256,
                asset_manifest=manifest, model_profiles=profile["model_profiles"],
            )

    def test_runtime_receipt_must_bind_smoke_log_bytes(self) -> None:
        args, _, _, _ = self._scorer_files()
        _, _, runtime = self._runtime_files(args)
        runtime["smoke_log_sha256"] = "0" * 64
        args.runtime_sha256 = _write_json(args.runtime_receipt, runtime)
        with patch.object(preflight, "_host_model_resources", return_value=(8 * 1024**3, 7000)):
            report = self._inspect(args)
        self.assertTrue(report["gates"]["asset_manifest"])
        self.assertTrue(report["gates"]["smoke_log"])
        self.assertFalse(report["gates"]["runtime"])
        self.assertTrue(any("verified smoke log" in issue for issue in report["blockers"]))

    def test_tampered_smoke_log_bytes_fail_runtime_chain(self) -> None:
        args, _, _, _ = self._scorer_files()
        self._runtime_files(args)
        args.smoke_log.write_text(args.smoke_log.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with patch.object(preflight, "_host_model_resources", return_value=(8 * 1024**3, 7000)):
            report = self._inspect(args)
        self.assertTrue(report["gates"]["asset_manifest"])
        self.assertFalse(report["gates"]["smoke_log"])
        self.assertFalse(report["gates"]["runtime"])
        self.assertTrue(any("lock SHA-256 differs" in issue for issue in report["blockers"]))

    def test_scorer_source_lock_must_match_cohort_id_to_hash_map(self) -> None:
        args, source_lock, _, _ = self._scorer_files()
        first, second = source_lock["sources"][:2]
        first["source_sha256"], second["source_sha256"] = second["source_sha256"], first["source_sha256"]
        args.source_lock_sha256 = _write_json(args.source_lock, source_lock)
        report = self._inspect(args)
        self.assertFalse(report["gates"]["source_lock"])
        self.assertFalse(report["gates"]["gold"])

    def test_human_receipt_must_bind_scorer_hashes_and_field_anchors(self) -> None:
        args, _, gold, _ = self._scorer_files()
        planned = {row["id"]: row["sha256"] for row in self.manifest["sources"]}
        gold_docs = preflight.validate_gold(gold, planned, args.source_lock_sha256)
        human = {"version": 1, "status": "adjudicated_source_only",
                 "source_manifest_sha256": args.manifest_sha256,
                 "eligibility_sha256": args.eligibility_sha256,
                 "source_lock_sha256": args.source_lock_sha256,
                 "gold_sha256": args.gold_sha256, "aliases_sha256": args.aliases_sha256,
                 "annotators": ["A", "B"], "adjudicator": "C",
                 "sources": [{"doc_id": source["id"], "source_sha256": source["sha256"],
                              "full_source_pass": True,
                              "fields": [{"field_id": "invoice_number", "anchors": [
                                  {"locator": "page:1", "quote": "Invoice Number"}]}]}
                             for source in self.manifest["sources"]]}
        preflight._validate_human(human, manifest_sha256=args.manifest_sha256,
                                  eligibility_sha256=args.eligibility_sha256,
                                  source_lock_sha256=args.source_lock_sha256,
                                  gold_sha256=args.gold_sha256, aliases_sha256=args.aliases_sha256,
                                  planned=planned, gold_docs=gold_docs)
        human["adjudicator"] = " a "
        with self.assertRaisesRegex(preflight.PreflightError, "independent annotation"):
            preflight._validate_human(human, manifest_sha256=args.manifest_sha256,
                                      eligibility_sha256=args.eligibility_sha256,
                                      source_lock_sha256=args.source_lock_sha256,
                                      gold_sha256=args.gold_sha256, aliases_sha256=args.aliases_sha256,
                                      planned=planned, gold_docs=gold_docs)
        human["adjudicator"] = "C"
        human["aliases_sha256"] = "0" * 64
        with self.assertRaisesRegex(preflight.PreflightError, "exact scorer inputs"):
            preflight._validate_human(human, manifest_sha256=args.manifest_sha256,
                                      eligibility_sha256=args.eligibility_sha256,
                                      source_lock_sha256=args.source_lock_sha256,
                                      gold_sha256=args.gold_sha256, aliases_sha256=args.aliases_sha256,
                                      planned=planned, gold_docs=gold_docs)

    def test_rights_receipt_needs_each_original_hash_and_permission(self) -> None:
        args, _, _, _ = self._scorer_files()
        planned = {row["id"]: row["sha256"] for row in self.manifest["sources"]}
        rights = {"version": 1, "status": "cleared_for_local_ai_inference",
                  "source_manifest_sha256": args.manifest_sha256,
                  "source_lock_sha256": args.source_lock_sha256, "reviewed_by": "reviewer",
                  "sources": [{"doc_id": doc_id, "source_sha256": source_hash,
                               "local_ai_inference_permitted": True, "basis": "synthetic"}
                              for doc_id, source_hash in planned.items()]}
        preflight._validate_rights(rights, manifest_sha256=args.manifest_sha256,
                                   source_lock_sha256=args.source_lock_sha256, planned=planned)
        rights["sources"][0]["local_ai_inference_permitted"] = False
        with self.assertRaisesRegex(preflight.PreflightError, "incomplete or misbound"):
            preflight._validate_rights(rights, manifest_sha256=args.manifest_sha256,
                                       source_lock_sha256=args.source_lock_sha256, planned=planned)


if __name__ == "__main__":
    unittest.main()
