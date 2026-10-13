from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from product_eval.schema12_blind_schema_preflight import PreflightError, _cohort_sources, _external_lock


class SourceLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("SCHEMA12_TEST_TMP_ROOT"))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "raw").mkdir()
        self.manifest = {"candidate_denominator": 12, "model_inference": False, "sources": []}
        self.eligibility = {"source_manifest_sha256": "a" * 64, "sources": []}
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
        return _cohort_sources(self.root, self.manifest, self.eligibility, "a" * 64, 24000, 12)

    def test_verifies_twelve_distinct_originals_and_eligibility(self) -> None:
        result = self.verify()
        self.assertEqual(result["unique_source_hashes"], 12)
        self.assertEqual(result["eligible_under_character_cap"], 12)

    def test_detects_changed_source_bytes(self) -> None:
        (self.root / "raw" / "doc_00.html").write_bytes(b"changed")
        with self.assertRaisesRegex(PreflightError, "source bytes differ"):
            self.verify()

    def test_rejects_path_outside_raw_even_with_a_claimed_hash(self) -> None:
        self.manifest["sources"][0]["relative_path"] = "raw/../outside.html"
        with self.assertRaisesRegex(PreflightError, "escapes raw"):
            self.verify()

    def test_over_limit_source_stays_in_denominator(self) -> None:
        self.eligibility["sources"][0]["character_count"] = 24001
        self.eligibility["sources"][0]["meets_model_context_limit"] = False
        result = self.verify()
        self.assertEqual(result["source_count"], 12)
        self.assertEqual(result["eligible_under_character_cap"], 11)
        self.assertEqual(result["over_limit_source_ids"], ["doc_00"])

    def test_rights_receipt_must_clear_every_source(self) -> None:
        receipt = {"version": 1, "source_manifest_sha256": "a" * 64,
                   "status": "cleared_for_local_ai_inference", "reviewed_by": "reviewer",
                   "sources": [{"source_id": "doc_00", "local_ai_inference_permitted": True,
                                "basis": "example"}]}
        path = self.root / "rights.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        ok, message, _ = _external_lock(path, hashlib.sha256(path.read_bytes()).hexdigest(),
                                        kind="rights", manifest_sha256="a" * 64,
                                        source_ids={f"doc_{i:02d}" for i in range(12)})
        self.assertFalse(ok)
        self.assertIn("incomplete", message)

    def test_runtime_receipt_cannot_cover_another_profile(self) -> None:
        receipt = {"version": 1, "source_manifest_sha256": "a" * 64,
                   "status": "source_free_verified", "protocol_profile_sha256": "b" * 64,
                   "model_arms": {"nuextract3_q4": {"loaded": True, "source_free_smoke": True,
                                                    "weight_sha256": "d" * 64},
                                  "qwen35_2b_bf16": {"loaded": True, "source_free_smoke": True,
                                                      "weight_sha256": "e" * 64}}}
        path = self.root / "runtime.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        ok, message, _ = _external_lock(path, hashlib.sha256(path.read_bytes()).hexdigest(),
                                        kind="runtime", manifest_sha256="a" * 64,
                                        source_ids={f"doc_{i:02d}" for i in range(12)},
                                        profile_sha256="c" * 64,
                                        model_profiles={"nuextract3_q4": {"weight_sha256": "d" * 64},
                                                        "qwen35_2b_bf16": {"weight_sha256": "e" * 64}})
        self.assertFalse(ok)
        self.assertIn("source-free verified", message)


if __name__ == "__main__":
    unittest.main()
