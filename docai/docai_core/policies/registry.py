from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PolicyRegistry:
    def __init__(self, policy_dir: str | Path) -> None:
        self.policy_dir = Path(policy_dir)
        self.policy_dir.mkdir(parents=True, exist_ok=True)

    def list_policy_families(self) -> list[str]:
        return sorted(path.stem for path in self.policy_dir.glob("*.json"))

    def family_path(self, family_id: str) -> Path:
        return self.policy_dir / f"{family_id}.json"

    def load_family(self, family_id: str) -> dict:
        path = self.family_path(family_id)
        if not path.exists():
            raise ValueError(f"Policy family not found: {family_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        self._validate_family(data)
        return data

    def save_family(self, family_data: dict) -> Path:
        self._validate_family(family_data)
        family_id = family_data["family_id"]
        path = self.family_path(family_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(family_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def list_variants(self, family_id: str) -> list[dict]:
        family = self.load_family(family_id)
        return list(family["variants"])

    def _validate_family(self, data: dict[str, Any]) -> None:
        required_family_keys = ["family_id", "family_name", "description", "user_facing_name", "variants"]
        for key in required_family_keys:
            if key not in data or data[key] in (None, ""):
                raise ValueError(f"Invalid policy family: '{key}' is required")

        if not isinstance(data["variants"], list):
            raise ValueError("Invalid policy family: 'variants' must be a list")

        required_variant_keys = [
            "policy_id",
            "strategy_name",
            "user_facing_name",
            "version",
            "status",
            "description",
            "best_for",
            "not_recommended_for",
            "tradeoffs",
            "changes_summary",
            "applies_to",
            "requires",
            "preprocessing",
            "ocr",
            "model",
            "extraction",
            "validation",
            "recovery",
            "user_explanation",
            "technical_notes",
        ]
        for idx, variant in enumerate(data["variants"]):
            if not isinstance(variant, dict):
                raise ValueError(f"Invalid variant at index {idx}: must be an object")
            for key in required_variant_keys:
                if key not in variant:
                    raise ValueError(f"Invalid variant '{variant.get('policy_id', idx)}': '{key}' is required")
            if not variant.get("user_facing_name"):
                raise ValueError(f"Invalid variant '{variant.get('policy_id', idx)}': user_facing_name is required")

