from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from product_eval import gliner25_small_oracle_diagnostic as pilot


class OracleProtocolTests(unittest.TestCase):
    def test_locked_manifest_contains_six_only_ids_shapes_and_hashes(self) -> None:
        manifest = json.loads(pilot.SCHEMA_LOCK.read_text(encoding="utf-8"))
        self.assertEqual(pilot.sha256_file(pilot.SCHEMA_LOCK), pilot.SCHEMA_LOCK_SHA256)
        self.assertEqual(len(manifest["sources"]), 6)
        self.assertEqual(len({row["source_sha256"] for row in manifest["sources"]}), 6)
        self.assertFalse(any("gold_values" in row or "row" in row for row in manifest["sources"]))
        self.assertTrue(all(set(field) == {"field_id", "type"} for row in manifest["sources"]
                            for field in row["fields"]))
        self.assertEqual(manifest["settings"]["cross_chunk_join"], False)

    def test_schema_projection_does_not_export_reference_values(self) -> None:
        with TemporaryDirectory() as temporary:
            sidecar = Path(temporary) / "ocr.json"
            sidecar.write_text("{}", encoding="utf-8")
            inventory = [{"role": "scored", "doc_id": f"doc-{index}", "family": "synthetic",
                          "source_sha256": f"{index:064x}", "ocr_text": "source only",
                          "sidecar_path": sidecar} for index in range(6)]
            gold = {row["doc_id"]: {"gold_schema": [
                {"field_id": "merchant", "type": "string"},
                {"field_id": "item", "type": "array[object]"}],
                "gold_values": [{"field_id": "merchant", "value": "DO_NOT_LEAK_SECRET"},
                                {"field_id": "item", "value": [{"row": 9, "value": "ALSO_SECRET"}]}]}
                    for row in inventory}
            projected = pilot._schema_rows(gold, inventory)
            encoded = json.dumps(projected)
            self.assertNotIn("DO_NOT_LEAK_SECRET", encoded)
            self.assertNotIn("ALSO_SECRET", encoded)
            self.assertNotIn('"row": 9', encoded)
            self.assertEqual(projected[0]["record"]["anchor"], "item")

    def test_structured_rows_keep_identity_and_invalid_spans_are_not_verified(self) -> None:
        text = "ACME Apple 2 Banana 3"
        source = {"fields": [
            {"field_id": "merchant", "type": "string"},
            {"field_id": "item", "type": "array[object]"},
            {"field_id": "quantity", "type": "array[object]"}],
            "record": {"fields": ["item", "quantity"]}}
        raw = {"entities": {"merchant": [{"text": "ACME", "start": 0, "end": 4}]},
               "line_items": [
                   {"item": {"text": "Apple", "start": 5, "end": 10},
                    "quantity": {"text": "2", "start": 11, "end": 12}},
                   {"item": {"text": "Banana", "start": 13, "end": 19},
                    "quantity": {"text": "3", "start": 0, "end": 1}}]}
        reply, spans = pilot._candidate_to_reply(raw, source, text)
        self.assertEqual(reply["merchant"], "ACME")
        self.assertEqual(reply["line_items"], [
            {"item": "Apple", "quantity": "2"},
            {"item": "Banana", "quantity": "3"}])
        self.assertEqual(spans["verified_offsets"], 4)
        self.assertEqual(spans["invalid_or_missing_offsets"], 1)

    def test_multiple_distinct_scalar_mentions_abstain(self) -> None:
        reply, spans = pilot._candidate_to_reply(
            {"entities": {"amount": ["$10", "$20"]}},
            {"fields": [{"field_id": "amount", "type": "string"}], "record": None},
            "$10 and $20")
        self.assertIsNone(reply["amount"])
        self.assertEqual(spans["ambiguous_scalar_fields"], 1)


if __name__ == "__main__":
    unittest.main()
