# DocAI v2 Implementation Plan

Status: Current
Last updated: 2026-05-02 (9)

## Completed

### Infrastructure
- AGENTS.md development rules
- backend/core skeleton
- backend contract models
- ArtifactStore
- SchemaRegistry
- PolicyRegistry
- StrategyAssigner
- JobContextBuilder
- DocumentQueueBuilder
- RunPlanBuilder
- StubExtractionRunner
- StubValidationRunner
- StubRecoveryRunner
- RuntimeOrchestrator renamed from FakeOrchestrator
- fake_orchestrator.py kept only as compatibility alias
- CapabilityRegistry wired into RuntimeOrchestrator
- RunArtifactWriter extracted from RuntimeOrchestrator
- RuntimeOrchestrator now coordinates builders/runners/writer instead of owning artifact-writing details
- OCR plugin interface foundation
- Local model plugin interface foundation
- CapabilityRegistry foundation
- runtime spine tests
- research evidence plan
- frontend draft audit and frontend type foundation

### Application Service Layer
- JobRunService as single entry point for job execution
- DocumentProcessor extracted from RuntimeOrchestrator for per-document processing
- StubMetricsService for computable runtime metrics (validation_pass_rate, recovery_success_rate)
- metrics_report.json now carries partial_stub computable values instead of all-None

### Review Evidence Foundation
- ReviewService for building ExpectedValues from FinalOutput with optional corrections
- ExpectedValues dataclasses (ExpectedFieldValue, ExpectedTableRowValue, ExpectedValues)
- ReviewRecord dataclass
- expected_values.json artifact writing support (RunArtifactWriter.write_expected_values)
- review_record.json artifact writing support (RunArtifactWriter.write_review_record)

### Extraction Utilities (Legacy Salvage)
- degarble.py salvaged from legacy (idpo/agents/degarble.py)
- purpose: garbled PDF font encoding detection and character-level recovery
- method: Unicode range heuristic (>15% Latin Extended U+0100–U+024F or Greek digit U+03EC–U+03F5)
- not yet wired into runtime or OCR pipeline — standalone tested utility only
- normalization.py salvaged from legacy (idpo/agents/extraction_parsing.py)
- includes: normalize_key, clean_candidate_value, MISSING_VALUE_MARKERS, TOKEN_EQUIVALENTS
- normalize_key: lowercase, underscore-delimit, 40-char truncation at last word boundary
- clean_candidate_value: bullet prefix removal, whitespace collapse, trailing punct strip
- TOKEN_EQUIVALENTS exported for canonicalization callers; not applied inside normalize_key
- not yet wired into runtime or extraction pipeline — standalone tested utility only
- canonicalization.py salvaged from legacy (idpo/agents/extraction_parsing.py)
- includes: canonicalize_entities (token overlap + containment + description expansion, threshold 0.62) and merge_by_key
- operates on plain dicts (key/value/confidence/metadata) instead of legacy Entity objects
- unmatched entities are kept unchanged (legacy behavior); canonicalized key changes stored as metadata["raw_key"]
- not yet wired into runtime or extraction pipeline — standalone tested utility only
- parsing_utils.py salvaged from legacy (idpo/agents/extraction_parsing.py)
- includes: parse_json_payload (3-pass: direct / brace-extract / array-extract) and parse_entities_response
- parse_entities_response adapted: returns list[dict] instead of list[Entity]; accepts flat dict, entities array, bare array, markdown-fenced shapes
- private _salvage_entity_items copied (character-level bracket scanner for partially-broken arrays)
- not yet wired into runtime or extraction pipeline — standalone tested utility only
- generic_kv.py added as fresh minimal implementation (inspired by legacy review, not a copy)
    - purpose: deterministic key-value candidate extraction from OCR/native text
    - KeyValueCandidate dataclass; parse_kv_line, parse_multi_kv_line, parse_amount_line, extract_key_values
    - label char class restricts digits/hyphens in multi-KV regex so values like "INV-001" never become label prefixes
    - noise filters curated for IDP/invoice domain; IoT entries (soil, tank, rain, actuation) deliberately excluded
    - invoice-relevant single-word keys (date, status, type, total, tax) explicitly kept
    - confidence scoring: 0.75 date / 0.72 amount / 0.70 ID-like / 0.35 long-text / 0.55 default
    - not yet wired into runtime/extraction pipeline — standalone tested utility only
    - HybridExtractionRunner wiring comes later
- prompt_builder.py salvaged from legacy (idpo/agents/extraction_prompts.py)
- includes: build_extraction_prompt, build_single_field_prompt, build_extraction_input, SYSTEM_PROMPT
- build_extraction_prompt: schema fields + optional descriptions → 7-rule extraction prompt; no_think=True prepends /no_think for Qwen3 thinking suppression
- build_single_field_prompt: single-field focused prompt variant
- build_extraction_input: context selection — full text if fits, targeted context if sufficient, else smart-truncate; operates on plain str (no Document/page objects)
- _targeted_context: tokenises field names + descriptions, scans lines for matching terms, collects window_lines before/after (deduped); no page-number prefix
- _smart_truncate: cuts at last paragraph break >70%, else last sentence >70%, else last line >80%
- dropped: AgentContext, Document type, build_chat_messages/build_single_field_messages (provider-specific wrappers)
- not yet wired into runtime or extraction pipeline — standalone tested utility only

### Extraction Runner Foundation
- ExtractionRunnerProtocol added (docai_core/extraction/base.py)
    - structural Protocol: build_ocr_output(Document) → OCROutput; build_extracted_output(schema, document, policy, ocr_output) → ExtractedOutput
    - StubExtractionRunner predates this protocol (uses ocr_text: str); to be migrated in a later task
- KVOnlyExtractionRunner added (docai_core/extraction/kv_extraction_runner.py)
    - first real non-stub extraction runner
    - flow: degarble → extract_key_values → canonicalize_entities → merge_by_key → FieldOutput assembly
    - missing fields → value="N/A", confidence=0.0, extraction_method="not_found", validation_status="missing"
    - found fields → extraction_method="generic_kv", validation_status="needs_review"
    - tables always empty — table extraction is future work
    - not yet wired into DocumentProcessor/runtime
    - model-assisted HybridExtractionRunner still future work

### Text Processing
- OCRPostProcessor added (docai_core/extraction/ocr_postprocessor.py)
    - purpose: deterministic cleanup for OCR/native extracted text before extraction runners
    - applies degarble per page when garbled_ratio ≥ garble_threshold (default 0.15)
    - always applies: hyphen-break joining, control-char removal, line-ending normalization, trailing-space trim, multi-blank-line collapse
    - rebuilds OCROutput.text from cleaned pages; does not mutate the input object
    - consumers: NativePdfTextExtractor output, real OCRPlugin outputs, KVOnlyExtractionRunner, HybridExtractionRunner
    - not yet wired into runtime
- text-to-ExtractedOutput integration test added (tests/integration/test_text_to_extracted_output_pipeline.py)
    - proves OCRPostProcessor + KVOnlyExtractionRunner composition without runtime orchestration or stubs
    - raw OCROutput (with control chars + extra blank lines) → cleaned → four schema fields extracted
    - missing-field path also covered
    - not wired into runtime spine

### Text Acquisition / Multi-Format Input Foundation
- TextExtractorProtocol added (docai_core/text_acquisition/base.py)
    - structural Protocol: extract(Document) → OCROutput
    - UnsupportedDocumentTypeError exception for unregistered/not-yet-implemented types
- PlainTextExtractor added (docai_core/text_acquisition/plain_text_extractor.py)
    - reads .txt files as UTF-8; falls back with errors="replace" on decode failure
    - engine_id="plain_text_extractor"; confidence 1.0 / 0.0 based on non-empty text
    - raises FileNotFoundError for missing files; ValueError for directories
- TextAcquisitionRouter added (docai_core/text_acquisition/router.py)
    - .txt → PlainTextExtractor; .pdf → NativePdfTextExtractor (embedded-text only)
    - .png / .jpg / .jpeg / .tif / .tiff → ImageOCRExtractor (Tesseract)
    - .docx → UnsupportedDocumentTypeError (DOCX message)
    - extension matching is case-insensitive; router delegates, never reads files directly
- docai_core/text_acquisition/__init__.py package created
- File-to-ExtractedOutput integration test (tests/integration/test_file_to_extracted_output_pipeline.py)
    - TXT → TextAcquisitionRouter → OCRPostProcessor → KVOnlyExtractionRunner path covered
    - image (.png) with fake OCR callable demonstrates routing path
    - not wired into runtime spine
- Future: PDFs are not always native-text. Page-aware fallback (OCR for weak/empty/garbled pages)
  is required before real PDF documents are processed. Image OCR is core to the roadmap but
  dependency-gated (Tesseract / PaddleOCR are not yet added).

### Text Acquisition / ImageOCRExtractor v1
- ImageOCRExtractor added (docai_core/text_acquisition/image_ocr_extractor.py)
    - implements TextExtractorProtocol; routes .png/.jpg/.jpeg/.tif/.tiff through the acquisition layer
    - uses ImagePreprocessor (grayscale, autocontrast, upscale, sharpen) before OCR
    - calls pytesseract.image_to_string; language and config are configurable fields
    - engine_id="tesseract_image_ocr"; confidence 1.0/0.0 based on non-empty OCR text
    - ocr_callable injection allows tests to bypass Tesseract entirely
    - ImageOCRDependencyError raised (not ImportError) if Pillow, pytesseract, or Tesseract binary absent
    - all OCR imports are lazy — importing docai_core does not fail if Tesseract is not installed
    - not yet wired into DocumentProcessor or runtime
    - design reference: legacy preprocess.py (_ocr_image, _normalize_image); no idpo code copied
- Image-to-ExtractedOutput integration test added (tests/integration/test_image_to_extracted_output_pipeline.py)
    - .png → TextAcquisitionRouter → ImageOCRExtractor(fake) → OCRPostProcessor → KVOnlyExtractionRunner
    - all four invoice fields extracted from fake OCR text
    - Tesseract dependency error propagation tested via sys.modules monkeypatching
- No scanned PDF fallback yet; no advanced deskew/orientation; PaddleOCR/Docling remain future work
- Multi-format acquisition-to-extraction integration matrix added
  (tests/integration/test_multiformat_acquisition_to_extraction_pipeline.py)
    - shared _run_pipeline helper drives all three format tests through an identical pipeline
    - test_txt_pipeline: TXT → plain_text_extractor → ExtractedOutput (all 4 fields)
    - test_pdf_pipeline: embedded-text PDF → native_pdf_text_extractor → ExtractedOutput (all 4 fields)
    - test_image_pipeline_with_fake_ocr: PNG + fake OCR callable → tesseract_image_ocr → ExtractedOutput (all 4 fields)
    - confirms source-agnostic pipeline contract: every format produces OCROutput → same downstream
    - not wired into DocumentProcessor or runtime

### Text Acquisition / Image Preprocessing
- ImagePreprocessor v1 added (docai_core/text_acquisition/image_preprocessor.py)
    - purpose: deterministic Pillow-based image normalization before any OCR engine
    - pipeline: RGB convert → autocontrast (cutoff=2) → grayscale → conditional 2× BICUBIC upscale
      (if max dimension < upscale_threshold, default 1400px) → optional binarize at threshold 170
      → SHARPEN → optional MedianFilter(3×3)
    - binarize and median_filter flags default False; all thresholds configurable as dataclass fields
    - no file I/O; accepts PIL.Image.Image, returns PIL.Image.Image; never mutates input
    - no OCR calls; no system binary dependencies; Pillow 12.1.0 available
    - not yet wired into router or runtime
    - design reference: legacy preprocess.py (_normalize_image, _preprocess_for_paddle); no
      legacy Agent/Context/idpo code was copied
    - future consumers: ImageOCRExtractor (Tesseract), ScannedPdfExtractor, PaddleOCR path, VLM path

### OCR Acquisition
- NativePdfTextExtractor added (docai_core/ocr/native_pdf_text_extractor.py)
    - purpose: extract embedded text from PDF files without an OCR engine
    - uses pypdf.PdfReader; engine_id="native_pdf_text_extractor"
    - confidence: 1.0 if any non-empty page text found, 0.0 if all pages empty
    - aggregate text: "\n\n".join(non-empty page texts) — page-boundary preserved
    - raises FileNotFoundError for missing file; ValueError for invalid/unreadable PDF
    - not yet wired into DocumentProcessor or runtime
- docai_core/ocr/__init__.py package created; exports NativePdfTextExtractor
- PDF-to-ExtractedOutput integration test added (tests/integration/test_pdf_to_extracted_output_pipeline.py)
    - proves NativePdfTextExtractor → OCRPostProcessor → KVOnlyExtractionRunner composition
    - single-page and multi-page PDF paths both covered
    - not wired into runtime spine

### Validation / Grounding
- GroundingValidator v1 added (docai_core/validation/grounding_validator.py)
    - validates extracted field values against cleaned source text
    - supports exact match, case-insensitive match, whitespace-normalized match,
      and conservative numeric/currency loose match (strips leading $ and commas)
    - _looks_numeric_or_currency guard prevents IDs like "INV-001" from being
      loose-matched against bare digits in source
    - missing value markers ("", "N/A", "n/a", "None", None) counted separately
      from ungrounded values
    - does not use LLM-as-judge, no external fuzzy libraries, no model calls
    - does not mutate ExtractedOutput; returns GroundingResult with per-field verdicts
    - not yet wired into runtime validation reports or StubValidationRunner
    - required foundation before Qwen/model-centered extraction is wired in
- GroundingResult, GroundedFieldResult dataclasses added
- docai_core/validation/__init__.py exports GroundingValidator, GroundingResult, GroundedFieldResult
- Integration test: TXT → TextAcquisitionRouter → OCRPostProcessor → KVOnlyExtractionRunner
  → GroundingValidator; all found fields grounded, hallucinated value correctly flagged
- ValidationRunnerProtocol added (docai_core/validation/base.py)
    - structural Protocol: build_validation_report(extracted_output, ocr_output) → ValidationReport
- GroundingValidationRunner added (docai_core/validation/grounding_validation_runner.py)
    - thin wrapper around GroundingValidator; converts GroundingResult → ValidationReport
    - field_issues encode ungrounded/missing reasons as "field_name: reason" strings
    - pass_status=True when ungrounded_count==0 (missing values do not fail pass_status)
    - summary = "{grounded} grounded, {ungrounded} ungrounded, {missing} missing"
    - does not duplicate GroundingValidator logic
- StubValidationRunner migrated to protocol signature
    - signature changed: (document: Document) → (extracted_output: ExtractedOutput, ocr_output: OCROutput)
    - uses extracted_output.document_id for ValidationReport.document_id
    - stub behavior unchanged: pass_status=True, field_issues=[], summary="stub validation passed"
- DocumentProcessor updated:
    - optional field added: validation_runner: ValidationRunnerProtocol | None = None
    - call site updated: uses validation_runner or stub_validation_runner
    - both receive (extracted_output, ocr_output) — stub path behavior unchanged
- build_local_text_pipeline() updated: injects GroundingValidationRunner
- build_stub_pipeline() unchanged
- local_text artifacts now write grounding-derived validation_report.json
- ValidationReport contract unchanged; v1 grounding issues encoded in field_issues strings
- Qwen/model extraction still not wired into runtime pipeline

### Reviewed Metrics Layer
- MetricsEvaluator for deterministic FinalOutput vs ExpectedValues comparison
- field_accuracy, table_cell_accuracy, overall_accuracy
- field-level precision / recall / F1 with explicit TP / FP / FN definitions
- JobMetricsAggregator for aggregating DocumentMetrics into JobMetrics
- document_metrics.json artifact writing support (RunArtifactWriter.write_document_metrics)
- reviewed_metrics_report.json artifact writing support (RunArtifactWriter.write_reviewed_metrics_report)
- ReviewEvaluationService coordinating post-review metrics evaluation and artifact writing
- ReviewEvaluationApplicationService as application-layer entry point for post-review evaluation
- End-to-end integration test: JobRunService → ReviewService → ReviewEvaluationApplicationService in shared store

### Runtime Pipeline Factory
- RuntimePipelineConfig dataclass added (docai_core/orchestration/pipeline_config.py)
    - fields: document_processor, generated_by, is_stub, note
    - no methods; constructed only via factory functions
- pipeline_factory.py added (docai_core/orchestration/pipeline_factory.py)
    - build_stub_pipeline(): reproduces previous inline DocumentProcessor construction in RuntimeOrchestrator
      generated_by="stub_runtime_orchestrator", is_stub=True; default pipeline when none injected
    - build_local_text_pipeline(): injects TextAcquisitionRouter + OCRPostProcessor + KVOnlyExtractionRunner
      generated_by="local_text_pipeline_v1", is_stub=False; supports .txt, native-text .pdf, images (Tesseract)
    - both functions accept optional policy_dir; default resolves to configs/policies
- RuntimeOrchestrator updated:
    - added optional field: pipeline_config: RuntimePipelineConfig | None = None
    - removed hardcoded _stub_generated_by/_stub_note fields
    - run_job uses cfg = self.pipeline_config or build_stub_pipeline()
    - generated_by, is_stub, note all flow from cfg; no hardcoded stub values remain
    - default behavior (no pipeline_config) is identical to previous stub behavior
- JobRunService updated:
    - added optional field: pipeline_config: RuntimePipelineConfig | None = None
    - passes pipeline_config to RuntimeOrchestrator only when not None (preserves FakeOrchestrator compat)
- RunArtifactWriter metadata now reflects runtime mode:
    - is_stub field added (default True) replaces three hardcoded "is_stub": True literals
    - RuntimeOrchestrator passes cfg.is_stub to RunArtifactWriter
    - local_text mode artifacts (final_output.json, ocr_output.json, document_queue.json, etc.) no longer claim is_stub=True
    - artifact filenames and payload structure unchanged; only is_stub value changes with mode
- No second service created; no duplicate job execution path
- local_text mode: no scanned PDF fallback; no model inference; no Tesseract required for .txt/.pdf
- hybrid_model mode and local_ocr mode are future work

### Runtime Integration / DocumentProcessor Real Acquisition Path
- StubExtractionRunner.build_extracted_output migrated: fourth parameter changed from
  ocr_text: str to ocr_output: OCROutput; internal uses updated to ocr_output.text
  — now satisfies ExtractionRunnerProtocol
- DocumentProcessor updated with three optional fields (all default None):
    - text_acquisition_router: TextAcquisitionRouter | None = None
    - ocr_postprocessor: OCRPostProcessor | None = None
    - extraction_runner: ExtractionRunnerProtocol | None = None
  When all three are None: stub path unchanged (existing tests unaffected)
  When injected: Document.file_path → TextAcquisitionRouter → OCRPostProcessor
    → KVOnlyExtractionRunner → ExtractedOutput flows through DocumentProcessor
- RuntimeOrchestrator not changed — still constructs DocumentProcessor stub-only
- test_stub_extraction_runner.py updated to pass OCROutput (not raw str) to the migrated method
- Integration test: tests/integration/test_document_processor_real_acquisition.py
    - TXT file: engine_id "plain_text_extractor", real field values
    - PDF file: engine_id "native_pdf_text_extractor", real field values
    - image file (fake OCR): engine_id "tesseract_image_ocr", real field values
    - unsupported extension: UnsupportedDocumentTypeError propagates
    - stub path unchanged: "Fake OCR" in text, all values "fake_*"
- Next step: runtime feature flag / dedicated real-run service path; not automatic replacement

### Model Plugin / Qwen Extraction Boundary
- QwenModelPlugin added (docai_core/plugins/models/qwen_model_plugin.py)
    - implements ModelPlugin Protocol; interchangeable with StubModelPlugin or any future adapter
    - fields: plugin_id, provider_name, model_name, endpoint_url, timeout_seconds, api_key
    - default endpoint: http://localhost:11434/api/generate (Ollama-compatible)
    - generate(ModelRequest) → ModelResponse: POST to endpoint, parse response defensively
    - handles four common shapes: {"response": ...}, {"text": ...},
      {"message": {"content": ...}}, choices[0].message.content
    - adds Authorization header only when api_key is set
    - on any transport / HTTP / import failure: returns ModelResponse(success=False)
    - never raises; requests imported lazily inside generate() — module import never fails
    - parsed_json populated when response text is valid JSON
- QwenExtractionStep added (docai_core/extraction/qwen_extraction_step.py)
    - uses any ModelPlugin (not QwenModelPlugin specifically)
    - run(schema, document_text) → list[dict[str, object]] (canonicalized candidates)
    - flow: build_extraction_input → build_extraction_prompt (no_think=True by default)
      → ModelPlugin.generate → parse_entities_response → canonicalize_entities → merge_by_key
    - returns [] on model failure, empty text, or unparseable response; never raises
    - does not build ExtractedOutput; callers (HybridExtractionRunner) own that step
    - does not merge with KV candidates; that is HybridExtractionRunner's responsibility
    - no runtime wiring; no DocumentProcessor changes; no pipeline_factory changes
    - model output is not trusted as final — grounding validation required before use
- Future model providers / fine-tuned models: implement ModelPlugin, not change the extraction pipeline
- HybridExtractionRunner: not yet implemented; superseded by ModelCenteredExtractionRunner design

### Model-Centered Extraction Runner
- ModelCenteredExtractionRunner added (docai_core/extraction/model_centered_extraction_runner.py)
    - satisfies ExtractionRunnerProtocol; not yet wired into DocumentProcessor or runtime
    - fields: model_step: QwenExtractionStep, kv_runner: KVOnlyExtractionRunner,
      model_confidence_floor: float = 0.30
    - build_ocr_output: delegates to kv_runner (protocol compatibility only)
    - build_extracted_output: runs KV path + model path, merges per-field by confidence rules
    - legacy-informed hardening guards applied to model candidates before merge:
        - model_confidence_floor=0.30: candidates below this are treated as not found
          (source: legacy LLMExtractionAgent._dedupe_entities drops entities below 0.30)
        - _is_valid_model_value: rejects values with len < 2, len > 180, trailing ":",
          or single-char alpha-only (source: legacy is_valid_candidate_value)
        - _is_missing check against MISSING_VALUE_MARKERS unchanged
        - guards applied in _model_usable(); NOT applied to KV output (KVOnlyExtractionRunner has own guards)
    - no legacy idpo code imported; guards re-implemented from review findings
    - merge rules:
        - both found, values agree (stripped compare): hybrid_kv_model, confidence=max(kv, model)
        - both found, values differ: higher confidence wins; extraction_method="model_extraction" or "generic_kv"
        - model only: extraction_method="model_extraction"
        - KV only: extraction_method="generic_kv"
        - neither: value="N/A", confidence=0.0, extraction_method="not_found", validation_status="missing"
    - MISSING_VALUE_MARKERS from model count as not found; model N/A cannot override valid KV value
    - schema field order preserved in ExtractedOutput; tables=[] always
    - model is primary semantic extractor; KV is fallback/cross-check
    - GroundingValidationRunner remains responsible for validating model output; high model confidence
      does not bypass grounding (integration test proves this with hallucinated value case)
    - no live model required in tests; all tests use fake QwenExtractionStep / FakeModelPlugin

## Current Checkpoint

The backend now has two clean execution paths:

### Runtime execution path (stub default)
```
JobRunService
→ RuntimeOrchestrator
→ DocumentProcessor (stub_extraction_runner by default)
→ RunArtifactWriter
→ runtime artifacts (metrics_report.json = partial_stub computable values)
```

### Runtime execution path (real acquisition — opt-in injection)
```
DocumentProcessor (text_acquisition_router + ocr_postprocessor + extraction_runner injected)
→ TextAcquisitionRouter → OCROutput
→ OCRPostProcessor → cleaned OCROutput
→ KVOnlyExtractionRunner → real ExtractedOutput
→ FinalOutput
```

### Post-review evaluation path
```
ReviewService
→ ExpectedValues / ReviewRecord
→ ReviewEvaluationService
→ MetricsEvaluator
→ JobMetricsAggregator
→ reviewed metrics artifacts (document_metrics.json, reviewed_metrics_report.json)
```

Both paths are independently testable without real OCR, LLM, database, or API.

## Warning

Do not wire reviewed metrics into RuntimeOrchestrator.
RuntimeOrchestrator is extraction-time execution only.
Reviewed metrics happen after human review, in a separate pass.

Do not build LearningService until reviewed metrics artifacts are stable
and exercised through an application service.

Do not add more responsibilities directly into RuntimeOrchestrator.
Do not create a second workflow path through CLI.
Frontend and API must use the same backend application service later.

## Next Implementation Direction

1. ~~Create a separate application service for review evaluation.~~ Done.
2. ~~Add a small reviewed-evidence fixture/demo integration test path.~~ Done.
3. ~~Start real OCR/layout adapter planning.~~ NativePdfTextExtractor + TextAcquisitionRouter added. Multi-format acquisition foundation complete. Next: wire TextAcquisitionRouter into DocumentProcessor.
4. LearningAdvisor comes later, after real reviewed metrics are used in at least one end-to-end flow.

### build_model_pipeline() — Runtime Wiring for Model-Centered Path
- build_model_pipeline(model_step, policy_dir) added to pipeline_factory.py
    - mirrors build_local_text_pipeline() but injects ModelCenteredExtractionRunner
    - caller supplies QwenExtractionStep (real or fake); no Qwen endpoint required in tests
    - generated_by="model_centered_pipeline_v1", is_stub=False
    - same TextAcquisitionRouter + OCRPostProcessor + GroundingValidationRunner as local_text
    - Stage 3 of pipeline validation plan complete
- Integration tests added (tests/integration/test_runtime_orchestrator_model_pipeline.py):
    - artifact completeness, is_stub=False truthfulness, grounding report presence,
      valid extraction_method values end-to-end (fake model → KV fallback path)

### Local API Layer
- docai_core/api/ package added: app.py, routes.py, schemas.py
- FastAPI application; uvicorn-runnable via `uvicorn docai_core.api.app:app`
- API is thin transport over JobRunService — no OCR/extraction/model logic in routes
- create_app(runs_dir) factory for test isolation; module-level app for uvicorn
- Endpoints:
    - GET /health → {"status": "ok", "service": "docai-v2-api"}
    - POST /runs (multipart: mode + files) → RunResponse
        - mode "stub" → build_stub_pipeline()
        - mode "local_text" → build_local_text_pipeline()
        - mode "local_text_model" → build_model_pipeline(StubModelPlugin by default)
        - unknown mode → HTTP 400
    - GET /runs/{run_id}/artifacts → ArtifactListResponse (file listing from ArtifactStore)
    - GET /runs/{run_id}/documents/{doc_id}/final-output → final_output.json payload
    - GET /runs/{run_id}/documents/{doc_id}/validation-report → validation_report.json payload
    - POST /advisory/recommend → AdvisoryResponse (read-only policy recommendations from reviewed evidence)
- No database, no auth, no cloud deployment — local dev only
- No learning/AHMN/TS/RABI/DAAF in runtime paths
- No real Qwen required in API tests (StubModelPlugin default for local_text_model)
- Frontend can later call POST /runs to start real pipeline runs
- 14 integration tests in tests/integration/test_api_runs.py (all passing)

### AHMN Advisory HTTP Endpoint (read-only recommendation)
- POST /advisory/recommend endpoint added to docai_core/api/routes.py
- accepts PolicyRecordInput list via FastAPI body (AdvisoryRequest schema)
- converts PolicyRecordInput → PolicyPerformanceRecord domain objects
- creates AHMNAdvisoryRequest; delegates to AHMNAdvisoryService.recommend()
- returns AdvisoryResponse with status ("recommended" | "no_recommendation"), reason, and optional recommendation
- recommendation contains: policy_id, policy_version, document_type, quality_bin, score, reason,
  evidence_document_count, field_f1, field_accuracy, missing_rate, correction_rate
- does not mutate policy JSON files; does not create run artifacts; does not trigger JobRunService
- does not implement Thompson Sampling / RABI / DAAF / automatic learning
- does not affect runtime policy selection (advisory-only)
- 5 integration tests in tests/integration/test_api_advisory.py:
    - endpoint returns recommendation when eligible evidence exists
    - endpoint returns no_recommendation when records list is empty
    - endpoint respects min_document_count threshold
    - policy JSON files are byte-identical after advisory call (no mutation)
    - no run artifacts created by advisory endpoint
- All 398 tests passing (5 new advisory tests)

### Ollama/Qwen Env Configuration (local_text_model mode)
- _model_plugin_for_env() in routes.py reads DOCAI_MODEL_PROVIDER at request time (not startup)
- Default (unset / "stub"): StubModelPlugin — no network, no Qwen required; CI-safe
- DOCAI_MODEL_PROVIDER=ollama: constructs QwenModelPlugin with Ollama endpoint
    - DOCAI_OLLAMA_BASE_URL (default: http://localhost:11434)
    - DOCAI_OLLAMA_MODEL (default: qwen)
    - DOCAI_OLLAMA_TIMEOUT_SECONDS (default: 60)
- Unknown DOCAI_MODEL_PROVIDER value → HTTP 400 with clear error message
- QwenModelPlugin imported lazily inside the ollama branch — no import cost for default path
- No second processing path created; all modes still call JobRunService only

### Frontend Run Submission (mock_shell → real API)
- New page: RunExtractionPage at /run (docs/Doc-AI-V2-Front End Gemini Draft/src/pages/RunExtractionPage.tsx)
- Sidebar link added (Play icon, top-level, always visible)
- API client: src/lib/docaiApi.ts — submitRun(), getRunArtifacts(), getDocumentJson()
- API base URL: VITE_DOCAI_API_BASE_URL env var (default: http://localhost:8000)
- RunExtractionPage behavior:
    - User selects mode (local_text, local_text_model, stub) via dropdown
    - User uploads a single document (TXT, PDF, image)
    - POST /runs called on submit; result displayed (run_id, job_id, is_stub, generated_by, counts)
    - "Final Output" and "Validation Report" buttons call artifact endpoints for doc-0
    - Artifact file list shown from GET /runs/{id}/artifacts
    - API errors surfaced clearly; no silent fallback to mock data
- Pages still using mock data (ProjectsPage, ProjectDashboardPage, SchemaBuilderPage,
  JobsPage, NewJobPage, JobViewerPage, DocumentReviewPage, MetricsPage) are UNCHANGED
- No mock warnings removed; no learning/AHMN/TS/RABI/DAAF UI added
- TypeScript lint: clean. Vite build: clean (412 kB JS, 54 kB CSS).

### CORS Middleware
- CORSMiddleware added to create_app() in docai_core/api/app.py
- Transport-only change; no pipeline behavior modified
- Origins configurable via DOCAI_CORS_ALLOW_ORIGINS env var:
    - Unset: allows http://localhost:5173, :3000, http://127.0.0.1:5173, :3000
    - "*": allow all origins
    - Comma-separated list: parsed and trimmed
- Methods: GET, POST, OPTIONS. Headers: *. Credentials: false.
- Production deployments should set DOCAI_CORS_ALLOW_ORIGINS to the deployed frontend URL
- Auth still not implemented
- 2 CORS integration tests added (preflight default origins, env-configured custom origin)

### Policy-to-Pipeline Wiring (A/B strategy evaluation foundation)
- All policy JSON variants now carry a "runtime" block:
    - pipeline_mode: "local_text" | "local_text_model"
    - extraction_runner: "kv_only" | "model_centered"
    - grounding_required: true
- Assignments: invoice_basic_local_v1 and invoice_table_heavy_local_v1 and receipt_basic_local_v1 → local_text; noisy_scan_rescue_v1 → local_text_model
- _FixedPolicyAssigner added to pipeline_factory.py — replaces StrategyAssigner for forced-policy runs; always returns the pre-selected SelectedPolicy regardless of document profile
- _find_variant() searches all policy families for a matching policy_id; raises ValueError on miss
- build_pipeline_for_policy(policy_id, policy_dir, model_step) builds the correct pipeline from policy JSON and injects _FixedPolicyAssigner via dataclasses.replace
- POST /runs now accepts optional policy_id Form parameter:
    - policy_id present → build_pipeline_for_policy(); takes precedence over mode
    - mode only → existing behavior unchanged
    - unknown policy_id → HTTP 400
    - neither provided → HTTP 400
- selected_policy.json artifact always reflects the forced policy_id (via _FixedPolicyAssigner)
- policies_used in API response reflects the forced policy_id
- mode parameter remains backward-compatible; all existing tests pass
- Real A/B evaluation now possible: POST /runs?policy_id=invoice_basic_local_v1 vs POST /runs?policy_id=noisy_scan_rescue_v1 on same document → different pipeline → different extraction behavior → ReviewEvaluationService compares results
- No AHMN/TS/RABI/DAAF; no policy auto-mutation; no learning

### Policy A/B Evaluation Harness
- tests/integration/test_policy_ab_evaluation.py — first evidence loop
- Same document can be run under two policy_ids and compared via ReviewEvaluationApplicationService
- Test 1 (test_policy_ab_evaluation_compares_two_policy_runs):
    - invoice_basic_local_v1 (local_text_pipeline_v1) vs noisy_scan_rescue_v1 (model_centered_pipeline_v1)
    - Same KV invoice text, same ExpectedValues ground truth
    - Proves both runs produce reviewed metrics (field_accuracy, precision, recall, f1)
    - Proves policy_id and generated_by differ between runs
- Test 2 (test_policy_ab_evaluation_detects_metric_difference):
    - Prose text (no colon-separated KV patterns) defeats KV-only extraction
    - _FakeModelPlugin returns all four correct fields for the model-centered policy
    - Asserts model-centered field_recall >= KV-only field_recall on prose text
    - No real Qwen/Ollama required — fake plugin used for model-centered path
- ReviewEvaluationApplicationService reused as-is; no new production code added
- This is the prerequisite evidence loop before AHMN/TS/RABI/DAAF
- No policies mutated. No learning performed.

### PolicyPerformanceRecord Aggregation
- DocumentPolicyProfile dataclass (docai_core/metrics/policy_performance.py)
    - fields: policy_id, policy_version="v1", document_type="unknown", quality_bin="unknown"
    - maps a processed document to the policy that extracted it
- PolicyPerformanceRecord dataclass
    - fields: policy_id, policy_version, document_type, quality_bin, document_count,
      field_accuracy, field_precision, field_recall, field_f1, missing_rate, correction_rate, evaluated_at
    - one record per (policy_id, policy_version, document_type, quality_bin) group
    - missing_rate = sum(missing_expected_field_count) / sum(field_total); None when field_total == 0
    - correction_rate = sum(corrected_field_count) / sum(field_total); None when field_total == 0
    - field_accuracy/precision/recall/f1: averaged across documents in the group (_avg helper)
- _GroupKey NamedTuple for grouping; documents without a profile fall into ("unknown", ...) group
- PolicyPerformanceAggregator.aggregate(document_metrics, profile_by_document_id) → list[PolicyPerformanceRecord]
    - groups DocumentMetrics by _GroupKey, computes per-group record; no artifact I/O, no model calls
- docai_core/metrics/__init__.py updated to export DocumentPolicyProfile, PolicyPerformanceRecord, PolicyPerformanceAggregator
- 7 unit tests in tests/unit/test_policy_performance.py:
    - empty input → empty output
    - single document → single record
    - two docs same group → merged (averaged metrics, summed for rates)
    - two different policies → two records
    - missing profile → "unknown" group
    - missing_rate and correction_rate computed correctly
    - zero field_total → None rates (no ZeroDivisionError)
- All 375 tests passing

### AHMNPolicyAdvisor v1 (read-only recommendation layer)
- AHMNPolicyRecommendation dataclass (docai_core/policies/ahmn_policy_advisor.py)
    - fields: policy_id, policy_version, document_type, quality_bin, score, reason,
      evidence_document_count, field_f1, field_accuracy, missing_rate, correction_rate
    - output-only; never fed back into runtime selection or policy files
- AHMNPolicyAdvisor dataclass
    - field: min_document_count: int = 10
    - recommend(records, document_type, quality_bin) → AHMNPolicyRecommendation | None
    - filters by document_type + quality_bin + min_document_count threshold
    - scoring v1: base = field_f1 (or field_accuracy as fallback); penalise missing_rate and
      correction_rate by 0.10× each; clamped to [0.0, 1.0]; fully deterministic
    - returns None when no eligible records exist (no fake/speculative recommendations)
    - reason string names the winning policy, metric used, value, profile, and evidence count
- This is the first AHMN foundation step: read evidence → produce recommendation
- Read-only: does not mutate policies, does not write artifacts, does not call models
- Does not implement Thompson Sampling
- Does not implement RABI / DAAF
- Does not implement automatic learning or automatic policy selection
- Requires min_document_count reviewed documents before any recommendation (evidence gate)
- docai_core/policies/__init__.py exports AHMNPolicyAdvisor and AHMNPolicyRecommendation
- 8 unit tests in tests/unit/test_ahmn_policy_advisor.py:
    - highest F1 record wins
    - document_type mismatch excluded
    - quality_bin mismatch excluded
    - below min_document_count excluded
    - accuracy fallback when F1 is None
    - penalty for high missing/correction rate breaks F1 ties
    - None returned when no eligible records
    - public export from docai_core.policies verified
- All 383 tests passing (8 new)

### AHMNAdvisoryService v1 (application layer wrapper)
- AHMNAdvisoryRequest dataclass (docai_core/application/ahmn_advisory_service.py)
    - fields: records: list[PolicyPerformanceRecord], document_type, quality_bin,
      min_document_count=10
- AHMNAdvisoryResult dataclass
    - fields: recommendation: AHMNPolicyRecommendation | None, status: str, reason: str
    - status values: "recommended" | "no_recommendation"
- AHMNAdvisoryService.recommend(request) → AHMNAdvisoryResult
    - constructs AHMNPolicyAdvisor with request.min_document_count
    - delegates to advisor.recommend(); wraps result in AHMNAdvisoryResult
    - no_recommendation path provides human-readable reason naming document_type/quality_bin/threshold
- Thin wrapper: all scoring and filtering logic stays in AHMNPolicyAdvisor; service owns only the request/result boundary
- Read-only: no artifact writing, no file I/O, no model calls, no policy mutation
- Does not affect runtime policy selection
- Does not implement Thompson Sampling / RABI / DAAF / learning loops
- Intended next use: expose via a read-only API advisory endpoint (not yet implemented)
- 5 unit tests in tests/unit/test_ahmn_advisory_service.py:
    - recommended status and correct policy_id when eligible evidence exists
    - no_recommendation with empty records
    - no_recommendation when all records below min_document_count
    - input records list not mutated
    - human-readable reason for both status paths
- All 388 tests passing (5 new)

### Real Policy Evaluation Batch Harness
- tests/integration/test_real_policy_evaluation_batch.py — first real evidence batch
- 3 fixture invoice documents (clean KV, prose, missing-field) run through two policies
    - invoice_basic_local_v1 (KV-only, local_text pipeline)
    - noisy_scan_rescue_v1 (model-centered pipeline with fake model in tests)
- Full chain exercised per test: JobRunService → artifacts → ReviewEvaluationApplicationService
  → document_metrics.json → PolicyPerformanceAggregator → PolicyPerformanceRecord → AHMNAdvisoryService
- No Qwen/Ollama/Tesseract required; fake model plugin used for prose document under model policy
- No fake performance records — all DocumentMetrics read from real written artifacts
- 5 integration tests:
    - Both policies produce final_output.json + correct selected_policy.json for every document
    - All runs are review_based with field_total=4
    - PolicyPerformanceAggregator groups by policy_id; document_count=3 per group
    - AHMNAdvisoryService recommends from real aggregated evidence (min_document_count=3 to match fixture)
    - Policy JSON files are byte-identical after the batch run (no mutation)
- Advisory API still deferred — endpoint only useful after real production evidence exists
- Thompson Sampling / RABI / DAAF still deferred
- All 393 tests passing (5 new)

## Do Not Add

- real OCR
- real LLM (Qwen requires explicit plugin swap; not the default)
- database
- auth/cloud deployment
- AHMN
- Thompson Sampling
- RABI / DAAF
- automatic prompt rewriting
- automatic policy mutation
- LearningService before reviewed metrics are stable
