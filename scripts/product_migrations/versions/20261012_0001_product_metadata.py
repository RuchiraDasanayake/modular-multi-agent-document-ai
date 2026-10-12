"""Owner-scoped product metadata and append-only review/recipe events.

Revision ID: 20261012_0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261012_0001"
down_revision = None
branch_labels = None
depends_on = None


def _json_object(name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"jsonb_typeof({name}) = 'object'", name=f"ck_{name}_object")


def upgrade() -> None:
    """Create an unused product store; live writers still use files."""
    op.create_table(
        "jobs",
        sa.Column("owner_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("owner_user_id", "job_id", name="pk_product_jobs"),
        sa.UniqueConstraint("job_id", name="uq_product_job_id"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("job_id ~ '^[0-9a-f]{32}$'", name="ck_product_job_id"),
        sa.CheckConstraint("revision >= 1", name="ck_product_job_revision"),
        sa.CheckConstraint("status IN ('draft', 'queued', 'running', 'success', 'failed')", name="ck_product_job_status"),
        sa.CheckConstraint("length(name) >= 1", name="ck_product_job_name"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_product_job_timestamps"),
        _json_object("snapshot"),
        schema="product",
    )
    op.create_index("ix_product_jobs_owner_created", "jobs", ["owner_user_id", "created_at"], schema="product")

    op.create_table(
        "documents",
        sa.Column("owner_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("stored_name", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_sha256", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("owner_user_id", "job_id", "file_id", name="pk_product_documents"),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "job_id"], ["product.jobs.owner_user_id", "product.jobs.job_id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("file_id ~ '^[0-9a-f]{32}$'", name="ck_product_file_id"),
        sa.CheckConstraint("length(file_name) BETWEEN 1 AND 1024", name="ck_product_file_name"),
        sa.CheckConstraint("length(stored_name) BETWEEN 1 AND 1200", name="ck_product_stored_name"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_product_file_size"),
        sa.CheckConstraint("source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'", name="ck_product_source_hash"),
        sa.CheckConstraint("status IN ('loaded', 'processing', 'processed', 'failed')", name="ck_product_document_status"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_product_document_timestamps"),
        _json_object("snapshot"),
        schema="product",
    )
    op.create_index(
        "ix_product_documents_job_created", "documents", ["owner_user_id", "job_id", "created_at"], schema="product"
    )

    op.create_table(
        "runs",
        sa.Column("owner_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("pipeline_version", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_sha256", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("owner_user_id", "job_id", "run_id", name="pk_product_runs"),
        sa.UniqueConstraint("run_id", name="uq_product_run_id"),
        sa.UniqueConstraint("owner_user_id", "job_id", "idempotency_key", name="uq_product_run_idempotency"),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "job_id"], ["product.jobs.owner_user_id", "product.jobs.job_id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("run_id ~ '^auto_[0-9a-f]{32}$'", name="ck_product_run_id"),
        sa.CheckConstraint("status IN ('running', 'success', 'failed')", name="ck_product_run_status"),
        sa.CheckConstraint("length(pipeline_version) BETWEEN 1 AND 100", name="ck_product_pipeline_version"),
        sa.CheckConstraint("idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_product_idempotency_key"),
        sa.CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="ck_product_request_hash"),
        sa.CheckConstraint("(status = 'running') = (ended_at IS NULL)", name="ck_product_run_terminal_time"),
        _json_object("snapshot"),
        schema="product",
    )
    op.create_index("ix_product_runs_job_created", "runs", ["owner_user_id", "job_id", "created_at"], schema="product")

    op.create_table(
        "run_documents",
        sa.Column("owner_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("candidate_sha256", sa.Text(), nullable=True),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("owner_user_id", "job_id", "run_id", "doc_id", name="pk_product_run_documents"),
        sa.UniqueConstraint(
            "owner_user_id", "job_id", "run_id", "doc_id", "source_sha256", name="uq_product_run_doc_source"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "job_id", "run_id"],
            ["product.runs.owner_user_id", "product.runs.job_id", "product.runs.run_id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "job_id", "file_id"],
            ["product.documents.owner_user_id", "product.documents.job_id", "product.documents.file_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("doc_id ~ '^[A-Za-z0-9_-]{1,100}$'", name="ck_product_doc_id"),
        sa.CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name="ck_product_run_source_hash"),
        sa.CheckConstraint(
            "candidate_sha256 IS NULL OR candidate_sha256 ~ '^[0-9a-f]{64}$'", name="ck_product_candidate_hash"
        ),
        sa.CheckConstraint(
            "status IN ('processed', 'needs_review', 'unsupported', 'failed')", name="ck_product_result_status"
        ),
        _json_object("snapshot"),
        schema="product",
    )
    op.create_index(
        "ix_product_run_docs_file", "run_documents", ["owner_user_id", "job_id", "file_id"], schema="product"
    )

    op.create_table(
        "review_events",
        sa.Column("owner_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("audit_event_id", sa.Text(), nullable=False),
        sa.Column("previous_event_id", sa.Text(), nullable=True),
        sa.Column(
            "previous_revision", sa.BigInteger(),
            sa.Computed("CASE WHEN revision > 1 THEN revision - 1 ELSE NULL END", persisted=True),
        ),
        sa.Column("reviewer_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_sha256", sa.Text(), nullable=True),
        sa.Column("reported_active_review_seconds", sa.Integer(), nullable=True),
        sa.Column("event", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint(
            "owner_user_id", "job_id", "run_id", "doc_id", "revision", name="pk_product_review_events"
        ),
        sa.UniqueConstraint("audit_event_id", name="uq_product_review_audit_id"),
        sa.UniqueConstraint(
            "owner_user_id", "job_id", "run_id", "doc_id", "revision", "audit_event_id",
            name="uq_product_review_chain_target",
        ),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "job_id", "run_id", "doc_id"],
            ["product.run_documents.owner_user_id", "product.run_documents.job_id",
             "product.run_documents.run_id", "product.run_documents.doc_id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "job_id", "run_id", "doc_id", "source_sha256"],
            ["product.run_documents.owner_user_id", "product.run_documents.job_id",
             "product.run_documents.run_id", "product.run_documents.doc_id", "product.run_documents.source_sha256"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "job_id", "run_id", "doc_id", "previous_revision", "previous_event_id"],
            ["product.review_events.owner_user_id", "product.review_events.job_id", "product.review_events.run_id",
             "product.review_events.doc_id", "product.review_events.revision", "product.review_events.audit_event_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_product_review_revision"),
        sa.CheckConstraint("audit_event_id ~ '^[0-9a-f]{32}$'", name="ck_product_review_audit_id"),
        sa.CheckConstraint(
            "(revision = 1 AND previous_event_id IS NULL) OR "
            "(revision > 1 AND previous_event_id ~ '^[0-9a-f]{32}$')", name="ck_product_review_chain"
        ),
        sa.CheckConstraint("status IN ('pending', 'completed')", name="ck_product_review_status"),
        sa.CheckConstraint("source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'", name="ck_product_review_hash"),
        sa.CheckConstraint(
            "reported_active_review_seconds IS NULL OR reported_active_review_seconds BETWEEN 1 AND 14400",
            name="ck_product_review_seconds",
        ),
        _json_object("event"),
        schema="product",
    )
    op.create_index(
        "ix_product_reviews_reviewer_created", "review_events", ["reviewer_user_id", "created_at"], schema="product"
    )

    op.create_table(
        "recipe_events",
        sa.Column("owner_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("recipe_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("audit_event_id", sa.Text(), nullable=False),
        sa.Column("previous_event_id", sa.Text(), nullable=True),
        sa.Column(
            "previous_revision", sa.BigInteger(),
            sa.Computed("CASE WHEN revision > 1 THEN revision - 1 ELSE NULL END", persisted=True),
        ),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("family_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_job_id", sa.Text(), nullable=False),
        sa.Column("source_run_id", sa.Text(), nullable=False),
        sa.Column("source_doc_id", sa.Text(), nullable=False),
        sa.Column("source_review_revision", sa.BigInteger(), nullable=False),
        sa.Column("source_review_event_id", sa.Text(), nullable=False),
        sa.Column("source_digest_sha256", sa.Text(), nullable=False),
        sa.Column("event", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("owner_user_id", "recipe_id", "revision", name="pk_product_recipe_events"),
        sa.UniqueConstraint("audit_event_id", name="uq_product_recipe_audit_id"),
        sa.UniqueConstraint(
            "owner_user_id", "recipe_id", "revision", "audit_event_id", name="uq_product_recipe_chain_target"
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "source_job_id", "source_run_id", "source_doc_id", "source_review_revision",
             "source_review_event_id"],
            ["product.review_events.owner_user_id", "product.review_events.job_id", "product.review_events.run_id",
             "product.review_events.doc_id", "product.review_events.revision", "product.review_events.audit_event_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "recipe_id", "previous_revision", "previous_event_id"],
            ["product.recipe_events.owner_user_id", "product.recipe_events.recipe_id",
             "product.recipe_events.revision", "product.recipe_events.audit_event_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("recipe_id ~ '^recipe_[0-9a-f]{32}$'", name="ck_product_recipe_id"),
        sa.CheckConstraint("audit_event_id ~ '^[0-9a-f]{32}$'", name="ck_product_recipe_audit_id"),
        sa.CheckConstraint(
            "(revision = 1 AND previous_event_id IS NULL AND action = 'draft_created' AND state = 'draft') OR "
            "(revision = 2 AND previous_event_id ~ '^[0-9a-f]{32}$' AND action = 'approved_shadow' "
            "AND state = 'approved_shadow') OR "
            "(revision = 3 AND previous_event_id ~ '^[0-9a-f]{32}$' AND action = 'disabled' "
            "AND state = 'disabled')", name="ck_product_recipe_transition"
        ),
        sa.CheckConstraint("length(family_name) BETWEEN 1 AND 100", name="ck_product_recipe_name"),
        sa.CheckConstraint("source_digest_sha256 ~ '^[0-9a-f]{64}$'", name="ck_product_recipe_digest"),
        _json_object("event"),
        schema="product",
    )
    op.create_index(
        "ix_product_recipes_owner_created", "recipe_events", ["owner_user_id", "created_at"], schema="product"
    )

    op.execute(
        """CREATE FUNCTION product.reject_event_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Product audit events are append-only';
            RETURN NULL;
        END;
        $$"""
    )
    op.execute(
        "CREATE TRIGGER review_events_immutable BEFORE UPDATE OR DELETE ON product.review_events "
        "FOR EACH ROW EXECUTE FUNCTION product.reject_event_mutation()"
    )
    op.execute(
        "CREATE TRIGGER recipe_events_immutable BEFORE UPDATE OR DELETE ON product.recipe_events "
        "FOR EACH ROW EXECUTE FUNCTION product.reject_event_mutation()"
    )
    # TRUNCATE does not fire DELETE triggers; protect entire audit trails as well.
    op.execute(
        "CREATE TRIGGER review_events_no_truncate BEFORE TRUNCATE ON product.review_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION product.reject_event_mutation()"
    )
    op.execute(
        "CREATE TRIGGER recipe_events_no_truncate BEFORE TRUNCATE ON product.recipe_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION product.reject_event_mutation()"
    )


def downgrade() -> None:
    """Keep audit data intact; revert the application before restoring a DB backup."""
    raise RuntimeError("Product metadata migrations are forward-only; restore a database backup to remove this schema")
