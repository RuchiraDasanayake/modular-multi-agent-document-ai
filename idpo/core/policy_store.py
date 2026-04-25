"""Document processing policy storage, selection, and override logic."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from idpo.core.types import DAEOutput, Document, PolicyDefinition

class PolicyStore:
    def __init__(self, path: str | None, default_policy_id: str = "default") -> None:
        self.path = Path(path) if path else None
        self.default_policy_id = default_policy_id
        self.policies = self._load()
        self._policy_map = {policy.policy_id: policy for policy in self.policies}

    def select_policy(
        self,
        dae_output: DAEOutput | None,
        doc: Document | None = None,
    ) -> tuple[PolicyDefinition, str]:
        policy_id = doc.metadata.get("policy_id") if doc else None
        if policy_id and policy_id in self._policy_map:
            return self._policy_map[policy_id], "metadata"

        for policy in self.policies:
            if self._matches(policy.conditions, dae_output, doc):
                return policy, "match"

        fallback = self._policy_map.get(self.default_policy_id)
        if fallback:
            return fallback, "default"
        return self.policies[0], "fallback"

    def to_payload(self, policy: PolicyDefinition, reason: str) -> dict[str, object]:
        payload = asdict(policy)
        payload["selection_reason"] = reason
        return payload

    def matches_policy(
        self,
        policy: PolicyDefinition,
        dae_output: DAEOutput | None,
        doc: Document | None = None,
    ) -> bool:
        return self._matches(policy.conditions, dae_output, doc)

    def matching_policies(
        self,
        dae_output: DAEOutput | None,
        doc: Document | None = None,
    ) -> list[PolicyDefinition]:
        return [
            policy
            for policy in self.policies
            if self._matches(policy.conditions, dae_output, doc)
        ]

    def _load(self) -> list[PolicyDefinition]:
        if self.path and self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("default_policy_id"):
                self.default_policy_id = str(data.get("default_policy_id") or self.default_policy_id)
            items = data.get("policies", data)
            if isinstance(items, dict):
                items = [items]
            policies = [self._policy_from_dict(item) for item in items if item]
            if policies:
                return self._ensure_default(policies)
        return [self._default_policy()]

    def _ensure_default(self, policies: Iterable[PolicyDefinition]) -> list[PolicyDefinition]:
        policies_list = list(policies)
        if any(policy.policy_id == self.default_policy_id for policy in policies_list):
            return policies_list
        policies_list.append(self._default_policy())
        return policies_list

    def _policy_from_dict(self, payload: dict[str, object]) -> PolicyDefinition:
        if "actions" in payload or "conditions" in payload:
            conditions = payload.get("conditions", {}) if isinstance(payload.get("conditions"), dict) else {}
            actions = payload.get("actions", {}) if isinstance(payload.get("actions"), dict) else {}
            metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
            return PolicyDefinition(
                policy_id=str(payload.get("policy_id", "default")),
                name=str(payload.get("name", payload.get("policy_id", "default"))),
                conditions=conditions,
                actions=actions,
                metadata=metadata,
            )

        preprocess = payload.get("preprocess", {}) if isinstance(payload.get("preprocess"), dict) else {}
        matches = payload.get("matches", {}) if isinstance(payload.get("matches"), dict) else {}
        metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        actions = {
            "preprocess": preprocess,
            "extraction": {
                "explicit_entities": [str(item) for item in payload.get("explicit_entities", [])],
                "model_tier": payload.get("model_preference"),
            },
        }
        return PolicyDefinition(
            policy_id=str(payload.get("policy_id", "default")),
            name=str(payload.get("name", payload.get("policy_id", "default"))),
            conditions={key: list(values) for key, values in matches.items() if isinstance(values, list)},
            actions=actions,
            metadata=metadata,
        )

    def _default_policy(self) -> PolicyDefinition:
        return PolicyDefinition(policy_id="default", name="Default Policy")

    def _matches(
        self,
        conditions: dict[str, object],
        dae_output: DAEOutput | None,
        doc: Document | None,
    ) -> bool:
        if not conditions:
            return False
        value_map: dict[str, object] = {}
        if dae_output:
            value_map.update(
                {
                    "doc_type": dae_output.doc_type,
                    "vendor_cluster": dae_output.vendor_cluster,
                    "semantic_doc_type": getattr(dae_output, "semantic_doc_type", None),
                    "layout_cluster_id": dae_output.layout_cluster_id,
                    "quality_bin": dae_output.quality_bin,
                    "complexity_bin": dae_output.complexity_bin,
                    "content_profile": dae_output.content_profile,
                    "route_bin": dae_output.route_bin,
                    "quality_score": dae_output.quality_score,
                    "complexity_score": dae_output.complexity_score,
                }
            )
            for key, value in dae_output.quality_features.items():
                value_map[f"quality_features.{key}"] = value
            for key, value in dae_output.structural_features.items():
                value_map[f"structural_features.{key}"] = value
            for key, value in dae_output.signals.items():
                value_map[f"signals.{key}"] = value
        if doc:
            value_map.update(
                {
                    "profile": doc.profile,
                    "source": doc.source,
                }
            )
            value_map.update({key: doc.metadata.get(key) for key in doc.metadata})
        for key, expectation in conditions.items():
            current = value_map.get(key)
            if isinstance(expectation, dict):
                if current is None:
                    return False
                if "min" in expectation and current is not None and current < expectation["min"]:
                    return False
                if "max" in expectation and current is not None and current > expectation["max"]:
                    return False
                if "equals" in expectation and current != expectation["equals"]:
                    return False
                continue
            if isinstance(expectation, list):
                if current is None or current not in expectation:
                    return False
                continue
            if current != expectation:
                return False
        return True
