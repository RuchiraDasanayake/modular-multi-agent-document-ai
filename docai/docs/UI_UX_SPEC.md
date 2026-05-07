# DocAI v2 UI/UX Spec

## 1. UX Goal

DocAI v2 should let users easily:

- create a project
- define fields and tables to extract
- upload documents
- run extraction jobs
- review extracted values
- correct expected values
- export structured output
- view metrics and policy behavior

The UI must prioritize clarity, speed, and trust.

## 2. Main Navigation

Use simple navigation:

- Projects
- Schemas
- Jobs
- Review
- Metrics
- Settings

Avoid clutter.

## 3. Core Screens

Define these screens:

### Projects Page

Purpose:  
Show all extraction projects.

Actions:
- create project
- open project
- view recent job status

Show:
- project name
- description
- number of jobs
- last run status
- latest accuracy/metrics if available

### Project Dashboard

Purpose:  
Central workspace for one project.

Show:
- schemas
- recent jobs
- documents processed
- failed documents
- review pending count
- latest metrics

Actions:
- create schema
- create job
- view metrics
- open review queue

### Schema Builder

Purpose:  
Let users define the structured output.

Must support:
- add simple field
- add table
- add columns to table
- field/column descriptions
- type selection
- required/optional toggle
- example values
- validation rules

Use simple labels:
- Fields
- Tables
- Columns
- Rows

### New Job Page

Purpose:  
Create a processing job.

Inputs:
- job name
- project
- extraction schema
- documents
- run mode

Run modes:
- fixed_ocr_llm later
- static_policy later
- policy_driven
- adaptive_learning later

For MVP, allow only stub/policy_driven placeholder if needed.

### Job Run Viewer

Purpose:  
Show job progress and document results.

Show:
- job status
- document list
- per-document status
- selected policy
- validation status
- extraction progress
- artifact links

### Document Review Page

Purpose:  
Review one document in detail.

Layout:  
Left side:
- document preview
- OCR text toggle
- artifact links

Right side:
- extracted fields
- expected values
- confidence
- validation status
- correction input

For tables:
- show extracted rows
- allow row correction
- allow missing row marking
- allow column correction

### Results Export Page

Purpose:  
Export structured output.

Actions:
- export JSON
- export CSV
- export reviewed results
- export metrics

### Metrics Page

Purpose:  
Show evaluation results.

Show:
- precision
- recall
- F1
- field accuracy
- table accuracy
- validation pass rate
- recovery success rate
- policy distribution

## 4. Design Principles

- One primary action per screen.
- Always show job status clearly.
- Always show selected policy when available.
- Always show validation issues clearly.
- Make human correction easy.
- Do not hide artifacts.
- Do not overload screens with charts.
- Prefer tables and cards over complex dashboards.
- Use plain language.

## 5. MVP UI Scope

First UI version should support:

- projects page
- project dashboard
- schema builder
- new job page
- job run viewer
- document review page
- JSON export placeholder

Do not include:
- billing
- permissions
- team management
- advanced dashboards
- chat interface
- complex automation builder

Keep the document clear and practical.
