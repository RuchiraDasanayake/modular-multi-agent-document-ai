# Research Log

This file is the running research journal for paper-facing decisions and evidence.

Rules:

- record only decisions backed by code, artifacts, or measured results
- separate runtime fixes from dataset or scoring fixes
- include exact artifact paths when results matter
- do not silently rewrite past conclusions; add a new dated entry instead

Suggested entry structure:

- `Date`
- `Change`
- `Reason`
- `Evidence`
- `Claim impact`
- `Risk`
- `Next action`

## 2026-04-29

### Entry 1: Schema-conditioned benchmark moved to 7-field schema v2

- `Date`: 2026-04-29
- `Change`:
  - replaced the previous 9-field mixed schema with a 7-field business-header schema:
    - `document_type`
    - `document_date`
    - `issuer_name`
    - `recipient_name`
    - `reference_id`
    - `primary_organization`
    - `total_amount`
  - updated the pack builder, benchmark normalization, prompt guidance, and plan doc
- `Reason`:
  - the old schema carried weak or low-value fields (`address`, `brief_explanation`)
  - the old names were too vague (`sender`, `subject`, `company`, `amount`)
  - the 100-record mix supports a narrower business-header schema more cleanly
- `Evidence`:
  - code:
    - [scripts/build_schema_conditioned_pack.py](</E:/Research Project/Code/IDPO/scripts/build_schema_conditioned_pack.py:1>)
    - [scripts/run_idpo_benchmark.py](</E:/Research Project/Code/IDPO/scripts/run_idpo_benchmark.py:148>)
    - [idpo/agents/extraction_prompts.py](</E:/Research Project/Code/IDPO/idpo/agents/extraction_prompts.py:33>)
    - [docs/SCHEMA_CONDITIONED_ONLINE_LEARNING_PLAN.md](</E:/Research Project/Code/IDPO/docs/SCHEMA_CONDITIONED_ONLINE_LEARNING_PLAN.md:1>)
  - regenerated pack summary:
    - `doc_count = 100`
    - `document_date = 52`
    - `issuer_name = 45`
    - `recipient_name = 44`
    - `primary_organization = 40`
    - `total_amount = 39`
    - `reference_id = 34`
    - `avg_non_type_positive_fields = 2.54`
  - artifact:
    - [schema_conditioned_100.json](</E:/Research Project/Code/IDPO/datasets/schema_conditioned_100.json:1>)
- `Claim impact`:
  - strengthens the paper claim by narrowing it to shared structured business-header extraction
  - removes non-structured narrative output from the main benchmark contract
- `Risk`:
  - the schema is better, but synthetic invoice `total_amount` still lacked trusted labels upstream
- `Next action`:
  - quarantine synthetic invoice `total_amount` from scoring until trusted labels exist

### Entry 2: Synthetic invoice `total_amount` quarantined from exact scoring

- `Date`: 2026-04-29
- `Change`:
  - marked invoice-source `total_amount` as `quarantined_invoice_total_unlabeled`
  - changed benchmark scoring to skip quarantined fields entirely
- `Reason`:
  - the local synthetic invoice source file contains no trusted upstream total label
  - treating extracted totals as hallucinations would push wrong negative feedback into AHMN
- `Evidence`:
  - source inspection:
    - [datasets/diverse_docs/invoice_cases.json](</E:/Research Project/Code/IDPO/datasets/diverse_docs/invoice_cases.json:1>)
    - invoice cases carry `invoice_number`, `invoice_date`, `vendor_name`, `customer_name`
    - no `total_amount` label exists in that source file
  - code:
    - [scripts/build_schema_conditioned_pack.py](</E:/Research Project/Code/IDPO/scripts/build_schema_conditioned_pack.py:210>)
    - [scripts/run_idpo_benchmark.py](</E:/Research Project/Code/IDPO/scripts/run_idpo_benchmark.py:137>)
    - [idpo/tests/test_research_features.py](</E:/Research Project/Code/IDPO/idpo/tests/test_research_features.py:1575>)
  - validation:
    - `.venv\Scripts\python.exe -m pytest idpo/tests/test_research_features.py -v`
    - quarantined-field regression test passed
- `Claim impact`:
  - prevents corrupted online-learning feedback
  - narrows the benchmark: invoice totals from this synthetic source are currently out of exact scope
- `Risk`:
  - this is a quarantine, not a label recovery
  - the benchmark no longer measures invoice total extraction quality for this source
- `Next action`:
  - continue the online-learning loop only with the quarantined scorer, or replace the source with trusted invoice total labels later

### Entry 3: Clean schema v2 online-learning run restarted

- `Date`: 2026-04-29
- `Change`:
  - restarted the schema v2 online-learning loop from a fresh adaptive job after quarantine
  - ran batch 01 and batch 02 under one persistent adaptive scope
- `Reason`:
  - old schema v2 batch 01 before quarantine had wrong negative signal on synthetic invoice totals
  - changing benchmark semantics required a clean restart
- `Evidence`:
  - clean frontend job:
    - [6eca91f89b1a42d381dbcb3ab64eecf8.json](</E:/Research Project/Code/idpo-data/frontend/jobs/6eca91f89b1a42d381dbcb3ab64eecf8.json:1>)
  - clean benchmark reports:
    - [benchmark_1777405173/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777405173/paper_evidence.json:1>)
    - [benchmark_1777405492/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777405492/paper_evidence.json:1>)
  - AHMN scope persistence:
    - [adaptive_safe_batch_1777405173513/ahmn_state.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777405173513/ahmn_state.json:1>) -> `call_count: 5`
    - [adaptive_safe_batch_1777405492051/ahmn_state.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777405492051/ahmn_state.json:1>) -> `call_count: 10`
  - batch results:
    - batch 01:
      - `document_type_accuracy = 1.0`
      - `positive_field_f1 = 0.6341`
      - `unavailable_field_count = 0`
    - batch 02:
      - `document_type_accuracy = 1.0`
      - `positive_field_f1 = 0.6364`
      - `unavailable_field_count = 0`
- `Claim impact`:
  - the benchmark loop is now clean enough to continue without known scorer-induced negative feedback
  - current runtime claim remains narrow: adaptive extraction over a shared structured schema with auditable job-scoped learning
- `Risk`:
  - these first 10 records are invoice-heavy and do not yet prove heterogeneous advantage
  - issuer and recipient extraction are still weak on several synthetic invoices
- `Next action`:
  - continue with batch 03 under the same clean job and inspect whether heterogeneous batches preserve or improve positive-field F1

### Entry 4: Clean schema v2 batch 03 completed under the same adaptive scope

- `Date`: 2026-04-29
- `Change`:
  - ran batch 03 under the existing clean frontend job `6eca91f89b1a42d381dbcb3ab64eecf8`
  - kept the same adaptive AHMN learning scope created at batch 01
  - extended the clean online-learning trace from 10 to 15 processed records
- `Reason`:
  - the clean post-quarantine benchmark loop needed one more batch to confirm that scope persistence still holds after additional feedback
  - the research log needed a first-15-record checkpoint with exact artifact references
- `Evidence`:
  - batch 03 benchmark report:
    - [benchmark_1777405814/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777405814/paper_evidence.json:1>)
  - latest adaptive run and state:
    - [adaptive_safe_batch_1777405815192/ahmn_state.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777405815192/ahmn_state.json:1>) -> `call_count: 15`
  - clean frontend job continuity:
    - [6eca91f89b1a42d381dbcb3ab64eecf8.json](</E:/Research Project/Code/idpo-data/frontend/jobs/6eca91f89b1a42d381dbcb3ab64eecf8.json:1>)
    - `latestRunId = adaptive_safe_batch_1777405815192`
    - `learningJobIds.adaptive_safe = bench_benchmark_1777405173_adaptive_safe`
  - batch 03 results:
    - `document_type_accuracy = 1.0`
    - `positive_field_precision = 0.7619`
    - `positive_field_recall = 0.64`
    - `positive_field_f1 = 0.6957`
    - `exact_f1 = 0.4545`
    - `avg_reward = 0.9301`
    - `avg_schema_coverage = 0.8857`
    - `unavailable_field_count = 0`
  - aggregate over clean batches 01 to 03:
    - `doc_count = 15`
    - `document_type_accuracy = 1.0`
    - `positive_field_precision = 0.7679`
    - `positive_field_recall = 0.5733`
    - `positive_field_f1 = 0.6565`
    - `exact_precision = 0.5233`
    - `exact_recall = 0.4286`
    - `exact_f1 = 0.4712`
    - `avg_reward = 0.8905`
    - `avg_schema_coverage = 0.8190`
- `Claim impact`:
  - confirms that the clean schema `v2` loop preserves one job-scoped adaptive memory across 15 records with benchmark feedback logged on every document
  - gives a paper-usable first-15-record checkpoint with no known scorer-induced unavailable hallucination penalty
- `Risk`:
  - the first 15 clean records are still all synthetic invoices, so this does not support a heterogeneity claim yet
  - issuer and recipient extraction remain the main quality bottlenecks inside this invoice-only slice
- `Next action`:
  - run batch 04 under the same clean job and inspect the first mixed slice before drawing any online-learning effectiveness conclusion

### Entry 5: First mixed slice caused a sharp regression at batch 04

- `Date`: 2026-04-29
- `Change`:
  - ran batch 04 under the same clean frontend job `6eca91f89b1a42d381dbcb3ab64eecf8`
  - extended the persistent adaptive scope from 15 to 20 records
  - recorded the first mixed slice result: `4` synthetic invoices and `1` DocVQA `other` case
- `Reason`:
  - the clean loop needed a non-invoice-only checkpoint before any claim about broader usefulness
  - the benchmark now has evidence that the first mixed slice does not behave like the first three invoice-only batches
- `Evidence`:
  - batch 04 benchmark report:
    - [benchmark_1777406074/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777406074/paper_evidence.json:1>)
  - latest adaptive run and state:
    - [adaptive_safe_batch_1777406074882/ahmn_state.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777406074882/ahmn_state.json:1>) -> `call_count: 20`
  - clean frontend job continuity:
    - [6eca91f89b1a42d381dbcb3ab64eecf8.json](</E:/Research Project/Code/idpo-data/frontend/jobs/6eca91f89b1a42d381dbcb3ab64eecf8.json:1>)
    - `latestRunId = adaptive_safe_batch_1777406074882`
    - batch 04 appended `schema_invoice_0016` to `schema_invoice_0019` and `schema_docvqa_14184`
  - batch 04 mix:
    - [schema_mixed_batch_04.json](</E:/Research Project/Code/IDPO/datasets/schema_conditioned_batches/schema_mixed_batch_04.json:1>)
    - `invoice = 4`
    - `other = 1`
    - source mix: `Diverse invoices local = 4`, `DocVQA local = 1`
  - batch 04 results:
    - `document_type_accuracy = 0.6`
    - `positive_field_precision = 0.0`
    - `positive_field_recall = 0.0`
    - `positive_field_f1 = 0.0`
    - `exact_f1 = 0.0968`
    - `unavailable_field_count = 4`
    - `unavailable_hallucination_rate = 0.75`
    - `validation_pass_rate = 0.8`
    - `recovery_rate = 0.2`
    - `escalation_rate = 0.2`
  - aggregate over clean batches 01 to 04:
    - `doc_count = 20`
    - `document_type_accuracy = 0.9000`
    - `positive_field_precision = 0.5972`
    - `positive_field_recall = 0.4433`
    - `positive_field_f1 = 0.5089`
    - `exact_precision = 0.4248`
    - `exact_recall = 0.3429`
    - `exact_f1 = 0.3794`
    - `unavailable_field_count = 4`
    - `unavailable_hallucination_rate = 0.7500`
- `Claim impact`:
  - the persistent-job claim still holds
  - the usefulness claim does not hold across the first mixed slice yet
  - the current adaptive loop cannot be described as robust across document-family transition
- `Risk`:
  - continuing more batches without inspecting case-level failures risks training on a broader mixed-distribution error mode
  - this regression may reflect schema mismatch, dataset mapping weakness, or extraction behavior on the first DocVQA-style case
- `Next action`:
  - inspect the batch 04 case-level failures before running batch 05

### Entry 6: Batch 05 confirms DocVQA-other over-extraction and sparse-label weakness

- `Date`: 2026-04-29
- `Change`:
  - ran batch 05 under the same clean frontend job `6eca91f89b1a42d381dbcb3ab64eecf8`
  - extended the persistent adaptive scope from 20 to 25 records
  - recorded the first all-DocVQA `other` slice and captured the main failure pattern
- `Reason`:
  - batch 04 already showed the first mixed-slice regression
  - batch 05 was needed to determine whether that regression was a one-off or a stable failure mode on `other` business documents
- `Evidence`:
  - batch 05 benchmark report:
    - [benchmark_1777406293/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777406293/paper_evidence.json:1>)
  - latest adaptive run and state:
    - [adaptive_safe_batch_1777406293318/ahmn_state.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777406293318/ahmn_state.json:1>) -> `call_count: 25`
  - batch 05 pack:
    - [schema_mixed_batch_05.json](</E:/Research Project/Code/IDPO/datasets/schema_conditioned_batches/schema_mixed_batch_05.json:1>)
    - `document_type = other` for all 5 docs
    - `source = DocVQA local` for all 5 docs
    - `avg_non_type_positive_fields = 1.2`
  - batch 05 results:
    - `document_type_accuracy = 0.8`
    - `positive_field_f1 = 0.0`
    - `exact_f1 = 0.1270`
    - `validation_pass_rate = 0.0`
    - `recovery_rate = 0.6`
    - `escalation_rate = 1.0`
    - `unavailable_field_count = 24`
    - `unavailable_hallucination_rate = 0.7083`
  - aggregate over clean batches 01 to 05:
    - `doc_count = 25`
    - `document_type_accuracy = 0.8800`
    - `positive_field_f1 = 0.4751`
    - `exact_f1 = 0.3291`
    - `unavailable_field_count = 28`
    - `unavailable_hallucination_rate = 0.7143`
  - case-level examples:
    - [schema_docvqa_5232 extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777406293318/docs/schema_docvqa_5232/structuring/extracted.json:1>)
      - expected `reference_id = Menopausal Health Publication Management`
      - extracted `reference_id = DUROJ012-001293`
      - extracted low-confidence `document_date = 5-6/01`
      - extracted low-confidence `total_amount = 555-6B`
    - [schema_docvqa_214 extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777406293318/docs/schema_docvqa_214/structuring/extracted.json:1>)
      - expected `reference_id = SARGASSO SEA TEMPERATURE`
      - extracted `reference_id = ttwl0228`
      - expected `primary_organization = Exxonmobil`
      - extracted `primary_organization = National Research Council`
    - [schema_docvqa_14388 extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777406293318/docs/schema_docvqa_14388/structuring/extracted.json:1>)
      - expected `document_type = other`
      - extracted `document_type = receipt`
      - expected `document_date = february 22, 1971`
      - extracted `document_date = APRIL`
      - hallucinated `total_amount = $6.00`
- `Claim impact`:
  - the persistent-job claim still holds through 25 records
  - the extraction-quality claim weakens materially once the benchmark shifts from synthetic invoices to DocVQA `other` pages
  - the current shared-schema benchmark mixes two things that should be separated in the paper:
    - genuine extraction failure
    - sparse-label silence compliance on `other` documents
- `Risk`:
  - continuing more batches without fixing the `other`-document contract will keep producing low-signal negative feedback
  - many DocVQA `other` cases label only one or two fields and mark the rest `unavailable_from_unmapped_label`, so the benchmark rewards suppression more than useful extraction
- `Next action`:
  - implement a high-ROI guardrail for `other` documents: suppress low-confidence regex fallback on `document_date`, `reference_id`, and `total_amount`, and block `issuer_name` / `recipient_name` / `total_amount` unless there is strong explicit grounding

### Entry 7: Added conservative fallback guardrail for `other`-document extraction

- `Date`: 2026-04-29
- `Change`:
  - strengthened per-field prompt rules for:
    - `document_type`
    - `reference_id`
    - `total_amount`
  - added a heuristic extraction guardrail that suppresses low-confidence regex fallback for:
    - `document_date`
    - `reference_id`
    - `total_amount`
    - when the document does not look transaction-like or form-like
- `Reason`:
  - batch 05 showed that DocVQA `other` pages were being filled with low-signal fallback values such as dates, codes, and amounts that should have remained missing
  - the highest-ROI fix was to stop permissive fallback from manufacturing structured fields in low-label `other` slices
- `Evidence`:
  - code:
    - [idpo/agents/extraction_prompts.py](</E:/Research Project/Code/IDPO/idpo/agents/extraction_prompts.py:1>)
    - [idpo/agents/llm_extraction.py](</E:/Research Project/Code/IDPO/idpo/agents/llm_extraction.py:1>)
  - regression tests:
    - [idpo/tests/test_extraction_enhancements.py](</E:/Research Project/Code/IDPO/idpo/tests/test_extraction_enhancements.py:1>)
    - added coverage proving:
      - risky regex fallback is blocked for `other` documents
      - transaction-style fallback still works for invoice-like documents
      - new single-field prompt rules are present for `document_type` and `reference_id`
  - validation:
    - `.venv\Scripts\python.exe -m pytest idpo/tests/test_extraction_enhancements.py -v`
    - `.venv\Scripts\python.exe -m pytest idpo/tests/test_research_features.py -k schema_conditioned -v`
- `Claim impact`:
  - improves the defensibility of the shared-schema benchmark by making the extractor more conservative on sparse-label `other` documents
  - does not yet prove an empirical benchmark gain because no post-fix batch rerun has been executed yet
- `Risk`:
  - this is an extractor-side guardrail, not a dataset fix
  - `reference_id` and party-role semantics on DocVQA `other` pages may still need additional tuning after rerun
- `Next action`:
  - rerun batch 05 after the guardrail change and compare unavailable hallucination rate and positive-field F1 against `benchmark_1777406293`

### Entry 8: Post-fix five-batch run shows DocVQA improvement but form-slice failure remains

- `Date`: 2026-04-29
- `Change`:
  - started a fresh clean post-fix benchmark job at batch 05
  - ran five consecutive adaptive-only batches under one persistent scope:
    - batch 05
    - batch 06
    - batch 07
    - batch 08
    - batch 09
- `Reason`:
  - the extractor-side guardrail needed end-to-end validation, not just unit tests
  - a fresh job was required to avoid mixing pre-fix and post-fix adaptive memory
- `Evidence`:
  - clean frontend job:
    - [d8b862c1c9944facbe0482d39cc26450.json](</E:/Research Project/Code/idpo-data/frontend/jobs/d8b862c1c9944facbe0482d39cc26450.json:1>)
  - persistent AHMN scope:
    - [adaptive_safe_batch_1777416953077/ahmn_state.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777416953077/ahmn_state.json:1>) -> `call_count: 25`
    - `scope_key = job_bench_benchmark_1777416388_adaptive_safe`
  - batch reports:
    - [benchmark_1777416388/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777416388/paper_evidence.json:1>)
    - [benchmark_1777416556/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777416556/paper_evidence.json:1>)
    - [benchmark_1777416703/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777416703/paper_evidence.json:1>)
    - [benchmark_1777416831/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777416831/paper_evidence.json:1>)
    - [benchmark_1777416952/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777416952/paper_evidence.json:1>)
  - batch mix:
    - batch 05: `DocVQA local = 5`, all `other`, `avg_non_type_positive_fields = 1.2`
    - batch 06: `DocVQA local = 5`, all `other`, `avg_non_type_positive_fields = 1.8`
    - batch 07: `DocVQA local = 4`, `FUNSD = 1`, mix of `other` and `form`
    - batch 08: `FUNSD = 5`, all `form`
    - batch 09: `FUNSD = 5`, all `form`
  - direct batch 05 comparison before vs after the guardrail:
    - old batch 05 report: [benchmark_1777406293/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777406293/paper_evidence.json:1>)
    - new batch 05:
      - `document_type_accuracy` improved from `0.8` to `1.0`
      - `exact_f1` improved from `0.1270` to `0.1695`
      - `unavailable_hallucination_rate` improved from `0.7083` to `0.6250`
      - `unavailable_hallucination_count` improved from `17` to `15`
      - `positive_field_f1` stayed at `0.0`
  - aggregate over post-fix batches 05 to 09:
    - `doc_count = 25`
    - `document_type_accuracy = 0.5600`
    - `positive_field_precision = 0.2188`
    - `positive_field_recall = 0.1296`
    - `positive_field_f1 = 0.1628`
    - `exact_precision = 0.2100`
    - `exact_recall = 0.1200`
    - `exact_f1 = 0.1527`
    - `unavailable_field_count = 96`
    - `unavailable_hallucination_rate = 0.4479`
    - `avg_schema_coverage = 0.5771`
- `Claim impact`:
  - the guardrail helped the DocVQA `other` silence-compliance problem
  - the benchmark still fails as a broad mixed-family claim because the next exposed weakness is form-heavy extraction and classification
  - the current post-fix result supports a narrower claim:
    - conservative fallback reduced hallucinated unavailable fields on sparse `other` pages
    - but did not solve cross-family structured extraction quality
- `Risk`:
  - averaging batches 05 to 09 hides the transition in failure mode
  - the dominant remaining weakness is no longer just DocVQA `other`; it is also poor `form` handling in the FUNSD-heavy slices
- `Next action`:
  - inspect the first FUNSD-heavy failures from batches 08 and 09 before running any more benchmark batches

### Entry 9: Recovery disabled by default pending contract repair

- `Date`: 2026-04-29
- `Change`:
  - added a real core config switch for recovery and set it to `disabled` by default
  - removed the recovery step from default plan construction when recovery is disabled
  - added an executor backstop so legacy plans cannot silently run recovery when the config says it is off
  - updated system and project docs to state that recovery must remain disabled until fixed
- `Reason`:
  - recovery was introducing semantically invalid values such as header words being written back as dates
  - recovery field targeting is not trustworthy enough for benchmark evidence
  - allowing it to remain enabled by default would continue to contaminate adaptive-safe evaluation
- `Evidence`:
  - code:
    - [idpo/core/config.py](</E:/Research Project/Code/IDPO/idpo/core/config.py:1>)
    - [idpo/pipeline/planning.py](</E:/Research Project/Code/IDPO/idpo/pipeline/planning.py:1>)
    - [idpo/pipeline/executor.py](</E:/Research Project/Code/IDPO/idpo/pipeline/executor.py:1>)
    - [idpo/agents/recovery.py](</E:/Research Project/Code/IDPO/idpo/agents/recovery.py:1>)
    - [configs/config.json](</E:/Research Project/Code/IDPO/configs/config.json:1>)
    - [configs/idpo_research_config.json](</E:/Research Project/Code/IDPO/configs/idpo_research_config.json:1>)
  - docs:
    - [docs/SYSTEM_CONTRACT.md](</E:/Research Project/Code/IDPO/docs/SYSTEM_CONTRACT.md:1>)
    - [docs/PROJECT_DIRECTION.md](</E:/Research Project/Code/IDPO/docs/PROJECT_DIRECTION.md:1>)
- `Claim impact`:
  - reduces the chance of benchmark contamination from invalid recovery writeback
  - narrows the active runtime claim: current adaptive-safe evaluation no longer includes recovery as an enabled core behavior
- `Risk`:
  - some genuinely recoverable low-confidence fields will now remain missing
  - recovery artifacts still exist for compatibility, so readers must not mistake artifact presence for active recovery behavior
- `Next action`:
  - rerun one previously recovery-affected failing batch to confirm the benchmark no longer receives recovery-induced false values

### Entry 10: DAE OCR bootstrap and extraction-context plumbing repaired

- `Date`: 2026-04-29
- `Change`:
  - made the canonical pipeline bootstrap OCR before DAE when an image-backed document arrives without usable text, so routing no longer operates on an empty-text state
  - tightened generic form-feature detection in DAE so label-anchored OCR lines contribute to `form_ratio` and `kv_density` even when they do not use a colon
  - fixed extraction-context propagation so executor actually passes `extraction_context` into the extraction agent
  - composed extraction context from generic analysis context plus accumulated job context, instead of leaving job context trapped in the advisor payload and never reaching the extractor
  - allowed adaptive recommendation field templates to merge into extraction field descriptions when present
- `Reason`:
  - DAE was making routing decisions before OCR text existed for image-only pages
  - extraction context was effectively dead because the executor and extraction agent were not honoring the planned `extraction_context` field
  - job context accumulation existed, but the extractor never saw it
- `Evidence`:
  - code:
    - [idpo/pipeline/orchestrator.py](</E:/Research Project/Code/IDPO/idpo/pipeline/orchestrator.py:1>)
    - [idpo/agents/doc_analysis.py](</E:/Research Project/Code/IDPO/idpo/agents/doc_analysis.py:1>)
    - [idpo/pipeline/planning.py](</E:/Research Project/Code/IDPO/idpo/pipeline/planning.py:1>)
    - [idpo/pipeline/executor.py](</E:/Research Project/Code/IDPO/idpo/pipeline/executor.py:1>)
    - [idpo/agents/llm_extraction.py](</E:/Research Project/Code/IDPO/idpo/agents/llm_extraction.py:1>)
- `Claim impact`:
  - strengthens the core adaptive-safe claim because policy selection and extraction context now operate on OCR-derived state instead of dead wiring
  - keeps the fix generic: better OCR-grounded state and context propagation, not dataset-template special casing
- `Risk`:
  - image-backed documents may now incur an extra OCR pass before routing
  - if OCR bootstrap quality is poor, routing can still be wrong, but it is now wrong on observed text rather than on a blank state
- `Next action`:
  - rerun one previously misrouted mixed batch and inspect whether DAE state, selected policy, and extraction context all align in the emitted artifacts

### Entry 11: Continued same adaptive job for 10 more mixed documents after OCR/context repair

- `Date`: 2026-04-29
- `Change`:
  - continued the existing mixed benchmark job `d8b862c1c9944facbe0482d39cc26450` for 10 additional adaptive-only documents
  - processed batch 10 and batch 11 under the same persisted adaptive learning scope `job_bench_benchmark_1777416388_adaptive_safe`
- `Reason`:
  - the goal was to observe what the repaired DAE and extraction-context plumbing do in the live mixed-job continuation, not in a fresh clean restart
- `Evidence`:
  - run directories:
    - [adaptive_safe_batch_1777424388659](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424388659>)
    - [adaptive_safe_batch_1777424388685](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424388685>)
  - sample repaired artifact chain:
    - [schema_funsd_test_83553333_3334 dae/output.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424388659/docs/schema_funsd_test_83553333_3334/dae/output.json:1>)
    - [schema_funsd_test_83553333_3334 plan/primary.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424388659/docs/schema_funsd_test_83553333_3334/plan/primary.json:1>)
    - [schema_funsd_test_83772145 dae/output.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424388685/docs/schema_funsd_test_83772145/dae/output.json:1>)
    - [schema_funsd_test_83772145 plan/primary.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424388685/docs/schema_funsd_test_83772145/plan/primary.json:1>)
  - batch-level runtime summaries:
    - batch 10 run metrics: [adaptive_safe_batch_1777424388659/metrics.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424388659/metrics.json:1>)
    - batch 11 benchmark report: [benchmark_1777424388/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777424388/paper_evidence.json:1>)
- `Observed effect`:
  - batch 10:
    - `document_type_accuracy = 0.0`
    - `positive_field_f1 = 0.6857`
    - `exact_f1 = 0.3934`
    - `unavailable_hallucination_rate = 0.3333`
  - batch 11:
    - `document_type_accuracy = 0.4`
    - `positive_field_f1 = 0.48`
    - `exact_f1 = 0.2759`
    - `unavailable_hallucination_rate = 0.5333`
  - combined over these 10 docs:
    - `document_type_accuracy = 0.2`
    - `positive_field_tp = 18`, `fp = 9`, `fn = 15`, `positive_field_f1 = 0.6`
    - `unavailable_field_count = 27`, `unavailable_hallucination_count = 12`, `unavailable_hallucination_rate = 0.4444`
  - the repaired contract is visible:
    - DAE now emits OCR-derived semantic/structural state for these FUNSD scans instead of `text_density = 0`
    - extraction plans now contain `JOB CONTEXT` and `ANALYSIS CONTEXT`
    - specialist policy selection appears in the plan for some form/correspondence pages
- `Claim impact`:
  - this is meaningful runtime evidence that the state/context plumbing repair is real
  - it improves field extraction quality on form-heavy slices
  - it still does not fix the core `document_type` problem well enough for a strong mixed-family claim
- `Risk`:
  - batch 10 and batch 11 were launched concurrently under the same benchmark job and collided on the same benchmark run id `benchmark_1777424388`
  - only one benchmark report survived cleanly, so this 10-doc continuation is operational evidence, not clean paper-grade benchmark evidence
  - one feedback write also failed with a file-access error during the collision
- `Next action`:
  - rerun batch 10 and batch 11 sequentially under the same job if we want clean benchmark evidence from this repaired runtime

### Entry 12: New sequential batch 12 after repair shows context wiring works but AHMN learning still does not

- `Date`: 2026-04-29
- `Change`:
  - ran one new unseen adaptive-only batch under the same ongoing benchmark job `d8b862c1c9944facbe0482d39cc26450`
  - processed batch 12 sequentially to avoid the earlier benchmark-run collision
- `Evidence`:
  - benchmark report:
    - [benchmark_1777424865/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777424865/paper_evidence.json:1>)
  - adaptive run:
    - [adaptive_safe_batch_1777424865275](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424865275>)
  - AHMN state after the run:
    - [job_bench_benchmark_1777416388_adaptive_safe.json](</E:/Research Project/Code/idpo-data/ahmn/direct_advisor/job_bench_benchmark_1777416388_adaptive_safe.json:1>)
  - representative repaired artifact chain:
    - [schema_funsd_test_86075409_5410 dae/output.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424865275/docs/schema_funsd_test_86075409_5410/dae/output.json:1>)
    - [schema_funsd_test_86075409_5410 plan/primary.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424865275/docs/schema_funsd_test_86075409_5410/plan/primary.json:1>)
    - [schema_funsd_test_86075409_5410 extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424865275/docs/schema_funsd_test_86075409_5410/structuring/extracted.json:1>)
    - [schema_funsd_test_86075409_5410 validation/results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777424865275/docs/schema_funsd_test_86075409_5410/validation/results.json:1>)
- `Observed effect`:
  - batch 12 metrics:
    - `document_type_accuracy = 0.0`
    - `positive_field_f1 = 0.2963`
    - `exact_f1 = 0.1231`
    - `unavailable_hallucination_rate = 0.125`
    - `validation_pass_rate = 0.6`
    - `avg_latency_ms = 14118.35`
  - compared with batches 10 and 11:
    - positive extraction quality got worse
    - abstention quality got better
    - the system became more conservative, not more correct overall
  - context wiring is now real:
    - extraction plan contains `JOB CONTEXT (35 docs processed so far)`
    - extraction plan contains `ANALYSIS CONTEXT` and OCR noise guidance
  - job-context summary after 40 docs:
    - `document_type` success rate is only `0.189`
    - `document_date`, `issuer_name`, `recipient_name`, and `primary_organization` are near-perfect
    - this means the runtime is gathering the right failure evidence, but still not turning it into better `document_type` behavior
  - AHMN learning still appears broken:
    - `call_count` advanced from `32` to `37`
    - benchmark reports show `feedback_logged_count = 5`
    - but the persisted posterior values in the AHMN state file did not change
- `Interpretation`:
  - OCR is not the main failure on this slice; the OCR artifact clearly contains usable `From`, `To`, and date information
  - the dominant failure is semantic: the system routes many pages as `correspondence`, but the benchmark schema expects `document_type = form`
  - the current job context only warns that `document_type` is difficult; it does not help the extractor resolve the ontology mismatch
  - AHMN persistence works, but posterior updating still does not appear to work in practice on this path
- `Next action`:
  - audit and fix the AHMN feedback-to-posterior update path before interpreting any “online learning” claim from this benchmark

### Entry 13: Fixed cross-process direct-advisor feedback so benchmark exact scoring updates the correct scoped posterior

- `Date`: 2026-04-29
- `Change`:
  - audited the exact `feedback_logged -> direct_advisor` path and found a process-boundary bug
  - `process-inbox` issues AHMN advice in a child Python process, but benchmark exact feedback is logged later in the parent benchmark process
  - the direct advisor previously kept `advice_id -> scope_key` only in memory, so parent-side feedback could not recover the original job scope
  - added durable advice-scope persistence in [ahmn_core/direct_advisor.py](</E:/Research Project/Code/IDPO/ahmn_core/direct_advisor.py:1>) so later feedback can restore the correct scoped posterior even after reload/process exit
  - added a direct advisor regression test in [ahmn_core/tests/test_direct_advisor.py](</E:/Research Project/Code/IDPO/ahmn_core/tests/test_direct_advisor.py:1>)
  - added an exact benchmark feedback regression in [idpo/tests/test_research_features.py](</E:/Research Project/Code/IDPO/idpo/tests/test_research_features.py:1>)
- `Root cause`:
  - child process: `get_advice()` populated `_advice_scopes` and wrote scoped state
  - parent process: `_log_exact_benchmark_feedback()` imported `ahmn_core.direct_advisor` fresh and called `log_outcome()`
  - fresh import meant `_advice_scopes` was empty, so `log_outcome()` fell back to the active/default scope and updated the wrong state file
  - this is why benchmark reports showed `feedback_logged_count > 0` while the intended job-scoped posterior file did not change
- `Expected effect`:
  - benchmark exact feedback should now mutate the same job-scoped posterior state that produced the advice
  - `call_count` and posterior alpha/beta should finally move together on future online-learning batches
- `Next action`:
  - run targeted tests, then rerun a narrow adaptive batch and verify the job-scoped AHMN posterior file changes after exact feedback is logged

### Entry 14: Batch 13 confirms scoped Thompson Sampling updates are now happening in real benchmark runs

- `Date`: 2026-04-29
- `Change`:
  - ran the next adaptive-only schema batch under the existing benchmark job `d8b862c1c9944facbe0482d39cc26450`
  - used the repaired direct-advisor feedback path without changing the runtime architecture
- `Evidence`:
  - benchmark report:
    - [benchmark_1777426156/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777426156/paper_evidence.json:1>)
  - scoped AHMN state before/after:
    - [job_bench_benchmark_1777416388_adaptive_safe.json](</E:/Research Project/Code/idpo-data/ahmn/direct_advisor/job_bench_benchmark_1777416388_adaptive_safe.json:1>)
- `Observed effect`:
  - `call_count` advanced from `37` to `42`
  - scoped posteriors also changed, which is the key confirmation:
    - `default`: beta `1.0 -> 2.0`
    - `fast_local_text`: beta `1.0 -> 2.0`
    - `receipt_specialist`: beta `1.0 -> 4.0`
  - this is the first clean evidence in the benchmark path that logged feedback is mutating the intended job-scoped Thompson Sampling state rather than only advancing `call_count`
  - batch 13 metrics:
    - `document_type_accuracy = 0.4`
    - `positive_field_f1 = 0.3636`
    - `exact_f1 = 0.2`
    - `unavailable_hallucination_rate = 0.5556`
    - `validation_pass_rate = 0.0`
    - `feedback_logged_count = 5`
  - job context after 45 docs:
    - `document_type` success rate improved slightly to `0.238`
    - `document_date = 0.972`
    - `issuer_name = 1.0`
    - `recipient_name = 1.0`
    - `primary_organization = 1.0`
    - `total_amount = 0.875`
    - `reference_id = 0.727`
- `Interpretation`:
  - Thompson Sampling persistence and posterior updating now work in the actual benchmark execution path
  - job context gathering still works and continues to highlight `document_type` as the main chronic failure
  - learning is now mechanically real, but extraction quality remains mixed and validation still fails across the full batch
- `Next action`:
  - continue with the next adaptive batch, but evaluate improvement per field and per policy family rather than relying on a single averaged score

### Entry 15: Batches 14 and 15 show real TS updating but highly non-stationary extraction quality

- `Date`: 2026-04-29
- `Change`:
  - continued sequential adaptive-only benchmarking on the same job after confirming scoped posterior updates now work
  - processed batch 14 and batch 15 under `d8b862c1c9944facbe0482d39cc26450`
- `Evidence`:
  - batch 14 report:
    - [benchmark_1777426495/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777426495/paper_evidence.json:1>)
  - batch 15 report:
    - [benchmark_1777426680/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777426680/paper_evidence.json:1>)
  - updated scoped AHMN state:
    - [job_bench_benchmark_1777416388_adaptive_safe.json](</E:/Research Project/Code/idpo-data/ahmn/direct_advisor/job_bench_benchmark_1777416388_adaptive_safe.json:1>)
- `Observed effect`:
  - batch 14 was poor:
    - `document_type_accuracy = 0.2`
    - `positive_field_f1 = 0.0`
    - `exact_f1 = 0.0312`
    - `unavailable_hallucination_rate = 0.7647`
    - policies used: `correspondence_specialist` x2, `default` x1, `receipt_specialist` x2
  - batch 15 was materially better:
    - `document_type_accuracy = 0.8`
    - `positive_field_f1 = 0.8`
    - `exact_f1 = 0.2909`
    - `unavailable_hallucination_rate = 0.4`
    - policies used: `default` x2, `receipt_fast_local` x1, `receipt_specialist` x2
  - Thompson Sampling state continued to update in the correct scoped file:
    - after batch 14:
      - `correspondence_specialist` beta `1.0 -> 3.0`
      - `default` beta `2.0 -> 3.0`
      - `receipt_specialist` beta `4.0 -> 6.0`
    - after batch 15:
      - `default` beta `3.0 -> 5.0`
      - `receipt_specialist` alpha/beta `3.0/6.0 -> 4.0/7.0`
      - new `receipt_fast_local` prior was initialized and then updated to `2.5/1.0`
  - job context after 55 docs:
    - `document_type = 0.269`
    - `document_date = 0.886`
    - `issuer_name = 1.0`
    - `recipient_name = 1.0`
    - `primary_organization = 1.0`
    - `total_amount = 0.938`
    - `reference_id = 0.733`
- `Interpretation`:
  - the learning loop is now mechanically real and persistent
  - but quality is highly non-stationary across small 5-doc slices, so raw posterior movement alone is not enough evidence of useful adaptation
  - `document_type` remains the main systematic weakness even as several header fields are consistently strong
  - `receipt_specialist` is not simply “good” or “bad”; its outcomes are mixed enough that per-policy, per-family analysis is now more important than aggregate means
- `Next action`:
  - continue with the next batch and inspect whether the emerging `receipt_fast_local` arm continues to earn positive updates or was only a one-batch win

### Entry 16: Batches 16 and 17 strengthen the receipt-policy signal but do not fix validation or document-type globally

- `Date`: 2026-04-29
- `Change`:
  - continued sequential adaptive-only benchmarking with batch 16 and batch 17 on the same persistent job
- `Evidence`:
  - batch 16 report:
    - [benchmark_1777441099/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777441099/paper_evidence.json:1>)
  - batch 17 report:
    - [benchmark_1777441246/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777441246/paper_evidence.json:1>)
  - updated scoped AHMN state:
    - [job_bench_benchmark_1777416388_adaptive_safe.json](</E:/Research Project/Code/idpo-data/ahmn/direct_advisor/job_bench_benchmark_1777416388_adaptive_safe.json:1>)
- `Observed effect`:
  - batch 16:
    - `document_type_accuracy = 1.0`
    - `positive_field_f1 = 0.8`
    - `exact_f1 = 0.3158`
    - `unavailable_hallucination_rate = 0.48`
    - `rollback_count = 1`
    - `blocked_policy_count = 1`
    - policy distribution: `receipt_specialist` x5
  - batch 17:
    - `document_type_accuracy = 1.0`
    - `positive_field_f1 = 1.0`
    - `exact_f1 = 0.3509`
    - `unavailable_hallucination_rate = 0.48`
    - policy distribution: `receipt_fast_local` x2, `receipt_specialist` x3
  - scoped TS state after both batches:
    - `receipt_fast_local`: `2.5/1.0 -> 4.5/1.0`
    - `receipt_specialist`: `4.0/7.0 -> 10.0/9.0`
    - `default` remained at `1.5/5.0`
  - this means the newly emerged `receipt_fast_local` arm did not collapse; it accumulated additional positive evidence immediately
  - job context after 65 docs:
    - `document_type = 0.226`
    - `document_date = 0.75`
    - `issuer_name = 1.0`
    - `recipient_name = 1.0`
    - `primary_organization = 1.0`
    - `total_amount = 0.962`
    - `reference_id = 0.789`
- `Interpretation`:
  - on receipt-heavy slices, the current TS loop is now finding and reinforcing useful policy arms
  - however, the global `document_type` field remains weak across the full mixed job despite these strong receipt batches
  - `validation_pass_rate` stayed at `0.0` for both batches, so better exact extraction is still not enough to satisfy the validation contract
  - the system is learning something real now, but its benefit is slice-dependent rather than uniformly improving the mixed workload
- `Next action`:
  - continue with the next mixed batch and inspect whether the receipt-focused gains transfer outside the receipt-heavy regime or collapse again

### Entry 17: Batches 18 to 20 complete the staged sequence with stable receipt-policy behavior but persistent validation failure

- `Date`: 2026-04-29
- `Change`:
  - completed the remaining staged batches `18`, `19`, and `20` under the same persistent benchmark job
- `Evidence`:
  - batch 18 report:
    - [benchmark_1777441582/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777441582/paper_evidence.json:1>)
  - batch 19 report:
    - [benchmark_1777441699/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777441699/paper_evidence.json:1>)
  - batch 20 report:
    - [benchmark_1777441823/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777441823/paper_evidence.json:1>)
  - final scoped AHMN state:
    - [job_bench_benchmark_1777416388_adaptive_safe.json](</E:/Research Project/Code/idpo-data/ahmn/direct_advisor/job_bench_benchmark_1777416388_adaptive_safe.json:1>)
- `Processed files`:
  - batch 18:
    - `schema_cord_validation_0016` -> [cord_validation_0016.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0016.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441582385/docs/schema_cord_validation_0016/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441582385/docs/schema_cord_validation_0016/validation/results.json:1>)
    - `schema_cord_validation_0017` -> [cord_validation_0017.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0017.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441582385/docs/schema_cord_validation_0017/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441582385/docs/schema_cord_validation_0017/validation/results.json:1>)
    - `schema_cord_validation_0018` -> [cord_validation_0018.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0018.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441582385/docs/schema_cord_validation_0018/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441582385/docs/schema_cord_validation_0018/validation/results.json:1>)
    - `schema_cord_validation_0019` -> [cord_validation_0019.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0019.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441582385/docs/schema_cord_validation_0019/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441582385/docs/schema_cord_validation_0019/validation/results.json:1>)
    - `schema_cord_validation_0020` -> [cord_validation_0020.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0020.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441582385/docs/schema_cord_validation_0020/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441582385/docs/schema_cord_validation_0020/validation/results.json:1>)
  - batch 19:
    - `schema_cord_validation_0021` -> [cord_validation_0021.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0021.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441699998/docs/schema_cord_validation_0021/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441699998/docs/schema_cord_validation_0021/validation/results.json:1>)
    - `schema_cord_validation_0022` -> [cord_validation_0022.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0022.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441699998/docs/schema_cord_validation_0022/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441699998/docs/schema_cord_validation_0022/validation/results.json:1>)
    - `schema_cord_validation_0023` -> [cord_validation_0023.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0023.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441699998/docs/schema_cord_validation_0023/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441699998/docs/schema_cord_validation_0023/validation/results.json:1>)
    - `schema_cord_validation_0024` -> [cord_validation_0024.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0024.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441699998/docs/schema_cord_validation_0024/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441699998/docs/schema_cord_validation_0024/validation/results.json:1>)
    - `schema_cord_validation_0025` -> [cord_validation_0025.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0025.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441699998/docs/schema_cord_validation_0025/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441699998/docs/schema_cord_validation_0025/validation/results.json:1>)
  - batch 20:
    - `schema_cord_validation_0026` -> [cord_validation_0026.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0026.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441823866/docs/schema_cord_validation_0026/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441823866/docs/schema_cord_validation_0026/validation/results.json:1>)
    - `schema_cord_validation_0027` -> [cord_validation_0027.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0027.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441823866/docs/schema_cord_validation_0027/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441823866/docs/schema_cord_validation_0027/validation/results.json:1>)
    - `schema_cord_validation_0028` -> [cord_validation_0028.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0028.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441823866/docs/schema_cord_validation_0028/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441823866/docs/schema_cord_validation_0028/validation/results.json:1>)
    - `schema_cord_validation_0029` -> [cord_validation_0029.png](</E:/Research Project/Code/IDPO/datasets/derived/cord_validation_100_seed17/images/cord_validation_0029.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441823866/docs/schema_cord_validation_0029/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441823866/docs/schema_cord_validation_0029/validation/results.json:1>)
    - `schema_funsd_train_0000990274` -> [0000990274.png](</E:/Research Project/Code/IDPO/datasets/FUNSD/training_data/images/0000990274.png>)
      extraction: [extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441823866/docs/schema_funsd_train_0000990274/structuring/extracted.json:1>)
      validation: [results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777441823866/docs/schema_funsd_train_0000990274/validation/results.json:1>)
- `Observed effect`:
  - batch 18:
    - `document_type_accuracy = 1.0`
    - `positive_field_f1 = 0.6`
    - `exact_f1 = 0.2807`
    - `unavailable_hallucination_rate = 0.48`
    - policy distribution: `receipt_specialist` x4, `fast_local_text` x1
  - batch 19:
    - `document_type_accuracy = 1.0`
    - `positive_field_f1 = 0.6`
    - `exact_f1 = 0.2963`
    - `unavailable_hallucination_rate = 0.36`
    - policy distribution: `receipt_specialist` x4, `fast_local_text` x1
  - batch 20:
    - `document_type_accuracy = 0.8`
    - `positive_field_f1 = 0.6667`
    - `exact_f1 = 0.2963`
    - `unavailable_hallucination_rate = 0.3333`
    - policy distribution: `receipt_specialist` x3, `correspondence_specialist` x1, `scanned_text` x1
  - scoped TS state at the end:
    - `call_count = 77`
    - `receipt_specialist = 14.0 / 16.0`
    - `receipt_fast_local = 4.5 / 1.0`
    - `fast_local_text = 2.0 / 3.0`
    - `correspondence_specialist = 4.0 / 3.0`
    - `scanned_text = 1.5 / 2.0`
  - job context after the full staged continuation:
    - `document_type = 0.195`
    - `document_date = 0.625`
    - `issuer_name = 1.0`
    - `recipient_name = 1.0`
    - `primary_organization = 1.0`
    - `total_amount = 0.975`
    - `reference_id = 0.84`
- `Interpretation`:
  - Thompson Sampling remained stable through the end of the staged continuation and continued to update the correct scoped state
  - receipt-focused policy behavior looks genuinely learnable now; `receipt_specialist` and `receipt_fast_local` both hold meaningful positive mass rather than collapsing immediately
  - however, `validation_pass_rate` stayed at `0.0` across batches `18` to `20`, so the extraction/validation contract is still not aligned well enough for a strong end-to-end claim
  - the field-level picture is now uneven but clear:
    - strong: `issuer_name`, `recipient_name`, `primary_organization`, `total_amount`, `reference_id`
    - weak: `document_type`
    - degraded over the longer run: `document_date`
  - there is also a run-accounting inconsistency:
    - the frontend benchmark job showed `doc_count = 75` after batch `20`
    - but job-context aggregation reported `doc_count = 80`
    - that mismatch weakens evidence traceability and should be treated as a real bookkeeping bug until reconciled
- `Next action`:
  - stop adding more sequential batches and audit why validation still fails even on receipt-heavy slices with good exact-field performance

### Entry 18: General validation and normalization contract fix materially improves batch-20 validation without dataset-specific logic

- `Date`: 2026-04-29
- `Change`:
  - implemented a general contract fix across:
    - [idpo/agents/validation.py](</E:/Research Project/Code/IDPO/idpo/agents/validation.py:1>)
    - [idpo/agents/extraction_rules.py](</E:/Research Project/Code/IDPO/idpo/agents/extraction_rules.py:1>)
    - [configs/idpo_research_config.json](</E:/Research Project/Code/IDPO/configs/idpo_research_config.json:74>)
    - [configs/config.json](</E:/Research Project/Code/IDPO/configs/config.json:74>)
  - changed validation to normalize dates into canonical `YYYY-MM-DD` before pattern checks
  - added field-aware document-type grounding so categorical predictions can be supported by analysis metadata instead of raw token matching alone
  - tightened generic regex fallback so plain OCR words are not promoted into `reference_id` or `document_date`, and identifier fallback now requires a real alphanumeric ID shape with digits
- `Evidence`:
  - targeted tests:
    - [idpo/tests/test_pipeline_tuning_upgrades.py](</E:/Research Project/Code/IDPO/idpo/tests/test_pipeline_tuning_upgrades.py:1>)
    - [idpo/tests/test_extraction_enhancements.py](</E:/Research Project/Code/IDPO/idpo/tests/test_extraction_enhancements.py:1>)
  - fresh smoke benchmark after the fix:
    - [benchmark_1777442871/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777442871/paper_evidence.json:1>)
- `Observed effect`:
  - on the fresh batch-20 smoke run:
    - `validation_pass_rate` improved from `0.0` to `0.6`
    - `unavailable_hallucination_rate` improved from `0.3333` in the earlier batch-20 continuation slice to `0.1667`
    - `document_type_accuracy = 0.6`
    - `positive_field_f1 = 0.5`
  - per-doc evidence from the smoke run:
    - `schema_cord_validation_0026` passed validation with no issues
    - `schema_cord_validation_0028` passed validation with no issues
    - `schema_cord_validation_0029` passed validation with no issues
    - `schema_funsd_train_0000990274` no longer fails on natural-language date format; the remaining issue is `document_type: ungrounded_value`
    - remaining failures are now concentrated in `document_type`, not in the old date-format contract
- `Interpretation`:
  - this is a real strengthening of the end-to-end claim because the fix removed validator/normalizer brittleness rather than tuning to one dataset
  - the system still is not clean end to end, but some of the earlier “failures” were in fact contract bugs and are now gone
- `Next action`:
  - finish the general `document_type` contract alignment so categorical routing, extraction, and validation stop disagreeing on the same document

### Entry 19: Separate internal routing family from schema `document_type` in runtime metadata and extraction context

- `Date`: 2026-04-29
- `Change`:
  - made the internal routing family explicit as `routing_family` while preserving `semantic_doc_type` for compatibility
  - persisted `routing_family` through runtime metadata and per-document artifacts:
    - [idpo/agents/doc_analysis.py](</E:/Research Project/Code/IDPO/idpo/agents/doc_analysis.py:79>)
    - [idpo/pipeline/orchestrator.py](</E:/Research Project/Code/IDPO/idpo/pipeline/orchestrator.py:228>)
    - [idpo/pipeline/results.py](</E:/Research Project/Code/IDPO/idpo/pipeline/results.py:15>)
    - [idpo/pipeline/doc_artifacts.py](</E:/Research Project/Code/IDPO/idpo/pipeline/doc_artifacts.py:145>)
    - [idpo/pipeline/doc_records.py](</E:/Research Project/Code/IDPO/idpo/pipeline/doc_records.py:74>)
  - changed extraction context so internal routing signals are clearly marked as routing-only hints, while schema `document_type` remains constrained to `invoice | receipt | form | other`
    - [idpo/pipeline/planning.py](</E:/Research Project/Code/IDPO/idpo/pipeline/planning.py:558>)
  - updated validation so `document_type` grounding can use `routing_family` / `route_specialization` as support signals without treating them as schema labels
    - [idpo/agents/validation.py](</E:/Research Project/Code/IDPO/idpo/agents/validation.py:351>)
- `Evidence`:
  - [idpo/tests/test_research_features.py](</E:/Research Project/Code/IDPO/idpo/tests/test_research_features.py:664>)
  - [idpo/tests/test_pipeline_tuning_upgrades.py](</E:/Research Project/Code/IDPO/idpo/tests/test_pipeline_tuning_upgrades.py:137>)
  - [idpo/tests/test_storage_paths.py](</E:/Research Project/Code/IDPO/idpo/tests/test_storage_paths.py:126>)
- `Interpretation`:
  - the system already had richer internal families, but they were only implicit and easy to confuse with the public schema field
  - this change makes the separation explicit and auditable without widening the benchmark schema or adding a dataset-specific branch
- `Next action`:
  - rerun a mixed batch and verify that plan context, extracted `document_type`, and validation now disagree less often on correspondence-like pages

### Entry 20: Benchmark exact-feedback path now matches runtime AHMN channel selection order

- `Date`: 2026-04-29
- `Change`:
  - updated [scripts/run_idpo_benchmark.py](</E:/Research Project/Code/IDPO/scripts/run_idpo_benchmark.py:585>) so exact benchmark feedback no longer assumes direct-import only
  - benchmark feedback now uses the same channel order as runtime feedback:
    - HTTP AHMN service first when configured
    - direct-import fallback only when allowed and HTTP is unavailable
  - added focused parity coverage in [idpo/tests/test_research_features.py](</E:/Research Project/Code/IDPO/idpo/tests/test_research_features.py:2127>) for:
    - existing adaptive benchmark feedback via direct-import
    - scoped direct-advisor state update across reload
    - HTTP benchmark feedback posting
    - auto-mode fallback from HTTP to direct-import
- `Evidence`:
  - `python -m pytest idpo/tests/test_research_features.py -k "run_benchmark_logs_exact_feedback_for_adaptive_docs or benchmark_exact_feedback_updates_scoped_direct_advisor_state_across_reload or benchmark_exact_feedback_posts_http_when_mode_is_http or benchmark_exact_feedback_auto_falls_back_to_direct_import_when_http_unreachable" -v`
  - `python -m pytest idpo/tests/test_research_features.py -k "pipeline_posts_ahmn_feedback_after_execution" -v`
- `Interpretation`:
  - this removes one major source of architectural drift between benchmark feedback and runtime feedback
  - the benchmark path can now talk to the full AHMN service through the same log contract as runtime
  - however, this is transport-contract parity, not full reward parity
  - the direct-import stub still receives a precomputed scalar reward, while the full service still recomputes blended reward from metrics at `/advice/log`
- `Next action`:
  - add a narrow service-parity test around reward semantics before running a fresh 5-document service-backed benchmark job

### Entry 21: Service-backed headline benchmark runs are now explicitly gated by a parity checklist

- `Date`: 2026-04-29
- `Change`:
  - added [docs/AHMN_SERVICE_PARITY_CHECKLIST.md](</E:/Research Project/Code/IDPO/docs/AHMN_SERVICE_PARITY_CHECKLIST.md:1>)
  - updated [docs/PROJECT_DIRECTION.md](</E:/Research Project/Code/IDPO/docs/PROJECT_DIRECTION.md:1>) so:
    - TS-stub stabilization remains allowed
    - headline service-backed benchmark runs are blocked until the checklist is complete
- `Checklist scope`:
  - reward semantics parity
  - advice/log contract parity
  - RABI activation check
  - DAAF update/forgetting check
  - mixed-slice `document_type` smoke run
  - evidence bookkeeping reconciliation
- `Interpretation`:
  - this is claim-protection cleanup, not architecture expansion
  - it reduces the chance of mixing service-path uncertainty into paper-facing results before the transport, reward, and evidence contracts are clear
- `Next action`:
  - keep stabilization work on the current TS-stub path and close the checklist items one by one before any service-backed headline run

### Entry 22: Fresh issue-discovery job started on the same 100-pack; learning confirmed batch-to-batch, not within batch

- `Date`: 2026-04-29
- `Fresh job`:
  - frontend benchmark job: [1684edcbb30041a5b7aea99312307dad.json](</E:/Research Project/Code/idpo-data/frontend/jobs/1684edcbb30041a5b7aea99312307dad.json:1>)
  - shared adaptive learning scope: `job_bench_benchmark_1777446248_adaptive_safe`
- `Batch 01 evidence`:
  - report: [benchmark_1777446248/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777446248/paper_evidence.json:1>)
  - result: `document_type_accuracy = 1.0`, `positive_field_f1 = 0.4286`, `exact_f1 = 0.3226`, `validation_pass_rate = 1.0`
  - policy distribution: `receipt_specialist x3`, `default x2`
- `Batch 02 evidence`:
  - report: [benchmark_1777446601/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777446601/paper_evidence.json:1>)
  - run: [adaptive_safe_batch_1777446601886](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777446601886>)
  - AHMN state: [ahmn_state.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777446601886/ahmn_state.json:1>)
  - result: `document_type_accuracy = 1.0`, `positive_field_f1 = 0.4091`, `exact_f1 = 0.3125`, `validation_pass_rate = 1.0`
  - policy distribution: `default x4`, `receipt_specialist x1`
- `Learning interpretation`:
  - benchmark exact feedback is logged only after the `process-inbox` run returns, so exact benchmark learning does not change docs inside the same 5-document batch
  - learning effect appears between batches on the same fresh job
  - after batches `01` and `02`, the scoped TS state moved to:
    - `default = alpha 2.5 / beta 2.0`
    - `receipt_specialist = alpha 3.0 / beta 4.0`
    - `call_count = 10`
  - this means the fresh job learned enough after batch `01` to shift batch `02` advice toward `default`
- `Obvious remaining issues after batch 02`:
  - invoice-family positive extraction is still weak on party fields:
    - `issuer_name` remains frequently missing
    - `recipient_name` and `primary_organization` are still often collapsed into the same organization
  - example: [schema_invoice_0005 extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777446601886/docs/schema_invoice_0005/structuring/extracted.json:1>)
    - extracted `recipient_name = Lowery LLC`
    - extracted `primary_organization = Lowery LLC`
    - `issuer_name` stayed missing
  - validation is no longer the main blocker on this invoice slice:
    - [schema_invoice_0005 validation/results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777446601886/docs/schema_invoice_0005/validation/results.json:1>) has `issues = []`
  - so the current weakness is more extraction semantics than validator brittleness on these first 10 docs
- `Paper implication`:
  - the fresh-job evidence supports a narrow claim that job-scoped TS adaptation is real and can change policy allocation across batches
  - it does not yet support a stronger claim that learning is clearly improving extraction quality on the invoice slice, because batch `02` quality stayed roughly flat while policy allocation shifted
- `Next action`:
  - continue to batch `03` on the same fresh job and inspect whether the policy shift away from `receipt_specialist` reduces invoice-field misses or just changes policy usage without quality gains

### Entry 23: Fresh issue-discovery continuation through batches 03 to 05 shows real TS adaptation but a clear collapse on the first DocVQA-heavy slices

- `Date`: 2026-04-29
- `Job`:
  - continued the same fresh adaptive job [1684edcbb30041a5b7aea99312307dad.json](</E:/Research Project/Code/idpo-data/frontend/jobs/1684edcbb30041a5b7aea99312307dad.json:1>)
- `Batch 03 evidence`:
  - report: [benchmark_1777447211/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777447211/paper_evidence.json:1>)
  - result: `document_type_accuracy = 1.0`, `positive_field_f1 = 0.3182`, `exact_f1 = 0.3125`, `validation_pass_rate = 1.0`
  - policy distribution: `default x4`, `receipt_specialist x1`
- `Batch 04 evidence`:
  - report: [benchmark_1777447475/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777447475/paper_evidence.json:1>)
  - run: [adaptive_safe_batch_1777447476012](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777447476012>)
  - first mixed slice with `4` invoices and `1` DocVQA `other`
  - result: `document_type_accuracy = 0.6`, `positive_field_f1 = 0.0`, `exact_f1 = 0.1034`, `unavailable_hallucination_rate = 0.75`
  - policy distribution: `default x3`, `receipt_specialist x1`, `scanned_text x1`
- `Batch 05 evidence`:
  - report: [benchmark_1777447738/paper_evidence.json](</E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777447738/paper_evidence.json:1>)
  - run: [adaptive_safe_batch_1777447738208](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777447738208>)
  - DocVQA `other` slice
  - result: `document_type_accuracy = 0.8`, `positive_field_f1 = 0.2`, `exact_f1 = 0.1667`, `unavailable_hallucination_rate = 0.6667`, `validation_pass_rate = 0.2`
  - policy distribution: `correspondence_specialist x2`, `default x2`, `receipt_specialist x1`
- `Learning state after 25 docs`:
  - [ahmn_state.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777447738208/ahmn_state.json:1>)
  - `call_count = 25`
  - `default = alpha 3.5 / beta 12.0`
  - `receipt_specialist = alpha 3.0 / beta 7.0`
  - `correspondence_specialist = alpha 3.0 / beta 1.0`
  - `scanned_text = alpha 1.5 / beta 2.0`
- `Interpretation`:
  - TS adaptation is real and policy mass is moving
  - but the fresh-job evidence now shows a sharp transition:
    - invoice-heavy batches `01` to `03` remained weak but stable
    - the first mixed and DocVQA-heavy slices `04` and `05` exposed major unsupported-field hallucination and low positive extraction quality
  - the learner is not yet showing clear cross-family quality improvement; it is exploring policy changes, but the extraction pipeline still breaks on sparse `other` documents
- `Representative failure`:
  - [schema_docvqa_5232 extracted.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777447738208/docs/schema_docvqa_5232/structuring/extracted.json:1>)
  - [schema_docvqa_5232 validation/results.json](</E:/Research Project/Code/idpo-data/runs/adaptive_safe_batch_1777447738208/docs/schema_docvqa_5232/validation/results.json:1>)
  - current behavior is more conservative than the earlier pre-fix failures, but still weak:
    - `document_type = other` is correct
    - `document_date = 5-6/01` still survives regex fallback and fails validation
    - `reference_id` still prefers an OCR code (`DUROJ012-001293`) over the expected title-like anchor
    - `issuer_name` and `primary_organization` collapse to the same noisy string
- `Paper implication`:
  - after 25 fresh documents, the strongest defensible claim remains:
    - job-scoped TS adaptation is real and auditable
    - policy allocation changes across batches
    - mixed-document extraction quality remains uneven and fails sharply on sparse `other` slices
  - this does not yet support a stronger “adaptive learning improves heterogeneous extraction quality” claim
- `Next action`:
  - stop extending the fresh job blindly and fix the remaining general fallback/field-semantics issues for sparse `other` documents before continuing to the next unseen slice

### Entry 24: Benchmark exact supervision is now a real post-extraction review artifact and the learning signal now comes from reviewed exact F1

- `Date`: 2026-04-29
- `Change`:
  - updated [scripts/run_idpo_benchmark.py](</E:/Research Project/Code/IDPO/scripts/run_idpo_benchmark.py:1>) so each benchmarked adaptive document now gets an explicit post-extraction review result built from:
    - dataset expected values
    - normalized extracted values
    - exact `tp/fp/fn/precision/recall/f1`
    - field-level reviewed states
  - the benchmark now writes a per-document review artifact to:
    - `runs/<run_id>/docs/<doc_id>/review/results.json`
  - adaptive learning now uses the reviewed signal directly:
    - HTTP AHMN mode posts benchmark review payloads to `/advice/review`
    - direct-import TS mode falls back to reviewed exact `f1` instead of the old schema proxy reward
- `Why this matters`:
  - previously the benchmark already *displayed* `human_reviewed`, but learning still went through a separate proxy reward path
  - that was weaker than the intended research contract because the expected-value supervision that produced benchmark F1 was not the same signal driving adaptive feedback
  - after this change, the benchmark behaves more like delayed human validation:
    - extraction happens first
    - labeled expected values are applied after extraction
    - exact reviewed quality is persisted and fed back
- `Validation`:
  - targeted tests passed in [idpo/tests/test_research_features.py](</E:/Research Project/Code/IDPO/idpo/tests/test_research_features.py:1>) covering:
    - direct-import benchmark reviewed feedback
    - scoped direct-advisor update after reload
    - HTTP reviewed feedback posting to `/advice/review`
    - HTTP failure fallback to direct-import reviewed F1
- `Important remaining risk`:
  - this improves *benchmark supervision integrity*, but it does not fully close service/stub parity
  - the TS stub still reduces reviewed F1 to a binary posterior success/failure threshold, while the full AHMN service uses continuous `alpha/beta` review deltas
  - so the benchmark now uses the right source of supervision in both paths, but the update mechanics are still not identical
- `Next action`:
  - continue TS-stub stabilization with this corrected reviewed-learning contract, and keep the service-backed headline benchmark gated until the remaining parity checklist items are closed
