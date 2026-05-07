from datetime import datetime, timezone

from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import (
    Column,
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    Job,
    Project,
    Table,
)
from docai_core.orchestration.runtime_orchestrator import RuntimeOrchestrator


def test_runtime_orchestrator_runtime_spine(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    orchestrator = RuntimeOrchestrator(artifact_store=store)
    now = datetime.now(timezone.utc)

    project = Project(
        project_id="proj-1",
        name="Demo Project",
        description="Demo",
        created_at=now,
        updated_at=now,
    )
    schema = ExtractionSchema(
        schema_id="schema-1",
        project_id="proj-1",
        name="Invoice Schema",
        description="Invoice extraction schema",
        version="v1",
        fields=[
            Field(
                field_id="f-1",
                name="invoice_number",
                description="Invoice number",
                type="string",
                required=True,
            ),
            Field(
                field_id="f-2",
                name="total_amount",
                description="Total amount",
                type="string",
                required=True,
            ),
        ],
        tables=[
            Table(
                table_id="t-1",
                name="line_items",
                description="Invoice rows",
                columns=[
                    Column(
                        column_id="c-1",
                        name="description",
                        description="Item description",
                        type="string",
                        required=True,
                    ),
                    Column(
                        column_id="c-2",
                        name="line_total",
                        description="Line total",
                        type="string",
                        required=True,
                    ),
                ],
            )
        ],
        created_at=now,
        updated_at=now,
    )
    job = Job(
        job_id="job-1",
        project_id="proj-1",
        schema_id="schema-1",
        name="Run 1",
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
            original_filename="noisy_scan_001.png",
            file_path="noisy_scan_001.png",
            status="uploaded",
            uploaded_at=now,
            profile=DocumentProfile(document_id="doc-2"),
        ),
    ]

    summary = orchestrator.run_job(project=project, schema=schema, job=job, documents=documents)

    assert summary["document_count"] == 2

    required_document_artifacts = [
        "document_profile.json",
        "selected_policy.json",
        "run_plan.json",
        "ocr_output.json",
        "extracted_output.json",
        "validation_report.json",
        "recovery_report.json",
        "final_output.json",
    ]
    for doc_id in ["doc-1", "doc-2"]:
        for filename in required_document_artifacts:
            assert store.document_artifact_path("job-1", doc_id, filename).exists()

    invoice_profile = store.read_json(store.document_artifact_path("job-1", "doc-1", "document_profile.json"))
    noisy_profile = store.read_json(store.document_artifact_path("job-1", "doc-2", "document_profile.json"))
    assert invoice_profile["document_id"] == "doc-1"
    assert noisy_profile["document_id"] == "doc-2"

    invoice_policy = store.read_json(store.document_artifact_path("job-1", "doc-1", "selected_policy.json"))
    noisy_policy = store.read_json(store.document_artifact_path("job-1", "doc-2", "selected_policy.json"))
    assert invoice_policy["policy_id"] == "invoice_table_heavy_local_v1"
    assert noisy_policy["policy_id"] == "noisy_scan_rescue_v1"
    assert isinstance(invoice_policy["reasons"], list) and len(invoice_policy["reasons"]) > 0
    assert isinstance(noisy_policy["reasons"], list) and len(noisy_policy["reasons"]) > 0
    assert isinstance(invoice_policy["disabled_candidates"], list)
    assert isinstance(noisy_policy["disabled_candidates"], list)
    for candidate in invoice_policy["disabled_candidates"]:
        assert "policy_id" in candidate
        assert "reason_disabled" in candidate
    for candidate in noisy_policy["disabled_candidates"]:
        assert "policy_id" in candidate
        assert "reason_disabled" in candidate

    invoice_run_plan = store.read_json(store.document_artifact_path("job-1", "doc-1", "run_plan.json"))
    assert "fields_to_extract" in invoice_run_plan
    assert "tables_to_extract" in invoice_run_plan

    invoice_ocr = store.read_json(store.document_artifact_path("job-1", "doc-1", "ocr_output.json"))
    assert "text" in invoice_ocr and "engine_id" in invoice_ocr

    invoice_extracted = store.read_json(store.document_artifact_path("job-1", "doc-1", "extracted_output.json"))
    assert "fields" in invoice_extracted and "tables" in invoice_extracted

    invoice_validation = store.read_json(store.document_artifact_path("job-1", "doc-1", "validation_report.json"))
    assert "pass_status" in invoice_validation

    invoice_recovery = store.read_json(store.document_artifact_path("job-1", "doc-1", "recovery_report.json"))
    assert "attempted" in invoice_recovery

    invoice_final = store.read_json(store.document_artifact_path("job-1", "doc-1", "final_output.json"))
    assert "fields" in invoice_final
    assert "tables" in invoice_final
    assert "artifact_paths" in invoice_final
    assert invoice_final["is_stub"] is True
    assert invoice_final["generated_by"] == "stub_runtime_orchestrator"
    assert "Stub output for runtime spine validation only." in invoice_final["note"]

    job_context_path = store.job_artifact_path("job-1", "job_context.json")
    document_queue_path = store.job_artifact_path("job-1", "document_queue.json")
    metrics_path = store.job_artifact_path("job-1", "metrics_report.json")
    export_path = store.job_artifact_path("job-1", "extracted_data_export.json")
    run_log_path = store.job_artifact_path("job-1", "run_log.jsonl")

    assert job_context_path.exists()
    assert document_queue_path.exists()
    assert metrics_path.exists()
    assert export_path.exists()
    assert run_log_path.exists()

    job_context = store.read_json(job_context_path)
    assert job_context["job_id"] == "job-1"
    assert job_context["project_id"] == "proj-1"
    assert job_context["schema_id"] == "schema-1"
    assert job_context["run_type"] == "training"
    assert job_context["document_count"] == 2
    assert set(job_context["queued_document_ids"]) == {"doc-1", "doc-2"}
    assert "project_context_snapshot" in job_context
    assert job_context["is_stub"] is True
    assert job_context["generated_by"] == "stub_runtime_orchestrator"

    document_queue = store.read_json(document_queue_path)
    assert document_queue["job_id"] == "job-1"
    assert document_queue["is_stub"] is True
    assert document_queue["generated_by"] == "stub_runtime_orchestrator"
    assert len(document_queue["documents"]) == 2
    queue_doc_ids = {item["document_id"] for item in document_queue["documents"]}
    assert queue_doc_ids == {"doc-1", "doc-2"}
    assert all(item["review_status"] == "required" for item in document_queue["documents"])

    metrics = store.read_json(metrics_path)
    assert metrics["is_stub"] is True
    assert metrics["metrics_status"] == "partial_stub"
    assert "Stub output for runtime spine validation only." in metrics["note"]
    # Computable runtime metrics must be populated.
    assert metrics["validation_pass_rate"] is not None
    assert metrics["validation_pass_rate"] == 1.0
    # Recovery was not attempted by the stub runner; rate is correctly None.
    assert metrics["recovery_success_rate"] is None
    # Review-dependent metrics must remain None until ReviewRecord evidence exists.
    assert metrics["precision"] is None
    assert metrics["recall"] is None
    assert metrics["f1"] is None
    assert metrics["field_accuracy"] is None
    assert metrics["table_accuracy"] is None
    assert metrics["grounding_coverage"] is None

    run_log_lines = run_log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(run_log_lines) >= 1
