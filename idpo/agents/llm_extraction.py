"""LLM-based entity and key-value extraction agent."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except Exception:
    ANTHROPIC_AVAILABLE = False

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, Entity, ExtractionPolicy, ModelDecision, StageSignal

# Pre-compiled regex patterns for performance
_RE_KV_COLON = re.compile(r"^([A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s*[:=\-]\s*(.+)$")
_RE_KV_SPACE = re.compile(r"^([A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s{2,}(.+)$")
_RE_MULTI_KV = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s*[:=]\s*"
    r"(?P<value>.*?)(?=(?:[A-Za-z][A-Za-z0-9 #/&()._-]{1,40}\s*[:=])|$)"
)
_RE_AMOUNT = re.compile(r"((?:\$|usd\s*)?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")
_RE_NORMALIZE_KEY = re.compile(r"[^a-z0-9]+")
_RE_BULLET_PREFIX = re.compile(r"^[\-\*•◦●○▪■□]+")

_TOKEN_EQUIVALENTS = {
    "no": ("number",),
    "num": ("number",),
    "qty": ("quantity",),
    "amt": ("amount",),
    "addr": ("address",),
    "tel": ("telephone", "phone"),
    "inv": ("invoice",),
    "po": ("purchase", "order"),
    "dob": ("date", "birth"),
}

_DESC_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "for",
    "from",
    "field",
    "value",
    "document",
    "extract",
    "this",
    "that",
    "with",
}

_MISSING_VALUE_MARKERS = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "not found",
    "-",
}

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
        llm_diagnostics: dict[str, object] = {
            "enabled": bool(ctx.config.llm.use_extraction),
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
        llm_entities: list[Entity] = []
        if ctx.config.llm.use_extraction and model:
            if model.mode == "local":
                llm_diagnostics["local_attempted"] = True
                local_raw, local_meta = self._unpack_extraction_call(
                    self._llm_extract(
                        doc,
                        explicit_keys,
                        model.model_name,
                        ctx,
                        field_descriptions=normalized_descriptions,
                    )
                )
                llm_diagnostics["local_call"] = local_meta
                local_entities = self._canonicalize_entities(local_raw, explicit_keys, normalized_descriptions)
                llm_entities.extend(local_entities)
                if local_entities:
                    llm_diagnostics["local_succeeded"] = True
                else:
                    llm_diagnostics["local_failure_reason"] = "empty_or_unavailable"

                # Local-first strategy: retry only unresolved/weak fields in cloud.
                fallback_keys = self._fallback_keys_for_cloud(
                    explicit_keys,
                    explicit_entities + llm_entities,
                    ctx.config.validation.min_confidence,
                    max_fields=ctx.config.llm.max_cloud_fields_per_call,
                )
                llm_diagnostics["fallback_keys"] = list(fallback_keys)
                if fallback_keys and ctx.config.llm.allow_cloud_fallback:
                    llm_diagnostics["cloud_attempted"] = True
                    cloud_raw, cloud_meta = self._unpack_extraction_call(
                        self._cloud_extract(
                            doc,
                            fallback_keys,
                            ctx.config.llm.cloud_model,
                            ctx,
                            field_descriptions=normalized_descriptions,
                        )
                    )
                    self._record_cloud_call(llm_diagnostics, cloud_meta)
                    cloud_entities = self._canonicalize_entities(cloud_raw, explicit_keys, normalized_descriptions)
                    llm_entities.extend(cloud_entities)
                    if cloud_entities:
                        llm_diagnostics["cloud_succeeded"] = True
                    else:
                        llm_diagnostics["cloud_failure_reason"] = cloud_meta.get("error", "empty_or_unavailable")

                    unresolved = self._fallback_keys_for_cloud(
                        explicit_keys,
                        explicit_entities + llm_entities,
                        ctx.config.validation.min_confidence,
                        max_fields=ctx.config.llm.max_cloud_fields_per_call,
                    )
                    if self._should_use_flagship_fallback(ctx, unresolved):
                        flagship_model = self._resolve_flagship_model(ctx)
                        llm_diagnostics["flagship_model"] = flagship_model
                        if flagship_model and flagship_model != ctx.config.llm.cloud_model:
                            llm_diagnostics["flagship_attempted"] = True
                            flagship_raw, flagship_meta = self._unpack_extraction_call(
                                self._cloud_extract(
                                    doc,
                                    unresolved,
                                    flagship_model,
                                    ctx,
                                    field_descriptions=normalized_descriptions,
                                )
                            )
                            self._record_cloud_call(llm_diagnostics, flagship_meta)
                            flagship_entities = self._canonicalize_entities(
                                flagship_raw,
                                explicit_keys,
                                normalized_descriptions,
                            )
                            llm_entities.extend(flagship_entities)
                            if flagship_entities:
                                llm_diagnostics["flagship_succeeded"] = True
                                llm_diagnostics["cloud_succeeded"] = True
                            else:
                                llm_diagnostics["flagship_failure_reason"] = flagship_meta.get(
                                    "error",
                                    "empty_or_unavailable",
                                )
                elif fallback_keys and not ctx.config.llm.allow_cloud_fallback:
                    llm_diagnostics["cloud_failure_reason"] = "cloud_fallback_disabled"
            elif model.mode == "cloud":
                llm_diagnostics["cloud_attempted"] = True
                cloud_raw, cloud_meta = self._unpack_extraction_call(
                    self._cloud_extract(
                        doc,
                        explicit_keys,
                        model.model_name,
                        ctx,
                        field_descriptions=normalized_descriptions,
                    )
                )
                self._record_cloud_call(llm_diagnostics, cloud_meta)
                llm_entities = self._canonicalize_entities(cloud_raw, explicit_keys, normalized_descriptions)
                if llm_entities:
                    llm_diagnostics["cloud_succeeded"] = True
                else:
                    llm_diagnostics["cloud_failure_reason"] = cloud_meta.get("error", "empty_or_unavailable")

                # Cloud-first strategy: if requested fields remain unresolved, escalate to flagship model.
                fallback_keys = self._fallback_keys_for_cloud(
                    explicit_keys,
                    explicit_entities + llm_entities,
                    ctx.config.validation.min_confidence,
                    max_fields=ctx.config.llm.max_cloud_fields_per_call,
                )
                llm_diagnostics["fallback_keys"] = list(fallback_keys)
                if self._should_use_flagship_fallback(ctx, fallback_keys):
                    flagship_model = self._resolve_flagship_model(ctx)
                    llm_diagnostics["flagship_model"] = flagship_model
                    if flagship_model and flagship_model != model.model_name:
                        llm_diagnostics["flagship_attempted"] = True
                        flagship_raw, flagship_meta = self._unpack_extraction_call(
                            self._cloud_extract(
                                doc,
                                fallback_keys,
                                flagship_model,
                                ctx,
                                field_descriptions=normalized_descriptions,
                            )
                        )
                        self._record_cloud_call(llm_diagnostics, flagship_meta)
                        flagship_entities = self._canonicalize_entities(
                            flagship_raw,
                            explicit_keys,
                            normalized_descriptions,
                        )
                        llm_entities.extend(flagship_entities)
                        if flagship_entities:
                            llm_diagnostics["flagship_succeeded"] = True
                            llm_diagnostics["cloud_succeeded"] = True
                        else:
                            llm_diagnostics["flagship_failure_reason"] = flagship_meta.get(
                                "error",
                                "empty_or_unavailable",
                            )

                if not llm_entities:
                    # Cloud-first fallback when API is unavailable.
                    llm_diagnostics["local_attempted"] = True
                    local_raw, local_meta = self._unpack_extraction_call(
                        self._llm_extract(
                            doc,
                            explicit_keys,
                            ctx.config.llm.local_model,
                            ctx,
                            field_descriptions=normalized_descriptions,
                        )
                    )
                    llm_diagnostics["local_call"] = local_meta
                    local_entities = self._canonicalize_entities(local_raw, explicit_keys, normalized_descriptions)
                    if local_entities:
                        llm_entities.extend(local_entities)
                        llm_diagnostics["local_succeeded"] = True
                    else:
                        llm_diagnostics["local_failure_reason"] = "cloud_failed_and_local_unavailable"
        elif not ctx.config.llm.use_extraction:
            llm_diagnostics["local_failure_reason"] = "llm_extraction_disabled"
        else:
            llm_diagnostics["local_failure_reason"] = "no_model_decision"

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
        if not isinstance(field_descriptions, dict):
            return {}
        normalized: dict[str, str] = {}
        for raw_key, raw_value in field_descriptions.items():
            key = self._normalize_key(str(raw_key))
            if not key:
                continue
            normalized[key] = str(raw_value or "").strip()
        return normalized

    def _refine_field_descriptions(
        self,
        explicit_keys: list[str],
        field_descriptions: dict[str, str],
        ctx: AgentContext,
    ) -> tuple[dict[str, str], dict[str, object]]:
        meta: dict[str, object] = {
            "enabled": bool(ctx.config.llm.refine_field_descriptions),
            "attempted": False,
            "succeeded": False,
            "cache_hit": False,
            "model": None,
            "error": None,
            "input_fields": 0,
        }
        if not explicit_keys:
            return field_descriptions, meta

        max_fields = max(1, int(ctx.config.llm.description_refinement_max_fields))
        selected_keys = [self._normalize_key(key) for key in explicit_keys if self._normalize_key(key)][:max_fields]
        if not selected_keys:
            return field_descriptions, meta

        base_map: dict[str, str] = {}
        for key in selected_keys:
            seed = (field_descriptions.get(key) or key.replace("_", " ")).strip()
            if seed:
                base_map[key] = seed
        meta["input_fields"] = len(base_map)
        if not base_map:
            return field_descriptions, meta
        if not ctx.config.llm.refine_field_descriptions:
            merged = dict(field_descriptions)
            merged.update(base_map)
            return merged, meta

        if ctx.config.llm.cloud_provider != "openai":
            meta["error"] = "refinement_requires_openai"
            merged = dict(field_descriptions)
            merged.update(base_map)
            return merged, meta
        if not OPENAI_AVAILABLE:
            meta["error"] = "openai_sdk_unavailable"
            merged = dict(field_descriptions)
            merged.update(base_map)
            return merged, meta

        api_key = os.getenv("OPENAI_API_KEY") or ctx.config.llm.openai_api_key
        key_value = (api_key or "").strip().lower()
        if not key_value or key_value.startswith("${") or key_value in {"sk-placeholder", "sk-", "changeme"}:
            meta["error"] = "missing_openai_key"
            merged = dict(field_descriptions)
            merged.update(base_map)
            return merged, meta

        model_name = (ctx.config.llm.description_refinement_model or ctx.config.llm.cloud_model).strip()
        meta["model"] = model_name
        cache_key = f"{model_name}|{json.dumps(base_map, sort_keys=True)}"
        cached = self._description_refinement_cache.get(cache_key)
        if cached:
            merged = dict(field_descriptions)
            merged.update(cached)
            meta["cache_hit"] = True
            meta["succeeded"] = True
            return merged, meta

        meta["attempted"] = True
        base_url = self._normalize_openai_base_url(os.getenv("OPENAI_API_URL") or ctx.config.llm.openai_api_url)
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=ctx.config.llm.cloud_timeout_s)
        prompt = (
            "Refine field descriptions for document extraction.\n"
            "Return a JSON object mapping each key to one concise extraction description.\n"
            "Each description should be 8-20 words and include synonyms/format hints.\n"
            "Do not add new keys.\n\n"
            f"Input map:\n{json.dumps(base_map, ensure_ascii=False)}"
        )
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You optimize extraction field descriptions."},
                    {"role": "user", "content": prompt},
                ],
                temperature=ctx.config.llm.description_refinement_temperature,
                max_tokens=ctx.config.llm.description_refinement_max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content if response.choices else ""
            parsed = self._parse_json_payload(content or "")
            refined: dict[str, str] = {}
            if isinstance(parsed, dict):
                container = parsed.get("descriptions", parsed)
                if isinstance(container, dict):
                    for key in selected_keys:
                        value = container.get(key)
                        if isinstance(value, str) and value.strip():
                            refined[key] = value.strip()
            merged = dict(field_descriptions)
            merged.update(base_map)
            merged.update(refined)
            if refined:
                self._description_refinement_cache[cache_key] = dict(refined)
                meta["succeeded"] = True
            else:
                meta["error"] = "empty_refinement_output"
            return merged, meta
        except Exception as exc:
            meta["error"] = str(exc)[:220]
            merged = dict(field_descriptions)
            merged.update(base_map)
            return merged, meta

    def _extract_explicit(
        self,
        doc: Document,
        explicit_keys: list[str],
        generic_entities: list[Entity],
        ctx: AgentContext,
        policy: ExtractionPolicy | None,
        model: ModelDecision | None,
    ) -> list[Entity]:
        rule_map = {self._normalize_key(rule.key): rule for rule in ctx.config.structuring.extraction_rules}
        explicit_map: dict[str, Entity] = {}
        for key in explicit_keys:
            rule = rule_map.get(key)
            if rule:
                match_value, page_num, span = self._match_rule_in_pages(doc, rule.pattern)
                if match_value:
                    entity = Entity(
                        key=rule.key,
                        value=match_value,
                        confidence=0.82,
                        page=page_num,
                        span=span,
                        metadata={
                            "explicit": True,
                            "source": "rule",
                            "label": rule.label,
                            "policy_id": policy.policy_id if policy else None,
                            "model": model.model_name if model else None,
                        },
                    )
                    self._pick_best(explicit_map, entity)

        explicit_set = {self._normalize_key(key) for key in explicit_keys}
        for entity in generic_entities:
            if self._normalize_key(entity.key) in explicit_set:
                candidate = Entity(
                    key=entity.key,
                    value=entity.value,
                    confidence=max(entity.confidence, 0.62),
                    page=entity.page,
                    span=entity.span,
                    metadata={**entity.metadata, "explicit": True, "source": "generic_kv"},
                )
                self._pick_best(explicit_map, candidate)

        return list(explicit_map.values())

    def _generic_kv_entities(self, doc: Document) -> list[Entity]:
        """Extract key-value entities from document text using heuristic parsing.

        Applies multi-layer noise filtering to prevent garbage entities:
        - Key constraints: length 3-50 chars, max 5 words, low numeric noise, no noise prefixes
        - Value constraints: length 2-180 chars, no bullets/brackets/arrows/orphan quotes
        - Rejects sentence-like values, single common words, and unmatched parens
        - Confidence scoring: 0.72 for numeric, 0.75 for dates, 0.70 for IDs, 0.35 for long text
        """
        _SINGLE_WORD_NOISE = {
            "member", "shows", "role", "logic", "type", "name",
            "value", "label", "model", "sensor", "step", "code",
            "data", "text", "note", "item", "page", "line",
            "file", "path", "info", "mode", "size", "count",
            "list", "link", "icon", "view", "form", "test",
            "soil", "temp", "light", "tank", "water", "task",
            "software", "hardware", "physical", "widget", "color",
            "alert", "prediction", "reason", "scenario", "output",
            "input", "transmission", "execution", "rain", "system",
            "actuation", "run", "class", "prob", "context",
            "phase", "stage", "layer", "source", "target",
            "status", "action", "result", "process", "method",
            "signal", "event", "state", "table", "field",
            "section", "header", "footer", "title", "body",
            "group", "category", "block", "segment", "unit",
            "level", "scope", "range", "margin", "padding",
            "width", "height", "depth", "weight", "length",
            "measure", "metric", "factor", "ratio", "scale",
            "device", "module", "component", "element", "object",
            "feature", "option", "setting", "config", "param",
            "error", "warning", "debug", "trace", "log",
        }
        _NOISE_PREFIXES = {
            "e", "o", "the", "a", "an", "if", "but", "and", "or",
            "so", "yet", "nor", "for", "it", "this", "that", "what",
            "how", "why", "when", "where", "who", "which", "result",
            "note", "example", "step", "concept", "twist",
            "s_special", "e_logic", "e_why", "shows", "tells",
            "circular", "line", "sun", "member", "role",
            "sensing", "context", "run", "actuation", "execution",
            "members", "scenario", "watering", "model", "rain",
            "system", "here", "there", "where", "our", "my",
        }
        _SINGLE_VALUE_NOISE = {
            "sensor", "model", "label", "value", "moisture",
            "humidity", "resistor", "gauge", "graph", "icon",
            "yes", "no", "true", "false", "none", "null",
            "stop", "start", "high", "low", "medium",
        }
        _SENTENCE_STARTS = (
            "the ", "a ", "an ", "it ", "this ", "that ", "these ",
            "those ", "we ", "you ", "they ", "he ", "she ", "normal ",
            "before ", "your ", "shows ", "tells ", "will ", "can ",
            "should ", "would ", "could ", "may ", "might ",
            "set ", "make ", "find ", "get ", "put ", "do ",
            "write ", "read ", "build ", "create ", "handle ",
            "large ", "small ", "how ", "what ", "if ", "when ",
            "○ ", "● ", "■ ",
        )

        entities: list[Entity] = []
        for page in doc.pages:
            for line in page.text.splitlines():
                normalized = line.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
                parsed_pairs = self._parse_multi_kv_line(normalized)
                if not parsed_pairs:
                    parsed = self._parse_kv_line(normalized)
                    parsed_pairs = [parsed] if parsed else []
                if not parsed_pairs:
                    parsed = self._parse_amount_line(normalized)
                    parsed_pairs = [parsed] if parsed else []
                for parsed in parsed_pairs:
                    if not parsed:
                        continue
                    key, value = parsed
                    if not key or not value:
                        continue

                    if len(key) < 3 or len(key) > 50:
                        continue
                    if len(value) > 180:
                        continue
                    key_words = key.replace("_", " ").split()
                    if len(key_words) > 5:
                        continue
                    if len(key_words) == 1 and key_words[0].lower() in _SINGLE_WORD_NOISE:
                        continue
                    first_word = key_words[0].lower() if key_words else ""
                    if first_word in _NOISE_PREFIXES:
                        continue
                    digit_count = sum(char.isdigit() for char in key)
                    if digit_count > 2:
                        continue

                    if len(value.strip()) <= 1:
                        continue
                    value_stripped = value.strip()
                    if _RE_BULLET_PREFIX.match(value_stripped):
                        continue
                    if value_stripped.startswith('[') or value_stripped.startswith('{'):
                        continue
                    if '->' in value or '=>' in value:
                        continue
                    if value_stripped.endswith('"') and not value_stripped.startswith('"'):
                        continue
                    if value_stripped.startswith('"') and not value_stripped.endswith('"'):
                        continue
                    if value_stripped.endswith(','):
                        value = value_stripped = value_stripped[:-1].strip()
                        if not value_stripped:
                            continue
                    if value_stripped.count('(') != value_stripped.count(')'):
                        continue
                    value_words = value.strip().split()
                    if len(value_words) == 1 and value_words[0].lower() in _SINGLE_VALUE_NOISE:
                        continue
                    value_lower = value.lower().strip()
                    if any(value_lower.startswith(s) for s in _SENTENCE_STARTS):
                        continue
                    if value.startswith('"') and value.endswith('"'):
                        inner = value[1:-1].strip()
                        if len(inner.split()) <= 4:
                            continue

                    confidence = 0.55
                    if re.match(r'^[\d.,/$%]+$', value.strip()):
                        confidence = 0.72
                    elif re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$', value.strip()):
                        confidence = 0.75
                    elif re.match(r'^[A-Z0-9][A-Z0-9-]{2,}$', value.strip()):
                        confidence = 0.70
                    elif len(value.split()) > 8:
                        confidence = 0.35
                    span = self._span_for_line(page.text, line, value)
                    entities.append(
                        Entity(
                            key=key,
                            value=value,
                            confidence=confidence,
                            page=page.number,
                            span=span,
                            metadata={"generic_kv": True, "evidence": value},
                        )
                    )
        return entities

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
        if not explicit_key_set:
            return entities
        filtered: list[Entity] = []
        for entity in entities:
            if self._normalize_key(entity.key) in explicit_key_set:
                filtered.append(entity)
        return filtered

    def _merge_by_key(self, entities: list[Entity]) -> list[Entity]:
        selected: dict[str, Entity] = {}
        for entity in entities:
            key = self._normalize_key(entity.key)
            current = selected.get(key)
            if not current or entity.confidence > current.confidence:
                selected[key] = entity
        return list(selected.values())

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
                    "value": "",
                    "source": "none",
                }
                continue
            source = str((entity.metadata or {}).get("source", "unknown"))
            if entity.confidence >= threshold:
                status = "extracted"
            elif entity.confidence >= low_threshold:
                status = "low_confidence"
            else:
                status = "low_confidence"
            status_map[norm_key] = {
                "status": status,
                "confidence": entity.confidence,
                "value": entity.value,
                "source": source,
            }
        return status_map

    def _canonicalize_entities(
        self,
        entities: list[Entity],
        explicit_keys: list[str],
        field_descriptions: dict[str, str],
    ) -> list[Entity]:
        if not entities:
            return []
        explicit_norm = [self._normalize_key(key) for key in explicit_keys if self._normalize_key(key)]
        if not explicit_norm:
            return entities

        canonicalized: list[Entity] = []
        for entity in entities:
            raw_key = self._normalize_key(entity.key)
            target_key = raw_key
            match_key, score = self._closest_explicit_key(raw_key, explicit_norm, field_descriptions)
            if match_key and score >= 0.62:
                target_key = match_key
            metadata = dict(entity.metadata or {})
            if target_key != raw_key:
                metadata["canonicalized_from"] = raw_key
            canonicalized.append(
                Entity(
                    key=target_key,
                    value=entity.value,
                    confidence=entity.confidence,
                    page=entity.page,
                    span=entity.span,
                    metadata=metadata,
                )
            )
        return canonicalized

    def _closest_explicit_key(
        self,
        candidate_key: str,
        explicit_keys: list[str],
        field_descriptions: dict[str, str],
    ) -> tuple[str | None, float]:
        best_key = None
        best_score = 0.0
        for target in explicit_keys:
            score = self._field_match_score(candidate_key, target, field_descriptions.get(target, ""))
            if score > best_score:
                best_score = score
                best_key = target
        return best_key, best_score

    def _field_match_score(self, candidate: str, target: str, description: str) -> float:
        if not candidate or not target:
            return 0.0
        if candidate == target:
            return 1.0

        cand_tokens = set(self._tokenize(candidate))
        target_tokens = self._field_tokens(target, description)
        if not cand_tokens or not target_tokens:
            return 0.0

        overlap = len(cand_tokens.intersection(target_tokens))
        union = len(cand_tokens.union(target_tokens))
        containment = overlap / max(len(target_tokens), 1)
        jaccard = overlap / max(union, 1)
        score = max(containment, jaccard)

        if candidate in target or target in candidate:
            score += 0.2
        if overlap and any(token in {"id", "number", "date", "amount", "total"} for token in cand_tokens):
            score += 0.08
        return min(score, 1.0)

    def _field_tokens(self, key: str, description: str) -> set[str]:
        tokens = set(self._tokenize(key))
        expanded = set(tokens)
        for token in list(tokens):
            for alt in _TOKEN_EQUIVALENTS.get(token, ()):
                expanded.update(self._tokenize(alt))
        desc_tokens = {
            token
            for token in self._tokenize(description)
            if token not in _DESC_STOPWORDS and len(token) > 2
        }
        return expanded.union(desc_tokens)

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
        key = _RE_NORMALIZE_KEY.sub("_", raw.strip().lower()).strip("_")
        # Truncate excessively long keys to 40 chars at word boundary
        if len(key) > 40:
            truncated = key[:40]
            last_underscore = truncated.rfind("_")
            if last_underscore > 20:
                key = truncated[:last_underscore]
            else:
                key = truncated
        return key

    def _span_for_line(self, page_text: str, line: str, value: str) -> tuple[int, int] | None:
        start = page_text.find(line)
        if start == -1:
            return None
        value_start = line.find(value)
        if value_start == -1:
            return None
        span_start = start + value_start
        return (span_start, span_start + len(value))

    def _parse_kv_line(self, line: str) -> tuple[str, str] | None:
        cleaned = line.strip()
        if not cleaned:
            return None
        match = _RE_KV_COLON.match(cleaned)
        if not match:
            match = _RE_KV_SPACE.match(cleaned)
        if not match:
            return None
        key_part = match.group(1).strip()
        value_part = match.group(2).strip()
        if not key_part or not value_part or len(value_part) > 200:
            return None
        return self._normalize_key(key_part), value_part

    def _parse_multi_kv_line(self, line: str) -> list[tuple[str, str]]:
        cleaned = line.strip()
        if not cleaned:
            return []
        pairs: list[tuple[str, str]] = []
        for match in _RE_MULTI_KV.finditer(cleaned):
            label = match.group("label").strip()
            value = match.group("value").strip().strip(".")
            if not label or not value:
                continue
            if len(value) > 200:
                continue
            pairs.append((self._normalize_key(label), value))
        return pairs

    def _parse_amount_line(self, line: str) -> tuple[str, str] | None:
        cleaned = line.strip()
        if not cleaned:
            return None
        lowered = cleaned.lower()
        if not any(token in lowered for token in ["total", "amount", "balance", "due", "subtotal", "invoice total"]):
            return None
        match = _RE_AMOUNT.search(cleaned)
        if not match:
            return None
        value = match.group(1).strip()
        prefix = cleaned[: match.start()].strip()
        key = self._normalize_key(prefix) if prefix else "amount"
        return key, value

    def _match_rule_in_pages(self, doc: Document, pattern: str) -> tuple[str | None, int | None, tuple[int, int] | None]:
        for page in doc.pages:
            match = re.search(pattern, page.text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                return value, page.number, match.span(1)
        return None, None, None

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
            smart = self._smart_field_extract(key, doc, text)
            if smart:
                filled.append(smart)
                continue
            desc = field_descriptions.get(key, "")
            anchored = self._extract_by_label_anchor(key, desc, doc)
            if anchored:
                filled.append(anchored)
                continue
            tokens = self._tokenize(f"{key} {desc}")
            match = self._best_generic_match(tokens, generic_by_key)
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
            fallback = self._regex_fallback(key, tokens, text)
            if fallback:
                filled.append(fallback)
        return filled

    def _smart_field_extract(self, key: str, doc: Document, text: str) -> Entity | None:
        """Use document structure to extract common field types."""
        key_lower = key.lower()

        # --- Project/document title ---
        if any(tok in key_lower for tok in ["title", "project_name", "document_name"]):
            # Strategy 1: Look for explicit "Title:" or "Project Title:" label
            title_match = re.search(
                r'(?:project\s+title|title|project\s+name|document\s+title)\s*[:=\-]\s*(.+)',
                text, re.IGNORECASE,
            )
            if title_match:
                val = title_match.group(1).strip()
                if 2 < len(val) < 100:
                    return Entity(key=key, value=val, confidence=0.80,
                                  metadata={"explicit": True, "source": "smart_heuristic"})
            # Strategy 2: First non-empty line of page 1 (common title position)
            if doc.pages:
                first_page_text = doc.pages[0].text
                for line in first_page_text.splitlines():
                    line = line.strip()
                    if line and len(line) > 2 and len(line) < 80 and len(line.split()) <= 10:
                        # Check it looks like a title (not a sentence, not a number)
                        if not line[0].isdigit() and not line.startswith(('●', '○', '■', '•', '-', '*')):
                            return Entity(key=key, value=line, confidence=0.70,
                                          metadata={"explicit": True, "source": "smart_heuristic", "rule": "first_line"})
                        break
            # Strategy 3: Use the document filename (doc_id) as a fallback
            if doc.doc_id and len(doc.doc_id) > 2:
                # Clean up common filename artifacts
                clean_name = re.sub(r'[_-]', ' ', doc.doc_id).strip()
                if clean_name:
                    return Entity(key=key, value=clean_name, confidence=0.60,
                                  metadata={"explicit": True, "source": "smart_heuristic", "rule": "filename"})

        # --- Team members / authors ---
        if any(tok in key_lower for tok in ["member", "author", "team", "contributor", "participant"]):
            # Look for "Members:", "Team:", "Authors:" label followed by names
            members_match = re.search(
                r'(?:team\s+members?|members?|authors?|prepared\s+by|contributors?|participants?)\s*[:=\-]\s*(.+?)(?:\n\n|\n(?=[A-Z][a-z]+\s*:)|\Z)',
                text, re.IGNORECASE | re.DOTALL,
            )
            if members_match:
                raw_val = members_match.group(1).strip()
                # Clean up bullet points and newlines
                cleaned = re.sub(r'[○●■□▪▸►▶•]', '', raw_val)
                cleaned = re.sub(r'\n+', ', ', cleaned).strip(', ')
                if 2 < len(cleaned) < 300:
                    return Entity(key=key, value=cleaned, confidence=0.75,
                                  metadata={"explicit": True, "source": "smart_heuristic"})
            # Look for "Member N:" patterns
            member_lines = re.findall(r'Member\s*\d+\s*[:=\-]\s*(.+)', text, re.IGNORECASE)
            if member_lines:
                val = ", ".join(m.strip() for m in member_lines)
                if 2 < len(val) < 300:
                    return Entity(key=key, value=val, confidence=0.70,
                                  metadata={"explicit": True, "source": "smart_heuristic"})

        # --- Supervisor / advisor ---
        if any(tok in key_lower for tok in ["supervisor", "advisor", "professor", "mentor", "instructor"]):
            supervisor_match = re.search(
                r'(?:supervisor|advisor|professor|mentor|instructor|supervised\s+by|advised\s+by)\s*[:=\-]\s*(.+)',
                text, re.IGNORECASE,
            )
            if supervisor_match:
                val = supervisor_match.group(1).strip()
                val = re.sub(r'[○●■□▪▸►▶•]', '', val).strip()
                if 2 < len(val) < 100:
                    return Entity(key=key, value=val, confidence=0.80,
                                  metadata={"explicit": True, "source": "smart_heuristic"})

        # --- Date fields ---
        if any(tok in key_lower for tok in ["date", "submitted", "created", "issued"]):
            date_match = re.search(
                r'(?:date|submitted|created|issued)\s*[:=\-]\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})',
                text, re.IGNORECASE,
            )
            if date_match:
                return Entity(key=key, value=date_match.group(1).strip(), confidence=0.78,
                              metadata={"explicit": True, "source": "smart_heuristic"})

        # --- Course / subject ---
        if any(tok in key_lower for tok in ["course", "subject", "module", "class_name"]):
            course_match = re.search(
                r'(?:course|subject|module|class)\s*(?:name|code|number)?\s*[:=\-]\s*(.+)',
                text, re.IGNORECASE,
            )
            if course_match:
                val = course_match.group(1).strip()
                if 2 < len(val) < 100:
                    return Entity(key=key, value=val, confidence=0.75,
                                  metadata={"explicit": True, "source": "smart_heuristic"})

        return None

    def _extract_by_label_anchor(self, key: str, description: str, doc: Document) -> Entity | None:
        variants = self._field_label_variants(key, description)
        if not variants:
            return None

        for page in doc.pages:
            lines = page.text.splitlines()
            for idx, raw_line in enumerate(lines):
                line = raw_line.strip()
                if not line or len(line) > 240:
                    continue
                for label in variants:
                    escaped = re.escape(label)
                    inline = re.search(
                        rf"(?i)\b{escaped}\b\s*(?:[:=\-#]|is)?\s*(.+)$",
                        line,
                    )
                    if inline:
                        value = self._clean_candidate_value(inline.group(1))
                        if self._is_valid_candidate_value(value):
                            span = self._span_for_line(page.text, raw_line, value)
                            return Entity(
                                key=key,
                                value=value,
                                confidence=0.68,
                                page=page.number,
                                span=span,
                                metadata={"explicit": True, "source": "label_anchor"},
                            )

                    # Common pattern where label is on one line and value on the next.
                    label_only = re.fullmatch(rf"(?i){escaped}\s*[:=\-#]?\s*", line)
                    if label_only and idx + 1 < len(lines):
                        next_raw = lines[idx + 1]
                        next_value = self._clean_candidate_value(next_raw)
                        if self._is_valid_candidate_value(next_value):
                            span = self._span_for_line(page.text, next_raw, next_value)
                            return Entity(
                                key=key,
                                value=next_value,
                                confidence=0.64,
                                page=page.number,
                                span=span,
                                metadata={"explicit": True, "source": "label_anchor_next_line"},
                            )
        return None

    def _field_label_variants(self, key: str, description: str) -> list[str]:
        base_tokens = self._tokenize(key)
        if not base_tokens:
            return []
        variants = {" ".join(base_tokens)}

        # Token-level synonym expansion.
        for idx, token in enumerate(base_tokens):
            for alt in _TOKEN_EQUIVALENTS.get(token, ()):
                alt_tokens = list(base_tokens)
                alt_tokens[idx : idx + 1] = self._tokenize(alt)
                variants.add(" ".join(alt_tokens))

        if "number" in base_tokens:
            variants.add(" ".join("no" if tok == "number" else tok for tok in base_tokens))
            variants.add(" ".join("#" if tok == "number" else tok for tok in base_tokens))

        if description:
            desc_tokens = [
                token
                for token in self._tokenize(description)
                if token not in _DESC_STOPWORDS and len(token) > 2
            ]
            if desc_tokens:
                variants.add(" ".join(desc_tokens[:4]))

        cleaned = [item.strip() for item in variants if item and len(item.split()) <= 5]
        cleaned.sort(key=len, reverse=True)
        return cleaned[:12]

    def _clean_candidate_value(self, raw: str) -> str:
        value = (raw or "").strip()
        value = _RE_BULLET_PREFIX.sub("", value).strip()
        value = re.sub(r"^[\-\:=#\|]+", "", value).strip()
        value = re.sub(r"\s+", " ", value)
        value = value.strip("|;,. ")
        return value

    def _is_valid_candidate_value(self, value: str) -> bool:
        if not value:
            return False
        lowered = value.lower().strip()
        if lowered in _MISSING_VALUE_MARKERS:
            return False
        if len(value) < 2 or len(value) > 180:
            return False
        if value.endswith(":"):
            return False
        if value.count(" ") == 0 and re.fullmatch(r"[A-Za-z]+", value) and len(value) <= 2:
            return False
        return True

    def _best_generic_match(self, tokens: list[str], generic_by_key: dict[str, list[Entity]]) -> Entity | None:
        if not tokens:
            return None
        best = None
        best_score = 0.0
        token_set = set(tokens)
        for key, entities in generic_by_key.items():
            key_tokens = set(self._tokenize(key))
            if not key_tokens:
                continue
            overlap = token_set.intersection(key_tokens)
            score = len(overlap) / max(len(token_set), 1)
            if key in token_set or any(tok in key for tok in token_set):
                score += 0.15
            if score > best_score:
                best_score = score
                best = max(entities, key=lambda item: item.confidence)
        # Require stronger match to avoid garbage matches
        if best_score >= 0.55:
            return best
        return None

    def _regex_fallback(self, key: str, tokens: list[str], text: str) -> Entity | None:
        lowered = " ".join(tokens)
        if any(token in lowered for token in ["amount", "total", "balance", "due", "price", "cost"]):
            candidates = re.findall(
                r"(?:total|amount|balance|due|subtotal|tax|invoice\s+total)[^\d\n]{0,18}"
                r"((?:\$|usd\s*)?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",
                text,
                re.IGNORECASE,
            )
            if candidates:
                best = max(
                    candidates,
                    key=lambda item: float(item.replace(",", "").replace("usd", "").replace("$", "") or 0),
                )
                return Entity(
                    key=key,
                    value=best.strip(),
                    confidence=0.45,
                    metadata={"explicit": True, "source": "schema_regex", "rule": "amount"},
                )
            currency = re.findall(r"(?:\$|usd\s*)\d{1,3}(?:,\d{3})*(?:\.\d{2})?", text, re.IGNORECASE)
            if currency:
                best = max(
                    currency,
                    key=lambda item: float(item.replace(",", "").replace("usd", "").replace("$", "") or 0),
                )
                return Entity(
                    key=key,
                    value=best.strip(),
                    confidence=0.4,
                    metadata={"explicit": True, "source": "schema_regex", "rule": "amount_any"},
                )
        if any(token in lowered for token in ["date", "issued", "invoice_date", "due_date"]):
            date_match = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
            if not date_match:
                date_match = re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b", text, re.IGNORECASE)
            if not date_match:
                date_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
            if date_match:
                return Entity(
                    key=key,
                    value=date_match.group(0),
                    confidence=0.45,
                    metadata={"explicit": True, "source": "schema_regex", "rule": "date"},
                )
        if any(token in lowered for token in ["invoice", "id", "number", "reference"]):
            id_match = re.search(r"\b[A-Z]{0,4}[\-#]?\d{3,}[A-Z0-9-]*\b", text)
            if not id_match:
                id_match = re.search(r"\b[A-Z0-9-]{5,}\b", text)
            if id_match:
                return Entity(
                    key=key,
                    value=id_match.group(0),
                    confidence=0.42,
                    metadata={"explicit": True, "source": "schema_regex", "rule": "id"},
                )
        if any(token in lowered for token in ["fax", "phone", "telephone", "tel"]):
            phone_pattern = r"\(?(\d{3})\)?[-.\s]*(\d{3})[-.\s]*(\d{4})"
            fax_match = None
            if "fax" in lowered:
                fax_match = re.search(r"fax[^\d]{0,6}" + phone_pattern, text, re.IGNORECASE)
            if fax_match:
                number = "-".join(fax_match.groups())
                return Entity(
                    key=key,
                    value=number,
                    confidence=0.45,
                    metadata={"explicit": True, "source": "schema_regex", "rule": "fax"},
                )
            phone_match = re.search(phone_pattern, text)
            if phone_match:
                number = "-".join(phone_match.groups())
                return Entity(
                    key=key,
                    value=number,
                    confidence=0.42,
                    metadata={"explicit": True, "source": "schema_regex", "rule": "phone"},
                )
        return None

    def _tokenize(self, text: str) -> list[str]:
        return [part for part in re.split(r"[^a-z0-9]+", text.lower()) if part]

    def _llm_extract(
        self,
        doc: Document,
        explicit_keys: list[str],
        model_name: str,
        ctx: AgentContext,
        field_descriptions: dict[str, str] | None = None,
    ) -> list[Entity] | tuple[list[Entity], dict[str, object]]:
        started = time.time()
        text, context_meta = self._build_extraction_input(doc, explicit_keys, field_descriptions or {}, ctx)
        if not text.strip():
            return [], {"provider": "ollama", "model": model_name, "error": "empty_document", "latency_ms": 0.0}
        prompt = self._build_prompt(text, explicit_keys, ctx, field_descriptions or {})
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
        }
        response = self._ollama_request(
            ctx.config.llm.base_url,
            payload,
            ctx.config.llm.timeout_s,
        )
        meta = {
            "provider": "ollama",
            "model": model_name,
            "prompt_chars": len(prompt),
            "requested_fields": len(explicit_keys),
            "latency_ms": (time.time() - started) * 1000,
            "success": False,
            "entity_count": 0,
            "prompt_version": "extraction_v2",
            "context": context_meta,
        }
        if not response:
            meta["error"] = "empty_or_unavailable"
            return [], meta
        entities = self._parse_entities_response(response, model_name, source="llm_local")
        meta["success"] = bool(entities)
        meta["entity_count"] = len(entities)
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
        text, context_meta = self._build_extraction_input(doc, explicit_keys, field_descriptions or {}, ctx)
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
        prompt = self._build_prompt(text, explicit_keys, ctx, field_descriptions or {})
        meta["prompt_chars"] = len(prompt)
        provider = ctx.config.llm.cloud_provider
        if provider == "openai":
            request_meta = meta.get("request")
            if isinstance(request_meta, dict):
                request_meta["endpoint"] = "chat.completions"
            if not OPENAI_AVAILABLE:
                meta["error"] = "openai_sdk_unavailable"
                meta["latency_ms"] = (time.time() - started) * 1000
                return [], meta
            api_key = os.getenv("OPENAI_API_KEY") or ctx.config.llm.openai_api_key
            _key = (api_key or "").strip().lower()
            if (
                not _key
                or _key == "sk-placeholder"
                or _key.startswith("${")
                or "your" in _key and "key" in _key   # e.g. sk-your-key-here
                or _key in ("sk-", "sk-xxx", "sk-test", "changeme", "replace-me")
            ):
                meta["error"] = "missing_or_placeholder_key"
                meta["latency_ms"] = (time.time() - started) * 1000
                return [], meta
            base_url = os.getenv("OPENAI_API_URL") or ctx.config.llm.openai_api_url
            base_url = self._normalize_openai_base_url(base_url)
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=ctx.config.llm.cloud_timeout_s)
            kwargs = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "Return only valid JSON with extracted entities."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": ctx.config.llm.cloud_temperature,
                "max_tokens": cloud_max_tokens,
            }
            if ctx.config.llm.strict_json_output:
                kwargs["response_format"] = self._openai_response_format(explicit_keys)
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as exc:
                if ctx.config.llm.strict_json_output and ctx.config.llm.cloud_retry_without_json_mode:
                    kwargs.pop("response_format", None)
                    try:
                        response = client.chat.completions.create(**kwargs)
                    except Exception as retry_exc:
                        meta["error"] = str(retry_exc)[:220]
                        meta["latency_ms"] = (time.time() - started) * 1000
                        return [], meta
                else:
                    meta["error"] = str(exc)[:220]
                    meta["latency_ms"] = (time.time() - started) * 1000
                    return [], meta

            content = response.choices[0].message.content if response.choices else ""
            usage = getattr(response, "usage", None)
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)
            entities = self._parse_entities_response(content or "", model_name, source="llm_cloud")
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
            request_meta = meta.get("request")
            if isinstance(request_meta, dict):
                request_meta["endpoint"] = "messages.create"
            if not ANTHROPIC_AVAILABLE:
                meta["error"] = "anthropic_sdk_unavailable"
                meta["latency_ms"] = (time.time() - started) * 1000
                return [], meta
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                meta["error"] = "missing_anthropic_key"
                meta["latency_ms"] = (time.time() - started) * 1000
                return [], meta
            client = Anthropic(api_key=api_key)
            try:
                response = client.messages.create(
                    model=model_name,
                    max_tokens=cloud_max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
            except Exception as exc:
                meta["error"] = str(exc)[:220]
                meta["latency_ms"] = (time.time() - started) * 1000
                return [], meta
            content = response.content[0].text if response.content else ""
            entities = self._parse_entities_response(content or "", model_name, source="llm_cloud")
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            meta.update(
                {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "latency_ms": (time.time() - started) * 1000,
                    "success": bool(entities),
                    "entity_count": len(entities),
                }
            )
            return entities, meta
        meta["error"] = "unknown_provider"
        meta["latency_ms"] = (time.time() - started) * 1000
        return [], meta

    def _build_prompt(
        self,
        text: str,
        explicit_keys: list[str],
        ctx: AgentContext,
        field_descriptions: dict[str, str],
    ) -> str:
        keys = explicit_keys or [rule.key for rule in ctx.config.structuring.extraction_rules]
        # Build a structured field list with descriptions inline for better accuracy
        if field_descriptions and keys:
            fields_block = "\n".join(
                f"  - \"{key}\": {field_descriptions.get(key, 'Extract this field value')}"
                for key in keys
            )
        elif keys:
            fields_block = "\n".join(f"  - \"{key}\"" for key in keys)
        else:
            fields_block = "  - Extract any relevant key-value fields you find"

        return (
            "You are an expert document data extraction system.\n\n"
            "TASK: Extract structured fields from the document text below.\n\n"
            "FIELDS TO EXTRACT:\n"
            f"{fields_block}\n\n"
            "RULES:\n"
            "1. Return ONLY valid JSON with top-level key 'entities' as a list.\n"
            "2. Each entity object must be exactly: {\"key\": \"<requested_key>\", \"value\": \"<exact_span>\", \"confidence\": <0.0-1.0>}.\n"
            "3. Use ONLY requested key names; never invent keys.\n"
            "4. If a field is not found, omit it (no hallucinated values).\n"
            "5. Prefer exact spans from the text. Keep original formatting for amounts, IDs, and dates.\n"
            "6. Confidence: 0.9+ exact evidence, 0.6-0.8 probable, <0.6 weak.\n"
            "7. No markdown, no explanations, no extra keys.\n\n"
            "8. At most one entity per key; keep the best supported value.\n\n"
            "DOCUMENT TEXT:\n"
            "```\n"
            f"{text}\n"
            "```\n\n"
            "Return JSON:\n"
        )

    def _build_extraction_text(
        self,
        doc: Document,
        explicit_keys: list[str],
        field_descriptions: dict[str, str],
        ctx: AgentContext,
    ) -> str:
        text, _ = self._build_extraction_input(doc, explicit_keys, field_descriptions, ctx)
        return text

    def _build_extraction_input(
        self,
        doc: Document,
        explicit_keys: list[str],
        field_descriptions: dict[str, str],
        ctx: AgentContext,
    ) -> tuple[str, dict[str, object]]:
        full_text = "\n".join(page.text for page in doc.pages)
        meta: dict[str, object] = {
            "strategy": "empty",
            "full_chars": len(full_text),
            "selected_chars": 0,
            "truncated": False,
            "targeted_context_chars": 0,
            "targeted_context_lines": 0,
        }
        if not full_text.strip():
            return "", meta

        max_chars = max(2000, int(ctx.config.llm.prompt_max_chars))
        if len(full_text) <= max_chars:
            meta.update({"strategy": "full", "selected_chars": len(full_text)})
            return full_text, meta
        if not ctx.config.llm.prefer_targeted_context:
            truncated = self._smart_truncate(full_text, max_chars)
            meta.update(
                {
                    "strategy": "truncate",
                    "selected_chars": len(truncated),
                    "truncated": len(truncated) < len(full_text),
                }
            )
            return truncated, meta

        targeted = self._targeted_context(
            doc,
            explicit_keys,
            field_descriptions,
            window_lines=max(0, int(ctx.config.llm.context_window_lines)),
        )
        if targeted:
            targeted_lines = len([line for line in targeted.splitlines() if line.strip()])
            meta["targeted_context_chars"] = len(targeted)
            meta["targeted_context_lines"] = targeted_lines
            if len(targeted) >= int(max_chars * 0.8):
                truncated = self._smart_truncate(targeted, max_chars)
                meta.update(
                    {
                        "strategy": "targeted_only",
                        "selected_chars": len(truncated),
                        "truncated": len(truncated) < len(full_text),
                    }
                )
                return truncated, meta
            remaining = max(0, max_chars - len(targeted) - 2)
            if remaining:
                combined = targeted + "\n\n" + self._smart_truncate(full_text, remaining)
                meta.update(
                    {
                        "strategy": "targeted_plus_truncated",
                        "selected_chars": len(combined),
                        "truncated": len(combined) < len(full_text),
                    }
                )
                return combined, meta
            meta.update(
                {
                    "strategy": "targeted_only",
                    "selected_chars": len(targeted),
                    "truncated": len(targeted) < len(full_text),
                }
            )
            return targeted, meta
        truncated = self._smart_truncate(full_text, max_chars)
        meta.update(
            {
                "strategy": "truncate",
                "selected_chars": len(truncated),
                "truncated": len(truncated) < len(full_text),
            }
        )
        return truncated, meta

    def _targeted_context(
        self,
        doc: Document,
        explicit_keys: list[str],
        field_descriptions: dict[str, str],
        window_lines: int = 1,
    ) -> str:
        if not explicit_keys:
            return ""
        terms: set[str] = set()
        for key in explicit_keys:
            terms.update(token for token in self._tokenize(key) if len(token) > 2)
            description = field_descriptions.get(key, "")
            terms.update(
                token
                for token in self._tokenize(description)
                if token not in _DESC_STOPWORDS and len(token) > 2
            )
        if not terms:
            return ""

        seen: set[tuple[int, int]] = set()
        snippets: list[str] = []
        for page in doc.pages:
            lines = page.text.splitlines()
            for idx, line in enumerate(lines):
                lowered = line.lower()
                if not any(term in lowered for term in terms):
                    continue
                start = max(0, idx - window_lines)
                end = min(len(lines), idx + window_lines + 1)
                for line_idx in range(start, end):
                    marker = (page.number, line_idx)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    text_line = lines[line_idx].strip()
                    if not text_line:
                        continue
                    snippets.append(f"[p{page.number}] {text_line}")
        return "\n".join(snippets)

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
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if not cleaned:
            return []
        parsed = self._parse_json_payload(cleaned)
        if parsed is None:
            return []

        if isinstance(parsed, dict) and "entities" not in parsed:
            # Also support {"field_a": "...", "field_b": "..."} shapes.
            items = [
                {"key": key, "value": value, "confidence": 0.65}
                for key, value in parsed.items()
                if isinstance(value, (str, int, float, bool))
            ]
        else:
            items = parsed.get("entities", parsed) if isinstance(parsed, dict) else parsed
        if isinstance(items, dict):
            if {"key", "value"}.issubset(items.keys()):
                items = [items]
            else:
                items = [
                    {"key": key, "value": value, "confidence": 0.65}
                    for key, value in items.items()
                    if isinstance(value, (str, int, float, bool))
                ]

        entities: list[Entity] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            key = self._normalize_key(str(item.get("key", "")).strip())
            raw_value = item.get("value", "")
            value = self._clean_candidate_value(str(raw_value))
            if not key or not value:
                continue
            if value.lower() in _MISSING_VALUE_MARKERS:
                continue
            try:
                confidence = float(item.get("confidence", 0.7))
            except Exception:
                confidence = 0.7
            confidence = max(0.0, min(confidence, 1.0))
            entities.append(
                Entity(
                    key=key,
                    value=value,
                    confidence=confidence,
                    metadata={"explicit": True, "source": source, "model": model_name},
                )
            )
        return entities

    def _parse_json_payload(self, cleaned: str) -> object | None:
        try:
            return json.loads(cleaned)
        except Exception:
            pass

        # Fall back to the largest bracketed JSON snippet inside model chatter.
        object_start = cleaned.find("{")
        object_end = cleaned.rfind("}")
        if object_start != -1 and object_end > object_start:
            candidate = cleaned[object_start : object_end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        array_start = cleaned.find("[")
        array_end = cleaned.rfind("]")
        if array_start != -1 and array_end > array_start:
            candidate = cleaned[array_start : array_end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                return None
        return None

    def _normalize_openai_base_url(self, base_url: str) -> str:
        if not base_url:
            return "https://api.openai.com/v1"
        cleaned = base_url.rstrip("/")
        if cleaned.endswith("/chat/completions"):
            cleaned = cleaned[: -len("/chat/completions")]
        if cleaned.endswith("/v1"):
            return cleaned
        return cleaned

    def _smart_truncate(self, text: str, max_chars: int) -> str:
        """Truncate text at a paragraph or sentence boundary to avoid cutting mid-entity."""
        if len(text) <= max_chars:
            return text
        # Try to break at a paragraph boundary
        truncated = text[:max_chars]
        last_para = truncated.rfind("\n\n")
        if last_para > max_chars * 0.7:
            return truncated[:last_para]
        # Try to break at a sentence boundary
        last_sentence = max(truncated.rfind(". "), truncated.rfind(".\n"))
        if last_sentence > max_chars * 0.7:
            return truncated[:last_sentence + 1]
        # Try to break at a line boundary
        last_line = truncated.rfind("\n")
        if last_line > max_chars * 0.8:
            return truncated[:last_line]
        return truncated

    def _ollama_request(self, base_url: str, payload: dict[str, object], timeout_s: int) -> str | None:
        url = base_url.rstrip("/") + "/api/generate"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.URLError:
            return None
        try:
            parsed = json.loads(body)
            return parsed.get("response")
        except Exception:
            return None


