"""
Tests for AHMN core infrastructure:
  1. Pydantic schemas — request/response validation
  2. EmbeddingService — vector generation for similarity search
"""
import pytest
from uuid import uuid4

from ahmn_core.schemas import (
    DocumentContext, OutcomeMetrics, PolicyResponse, LogRequest, FeedbackRequest,
)
from ahmn_core.services.embedding import EmbeddingService


# ── Schemas ───────────────────────────────────────────────────────

class TestSchemas:

    def test_document_context_defaults(self):
        ctx = DocumentContext(doc_type="invoice")
        assert ctx.vendor is None
        assert ctx.extra_context == {}

    def test_outcome_metrics_validation(self):
        m = OutcomeMetrics(f1_score=0.92, cost=0.05, processing_time_ms=230, success=True)
        assert m.f1_score == 0.92
        with pytest.raises(Exception):
            OutcomeMetrics(f1_score=0.92)  # type: ignore  — missing required fields

    def test_policy_response(self):
        pr = PolicyResponse(
            advice_id=uuid4(), policy_id="ocr_tesseract",
            policy_data={"engine": "tesseract"}, retrieval_source="LTM",
            confidence=0.85, rabi_used=True, n_neighbors=3,
        )
        assert pr.rabi_used is True
        assert pr.retrieval_source == "LTM"

    def test_log_and_feedback(self):
        lr = LogRequest(
            advice_id=uuid4(), policy_id_used="ocr_tesseract",
            metrics=OutcomeMetrics(f1_score=0.9, cost=0.1, processing_time_ms=100, success=True),
        )
        assert lr.metrics.f1_score == 0.9

        fr = FeedbackRequest(advice_id=uuid4(), human_corrected=True)
        assert fr.human_corrected is True


# ── Embeddings ────────────────────────────────────────────────────

class TestEmbeddings:

    @pytest.fixture(autouse=True)
    def _svc(self):
        self.svc = EmbeddingService()

    def test_produces_384_dim_vector(self):
        vec = self.svc.generate_embedding("invoice from acme")
        assert len(vec) == 384
        assert all(isinstance(v, float) for v in vec)

    def test_deterministic(self):
        v1 = self.svc.generate_embedding("invoice from acme")
        v2 = self.svc.generate_embedding("invoice from acme")
        assert v1 == v2

    def test_different_inputs_differ(self):
        v1 = self.svc.generate_embedding("invoice from acme")
        v2 = self.svc.generate_embedding("receipt from walmart")
        assert v1 != v2

    def test_singleton(self):
        a = EmbeddingService()
        b = EmbeddingService()
        assert a is b
