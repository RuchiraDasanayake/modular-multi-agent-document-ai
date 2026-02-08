"""
Database Seeding Script for AHMN
Populates initial policy configurations into LTM (Long-Term Memory)
Run this ONCE after setting up the database to bootstrap the system.
"""

import asyncio
import sys
import os
import json
import hashlib

# Add ahmn_core root to path (parent of utils/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import DatabasePool
from app.services.embedding import EmbeddingService


# Initial Policy Configurations
# Add your OCR/processing policies here with their optimal parameters
INITIAL_POLICIES = [
    # Tesseract OCR Policies
    {
        "context": {"doc_type": "invoice", "vendor": "generic"},
        "policy_id": "ocr_tesseract",
        "policy_data": {
            "engine": "tesseract",
            "lang": "eng",
            "psm": 6,  # Assume uniform block of text
            "oem": 3,  # Default OCR Engine Mode
            "timeout": 5000
        },
        "alpha": 10.0,  # Initial success count (prior knowledge)
        "beta": 3.0,    # Initial failure count
    },
    {
        "context": {"doc_type": "receipt", "vendor": "generic"},
        "policy_id": "ocr_tesseract",
        "policy_data": {
            "engine": "tesseract",
            "lang": "eng",
            "psm": 11,  # Sparse text, find as much as possible
            "oem": 3,
            "timeout": 5000
        },
        "alpha": 8.0,
        "beta": 4.0,
    },
    {
        "context": {"doc_type": "contract", "vendor": "generic"},
        "policy_id": "ocr_tesseract",
        "policy_data": {
            "engine": "tesseract",
            "lang": "eng",
            "psm": 3,  # Fully automatic page segmentation
            "oem": 3,
            "timeout": 10000
        },
        "alpha": 7.0,
        "beta": 5.0,
    },
    
    # EasyOCR Policies
    {
        "context": {"doc_type": "invoice", "vendor": "generic"},
        "policy_id": "ocr_easyocr",
        "policy_data": {
            "engine": "easyocr",
            "languages": ["en"],
            "gpu": False,
            "detail": 1,
            "paragraph": False
        },
        "alpha": 9.0,
        "beta": 3.0,
    },
    {
        "context": {"doc_type": "receipt", "vendor": "generic"},
        "policy_id": "ocr_easyocr",
        "policy_data": {
            "engine": "easyocr",
            "languages": ["en"],
            "gpu": False,
            "detail": 1,
            "paragraph": True
        },
        "alpha": 12.0,
        "beta": 2.0,
    },
    
    # Azure Computer Vision Policies
    {
        "context": {"doc_type": "invoice", "vendor": "generic"},
        "policy_id": "azure_cv",
        "policy_data": {
            "engine": "azure_cv",
            "api_version": "2023-04-15",
            "features": ["read"],
            "language": "en",
            "timeout": 15000
        },
        "alpha": 11.0,
        "beta": 2.0,
    },
    
    # Vendor-Specific Policies (Examples)
    {
        "context": {"doc_type": "invoice", "vendor": "acme_corp"},
        "policy_id": "ocr_tesseract",
        "policy_data": {
            "engine": "tesseract",
            "lang": "eng",
            "psm": 6,
            "oem": 3,
            "dpi": 300,  # Vendor-specific: ACME uses high-res scans
            "timeout": 5000
        },
        "alpha": 15.0,  # Higher confidence - we know this works well
        "beta": 2.0,
    },
    {
        "context": {"doc_type": "invoice", "vendor": "beta_inc"},
        "policy_id": "ocr_easyocr",
        "policy_data": {
            "engine": "easyocr",
            "languages": ["en"],
            "gpu": False,
            "detail": 1,
            "contrast_ths": 0.3,  # Vendor-specific: Beta Inc has low contrast docs
            "adjust_contrast": 0.7
        },
        "alpha": 13.0,
        "beta": 3.0,
    },
    
    # Default Fallback Policy
    {
        "context": {"doc_type": "default", "vendor": None},
        "policy_id": "default_policy",
        "policy_data": {
            "engine": "basic",
            "action": "standard_processing",
            "fallback": True
        },
        "alpha": 5.0,
        "beta": 5.0,  # Neutral prior
    },
]


async def seed_database():
    """Populate LTM with initial policy configurations."""
    print("=" * 60)
    print("AHMN Database Seeding")
    print("=" * 60)
    print(f"Seeding {len(INITIAL_POLICIES)} initial policies...\n")
    
    pool = await DatabasePool.get_pool()
    embedding_service = EmbeddingService()
    
    inserted_count = 0
    skipped_count = 0

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for idx, policy_config in enumerate(INITIAL_POLICIES, 1):
                context = policy_config["context"]
                doc_type = context.get("doc_type", "unknown")
                vendor = context.get("vendor")
                
                # Generate context string and embedding
                context_str = embedding_service.create_context_string(doc_type, vendor)
                context_hash = hashlib.sha256(context_str.encode('utf-8')).hexdigest()
                embedding = embedding_service.generate_embedding(context_str)
                
                # Check if already exists
                check_query = "SELECT id FROM ltm_validated_policies WHERE context_hash = %s"
                await cur.execute(check_query, (context_hash,))
                existing = await cur.fetchone()
                
                if existing:
                    print(f"[{idx}/{len(INITIAL_POLICIES)}] SKIP: {context_str} (already exists)")
                    skipped_count += 1
                    continue
                
                # Insert new policy
                insert_query = """
                    INSERT INTO ltm_validated_policies (
                        context_hash,
                        context_embedding,
                        policy_id,
                        policy_data,
                        validation_metrics,
                        alpha,
                        beta,
                        confidence_score,
                        last_promoted_at
                    ) VALUES (
                        %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, NOW()
                    )
                """
                
                validation_metrics = {
                    "source": "manual_seed",
                    "description": "Initial bootstrap configuration"
                }
                
                await cur.execute(insert_query, (
                    context_hash,
                    embedding,
                    policy_config["policy_id"],
                    json.dumps(policy_config["policy_data"]),
                    json.dumps(validation_metrics),
                    policy_config["alpha"],
                    policy_config["beta"],
                    1.0  # confidence_score
                ))
                
                print(f"[{idx}/{len(INITIAL_POLICIES)}] ✓ Inserted: {context_str} → {policy_config['policy_id']}")
                print(f"              Alpha: {policy_config['alpha']}, Beta: {policy_config['beta']}")
                inserted_count += 1
            
            await conn.commit()
    
    await DatabasePool.close_pool()
    
    print("\n" + "=" * 60)
    print(f"Seeding Complete!")
    print(f"  Inserted: {inserted_count}")
    print(f"  Skipped:  {skipped_count}")
    print(f"  Total:    {len(INITIAL_POLICIES)}")
    print("=" * 60)
    print("\nYour AHMN system is now ready to use!")
    print("Start the API server with: python main.py")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed_database())
