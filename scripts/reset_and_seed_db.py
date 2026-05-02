#!/usr/bin/env python3
"""
AHMN Database Reset & Seed Script
================================

Clears AHMN memory tables and optionally reseeds them with the canonical
research seed set. This is the practical control point for seeded vs
unseeded AHMN evaluations.

Usage:
    # Seeded reset
    POSTGRES_URI="postgresql://user:password@localhost:5432/ahmn_db" python scripts/reset_and_seed_db.py

    # Unseeded reset
    POSTGRES_URI="postgresql://user:password@localhost:5432/ahmn_db" python scripts/reset_and_seed_db.py --no-seed
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from psycopg_pool import AsyncConnectionPool

# Allow running from repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ahmn_core.seeds import LTM_SEEDS

POSTGRES_URI = os.getenv(
    "POSTGRES_URI", "postgresql://user:password@localhost:5432/ahmn_db"
)

_embedding_service = None


def _get_embedding_service():
    global _embedding_service
    if _embedding_service is None:
        from ahmn_core.services.embedding import EmbeddingService

        _embedding_service = EmbeddingService()
    return _embedding_service


def _create_context_string(
    doc_type: str,
    vendor: str | None = None,
    content_profile: str | None = None,
    extra_context: dict | None = None,
) -> str:
    svc = _get_embedding_service()
    return svc.create_context_string(doc_type, vendor, content_profile, extra_context)


def _embed(text: str) -> list[float]:
    return _get_embedding_service().generate_embedding(text)


def _context_hash(ctx_str: str, policy_id: str) -> str:
    return hashlib.sha256(f"{ctx_str}:{policy_id}".encode()).hexdigest()


MTM_SEEDS = [
    {
        "policy_id_used": "table_heavy",
        "document_context": {
            "doc_type": "invoice",
            "vendor": None,
            "content_profile": "table-heavy",
        },
        "outcome_metrics": {
            "f1_score": 0.87,
            "cost": 0.01,
            "processing_time_ms": 1250.0,
            "success": True,
        },
    },
    {
        "policy_id_used": "forms",
        "document_context": {
            "doc_type": "form_document",
            "vendor": None,
            "content_profile": "form-centric",
        },
        "outcome_metrics": {
            "f1_score": 0.82,
            "cost": 0.01,
            "processing_time_ms": 980.0,
            "success": True,
        },
    },
    {
        "policy_id_used": "table_heavy",
        "document_context": {
            "doc_type": "financial_statement",
            "vendor": None,
            "content_profile": "table-heavy",
        },
        "outcome_metrics": {
            "f1_score": 0.78,
            "cost": 0.01,
            "processing_time_ms": 1500.0,
            "success": True,
        },
    },
    {
        "policy_id_used": "mixed_content",
        "document_context": {
            "doc_type": "contract",
            "vendor": None,
            "content_profile": "mixed",
        },
        "outcome_metrics": {
            "f1_score": 0.75,
            "cost": 0.01,
            "processing_time_ms": 1800.0,
            "success": True,
        },
    },
    {
        "policy_id_used": "forms",
        "document_context": {
            "doc_type": "medical_record",
            "vendor": None,
            "content_profile": "form-centric",
        },
        "outcome_metrics": {
            "f1_score": 0.80,
            "cost": 0.01,
            "processing_time_ms": 1100.0,
            "success": True,
        },
    },
    {
        "policy_id_used": "table_heavy",
        "document_context": {
            "doc_type": "invoice",
            "vendor": None,
            "content_profile": "image-heavy",
        },
        "outcome_metrics": {
            "f1_score": 0.72,
            "cost": 0.02,
            "processing_time_ms": 3200.0,
            "success": True,
        },
    },
    {
        "policy_id_used": "table_heavy",
        "document_context": {
            "doc_type": "table_document",
            "vendor": None,
            "content_profile": "table-heavy",
        },
        "outcome_metrics": {
            "f1_score": 0.68,
            "cost": 0.02,
            "processing_time_ms": 2800.0,
            "success": True,
        },
    },
    {
        "policy_id_used": "forms",
        "document_context": {
            "doc_type": "form_document",
            "vendor": None,
            "content_profile": "form-centric",
        },
        "outcome_metrics": {
            "f1_score": 0.65,
            "cost": 0.02,
            "processing_time_ms": 3500.0,
            "success": True,
        },
    },
]


async def main(seed_enabled: bool) -> None:
    print("=" * 70)
    print("AHMN Database Reset & Seed")
    print("=" * 70)
    print(f"Target: {POSTGRES_URI.split('@')[-1] if '@' in POSTGRES_URI else POSTGRES_URI}")
    print(f"Mode: {'seeded reset' if seed_enabled else 'clear only (unseeded)'}")
    print()

    pool = AsyncConnectionPool(conninfo=POSTGRES_URI, open=False, min_size=1, max_size=5)
    await pool.open()

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                print("[1/4] Clearing AHMN memory tables...")
                await cur.execute("DELETE FROM mtm_outcomes")
                await cur.execute("DELETE FROM ltm_validated_policies")
                await cur.execute("DELETE FROM experiment_runs")
                await cur.execute("DELETE FROM system_events")
                await conn.commit()
                print("      Cleared: mtm_outcomes, ltm_validated_policies, experiment_runs, system_events")

                if seed_enabled:
                    print(f"\n[2/4] Seeding LTM with {len(LTM_SEEDS)} policy entries...")
                    for seed in LTM_SEEDS:
                        ctx_str = _create_context_string(
                            seed["doc_type"],
                            seed.get("vendor"),
                            seed.get("content_profile"),
                            seed.get("extra_context"),
                        )
                        vector = _embed(ctx_str)
                        ctx_hash = _context_hash(ctx_str, seed["policy_id"])

                        await cur.execute(
                            """INSERT INTO ltm_validated_policies
                               (context_hash, context_embedding, policy_id, policy_data,
                                validation_metrics, alpha, beta, confidence_score, last_promoted_at)
                               VALUES (%s, %s::vector, %s, %s::jsonb, %s::jsonb, %s, %s, %s, NOW())
                               ON CONFLICT (context_hash) DO NOTHING""",
                            (
                                ctx_hash,
                                vector,
                                seed["policy_id"],
                                json.dumps(seed["policy_data"]),
                                json.dumps({"origin": "seed", "f1_score": 0.0}),
                                seed["alpha"],
                                seed["beta"],
                                seed["confidence"],
                            ),
                        )
                        print(
                            f"      LTM: {seed['doc_type']:25s} -> {seed['policy_id']:20s} "
                            f"(alpha={seed['alpha']:.0f}, beta={seed['beta']:.0f})"
                        )
                    await conn.commit()

                    print(f"\n[3/4] Seeding MTM with {len(MTM_SEEDS)} outcome records...")
                    base_time = datetime.now(timezone.utc) - timedelta(hours=2)
                    for i, seed in enumerate(MTM_SEEDS):
                        advice_id = uuid.uuid4()
                        created_at = base_time + timedelta(minutes=i * 15)
                        await cur.execute(
                            """INSERT INTO mtm_outcomes
                               (advice_id, policy_id_used, document_context, outcome_metrics, created_at)
                               VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)""",
                            (
                                advice_id,
                                seed["policy_id_used"],
                                json.dumps(seed["document_context"]),
                                json.dumps(seed["outcome_metrics"]),
                                created_at,
                            ),
                        )
                        f1 = float(seed["outcome_metrics"]["f1_score"])
                        print(
                            f"      MTM: {seed['document_context']['doc_type']:25s} -> "
                            f"{seed['policy_id_used']:20s} (F1={f1:.2f})"
                        )
                    await conn.commit()
                else:
                    print("\n[2/4] Skipping LTM seeding (--no-seed)")
                    print("[3/4] Skipping MTM seeding (--no-seed)")

                print("\n[4/4] Verifying database state...")
                await cur.execute("SELECT COUNT(*) FROM ltm_validated_policies")
                ltm_count = int((await cur.fetchone())[0])  # type: ignore[index]
                await cur.execute("SELECT COUNT(*) FROM mtm_outcomes")
                mtm_count = int((await cur.fetchone())[0])  # type: ignore[index]
                await cur.execute("SELECT COUNT(*) FROM users")
                user_count = int((await cur.fetchone())[0])  # type: ignore[index]

                await cur.execute(
                    """SELECT policy_id, COUNT(*), AVG(alpha/(alpha+beta)) AS avg_mean
                       FROM ltm_validated_policies
                       GROUP BY policy_id ORDER BY COUNT(*) DESC"""
                )
                ltm_rows = await cur.fetchall()

                print(f"\n      LTM Policies: {ltm_count}")
                for policy_id, count, avg_mean in ltm_rows:
                    print(f"        {policy_id:20s}: {count} entries, avg mean={avg_mean:.3f}")
                print(f"      MTM Outcomes:  {mtm_count}")
                print(f"      Users:         {user_count}")
    finally:
        await pool.close()

    print("\n" + "=" * 70)
    print("Database reset completed successfully.")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reset AHMN memory tables and optionally reseed them."
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Clear AHMN memory tables without reseeding LTM or MTM.",
    )
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(seed_enabled=not args.no_seed))
