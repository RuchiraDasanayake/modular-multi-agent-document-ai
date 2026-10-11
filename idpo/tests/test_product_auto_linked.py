"""Repeated records remain linked, bounded and reviewable in auto mode."""

from __future__ import annotations

import json
from pathlib import Path

from idpo.product_auto import process_auto
from idpo.product_auto.logic import parse_schema_reply, parse_values_reply
from idpo.product_auto.provider import ModelReply
from product_eval.contracts import load_jsonl
from product_eval.scorer import score_records


def test_linked_columns_keep_shared_row_ordinals_and_source_quotes(tmp_path: Path) -> None:
    source = tmp_path / "items.txt"
    source.write_text("Items:\nA 2\nB 0\n", encoding="utf-8")

    class Model:
        model = "synthetic-local"

        def __init__(self) -> None:
            self.replies = [
                ModelReply(text=json.dumps({"fields": [
                    {"field_id": "item", "type": "array[object]", "group": "items"},
                    {"field_id": "quantity", "type": "array[object]", "group": "items"},
                ]}), latency_ms=1),
                ModelReply(text=json.dumps({"values": [
                    {"field_id": "item", "value": [
                        {"row": 0, "value": "A", "page": 1, "quote": "A 2"},
                        {"row": 1, "value": "B", "page": 1, "quote": "B 0"},
                    ]},
                    {"field_id": "quantity", "value": [
                        {"row": 0, "value": "2", "page": 1, "quote": "A 2"},
                        {"row": 1, "value": "0", "page": 1, "quote": "B 0"},
                    ]},
                ]}), latency_ms=1),
            ]

        def complete_json(self, *, system: str, prompt: str) -> ModelReply:
            return self.replies.pop(0)

    run = process_auto(source, run_id="linked_columns", model=Model(), output_root=tmp_path / "runs")
    candidate = next(iter(load_jsonl(Path(run["run_dir"]) / "candidates.jsonl", kind="candidate").values()))
    assert candidate["document_status"] == "needs_review"
    assert {field["type"] for field in candidate["proposed_schema"]} == {"array[object]"}
    for field in candidate["extracted_values"]:
        assert field["status"] == "needs_review"
        assert field["review_state"] == "pending"
        assert [cell["row"] for cell in field["value"]] == [0, 1]
        assert all(cell["status"] == "accepted" and cell["evidence"]["page"] == 1 for cell in field["value"])

    gold = {
        candidate["doc_id"]: {
            "contract_version": 1, "doc_id": candidate["doc_id"],
            "pages": [{"page": 1, "text": "Items:\nA 2\nB 0"}],
            "gold_schema": [
                {"field_id": "item", "type": "array[object]", "critical": False},
                {"field_id": "quantity", "type": "array[object]", "critical": False},
            ],
            "gold_values": [
                {"field_id": "item", "value": [{"row": 0, "value": "A"}, {"row": 1, "value": "B"}]},
                {"field_id": "quantity", "value": [{"row": 0, "value": "2"}, {"row": 1, "value": "0"}]},
            ],
        }
    }
    score = score_records(gold, {candidate["doc_id"]: candidate})["linked_rows"]
    assert score["proposed_cells"]["tp"] == 4
    assert score["proposed_complete_rows"]["tp"] == 2
    assert score["accepted_cells"]["tp"] == 0


def test_linked_model_contract_rejects_duplicate_or_oversized_rows() -> None:
    fields = parse_schema_reply('{"fields":[{"field_id":"item","type":"array[object]"}]}')
    assert fields is not None
    pages = [{"page": 1, "text": "A 2\nB 0"}]
    valid = parse_values_reply(
        '{"values":[{"field_id":"item","value":[{"row":0,"value":"A","page":1,"quote":"A 2"}]}]}',
        fields, pages,
    )
    assert valid is not None and valid["item"]["value"][0]["status"] == "accepted"
    assert parse_values_reply('{"values":[{"field_id":"item","value":null}]}', fields, pages)["item"]["value"] is None
    for malformed in (
        [{"row": 0, "value": "A"}, {"row": 0, "value": "B"}],
        [{"row": -1, "value": "A"}],
        [{"row": 128, "value": "A"}],
        [{"row": 0, "value": ""}],
        [{"row": 0, "value": 2}],
        [{"row": index, "value": "A"} for index in range(129)],
    ):
        reply = json.dumps({"values": [{"field_id": "item", "value": malformed}]})
        assert parse_values_reply(reply, fields, pages) is None
