"""MTM → LTM Promotion Job.

Promotes successful strategies from Medium-Term Memory to Long-Term Memory
based on observed F1 performance metrics via Thompson Sampling updates.
"""

import asyncio
import hashlib
import logging
import sys
import os
import json
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg_pool import AsyncConnectionPool
from ahmn_core.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

POSTGRES_URI = os.getenv(
    "POSTGRES_URI", "postgresql://user:password@localhost:5432/ahmn_db"
)

async def promote_strategies():
    """Promote successful strategies from MTM to LTM based on performance metrics."""
    logger.info("Starting promotion job")

    pool = AsyncConnectionPool(conninfo=POSTGRES_URI, open=False, min_size=1, max_size=5)
    await pool.open()
    embedding_service = EmbeddingService()

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Only consider outcomes from the last 24 hours to avoid re-promoting
                query = """
                    SELECT 
                        document_context,
                        policy_id_used,
                        COUNT(*) as usage_count,
                        AVG((outcome_metrics->>'f1_score')::float) as avg_f1
                    FROM mtm_outcomes
                    WHERE (outcome_metrics->>'f1_score')::float > 0.50
                      AND policy_id_used != 'default_policy'
                      AND created_at > NOW() - interval '24 hours'
                    GROUP BY document_context, policy_id_used
                    HAVING COUNT(*) >= 2
                """

                await cur.execute(query)
                rows = await cur.fetchall()

                logger.info(\"Found %d candidate strategies for promotion\", len(rows))

                for row in rows:
                    doc_context_json, policy_id, count, avg_f1 = row

                    if isinstance(doc_context_json, str):
                        context_dict = json.loads(doc_context_json)
                    else:
                        context_dict = doc_context_json

                    doc_type = context_dict.get("doc_type", "unknown")
                    vendor = context_dict.get("vendor")
                    content_profile = context_dict.get("content_profile")

                    context_str = embedding_service.create_context_string(doc_type, vendor)
                    if content_profile:
                        context_str += f". Content profile: {content_profile}"
                    vector = embedding_service.generate_embedding(context_str)

                    context_hash = hashlib.sha256(
                        f"{context_str}:{policy_id}".encode('utf-8')
                    ).hexdigest()

                    # Scale alpha/beta by observed performance
                    alpha_init = 1.0 + avg_f1 * count
                    beta_init = 1.0 + (1.0 - avg_f1) * count

                    upsert_query = """
                        INSERT INTO ltm_validated_policies 
                        (context_hash, context_embedding, policy_id, policy_data,
                         validation_metrics, alpha, beta, confidence_score, last_promoted_at)
                        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, NOW())
                        ON CONFLICT (context_hash) 
                        DO UPDATE SET
                            validation_metrics = EXCLUDED.validation_metrics,
                            alpha = ltm_validated_policies.alpha + EXCLUDED.alpha - 1.0,
                            beta = ltm_validated_policies.beta + EXCLUDED.beta - 1.0,
                            confidence_score = LEAST(1.0, ltm_validated_policies.confidence_score + 0.1),
                            last_promoted_at = NOW();
                    """

                    policy_data = {
                        "origin": "promoted_from_mtm",
                        "avg_f1": avg_f1,
                        "doc_type": doc_type,
                        "vendor": vendor,
                        "content_profile": content_profile,
                    }
                    validation_metrics = {
                        "f1_score": avg_f1,
                        "sample_size": count,
                        "document_context": {
                            "doc_type": doc_type,
                            "vendor": vendor,
                            "content_profile": content_profile,
                        },
                    }
                    confidence = min(1.0, 0.5 + avg_f1 * 0.3 + min(count / 10.0, 0.2))

                    await cur.execute(upsert_query, (
                        context_hash,
                        vector,
                        policy_id,
                        json.dumps(policy_data),
                        json.dumps(validation_metrics),
                        alpha_init,
                        beta_init,
                        confidence,
                    ))

                await conn.commit()
                logger.info("Promotion job completed")
    finally:
        await pool.close()

if __name__ == "__main__":
    # Fix for Windows: psycopg async requires SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(promote_strategies())
