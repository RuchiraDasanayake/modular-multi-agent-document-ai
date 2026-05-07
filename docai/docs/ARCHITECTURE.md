# DocAI v2 Architecture

## 1. System Purpose

DocAI v2 converts unstructured documents into user-defined structured outputs.

Users define what they want extracted using:
- simple fields
- repeatable tables
- table columns with descriptions

The system processes batches of documents and fills those fields/tables using OCR, document parsing, LLM/VLM extraction, validation, recovery, and human review.

The goal is to support thousands of heterogeneous documents and convert them into structured JSON/CSV outputs, with realistic limitations.

## 2. Architecture Style

DocAI v2 starts as a modular monolith, not microservices.

It must be:
- simple to run locally
- simple to host
- simple to debug
- easy to monitor
- API-ready later
- benchmark-ready from the start

Components should be separated by modules and contracts, not by unnecessary infrastructure.

## 3. Product Flow

The UI is central.

User flow:

Project
? Extraction Schema
? Job
? Upload Documents
? Run Extraction
? Review Results
? Set/Correct Expected Values
? Export JSON/CSV
? View Metrics

This should feel like a modern document extraction orchestrator.

## 4. Real IDP Vocabulary

Use simple product terms inspired by enterprise IDP systems.

Use:
- Project
- Extraction Schema
- Field
- Table
- Column
- Job
- Document
- Review
- Expected Output
- Metrics
- Policy
- Artifact

Avoid overly academic wording in user-facing areas.

Internally, tables may be represented as repeating entities, but the UI should call them tables and rows.

## 5. Main Components

The system should contain these components:

- Web UI
- Backend API
- Job Orchestrator
- Database
- Artifact Store
- Schema Registry
- Policy Registry
- Capability Registry
- Policy Resolver
- Extraction Planner
- Document Preprocessor
- OCR / Document Parser Plugin Layer
- Layout / Table Parser
- Model / LLM / VLM Plugin Layer
- Field and Table Extractor
- Validator
- Recovery Engine
- Human Review Layer
- Result Assembler
- Metrics / Evaluation Engine
- Learning Engine later

## 6. Main Runtime Flow

Runtime flow:

User creates project
? user defines extraction schema
? user creates job
? user uploads documents
? orchestrator creates document profile
? capability registry checks available OCR/model/parser plugins
? policy resolver selects compatible policy
? extraction planner creates run plan
? preprocessing runs if needed
? OCR/document parser runs
? layout/table/reading-order signals are created if supported
? fields and table rows are extracted
? validation runs
? recovery runs if needed
? final structured output is saved
? user reviews/corrects fields and table rows
? expected output is saved
? metrics are calculated
? learning record is created later

## 7. Extraction Schema Model

The system converts documents into user-defined structured output.

The schema builder must support:

### Simple Fields

Example fields:
- vendor_name
- invoice_date
- total_amount
- patient_name
- claim_id

Each field must support:
- name
- description
- type
- required/optional
- examples
- validation rules

### Repeatable Tables

Tables are used when the document contains repeated rows.

Example: invoice line_items table

Columns:
- description: item or service description
- quantity: number of units
- unit_price: price per unit
- line_total: total amount for the row

Example: RCM service_lines table

Columns:
- date_of_service: service date
- cpt_code: CPT/procedure code
- modifier: CPT modifier
- units: number of units
- charge_amount: billed amount

Each table must support:
- table name
- table description
- columns
- column descriptions
- column types
- required/optional columns
- examples
- validation rules

In the UI, use:
- Fields
- Tables
- Columns
- Rows

In the backend, tables can be represented as repeating entities.

## 8. Document Preprocessing Layer

Preprocessing is a first-class step.

Policies may control:
- DPI
- image normalization
- denoising
- deskew
- rotation correction
- contrast enhancement
- binarization
- page splitting
- region cropping
- OCR retry preparation

The preprocessor must write artifacts showing what was changed.

## 9. OCR / Parser Architecture

OCR engines and document parsers must be plug-and-play.

Initial engines may include:
- Tesseract
- PaddleOCR
- PDF text extractor
- future PaddleOCR-VL or similar document parser
- future VLM parser

The system should support both plain OCR and richer document parsing.

Plain OCR returns:
- text
- optional confidence

Advanced parsers may return:
- text
- bounding boxes
- confidence scores
- layout blocks
- tables
- reading order
- Markdown
- JSON

## 10. Capability Architecture

Each OCR/parser/model plugin must declare its capabilities.

Example capabilities:
- text_output
- bbox_output
- confidence_scores
- table_detection
- reading_order
- multilingual
- handwritten_text
- layout_blocks
- markdown_output
- json_output
- long_context
- deterministic_generation

Policies can only use capabilities that the selected OCR/model/parser supports.

If a policy requires bounding boxes or table detection and the selected engine does not support it, that policy must be disabled with a clear reason.

## 11. Policy Architecture

Policies belong to families.

Initial policy families:
- invoice_extraction
- receipt_extraction
- form_extraction
- correspondence_extraction
- noisy_scan_rescue

Later policy families:
- rcm_claim_extraction
- eob_extraction
- long_pdf_extraction

Each family has policy variants.

A policy variant can control:
- preprocessing settings
- OCR/parser engine preference
- OCR/parser settings
- model preference
- prompt pack
- extraction mode
- validation strictness
- recovery strategy

Policies must be versioned configs.

Do not hardcode random policy names in Python.

Example policy variant behavior:
- invoice_basic_local_v1 uses normal OCR and simple field extraction
- invoice_table_heavy_local_v1 uses table-aware parsing and row extraction
- noisy_scan_rescue_v1 uses stronger preprocessing and OCR retry
- rcm_claim_service_line_v1 later extracts claim-level fields and service line tables

## 12. Extraction Planner

The Extraction Planner converts:

Extraction Schema
+ Document Profile
+ Selected Policy
+ Available Capabilities

into an executable run plan.

The plan should define:
- preprocessing steps
- OCR/parser engine
- OCR/parser settings
- model/provider
- prompt pack
- fields to extract
- tables to extract
- validation rules
- recovery rules
- artifact paths

## 13. Field and Table Extraction

The extractor must support:

- simple field extraction
- table row extraction
- column-level extraction
- field evidence
- table row evidence
- confidence
- raw model response storage

Every extracted value should include:
- value
- normalized value if applicable
- confidence
- evidence text
- evidence location if available
- extraction method
- validation status

## 14. Validation and Recovery

Validation must support:
- required field check
- required column check
- grounding against OCR/parser output
- type checks
- pattern checks
- numeric checks
- date checks
- table row consistency
- document-level consistency

Recovery must support:
- field retry
- table row retry
- region retry
- OCR retry with different preprocessing
- alternate parser/model fallback
- fallback to N/A
- human review if unresolved

Recovery should target the failed field/table row, not blindly rerun the whole document.

## 15. Storage Approach

Database stores:
- projects
- extraction schemas
- jobs
- documents
- policy definitions
- policy decisions
- review status
- result summaries
- expected output
- metrics

Artifact store stores:
- uploaded files
- preprocessed images
- OCR text
- OCR blocks
- layout/table outputs
- raw model responses
- run plans
- field outputs
- table row outputs
- validation reports
- recovery reports
- final JSON
- run logs

Do not store large raw artifacts directly in the database.

## 16. Human Review

The UI must allow users to:
- view extracted fields
- view extracted table rows
- compare extracted values with expected values
- correct wrong values
- mark missing values
- approve final outputs
- save expected output for benchmarking and learning

Human correction is a first-class signal.

## 17. Metrics and Benchmarking

The system must be benchmark-ready.

Metrics should support:
- precision
- recall
- F1
- field accuracy
- table row accuracy
- grounding coverage
- validation pass rate
- recovery success rate
- latency
- policy distribution

Benchmark mode should allow the same documents to run under different modes later:
- fixed OCR+LLM
- static policy
- policy-driven
- adaptive learning later

## 18. Learning Engine Later

Learning/AHMN is not part of the first implementation target.

Later, the Learning Engine can use:
- expected output
- human corrections
- validation outcomes
- recovery outcomes
- extraction metrics
- policy performance

to improve policy selection over time.

The first system must produce clean learning records, but does not need full learning yet.

## 19. API Exposure Later

The system should be designed so the same backend flow can later support external API usage.

Future API usage:
- create job
- upload documents
- define schema
- run extraction
- fetch final output
- fetch artifacts
- fetch metrics

Do not overbuild external API features in the first MVP.

## 20. Legacy Approach

The legacy system is reference only.

Useful legacy code may be reused later only through adapters.

The new orchestrator must not directly import legacy modules.

## 21. First Implementation Target

The first version should support:
- project creation
- schema creation with fields and tables
- job creation
- document upload
- fake/stub extraction pipeline
- review screen support
- artifact writing
- JSON export

Do not include full AHMN learning in the first implementation target.

Keep the document clear, practical, and not overly long.
