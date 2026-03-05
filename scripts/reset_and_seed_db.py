#!/usr/bin/env python3
"""
AHMN Database Reset & Seed Script
===================================
Clears all AHMN memory tables (MTM, LTM, experiments) and reseeds with
properly matched data that aligns with:
  - The policy_store.json policies (forms, scanned_text, table_heavy, mixed_content, default)
  - The sample documents in inputs/inbox/
  - The Guardrails DocumentType enum values

Usage:
    # Against Docker database
    POSTGRES_URI="postgresql://user:password@localhost:5432/ahmn_db" python scripts/reset_and_seed_db.py

    # Or from docker exec
    docker compose exec ahmn python /app/scripts/reset_and_seed_db.py
"""

import asyncio
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg_pool import AsyncConnectionPool

POSTGRES_URI = os.getenv(
    "POSTGRES_URI", "postgresql://user:password@localhost:5432/ahmn_db"
)

# ─── Embedding helper ─────────────────────────────────────────────────────
# Lazy-load to avoid pulling in torch until needed
_embedding_service = None

def _get_embedding_service():
    global _embedding_service
    if _embedding_service is None:
        from ahmn_core.services.embedding import EmbeddingService
        _embedding_service = EmbeddingService()
    return _embedding_service

def _create_context_string(doc_type: str, vendor: str | None = None, content_profile: str | None = None) -> str:
    """Build the same context string the AHMN service uses for embedding."""
    svc = _get_embedding_service()
    ctx = svc.create_context_string(doc_type, vendor)
    if content_profile:
        ctx += f". Content profile: {content_profile}"
    return ctx

def _embed(text: str) -> list[float]:
    return _get_embedding_service().generate_embedding(text)

def _context_hash(ctx_str: str, policy_id: str) -> str:
    return hashlib.sha256(f"{ctx_str}:{policy_id}".encode()).hexdigest()

# ═══════════════════════════════════════════════════════════════════════════
# SEED DATA — properly matched to policy_store.json and sample documents
# ═══════════════════════════════════════════════════════════════════════════

LTM_SEEDS = [
    # ── Invoice documents → table_heavy policy ──
    {
        "doc_type": "invoice",
        "content_profile": "table-heavy",
        "vendor": None,
        "policy_id": "table_heavy",
        "policy_data": {"action": "invoice_processing", "origin": "seed"},
        "alpha": 9.0,
        "beta": 2.0,
        "confidence": 0.82,
    },
    # ── Table documents → table_heavy policy ──
    {
        "doc_type": "table_document",
        "content_profile": "table-heavy",
        "vendor": None,
        "policy_id": "table_heavy",
        "policy_data": {"action": "table_extraction", "origin": "seed"},
        "alpha": 8.0,
        "beta": 3.0,
        "confidence": 0.73,
    },
    # ── Receipt → table_heavy ──
    {
        "doc_type": "receipt",
        "content_profile": "table-heavy",
        "vendor": None,
        "policy_id": "table_heavy",
        "policy_data": {"action": "receipt_processing", "origin": "seed"},
        "alpha": 7.0,
        "beta": 3.0,
        "confidence": 0.70,
    },
    # ── Form documents → forms policy ──
    {
        "doc_type": "form_document",
        "content_profile": "form-centric",
        "vendor": None,
        "policy_id": "forms",
        "policy_data": {"action": "form_extraction", "origin": "seed"},
        "alpha": 7.0,
        "beta": 3.0,
        "confidence": 0.70,
    },
    # ── Scanned documents → scanned_text policy ──
    {
        "doc_type": "scanned_document",
        "content_profile": "scanned",
        "vendor": None,
        "policy_id": "scanned_text",
        "policy_data": {"action": "ocr_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 4.0,
        "confidence": 0.60,
    },
    # ── Mixed content → mixed_content policy ──
    {
        "doc_type": "mixed_document",
        "content_profile": "mixed",
        "vendor": None,
        "policy_id": "mixed_content",
        "policy_data": {"action": "mixed_processing", "origin": "seed"},
        "alpha": 5.0,
        "beta": 3.0,
        "confidence": 0.63,
    },
    # ── Contract → mixed_content (contracts are multi-section) ──
    {
        "doc_type": "contract",
        "content_profile": "mixed",
        "vendor": None,
        "policy_id": "mixed_content",
        "policy_data": {"action": "contract_processing", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    # ── Financial report → table_heavy (numbers + tables) ──
    {
        "doc_type": "financial_statement",
        "content_profile": "table-heavy",
        "vendor": None,
        "policy_id": "table_heavy",
        "policy_data": {"action": "financial_extraction", "origin": "seed"},
        "alpha": 7.0,
        "beta": 4.0,
        "confidence": 0.64,
    },
    # ── Text document → scanned_text ──
    {
        "doc_type": "text_document",
        "content_profile": "text-heavy",
        "vendor": None,
        "policy_id": "scanned_text",
        "policy_data": {"action": "text_extraction", "origin": "seed"},
        "alpha": 5.0,
        "beta": 4.0,
        "confidence": 0.56,
    },
    # ── Unknown → default policy with flat prior ──
    {
        "doc_type": "unknown",
        "content_profile": "unknown",
        "vendor": None,
        "policy_id": "default",
        "policy_data": {"action": "default_processing", "origin": "seed"},
        "alpha": 4.0,
        "beta": 4.0,
        "confidence": 0.50,
    },
    # ── Clinical summary → forms (structured extraction) ──  
    {
        "doc_type": "clinical_summary",
        "content_profile": "form-centric",
        "vendor": None,
        "policy_id": "forms",
        "policy_data": {"action": "clinical_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    # ── Medical record → forms ──
    {
        "doc_type": "medical_record",
        "content_profile": "form-centric",
        "vendor": None,
        "policy_id": "forms",
        "policy_data": {"action": "medical_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 4.0,
        "confidence": 0.60,
    },
]

# ── MTM seed outcomes matching the sample documents ──
MTM_SEEDS = [
    # invoice_sample_001.txt
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
    # employee_form_002.txt
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
    # financial_report_003.txt
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
    # service_contract_004.txt
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
    # medical_record_005.txt
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
    # invoice_image_006.png (scanned)
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
    # table_report_007.png (scanned table)
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
    # medical_form_008.png (scanned form)
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

async def main():
    print("=" * 70)
    print("AHMN Database Reset & Seed")
    print("=" * 70)
    print(f"Target: {POSTGRES_URI.split('@')[-1] if '@' in POSTGRES_URI else POSTGRES_URI}")
    print()

    pool = AsyncConnectionPool(conninfo=POSTGRES_URI, open=False, min_size=1, max_size=5)
    await pool.open()

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # ── Step 1: Clear all AHMN tables ──
                print("[1/4] Clearing AHMN memory tables...")
                await cur.execute("DELETE FROM mtm_outcomes")
                await cur.execute("DELETE FROM ltm_validated_policies")
                await cur.execute("DELETE FROM experiment_runs")
                # Clear system events too
                await cur.execute("DELETE FROM system_events")
                await conn.commit()
                print("      ✓ Cleared: mtm_outcomes, ltm_validated_policies, experiment_runs, system_events")

                # ── Step 2: Seed LTM with properly matched policies ──
                print(f"\n[2/4] Seeding LTM with {len(LTM_SEEDS)} policy entries...")
                for seed in LTM_SEEDS:
                    ctx_str = _create_context_string(
                        seed["doc_type"],
                        seed.get("vendor"),
                        seed.get("content_profile"),
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
                    print(f"      ✓ LTM: {seed['doc_type']:25s} → {seed['policy_id']:15s} (α={seed['alpha']:.0f}, β={seed['beta']:.0f})")
                await conn.commit()

                # ── Step 3: Seed MTM with realistic outcome data ──
                print(f"\n[3/4] Seeding MTM with {len(MTM_SEEDS)} outcome records...")
                base_time = datetime.now(timezone.utc) - timedelta(hours=2)
                for i, seed in enumerate(MTM_SEEDS):
                    advice_id = uuid.uuid4()
                    # Stagger creation times for realistic ordering
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
                    f1 = seed["outcome_metrics"]["f1_score"]
                    print(f"      ✓ MTM: {seed['document_context']['doc_type']:25s} → {seed['policy_id_used']:15s} (F1={f1:.2f})")
                await conn.commit()

                # ── Step 4: Verify ──
                print("\n[4/4] Verifying seeded data...")
                await cur.execute("SELECT COUNT(*) FROM ltm_validated_policies")
                ltm_count = (await cur.fetchone())[0] # type: ignore
                await cur.execute("SELECT COUNT(*) FROM mtm_outcomes")
                mtm_count = (await cur.fetchone())[0] # type: ignore
                await cur.execute("SELECT COUNT(*) FROM users")
                user_count = (await cur.fetchone())[0] # type: ignore

                # Show LTM policy distribution
                await cur.execute(
                    """SELECT policy_id, COUNT(*), AVG(alpha/(alpha+beta)) AS avg_mean
                       FROM ltm_validated_policies
                       GROUP BY policy_id ORDER BY COUNT(*) DESC"""
                )
                ltm_rows = await cur.fetchall()

                print(f"\n      LTM Policies: {ltm_count}")
                for r in ltm_rows:
                    print(f"        {r[0]:20s}: {r[1]} entries, avg mean={r[2]:.3f}")
                print(f"      MTM Outcomes:  {mtm_count}")
                print(f"      Users:         {user_count}")

    finally:
        await pool.close()

    print("\n" + "=" * 70)
    print("Database reset and seed completed successfully.")
    print("=" * 70)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
