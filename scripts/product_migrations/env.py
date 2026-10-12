"""Forward-only product metadata migrations on the existing PostgreSQL database."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


def run_migrations_offline() -> None:
    """Render reviewable PostgreSQL SQL without opening a database connection."""
    context.configure(
        dialect_name="postgresql",
        version_table="alembic_version_product",
        version_table_schema="product",
        transactional_ddl=True,
    )
    with context.begin_transaction():
        context.execute("CREATE SCHEMA IF NOT EXISTS product")
        context.run_migrations()


def run_migrations_online() -> None:
    """Serialize upgrades and commit the schema and version row together."""
    uri = os.environ.get("POSTGRES_URI")
    if uri:
        url = make_url(uri)
        if url.get_backend_name() != "postgresql":
            raise RuntimeError("Product migrations require PostgreSQL")
        url = url.set(drivername="postgresql+psycopg")
    else:
        required = ("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
        if any(not os.environ.get(name) for name in required):
            raise RuntimeError("POSTGRES_URI or all POSTGRES_HOST/USER/PASSWORD/DB values are required")
        url = URL.create(
            "postgresql+psycopg",
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.environ["POSTGRES_HOST"],
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            database=os.environ["POSTGRES_DB"],
        )
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            # One migration process owns the whole upgrade, including Alembic's
            # version check. DDL and its version row roll back together.
            connection.execute(text("SELECT pg_advisory_xact_lock(721681037741916554)"))
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS product"))
            context.configure(
                connection=connection,
                version_table="alembic_version_product",
                version_table_schema="product",
                transactional_ddl=True,
                transaction_per_migration=False,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
