"""
PEAK UPGRADE – All thresholds, policies, allowed lists are here.
Everything is overridable via .env or external JSON later.
SL-VAT 2026 alignment: standard 18%, zero-rated 0%, exempt support.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Dict, Any


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore'
    )

    LOG_LEVEL: str = Field(default="INFO")
    EMBEDDER_MODEL: str = Field(default="all-mpnet-base-v2")
    FAITHFULNESS_THRESHOLD: float = Field(default=0.62)

    # Central POLICIES dictionary – heart of dynamism
    POLICIES: Dict[str, Any] = Field(default_factory=lambda: {
        "relevance": {
            "high_threshold": 0.50,         # Lowered for demo – raise to 0.75 later
            "medium_threshold": 0.35,
            "keyword_boost": 0.35,
            "expected_fields": {
                "Invoice": ["customer_name", "invoice_number", "date", "subtotal", "tax", "vat", "total", "items", "discount"],
                "Receipt": ["merchant", "date", "total", "items"],
                "PurchaseOrder": ["po_number", "supplier", "date", "total_amount", "items"],
                "BankStatement": ["account_holder", "bank_name", "account_number", "balance", "date", "transactions"],
                "InsuranceClaim": ["policy_number", "claimant_name", "claim_date", "claim_amount", "status"],
            },
            "financial_keywords": ["total", "subtotal", "tax", "vat", "amount", "balance", "claim", "invoice", "receipt", "po", "lkr"],
        },

        "domain_rules": {
            "tax": {
                "default": {
                    "allowed_rates": [0.0, 18.0],
                    "min_rate": 0.0,
                    "max_rate": 18.0,
                    "tolerance_pct": 0.5,
                    "zero_rated_keywords": [
                        "export", "zero-rated", "zero rated", "exempt", "nil vat", "section 5",
                        "reinsurance", "international transport", "export of goods", "zero-rated supply", "exempt supply"
                    ]
                },
                "Invoice": {
                    "allowed_rates": [0.0, 18.0],
                    "min_rate": 0.0,
                    "max_rate": 18.0,
                    "tolerance_pct": 0.5,
                    "zero_rated_keywords": ["export", "zero rated", "section 5 vat act", "exempt supply"]
                },
                "Receipt": {
                    "allowed_rates": [0.0, 18.0],
                    "min_rate": 0.0,
                    "max_rate": 18.0,
                    "tolerance_pct": 0.5,
                },
                "PurchaseOrder": {
                    "allowed_rates": [0.0, 18.0],
                    "min_rate": 0.0,
                    "max_rate": 18.0,
                    "tolerance_pct": 0.5,
                },
                "BankStatement": {
                    "allowed_rates": [0.0],
                    "min_rate": 0.0,
                    "max_rate": 18.0,
                    "tolerance_pct": 0.5,
                },
                "InsuranceClaim": {
                    "allowed_rates": [0.0, 18.0],
                    "min_rate": 0.0,
                    "max_rate": 18.0,
                    "tolerance_pct": 0.5,
                },
            },
            "blacklist_keywords": ["test", "sample", "dummy", "fake", "demo", "placeholder"],
            "large_amount_thresholds": {
                "Invoice": 1000000.0,
                "Receipt": 50000.0,
                "PurchaseOrder": 5000000.0,
                "InsuranceClaim": 1000000.0,
            },
        },

        "pii_leakage": {
            "allowed_entities": {
                "Invoice": ["PERSON", "ORG", "MONEY", "DATE_TIME", "PERCENT", "LOCATION", "CARDINAL"],
                "Receipt": ["PERSON", "ORG", "MONEY", "DATE_TIME", "LOCATION"],
                "PurchaseOrder": ["PERSON", "ORG", "MONEY", "DATE_TIME"],
                "BankStatement": ["PERSON", "ORG", "MONEY", "DATE_TIME", "CARDINAL"],
                "InsuranceClaim": ["PERSON", "ORG", "MONEY", "DATE_TIME"],
            },
            "min_confidence": 0.70,
        },

        "faithfulness": {
            "semantic_weight": 0.50,
            "numerical_weight": 0.40,
            "entity_weight": 0.10,
            "field_importance": {
                "total": 1.5, "subtotal": 1.4, "tax": 1.3, "vat": 1.3,
                "balance": 1.4, "claim_amount": 1.5, "default": 1.0
            },
            "numerical_tolerance": {
                "amount": 0.001,
                "tax": 0.01,
                "default": 0.005
            }
        },

        "internal_consistency": {
            "math_tolerance": 0.05,
            "date_future_allowed": False,
        }
    })


# Instantiate settings
settings = Settings()