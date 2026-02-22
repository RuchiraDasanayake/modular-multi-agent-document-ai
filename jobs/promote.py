import asyncio
import sys
import os
import json
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg_pool import AsyncConnectionPool
from ahmn_core.services.embedding import EmbeddingService

POSTGRES_URI = os.getenv(
    "POSTGRES_URI", "postgresql://user:password@localhost:5432/ahmn_db"
)


async def promote_strategies():
    """Promote successful strategies from MTM to LTM based on performance metrics."""
    print("Starting promotion job...")

    pool = AsyncConnectionPool(conninfo=POSTGRES_URI, open=False, min_size=1, max_size=5)
    await pool.open()
    embedding_service = EmbeddingService()

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            query = """
                SELECT 
                    document_context,
                    policy_id_used,
                    COUNT(*) as usage_count,
                    AVG((outcome_metrics->>'f1_score')::float) as avg_f1
                FROM mtm_outcomes
                WHERE (outcome_metrics->>'f1_score')::float > 0.95
                GROUP BY document_context, policy_id_used
                HAVING COUNT(*) > 5
            """
            
            await cur.execute(query)
            rows = await cur.fetchall()
            
            print(f"Found {len(rows)} candidate strategies for promotion.")

            for row in rows:
                doc_context_json, policy_id, count, avg_f1 = row
                
                if isinstance(doc_context_json, str):
                    context_dict = json.loads(doc_context_json)
                else:
                    context_dict = doc_context_json

                doc_type = context_dict.get("doc_type", "unknown")
                vendor = context_dict.get("vendor")
                
                context_str = embedding_service.create_context_string(doc_type, vendor)
                vector = embedding_service.generate_embedding(context_str)
                
                import hashlib
                context_hash = hashlib.sha256(context_str.encode('utf-8')).hexdigest()

                upsert_query = """
                    INSERT INTO ltm_validated_policies 
                    (context_hash, context_embedding, policy_id, policy_data, validation_metrics, last_promoted_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, NOW())
                    ON CONFLICT (context_hash) 
                    DO UPDATE SET
                        validation_metrics = EXCLUDED.validation_metrics,
                        confidence_score = 1.0,
                        last_promoted_at = NOW();
                """
                
                policy_data = {"origin": "promoted_from_mtm", "avg_f1": avg_f1}
                validation_metrics = {"f1_score": avg_f1, "sample_size": count}

                await cur.execute(upsert_query, (
                    context_hash,
                    vector,
                    policy_id,
                    json.dumps(policy_data),
                    json.dumps(validation_metrics)
                ))
            
            await conn.commit()
            print("Promotion job completed successfully.")

    await pool.close()

if __name__ == "__main__":
    # Fix for Windows: psycopg async requires SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(promote_strategies())
