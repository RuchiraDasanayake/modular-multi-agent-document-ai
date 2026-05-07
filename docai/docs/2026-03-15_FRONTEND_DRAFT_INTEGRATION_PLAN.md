# Frontend Draft Integration Plan

Status: Current as of 2026-03-15

## 1. Purpose

The Gemini frontend draft is a reference UI foundation, not production UI yet.

## 2. Current Location

The draft currently lives at:

`docs/Doc-AI-V2-Front End Gemini Draft`

## 3. Target Location Later

The cleaned frontend will later live at:

`apps/ui`

This move happens only after cleanup and review.

## 4. Reuse Strategy

Use this sequence:

reference  
→ audit  
→ type  
→ clean  
→ split  
→ align  
→ integrate  
→ connect backend later

## 5. What We Keep

Keep:

- sidebar layout
- route-level page structure
- projects page
- project dashboard
- schema builder concept
- jobs page
- new job page
- job viewer concept
- document review split layout
- metrics page concept
- design token direction
- reusable UI primitives as a starting point

## 6. What Must Be Cleaned

Must clean:

- split large JobViewerPage
- define frontend contract types
- remove page-embedded mock arrays
- create typed mock fixture layer
- standardize vocabulary
- replace hardcoded colors with tokens
- add loading/error/empty states later
- remove generator-specific artifacts
- fix visible typos and encoding issues

## 7. Required Frontend Contracts

The UI should eventually align with:

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

## 8. Vocabulary Standard

Use:

- Extraction Schema
- Extraction Strategy
- Policy only as technical secondary wording
- Expected Values
- Training Run
- Production Run
- Document Queue
- Extracted Data
- Review
- Metrics

Avoid mixing:

- schema/output schema/extraction schema
- policy/strategy inconsistently
- expected output/expected values inconsistently

## 9. Cleanup Order

1. Preserve the draft as-is.
2. Create shared frontend types.
3. Move mock data into typed fixtures.
4. Split JobViewerPage into tab components.
5. Split DocumentReviewPage into review components.
6. Split SchemaBuilderPage if needed.
7. Normalize design tokens.
8. Standardize vocabulary.
9. Add API boundary stubs.
10. Move cleaned UI to apps/ui.
11. Connect backend later.

## 10. Do Not Do Yet

Do not:

- connect backend
- add real learning logic
- add authentication
- add permissions
- add billing
- rebuild UI from scratch
- let Codex redesign the product
- directly integrate draft into production

## 11. Documentation Rule Going Forward

All planning docs must include:

- date in filename
- status line near the top
- note if superseded or outdated
- replacement document link/name if superseded

Example:

`2026-03-15_FRONTEND_DRAFT_INTEGRATION_PLAN.md`

If a newer version replaces this file, add this near the top:

`Status: Outdated as of YYYY-MM-DD. Replaced by <new document filename>.`

If this plan no longer matches the frontend implementation, mark it as outdated at the top before creating a replacement document.
