-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ═══════════════════════════════════════════════════════════════
-- AUTH
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',          -- 'admin' | 'viewer'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- PASSWORD RESET TOKENS
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reset_token ON password_reset_tokens (token);
CREATE INDEX IF NOT EXISTS idx_reset_user ON password_reset_tokens (user_id);

-- ═══════════════════════════════════════════════════════════════
-- AHMN MEMORY TIERS
-- ═══════════════════════════════════════════════════════════════

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
    alpha FLOAT DEFAULT 1.0,
    beta FLOAT DEFAULT 1.0,
    confidence_score FLOAT DEFAULT 1.0,
    last_promoted_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- EXPERIMENT TRACKING
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS experiment_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    method TEXT NOT NULL,
    scenario TEXT NOT NULL,
    seed INTEGER NOT NULL,
    total_regret FLOAT NOT NULL,
    final_accuracy FLOAT,
    convergence_round INTEGER,
    rewards JSONB NOT NULL,
    cumulative_regret JSONB NOT NULL,
    run_config JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- GUARDRAIL AUDIT LOG
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS guardrail_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id TEXT,
    doc_type TEXT NOT NULL,
    overall_passes BOOLEAN NOT NULL,
    processing_time_ms FLOAT NOT NULL,
    checks JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_guardrail_created ON guardrail_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_guardrail_doc_type ON guardrail_audit_log (doc_type);

-- ═══════════════════════════════════════════════════════════════
-- XAI-HITL FEEDBACK
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS xai_hitl_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id TEXT UNIQUE NOT NULL,
    question TEXT NOT NULL,
    original_answer TEXT NOT NULL,
    feedback_type TEXT NOT NULL,
    is_answer_correct BOOLEAN NOT NULL,
    corrected_answer TEXT,
    explanation_quality INT NOT NULL,
    highlight_accuracy INT NOT NULL,
    xai_helpfulness INT NOT NULL,
    additional_context TEXT,
    knowledge_update TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
    reviewer_notes TEXT,
    tags JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hitl_feedback_id ON xai_hitl_feedback (feedback_id);
CREATE INDEX IF NOT EXISTS idx_hitl_created ON xai_hitl_feedback (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hitl_type ON xai_hitl_feedback (feedback_type);

CREATE TABLE IF NOT EXISTS system_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    event_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- INDEXES
-- ═══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_mtm_created ON mtm_outcomes (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mtm_policy ON mtm_outcomes (policy_id_used);
CREATE INDEX IF NOT EXISTS idx_ltm_policy ON ltm_validated_policies (policy_id);
CREATE INDEX IF NOT EXISTS idx_experiment_method ON experiment_runs (method, scenario);
CREATE INDEX IF NOT EXISTS idx_events_type ON system_events (event_type, created_at DESC);

-- ═══════════════════════════════════════════════════════════════
-- ADMIN ACCOUNT
-- No account is seeded here. The gateway creates the first admin at
-- startup from ADMIN_PASSWORD (see .env.example) while none exists.
-- ═══════════════════════════════════════════════════════════════
