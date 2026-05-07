# DocAI v2 Deployment and Scaling Plan

Status: Current  
Last updated: 2026-03-15

## 1. Purpose

Define how DocAI v2 should scale from local development to hosted multi-project usage without overengineering the first version.

## 2. Current MVP Deployment

The first version should run as a simple modular monolith.

MVP components:
- React frontend later
- Python backend/core
- local artifact storage
- local configs
- local test runs
- no distributed workers yet
- no cloud dependency required

The goal is to prove the product flow first:  
Project  
? Extraction Schema  
? Job  
? Document Queue  
? Strategy Assignment  
? Extraction  
? Review  
? Export  
? Metrics

## 3. Near-Term Hosted Deployment

When ready to host, use a simple structure:

- Frontend app
- Backend API
- Background worker
- Database
- Artifact storage

Recommended logical components:
- API service for projects, schemas, jobs, documents, results
- Worker service for document processing
- Database for metadata
- Object/file storage for artifacts
- Local or hosted model/OCR runtime depending on deployment

Do not split into many microservices early.

## 4. Database vs Artifact Storage

Database should store:
- projects
- schemas
- jobs
- documents
- document status
- selected strategies
- review status
- metrics summaries
- expected values metadata

Artifact storage should store:
- uploaded files
- OCR output
- extracted output
- validation reports
- recovery reports
- final JSON
- raw model responses
- run logs

Do not store large raw artifacts directly in the database.

## 5. Scaling Jobs

For 1000+ documents per job, the system should eventually support:
- document queue
- per-document status
- retry failed documents
- pagination
- background processing
- progress updates
- resumable jobs
- artifact cleanup policy

Processing should be per document, not one giant job transaction.

## 6. Worker Model Later

Later worker responsibilities:
- document profiling
- strategy assignment
- OCR/parser execution
- extraction
- validation
- recovery
- artifact writing
- metrics update

The API should not do heavy document processing directly in production.

## 7. Multi-Company Support Later

Do not build this now, but leave space for:
- organization
- project ownership
- user roles
- data separation
- per-company model/settings
- per-company artifact storage prefix

First version can treat each company/client as a Project.

## 8. Hosting Priorities

Priorities:
1. reliability
2. traceability
3. reproducibility
4. easy debugging
5. simple deployment
6. scale later

Avoid:
- premature Kubernetes
- many microservices
- complex event systems
- cloud lock-in
- hidden background behavior

## 9. Observability

Every job should expose:
- job status
- document status
- selected strategy
- current stage
- failure reason
- artifact links
- run logs

This is more important than fancy dashboards.

## 10. Security Later

Not part of MVP, but plan for:
- authentication
- role permissions
- project-level access
- document retention policy
- audit logs
- secure artifact access
- PHI/PII handling for RCM documents later

## 11. Do Not Build Yet

Do not build yet:
- production queue
- cloud deployment automation
- Kubernetes
- multi-tenant permissions
- billing
- advanced monitoring
- distributed OCR workers
- autoscaling

## 12. Implementation Direction

Current implementation should continue with:
- contracts
- artifact store
- schema registry
- policy registry
- stub orchestrator
- tests

Deployment and scaling should influence structure, but should not slow down the MVP.

Keep this document clear and practical.