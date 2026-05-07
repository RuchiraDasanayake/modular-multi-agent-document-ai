# 2026-03-15 Legacy Reuse Audit

Status: Current as of 2026-03-15

Legacy reference analyzed:
`E:\modular-multi-agent-document-ai-feature-IDPO`

## 1. QUARANTINE_AND_REUSE

- `idpo/core/policy_store.py` for policy matching ideas
- `idpo/core/types.py` for document profile concepts
- `idpo/agents/preprocess.py` selected OCR/preprocessing utilities only
- `idpo/agents/validation.py` validation and grounding ideas
- `idpo/pipeline/reward.py` scoring, grounding coverage, hallucination/missing field logic
- `ahmn_core/direct_advisor.py` Thompson Sampling/job-scoped policy ranking ideas later
- `datasets/` benchmark packs

## 2. STUDY_ONLY

- `idpo/agents/llm_extraction.py`
- `idpo/pipeline/planning.py`
- `idpo/pipeline/executor.py`
- `xai_hitl/`
- old frontend/

## 3. REWRITE

- orchestrator
- benchmark runner
- recovery system
- frontend integration layer
- policy schema

## 4. DO_NOT_REUSE

- old architecture as foundation
- giant integration files
- direct legacy imports into `docai_core`
- mock OCR behavior as production logic
- deployment/demo scripts as product architecture

## Best Engineering Ideas to Preserve

- policy matching by document profile
- OCR retry based on quality
- grounding validation
- field normalization
- reward based on requested fields
- policy gates
- job/run scoped learning
- benchmark packs

## Rules

- legacy code must go through `legacy_salvage` before reuse
- no direct imports from legacy into `docai_core`
- every salvaged function needs tests
- old architecture must not shape v2 architecture

This audit is intentionally practical: preserve proven ideas, discard architectural debt, and gate all reuse through quarantine and tests.
