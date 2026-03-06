#!/usr/bin/env python3
"""
demo_test.py – Console demo runner for the peak hallucination guardrails
Shows real-world financial scenarios including SL-VAT variations,
irrelevant fields, PII leaks, suspicious patterns, etc.

Run with:
    python -m hallucination_guardrails.demo_test
"""

import asyncio
import json
from datetime import datetime

from hallucination_guardrails.models import (
    RAGInput,
    DocumentContext,
    DocumentType
)
from hallucination_guardrails.core.ensemble import run_validation_ensemble

print(">>> PEAK VERSION DEMO – Financial Hallucination Guardrails (2026) <<<")
print("    Testing dynamic input, SL-VAT policies, relevance, PII, etc.")
print("=" * 80)


async def run_and_print_case(case_name: str, rag_input: RAGInput):
    print(f"\n{case_name.upper():^80}")
    print("-" * 80)

    start = datetime.now()
    result = await run_validation_ensemble(rag_input)
    duration = (datetime.now() - start).total_seconds() * 1000

    print(f"Overall Pass:      {result.overall_passes}")
    print(f"Hallucination:     {'YES' if result.hallucination_detected else 'NO'}")
    print(f"Risk Level:        {result.risk_level}")
    print(f"Time:              {duration:.1f} ms")
    print(f"Audit ID:          {result.audit_log_id[:8]}…")

    print("\nLayer Results:")
    for r in result.validation_results:
        status = "PASS" if r.is_pass else ("SUSP" if r.score == 0.5 else "FAIL")
        print(f"  {r.name:22} | {status:6} | {r.score:.3f} | {r.details[:90]}{'...' if len(r.details) > 90 else ''}")

    print("\nKey Metrics:")
    print(f"  Guardrails success:   {result.metrics.get('guardrails_success')}")
    print(f"  Hallucination score:  {result.metrics.get('faithfulness_score')}")
    print(f"  Relevance score:      {result.metrics.get('relevance_score')}")
    print(f"  Failed checks:        {result.metrics.get('num_failed_checks')}")
    print(f"  Suspicious checks:    {result.metrics.get('num_suspicious_checks')}")

    print("=" * 80)


async def main():
    cases = [
        # 1. Good standard taxable invoice (18%) – rich source_contexts for high relevance
        (
            "1. Good standard invoice (18% VAT)",
            RAGInput(
                document_context=DocumentContext(
                    doc_type=DocumentType.INVOICE,
                    vendor="ABC Suppliers",
                    quality_bin=None
                ),
                query="Extract invoice details",
                answer_json=json.dumps({
                    "customer_name": "XYZ Traders",
                    "invoice_number": "INV-20260227-001",
                    "date": "2026-02-27",
                    "subtotal": 25000.00,
                    "tax": 4500.00,
                    "total": 29500.00
                }),
                source_contexts=[
                    "Invoice issued to customer XYZ Traders by vendor ABC Suppliers.",
                    "Invoice number INV-20260227-001 dated 2026-02-27.",
                    "Subtotal amount is 25000.00 LKR, tax/VAT calculated at 18% is 4500.00 LKR, grand total 29500.00 LKR."
                ],
                document_id="good-taxable-001"
            )
        ),

        # 2. Zero-rated export – rich source for high relevance
        (
            "2. Zero-rated export invoice",
            RAGInput(
                document_context=DocumentContext(
                    doc_type=DocumentType.INVOICE,
                    vendor=None,
                    quality_bin=None
                ),
                query="Extract export invoice",
                answer_json=json.dumps({
                    "customer_name": "Singapore Importer",
                    "subtotal": 120000.00,
                    "tax": 0.00,
                    "total": 120000.00,
                    "note": "Export of goods – zero rated under section 5"
                }),
                source_contexts=[
                    "Customer Singapore Importer, subtotal 120000.00 LKR.",
                    "Tax/VAT 0.00 because this is an export of goods zero-rated under section 5 of VAT Act.",
                    "Total amount payable 120000.00 LKR, note: Export of goods – zero rated under section 5."
                ],
                document_id="zero-rated-export"
            )
        ),

        # 3. Exempt supply – rich source
        (
            "3. Exempt supply (no tax line)",
            RAGInput(
                document_context=DocumentContext(
                    doc_type=DocumentType.INVOICE,
                    vendor=None,
                    quality_bin=None
                ),
                query="Extract exempt invoice",
                answer_json=json.dumps({
                    "customer_name": "Local School",
                    "subtotal": 8000.00,
                    "total": 8000.00,
                    "description": "Educational service – exempt supply"
                }),
                source_contexts=[
                    "Customer Local School, subtotal 8000.00 LKR, total 8000.00 LKR.",
                    "Description: Educational service – exempt supply under VAT regulations, no tax applicable."
                ],
                document_id="exempt-supply-001"
            )
        ),

        # 4. Suspicious high tax – should FAIL domain_rules
        (
            "4. Suspicious 40% tax rate",
            RAGInput(
                document_context=DocumentContext(
                    doc_type=DocumentType.INVOICE,
                    vendor=None,
                    quality_bin=None
                ),
                query="Extract invoice",
                answer_json=json.dumps({
                    "customer_name": "Test Customer",
                    "subtotal": 100.00,
                    "tax": 40.00,
                    "total": 140.00
                }),
                source_contexts=[
                    "Customer Test Customer, subtotal 100.00 LKR, tax 40.00 LKR, total 140.00 LKR."
                ],
                document_id="suspicious-tax-40"
            )
        ),

        # 5. Irrelevant extra field – should FAIL relevance
        (
            "5. Irrelevant extra field",
            RAGInput(
                document_context=DocumentContext(
                    doc_type=DocumentType.INVOICE,
                    vendor=None,
                    quality_bin=None
                ),
                query="Extract invoice",
                answer_json=json.dumps({
                    "customer_name": "John Doe",
                    "subtotal": 5000.00,
                    "total": 5900.00,
                    "patient_condition": "Stable after checkup"
                }),
                source_contexts=[
                    "Customer John Doe, subtotal 5000.00 LKR, total 5900.00 LKR."
                ],
                document_id="irrelevant-halluc"
            )
        ),

        # 6. PII leakage – should FAIL pii_leakage
        (
            "6. PII leakage (phone + email)",
            RAGInput(
                document_context=DocumentContext(
                    doc_type=DocumentType.INVOICE,
                    vendor=None,
                    quality_bin=None
                ),
                query="Extract invoice",
                answer_json=json.dumps({
                    "customer_name": "Jane Smith",
                    "subtotal": 15000.00,
                    "total": 17700.00,
                    "contact_phone": "0777-123456",
                    "email": "jane@example.com"
                }),
                source_contexts=[
                    "Customer Jane Smith, subtotal 15000.00 LKR, total 17700.00 LKR."
                ],
                document_id="pii-leak-phone-email"
            )
        ),

        # 7. Negative total – should FAIL internal_consistency
        (
            "7. Negative total value",
            RAGInput(
                document_context=DocumentContext(
                    doc_type=DocumentType.RECEIPT,
                    vendor=None,
                    quality_bin=None
                ),
                query="Extract receipt",
                answer_json=json.dumps({
                    "merchant": "Super Mart",
                    "total": -250.00,
                    "date": "2026-02-27"
                }),
                source_contexts=[
                    "Merchant Super Mart issued receipt for total -250.00 LKR on 2026-02-27."
                ],
                document_id="negative-total"
            )
        ),
    ]

    for name, inp in cases:
        await run_and_print_case(name, inp)


if __name__ == "__main__":
    asyncio.run(main())