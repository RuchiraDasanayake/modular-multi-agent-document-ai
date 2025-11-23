-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- MTM (Mid-Term Memory): Raw Logs
CREATE TABLE IF NOT EXISTS mtm_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    advice_id UUID NOT NULL,
    policy_id_used TEXT NOT NULL,
    document_context JSONB NOT NULL,
    outcome_metrics JSONB NOT NULL,
    human_corrected BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- LTM (Long-Term Memory): Validated Strategies
CREATE TABLE IF NOT EXISTS ltm_validated_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    context_hash TEXT UNIQUE NOT NULL,
    context_embedding vector(384),
    policy_id TEXT NOT NULL,
    policy_data JSONB NOT NULL,
    validation_metrics JSONB NOT NULL,
    last_promoted_at TIMESTAMPTZ DEFAULT NOW()
);
