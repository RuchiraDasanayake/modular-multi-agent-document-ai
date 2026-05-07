from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import (
    AvailableTool,
    AvailableTools,
    DisabledCandidate,
    DocumentProfile,
    ExtractionSchema,
    SelectedPolicy,
)
from docai_core.policies.registry import PolicyRegistry


@dataclass(slots=True)
class StrategyAssigner:
    registry: PolicyRegistry

    def assign_strategy(
        self,
        schema: ExtractionSchema,
        document_profile: DocumentProfile,
        available_tools: AvailableTools,
    ) -> SelectedPolicy:
        families = self._load_all_families()
        variants = self._build_variant_index(families)
        available_capabilities = self._collect_capabilities(available_tools)

        ordered_candidates = self._candidate_order(schema, document_profile)
        disabled_candidates: list[DisabledCandidate] = []

        for policy_id in ordered_candidates:
            variant = variants.get(policy_id)
            if not variant:
                continue
            ok, reason = self._is_compatible(variant, available_capabilities)
            if ok:
                confidence, human_reason = self._selection_reason(policy_id, schema, document_profile)
                return SelectedPolicy(
                    policy_id=policy_id,
                    policy_family=self._family_for_policy(families, policy_id),
                    policy_version=str(variant["version"]),
                    selected_by="deterministic_strategy_assigner",
                    confidence=confidence,
                    reasons=[human_reason],
                    disabled_candidates=disabled_candidates,
                )
            disabled_candidates.append(DisabledCandidate(policy_id=policy_id, reason_disabled=reason))

        raise ValueError(
            f"No compatible extraction strategy found for document '{document_profile.document_id}'. "
            f"Disabled candidates: {disabled_candidates}"
        )

    def _load_all_families(self) -> list[dict]:
        return [self.registry.load_family(family_id) for family_id in self.registry.list_policy_families()]

    def _build_variant_index(self, families: list[dict]) -> dict[str, dict]:
        index: dict[str, dict] = {}
        for family in families:
            for variant in family.get("variants", []):
                index[variant["policy_id"]] = variant
        return index

    def _collect_capabilities(self, available_tools: AvailableTools) -> set[str]:
        capabilities: set[str] = set()
        all_tool_groups = [
            available_tools.available_ocr_engines,
            available_tools.available_parsers,
            available_tools.available_models,
            available_tools.available_validators,
            available_tools.available_recovery_strategies,
        ]
        for group in all_tool_groups:
            for tool in group:
                if self._tool_enabled(tool):
                    capabilities.update(tool.capabilities)
        return capabilities

    def _tool_enabled(self, tool: AvailableTool) -> bool:
        return bool(tool.enabled)

    def _candidate_order(self, schema: ExtractionSchema, document_profile: DocumentProfile) -> list[str]:
        if document_profile.quality_bin == "low":
            return [
                "noisy_scan_rescue_v1",
                "invoice_table_heavy_local_v1",
                "receipt_basic_local_v1",
                "invoice_basic_local_v1",
            ]
        if len(schema.tables) > 0 and document_profile.layout_type == "table_heavy":
            return [
                "invoice_table_heavy_local_v1",
                "invoice_basic_local_v1",
                "receipt_basic_local_v1",
                "noisy_scan_rescue_v1",
            ]
        if document_profile.detected_type == "receipt":
            return [
                "receipt_basic_local_v1",
                "invoice_basic_local_v1",
                "noisy_scan_rescue_v1",
                "invoice_table_heavy_local_v1",
            ]
        return [
            "invoice_basic_local_v1",
            "invoice_table_heavy_local_v1",
            "receipt_basic_local_v1",
            "noisy_scan_rescue_v1",
        ]

    def _is_compatible(self, variant: dict, available_capabilities: set[str]) -> tuple[bool, str]:
        requires = variant.get("requires")
        if not requires:
            return True, ""

        if isinstance(requires, list):
            missing = [cap for cap in requires if cap not in available_capabilities]
            if missing:
                return (
                    False,
                    f"Requires {', '.join(missing)}, but available capabilities are {sorted(available_capabilities)}.",
                )
            return True, ""

        if isinstance(requires, dict):
            all_of = requires.get("all_of", [])
            any_of = requires.get("any_of", [])

            missing_all = [cap for cap in all_of if cap not in available_capabilities]
            if missing_all:
                return (
                    False,
                    f"Requires all_of {missing_all}, but available capabilities are {sorted(available_capabilities)}.",
                )

            if any_of:
                found_any = any(cap in available_capabilities for cap in any_of)
                if not found_any:
                    return (
                        False,
                        f"Requires {' or '.join(any_of)}, but available capabilities are {sorted(available_capabilities)}.",
                    )
            return True, ""

        return False, "Invalid requires format."

    def _family_for_policy(self, families: list[dict], policy_id: str) -> str:
        for family in families:
            for variant in family.get("variants", []):
                if variant.get("policy_id") == policy_id:
                    return family.get("family_id", "unknown")
        return "unknown"

    def _selection_reason(
        self,
        policy_id: str,
        schema: ExtractionSchema,
        document_profile: DocumentProfile,
    ) -> tuple[float, str]:
        if policy_id == "noisy_scan_rescue_v1":
            return 0.95, "Document quality is low, so Noisy Scan Rescue was selected."
        if policy_id == "invoice_table_heavy_local_v1":
            return 0.93, "The schema includes tables and the document layout is table-heavy."
        if policy_id == "receipt_basic_local_v1":
            return 0.92, "Document type is receipt, so Basic Receipt Extraction was selected."
        return 0.85, "No stronger matching strategy was needed, so Basic Invoice Extraction was selected."
