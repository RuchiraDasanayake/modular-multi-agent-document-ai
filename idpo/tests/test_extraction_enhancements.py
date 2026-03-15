from __future__ import annotations

import types
from pathlib import Path

from idpo.agents.base import AgentContext
from idpo.agents.llm_extraction import LLMExtractionAgent
from idpo.core.artifacts import ArtifactStore
from idpo.core.config import PipelineConfig
from idpo.core.provenance import ProvenanceRecorder
from idpo.core.types import Document, Entity, ModelDecision, Page


def _ctx(tmp_path: Path, config: PipelineConfig | None = None) -> AgentContext:
    cfg = config or PipelineConfig()
    artifacts = ArtifactStore(str(tmp_path / "artifacts"))
    provenance = ProvenanceRecorder(str(tmp_path / "provenance.jsonl"))
    return AgentContext(config=cfg, artifact_store=artifacts, provenance=provenance, run_id="test-run")


def _doc(text: str) -> Document:
    return Document(
        doc_id="doc-1",
        source="digital",
        path="doc.txt",
        pages=[Page(number=1, text=text, raw_text=text)],
    )


def test_messy_document_maps_to_requested_structured_fields(tmp_path: Path) -> None:
    config = PipelineConfig()
    config.llm.use_extraction = False
    agent = LLMExtractionAgent()
    ctx = _ctx(tmp_path, config)

    doc = _doc(
        "Inv No : INV-2026-77\n"
        "Client Name = ACME Corporation\n"
        "Total Due USD 1,245.50\n"
    )

    result = agent.run(
        {
            "document": doc,
            "explicit_entities": ["invoice_number", "customer_name", "total_amount"],
            "field_descriptions": {
                "invoice_number": "Invoice number or reference id",
                "customer_name": "Client or customer name",
                "total_amount": "Grand total amount due",
            },
        },
        ctx,
    )

    by_key = {entity.key: entity.value for entity in result.artifacts["entities"]}
    assert by_key["invoice_number"] == "INV-2026-77"
    assert "ACME" in by_key["customer_name"]
    assert "1,245.50" in by_key["total_amount"]


def test_local_first_cloud_fallback_targets_failed_fields(tmp_path: Path) -> None:
    config = PipelineConfig()
    config.llm.use_extraction = True
    config.llm.allow_cloud_fallback = True
    config.validation.min_confidence = 0.7

    agent = LLMExtractionAgent()
    ctx = _ctx(tmp_path, config)
    cloud_requested: list[list[str]] = []

    def fake_local(self, doc, explicit_keys, model_name, context, field_descriptions=None):  # noqa: ANN001
        return [
            Entity(
                key="invoice_number",
                value="INV-LOW",
                confidence=0.40,
                metadata={"explicit": True, "source": "llm_local"},
            )
        ]

    def fake_cloud(self, doc, explicit_keys, model_name, context, field_descriptions=None):  # noqa: ANN001
        cloud_requested.append(list(explicit_keys))
        return [
            Entity(
                key="invoice_number",
                value="INV-900",
                confidence=0.82,
                metadata={"explicit": True, "source": "llm_cloud"},
            ),
            Entity(
                key="customer_name",
                value="Globex Corporation",
                confidence=0.86,
                metadata={"explicit": True, "source": "llm_cloud"},
            ),
        ]

    agent._llm_extract = types.MethodType(fake_local, agent)
    agent._cloud_extract = types.MethodType(fake_cloud, agent)

    result = agent.run(
        {
            "document": _doc("messy unstructured text without stable labels"),
            "model": ModelDecision(mode="local", model_name="phi3:mini", reason="test"),
            "explicit_entities": ["invoice_number", "customer_name"],
            "field_descriptions": {
                "invoice_number": "invoice id or invoice number",
                "customer_name": "name of customer",
            },
        },
        ctx,
    )

    by_key = {entity.key: entity.value for entity in result.artifacts["entities"]}
    assert cloud_requested
    assert "customer_name" in cloud_requested[0]
    assert by_key["invoice_number"] == "INV-900"
    assert by_key["customer_name"] == "Globex Corporation"


def test_parser_accepts_flat_json_mapping_and_drops_missing_values() -> None:
    agent = LLMExtractionAgent()
    parsed = agent._parse_entities_response(  # noqa: SLF001
        '{"invoice_no":"INV-88","total_amount":"$88.00","customer_name":"not found"}',
        model_name="unit-test",
        source="llm_local",
    )
    by_key = {entity.key: entity.value for entity in parsed}
    assert by_key["invoice_no"] == "INV-88"
    assert by_key["total_amount"] == "$88.00"
    assert "customer_name" not in by_key


def test_cloud_mode_uses_flagship_for_unresolved_fields(tmp_path: Path) -> None:
    config = PipelineConfig()
    config.llm.use_extraction = True
    config.llm.enable_flagship_fallback = True
    config.llm.flagship_min_missing_fields = 1
    config.llm.cloud_model = "gpt-4o-mini"
    config.llm.flagship_model = "gpt-4.1"
    config.validation.min_confidence = 0.7

    agent = LLMExtractionAgent()
    ctx = _ctx(tmp_path, config)
    cloud_calls: list[tuple[str, list[str]]] = []

    def fake_cloud(self, doc, explicit_keys, model_name, context, field_descriptions=None):  # noqa: ANN001
        cloud_calls.append((model_name, list(explicit_keys)))
        if model_name == "gpt-4o-mini":
            return [
                Entity(
                    key="invoice_number",
                    value="INV-900",
                    confidence=0.86,
                    metadata={"explicit": True, "source": "llm_cloud"},
                )
            ]
        return [
            Entity(
                key="customer_name",
                value="Globex Corporation",
                confidence=0.88,
                metadata={"explicit": True, "source": "llm_cloud"},
            )
        ]

    agent._cloud_extract = types.MethodType(fake_cloud, agent)

    result = agent.run(
        {
            "document": _doc("Invoice No: INV-900\nCustomer: Globex Corporation\n"),
            "model": ModelDecision(mode="cloud", model_name="gpt-4o-mini", reason="test"),
            "explicit_entities": ["invoice_number", "customer_name"],
        },
        ctx,
    )

    by_key = {entity.key: entity.value for entity in result.artifacts["entities"]}
    diagnostics = result.artifacts["llm_diagnostics"]
    assert by_key["invoice_number"] == "INV-900"
    assert by_key["customer_name"] == "Globex Corporation"
    assert diagnostics["flagship_attempted"] is True
    assert len(cloud_calls) == 2
    assert cloud_calls[0][0] == "gpt-4o-mini"
    assert cloud_calls[1][0] == "gpt-4.1"
    assert "customer_name" in cloud_calls[1][1]


def test_openai_schema_limits_keys_to_requested_fields() -> None:
    agent = LLMExtractionAgent()
    response_format = agent._openai_response_format(["Invoice Number", "total_amount", "total_amount"])  # noqa: SLF001
    schema = response_format["json_schema"]["schema"]
    key_schema = schema["properties"]["entities"]["items"]["properties"]["key"]

    assert response_format["type"] == "json_schema"
    assert key_schema["enum"] == ["invoice_number", "total_amount"]


def test_description_refinement_falls_back_to_base_descriptions(tmp_path: Path, monkeypatch) -> None:
    config = PipelineConfig()
    config.llm.refine_field_descriptions = True
    config.llm.openai_api_key = ""
    ctx = _ctx(tmp_path, config)
    agent = LLMExtractionAgent()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    refined, meta = agent._refine_field_descriptions(  # noqa: SLF001
        ["invoice_number", "customer_name"],
        {"invoice_number": "invoice id"},
        ctx,
    )

    assert refined["invoice_number"] == "invoice id"
    assert refined["customer_name"] == "customer name"
    assert meta["attempted"] is False


def test_explicit_field_jobs_suppress_generic_spillover(tmp_path: Path) -> None:
    config = PipelineConfig()
    config.llm.use_extraction = False
    agent = LLMExtractionAgent()
    ctx = _ctx(tmp_path, config)

    doc = _doc(
        "Invoice Number: INV-100\n"
        "Vendor Name: Contoso LLC\n"
        "Department: Finance\n"
    )
    result = agent.run(
        {
            "document": doc,
            "explicit_entities": ["invoice_number"],
        },
        ctx,
    )
    keys = {entity.key for entity in result.artifacts["entities"]}
    assert "invoice_number" in keys
    assert "vendor_name" not in keys
    assert "department" not in keys
