# Hallucination Guardrails for Modular Multi-Agent Document AI

**Project ID:** 25-261-129  
**Component:** Hallucination Detection & Guardrails  
**Team Member:** Wijetunga W.L.A.T. (Thenuka)  
**Collaborators:** Pathirana M.M., Dasanayake D.R.L., Nayanapriya S.A.T.  
**Degree:** BSc (Hons) in Information Technology – Specializing in Data Science  
**Institution:** Department of Data Science, Faculty of Computing, Sri Lanka Institute of Information Technology (SLIIT)  
**Timeline:** February 2026 (Progress Presentation 2)

## Overview

This component acts as the **safety & quality layer** in the Modular Multi-Agent Document AI system. It receives structured extractions from the IDPO (Intelligent Document Processing Orchestrator) and applies a **5-layer ensemble** of guardrails to:

- Detect hallucinations (ungrounded extraction)
- Enforce logical consistency
- Apply business-domain rules
- Prevent PII leakage
- Validate schema compliance

If any check fails, the output flags the result for human review or re-extraction, ensuring safe, trustworthy, and explainable document AI processing.

## Features

- **5-Layer Guardrail Ensemble**
  - Schema Adherence (Pydantic validation)
  - Internal Consistency (math, negatives, empty fields, future dates, dosage rules)
  - Domain Rules (vendor overlap/fraud, tax plausibility 0–30%, large amounts, keyword suspicion)
  - PII Leakage Detection (Presidio – context-aware: allow PERSON/DATE_TIME in medical docs)
  - Faithfulness / Hallucination Detection (sentence-transformers semantic similarity, threshold 0.78)

- **Context-Aware Safety**
  - Allows patient names/dates in medical documents (ClinicalSummary, MedicationDosage, InsuranceClaim)
  - Flags names in business/finance documents (Invoice, Receipt, etc.)

- **Structured Output**
  - Full audit trail (input echo, per-check details)
  - Overall pass/fail decision
  - Advice ID & audit logging
  - Metrics summary (num_failed_checks, per-check scores, processing time)

- **Interactive Testing**
  - Swagger UI (`/docs`) with dropdown examples for different scenarios
  - Local demo script (`demo_test.py`) with console + simulated JSON

## Installation & Setup

### Prerequisites
- Python 3.10+
- Virtual environment (recommended)

### Install Dependencies
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt

Run the API Server
Bashuvicorn hallucination_guardrails.main:app --reload

API available at: http://127.0.0.1:8000
Interactive docs: http://127.0.0.1:8000/docs (Swagger UI)

Run Local Demo
Bashpython -m hallucination_guardrails.demo_test
Shows console summary + simulated full JSON responses for 6 test scenarios.
Input & Output Contract
Input (from IDPO) – RAGInput
JSON{
  "document_context": {
    "doc_type": "Invoice",           // Required: one of 7 types
    "vendor": "ABC Suppliers Ltd",   // Optional: for domain rules
    "quality_bin": "high"            // Optional: OCR quality hint
  },
  "query": "Extract invoice details",
  "answer_json": "{\"customer_name\": \"Test Customer\", \"subtotal\": 100.0, \"tax\": 40.0, \"total\": 140.0}",
  "source_contexts": ["Subtotal 100, tax 40, total 140"],
  "document_id": "inv-test-001"     // Optional
}
Output – GuardrailOutput (JSON)
JSON{
  "rag_input": { ... echoed input ... },
  "validation_results": [
    {
      "name": "domain_rules",
      "score": 0.0,
      "is_pass": false,
      "details": "Implausible tax rate: 40.0% (expected 0–30%)",
      "timestamp": "2026-02-10T14:57:58.252274"
    },
    ...
  ],
  "overall_passes": false,
  "audit_log_id": "526d2815-cfa4-41d5-aac4-41fec83f8bd6",
  "processing_time_ms": 842.1,
  "timestamp": "2026-02-10T14:57:58.349652",
  "advice_id": "9906e228-351e-4e1c-a070-585f9dbdbe39",
  "metrics": {
    "guardrails_success": false,
    "num_failed_checks": 2,
    "faithfulness_avg_score": 0.32,
    "schema_adherence_score": 1.0,
    "consistency_score": 1.0,
    "domain_rules_score": 0.0,
    "pii_leakage_score": 1.0,
    "cost": 0.0,
    "processing_time_ms": 842.1
  }
}

.