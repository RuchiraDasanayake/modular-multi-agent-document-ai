-- SQLite schema for DocAI v2 platform control plane and evidence store.
-- Append-only design: evidence records are never overwritten, only added.

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_schemas_index (
    schema_id TEXT PRIMARY KEY,
    project_id TEXT,
    name TEXT NOT NULL,
    document_type TEXT NOT NULL,
    version TEXT NOT NULL,
    schema_path TEXT,
    is_builtin INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_schemas (
    schema_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    document_type TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    schema_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    profile_id TEXT,
    default_mode TEXT,
    name TEXT NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (schema_id) REFERENCES extraction_schemas_index(schema_id)
);

CREATE TABLE IF NOT EXISTS extraction_profiles (
    profile_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    ocr_strategy TEXT NOT NULL,
    validation_level TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_from_advice_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT,
    file_type TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    policy_id TEXT,
    mode TEXT,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL,
    artifact_root TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id),
    FOREIGN KEY (schema_id) REFERENCES extraction_schemas_index(schema_id)
);

CREATE TABLE IF NOT EXISTS run_documents (
    run_document_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    schema_id TEXT,
    mode TEXT,
    routing_reason TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (document_id) REFERENCES documents(document_id)
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    document_id TEXT,
    artifact_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT,
    payload_hash TEXT,
    file_path TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (document_id) REFERENCES documents(document_id)
);

CREATE TABLE IF NOT EXISTS document_metrics_index (
    metrics_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    policy_id TEXT,
    evidence_source TEXT,
    is_human_review INTEGER NOT NULL,
    field_precision REAL,
    field_recall REAL,
    field_f1 REAL,
    accuracy REAL,
    missing_rate REAL,
    correction_rate REAL,
    metrics_artifact_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (document_id) REFERENCES documents(document_id),
    FOREIGN KEY (schema_id) REFERENCES extraction_schemas_index(schema_id)
);

CREATE TABLE IF NOT EXISTS field_results (
    field_result_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    policy_id TEXT,
    field_name TEXT NOT NULL,
    expected_value TEXT,
    extracted_value TEXT,
    is_correct INTEGER,
    is_missing INTEGER,
    is_grounded INTEGER,
    confidence REAL,
    extraction_method TEXT,
    evidence_source TEXT,
    is_human_review INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (document_id) REFERENCES documents(document_id),
    FOREIGN KEY (schema_id) REFERENCES extraction_schemas_index(schema_id)
);

CREATE TABLE IF NOT EXISTS run_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    document_id TEXT,
    event_type TEXT NOT NULL,
    message TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (document_id) REFERENCES documents(document_id)
);

CREATE TABLE IF NOT EXISTS review_records (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    schema_id TEXT,
    review_status TEXT NOT NULL,
    reviewer_id TEXT,
    review_note TEXT,
    source TEXT NOT NULL DEFAULT 'human_review',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id),
    FOREIGN KEY (document_id) REFERENCES documents(document_id)
);

CREATE TABLE IF NOT EXISTS review_field_corrections (
    correction_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    extracted_value_snapshot TEXT,
    corrected_value TEXT,
    decision TEXT NOT NULL,
    evidence_text_snapshot TEXT,
    validation_status_snapshot TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES review_records(review_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_extraction_schemas_project_id ON extraction_schemas(project_id);
CREATE INDEX IF NOT EXISTS idx_extraction_schemas_updated_at ON extraction_schemas(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_profile_id ON jobs(profile_id);
CREATE INDEX IF NOT EXISTS idx_extraction_profiles_project_id ON extraction_profiles(project_id);
CREATE INDEX IF NOT EXISTS idx_extraction_profiles_project_default ON extraction_profiles(project_id, is_default);
CREATE INDEX IF NOT EXISTS idx_documents_job_id ON documents(job_id);
CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_project_id ON runs(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_job_id ON runs(job_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_run_documents_run_id ON run_documents(run_id);
CREATE INDEX IF NOT EXISTS idx_run_documents_run_doc ON run_documents(run_id, document_id);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_run_id ON run_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_document_id ON run_artifacts(document_id);
CREATE INDEX IF NOT EXISTS idx_metrics_project_id ON document_metrics_index(project_id);
CREATE INDEX IF NOT EXISTS idx_metrics_run_id ON document_metrics_index(run_id);
CREATE INDEX IF NOT EXISTS idx_field_results_document_id ON field_results(document_id);
CREATE INDEX IF NOT EXISTS idx_field_results_run_id ON field_results(run_id);
CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events(run_id);
CREATE INDEX IF NOT EXISTS idx_review_records_run_doc_created ON review_records(run_id, document_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_field_corrections_review_id ON review_field_corrections(review_id);
