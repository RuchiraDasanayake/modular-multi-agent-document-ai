# DocAI v2 Contracts

## 1. Purpose

Contracts define the standard data shapes passed between system components.

The goal is to keep the system:
- simple
- traceable
- testable
- reviewable
- benchmark-ready
- learning-ready later

Every major step in the pipeline must produce a clear contract/output.

## 2. Naming Principle

Use product-friendly names.

Use these terms:
- Project
- ExtractionSchema
- Field
- Table
- Column
- Job
- Document
- DocumentProfile
- AvailableTools
- SelectedPolicy
- RunPlan
- OCROutput
- ExtractedOutput
- FieldOutput
- TableOutput
- RowOutput
- ValidationReport
- RecoveryReport
- FinalOutput
- ExpectedOutput
- MetricsReport
- LearningRecord

Avoid over-engineered names unless absolutely necessary.

The UI should use simple terms:
- Fields
- Tables
- Columns
- Rows
- Expected Values
- Review
- Metrics

## 3. Project

Purpose:  
A Project groups related extraction work.

Fields:
- project_id
- name
- description
- created_at
- updated_at

Why important:  
Projects keep schemas, jobs, documents, outputs, reviews, and metrics organized.

## 4. ExtractionSchema

Purpose:  
Defines the structured output the user wants from documents.

It can include:
- simple fields
- repeatable tables

Fields:
- schema_id
- project_id
- name
- description
- version
- fields
- tables
- created_at
- updated_at

Why important:  
This is the user-defined target structure. The system extracts documents into this schema.

## 5. Field

Purpose:  
A single value to extract from a document.

Examples:
- vendor_name
- invoice_date
- total_amount
- patient_name
- claim_id

Fields:
- field_id
- name
- description
- type
- required
- examples
- validation_rules

Why important:  
Field descriptions guide extraction. Field types and validation rules help detect bad outputs.

## 6. Table

Purpose:  
A repeatable set of rows to extract from a document.

Examples:
- line_items
- service_lines
- payment_adjustments

Fields:
- table_id
- name
- description
- columns
- required
- validation_rules

Why important:  
Tables preserve relationships between repeated values. This is needed for invoices, claims, EOBs, receipts, and forms.

## 7. Column

Purpose:  
A field inside a table row.

Examples:  
For invoice line_items:
- description
- quantity
- unit_price
- line_total

For RCM service_lines:
- date_of_service
- cpt_code
- modifier
- units
- charge_amount

Fields:
- column_id
- name
- description
- type
- required
- examples
- validation_rules

Why important:  
Columns let users define what each row should contain.

## 8. Job

Purpose:  
A Job is a processing run inside a project.

Fields:
- job_id
- project_id
- schema_id
- name
- status
- run_mode
- created_at
- started_at
- completed_at

Run modes may later include:
- fixed_ocr_llm
- static_policy
- policy_driven
- adaptive_learning

Why important:  
Jobs make document processing trackable and reproducible.

## 9. Document

Purpose:  
Represents one uploaded file inside a job.

Fields:
- document_id
- job_id
- original_filename
- file_path
- status
- page_count
- uploaded_at
- profile

Why important:  
Each document needs its own lifecycle, artifacts, result, review status, and metrics.

## 10. DocumentProfile

Purpose:  
Stores what the system detects about a document before extraction.

Fields:
- document_id
- detected_type
- layout_type
- quality_bin
- language
- content_profile
- risk_flags
- signals

Examples:
- detected_type: invoice
- layout_type: table_heavy
- quality_bin: low
- content_profile: financial
- risk_flags: low_contrast, rotated, noisy_scan

Why important:  
The profile helps choose policies, OCR settings, preprocessing, extraction strategy, and recovery behavior.

## 11. AvailableTools

Purpose:  
Lists what OCR engines, parsers, models, validators, and recovery strategies are available at runtime.

Fields:
- available_ocr_engines
- available_parsers
- available_models
- available_validators
- available_recovery_strategies

Each tool should include:
- tool_id
- tool_type
- capabilities
- enabled
- unavailable_reason if disabled

Example capabilities:
- text_output
- bbox_output
- confidence_scores
- table_detection
- reading_order
- json_output
- long_context

Why important:  
Policies must only use tools that are actually available and compatible.

## 12. SelectedPolicy

Purpose:  
Stores which policy was selected and why.

Fields:
- policy_id
- policy_family
- policy_version
- selected_by
- confidence
- reasons
- disabled_candidates

disabled_candidates should include:
- policy_id
- reason_disabled

Why important:  
This makes policy behavior explainable and debuggable.

## 13. RunPlan

Purpose:  
Defines exactly how a document will be processed.

Inputs:
- ExtractionSchema
- DocumentProfile
- AvailableTools
- SelectedPolicy

Fields:
- plan_id
- document_id
- schema_id
- policy_id
- preprocessing_steps
- ocr_config
- parser_config
- model_config
- fields_to_extract
- tables_to_extract
- validation_rules
- recovery_rules

Why important:  
The RunPlan turns a policy into concrete runtime behavior.

## 14. OCROutput

Purpose:  
Stores OCR or parser output.

Fields:
- document_id
- engine_id
- text
- pages
- blocks
- tables_detected
- confidence
- artifact_paths

Pages may include:
- page_number
- text
- blocks

Blocks may include:
- text
- bbox
- confidence

Why important:  
OCR output is the evidence source for extraction, validation, and review.

## 15. ExtractedOutput

Purpose:  
Stores extracted fields and tables before final approval.

Fields:
- document_id
- schema_id
- policy_id
- fields
- tables
- artifact_paths

Why important:  
This is the system’s raw structured extraction result before or during validation/review.

## 16. FieldOutput

Purpose:  
Stores one extracted field value.

Fields:
- field_name
- value
- normalized_value
- confidence
- evidence_text
- evidence_location
- extraction_method
- validation_status
- issues

Why important:  
Each extracted value must be inspectable and reviewable.

## 17. TableOutput

Purpose:  
Stores one extracted table.

Fields:
- table_name
- rows
- confidence
- validation_status
- issues

Why important:  
Tables are needed for repeated structures such as invoice line items and claim service lines.

## 18. RowOutput

Purpose:  
Stores one extracted table row.

Fields:
- row_index
- columns
- evidence_text
- evidence_location
- confidence
- validation_status
- issues

Why important:  
Rows preserve relationships between columns.

Example:  
CPT code 99213 must stay connected to its correct date, units, and charge amount.

## 19. ValidationReport

Purpose:  
Stores validation results.

Fields:
- document_id
- field_issues
- table_issues
- document_issues
- pass_status
- summary

Validation should support:
- required field checks
- required column checks
- grounding checks
- type checks
- pattern checks
- numeric checks
- date checks
- table consistency checks
- document-level consistency checks

Why important:  
Validation tells the user and system whether the extraction can be trusted.

## 20. RecoveryReport

Purpose:  
Stores recovery attempts after validation failures.

Fields:
- document_id
- attempted
- recovered_fields
- recovered_table_rows
- failed_items
- strategies_used
- summary

Recovery strategies may include:
- field retry
- table row retry
- OCR retry
- region retry
- alternate model/parser fallback
- fallback to N/A
- human review

Why important:  
Recovery must be targeted and traceable.

## 21. FinalOutput

Purpose:  
The final structured output for a document.

Fields:
- document_id
- schema_id
- policy_id
- fields
- tables
- validation_report
- recovery_report
- quality_summary
- artifact_paths

Why important:  
This is the result users export as JSON or CSV.

## 22. ExpectedOutput

Purpose:  
Stores correct values for review, benchmarking, and learning.

Fields:
- document_id
- expected_fields
- expected_tables
- source
- reviewed_by
- reviewed_at

Sources may include:
- manual_review
- uploaded_labels
- benchmark_dataset
- correction

Why important:  
ExpectedOutput allows the system to calculate accuracy and learn from corrections.

## 23. MetricsReport

Purpose:  
Stores evaluation metrics for a document or job.

Fields:
- job_id
- document_id optional
- precision
- recall
- f1
- field_accuracy
- table_accuracy
- grounding_coverage
- validation_pass_rate
- recovery_success_rate
- latency_ms
- policy_id

Why important:  
Metrics make the system benchmark-ready and research-ready.

## 24. LearningRecord

Purpose:  
Stores a clean event for future policy learning.

Fields:
- learning_record_id
- document_id
- schema_id
- policy_id
- metrics
- validation_summary
- recovery_summary
- human_corrections
- created_at

Why important:  
Learning should be based on clean records, not hidden side effects.

Full AHMN learning is later, but the system must produce learning-ready records from the start.

## 25. Required Rules

Add these contract rules:

- Every document must have a DocumentProfile.
- Every run must have a SelectedPolicy.
- Every run must have a RunPlan.
- Every run must save OCROutput, even if OCR fails.
- Every extracted field should include evidence when possible.
- Every extracted table row should preserve column relationships.
- Failed fields and failed rows must have reasons.
- Human corrections must be stored as ExpectedOutput.
- Metrics must compare ExtractedOutput against ExpectedOutput when expected values exist.
- LearningRecord is created after metrics/review, but full learning comes later.
- Large raw outputs should be stored as artifacts, not directly in the database.
- Contracts should stay stable so UI, backend, benchmarks, and learning can rely on them.

Keep the document clear and practical.  
Do not make it overly academic.  
Do not add unrelated contracts such as billing, permissions, teams, or notifications.
