"""
Guardrail-specific configuration with comprehensive policy system.
SL-VAT 2026 alignment: standard 18%, zero-rated 0%, exempt support.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Dict, Any


class GuardrailSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    THRESHOLD_FAITHFULNESS: float = Field(0.62, description="Weighted faithfulness threshold")
    LOG_LEVEL: str = Field("INFO")
    POSTGRES_URI: str = Field("", description="PostgreSQL connection URI for audit log persistence")
    EMBEDDER_MODEL: str = Field(default="all-MiniLM-L6-v2")

    # Central POLICIES dictionary for all guardrail checks
    POLICIES: Dict[str, Any] = Field(default_factory=lambda: {
        "relevance": {
            "high_threshold": 0.50,
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
            },
            "blacklist_keywords": ["dummy", "fake", "test data", "demo data"],
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


guardrail_settings = GuardrailSettings()  # type: ignore
