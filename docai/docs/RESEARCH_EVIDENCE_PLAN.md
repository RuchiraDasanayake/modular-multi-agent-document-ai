# DocAI v2 Research Evidence Plan

Status: Current  
Last updated: 2026-03-15

## Purpose

Define how DocAI v2 will collect paper-ready evidence from system runs.

The goal is to ensure that benchmark results, training runs, production runs, validation outcomes, recovery outcomes, and policy assignment behavior are recorded in a reproducible way.

## Evidence Principle

Research evidence must come from actual system artifacts, not manually reconstructed claims.

Every experiment should be reproducible from stored configs, schemas, job context, artifacts, expected values, and metrics.

## Required Evidence Per Job

Each job should preserve:
- job_context.json
- schema snapshot
- project context snapshot
- document list
- run type
- model/OCR configuration
- policy assignment summary
- extracted data export
- metrics_report.json
- run_log.jsonl

## Required Evidence Per Document

Each document should preserve:
- original file reference
- document_profile.json
- selected_policy.json
- run_plan.json
- ocr_output.json
- extracted_output.json
- validation_report.json
- recovery_report.json
- final_output.json
- expected_output.json if reviewed

## Required Experiment Metadata

Every benchmark/experiment should record:
- experiment_id
- date
- dataset name
- dataset source
- document count
- schema version
- run mode
- baseline or proposed system
- OCR/parser used
- model used
- policy mode
- reviewer if human review was used

## Baselines To Support Later

The system should later support:
- fixed_ocr_llm
- static_policy
- policy_driven
- policy_driven_with_learning

## Metrics To Export

Export:
- precision
- recall
- F1
- field accuracy
- table row accuracy
- grounding coverage
- validation pass rate
- recovery success rate
- needs review rate
- latency
- policy distribution

## Paper-Ready Outputs

The system should later export:
- per_document_results.csv
- per_field_results.csv
- per_table_results.csv
- policy_assignment_summary.csv
- policy_leaderboard.csv
- error_analysis.json
- paper_tables.json
- paper_tables.tex

## Error Analysis

Track:
- missing fields
- wrong values
- hallucinated values
- not grounded values
- failed table rows
- OCR failures
- validation failures
- recovery failures
- human correction count

## Research Claim Support

This evidence should support claims such as:
- policy-driven extraction improves over fixed OCR+LLM
- reviewed training runs improve later production runs
- per-document policy assignment improves heterogeneous document batches
- validation/recovery reduces unsupported outputs
- policy learning reduces review workload
- time and resource savings
- better accuracy
- lower cost
- easier operation
- better configurability

Also explicitly call out technology limits whenever they affect results, including limits from OCR engines, local model quality, hardware constraints, runtime latency, and parser capability gaps.

## Rule

If a claim cannot be traced to artifacts or metrics, it should not appear in the paper.

Keep this document clear and practical.
