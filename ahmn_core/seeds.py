"""
LTM Seed Data — Single Source of Truth
========================================
Authoritative policy seed data for AHMN's long-term memory initialization.
Aligned with:
  - configs/policy_store.json (5 policies: forms, scanned_text, table_heavy, mixed_content, default)
  - IDPO pipeline document types and content profiles
  - Guardrails DocumentType enum values

Used by:
  - ahmn_core/main.py → Auto-seed on startup if LTM is empty
  - scripts/reset_and_seed_db.py → Reseed the database
  - scripts/fresh_deploy.py → Full reset via reset_and_seed_db.py

Policy Mappings:
  table_heavy    → invoice, receipt, financial_statement, table_document
  forms          → form_document, clinical_summary
  scanned_text   → scanned_document, text_document
  mixed_content  → mixed_document, contract
  default        → unknown (catch-all)
"""

LTM_SEEDS = [
    # Invoice documents → table_heavy policy
    {
        "doc_type": "invoice",
        "content_profile": "table-heavy",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "invoice", "content_profile": "table-heavy", "action": "invoice_processing", "origin": "seed"},
        "alpha": 9.0,
        "beta": 2.0,
        "confidence": 0.82,
    },
    # Table documents → table_heavy policy
    {
        "doc_type": "table_document",
        "content_profile": "table-heavy",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "table_document", "content_profile": "table-heavy", "action": "table_extraction", "origin": "seed"},
        "alpha": 8.0,
        "beta": 3.0,
        "confidence": 0.73,
    },
    # Receipt → table_heavy
    {
        "doc_type": "receipt",
        "content_profile": "table-heavy",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "receipt", "content_profile": "table-heavy", "action": "receipt_processing", "origin": "seed"},
        "alpha": 7.0,
        "beta": 3.0,
        "confidence": 0.70,
    },
    # Form documents → forms policy
    {
        "doc_type": "form_document",
        "content_profile": "form-centric",
        "policy_id": "forms",
        "policy_data": {"doc_type": "form_document", "content_profile": "form-centric", "action": "form_extraction", "origin": "seed"},
        "alpha": 7.0,
        "beta": 3.0,
        "confidence": 0.70,
    },
    # Scanned documents → scanned_text policy
    {
        "doc_type": "scanned_document",
        "content_profile": "scanned",
        "policy_id": "scanned_text",
        "policy_data": {"doc_type": "scanned_document", "content_profile": "scanned", "action": "ocr_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 4.0,
        "confidence": 0.60,
    },
    # Mixed content → mixed_content policy
    {
        "doc_type": "mixed_document",
        "content_profile": "mixed",
        "policy_id": "mixed_content",
        "policy_data": {"doc_type": "mixed_document", "content_profile": "mixed", "action": "mixed_processing", "origin": "seed"},
        "alpha": 5.0,
        "beta": 3.0,
        "confidence": 0.63,
    },
    # Contract → mixed_content (contracts are multi-section)
    {
        "doc_type": "contract",
        "content_profile": "mixed",
        "policy_id": "mixed_content",
        "policy_data": {"doc_type": "contract", "content_profile": "mixed", "action": "contract_processing", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    # Financial report → table_heavy (numbers + tables)
    {
        "doc_type": "financial_statement",
        "content_profile": "table-heavy",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "financial_statement", "content_profile": "table-heavy", "action": "financial_extraction", "origin": "seed"},
        "alpha": 7.0,
        "beta": 4.0,
        "confidence": 0.64,
    },
    # Text document → scanned_text
    {
        "doc_type": "text_document",
        "content_profile": "text-heavy",
        "policy_id": "fast_local_text",
        "policy_data": {"doc_type": "text_document", "content_profile": "text-heavy", "action": "fast_text_extraction", "origin": "seed"},
        "alpha": 7.0,
        "beta": 3.0,
        "confidence": 0.71,
    },
    # Clinical summary → forms (structured extraction)
    {
        "doc_type": "clinical_summary",
        "content_profile": "form-centric",
        "policy_id": "forms",
        "policy_data": {"doc_type": "clinical_summary", "content_profile": "form-centric", "action": "clinical_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    # Unknown → default policy with flat prior
    {
        "doc_type": "unknown",
        "content_profile": "unknown",
        "policy_id": "unknown_vendor_safe",
        "policy_data": {"doc_type": "unknown", "content_profile": "unknown", "action": "safe_unknown_processing", "origin": "seed"},
        "alpha": 4.0,
        "beta": 4.0,
        "confidence": 0.50,
    },
    # Medical record → forms
    {
        "doc_type": "medical_record",
        "content_profile": "form-centric",
        "policy_id": "forms",
        "policy_data": {"doc_type": "medical_record", "content_profile": "form-centric", "action": "medical_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 4.0,
        "confidence": 0.60,
    },
    {
        "doc_type": "invoice",
        "content_profile": "table-heavy",
        "policy_id": "noisy_ocr_rescue",
        "policy_data": {"doc_type": "invoice", "content_profile": "table-heavy", "action": "noisy_invoice_rescue", "origin": "seed"},
        "alpha": 5.0,
        "beta": 4.0,
        "confidence": 0.58,
    },
    {
        "doc_type": "contract",
        "content_profile": "mixed",
        "policy_id": "long_document_chunked",
        "policy_data": {"doc_type": "contract", "content_profile": "mixed", "action": "long_document_chunked", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.69,
    },
]
