import asyncio
import sys
import os
import json
from collections import defaultdict

# Add parent directory to path to allow imports from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import DatabasePool
from app.services.embedding import EmbeddingService

async def promote_strategies():
    print("Starting promotion job...")
    
    pool = await DatabasePool.get_pool()
    embedding_service = EmbeddingService()

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            # 1. Fetch successful outcomes from MTM
            # We are looking for patterns: same context -> same policy -> good result
            # This is a simplified aggregation. In production, you might use more complex SQL.
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
                
                # Parse context to generate embedding
                # doc_context_json is a dict (because psycopg converts JSONB to dict automatically)
                # or a string depending on driver config. Let's assume dict or parse it.
                if isinstance(doc_context_json, str):
                    context_dict = json.loads(doc_context_json)
                else:
                    context_dict = doc_context_json

                doc_type = context_dict.get("doc_type", "unknown")
                vendor = context_dict.get("vendor")
                
                # Generate embedding for the context
                context_str = embedding_service.create_context_string(doc_type, vendor)
                vector = embedding_service.generate_embedding(context_str)
                
                # Create a unique hash for the context to prevent duplicates
                # Use hashlib for stable hashing across runs
                import hashlib
                context_hash = hashlib.sha256(context_str.encode('utf-8')).hexdigest()

                # Upsert into LTM
                # We update the metrics if it already exists
                upsert_query = """
                    INSERT INTO ltm_validated_policies 
                    (context_hash, context_embedding, policy_id, policy_data, validation_metrics, last_promoted_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, NOW())
                    ON CONFLICT (context_hash) 
                    DO UPDATE SET
                        validation_metrics = EXCLUDED.validation_metrics,
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

    await DatabasePool.close_pool()

if __name__ == "__main__":
    asyncio.run(promote_strategies())
