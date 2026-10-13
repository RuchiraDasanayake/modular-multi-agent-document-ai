"""Offline checks for the first product metadata migration.

PostgreSQL integration still needs a live database before writers can cut over.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "scripts" / "product_migrations" / "alembic.ini"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("POSTGRES_")}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(CONFIG), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_upgrade_renders_scoped_postgres_constraints() -> None:
    result = _alembic("upgrade", "head", "--sql")
    assert result.returncode == 0, result.stderr
    sql = result.stdout
    for table in ("jobs", "documents", "runs", "run_documents", "review_events", "recipe_events"):
        assert f"CREATE TABLE product.{table}" in sql
        assert f"product.{table}" in sql
    assert "CREATE TABLE product.alembic_version_product" in sql
    assert "REFERENCES public.users (id) ON DELETE RESTRICT" in sql
    assert "FOREIGN KEY(owner_user_id, job_id) REFERENCES product.jobs" in sql
    assert "FOREIGN KEY(owner_user_id, job_id, run_id, doc_id) REFERENCES product.run_documents" in sql
    assert "FOREIGN KEY(owner_user_id, source_job_id, source_run_id, source_doc_id" in sql
    assert "REFERENCES product.review_events (owner_user_id, job_id, run_id, doc_id, revision, audit_event_id)" in sql
    assert "previous_revision BIGINT GENERATED ALWAYS AS" in sql
    assert "CONSTRAINT uq_product_run_idempotency UNIQUE (owner_user_id, job_id, idempotency_key)" in sql
    assert "idempotency_key TEXT NOT NULL" in sql
    assert "request_sha256 TEXT NOT NULL" in sql
    assert "CONSTRAINT ck_product_run_timestamps CHECK (ended_at IS NULL OR ended_at >= created_at)" in sql
    assert "CONSTRAINT ck_product_job_name CHECK (length(name) >= 1)" in sql
    assert "CONSTRAINT ck_product_recipe_name CHECK (length(family_name) BETWEEN 1 AND 100)" in sql
    assert "CREATE TRIGGER review_events_immutable BEFORE UPDATE OR DELETE" in sql
    assert "CREATE TRIGGER recipe_events_immutable BEFORE UPDATE OR DELETE" in sql
    assert "CREATE TRIGGER review_events_no_truncate BEFORE TRUNCATE" in sql
    assert "CREATE TRIGGER recipe_events_no_truncate BEFORE TRUNCATE" in sql
    assert "DROP TABLE" not in sql


def test_online_upgrade_refuses_implicit_database_defaults() -> None:
    result = _alembic("upgrade", "head")
    assert result.returncode != 0
    assert "POSTGRES_URI or all POSTGRES_HOST/USER/PASSWORD/DB values are required" in result.stderr
