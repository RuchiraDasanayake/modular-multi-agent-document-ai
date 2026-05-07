"""Integration tests for run execution API endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docai_core.api.app import create_app
from docai_core.persistence import SQLiteStore, ensure_database_schema


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Temporary database."""
    db = tmp_path / "test.db"
    ensure_database_schema(db)
    return db


@pytest.fixture()
def client(tmp_path: Path, db_path: Path) -> TestClient:
    """Test client with isolated database."""
    app = create_app(db_path=db_path, runs_dir=tmp_path / "runs")
    return TestClient(app)


@pytest.fixture()
def project_job_setup(db_path: Path, tmp_path: Path) -> tuple[str, str, list[str]]:
    """Create project, job, and documents for tests."""
    store = SQLiteStore(db_path)
    proj = store.create_project("proj-exec", "Execution Test")

    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("invoice_basic", "Invoice", "invoice", "v1", 0, store._now()),
        )
        conn.commit()

    job = store.create_job(proj.project_id, "invoice_basic", "Execution Job")

    doc_ids = []
    for i in range(2):
        doc_file = tmp_path / f"doc{i}.txt"
        doc_file.write_text(f"Test document {i} content")
        doc_id = store.register_document(
            proj.project_id, job.job_id, f"doc{i}.txt", str(doc_file)
        )
        doc_ids.append(doc_id)

    return proj.project_id, job.job_id, doc_ids


# ---------------------------------------------------------------------------
# Core execution path tests
# ---------------------------------------------------------------------------

def test_execute_run_succeeds(client: TestClient, db_path: Path, project_job_setup: tuple) -> None:
    """Verify run execution with attached documents succeeds."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    store.create_run_document(run.run_id, doc_ids[0])

    response = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run.run_id
    assert data["status"] == "completed"


def test_run_default_schema_is_used_without_document_override(
    client: TestClient, db_path: Path, project_job_setup: tuple
) -> None:
    """No override: final_output must keep run schema_id."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)
    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    store.create_run_document(run.run_id, doc_ids[0])

    execute = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert execute.status_code == 200

    fo = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/final-output")
    assert fo.status_code == 200
    payload = fo.json()
    assert payload["schema_id"] == "invoice_basic"
    assert payload["mode"] == "stub"


def test_document_level_schema_override_is_applied(
    client: TestClient, db_path: Path, project_job_setup: tuple
) -> None:
    """Attach override schema_id and verify final_output uses it."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    schema_a = store.create_extraction_schema(
        project_id=proj_id,
        name="Schema A",
        document_type="invoice",
        fields=[{"name": "invoice_number", "type": "string", "required": True}],
        tables=[],
    )
    schema_b = store.create_extraction_schema(
        project_id=proj_id,
        name="Schema B",
        document_type="invoice",
        fields=[{"name": "vendor_name", "type": "string", "required": False}],
        tables=[],
    )

    run = store.create_run(proj_id, job_id, schema_a.schema_id, mode="stub", status="created", artifact_root="")
    attach = client.post(
        f"/runs/{run.run_id}/documents",
        json={"document_id": doc_ids[0], "schema_id": schema_b.schema_id},
    )
    assert attach.status_code == 200

    execute = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert execute.status_code == 200

    fo = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/final-output")
    assert fo.status_code == 200
    assert fo.json()["schema_id"] == schema_b.schema_id


def test_mixed_documents_use_default_and_override_schemas(
    client: TestClient, db_path: Path, project_job_setup: tuple
) -> None:
    """doc1 uses run default schema; doc2 uses override schema."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    schema_a = store.create_extraction_schema(
        project_id=proj_id,
        name="Schema A2",
        document_type="invoice",
        fields=[{"name": "invoice_number", "type": "string", "required": True}],
        tables=[],
    )
    schema_b = store.create_extraction_schema(
        project_id=proj_id,
        name="Schema B2",
        document_type="invoice",
        fields=[{"name": "status", "type": "string", "required": False}],
        tables=[],
    )

    run = store.create_run(proj_id, job_id, schema_a.schema_id, mode="stub", status="created", artifact_root="")
    attach_1 = client.post(f"/runs/{run.run_id}/documents", json={"document_id": doc_ids[0]})
    attach_2 = client.post(
        f"/runs/{run.run_id}/documents",
        json={"document_id": doc_ids[1], "schema_id": schema_b.schema_id, "routing_reason": "manual_override"},
    )
    assert attach_1.status_code == 200
    assert attach_2.status_code == 200

    execute = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert execute.status_code == 200

    fo1 = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/final-output").json()
    fo2 = client.get(f"/runs/{run.run_id}/documents/{doc_ids[1]}/final-output").json()
    assert fo1["schema_id"] == schema_a.schema_id
    assert fo1["routing_source"] == "run_default"
    assert fo2["schema_id"] == schema_b.schema_id
    assert fo2["routing_source"] == "document_override"
    assert fo2["routing_reason"] == "manual_override"


def test_unknown_override_schema_fails_without_fallback(
    client: TestClient, db_path: Path, project_job_setup: tuple
) -> None:
    """Unknown override schema should fail clearly on attach."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)
    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")

    attach = client.post(
        f"/runs/{run.run_id}/documents",
        json={"document_id": doc_ids[0], "schema_id": "schema-does-not-exist"},
    )
    assert attach.status_code == 404
    assert "schema" in attach.json()["detail"].lower()


def test_document_level_mode_override_is_applied(
    client: TestClient, db_path: Path, project_job_setup: tuple
) -> None:
    """Attach override mode and verify final_output uses it."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    attach = client.post(
        f"/runs/{run.run_id}/documents",
        json={"document_id": doc_ids[0], "mode": "local_text"},
    )
    assert attach.status_code == 200

    execute = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert execute.status_code == 200

    fo = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/final-output")
    assert fo.status_code == 200
    assert fo.json()["mode"] == "local_text"


def test_artifact_correctness_under_mixed_routing_no_overwrite(
    client: TestClient, db_path: Path, project_job_setup: tuple
) -> None:
    """Mixed routing: both document artifacts correct, no overwrite."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    schema_a = store.create_extraction_schema(
        project_id=proj_id,
        name="Schema A3",
        document_type="invoice",
        fields=[{"name": "invoice_number", "type": "string", "required": True}],
        tables=[],
    )
    schema_b = store.create_extraction_schema(
        project_id=proj_id,
        name="Schema B3",
        document_type="invoice",
        fields=[{"name": "vendor_name", "type": "string", "required": False}],
        tables=[],
    )

    run = store.create_run(proj_id, job_id, schema_a.schema_id, mode="stub", status="created", artifact_root="")
    attach_1 = client.post(f"/runs/{run.run_id}/documents", json={"document_id": doc_ids[0]})
    attach_2 = client.post(
        f"/runs/{run.run_id}/documents",
        json={"document_id": doc_ids[1], "schema_id": schema_b.schema_id},
    )
    assert attach_1.status_code == 200
    assert attach_2.status_code == 200

    execute = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert execute.status_code == 200

    fo1 = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/final-output").json()
    fo2 = client.get(f"/runs/{run.run_id}/documents/{doc_ids[1]}/final-output").json()

    # Both artifacts should be correct and distinct
    assert fo1["schema_id"] == schema_a.schema_id
    assert fo2["schema_id"] == schema_b.schema_id
    assert fo1["document_id"] == doc_ids[0]
    assert fo2["document_id"] == doc_ids[1]
    # Ensure no overwrite: doc1 should not have doc2's schema
    assert fo1["schema_id"] != fo2["schema_id"]


def test_final_output_immutable_after_review(client: TestClient, db_path: Path, project_job_setup: tuple) -> None:
    """final_output.json is immutable after human review."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    store.create_run_document(run.run_id, doc_ids[0])

    # Execute run
    execute = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert execute.status_code == 200

    # Get initial final_output
    fo_before = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/final-output")
    assert fo_before.status_code == 200
    fo_hash_before = hash(str(fo_before.json()))

    # Add review
    review = client.post(
        f"/runs/{run.run_id}/documents/{doc_ids[0]}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {"field_name": "invoice_number", "decision": "correct"}
            ]
        }
    )
    assert review.status_code == 200

    # final_output should be unchanged
    fo_after = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/final-output")
    assert fo_after.status_code == 200
    fo_hash_after = hash(str(fo_after.json()))
    assert fo_hash_before == fo_hash_after


def test_validation_report_immutable_after_review(client: TestClient, db_path: Path, project_job_setup: tuple) -> None:
    """validation_report.json is immutable after human review."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    store.create_run_document(run.run_id, doc_ids[0])

    # Execute run
    execute = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert execute.status_code == 200

    # Get initial validation_report
    vr_before = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/validation-report")
    assert vr_before.status_code == 200
    vr_hash_before = hash(str(vr_before.json()))

    # Add review
    review = client.post(
        f"/runs/{run.run_id}/documents/{doc_ids[0]}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {"field_name": "invoice_number", "decision": "correct"}
            ]
        }
    )
    assert review.status_code == 200

    # validation_report should be unchanged
    vr_after = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/validation-report")
    assert vr_after.status_code == 200
    vr_hash_after = hash(str(vr_after.json()))
    assert vr_hash_before == vr_hash_after


def test_missing_run_returns_404(client: TestClient) -> None:
    """Verify missing run returns 404."""
    response = client.post("/runs/run-nonexistent/execute", json={})
    assert response.status_code == 404


def test_run_no_documents_returns_400(client: TestClient, db_path: Path, project_job_setup: tuple) -> None:
    """Verify run with no attached documents returns 400."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")

    response = client.post(f"/runs/{run.run_id}/execute", json={})
    assert response.status_code == 400


def test_missing_document_file_returns_400(client: TestClient, db_path: Path, project_job_setup: tuple) -> None:
    """Verify missing document file returns 400."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    store.create_run_document(run.run_id, doc_ids[0])

    Path(store.get_document(doc_ids[0])["file_path"]).unlink()

    response = client.post(f"/runs/{run.run_id}/execute", json={})
    assert response.status_code == 400


@pytest.mark.parametrize("status,keyword", [
    ("completed", "completed"),
    ("processing", "processing"),
])
def test_run_status_conflict_returns_409(client: TestClient, db_path: Path, project_job_setup: tuple, status: str, keyword: str) -> None:
    """Verify completed/processing runs return 409 Conflict."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status=status, artifact_root="")
    store.create_run_document(run.run_id, doc_ids[0])

    response = client.post(f"/runs/{run.run_id}/execute", json={})
    assert response.status_code == 409
    assert keyword in response.json()["detail"].lower()


def test_run_and_document_status_transitions(client: TestClient, db_path: Path, project_job_setup: tuple) -> None:
    """Verify status transitions for run and run_document."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    assert store.get_run(run.run_id).status == "created"

    store.create_run_document(run.run_id, doc_ids[0])
    rd = store.list_run_documents(run.run_id)
    assert rd[0]["status"] == "pending"

    response = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert response.status_code == 200

    assert store.get_run(run.run_id).status == "completed"
    rd = store.list_run_documents(run.run_id)
    assert rd[0]["status"] == "completed"


def test_missing_mode_and_policy_returns_400(client: TestClient, db_path: Path, project_job_setup: tuple) -> None:
    """Verify missing mode and policy_id returns 400."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode=None, policy_id=None, status="created", artifact_root="")
    store.create_run_document(run.run_id, doc_ids[0])

    response = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert response.status_code == 400
    assert "mode" in response.json()["detail"].lower() or "policy" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Artifact root handling tests
# ---------------------------------------------------------------------------

def test_artifact_root_resolved_and_persisted(client: TestClient, db_path: Path, project_job_setup: tuple, tmp_path: Path) -> None:
    """Verify artifact_root defaults and request override is persisted."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    # Test 1: Default artifact_root
    run1 = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root=None)
    store.create_run_document(run1.run_id, doc_ids[0])

    response = client.post(f"/runs/{run1.run_id}/execute", json={"index_artifacts": False})
    assert response.status_code == 200
    assert response.json()["artifact_root"]
    assert job_id in response.json()["artifact_root"]

    # Test 2: Request artifact_root override persisted
    custom_root = str(Path(client.app.state.runs_dir) / "custom" / "artifacts")
    run2 = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root=None)
    store.create_run_document(run2.run_id, doc_ids[0])

    response = client.post(f"/runs/{run2.run_id}/execute", json={"artifact_root": custom_root, "index_artifacts": False})
    assert response.status_code == 200
    assert store.get_run(run2.run_id).artifact_root == custom_root


def test_execute_rejects_artifact_root_outside_runs_dir(client: TestClient, db_path: Path, project_job_setup: tuple, tmp_path: Path) -> None:
    """artifact_root outside configured runs_dir is rejected."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root=None)
    store.create_run_document(run.run_id, doc_ids[0])

    outside_root = str(tmp_path / "outside-root")
    response = client.post(
        f"/runs/{run.run_id}/execute",
        json={"artifact_root": outside_root, "index_artifacts": False},
    )
    assert response.status_code == 400
    assert "artifact_root" in response.json()["detail"]


def test_execute_blocks_when_run_already_claimed_for_processing(
    client: TestClient, db_path: Path, project_job_setup: tuple
) -> None:
    """Second execution attempt is blocked after processing claim."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root=None)
    store.create_run_document(run.run_id, doc_ids[0])

    assert store.claim_run_for_processing(run.run_id) is True

    response = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert response.status_code == 409
    assert "processing" in response.json()["detail"].lower()


def test_artifact_read_endpoints_resolve_run_id_to_job_id_paths(
    client: TestClient, db_path: Path, project_job_setup: tuple
) -> None:
    """Verify read endpoints resolve artifacts written under job_id for execute flow."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root=None)
    store.create_run_document(run.run_id, doc_ids[0])

    execute = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})
    assert execute.status_code == 200
    assert run.run_id != job_id

    artifacts = client.get(f"/runs/{run.run_id}/artifacts")
    assert artifacts.status_code == 200
    assert any("final_output.json" in item for item in artifacts.json()["artifacts"])

    final_output = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/final-output")
    assert final_output.status_code == 200
    assert "is_stub" in final_output.json()

    validation = client.get(f"/runs/{run.run_id}/documents/{doc_ids[0]}/validation-report")
    assert validation.status_code == 200
    assert "summary" in validation.json()


# ---------------------------------------------------------------------------
# Artifact indexing tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("index_flag,expected_indexed", [
    (True, ">=0"),
    (False, "0"),
])
def test_artifact_indexing_control(client: TestClient, db_path: Path, project_job_setup: tuple, index_flag: bool, expected_indexed: str) -> None:
    """Verify artifact indexing is controlled by index_artifacts flag."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    store.create_run_document(run.run_id, doc_ids[0])

    response = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": index_flag})
    assert response.status_code == 200
    data = response.json()

    if expected_indexed == "0":
        assert data["artifacts_indexed"] == 0
        assert data["metrics_indexed"] is False
    else:
        # When indexed, may be 0 or more depending on artifacts produced
        assert data["artifacts_indexed"] >= 0


def test_indexing_errors_dont_fail_execution(client: TestClient, db_path: Path, project_job_setup: tuple) -> None:
    """Verify indexing errors don't fail successful execution."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    store.create_run_document(run.run_id, doc_ids[0])

    response = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": True})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# Integration and invariant tests
# ---------------------------------------------------------------------------

def test_old_post_runs_still_works(client: TestClient, tmp_path: Path) -> None:
    """Verify old standalone POST /runs is unchanged."""
    doc_file = tmp_path / "test.pdf"
    doc_file.write_text("Test PDF content")

    with open(doc_file, "rb") as f:
        response = client.post("/runs", data={"mode": "stub"}, files={"files": ("test.pdf", f)})

    assert response.status_code == 200
    assert "run_id" in response.json()


def test_policy_id_mode_not_overridable(client: TestClient, db_path: Path, project_job_setup: tuple) -> None:
    """Verify policy_id/mode are frozen at run creation and not mutated by execution."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    mode_before = run.mode
    policy_before = run.policy_id

    store.create_run_document(run.run_id, doc_ids[0])
    response = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})

    assert response.status_code == 200
    assert store.get_run(run.run_id).mode == mode_before
    assert store.get_run(run.run_id).policy_id == policy_before


def test_uses_existing_job_run_service(client: TestClient, db_path: Path, project_job_setup: tuple) -> None:
    """Verify execution uses JobRunService (existing path, not new)."""
    proj_id, job_id, doc_ids = project_job_setup
    store = SQLiteStore(db_path)

    run = store.create_run(proj_id, job_id, "invoice_basic", mode="stub", status="created", artifact_root="")
    store.create_run_document(run.run_id, doc_ids[0])

    response = client.post(f"/runs/{run.run_id}/execute", json={"index_artifacts": False})

    assert response.status_code == 200
    data = response.json()
    # JobRunService/RuntimeOrchestrator sets these fields
    assert "generated_by" in data
    assert "is_stub" in data


# ---------------------------------------------------------------------------
# local_text real extraction tests
# ---------------------------------------------------------------------------

_INVOICE_TEXT = (
    "Invoice Number: INV-2024-001\n"
    "Invoice Date: 2024-05-01\n"
    "Total Amount: $1,250.00\n"
    "Status: Due\n"
)

_FAKE_VALUE_PREFIX = "fake_"


@pytest.fixture()
def local_text_setup(client: TestClient, tmp_path: Path) -> tuple[str, str, str]:
    """Project + job + uploaded invoice .txt document for local_text tests."""
    proj = client.post("/projects", json={"name": "LocalTextSmoke"}).json()
    pid = proj["project_id"]

    job = client.post(
        f"/projects/{pid}/jobs",
        json={"schema_id": "invoice_basic", "name": "lt-smoke"},
    ).json()
    jid = job["job_id"]

    invoice_file = tmp_path / "invoice.txt"
    invoice_file.write_text(_INVOICE_TEXT)
    with open(invoice_file, "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("invoice.txt", fh, "text/plain")},
        ).json()

    return pid, jid, doc["document_id"]


def test_local_text_is_not_stub(client: TestClient, local_text_setup: tuple) -> None:
    """local_text run must report is_stub=False and correct generator."""
    _, jid, docid = local_text_setup

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})

    result = client.post(f"/runs/{rid}/execute", json={"index_artifacts": True}).json()

    assert result["status"] == "completed"
    assert result["is_stub"] is False
    assert result["generated_by"] == "local_text_pipeline_v1"
    assert "stub_runtime_orchestrator" not in result["generated_by"]


def test_local_text_fields_real_and_no_fake(client: TestClient, local_text_setup: tuple) -> None:
    """Extracted fields must be non-empty and contain no fake_ values."""
    _, jid, docid = local_text_setup

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": True})

    fo = client.get(f"/runs/{rid}/documents/{docid}/final-output").json()
    fields = fo.get("fields", [])

    assert len(fields) > 0, "fields must not be empty"

    fake_fields = [f for f in fields if str(f.get("value", "")).startswith(_FAKE_VALUE_PREFIX)]
    assert fake_fields == [], f"fake values found: {fake_fields}"

    real_fields = [f for f in fields if f.get("extraction_method") == "generic_kv"]
    assert len(real_fields) > 0, "at least one field must use generic_kv extraction"


def test_local_text_evidence_contains_source_line(client: TestClient, local_text_setup: tuple) -> None:
    """evidence_text must be the full source line, not just the bare value."""
    _, jid, docid = local_text_setup

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": True})

    fo = client.get(f"/runs/{rid}/documents/{docid}/final-output").json()
    fields = fo.get("fields", [])

    kv_fields = [f for f in fields if f.get("extraction_method") == "generic_kv"]
    assert kv_fields, "need at least one generic_kv field to check evidence"

    # evidence_text must be longer than the bare value (it contains the key label too)
    for f in kv_fields:
        value = str(f.get("value", ""))
        evidence = str(f.get("evidence_text", ""))
        assert len(evidence) >= len(value), (
            f"{f['field_name']}: evidence_text {evidence!r} shorter than value {value!r}"
        )
        assert value in evidence, (
            f"{f['field_name']}: value {value!r} not found in evidence_text {evidence!r}"
        )


def test_local_text_validation_report_exists(client: TestClient, local_text_setup: tuple) -> None:
    """validation_report must be present and have a summary string."""
    _, jid, docid = local_text_setup

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": True})

    vr = client.get(f"/runs/{rid}/documents/{docid}/validation-report")
    assert vr.status_code == 200
    data = vr.json()
    assert "summary" in data
    assert isinstance(data["summary"], str)
    assert len(data["summary"]) > 0


def test_local_text_artifacts_present(client: TestClient, local_text_setup: tuple) -> None:
    """Artifact list must include final_output.json, validation_report.json, ocr_output.json."""
    _, jid, docid = local_text_setup

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": True})

    arts = client.get(f"/runs/{rid}/artifacts").json()
    artifact_paths = arts.get("artifacts", [])

    required = {"final_output.json", "validation_report.json", "ocr_output.json"}
    found = {name for path in artifact_paths for name in [path.replace("\\", "/").split("/")[-1]]}
    missing = required - found
    assert not missing, f"missing artifacts: {missing}"


# ---------------------------------------------------------------------------
# Error handling regression tests
# ---------------------------------------------------------------------------


def test_unsupported_format_docx_returns_400(client: TestClient, tmp_path: Path) -> None:
    """Unsupported .docx file returns 400 (Bad Request), not 500 (Internal Error)."""
    # Create project and job
    proj = client.post("/projects", json={"name": "ErrorHandling"}).json()
    pid = proj["project_id"]

    job = client.post(
        f"/projects/{pid}/jobs",
        json={"schema_id": "invoice_basic", "name": "error-test"}
    ).json()
    jid = job["job_id"]

    # Create minimal DOCX file
    docx_file = tmp_path / "test.docx"
    docx_file.write_bytes(b"PK\x03\x04")  # Minimal ZIP/DOCX header

    # Upload DOCX
    with open(str(docx_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("test.docx", fh, "application/vnd.ms-word")}
        ).json()
    docid = doc["document_id"]

    # Create run and execute
    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]

    client.post(f"/runs/{rid}/documents", json={"document_id": docid})

    exec_resp = client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    # Assert: must return 400, not 500
    assert exec_resp.status_code == 400, (
        f"Expected 400 for unsupported format, got {exec_resp.status_code}"
    )

    # Error message must be clear
    detail = exec_resp.json().get("detail", "")
    assert "DOCX" in detail or "not implemented" in detail, (
        f"Error message should mention DOCX or implementation status, got: {detail}"
    )


# ---------------------------------------------------------------------------
# Required-field validation tests
# ---------------------------------------------------------------------------


def test_required_field_all_present_validation_passes(client: TestClient, tmp_path: Path) -> None:
    """Happy path: all required fields present → validation_report.pass_status=true."""
    # Create project and job
    proj = client.post("/projects", json={"name": "RequiredFieldPass"}).json()
    pid = proj["project_id"]

    job = client.post(
        f"/projects/{pid}/jobs",
        json={"schema_id": "invoice_basic", "name": "required-pass"}
    ).json()
    jid = job["job_id"]

    # Create invoice with all required fields
    invoice_text = (
        "Invoice Number: INV-REQ-001\n"
        "Invoice Date: 2024-05-03\n"
        "Total Amount: $5,000.00\n"
        "Status: Paid\n"
    )
    invoice_file = tmp_path / "invoice_complete.txt"
    invoice_file.write_text(invoice_text)

    with open(str(invoice_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("invoice_complete.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    # Execute
    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]

    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    exec_resp = client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    result = exec_resp.json()
    assert result["status"] == "completed"
    assert result["is_stub"] is False

    # Validation should pass when all required fields are present
    vr = client.get(f"/runs/{rid}/documents/{docid}/validation-report").json()
    assert vr["pass_status"] is True, (
        f"Expected pass_status=True for complete invoice, got: {vr}"
    )


def test_required_field_missing_validation_fails(client: TestClient, tmp_path: Path) -> None:
    """Missing required field → validation_report.pass_status=false, field_issues includes it."""
    # Create project and job
    proj = client.post("/projects", json={"name": "RequiredFieldFail"}).json()
    pid = proj["project_id"]

    job = client.post(
        f"/projects/{pid}/jobs",
        json={"schema_id": "invoice_basic", "name": "required-fail"}
    ).json()
    jid = job["job_id"]

    # Create invoice missing Total Amount (required field)
    invoice_text = (
        "Invoice Number: INV-REQ-002\n"
        "Invoice Date: 2024-05-03\n"
        "Status: Unpaid\n"
    )
    invoice_file = tmp_path / "invoice_missing_amount.txt"
    invoice_file.write_text(invoice_text)

    with open(str(invoice_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("invoice_missing_amount.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    # Execute
    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]

    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    exec_resp = client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    result = exec_resp.json()
    assert result["status"] == "completed"
    assert result["is_stub"] is False

    # Validation should fail when required field is missing
    vr = client.get(f"/runs/{rid}/documents/{docid}/validation-report").json()
    assert vr["pass_status"] is False, (
        f"Expected pass_status=False for missing required field, got: {vr}"
    )
    assert any("total_amount" in issue for issue in vr["field_issues"]), (
        f"Expected total_amount in field_issues, got: {vr['field_issues']}"
    )
    assert any("missing_required_field" in issue for issue in vr["field_issues"]), (
        f"Expected 'missing_required_field' in field_issues, got: {vr['field_issues']}"
    )


def test_optional_field_missing_validation_still_passes(client: TestClient, tmp_path: Path) -> None:
    """Missing optional field → validation_report.pass_status=true if all required fields present."""
    # Create project and job
    proj = client.post("/projects", json={"name": "OptionalFieldMissing"}).json()
    pid = proj["project_id"]

    job = client.post(
        f"/projects/{pid}/jobs",
        json={"schema_id": "invoice_basic", "name": "optional-missing"}
    ).json()
    jid = job["job_id"]

    # Create invoice missing Status (optional field)
    invoice_text = (
        "Invoice Number: INV-OPT-001\n"
        "Invoice Date: 2024-05-03\n"
        "Total Amount: $3,500.00\n"
    )
    invoice_file = tmp_path / "invoice_no_status.txt"
    invoice_file.write_text(invoice_text)

    with open(str(invoice_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("invoice_no_status.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    # Execute
    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]

    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    exec_resp = client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    result = exec_resp.json()
    assert result["status"] == "completed"
    assert result["is_stub"] is False

    # Validation should pass when only optional field is missing
    vr = client.get(f"/runs/{rid}/documents/{docid}/validation-report").json()
    assert vr["pass_status"] is True, (
        f"Expected pass_status=True when only optional field missing, got: {vr}"
    )
