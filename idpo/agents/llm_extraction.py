"""Extraction agent for requested fields and fallback key-value recovery.

This module currently contains both orchestration and implementation details.
During cleanup it should trend toward a thinner agent entrypoint with provider,
prompt, parsing, and heuristic logic split into smaller modules.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter

from idpo.agents.base import Agent, AgentContext
from idpo.agents.extraction_descriptions import (
    normalize_field_descriptions as normalize_extraction_field_descriptions,
    refine_field_descriptions as refine_extraction_field_descriptions,
)
from idpo.agents.extraction_parsing import (
    canonicalize_entities,
    clean_candidate_value,
    filter_to_explicit_keys,
    merge_by_key,
    normalize_key,
    parse_entities_response,
    parse_json_payload,
)
from idpo.agents.extraction_heuristics import (
    extract_by_label_anchor,
    field_label_variants,
    smart_field_extract,
    span_for_line,
)
from idpo.agents.extraction_generic_kv import (
    generic_kv_entities,
    parse_amount_line,
    parse_kv_line,
    parse_multi_kv_line,
)
from idpo.agents.extraction_prompts import build_chat_messages, build_extraction_input, build_prompt
from idpo.agents.extraction_rules import (
    best_generic_match,
    extract_explicit_entities,
    is_valid_candidate_value,
    regex_fallback,
    tokenize,
)
from idpo.agents.extraction_providers import (
    anthropic_messages_completion,
    ollama_chat_detailed,
    ollama_generate,
    ollama_generate_detailed,
    openai_chat_completion,
)
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, Entity, ExtractionPolicy, ModelDecision, StageSignal

_RE_BULLET_PREFIX = re.compile(r"^(?:[-*]|\u2022|\u25E6|\u25CF|\u25CB|\u25AA|\u25A0|\u25A1)+")
_NAME_LIKE_KEY_RE = re.compile(r"(?:^|_)(?:name|author|person|party|customer|vendor|title)(?:$|_)")
_ALPHA_RE = re.compile(r"[A-Za-z]{2,}")

class LLMExtractionAgent(Agent):
    name = "llm_extraction"
    version = "v1"
    _description_refinement_cache: dict[str, dict[str, str]] = {}
    input_contract = {
        "document": "Document",
        "policy": "ExtractionPolicy|None",
        "model": "ModelDecision|None",
        "input_artifact_id": "str|None",
        "explicit_entities": "list|None",
        "field_descriptions": "dict|None",
    }
    output_contract = {
        "explicit_entities": "list",
        "default_entities": "list",
        "entities": "list",
        "explicit_source": "str",
        "requested_field_status": "dict",
        "llm_diagnostics": "dict",
        "signal": "StageSignal",
    }

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        policy: ExtractionPolicy | None = payload.get("policy")
        model: ModelDecision | None = payload.get("model")
        input_artifact_id = payload.get("input_artifact_id")
        explicit_override = payload.get("explicit_entities")
        field_descriptions = payload.get("field_descriptions")
        normalized_descriptions = self._normalize_field_descriptions(field_descriptions)

        generic_entities = self._generic_kv_entities(doc)
        explicit_keys, explicit_source = self._explicit_keys(policy, ctx, generic_entities, explicit_override)
        explicit_key_set = {self._normalize_key(key) for key in explicit_keys if self._normalize_key(key)}
        normalized_descriptions, description_refinement = self._refine_field_descriptions(
            explicit_keys,
            normalized_descriptions,
            ctx,
        )

        explicit_entities = self._canonicalize_entities(
            self._extract_explicit(doc, explicit_keys, generic_entities, ctx, policy, model),
            explicit_keys,
            normalized_descriptions,
        )
        explicit_entities = self._filter_implausible_entities(explicit_entities)
        llm_diagnostics = self._initial_llm_diagnostics(model, description_refinement)
        llm_entities = self._extract_llm_entities(
            doc,
            explicit_keys,
            explicit_entities,
            normalized_descriptions,
            model,
            ctx,
            llm_diagnostics,
        )

        heuristic_entities = self._heuristic_schema_fill(
            doc,
            explicit_keys,
            normalized_descriptions,
            generic_entities,
            explicit_entities + llm_entities,
        )
        explicit_entities = self._merge_by_key(
            self._canonicalize_entities(
                explicit_entities + llm_entities + heuristic_entities,
                explicit_keys,
                normalized_descriptions,
            )
        )
        explicit_entities = self._filter_implausible_entities(explicit_entities)
        explicit_entities = self._filter_to_explicit_keys(explicit_entities, explicit_key_set)
        default_entities = self._dedupe_entities(generic_entities)
        suppressed_defaults = 0
        if explicit_key_set:
            allowed_defaults = []
            for entity in default_entities:
                if self._normalize_key(entity.key) in explicit_key_set:
                    allowed_defaults.append(entity)
                else:
                    suppressed_defaults += 1
            default_entities = allowed_defaults
            # For explicit-field extraction, return only the requested-field entity set.
            combined_entities = self._merge_by_key(explicit_entities)
        else:
            combined_entities = self._merge_entities(explicit_entities, default_entities)
        requested_field_status = self._requested_field_status(
            explicit_keys,
            explicit_entities,
            ctx.config.validation.min_confidence,
        )
        unresolved_keys = sorted(
            key for key, item in requested_field_status.items() if str(item.get("status", "")).strip() != "extracted"
        )
        llm_diagnostics["unresolved_keys"] = unresolved_keys
        llm_diagnostics["unresolved_count"] = len(unresolved_keys)
        llm_diagnostics["resolved_count"] = max(len(requested_field_status) - len(unresolved_keys), 0)
        llm_diagnostics["generic_defaults_suppressed"] = suppressed_defaults

        payload_json = {
            "doc_id": doc.doc_id,
            "policy_id": policy.policy_id if policy else None,
            "policy_name": policy.name if policy else None,
            "model_name": model.model_name if model else None,
            "model_mode": model.mode if model else None,
            "explicit_source": explicit_source,
            "requested_fields": explicit_keys,
            "requested_field_status": requested_field_status,
            "llm_diagnostics": llm_diagnostics,
            "explicit_entities": [entity.__dict__ for entity in explicit_entities],
            "llm_entities": [entity.__dict__ for entity in llm_entities],
            "default_entities": [entity.__dict__ for entity in default_entities],
            "combined_entities": [entity.__dict__ for entity in combined_entities],
        }
        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_structured.json",
            payload_json,
            kind="structured_entities",
            raw=False,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "model": model.model_name if model else None,
                "policy_id": policy.policy_id if policy else None,
                "input_artifacts": [input_artifact_id] if input_artifact_id else [],
            },
        )

        signal = StageSignal(
            stage=self.name,
            confidence=0.7 if combined_entities else 0.4,
            uncertainty=0.3 if combined_entities else 0.6,
            metadata={
                "explicit_count": len(explicit_entities),
                "default_count": len(default_entities),
                "llm_count": len(llm_entities),
                "model": model.model_name if model else None,
                "requested_fields": len(explicit_keys),
                "missing_fields": sum(
                    1
                    for item in requested_field_status.values()
                    if item.get("status") == "missing"
                ),
                "llm_diagnostics": llm_diagnostics,
            },
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={
                "explicit_count": len(explicit_entities),
                "default_count": len(default_entities),
                "artifact_id": artifact.artifact_id,
                "explicit_source": explicit_source,
                "requested_field_status": requested_field_status,
                "llm_diagnostics": llm_diagnostics,
            },
            parameters={
                "model": model.model_name if model else None,
                "model_mode": model.mode if model else None,
                "policy_id": policy.policy_id if policy else None,
            },
            artifacts=[artifact.artifact_id],
            input_artifacts=[input_artifact_id] if input_artifact_id else [],
            output_artifacts=[artifact.artifact_id],
            started=started,
            cost_units=2.0 if model and model.mode == "cloud" else 0.8,
        )
        return AgentResult(
            artifacts={
                "explicit_entities": explicit_entities,
                "default_entities": default_entities,
                "entities": combined_entities,
                "explicit_source": explicit_source,
                "llm_entities": llm_entities,
                "requested_field_status": requested_field_status,
                "llm_diagnostics": llm_diagnostics,
                "structured_artifact": artifact,
                "signal": signal,
            }
        )

    def _initial_llm_diagnostics(
        self,
        model: ModelDecision | None,
        description_refinement: dict[str, object],
    ) -> dict[str, object]:
        return {
            "enabled": False if model is None else None,
            "requested_mode": model.mode if model else None,
            "strategy": "local_first_cloud_cascade",
            "local_attempted": False,
            "local_succeeded": False,
            "local_failure_reason": None,
            "local_call": {},
            "cloud_attempted": False,
            "cloud_succeeded": False,
            "cloud_failure_reason": None,
            "cloud_calls": [],
            "cloud_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
            },
            "flagship_attempted": False,
            "flagship_succeeded": False,
            "flagship_model": None,
            "flagship_failure_reason": None,
            "fallback_keys": [],
            "description_refinement": description_refinement,
        }

    def _extract_llm_entities(
        self,
        doc: Document,
        explicit_keys: list[str],
        explicit_entities: list[Entity],
        field_descriptions: dict[str, str],
        model: ModelDecision | None,
        ctx: AgentContext,
        diagnostics: dict[str, object],
    ) -> list[Entity]:
        diagnostics["enabled"] = bool(ctx.config.llm.use_extraction)
        if not ctx.config.llm.use_extraction:
            diagnostics["local_failure_reason"] = "llm_extraction_disabled"
            return []
        if not model:
            diagnostics["local_failure_reason"] = "no_model_decision"
            return []
        if model.mode == "local":
            return self._run_local_first_extraction(
                doc,
                explicit_keys,
                explicit_entities,
                field_descriptions,
                model,
                ctx,
                diagnostics,
            )
        if model.mode == "cloud":
            return self._run_cloud_first_extraction(
                doc,
                explicit_keys,
                explicit_entities,
                field_descriptions,
                model,
                ctx,
                diagnostics,
            )
        return []

    def _run_local_first_extraction(
        self,
        doc: Document,
        explicit_keys: list[str],
        explicit_entities: list[Entity],
        field_descriptions: dict[str, str],
        model: ModelDecision,
        ctx: AgentContext,
        diagnostics: dict[str, object],
    ) -> list[Entity]:
        llm_entities = self._attempt_local_extraction(
            doc,
            explicit_keys,
            model.model_name,
            field_descriptions,
            ctx,
            diagnostics,
            failure_reason="empty_or_unavailable",
        )
        fallback_keys = self._fallback_keys_for_cloud(
            explicit_keys,
            explicit_entities + llm_entities,
            ctx.config.validation.min_confidence,
            max_fields=ctx.config.llm.max_cloud_fields_per_call,
        )
        diagnostics["fallback_keys"] = list(fallback_keys)
        if not fallback_keys:
            return llm_entities
        if not ctx.config.llm.allow_cloud_fallback:
            diagnostics["cloud_failure_reason"] = "cloud_fallback_disabled"
            return llm_entities

        llm_entities.extend(
            self._attempt_cloud_extraction(
                doc,
                fallback_keys,
                explicit_keys,
                ctx.config.llm.cloud_model,
                field_descriptions,
                ctx,
                diagnostics,
                failure_field="cloud_failure_reason",
                mark_primary_success=True,
            )
        )
        unresolved = self._fallback_keys_for_cloud(
            explicit_keys,
            explicit_entities + llm_entities,
            ctx.config.validation.min_confidence,
            max_fields=ctx.config.llm.max_cloud_fields_per_call,
        )
        llm_entities.extend(
            self._attempt_flagship_fallback(
                doc,
                unresolved,
                explicit_keys,
                ctx.config.llm.cloud_model,
                field_descriptions,
                ctx,
                diagnostics,
            )
        )
        return llm_entities

    def _run_cloud_first_extraction(
        self,
        doc: Document,
        explicit_keys: list[str],
        explicit_entities: list[Entity],
        field_descriptions: dict[str, str],
        model: ModelDecision,
        ctx: AgentContext,
        diagnostics: dict[str, object],
    ) -> list[Entity]:
        llm_entities = self._attempt_cloud_extraction(
            doc,
            explicit_keys,
            explicit_keys,
            model.model_name,
            field_descriptions,
            ctx,
            diagnostics,
            failure_field="cloud_failure_reason",
            mark_primary_success=True,
        )
        fallback_keys = self._fallback_keys_for_cloud(
            explicit_keys,
            explicit_entities + llm_entities,
            ctx.config.validation.min_confidence,
            max_fields=ctx.config.llm.max_cloud_fields_per_call,
        )
        diagnostics["fallback_keys"] = list(fallback_keys)
        llm_entities.extend(
            self._attempt_flagship_fallback(
                doc,
                fallback_keys,
                explicit_keys,
                model.model_name,
                field_descriptions,
                ctx,
                diagnostics,
            )
        )
        if llm_entities:
            return llm_entities

        llm_entities.extend(
            self._attempt_local_extraction(
                doc,
                explicit_keys,
                ctx.config.llm.local_model,
                field_descriptions,
                ctx,
                diagnostics,
                failure_reason="cloud_failed_and_local_unavailable",
            )
        )
        return llm_entities

    def _attempt_local_extraction(
        self,
        doc: Document,
        explicit_keys: list[str],
        model_name: str,
        field_descriptions: dict[str, str],
        ctx: AgentContext,
        diagnostics: dict[str, object],
        failure_reason: str,
    ) -> list[Entity]:
        diagnostics["local_attempted"] = True
        local_raw, local_meta = self._unpack_extraction_call(
            self._llm_extract(
                doc,
                explicit_keys,
                model_name,
                ctx,
                field_descriptions=field_descriptions,
            )
        )
        diagnostics["local_call"] = local_meta
        local_entities = self._canonicalize_entities(local_raw, explicit_keys, field_descriptions)
        if local_entities:
            diagnostics["local_succeeded"] = True
        else:
            diagnostics["local_failure_reason"] = failure_reason
        return local_entities

    def _attempt_cloud_extraction(
        self,
        doc: Document,
        requested_keys: list[str],
        canonical_keys: list[str],
        model_name: str,
        field_descriptions: dict[str, str],
        ctx: AgentContext,
        diagnostics: dict[str, object],
        failure_field: str,
        mark_primary_success: bool = False,
    ) -> list[Entity]:
        diagnostics["cloud_attempted"] = True
        cloud_raw, cloud_meta = self._unpack_extraction_call(
            self._cloud_extract(
                doc,
                requested_keys,
                model_name,
                ctx,
                field_descriptions=field_descriptions,
            )
        )
        self._record_cloud_call(diagnostics, cloud_meta)
        cloud_entities = self._canonicalize_entities(cloud_raw, canonical_keys, field_descriptions)
        if cloud_entities:
            if mark_primary_success:
                diagnostics["cloud_succeeded"] = True
        else:
            diagnostics[failure_field] = cloud_meta.get("error", "empty_or_unavailable")
        return cloud_entities

    def _attempt_flagship_fallback(
        self,
        doc: Document,
        unresolved_keys: list[str],
        explicit_keys: list[str],
        current_model_name: str,
        field_descriptions: dict[str, str],
        ctx: AgentContext,
        diagnostics: dict[str, object],
    ) -> list[Entity]:
        if not self._should_use_flagship_fallback(ctx, unresolved_keys):
            return []
        flagship_model = self._resolve_flagship_model(ctx)
        diagnostics["flagship_model"] = flagship_model
        if not flagship_model or flagship_model == current_model_name:
            return []
        diagnostics["flagship_attempted"] = True
        flagship_entities = self._attempt_cloud_extraction(
            doc,
            unresolved_keys,
            explicit_keys,
            flagship_model,
            field_descriptions,
            ctx,
            diagnostics,
            failure_field="flagship_failure_reason",
        )
        if flagship_entities:
            diagnostics["flagship_succeeded"] = True
            diagnostics["cloud_succeeded"] = True
        return flagship_entities

    def _explicit_keys(
        self,
        policy: ExtractionPolicy | None,
        ctx: AgentContext,
        generic_entities: list[Entity],
        explicit_override: list[str] | None = None,
    ) -> tuple[list[str], str]:
        if explicit_override:
            return [self._normalize_key(key) for key in explicit_override], "plan"
        if policy:
            explicit = getattr(policy, "explicit_entities", None)
            if not explicit and hasattr(policy, "actions"):
                explicit = policy.actions.get("extraction", {}).get("explicit_entities")
            if explicit:
                return [self._normalize_key(key) for key in explicit], "policy"
        rules = ctx.config.structuring.extraction_rules
        if rules:
            return [self._normalize_key(rule.key) for rule in rules], "rules"
        inferred = self._infer_explicit_keys(generic_entities)
        return inferred, "inferred"

    def _normalize_field_descriptions(self, field_descriptions: object) -> dict[str, str]:
        return normalize_extraction_field_descriptions(
            field_descriptions,
            normalize_key=self._normalize_key,
        )

    def _refine_field_descriptions(
        self,
        explicit_keys: list[str],
        field_descriptions: dict[str, str],
        ctx: AgentContext,
    ) -> tuple[dict[str, str], dict[str, object]]:
        return refine_extraction_field_descriptions(
            explicit_keys,
            field_descriptions,
            ctx,
            normalize_key=self._normalize_key,
            parse_json_payload=self._parse_json_payload,
            cache=self._description_refinement_cache,
            generate=ollama_generate,
        )

    def _extract_explicit(
        self,
        doc: Document,
        explicit_keys: list[str],
        generic_entities: list[Entity],
        ctx: AgentContext,
        policy: ExtractionPolicy | None,
        model: ModelDecision | None,
    ) -> list[Entity]:
        return extract_explicit_entities(
            doc,
            explicit_keys,
            generic_entities,
            ctx.config.structuring.extraction_rules,
            policy.policy_id if policy else None,
            model.model_name if model else None,
        )

    def _generic_kv_entities(self, doc: Document) -> list[Entity]:
        return generic_kv_entities(doc, self._span_for_line)

    def _infer_explicit_keys(self, entities: list[Entity]) -> list[str]:
        if not entities:
            return []
        counts = Counter(self._normalize_key(entity.key) for entity in entities)
        ordered = [key for key, _ in counts.most_common()]
        return ordered[: min(5, len(ordered))]

    def _merge_entities(self, explicit: list[Entity], defaults: list[Entity]) -> list[Entity]:
        # Keep a single best value per normalized key.
        selected: dict[str, Entity] = {}
        for entity in defaults:
            key = self._normalize_key(entity.key)
            current = selected.get(key)
            if not current or entity.confidence > current.confidence:
                selected[key] = entity
        for entity in explicit:
            key = self._normalize_key(entity.key)
            current = selected.get(key)
            if (
                not current
                or entity.confidence >= current.confidence
                or (entity.metadata or {}).get("explicit")
            ):
                selected[key] = entity
        return list(selected.values())

    def _filter_to_explicit_keys(self, entities: list[Entity], explicit_key_set: set[str]) -> list[Entity]:
        return filter_to_explicit_keys(entities, explicit_key_set)

    def _merge_by_key(self, entities: list[Entity]) -> list[Entity]:
        return merge_by_key(entities)

    def _unpack_extraction_call(self, payload: object) -> tuple[list[Entity], dict[str, object]]:
        if (
            isinstance(payload, tuple)
            and len(payload) == 2
            and isinstance(payload[1], dict)
        ):
            entities, meta = payload
            if isinstance(entities, list):
                return entities, dict(meta)
            return [], dict(meta)
        if isinstance(payload, list):
            return payload, {}
        return [], {}

    def _record_cloud_call(self, diagnostics: dict[str, object], call_meta: dict[str, object]) -> None:
        if not call_meta:
            return
        calls = diagnostics.setdefault("cloud_calls", [])
        if isinstance(calls, list):
            calls.append(call_meta)
        usage = diagnostics.setdefault(
            "cloud_usage",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0},
        )
        if not isinstance(usage, dict):
            return
        usage["prompt_tokens"] = int(usage.get("prompt_tokens", 0)) + int(call_meta.get("prompt_tokens", 0) or 0)
        usage["completion_tokens"] = int(usage.get("completion_tokens", 0)) + int(call_meta.get("completion_tokens", 0) or 0)
        usage["total_tokens"] = int(usage.get("total_tokens", 0)) + int(call_meta.get("total_tokens", 0) or 0)
        usage["estimated_cost_usd"] = float(usage.get("estimated_cost_usd", 0.0)) + float(
            call_meta.get("estimated_cost_usd", 0.0) or 0.0
        )

    def _should_use_flagship_fallback(self, ctx: AgentContext, unresolved_keys: list[str]) -> bool:
        if not ctx.config.llm.enable_flagship_fallback:
            return False
        if not unresolved_keys:
            return False
        return len(unresolved_keys) >= max(1, int(ctx.config.llm.flagship_min_missing_fields))

    def _resolve_flagship_model(self, ctx: AgentContext) -> str:
        preferred = str(getattr(ctx.config.llm, "flagship_model", "") or "").strip()
        if preferred:
            return preferred
        escalation_choice = str(ctx.config.escalation.flagship_model or "").strip()
        if escalation_choice and "sim" not in escalation_choice.lower():
            return escalation_choice
        return ctx.config.llm.cloud_model

    def _fallback_keys_for_cloud(
        self,
        explicit_keys: list[str],
        entities: list[Entity],
        min_confidence: float,
        max_fields: int = 8,
    ) -> list[str]:
        if not explicit_keys:
            return []
        by_key = {self._normalize_key(entity.key): entity for entity in self._merge_by_key(entities)}
        threshold = max(0.5, min(min_confidence, 0.8) - 0.05)
        missing: list[str] = []
        weak: list[str] = []
        for key in explicit_keys:
            norm_key = self._normalize_key(key)
            entity = by_key.get(norm_key)
            if not entity:
                missing.append(norm_key)
            elif entity.confidence < threshold:
                weak.append(norm_key)
        # Keep cloud usage bounded per document while still covering failures.
        limit = max(1, int(max_fields))
        return (missing + weak)[:limit]

    def _requested_field_status(
        self,
        explicit_keys: list[str],
        entities: list[Entity],
        min_confidence: float,
    ) -> dict[str, dict[str, object]]:
        status_map: dict[str, dict[str, object]] = {}
        if not explicit_keys:
            return status_map
        by_key = {self._normalize_key(entity.key): entity for entity in self._merge_by_key(entities)}
        threshold = max(0.0, min(min_confidence, 1.0))
        low_threshold = max(0.3, threshold - 0.25)
        for key in explicit_keys:
            norm_key = self._normalize_key(key)
            if not norm_key:
                continue
            entity = by_key.get(norm_key)
            if not entity:
                status_map[norm_key] = {
                    "status": "missing",
                    "confidence": 0.0,
                    "value": "N/A",
                    "source": "none",
                }
                continue
            source = str((entity.metadata or {}).get("source", "unknown"))
            if entity.confidence >= threshold:
                status = "extracted"
                value = entity.value
            elif entity.confidence >= low_threshold:
                status = "low_confidence"
                value = "N/A"
            else:
                status = "low_confidence"
                value = "N/A"
            status_map[norm_key] = {
                "status": status,
                "confidence": entity.confidence,
                "value": value,
                "source": source,
            }
        return status_map

    def _canonicalize_entities(
        self,
        entities: list[Entity],
        explicit_keys: list[str],
        field_descriptions: dict[str, str],
    ) -> list[Entity]:
        return canonicalize_entities(entities, explicit_keys, field_descriptions)

    def _dedupe_entities(self, entities: list[Entity]) -> list[Entity]:
        """Deduplicate entities by normalized key, keeping highest confidence."""
        best_by_key: dict[str, Entity] = {}
        for entity in entities:
            norm_key = self._normalize_key(entity.key)
            existing = best_by_key.get(norm_key)
            if not existing or entity.confidence > existing.confidence:
                best_by_key[norm_key] = entity
        # Also remove entities below minimum confidence threshold
        return [e for e in best_by_key.values() if e.confidence >= 0.30]

    def _pick_best(self, selected: dict[str, Entity], candidate: Entity) -> None:
        current = selected.get(candidate.key)
        if not current or candidate.confidence > current.confidence:
            selected[candidate.key] = candidate

    def _normalize_key(self, raw: str) -> str:
        return normalize_key(raw)

    def _filter_implausible_entities(self, entities: list[Entity]) -> list[Entity]:
        filtered: list[Entity] = []
        for entity in entities:
            if self._is_plausible_for_key(entity.key, str(entity.value or "")):
                filtered.append(entity)
        return filtered

    def _is_plausible_for_key(self, key: str, value: str) -> bool:
        normalized_key = self._normalize_key(key)
        cleaned_value = clean_candidate_value(value)
        if not cleaned_value:
            return False
        if _NAME_LIKE_KEY_RE.search(normalized_key):
            if not _ALPHA_RE.search(cleaned_value):
                return False
        return True

    def _span_for_line(self, page_text: str, line: str, value: str) -> tuple[int, int] | None:
        return span_for_line(page_text, line, value)

    def _parse_kv_line(self, line: str) -> tuple[str, str] | None:
        return parse_kv_line(line)

    def _parse_multi_kv_line(self, line: str) -> list[tuple[str, str]]:
        return parse_multi_kv_line(line)

    def _parse_amount_line(self, line: str) -> tuple[str, str] | None:
        return parse_amount_line(line)

    def _heuristic_schema_fill(
        self,
        doc: Document,
        explicit_keys: list[str],
        field_descriptions: dict[str, str],
        generic_entities: list[Entity],
        existing: list[Entity],
    ) -> list[Entity]:
        if not explicit_keys:
            return []
        filled: list[Entity] = []
        existing_keys = {self._normalize_key(entity.key) for entity in existing}
        generic_by_key: dict[str, list[Entity]] = {}
        for entity in generic_entities:
            key = self._normalize_key(entity.key)
            generic_by_key.setdefault(key, []).append(entity)

        text = "\n".join(page.text for page in doc.pages)
        for key in explicit_keys:
            if key in existing_keys:
                continue
            # Try smart document-structure extraction first
            smart = smart_field_extract(key, doc, text)
            if smart:
                filled.append(smart)
                continue
            desc = field_descriptions.get(key, "")
            anchored = extract_by_label_anchor(
                key,
                desc,
                doc,
                self._clean_candidate_value,
                is_valid_candidate_value,
            )
            if anchored:
                filled.append(anchored)
                continue
            tokens = self._tokenize(f"{key} {desc}")
            match = best_generic_match(tokens, generic_by_key)
            if match:
                filled.append(
                    Entity(
                        key=key,
                        value=match.value,
                        confidence=min(0.6, match.confidence + 0.1),
                        page=match.page,
                        span=match.span,
                        metadata={**(match.metadata or {}), "explicit": True, "source": "schema_match"},
                    )
                )
                continue
            fallback = regex_fallback(key, tokens, text)
            if fallback:
                filled.append(fallback)
        return filled

    def _smart_field_extract(self, key: str, doc: Document, text: str) -> Entity | None:
        return smart_field_extract(key, doc, text)

    def _extract_by_label_anchor(self, key: str, description: str, doc: Document) -> Entity | None:
        return extract_by_label_anchor(
            key,
            description,
            doc,
            self._clean_candidate_value,
            is_valid_candidate_value,
        )

    def _field_label_variants(self, key: str, description: str) -> list[str]:
        return field_label_variants(key, description)

    def _clean_candidate_value(self, raw: str) -> str:
        return clean_candidate_value(raw)

    def _is_valid_candidate_value(self, value: str) -> bool:
        return is_valid_candidate_value(value)

    def _tokenize(self, text: str) -> list[str]:
        return tokenize(text)

    # Models that support the /api/chat endpoint and instruction templates.
    _CHAT_MODEL_PREFIXES = ("qwen", "llama3", "llama-3", "mistral", "gemma", "deepseek")

    @classmethod
    def _uses_chat_endpoint(cls, model_name: str) -> bool:
        lower = model_name.lower()
        return any(lower.startswith(p) for p in cls._CHAT_MODEL_PREFIXES)

    def _llm_extract(
        self,
        doc: Document,
        explicit_keys: list[str],
        model_name: str,
        ctx: AgentContext,
        field_descriptions: dict[str, str] | None = None,
    ) -> list[Entity] | tuple[list[Entity], dict[str, object]]:
        started = time.time()
        text, context_meta = build_extraction_input(doc, explicit_keys, field_descriptions or {}, ctx)
        if not text.strip():
            return [], {
                "provider": "ollama",
                "model": model_name,
                "error": "empty_document",
                "latency_ms": 0.0,
            }

        llm_cfg = ctx.config.llm
        use_chat = self._uses_chat_endpoint(model_name) or bool(getattr(llm_cfg, "local_use_chat_api", False))
        format_json = bool(getattr(llm_cfg, "local_format_json", True))
        options: dict[str, object] = {
            "temperature": float(getattr(llm_cfg, "local_temperature", 0.0)),
            "top_p": float(getattr(llm_cfg, "local_top_p", 0.9)),
            "num_predict": int(getattr(llm_cfg, "local_num_predict", 1024)),
        }

        if use_chat:
            # Instruction-tuned models (Qwen3, Llama3) work best via /api/chat.
            # /no_think disables Qwen3's extended thinking chain for faster,
            # more deterministic structured extraction.
            no_think = model_name.lower().startswith("qwen")
            messages = build_chat_messages(
                text, explicit_keys, ctx, field_descriptions or {}, no_think=no_think
            )
            response, call_meta = ollama_chat_detailed(
                llm_cfg.base_url,
                messages,
                model_name,
                timeout_s=llm_cfg.timeout_s,
                options=options,
                format_json=format_json,
            )
            prompt_chars = sum(len(m.get("content", "")) for m in messages)
            endpoint_used = "ollama.chat"
        else:
            prompt = build_prompt(text, explicit_keys, ctx, field_descriptions or {})
            payload: dict[str, object] = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": options,
            }
            if format_json:
                payload["format"] = "json"
            response, call_meta = ollama_generate_detailed(
                llm_cfg.base_url,
                payload,
                llm_cfg.timeout_s,
            )
            prompt_chars = len(prompt)
            endpoint_used = "ollama.generate"

        latency_ms = (time.time() - started) * 1000
        persist_raw = bool(getattr(llm_cfg, "persist_raw_llm_io", True))

        meta: dict[str, object] = {
            "provider": "ollama",
            "model": model_name,
            "prompt_chars": prompt_chars,
            "requested_fields": len(explicit_keys),
            "latency_ms": round(latency_ms, 2),
            "success": False,
            "entity_count": 0,
            "prompt_version": "extraction_v3",
            "context": context_meta,
            "request": {
                "format": "json" if format_json else "text",
                "options": options,
                "endpoint": endpoint_used,
                "base_url": llm_cfg.base_url,
                "chat_mode": use_chat,
            },
            **call_meta,
        }
        if persist_raw:
            meta["raw_messages"] = messages if use_chat else None
            if not use_chat:
                meta["raw_prompt"] = build_prompt(text, explicit_keys, ctx, field_descriptions or {})
            meta["raw_response"] = response or ""

        if not response:
            meta.setdefault("error", "empty_or_unavailable")
            return [], meta

        entities = self._parse_entities_response(response, model_name, source="llm_local")
        meta["success"] = bool(entities)
        meta["entity_count"] = len(entities)
        if not entities:
            if not persist_raw:
                meta["raw_response_preview"] = (response or "")[:1000]
            meta.setdefault("parse_failed", True)
        return entities, meta

    def _cloud_extract(
        self,
        doc: Document,
        explicit_keys: list[str],
        model_name: str,
        ctx: AgentContext,
        field_descriptions: dict[str, str] | None = None,
    ) -> list[Entity] | tuple[list[Entity], dict[str, object]]:
        started = time.time()
        text, context_meta = build_extraction_input(doc, explicit_keys, field_descriptions or {}, ctx)
        cloud_max_tokens = self._cloud_max_tokens(len(explicit_keys), int(ctx.config.llm.cloud_max_tokens))
        meta: dict[str, object] = {
            "provider": ctx.config.llm.cloud_provider,
            "model": model_name,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "prompt_chars": 0,
            "requested_fields": len(explicit_keys),
            "latency_ms": 0.0,
            "success": False,
            "entity_count": 0,
            "max_tokens_requested": cloud_max_tokens,
            "prompt_version": "extraction_v2",
            "context": context_meta,
            "request": {
                "temperature": ctx.config.llm.cloud_temperature,
                "strict_json_output": bool(ctx.config.llm.strict_json_output),
                "max_tokens": cloud_max_tokens,
                "response_format": "json_schema" if ctx.config.llm.strict_json_output else "none",
            },
        }
        if not text.strip():
            meta["error"] = "empty_document"
            return [], meta
        prompt = build_prompt(text, explicit_keys, ctx, field_descriptions or {})
        meta["prompt_chars"] = len(prompt)
        if bool(getattr(ctx.config.llm, "persist_raw_llm_io", True)):
            meta["raw_prompt"] = prompt
        provider = ctx.config.llm.cloud_provider
        if provider == "openai":
            content, call_meta = openai_chat_completion(
                model_name=model_name,
                prompt=prompt,
                api_key=(ctx.config.llm.openai_api_key or ""),
                base_url=(ctx.config.llm.openai_api_url or ""),
                timeout_s=ctx.config.llm.cloud_timeout_s,
                temperature=ctx.config.llm.cloud_temperature,
                max_tokens=cloud_max_tokens,
                response_format=self._openai_response_format(explicit_keys)
                if ctx.config.llm.strict_json_output
                else None,
                retry_without_json_mode=bool(ctx.config.llm.cloud_retry_without_json_mode),
            )
            meta.update(call_meta)
            request_meta = meta.get("request")
            if isinstance(request_meta, dict) and call_meta.get("endpoint"):
                request_meta["endpoint"] = call_meta["endpoint"]
            if meta.get("error"):
                meta["latency_ms"] = (time.time() - started) * 1000
                return [], meta
            prompt_tokens = int(meta.get("prompt_tokens", 0) or 0)
            completion_tokens = int(meta.get("completion_tokens", 0) or 0)
            total_tokens = int(meta.get("total_tokens", prompt_tokens + completion_tokens) or 0)
            entities = self._parse_entities_response(content or "", model_name, source="llm_cloud")
            if bool(getattr(ctx.config.llm, "persist_raw_llm_io", True)):
                meta["raw_response"] = content or ""
            elif content and not entities:
                meta["raw_response_preview"] = content[:1000]
            meta.update(
                {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "estimated_cost_usd": self._estimate_openai_cost(model_name, prompt_tokens, completion_tokens),
                    "latency_ms": (time.time() - started) * 1000,
                    "success": bool(entities),
                    "entity_count": len(entities),
                }
            )
            return entities, meta
        if provider == "anthropic":
            content, call_meta = anthropic_messages_completion(
                model_name=model_name,
                prompt=prompt,
                api_key="",
                max_tokens=cloud_max_tokens,
            )
            meta.update(call_meta)
            request_meta = meta.get("request")
            if isinstance(request_meta, dict) and call_meta.get("endpoint"):
                request_meta["endpoint"] = call_meta["endpoint"]
            if meta.get("error"):
                meta["latency_ms"] = (time.time() - started) * 1000
                return [], meta
            entities = self._parse_entities_response(content or "", model_name, source="llm_cloud")
            if bool(getattr(ctx.config.llm, "persist_raw_llm_io", True)):
                meta["raw_response"] = content or ""
            elif content and not entities:
                meta["raw_response_preview"] = content[:1000]
            input_tokens = int(meta.get("prompt_tokens", 0) or 0)
            output_tokens = int(meta.get("completion_tokens", 0) or 0)
            meta.update(
                {
                    "latency_ms": (time.time() - started) * 1000,
                    "success": bool(entities),
                    "entity_count": len(entities),
                }
            )
            return entities, meta
        meta["error"] = "unknown_provider"
        meta["latency_ms"] = (time.time() - started) * 1000
        return [], meta

    def _cloud_max_tokens(self, requested_fields: int, configured_max: int) -> int:
        configured_cap = max(128, int(configured_max))
        adaptive = max(160, int(max(1, requested_fields) * 80))
        return min(configured_cap, adaptive)

    def _openai_response_format(self, explicit_keys: list[str]) -> dict[str, object]:
        allowed_keys: list[str] = []
        seen: set[str] = set()
        for key in explicit_keys:
            normalized = self._normalize_key(key)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            allowed_keys.append(normalized)

        key_schema: dict[str, object] = {"type": "string", "minLength": 1}
        if allowed_keys:
            key_schema = {"type": "string", "enum": allowed_keys}

        return {
            "type": "json_schema",
            "json_schema": {
                "name": "extraction_entities",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "key": key_schema,
                                    "value": {"type": "string", "minLength": 1},
                                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                                },
                                "required": ["key", "value", "confidence"],
                            },
                        }
                    },
                    "required": ["entities"],
                },
            },
        }

    def _estimate_openai_cost(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        # Approximate price table in USD per 1K tokens for budgeting heuristics.
        price_per_1k: dict[str, tuple[float, float]] = {
            "gpt-4o-mini": (0.00015, 0.0006),
            "gpt-4o": (0.0025, 0.01),
            "gpt-4.1-mini": (0.0004, 0.0016),
            "gpt-4.1": (0.01, 0.03),
        }
        model_key = model_name.lower()
        input_rate, output_rate = price_per_1k.get(model_key, (0.001, 0.004))
        return ((prompt_tokens / 1000.0) * input_rate) + ((completion_tokens / 1000.0) * output_rate)

    def _parse_entities_response(self, response: str, model_name: str, source: str) -> list[Entity]:
        return parse_entities_response(response, model_name, source)

    def _parse_json_payload(self, cleaned: str) -> object | None:
        return parse_json_payload(cleaned)
