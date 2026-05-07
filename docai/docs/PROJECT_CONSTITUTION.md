# DocAI v2 Project Constitution

## System identity

DocAI v2 is a local-first, policy-driven document extraction system. It allows users to create projects, define extraction schemas, upload document batches, run extraction jobs, review extracted fields, set expected values, and improve policies over time.

## Core goals

- simple and scalable architecture
- UI-first document extraction workflow
- local OCR and local model support
- policy-driven OCR, preprocessing, extraction, validation, and recovery
- field-level and entity-level extraction
- artifact-first debugging
- benchmark-ready evaluation
- research-worthy adaptive policy learning later

## Non-goals

- not a chatbot
- not a random autonomous agent playground
- not a pile of scripts
- not a system where AI invents architecture
- not a system where policies are hardcoded randomly
- not a cloud-only extraction wrapper

## Core workflow

Project created  
→ schema defined  
→ job created  
→ documents uploaded  
→ policy selected  
→ OCR/parser executed  
→ fields/entities extracted  
→ validation performed  
→ recovery attempted  
→ user review/correction  
→ expected values saved  
→ learning event recorded

## Core principles

- contracts before implementation
- every run writes artifacts
- prompts are versioned assets
- policies are versioned configs
- every extracted value should have evidence
- every failed field should have a reason
- legacy code is reference only unless wrapped through an adapter
- Codex implements only requested modules

This document is intentionally clear and practical.
