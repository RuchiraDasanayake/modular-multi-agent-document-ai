from datetime import datetime, timezone

from docai_core.contracts.domain import Document, DocumentProfile, Job
from docai_core.orchestration.document_queue import DocumentQueueBuilder


def test_document_queue_builder_training_requires_review() -> None:
    now = datetime.now(timezone.utc)
    job = Job(
        job_id="job-1",
        project_id="proj-1",
        schema_id="schema-1",
        name="Training",
        run_type="training",
        status="queued",
        created_at=now,
    )
    documents = [
        Document(
            document_id="doc-1",
            job_id="job-1",
            original_filename="invoice_001.pdf",
            file_path="invoice_001.pdf",
            status="uploaded",
            uploaded_at=now,
            profile=DocumentProfile(document_id="doc-1"),
        )
    ]

    queue = DocumentQueueBuilder().build_queue(job, documents)

    assert len(queue) == 1
    assert queue[0].document_id == "doc-1"
    assert queue[0].job_id == "job-1"
    assert queue[0].filename == "invoice_001.pdf"
    assert queue[0].file_path == "invoice_001.pdf"
    assert queue[0].queue_status == "queued"
    assert queue[0].profile_status == "pending"
    assert queue[0].strategy_status == "pending"
    assert queue[0].processing_status == "not_started"
    assert queue[0].review_status == "required"


def test_document_queue_builder_production_optional_review() -> None:
    now = datetime.now(timezone.utc)
    job = Job(
        job_id="job-2",
        project_id="proj-1",
        schema_id="schema-1",
        name="Production",
        run_type="production",
        status="queued",
        created_at=now,
    )
    documents = [
        Document(
            document_id="doc-2",
            job_id="job-2",
            original_filename="receipt_001.pdf",
            file_path="receipt_001.pdf",
            status="uploaded",
            uploaded_at=now,
            profile=DocumentProfile(document_id="doc-2"),
        )
    ]

    queue = DocumentQueueBuilder().build_queue(job, documents)

    assert len(queue) == 1
    assert queue[0].document_id == "doc-2"
    assert queue[0].job_id == "job-2"
    assert queue[0].filename == "receipt_001.pdf"
    assert queue[0].file_path == "receipt_001.pdf"
    assert queue[0].queue_status == "queued"
    assert queue[0].profile_status == "pending"
    assert queue[0].strategy_status == "pending"
    assert queue[0].processing_status == "not_started"
    assert queue[0].review_status == "optional"
