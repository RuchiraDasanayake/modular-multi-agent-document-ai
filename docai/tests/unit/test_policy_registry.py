from pathlib import Path

import pytest

from docai_core.policies.registry import PolicyRegistry


def test_can_load_invoice_extraction_family() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry = PolicyRegistry(repo_root / "configs" / "policies")
    family = registry.load_family("invoice_extraction")
    assert family["family_id"] == "invoice_extraction"


def test_can_load_receipt_extraction_family() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry = PolicyRegistry(repo_root / "configs" / "policies")
    family = registry.load_family("receipt_extraction")
    assert family["family_id"] == "receipt_extraction"


def test_can_load_noisy_scan_rescue_family() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry = PolicyRegistry(repo_root / "configs" / "policies")
    family = registry.load_family("noisy_scan_rescue")
    assert family["family_id"] == "noisy_scan_rescue"


def test_can_list_policy_families() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry = PolicyRegistry(repo_root / "configs" / "policies")
    families = registry.list_policy_families()
    assert "invoice_extraction" in families
    assert "receipt_extraction" in families
    assert "noisy_scan_rescue" in families


def test_can_list_variants() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry = PolicyRegistry(repo_root / "configs" / "policies")
    variants = registry.list_variants("invoice_extraction")
    assert len(variants) >= 1


def test_each_variant_contains_required_explanatory_fields() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry = PolicyRegistry(repo_root / "configs" / "policies")
    for family_id in registry.list_policy_families():
        variants = registry.list_variants(family_id)
        for variant in variants:
            assert variant.get("user_facing_name")
            assert variant.get("description")
            assert variant.get("best_for")
            assert variant.get("changes_summary")
            assert variant.get("tradeoffs")


def test_invalid_family_raises_clear_error(tmp_path: Path) -> None:
    registry = PolicyRegistry(tmp_path)
    with pytest.raises(ValueError, match="Policy family not found"):
        registry.load_family("missing_family")

