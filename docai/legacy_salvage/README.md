# Legacy Salvage Area

## Purpose

This folder is a quarantine area for useful ideas or cleaned code pieces from the legacy system.

Legacy codebase path:
E:\Research Project\Code\IDPO

The legacy system is reference only.
It must not be imported directly into docai_core.

## Reuse Rule

Legacy code can only move through this flow:

study
? document useful idea
? copy only if needed
? clean
? wrap through adapter
? test
? use in docai_core

## Do Not Do

Do not:
- import legacy modules directly
- copy old orchestrator architecture
- copy giant files
- copy mock OCR as production logic
- copy deployment/demo scripts
- copy frontend architecture
- let old code shape DocAI v2 architecture

## Good Candidates To Study

### OCR / Preprocessing
Potential source:
idpo/agents/preprocess.py

Look for:
- OCR retry ideas
- DPI handling
- image preprocessing
- quality scoring
- text cleanup

### Validation / Grounding
Potential source:
idpo/agents/validation.py

Look for:
- field validation
- grounding checks
- normalization
- confidence penalties

### Scoring / Rewards
Potential source:
idpo/pipeline/reward.py

Look for:
- field-level scoring
- grounding coverage
- missing field detection
- hallucination detection

### Policy Matching
Potential source:
idpo/core/policy_store.py

Look for:
- condition matching
- policy metadata
- fallback behavior

### Learning
Potential sources:
ahmn_core/
ahmn_core/direct_advisor.py

Look for:
- Thompson Sampling ideas
- RABI ideas
- DAAF ideas
- job-scoped learning

### Benchmark Assets
Potential sources:
datasets/
idpo/benchmark/

Look for:
- CORD packs
- FUNSD packs
- mixed benchmark packs
- labels and expected values

## Salvage Categories

Use these labels:

QUARANTINE_AND_REUSE:
Useful code or logic that may be cleaned and reused later.

STUDY_ONLY:
Useful idea, but implementation is too coupled or messy.

REWRITE:
Concept is valid, but implementation should be rebuilt cleanly.

DO_NOT_REUSE:
Dangerous, bloated, fake, or incompatible with DocAI v2.

## Required Notes Per Salvaged Item

For every item considered later, document:

- source file
- useful idea
- problems
- reuse category
- target v2 component
- tests needed
- decision

## Current Rule

No legacy code is approved for direct use yet.
All legacy reuse requires review and explicit approval.