import json
import uuid
import random
import hashlib
import numpy as np
from typing import Optional, Tuple, List, Dict
from psycopg import AsyncConnection
from redis.asyncio import Redis
from ..schemas import DocumentContext, PolicyResponse, OutcomeMetrics
from .embedding import EmbeddingService
from .rabi import RABIInitializer, NeighborInfo, create_rabi_for_production
from .drift_forgetting import DriftEstimator, DriftType


class MemoryService:
    """
    Memory service with RABI (Retrieval-Augmented Bandit Initialization) 
    and online DAAF (Drift-Aware Adaptive Forgetting).
    
    Supports configurable modes:
    - use_rabi=True: Uses RABI for zero-shot initialization of new contexts
    - use_rabi=False: Standard Thompson Sampling with flat priors
    - use_daaf=True: Online drift-aware forgetting on each outcome
    - use_daaf=False: Standard Bayesian update (no forgetting)
    """
    
    # Class-level drift estimators persist across requests
    _drift_estimators: Dict[str, DriftEstimator] = {}
    
    def __init__(self, db: AsyncConnection, redis: Redis, 
                 use_rabi: bool = True, use_daaf: bool = True):
        self.db = db
        self.redis = redis
        self.embedding_service = EmbeddingService()
        self.use_rabi = use_rabi
        self.use_daaf = use_daaf
        
        # Initialize RABI with production-ready defaults
        if use_rabi:
            self.rabi = create_rabi_for_production(
                k=5,
                similarity_threshold=0.4,
                temperature=0.5
            )
        else:
            self.rabi = None
    
    def _get_drift_estimator(self, context_key: str) -> DriftEstimator:
        """Get or create a per-context drift estimator (class-level persistence)."""
        if context_key not in MemoryService._drift_estimators:
            MemoryService._drift_estimators[context_key] = DriftEstimator(
                window_size=50,
                min_samples=10,
                drift_threshold=0.05,
                abrupt_threshold=0.15
            )
        return MemoryService._drift_estimators[context_key]

    async def get_advice(self, context: DocumentContext) -> PolicyResponse:
        """
        Retrieve policy advice based on document context.
        
        If RABI is enabled:
            1. Find k-nearest neighbors in LTM
            2. Initialize prior using similarity-weighted posteriors
            3. Use Thompson Sampling with informed prior
        
        If RABI is disabled:
            Standard Thompson Sampling with flat priors
        """
        context_str = self.embedding_service.create_context_string(
            context.doc_type, context.vendor
        )
        vector = self.embedding_service.generate_embedding(context_str)
        
        # Query for similar contexts (neighbors for RABI)
        query = """
            SELECT policy_id, policy_data, alpha, beta, context_hash,
                   1 - (context_embedding <=> %s::vector) as similarity
            FROM ltm_validated_policies
            ORDER BY context_embedding <=> %s::vector
            LIMIT %s;
        """
        
        policy_id = "default_policy"
        policy_data = {"action": "standard_processing"}
        source = "DEFAULT"
        rabi_metadata = None
        confidence = 0.3  # Low confidence for default policy
        rabi_used = False
        n_neighbors_used = 0
        best_similarity = 0.0

        async with self.db.cursor() as cur:
            k = self.rabi.k if self.rabi else 5
            await cur.execute(query, (vector, vector, k))
            rows = await cur.fetchall()
            
            if rows:
                if self.use_rabi and self.rabi:
                    # RABI: Build neighbors and initialize prior
                    neighbors = self._build_neighbors(rows)
                    prior = self.rabi.initialize_prior(neighbors)
                    
                    rabi_used = True
                    n_neighbors_used = prior.n_neighbors
                    
                    # Store RABI metadata for analysis
                    rabi_metadata = {
                        "rabi_enabled": True,
                        "n_neighbors": prior.n_neighbors,
                        "avg_similarity": prior.avg_similarity,
                        "confidence": prior.confidence,
                        "initialized_alpha": prior.alpha,
                        "initialized_beta": prior.beta,
                        "expected_reward": self.rabi.get_expected_reward(prior)
                    }
                    
                    # Thompson Sampling with RABI-initialized prior
                    best_sample = -1.0
                    selected_row = None
                    
                    for row in rows:
                        p_id, p_data, alpha, beta, c_hash, sim = row
                        
                        # Use RABI prior for sampling (transferred knowledge)
                        # Blend RABI prior with individual arm's posterior
                        blended_alpha = prior.alpha + (alpha - 1) * sim
                        blended_beta = prior.beta + (beta - 1) * sim
                        
                        sample = random.betavariate(
                            max(0.1, blended_alpha),
                            max(0.1, blended_beta)
                        )
                        
                        if sample > best_sample:
                            best_sample = sample
                            selected_row = row
                            best_similarity = sim
                    
                    # Calculate confidence: combination of RABI confidence and similarity
                    if selected_row:
                        confidence = min(0.95, prior.confidence * 0.6 + best_similarity * 0.4)
                else:
                    # Standard Thompson Sampling (no RABI)
                    best_sample = -1.0
                    selected_row = None
                    
                    for row in rows:
                        p_id, p_data, alpha, beta, c_hash, sim = row
                        sample = random.betavariate(alpha, beta)
                        
                        if sample > best_sample:
                            best_sample = sample
                            selected_row = row
                            best_similarity = sim
                    
                    # Calculate confidence from alpha/beta ratio and similarity
                    if selected_row:
                        _, _, alpha, beta, _, sim = selected_row
                        # Higher alpha relative to beta = higher confidence
                        # More total samples (alpha + beta) = higher confidence
                        total_samples = alpha + beta
                        mean_estimate = alpha / total_samples
                        variance = (alpha * beta) / ((total_samples ** 2) * (total_samples + 1))
                        
                        # Confidence based on precision (inverse variance) and similarity
                        precision_confidence = min(1.0, 1.0 - variance * 10)  # Lower variance = higher confidence
                        similarity_confidence = sim
                        confidence = min(0.95, precision_confidence * 0.5 + similarity_confidence * 0.5)
                
                if selected_row:
                    policy_id, policy_data, _, _, _, _ = selected_row
                    source = "LTM"

        advice_id = uuid.uuid4()
        redis_data = {
            "context": context.model_dump(),
            "source_hash": selected_row[4] if selected_row and len(selected_row) > 4 else None,
            "rabi_metadata": rabi_metadata  # Store RABI info for analysis
        }
        
        redis_key = f"advice:{advice_id}"
        await self.redis.setex(
            redis_key,
            1800,
            json.dumps(redis_data)
        )

        return PolicyResponse(
            advice_id=advice_id,
            policy_id=policy_id,
            policy_data=policy_data,
            retrieval_source=source,
            confidence=round(confidence, 3),
            rabi_used=rabi_used,
            n_neighbors=n_neighbors_used if rabi_used else None
        )

    def _build_neighbors(self, rows: List) -> List[NeighborInfo]:
        """Build NeighborInfo list from database rows for RABI."""
        neighbors = []
        for row in rows:
            p_id, p_data, alpha, beta, c_hash, similarity = row
            neighbors.append(NeighborInfo(
                context_hash=c_hash,
                policy_id=p_id,
                alpha=alpha,
                beta=beta,
                similarity=similarity,
                n_samples=int(alpha + beta - 2)  # Exclude prior
            ))
        return neighbors

    async def log_outcome(self, advice_id: uuid.UUID, policy_id_used: str, metrics: OutcomeMetrics):
        """
        Log outcome to MTM and update LTM bandit parameters.
        
        If DAAF is enabled, applies drift-aware adaptive forgetting BEFORE
        the Bayesian update, so stale knowledge is discounted in real-time.
        """
        redis_key = f"advice:{advice_id}"
        redis_data_json = await self.redis.get(redis_key)
        
        if not redis_data_json:
            print(f"Warning: Context for advice_id {advice_id} not found in STM.")
            return

        redis_data = json.loads(redis_data_json)
        context_dict = redis_data.get("context")
        source_hash = redis_data.get("source_hash")
        
        mtm_query = """
            INSERT INTO mtm_outcomes 
            (advice_id, policy_id_used, document_context, outcome_metrics)
            VALUES (%s, %s, %s::jsonb, %s::jsonb)
        """

        if source_hash:
            target_hash = source_hash
        else:
            doc_type = context_dict.get("doc_type", "unknown")
            vendor = context_dict.get("vendor")
            context_str = self.embedding_service.create_context_string(doc_type, vendor)
            target_hash = hashlib.sha256(context_str.encode('utf-8')).hexdigest()
        
        reward = metrics.f1_score
        reward = max(0.0, min(1.0, reward))
        
        # --- DAAF: Online Drift-Aware Adaptive Forgetting ---
        daaf_gamma = 0.0  # No forgetting by default
        daaf_drift_type = "none"
        
        if self.use_daaf:
            doc_type = context_dict.get("doc_type", "unknown")
            vendor = context_dict.get("vendor")
            context_key = f"{doc_type}:{vendor}" if vendor else doc_type
            
            drift_estimator = self._get_drift_estimator(context_key)
            drift_metrics = drift_estimator.update(reward)
            
            daaf_gamma = drift_metrics.optimal_gamma
            daaf_drift_type = drift_metrics.drift_type.value
        
        # Build update query: apply forgetting THEN Bayesian update
        if self.use_daaf and daaf_gamma > 0.001:
            # DAAF-aware update: retain = (1 - γ), then add reward
            ltm_update_query = """
                UPDATE ltm_validated_policies
                SET 
                    alpha = (1.0 + (1.0 - %s) * (alpha - 1.0)) + %s,
                    beta  = (1.0 + (1.0 - %s) * (beta  - 1.0)) + (1 - %s),
                    confidence_score = 1.0,
                    last_promoted_at = NOW()
                WHERE context_hash = %s AND policy_id = %s
            """
            update_params = (
                daaf_gamma, reward,
                daaf_gamma, reward,
                target_hash, policy_id_used
            )
        else:
            # Standard Bayesian update (no forgetting)
            ltm_update_query = """
                UPDATE ltm_validated_policies
                SET 
                    alpha = alpha + %s,
                    beta = beta + (1 - %s),
                    confidence_score = 1.0,
                    last_promoted_at = NOW()
                WHERE context_hash = %s AND policy_id = %s
            """
            update_params = (reward, reward, target_hash, policy_id_used)
        
        async with self.db.cursor() as cur:
            await cur.execute(
                mtm_query,
                (
                    advice_id,
                    policy_id_used,
                    json.dumps(context_dict),
                    metrics.model_dump_json()
                )
            )

            await cur.execute(ltm_update_query, update_params)

            await self.db.commit()

    async def log_feedback(self, advice_id: uuid.UUID, human_corrected: bool):
        """
        Log human feedback for an advice record.
        
        If human_corrected=True, this penalizes the policy by incrementing beta
        (counting as a failure in the Beta-Bernoulli bandit model).
        """
        # Update MTM record
        mtm_query = """
            UPDATE mtm_outcomes
            SET human_corrected = %s
            WHERE advice_id = %s
        """
        
        async with self.db.cursor() as cur:
            await cur.execute(mtm_query, (human_corrected, advice_id))
            
            # If human had to correct, penalize the policy in LTM
            if human_corrected:
                # Get context and policy from MTM to find the LTM entry
                fetch_query = """
                    SELECT document_context, policy_id_used
                    FROM mtm_outcomes
                    WHERE advice_id = %s
                """
                await cur.execute(fetch_query, (advice_id,))
                row = await cur.fetchone()
                
                if row:
                    context_dict, policy_id = row
                    if isinstance(context_dict, str):
                        context_dict = json.loads(context_dict)
                    
                    doc_type = context_dict.get("doc_type", "unknown")
                    vendor = context_dict.get("vendor")
                    context_str = self.embedding_service.create_context_string(doc_type, vendor)
                    context_hash = hashlib.sha256(context_str.encode('utf-8')).hexdigest()
                    
                    # Penalize: increment beta (failure count) in bandit model
                    penalty_query = """
                        UPDATE ltm_validated_policies
                        SET beta = beta + 1.0
                        WHERE context_hash = %s AND policy_id = %s
                    """
                    await cur.execute(penalty_query, (context_hash, policy_id))
            
            await self.db.commit()
