import json
import uuid
from typing import Optional, Tuple
from psycopg import AsyncConnection
from redis.asyncio import Redis
from ..schemas import DocumentContext, PolicyResponse, OutcomeMetrics
from .embedding import EmbeddingService

class MemoryService:
    def __init__(self, db: AsyncConnection, redis: Redis):
        self.db = db
        self.redis = redis
        self.embedding_service = EmbeddingService()

    async def get_advice(self, context: DocumentContext) -> PolicyResponse:
        # 1. Create context string and embedding
        context_str = self.embedding_service.create_context_string(
            context.doc_type, context.vendor
        )
        vector = self.embedding_service.generate_embedding(context_str)
        
        # 2. Search LTM (Postgres)
        # Using <=> operator for cosine distance (requires pgvector)
        # We select the closest match if distance is small enough (e.g., < 0.2)
        query = """
            SELECT policy_id, policy_data
            FROM ltm_validated_policies
            ORDER BY context_embedding <=> %s::vector
            LIMIT 1;
        """
        
        # Note: In a real app, we'd want a threshold check here.
        # For now, we'll just take the top result if it exists.
        # To implement threshold: SELECT ... WHERE (embedding <=> %s) < 0.2 ...
        
        policy_id = "default_policy"
        policy_data = {"action": "standard_processing"}
        source = "DEFAULT"

        async with self.db.cursor() as cur:
            await cur.execute(query, (vector,))
            row = await cur.fetchone()
            if row:
                policy_id, policy_data = row
                source = "LTM"

        # 3. Generate Advice ID
        advice_id = uuid.uuid4()

        # 4. Cache in Redis (STM) for 30 mins
        # We store the original context so we can log it later
        redis_key = f"advice:{advice_id}"
        await self.redis.setex(
            redis_key,
            1800, # 30 minutes
            context.model_dump_json()
        )

        return PolicyResponse(
            advice_id=advice_id,
            policy_id=policy_id,
            policy_data=policy_data,
            retrieval_source=source
        )

    async def log_outcome(self, advice_id: uuid.UUID, policy_id_used: str, metrics: OutcomeMetrics):
        # 1. Fetch original context from Redis
        redis_key = f"advice:{advice_id}"
        context_json = await self.redis.get(redis_key)
        
        if not context_json:
            # Handle case where STM expired or missing
            # In production, might want to log an error or handle gracefully
            # For now, we'll assume context is lost but still log what we can or skip
            # Let's skip to avoid inserting bad data
            print(f"Warning: Context for advice_id {advice_id} not found in STM.")
            return

        # 2. Insert into MTM (Postgres)
        query = """
            INSERT INTO mtm_outcomes 
            (advice_id, policy_id_used, document_context, outcome_metrics)
            VALUES (%s, %s, %s::jsonb, %s::jsonb)
        """
        
        async with self.db.cursor() as cur:
            await cur.execute(
                query,
                (
                    advice_id,
                    policy_id_used,
                    context_json, # It's already a JSON string from Redis
                    metrics.model_dump_json()
                )
            )
            await self.db.commit()

    async def log_feedback(self, advice_id: uuid.UUID, human_corrected: bool):
        query = """
            UPDATE mtm_outcomes
            SET human_corrected = %s
            WHERE advice_id = %s
        """
        async with self.db.cursor() as cur:
            await cur.execute(query, (human_corrected, advice_id))
            await self.db.commit()
