from __future__ import annotations

from docai_core.extraction import parse_entities_response, parse_json_payload


def test_parse_json_payload_direct_object() -> None:
    result = parse_json_payload('{"invoice_number": "INV-001"}')
    assert isinstance(result, dict)
    assert result["invoice_number"] == "INV-001"


def test_parse_json_payload_direct_array() -> None:
    result = parse_json_payload('[{"key": "invoice_number", "value": "INV-001"}]')
    assert isinstance(result, list)
    assert result[0]["key"] == "invoice_number"


def test_parse_json_payload_markdown_fenced_json() -> None:
    # parse_json_payload uses brace extraction — the JSON inside fences is found
    # on the second pass (find outermost {...}).
    fenced = '```json\n{"total": "100.00"}\n```'
    result = parse_json_payload(fenced)
    assert isinstance(result, dict)
    assert result["total"] == "100.00"


def test_parse_json_payload_embedded_object() -> None:
    result = parse_json_payload('Here is the result: {"total": "100.00"} thanks')
    assert isinstance(result, dict)
    assert result["total"] == "100.00"


def test_parse_json_payload_invalid_returns_none() -> None:
    assert parse_json_payload("this is not json at all") is None
    assert parse_json_payload("") is None
    assert parse_json_payload("   ") is None


def test_parse_entities_response_flat_dict() -> None:
    response = '{"invoice_number": "INV-001", "total": "100.00"}'
    result = parse_entities_response(response, model_name="m", source="s")
    assert isinstance(result, list)
    keys = {item["key"] for item in result}
    assert "invoice_number" in keys
    assert "total" in keys
    # flat dict path assigns confidence 0.65
    for item in result:
        assert item["confidence"] == 0.65


def test_parse_entities_response_array_of_key_value_objects() -> None:
    response = '[{"key": "invoice_number", "value": "INV-001", "confidence": 0.9}]'
    result = parse_entities_response(response, model_name="m", source="s")
    assert len(result) == 1
    assert result[0]["key"] == "invoice_number"
    assert result[0]["value"] == "INV-001"
    assert result[0]["confidence"] == 0.9
    assert result[0]["metadata"]["explicit"] is True


def test_parse_entities_response_markdown_wrapped() -> None:
    response = '```json\n{"entities": [{"key": "total", "value": "100.00"}]}\n```'
    result = parse_entities_response(response, model_name="m", source="s")
    assert len(result) == 1
    assert result[0]["key"] == "total"
    assert result[0]["value"] == "100.00"
    # default confidence when not supplied
    assert result[0]["confidence"] == 0.7


def test_parse_entities_response_skips_missing_value_markers() -> None:
    # Legacy skips items whose value is in MISSING_VALUE_MARKERS.
    response = '[{"key": "vendor", "value": "n/a"}, {"key": "total", "value": "99.00"}]'
    result = parse_entities_response(response, model_name="m", source="s")
    keys = {item["key"] for item in result}
    assert "vendor" not in keys
    assert "total" in keys


def test_public_exports_available() -> None:
    assert callable(parse_json_payload)
    assert callable(parse_entities_response)
    # Smoke-test import path
    result = parse_json_payload('{"x": 1}')
    assert result == {"x": 1}
