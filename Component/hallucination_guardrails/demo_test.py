#!/usr/bin/env python3
import asyncio
import json
from datetime import datetime
import uuid
from hallucination_guardrails.models import RAGInput, DocumentContext, DocumentType
from hallucination_guardrails.core.ensemble import run_validation_ensemble

print(">>> THIS IS THE CORRECT UPDATED VERSION - DEMO_TEST.PY LOADED SUCCESSFULLY <<<")

async def main():
    print("Testing Hallucination Guardrails")
    print("=" * 60)
    
    good = RAGInput(
        document_context=DocumentContext(
            doc_type=DocumentType.CLINICAL_SUMMARY,
            vendor=None,
            quality_bin=None
        ),
        query="Summarize patient condition",
        answer_json='{"patient_name": "John Doe", "condition": "Stable", "summary": "Routine checkup, no issues", "next_steps": "Follow-up in 6 months"}',
        source_contexts=["Patient John Doe is stable with no issues noted."],
        document_id="1"
    )
    
    bad = RAGInput(
        document_context=DocumentContext(
            doc_type=DocumentType.INVOICE,
            vendor="VendorX",
            quality_bin=None
        ),
        query="Extract invoice details",
        answer_json='{"customer_name": "Jane Smith", "subtotal": 100, "tax": 10, "total": 120}',
        source_contexts=["Subtotal 100, tax 10, total 110"],
        document_id="2"
    )
    
    future_date = RAGInput(
        document_context=DocumentContext(
            doc_type=DocumentType.RECEIPT,
            vendor=None,
            quality_bin=None
        ),
        query="Extract receipt",
        answer_json='{"merchant": "StoreY", "total": 50, "date": "2026-01-01", "items": ["Item1"]}',
        source_contexts=["Date 2026-01-01, total 50"],
        document_id="3"
    )
    
    negative_total = RAGInput(
        document_context=DocumentContext(
            doc_type=DocumentType.INVOICE,
            vendor="ABC Shop",
            quality_bin=None
        ),
        query="Extract invoice details",
        answer_json='{"customer_name": "Jane Smith", "subtotal": 100, "tax": 10, "total": -5}',
        source_contexts=["Subtotal 100, tax 10, total 110"],
        document_id="negative_test"
    )

    empty_merchant = RAGInput(
        document_context=DocumentContext(
            doc_type=DocumentType.RECEIPT,
            vendor=None,
            quality_bin=None
        ),
        query="Extract receipt",
        answer_json='{"merchant": "   ", "total": 50, "date": "2025-01-01", "items": ["Item1"]}',
        source_contexts=["Receipt from StoreY, total 50, date 2025-01-01"],
        document_id="empty_test"
    )

    # NEW: Test case that triggers tax plausibility + keyword suspicion
    suspicious_tax = RAGInput(
        document_context=DocumentContext(
            doc_type=DocumentType.INVOICE,
            vendor="Expected Vendor Ltd",  # also triggers vendor mismatch if name differs
            quality_bin=None
        ),
        query="Extract invoice details",
        answer_json='{"customer_name": "Test Customer", "subtotal": 100, "tax": 40, "total": 140}',  # 40% tax + keyword "Test"
        source_contexts=["Subtotal 100, tax 40, total 140"],
        document_id="suspicious_tax_test"
    )

    cases = [good, bad, future_date, negative_total, empty_merchant, suspicious_tax]
    
    for case in cases:
        results = await run_validation_ensemble(case)
        print(f"\nDocument ID: {case.document_id} -> {len(results)} checks run")
        for r in results:
            print(f"  {r.name}: {'PASS' if r.is_pass else 'FAIL'} - {r.details}")
        
        # Simulated full JSON response – safe serialization
        simulated_response = {
            "rag_input": case.model_dump(),
            "validation_results": [r.model_dump() for r in results],
            "overall_passes": all(r.is_pass for r in results),
            "audit_log_id": str(uuid.uuid4()),
            "processing_time_ms": 842.1,
            "timestamp": datetime.now().isoformat(),
            "advice_id": str(uuid.uuid4()),
            "metrics": {
                "guardrails_success": all(r.is_pass for r in results),
                "num_failed_checks": sum(1 for r in results if not r.is_pass),
                "faithfulness_avg_score": next((r.score for r in results if r.name == "faithfulness"), None),
                "schema_adherence_score": next((r.score for r in results if r.name == "schema_adherence"), None),
                "consistency_score": next((r.score for r in results if r.name == "internal_consistency"), None),
                "domain_rules_score": next((r.score for r in results if r.name == "domain_rules"), None),
                "pii_leakage_score": next((r.score for r in results if r.name == "pii_leakage"), None),
                "cost": 0.0,
                "processing_time_ms": 842.1
            }
        }
        
        print("\nDemo Full JSON Response (simulated):")
        print(json.dumps(simulated_response, indent=2, default=str))

if __name__ == "__main__":
    asyncio.run(main())