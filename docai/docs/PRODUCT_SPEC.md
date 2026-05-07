# DocAI v2 Product Spec

## Product summary

DocAI v2 is a web-based document extraction orchestrator where users create projects, define extraction schemas, upload document batches, run jobs, review extracted results, set expected values, and export structured outputs.

## Main user roles

- Admin
- Extraction Operator
- Reviewer
- Research/Evaluation User

## Main user flows

A. Create project  
B. Define schema  
C. Create job  
D. Upload documents  
E. Run extraction  
F. Review extracted fields  
G. Set or correct expected values  
H. Export JSON/CSV  
I. View job metrics and policy behavior

## Core screens

- Projects page
- Project dashboard
- Schema builder
- New job page
- Job run viewer
- Document review page
- Results export page
- Benchmark/evaluation page

## UX principles

- simple actions
- clear job status
- no clutter
- show useful results quickly
- always show selected policy
- always show field value, expected value, validation status, and confidence
- allow human correction
- show artifact links for debugging

## MVP scope

- project creation
- schema creation with fields and descriptions
- job creation
- document upload
- run extraction using placeholder/fake pipeline first
- view extracted fields
- manually set expected values
- export result JSON

## Out of scope for first MVP

- full AHMN learning
- many OCR engines
- complex RCM claim extraction
- multi-user permissions
- advanced dashboards
- billing
- cloud deployment automation

This spec is intentionally clear and practical.
