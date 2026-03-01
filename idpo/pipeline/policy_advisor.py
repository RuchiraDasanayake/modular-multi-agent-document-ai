from __future__ import annotations

import importlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from idpo.core.config import PipelineConfig
from idpo.core.policy_store import PolicyStore
from idpo.core.types import DAEOutput, PolicyDefinition, SystemConstraints


@dataclass(frozen=True)
class PolicyRecommendation:
    policy_id: str
    score: float
    reason: str
    action_overrides: Dict[str, Any] = field(default_factory=dict)
    rag_hints: Dict[str, Any] = field(default_factory=dict)
    field_templates: Dict[str, Any] = field(default_factory=dict)
    source: str = "fallback"


@dataclass(frozen=True)
class PolicyAdvice:
    recommendations: List[PolicyRecommendation]
    source: str
    fallback_used: bool
    raw: Dict[str, Any] = field(default_factory=dict)


class PolicyAdvisor:
    """Fetches ranked policy advice from AHMN with deterministic fallback."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def advise(
        self,
        dae_output: DAEOutput,
        constraints: SystemConstraints,
        policy_store: PolicyStore,
        doc_metadata: Optional[Dict[str, Any]] = None,
    ) -> PolicyAdvice:
        metadata = doc_metadata or {}
        if self.config.ahmn.enabled:
            payload = {
                "doc": dae_output.__dict__,
                "constraints": constraints.__dict__,
                "objective": self.config.ahmn.objective,
                "metadata": metadata,
            }
            if self.config.ahmn.mode in {"http", "auto"}:
                remote = self._http_advice(payload)
                if remote:
                    self._send_log(payload, remote)
                    return remote
            if self.config.ahmn.mode in {"import", "auto"} and self.config.ahmn.direct_import:
                imported = self._import_advice(payload)
                if imported:
                    return imported

        recommendations = self._fallback_rank(dae_output, policy_store, metadata)
        return PolicyAdvice(
            recommendations=recommendations,
            source="fallback",
            fallback_used=True,
            raw={"reason": "ahmn_unavailable_or_disabled"},
        )

    def _http_advice(self, payload: Dict[str, Any]) -> Optional[PolicyAdvice]:
        endpoint = self.config.ahmn.endpoint
        if not endpoint:
            return None
        advice_url = endpoint.rstrip("/") + self.config.ahmn.advice_endpoint
        request = urllib.request.Request(
            advice_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        timeout = max(self.config.ahmn.timeout_ms, 10) / 1000.0
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, ValueError):
            return None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None
        return self._normalize_advice(parsed, source="ahmn_http")

    def _send_log(self, request_payload: Dict[str, Any], advice: PolicyAdvice) -> None:
        endpoint = self.config.ahmn.endpoint
        if not endpoint:
            return
        log_url = endpoint.rstrip("/") + self.config.ahmn.log_endpoint
        payload = {
            "request": request_payload,
            "advice_source": advice.source,
            "recommendations": [item.__dict__ for item in advice.recommendations],
        }
        req = urllib.request.Request(
            log_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        timeout = max(self.config.ahmn.timeout_ms, 10) / 1000.0
        try:
            with urllib.request.urlopen(req, timeout=timeout):
                return
        except Exception:
            return

    def _import_advice(self, payload: Dict[str, Any]) -> Optional[PolicyAdvice]:
        module_path = self.config.ahmn.direct_import
        if not module_path:
            return None
        try:
            module_name, func_name = module_path.split(":")
            module = importlib.import_module(module_name)
            func = getattr(module, func_name)
            result = func(payload)
            if isinstance(result, dict):
                return self._normalize_advice(result, source="ahmn_import")
        except Exception:
            return None
        return None

    def _normalize_advice(self, payload: Dict[str, Any], source: str) -> Optional[PolicyAdvice]:
        recs = payload.get("recommendations")
        if not isinstance(recs, list):
            return None
        items: List[PolicyRecommendation] = []
        for item in recs:
            if not isinstance(item, dict):
                continue
            policy_id = str(item.get("policy_id", "")).strip()
            if not policy_id:
                continue
            try:
                score = float(item.get("score", 0.0))
            except Exception:
                score = 0.0
            items.append(
                PolicyRecommendation(
                    policy_id=policy_id,
                    score=score,
                    reason=str(item.get("reason", "ahmn")),
                    action_overrides=item.get("action_overrides", {}) if isinstance(item.get("action_overrides"), dict) else {},
                    rag_hints=item.get("rag_hints", {}) if isinstance(item.get("rag_hints"), dict) else {},
                    field_templates=item.get("field_templates", {}) if isinstance(item.get("field_templates"), dict) else {},
                    source=source,
                )
            )
        if not items:
            return None
        items = sorted(items, key=lambda row: row.score, reverse=True)
        return PolicyAdvice(recommendations=items, source=source, fallback_used=False, raw=payload)

    def _fallback_rank(
        self,
        dae_output: DAEOutput,
        policy_store: PolicyStore,
        doc_metadata: Dict[str, Any],
    ) -> List[PolicyRecommendation]:
        ranked: List[PolicyRecommendation] = []
        for policy in policy_store.policies:
            score, reason = self._score_policy(policy, dae_output, doc_metadata)
            ranked.append(
                PolicyRecommendation(
                    policy_id=policy.policy_id,
                    score=score,
                    reason=reason,
                    source="fallback",
                )
            )
        ranked.sort(key=lambda row: row.score, reverse=True)
        if not ranked:
            return [PolicyRecommendation(policy_id="default", score=0.0, reason="default_fallback")]
        return ranked

    def _score_policy(
        self,
        policy: PolicyDefinition,
        dae_output: DAEOutput,
        doc_metadata: Dict[str, Any],
    ) -> tuple[float, str]:
        if not policy.conditions:
            return 0.1, "default_policy"

        values = {
            "doc_type": dae_output.doc_type,
            "vendor_cluster": dae_output.vendor_cluster,
            "layout_cluster_id": dae_output.layout_cluster_id,
            "quality_bin": dae_output.quality_bin,
            "complexity_bin": dae_output.complexity_bin,
            "content_profile": dae_output.content_profile,
            "route_bin": dae_output.route_bin,
            **{f"signals.{key}": value for key, value in dae_output.signals.items()},
            **doc_metadata,
        }
        matched = 0
        total = 0
        for key, expected in policy.conditions.items():
            total += 1
            current = values.get(key)
            if self._match_expectation(current, expected):
                matched += 1
        if total == 0:
            return 0.1, "conditionless"
        ratio = matched / total
        return ratio, f"conditions_matched:{matched}/{total}"

    def _match_expectation(self, current: Any, expected: Any) -> bool:
        if isinstance(expected, list):
            return current in expected
        if isinstance(expected, dict):
            if "min" in expected and current is not None and current < expected["min"]:
                return False
            if "max" in expected and current is not None and current > expected["max"]:
                return False
            if "equals" in expected:
                return current == expected["equals"]
            return True
        return current == expected
