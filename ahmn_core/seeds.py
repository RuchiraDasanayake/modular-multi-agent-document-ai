"""
LTM seed data for the canonical local-first policy bank.

This seed set is aligned with:
  - configs/policy_store_research.json
  - the default IDPO research runtime
  - the free local-first product direction

Optional paid cloud policies live in configs/policy_store_cloud_extensions.json
and are intentionally not seeded here.

Policy mappings:
  table_heavy / table_dense_local -> invoice, receipt, financial_statement, table_document
  forms / forms_rescue_local      -> form_document, clinical_summary, medical_record
  noisy_ocr_rescue / noisy_ocr_precision_local -> noisy invoice-like OCR contexts
  scanned_text          -> scanned_document
  mixed_content         -> mixed_document, contract
  long_document_chunked -> long heavy-route contracts
  fast_local_text       -> text_document
  default/unknown_vendor_safe -> unknown catch-all
"""

LTM_SEEDS = [
    {
        "doc_type": "invoice",
        "content_profile": "table-heavy",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "invoice", "content_profile": "table-heavy", "action": "invoice_processing", "origin": "seed"},
        "alpha": 9.0,
        "beta": 2.0,
        "confidence": 0.82,
    },
    {
        "doc_type": "invoice",
        "content_profile": "table-heavy",
        "policy_id": "table_dense_local",
        "policy_data": {"doc_type": "invoice", "content_profile": "table-heavy", "action": "invoice_processing_dense_local", "origin": "seed"},
        "alpha": 5.0,
        "beta": 4.0,
        "confidence": 0.56,
    },
    {
        "doc_type": "table_document",
        "content_profile": "table-heavy",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "table_document", "content_profile": "table-heavy", "action": "table_extraction", "origin": "seed"},
        "alpha": 8.0,
        "beta": 3.0,
        "confidence": 0.73,
    },
    {
        "doc_type": "table_document",
        "content_profile": "table-heavy",
        "policy_id": "table_dense_local",
        "policy_data": {"doc_type": "table_document", "content_profile": "table-heavy", "action": "table_extraction_dense_local", "origin": "seed"},
        "alpha": 5.0,
        "beta": 4.0,
        "confidence": 0.56,
    },
    {
        "doc_type": "receipt",
        "content_profile": "table-heavy",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "receipt", "content_profile": "table-heavy", "action": "receipt_processing", "origin": "seed"},
        "alpha": 7.0,
        "beta": 3.0,
        "confidence": 0.70,
    },
    {
        "doc_type": "receipt",
        "content_profile": "table-heavy",
        "policy_id": "table_dense_local",
        "policy_data": {"doc_type": "receipt", "content_profile": "table-heavy", "action": "receipt_processing_dense_local", "origin": "seed"},
        "alpha": 4.5,
        "beta": 4.0,
        "confidence": 0.53,
    },
    {
        "doc_type": "form_document",
        "content_profile": "form-centric",
        "policy_id": "forms",
        "policy_data": {"doc_type": "form_document", "content_profile": "form-centric", "action": "form_extraction", "origin": "seed"},
        "alpha": 7.0,
        "beta": 3.0,
        "confidence": 0.70,
    },
    {
        "doc_type": "form_document",
        "content_profile": "form-centric",
        "policy_id": "forms_rescue_local",
        "policy_data": {"doc_type": "form_document", "content_profile": "form-centric", "action": "form_extraction_rescue_local", "origin": "seed"},
        "alpha": 5.0,
        "beta": 4.0,
        "confidence": 0.56,
    },
    {
        "doc_type": "scanned_document",
        "content_profile": "scanned",
        "policy_id": "scanned_text",
        "policy_data": {"doc_type": "scanned_document", "content_profile": "scanned", "action": "ocr_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 4.0,
        "confidence": 0.60,
    },
    {
        "doc_type": "mixed_document",
        "content_profile": "mixed",
        "policy_id": "mixed_content",
        "policy_data": {"doc_type": "mixed_document", "content_profile": "mixed", "action": "mixed_processing", "origin": "seed"},
        "alpha": 5.0,
        "beta": 3.0,
        "confidence": 0.63,
    },
    {
        "doc_type": "contract",
        "content_profile": "mixed",
        "policy_id": "mixed_content",
        "policy_data": {"doc_type": "contract", "content_profile": "mixed", "action": "contract_processing", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    {
        "doc_type": "financial_statement",
        "content_profile": "table-heavy",
        "policy_id": "table_heavy",
        "policy_data": {"doc_type": "financial_statement", "content_profile": "table-heavy", "action": "financial_extraction", "origin": "seed"},
        "alpha": 7.0,
        "beta": 4.0,
        "confidence": 0.64,
    },
    {
        "doc_type": "text_document",
        "content_profile": "text-heavy",
        "policy_id": "fast_local_text",
        "policy_data": {"doc_type": "text_document", "content_profile": "text-heavy", "action": "fast_text_extraction", "origin": "seed"},
        "alpha": 7.0,
        "beta": 3.0,
        "confidence": 0.71,
    },
    {
        "doc_type": "clinical_summary",
        "content_profile": "form-centric",
        "policy_id": "forms",
        "policy_data": {"doc_type": "clinical_summary", "content_profile": "form-centric", "action": "clinical_extraction", "origin": "seed"},
        "alpha": 6.0,
        "beta": 3.0,
        "confidence": 0.67,
    },
    {
        "doc_type": "clinical_summary",
        "content_profile": "form-centric",
        "policy_id": "forms_rescue_local",
        "policy_data": {"doc_type": "clinical_summary", "content_profile": "form-centric", "action": "clinical_extraction_rescue_local", "origin": "seed"},
        "alpha": 4.8,
        "beta": 4.0,
        "confidence": 0.55,
    },
    {
        "doc_type": "unknown",
        "content_profile": "unknown",
        "policy_id": "unknown_vendor_safe",
        "policy_data": {"doc_type": "unknown", "content_profile": "unknown", "action": "safe_unknown_processing", "origin": "seed"},
        "alpha": 4.0,
        "beta": 4.0,
        "confidence": 0.50,
    },
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
        "doc_type": "medical_record",
        "content_profile": "form-centric",
        "policy_id": "forms_rescue_local",
        "policy_data": {"doc_type": "medical_record", "content_profile": "form-centric", "action": "medical_extraction_rescue_local", "origin": "seed"},
        "alpha": 4.5,
        "beta": 4.2,
        "confidence": 0.52,
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
        "doc_type": "invoice",
        "content_profile": "table-heavy",
        "policy_id": "noisy_ocr_precision_local",
        "policy_data": {"doc_type": "invoice", "content_profile": "table-heavy", "action": "noisy_invoice_precision_local", "origin": "seed"},
        "alpha": 4.6,
        "beta": 4.1,
        "confidence": 0.54,
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
