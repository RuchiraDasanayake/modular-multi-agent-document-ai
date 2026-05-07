# AGENTS.md — DocAI v2 Development Rules

## Project Purpose

DocAI v2 is a clean rebuild of a local, policy-driven document extraction orchestrator.

The product is inspired by enterprise IDP systems such as ABBYY Vantage and UiPath Document Understanding.

Core user flow:
Project
→ Extraction Schema
→ Job
→ Document Queue
→ Document Profile
→ Extraction Strategy Assignment
→ Run Plan
→ OCR / Parsing
→ Structured Extraction
→ Validation
→ Recovery
→ Review
→ Expected Values
→ Metrics
→ Learning Records
→ Export

## Product Vocabulary

Use these product terms:

- Extraction Schema
- Field
- Table
- Column
- Job
- Document Queue
- Document Profile
- Extraction Strategy
- Policy only as internal/technical wording
- Training Run
- Production Run
- Expected Values
- Review
- Metrics
- Learning Record

Do not use vague terms like:
- magic AI
- advanced policy
- visual QA
- smart extractor
- policy_1
- default policy

## Architecture Rules

DocAI v2 starts as a modular monolith.

Do not create microservices yet.
Do not add database yet.
Do not add API endpoints yet.
Do not connect frontend yet.
Do not add real OCR/LLM until the runtime spine is stable.
Do not import legacy code directly into docai_core.

Core backend folders:

docai_core/contracts/
docai_core/artifacts/
docai_core/schemas/
docai_core/policies/
docai_core/capabilities/
docai_core/planning/
docai_core/orchestration/
docai_core/extraction/
docai_core/validation/
docai_core/recovery/
docai_core/metrics/
docai_core/learning/

## Current Build Stage

Current stage:
Runtime spine foundation.

Implemented or in progress:
- backend contracts
- ArtifactStore
- SchemaRegistry
- PolicyRegistry
- StrategyAssigner
- JobContextBuilder
- DocumentQueueBuilder
- RunPlanBuilder
- StubExtractionRunner
- FakeOrchestrator as temporary runtime spine coordinator

## Strict Scope Rules

Every task must declare:
- allowed files
- forbidden files
- test command

Do not modify files outside the allowed list.

If a change requires touching another file, stop and report why.

## Fake / Stub Rule

FakeOrchestrator and StubExtractionRunner are temporary.

They exist only to prove runtime flow.

Do not add real OCR, LLM, learning, API, database, production processing, or frontend integration inside them.

All stub artifacts must be clearly labeled with:
- is_stub: true
- generated_by
- note

Fake metrics must be marked:
- metrics_status: not_real_metrics

Never report fake metrics as real performance.

## Orchestrator Rule

FakeOrchestrator should coordinate components, not own all logic.

Prefer extracting small builders/runners when it grows:
- JobContextBuilder
- DocumentQueueBuilder
- RunPlanBuilder
- StubExtractionRunner

Do not keep adding responsibilities to FakeOrchestrator.

## Domain Contract Rule

Do not keep growing docai_core/contracts/domain.py casually.

Before adding new contracts, consider whether they belong in a separate module later.

Do not use `Any` or `type: ignore` to hide contract mismatches.

If a contract mismatch appears, fix the contract or fix the caller.

## Policy / Strategy Rules

Use "Extraction Strategy" as the user-facing term.

Use "Policy" only internally.

Every strategy must explain:
- what it is
- when it is used
- what it changes
- tradeoffs
- not recommended cases

Strategy assignment is per document.

Do not implement AHMN, Thompson Sampling, RABI, or DAAF until deterministic strategy assignment and metrics are stable.

## Context / Learning Rules

ProjectContext is approved long-lived project memory.
JobContext is a run-specific snapshot.
LearningRecord is evidence, not automatic mutation.

Do not silently rewrite prompts, schemas, strategies, or policies.

Future learning flow:
reviewed evidence
→ recommendation
→ approval
→ new version

## Legacy Code Rules

Legacy path:
E:\modular-multi-agent-document-ai-feature-IDPO

Legacy code is reference only.

Allowed:
- study
- document useful ideas
- quarantine specific reviewed pieces later

Forbidden:
- direct imports from legacy into docai_core
- copying old orchestrator architecture
- copying giant files
- using old frontend architecture
- letting old architecture shape v2

Legacy quarantine location:
legacy_salvage/

## Frontend Rules

Gemini frontend draft path:
docs/Doc-AI-V2-Front End Gemini Draft

Do not modify frontend unless a task explicitly says frontend work is allowed.

Frontend is draft only until cleaned.

Do not connect frontend to backend yet.

## Documentation Rules

Prefer living docs:
- docs/IMPLEMENTATION_PLAN.md
- docs/FRONTEND_PLAN.md
- docs/CONTRACTS.md
- docs/ARCHITECTURE.md
- docs/RESEARCH_EVIDENCE_PLAN.md
- docs/DEPLOYMENT_AND_SCALING_PLAN.md

Dated docs are snapshots or audits.

Do not create new planning docs unless necessary.
Prefer updating existing living docs.

## Testing Rules

Use pytest.

For backend changes, run the narrow relevant test first.

Before commit, run:

python -m pytest tests/unit tests/integration -q

Tests should check behavior and artifact payloads, not just file existence.

## Review Workflow

Codex should not judge architecture.

For checkpoints:
1. Print exact relevant files.
2. Do not summarize.
3. Do not suggest fixes.
4. Human/architect reviews.
5. Then apply a scoped fix prompt.

## Output Rule

After implementation tasks, output:
- changed files
- test command run
- test result
- any errors

Do not add extra commentary.

## Forbidden Until Explicitly Approved

Do not build:
- real OCR
- real LLM extraction
- AHMN
- Thompson Sampling
- RABI
- DAAF
- backend API
- database
- authentication
- permissions
- deployment automation
- frontend-backend integration
- automatic prompt rewriting
- automatic policy mutation
