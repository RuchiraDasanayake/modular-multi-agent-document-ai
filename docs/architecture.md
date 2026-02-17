# Architecture

This prototype implements a multi-agent, preprocessing-aware document pipeline that remains domain-agnostic by default. Domain-specific extraction rules are configured via external config, not hard-coded.

## Pipeline Flow

1. Intake and raw artifact capture
2. DAE (Document Analysis Engine) emits doc type, bins, and signals
3. Router selects policy and builds an ExecutionPlan
4. Plan execution runs ordered operators with budgets and timeouts
5. Validation + field-level recovery + budgeted escalation
6. Chunking and embedding
7. Indexing (vector + BM25)
8. Hybrid retrieval and context selection
9. Answering with citations
10. Provenance export

## Agents and Responsibilities

- Intake: ingestion and raw capture
- DAE: quality/complexity bins + content profile + signals
- Router: policy selection, AHMN overrides, plan construction
- Preprocessing: OCR, denoise, deskew, table/form extraction (versioned + parameterized)
- Structuring: LLM entity extraction, sectioning, summarization
- Validation: rule-based checks, normalization, confidence estimates
- Recovery: field-level repair using raw signals
- Escalation: cost-aware fallback decisioning
- Chunking: section-aware chunk creation
- Retrieval: hybrid dense + lexical + metadata scoring
- Answering: citation-backed responses and abstention logic

## Contracts and Signals

Each agent declares an explicit input/output contract (JSON-like schemas) and emits a `StageSignal` with confidence, uncertainty, and failure reason. These signals drive routing, recovery, escalation, and abstention decisions.

## Provenance and Audit

Each agent call emits an immutable event with:

- agent name + version
- inputs and outputs
- parameters and cost units
- artifacts created
- latency

These events are stored in `runs/<run-id>/provenance.jsonl`. A provenance graph is kept in `runs/<run-id>/provenance_graph.json` to support the chain: answer -> chunks -> embeddings -> preprocessing -> raw document.
