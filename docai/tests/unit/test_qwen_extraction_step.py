"""Unit tests: QwenExtractionStep.

Uses a fake ModelPlugin that returns controlled ModelResponse objects.
No real Qwen endpoint, no HTTP calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone

from docai_core.contracts.domain import ExtractionSchema, Field
from docai_core.plugins.models.base import ModelRequest, ModelResponse
from docai_core.extraction.qwen_extraction_step import QwenExtractionStep
from docai_core.plugins.models.qwen_model_plugin import QwenModelPlugin
from docai_core.extraction.qwen_extraction_step import QwenExtractionStep as _QwenStep


# ---------------------------------------------------------------------------
# Fake ModelPlugin helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakePlugin:
    """Minimal fake that satisfies ModelPlugin Protocol."""
    plugin_id: str = "fake_plugin"
    provider_name: str = "fake"
    model_name: str = "fake-model"
    response_text: str = ""
    success: bool = True
    captured_requests: list[ModelRequest] = dc_field(default_factory=list)

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.captured_requests.append(request)
        return ModelResponse(
            text=self.response_text,
            model_name=self.model_name,
            is_stub=False,
            success=self.success,
        )


def _schema(fields: list[tuple[str, str, str]] | None = None) -> ExtractionSchema:
    """Create a test ExtractionSchema. fields = [(field_id, name, description)]."""
    if fields is None:
        fields = [
            ("f1", "invoice_number", "The unique invoice identifier"),
            ("f2", "invoice_date",   "Date the invoice was issued"),
            ("f3", "total_amount",   "Total amount due"),
            ("f4", "status",         "Payment status"),
        ]
    return ExtractionSchema(
        schema_id="schema-test",
        project_id="proj-1",
        name="Test Schema",
        description=None,
        version="v1",
        fields=[
            Field(field_id=fid, name=name, type="str", description=desc)
            for fid, name, desc in fields
        ],
    )


def _step(response_text: str = "", success: bool = True) -> tuple[_FakePlugin, QwenExtractionStep]:
    plugin = _FakePlugin(response_text=response_text, success=success)
    step = QwenExtractionStep(model_plugin=plugin)
    return plugin, step


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_qwen_extraction_step_parses_flat_json_response() -> None:
    _, step = _step('{"invoice_number": "INV-001", "total_amount": "$100.00"}')
    results = step.run(_schema(), "Invoice Number: INV-001\nTotal Amount: $100.00")

    key_map = {c["key"]: c["value"] for c in results}
    assert key_map.get("invoice_number") == "INV-001"
    assert key_map.get("total_amount") == "$100.00"


def test_qwen_extraction_step_parses_entities_array_response() -> None:
    text = '{"entities": [{"key": "invoice_number", "value": "INV-001", "confidence": 0.9}]}'
    _, step = _step(text)
    results = step.run(_schema(), "Invoice Number: INV-001")

    assert any(c["key"] == "invoice_number" and c["value"] == "INV-001" for c in results)


def test_qwen_extraction_step_parses_markdown_fenced_json() -> None:
    text = '```json\n{"invoice_number": "INV-001"}\n```'
    _, step = _step(text)
    results = step.run(_schema(), "Invoice Number: INV-001")

    key_map = {c["key"]: c["value"] for c in results}
    assert key_map.get("invoice_number") == "INV-001"


def test_qwen_extraction_step_returns_empty_on_model_failure() -> None:
    _, step = _step(response_text="", success=False)
    results = step.run(_schema(), "Invoice Number: INV-001")

    assert results == []


def test_qwen_extraction_step_returns_empty_on_empty_response_text() -> None:
    _, step = _step(response_text="", success=True)
    results = step.run(_schema(), "Invoice Number: INV-001")

    assert results == []


def test_qwen_extraction_step_returns_empty_on_empty_document_text() -> None:
    _, step = _step('{"invoice_number": "INV-001"}')
    results = step.run(_schema(), "")

    assert results == []


def test_qwen_extraction_step_uses_schema_field_names_in_prompt() -> None:
    plugin, step = _step('{}')
    step.run(_schema(), "Invoice Number: INV-001\nTotal Amount: $100.00")

    assert plugin.captured_requests, "generate() was never called"
    prompt = plugin.captured_requests[0].prompt
    assert "invoice_number" in prompt
    assert "total_amount" in prompt


def test_qwen_extraction_step_uses_no_think_when_enabled() -> None:
    plugin = _FakePlugin(response_text='{}')
    step = QwenExtractionStep(model_plugin=plugin, no_think=True)
    step.run(_schema(), "Invoice Number: INV-001")

    assert plugin.captured_requests
    prompt = plugin.captured_requests[0].prompt
    assert "/no_think" in prompt


def test_qwen_extraction_step_no_think_absent_when_disabled() -> None:
    plugin = _FakePlugin(response_text='{}')
    step = QwenExtractionStep(model_plugin=plugin, no_think=False)
    step.run(_schema(), "Invoice Number: INV-001")

    assert plugin.captured_requests
    prompt = plugin.captured_requests[0].prompt
    assert "/no_think" not in prompt


def test_qwen_extraction_step_sets_system_prompt_on_request() -> None:
    plugin, step = _step('{}')
    step.run(_schema(), "Invoice Number: INV-001")

    assert plugin.captured_requests
    assert plugin.captured_requests[0].system_prompt is not None
    assert len(plugin.captured_requests[0].system_prompt) > 0


def test_qwen_extraction_step_sets_json_mode_on_request() -> None:
    plugin, step = _step('{}')
    step.run(_schema(), "Invoice Number: INV-001")

    assert plugin.captured_requests
    assert plugin.captured_requests[0].json_mode is True
    assert plugin.captured_requests[0].expected_format == "json"


def test_qwen_extraction_step_canonicalizes_model_keys_to_schema() -> None:
    # "invoice_num" scores 0.7 against "invoice_number":
    # prefix substring match adds +0.2 on top of containment 0.5.
    text = '{"invoice_num": "INV-001"}'
    _, step = _step(text)
    schema = _schema([("f1", "invoice_number", "invoice number")])
    results = step.run(schema, "Invoice Num: INV-001")

    assert results, "expected at least one candidate"
    keys = [c["key"] for c in results]
    assert "invoice_number" in keys, f"expected invoice_number in {keys}"


def test_qwen_extraction_step_merges_duplicate_keys() -> None:
    # Two entities with same canonical key — merge_by_key keeps highest confidence
    text = (
        '{"entities": ['
        '{"key": "invoice_number", "value": "INV-001", "confidence": 0.8},'
        '{"key": "invoice_number", "value": "INV-002", "confidence": 0.9}'
        ']}'
    )
    _, step = _step(text)
    results = step.run(_schema(), "Invoice Number: INV-001")

    invoice_results = [c for c in results if c["key"] == "invoice_number"]
    assert len(invoice_results) == 1
    assert invoice_results[0]["value"] == "INV-002"


def test_qwen_extraction_step_schema_hint_set_on_request() -> None:
    plugin, step = _step('{}')
    step.run(_schema(), "Invoice Number: INV-001")

    assert plugin.captured_requests
    hint = plugin.captured_requests[0].schema_hint
    assert isinstance(hint, dict)
    assert "invoice_number" in hint


def test_public_exports_available() -> None:
    from docai_core.plugins.models import QwenModelPlugin
    from docai_core.extraction import QwenExtractionStep

    assert QwenModelPlugin is not None
    assert QwenExtractionStep is not None
