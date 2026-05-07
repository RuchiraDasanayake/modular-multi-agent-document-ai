# DocAI v2 Core Implementation Plan

Status: Current as of 2026-04-30

## 0. Execution Status

### Completed

- backend/core skeleton
- backend contracts
- ArtifactStore
- stub runtime orchestrator
- runtime spine checkpoint and fixes
- Schema Registry
- `invoice_v1` and `receipt_v1` seed schemas
- Research Evidence Plan

### Current

- Policy Registry and Strategy Assigner implementation/checkpoint

### Next

1. Connect stub orchestrator to Strategy Assigner.
2. Run checkpoint review.
3. Commit.
4. Document queue/run context improvements.

## 1. Purpose

Define the first backend/core implementation path for DocAI v2.

DocAI v2 should be built as a simple modular monolith first, not microservices.

The goal is to create a clean, reliable core that can later connect to the frontend draft.

## 2. Core Principle

Build the system in this order:

contracts  
→ artifact store  
→ fake orchestrator  
→ schema registry  
→ policy registry  
→ document queue  
→ document profiling  
→ policy assignment  
→ extraction planning  
→ OCR/plugin layer  
→ extraction  
→ validation  
→ recovery  
→ final output  
→ metrics  
→ learning records later

Do not start with AHMN.  
Do not start with real OCR.  
Do not start with frontend integration.

## 3. Target Backend Structure

The new backend/core should eventually use this structure:

`docai_core/`
- contracts/
- orchestration/
- artifacts/
- schemas/
- policies/
- capabilities/
- planning/
- plugins/
- extraction/
- validation/
- recovery/
- metrics/
- learning/

`configs/`
- schemas/
- policies/
- prompts/
- runtime/

`apps/`
- api/
- cli/
- ui/ later

`tests/`
- unit/
- integration/
- regression/

`legacy_salvage/`

## 4. First Build Target

The first implementation target is a fake/stub pipeline that proves the runtime spine.

It should support:

1. Create Project
2. Create Extraction Schema
3. Create Job
4. Add Documents to Job Queue
5. Create DocumentProfile
6. Assign SelectedPolicy per document
7. Create RunPlan per document
8. Produce fake OCROutput
9. Produce fake ExtractedOutput
10. Produce ValidationReport
11. Produce RecoveryReport
12. Produce FinalOutput
13. Write artifacts
14. Produce MetricsReport placeholder

No real OCR.  
No real LLM.  
No real learning.  
No frontend connection.

## 5. Why Fake Pipeline First

The fake pipeline is necessary to prove:

- contracts are correct
- artifacts are written
- run lifecycle works
- policy assignment is per document
- final output shape is stable
- frontend/backend integration later has a stable target

## 6. Run Lifecycle

Use this lifecycle:

job_created  
→ documents_queued  
→ profiling  
→ strategies_assigned  
→ planned  
→ extracting  
→ validating  
→ recovering  
→ completed  
→ needs_review  
→ failed

## 7. Policy Assignment Rule for MVP

For MVP, policy assignment should be simple and deterministic.

Input:
- ExtractionSchema
- DocumentProfile
- AvailableTools
- Project context

Output:
- SelectedPolicy per document

No AHMN yet.

Example:
- table-heavy invoice → invoice_table_heavy_local_v1
- low-quality scan → noisy_scan_rescue_v1
- simple receipt → receipt_basic_local_v1

## 8. Artifact Requirement

Every document run must write artifacts.

Required artifacts:
- document_profile.json
- selected_policy.json
- run_plan.json
- ocr_output.json
- extracted_output.json
- validation_report.json
- recovery_report.json
- final_output.json
- run_log.jsonl

Job-level artifacts:
- job_context.json
- metrics_report.json
- extracted_data_export.json

## 9. Implementation Phases

Define phases:

### Phase 1

Create backend contracts.

### Phase 2

Create artifact store.

### Phase 3

Create fake orchestrator.

### Phase 4

Create schema registry.

### Phase 5

Create policy registry and deterministic policy assignment.

### Phase 6

Create fake extraction and final output.

### Phase 7

Create validation/recovery placeholders.

### Phase 8

Create metrics placeholder.

### Phase 9

Only after this, add real OCR/plugin layer.

### Phase 10

Only later, connect frontend.

## 10. Do Not Do Yet

Do not:

- connect frontend
- add real OCR
- add real LLM
- add AHMN
- add RABI/DAAF
- add authentication
- add permissions
- add deployment complexity
- import legacy code directly
- rewrite Gemini UI

## 11. Parallel Work Rules

- Only parallelize docs work, frontend draft cleanup planning, and legacy audit notes.
- Do not parallelize core backend modifications.
- Do not connect frontend/backend yet.
- Do not implement OCR/LLM/AHMN yet.

## 12. Legacy Rule

The legacy codebase is reference only.

Useful code may later be copied into `legacy_salvage/` and wrapped through adapters.

The new orchestrator must never directly import old legacy modules.

Keep the document clear, strict, and practical.
