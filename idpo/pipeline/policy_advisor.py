from __future__ import annotations

import importlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from uuid import UUID
from typing import Any, Dict, List, Optional

from idpo.pipeline.job_context import read_job_context

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
    fallback_recommendations: List[PolicyRecommendation] = field(default_factory=list)
    advice_id: str | None = None
    confidence: float = 0.0
    retrieval_source: str | None = None
    rabi_used: bool = False
    n_neighbors: int | None = None
    raw: Dict[str, Any] = field(default_factory=dict)


class PolicyAdvisor:
    """Fetches AHMN policy advice with deterministic local fallback candidates."""

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
        fallback_recommendations = self._fallback_rank(dae_output, policy_store, metadata)
        if self.config.ahmn.enabled:
            payload = self._advice_payload(dae_output, constraints, metadata)
            if self.config.ahmn.mode in {"http", "auto"}:
                remote = self._http_advice(payload)
                if remote:
                    return self._merge_with_fallback(remote, fallback_recommendations)
            if self.config.ahmn.mode in {"import", "auto"} and self.config.ahmn.direct_import:
                imported = self._import_advice(payload)
                if imported:
                    return self._merge_with_fallback(imported, fallback_recommendations)

        return PolicyAdvice(
            recommendations=fallback_recommendations,
            source="fallback",
            fallback_used=True,
            fallback_recommendations=fallback_recommendations,
            raw={"reason": "ahmn_unavailable_or_disabled"},
        )

    def _advice_payload(
        self,
        dae_output: DAEOutput,
        constraints: SystemConstraints,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        job_id = str(os.getenv("IDPO_JOB_ID", "") or metadata.get("job_id", "") or "").strip()
        job_ctx = read_job_context(job_id) if job_id else {}

        return {
            "doc_type": dae_output.doc_type,
            "vendor": dae_output.vendor_cluster,
            "content_profile": dae_output.content_profile,
            "semantic_doc_type": dae_output.semantic_doc_type,
            "extra_context": {
                "vendor_cluster": dae_output.vendor_cluster,
                "semantic_doc_type": dae_output.semantic_doc_type,
                "layout_cluster_id": dae_output.layout_cluster_id,
                "route_bin": dae_output.route_bin,
                "quality_bin": dae_output.quality_bin,
                "complexity_bin": dae_output.complexity_bin,
                "analysis_confidence": dae_output.analysis_confidence,
                "quality_score": dae_output.quality_score,
                "complexity_score": dae_output.complexity_score,
                "quality_features": dae_output.quality_features,
                "structural_features": dae_output.structural_features,
                "signals": dae_output.signals,
                "constraints": constraints.__dict__,
                "objective": self.config.ahmn.objective,
                "job_context": job_ctx,
                "metadata": metadata,
            },
        }

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
        if self._is_policy_response(payload):
            policy_id = str(payload.get("policy_id", "")).strip()
            if not policy_id:
                return None
            try:
                confidence = float(payload.get("confidence", 0.0))
            except Exception:
                confidence = 0.0
            retrieval_source = str(payload.get("retrieval_source", "DEFAULT")).strip() or "DEFAULT"
            rabi_used = bool(payload.get("rabi_used", False))
            n_neighbors_raw = payload.get("n_neighbors")
            n_neighbors = int(n_neighbors_raw) if n_neighbors_raw is not None else None
            advice_id_raw = payload.get("advice_id")
            advice_id = str(advice_id_raw).strip() if advice_id_raw is not None else None
            reason = retrieval_source.lower()
            if rabi_used:
                reason = f"{reason}_rabi"
            return PolicyAdvice(
                recommendations=[
                    PolicyRecommendation(
                        policy_id=policy_id,
                        score=round(confidence, 4),
                        reason=reason,
                        source=source,
                    )
                ],
                source=source,
                fallback_used=False,
                fallback_recommendations=[],
                advice_id=advice_id,
                confidence=confidence,
                retrieval_source=retrieval_source,
                rabi_used=rabi_used,
                n_neighbors=n_neighbors,
                raw=payload,
            )
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
        return PolicyAdvice(
            recommendations=items,
            source=source,
            fallback_used=False,
            fallback_recommendations=[],
            raw=payload,
        )

    def _merge_with_fallback(
        self,
        advice: PolicyAdvice,
        fallback: List[PolicyRecommendation],
    ) -> PolicyAdvice:
        seen: set[str] = set()
        merged: List[PolicyRecommendation] = []
        for item in advice.recommendations + fallback:
            if item.policy_id in seen:
                continue
            seen.add(item.policy_id)
            merged.append(item)
        return PolicyAdvice(
            recommendations=merged,
            source=advice.source,
            fallback_used=advice.fallback_used,
            fallback_recommendations=fallback,
            advice_id=advice.advice_id,
            confidence=advice.confidence,
            retrieval_source=advice.retrieval_source,
            rabi_used=advice.rabi_used,
            n_neighbors=advice.n_neighbors,
            raw=advice.raw,
        )

    def _is_policy_response(self, payload: Dict[str, Any]) -> bool:
        if "recommendations" in payload:
            return False
        advice_id = payload.get("advice_id")
        policy_id = payload.get("policy_id")
        retrieval_source = payload.get("retrieval_source")
        if not policy_id or not retrieval_source:
            return False
        if advice_id is None:
            return False
        try:
            UUID(str(advice_id))
        except Exception:
            return False
        return True

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
            **{f"quality_features.{key}": value for key, value in dae_output.quality_features.items()},
            **{f"structural_features.{key}": value for key, value in dae_output.structural_features.items()},
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
            if current is None:
                return False
            if "min" in expected and current < expected["min"]:
                return False
            if "max" in expected and current > expected["max"]:
                return False
            if "equals" in expected:
                return current == expected["equals"]
            return True
        return current == expected
