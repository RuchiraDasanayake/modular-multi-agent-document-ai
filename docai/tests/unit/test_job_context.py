from datetime import datetime, timezone

from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    Job,
    Project,
    ProjectContext,
)
from docai_core.orchestration.job_context import JobContextBuilder


def test_job_context_builder_creates_job_context() -> None:
    now = datetime.now(timezone.utc)
    builder = JobContextBuilder()
    project = Project(
        project_id="proj-1",
        name="Project One",
        description="Demo",
        created_at=now,
        updated_at=now,
    )
    schema = ExtractionSchema(
        schema_id="schema-1",
        project_id="proj-1",
        name="Invoice Schema",
        description="Demo schema",
        version="v1",
        fields=[Field(field_id="f1", name="invoice_id", description="Invoice ID", type="string")],
    )
    job = Job(
        job_id="job-1",
        project_id="proj-1",
        schema_id="schema-1",
        name="Training Job",
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
        ),
        Document(
            document_id="doc-2",
            job_id="job-1",
            original_filename="invoice_002.pdf",
            file_path="invoice_002.pdf",
            status="uploaded",
            uploaded_at=now,
            profile=DocumentProfile(document_id="doc-2"),
        ),
    ]

    context = builder.build_job_context(project, schema, job, documents)

    assert context.job_id == "job-1"
    assert context.project_id == "proj-1"
    assert context.schema_id == "schema-1"
    assert context.run_type == "training"
    assert context.job_name == "Training Job"
    assert context.document_count == 2
    assert context.queued_document_ids == ["doc-1", "doc-2"]
    assert context.project_context_snapshot is not None
    assert context.project_context_snapshot.project_id == "proj-1"
    assert context.selected_ocr_preference == context.project_context_snapshot.ocr_preference
    assert context.strategy_mode == "deterministic_policy"


def test_job_context_builder_uses_copied_project_context_snapshot() -> None:
    now = datetime.now(timezone.utc)
    builder = JobContextBuilder()
    project = Project(
        project_id="proj-1",
        name="Project One",
        description="Demo",
        created_at=now,
        updated_at=now,
    )
    schema = ExtractionSchema(
        schema_id="schema-1",
        project_id="proj-1",
        name="Invoice Schema",
        description="Demo schema",
        version="v1",
    )
    job = Job(
        job_id="job-1",
        project_id="proj-1",
        schema_id="schema-1",
        name="Training Job",
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
    project_context = ProjectContext(
        project_id="proj-1",
        domain="finance",
        document_type="invoice",
        extraction_goal="Extract invoice fields and tables.",
        precision_preference="high_precision",
        local_model="qwen3.5-9b",
        ocr_preference="tesseract",
        field_hints=["invoice_id"],
        table_hints=["line_items"],
        validation_preferences={"strict": True},
        recovery_preferences={"retry": "field"},
        preferred_strategies=["invoice_table_heavy_local_v1"],
        version="v2",
        updated_at=now,
    )

    context = builder.build_job_context(project, schema, job, documents, project_context=project_context)

    assert context.project_context_snapshot is not None
    assert context.project_context_snapshot.domain == "finance"
    assert context.project_context_snapshot.document_type == "invoice"
    assert context.project_context_snapshot.local_model == "qwen3.5-9b"
    assert context.project_context_snapshot.ocr_preference == "tesseract"
    assert context.selected_ocr_preference == "tesseract"
    assert context.project_context_snapshot.field_hints == ["invoice_id"]
    assert context.project_context_snapshot.table_hints == ["line_items"]
    assert context.project_context_snapshot.validation_preferences == {"strict": True}
    assert context.project_context_snapshot.recovery_preferences == {"retry": "field"}
    assert context.project_context_snapshot.preferred_strategies == ["invoice_table_heavy_local_v1"]

    project_context.field_hints.append("total_amount")
    project_context.validation_preferences["strict"] = False
    project_context.preferred_strategies.append("invoice_basic_local_v1")

    assert context.project_context_snapshot.field_hints == ["invoice_id"]
    assert context.project_context_snapshot.validation_preferences == {"strict": True}
    assert context.project_context_snapshot.preferred_strategies == ["invoice_table_heavy_local_v1"]
