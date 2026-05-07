# Frontend Types Plan

Status: Current as of 2026-03-15

## 1. Purpose

Define the TypeScript domain types the frontend must eventually use so pages are not driven by random mock objects.

The goal is to align the frontend with DocAI v2 contracts before backend integration.

## 2. Target Location Later

When implemented, frontend types should live in:

`apps/ui/src/types/`

For now, this document only defines the intended types.

## 3. Required Type Groups

Define these type groups:

### Project Types

- Project
- ProjectSummary

### Schema Types

- ExtractionSchema
- Field
- Table
- Column

### Job Types

- Job
- JobRunType
- JobStatus

JobRunType values:

- training
- production

JobStatus values:

- draft
- queued
- profiling
- assigning_strategies
- running
- needs_review
- completed
- failed

### Document Types

- Document
- DocumentStatus
- DocumentProfile

DocumentStatus values:

- uploaded
- profiled
- strategy_pending
- ready
- processing
- completed
- needs_review
- failed

### Tool / Configuration Types

- AvailableTool
- AvailableTools
- LocalModelConfig

LocalModelConfig should include:

- provider
- model
- temperature
- max_tokens
- json_mode
- fallback_model

### Strategy / Policy Types

- ExtractionStrategy
- StrategyStatus
- StrategyAssignment

StrategyStatus values:

- candidate
- testing
- promoted
- stable
- drifting
- retired

StrategyAssignment should include:

- document_id
- strategy_id
- strategy_name
- reason_assigned
- compatible_tools
- learning_source
- status

### Output Types

- ExtractedOutput
- FieldOutput
- TableOutput
- RowOutput
- ExpectedOutput

### Validation / Recovery Types

- ValidationStatus
- ValidationIssue
- ValidationReport
- RecoveryStatus
- RecoveryReport

ValidationStatus values:

- valid
- low_confidence
- not_grounded
- missing
- recovered
- needs_review
- failed

### Metrics Types

- MetricsReport
- StrategyMetrics
- RunProgressionRecord

### Learning Types

- LearningRecord
- StrategyRecommendation

## 4. Rules

Add these rules:

- Pages should import shared types instead of defining local ad-hoc objects.
- Mock data should use these shared types.
- API responses later should map to these shared types.
- Do not embed large mock arrays directly inside page components.
- Keep UI labels product-friendly.
- Use “Extraction Strategy” in UI, with “Policy” only as secondary technical wording.
- Use “Expected Values” consistently.
- Use “Training Run” and “Production Run” consistently.

## 5. First Implementation Order Later

When implementation begins later, do it in this order:

1. Create `apps/ui/src/types/domain.ts`
2. Move mock data into `apps/ui/src/fixtures/`
3. Update Projects page to use typed fixtures
4. Update Project Dashboard
5. Update Jobs page
6. Update Job Viewer
7. Update Document Review
8. Update Metrics

## 6. Do Not Do Yet

Do not:

- connect backend
- add API hooks
- refactor page layouts
- split large pages
- rewrite components
- add real learning logic

Keep the document clear and practical.
