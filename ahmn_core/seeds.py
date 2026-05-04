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
    # ── table_heavy (3 seeds, balanced alpha) ──
    {
        "doc_type": "invoice",
        "content_profile": "table-heavy with line items, totals, tax breakdowns",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "invoice", "content_profile": "table-heavy", "action": "invoice_processing", "origin": "seed"},
        "alpha": 7.0,
        "beta": 3.0,
        "confidence": 0.70,
    },
    {
        "doc_type": "receipt",
        "content_profile": "table-heavy with itemised purchases and payment totals",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "receipt", "content_profile": "table-heavy", "action": "receipt_processing", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    {
        "doc_type": "financial_statement",
        "content_profile": "table-heavy with balance sheets, income statements, numerical columns",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "financial_statement", "content_profile": "table-heavy", "action": "financial_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    # ── forms (3 seeds) ──
    {
        "doc_type": "form_document",
        "content_profile": "form-centric with labeled fields, checkboxes, structured input areas",
        "policy_id": "forms",
        "policy_data": {"doc_type": "form_document", "content_profile": "form-centric", "action": "form_extraction", "origin": "seed"},
        "alpha": 7.0,
        "beta": 3.0,
        "confidence": 0.70,
    },
    {
        "doc_type": "clinical_summary",
        "content_profile": "form-centric with patient demographics, diagnosis codes, structured medical fields",
        "policy_id": "forms",
        "policy_data": {"doc_type": "clinical_summary", "content_profile": "form-centric", "action": "clinical_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    {
        "doc_type": "medical_record",
        "content_profile": "form-centric with patient history, lab results, structured clinical data",
        "policy_id": "forms",
        "policy_data": {"doc_type": "medical_record", "content_profile": "form-centric", "action": "medical_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    # ── scanned_text (3 seeds) ──
    {
        "doc_type": "scanned_document",
        "content_profile": "scanned image requiring OCR, handwritten or printed text on paper",
        "policy_id": "scanned_text",
        "policy_data": {"doc_type": "scanned_document", "content_profile": "scanned", "action": "ocr_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    {
        "doc_type": "text_document",
        "content_profile": "text-heavy with paragraphs, sections, narrative content",
        "policy_id": "scanned_text",
        "policy_data": {"doc_type": "text_document", "content_profile": "text-heavy", "action": "text_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    {
        "doc_type": "legal_document",
        "content_profile": "text-heavy with legal clauses, sections, regulatory language",
        "policy_id": "scanned_text",
        "policy_data": {"doc_type": "legal_document", "content_profile": "text-heavy", "action": "legal_text_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    # ── mixed_content (2 seeds) ──
    {
        "doc_type": "mixed_document",
        "content_profile": "mixed with text paragraphs, embedded tables, and images",
        "policy_id": "mixed_content",
        "policy_data": {"doc_type": "mixed_document", "content_profile": "mixed", "action": "mixed_processing", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    {
        "doc_type": "contract",
        "content_profile": "mixed with legal clauses, signature blocks, schedules, and appendices",
        "policy_id": "mixed_content",
        "policy_data": {"doc_type": "contract", "content_profile": "mixed", "action": "contract_processing", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    # ── default (1 seed, flat prior) ──
    {
        "doc_type": "unknown",
        "content_profile": "unknown document type, unclassified content",
        "policy_id": "default",
        "policy_data": {"doc_type": "unknown", "content_profile": "unknown", "action": "default_processing", "origin": "seed"},
        "alpha": 4.0,
        "beta": 4.0,
        "confidence": 0.50,
    },
]
