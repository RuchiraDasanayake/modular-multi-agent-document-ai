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

class LLMExtractionAgent(Agent):
    name = "llm_extraction"
    version = "v1"
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

        generic_entities = self._generic_kv_entities(doc)
        explicit_keys, explicit_source = self._explicit_keys(policy, ctx, generic_entities, explicit_override)

        explicit_entities = self._extract_explicit(doc, explicit_keys, generic_entities, ctx, policy, model)
        llm_entities: list[Entity] = []
        if ctx.config.llm.use_extraction and model:
            if model.mode == "local":
                llm_entities = self._llm_extract(
                    doc,
                    explicit_keys,
                    model.model_name,
                    ctx,
                    field_descriptions=field_descriptions,
                )
                if not llm_entities and ctx.config.llm.allow_cloud_fallback:
                    llm_entities = self._cloud_extract(
                        doc,
                        explicit_keys,
                        ctx.config.llm.cloud_model,
                        ctx,
                        field_descriptions=field_descriptions,
                    )
            elif model.mode == "cloud":
                llm_entities = self._cloud_extract(
                    doc,
                    explicit_keys,
                    model.model_name,
                    ctx,
                    field_descriptions=field_descriptions,
                )
        heuristic_entities = self._heuristic_schema_fill(
            doc,
            explicit_keys,
            field_descriptions or {},
            generic_entities,
            explicit_entities + llm_entities,
        )
        explicit_entities = self._merge_by_key(explicit_entities + llm_entities + heuristic_entities)
        default_entities = self._dedupe_entities(generic_entities)
        combined_entities = self._merge_entities(explicit_entities, default_entities)

        payload_json = {
            "doc_id": doc.doc_id,
            "policy_id": policy.policy_id if policy else None,
            "policy_name": policy.name if policy else None,
            "model_name": model.model_name if model else None,
            "model_mode": model.mode if model else None,
            "explicit_source": explicit_source,
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
        - Key constraints: length 3-50 chars, max 5 words, no digits, no noise prefixes
        - Value constraints: length 2-100 chars, no bullets/brackets/arrows/orphan quotes
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
                    if len(value) > 100:
                        continue
                    key_words = key.replace("_", " ").split()
                    if len(key_words) > 5:
                        continue
                    if len(key_words) == 1 and key_words[0].lower() in _SINGLE_WORD_NOISE:
                        continue
                    first_word = key_words[0].lower() if key_words else ""
                    if first_word in _NOISE_PREFIXES:
                        continue
                    if re.search(r'\d', key):
                        continue

                    if len(value.strip()) <= 1:
                        continue
                    value_stripped = value.strip()
                    if value_stripped and value_stripped[0] in '○●■□▪▸►▶•–—':
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
        combined = {}
        for entity in defaults:
            combined[(entity.key, entity.value)] = entity
        for entity in explicit:
            combined[(entity.key, entity.value)] = entity
        return list(combined.values())

    def _merge_by_key(self, entities: list[Entity]) -> list[Entity]:
        selected: dict[str, Entity] = {}
        for entity in entities:
            key = self._normalize_key(entity.key)
            current = selected.get(key)
            if not current or entity.confidence > current.confidence:
                selected[key] = entity
        return list(selected.values())

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
                best = entities[0]
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
    ) -> list[Entity]:
        text = "\n".join(page.text for page in doc.pages)
        if not text.strip():
            return []
        max_chars = 24000
        if len(text) > max_chars:
            text = self._smart_truncate(text, max_chars)
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
        if not response:
            return []
        return self._parse_entities_response(response, model_name, source="llm_local")

    def _cloud_extract(
        self,
        doc: Document,
        explicit_keys: list[str],
        model_name: str,
        ctx: AgentContext,
        field_descriptions: dict[str, str] | None = None,
    ) -> list[Entity]:
        text = "\n".join(page.text for page in doc.pages)
        if not text.strip():
            return []
        max_chars = 24000
        if len(text) > max_chars:
            text = self._smart_truncate(text, max_chars)
        prompt = self._build_prompt(text, explicit_keys, ctx, field_descriptions or {})
        provider = ctx.config.llm.cloud_provider
        if provider == "openai":
            if not OPENAI_AVAILABLE:
                return []
            api_key = os.getenv("OPENAI_API_KEY") or ctx.config.llm.openai_api_key
            _key = (api_key or "").strip().lower()
            if (
                not _key
                or _key == "sk-placeholder"
                or _key.startswith("${")
                or "your" in _key and "key" in _key   # e.g. sk-your-key-here
                or _key in ("sk-", "sk-xxx", "sk-test", "changeme", "replace-me")
            ):
                return []
            base_url = os.getenv("OPENAI_API_URL") or ctx.config.llm.openai_api_url
            base_url = self._normalize_openai_base_url(base_url)
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "Return only valid JSON with extracted entities."},
                    {"role": "user", "content": prompt},
                ],
                temperature=ctx.config.llm.cloud_temperature,
                max_tokens=ctx.config.llm.cloud_max_tokens,
            )
            content = response.choices[0].message.content if response.choices else ""
            return self._parse_entities_response(content or "", model_name, source="llm_cloud")
        if provider == "anthropic":
            if not ANTHROPIC_AVAILABLE:
                return []
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                return []
            client = Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model_name,
                max_tokens=ctx.config.llm.cloud_max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text if response.content else ""
            return self._parse_entities_response(content or "", model_name, source="llm_cloud")
        return []

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
            "1. Return ONLY valid JSON with key 'entities' as a list.\n"
            "2. Each entity must have: {\"key\": \"<field_name>\", \"value\": \"<extracted_value>\", \"confidence\": <0.0-1.0>}\n"
            "3. Set confidence based on how certain you are: 0.9+ for exact matches, 0.5-0.8 for inferred values.\n"
            "4. If a field is NOT found in the text, DO NOT include it (do not guess or hallucinate).\n"
            "5. Values should be exact text from the document, not paraphrased.\n"
            "6. For amounts, include currency symbols if present.\n"
            "7. For dates, preserve the original format from the document.\n\n"
            "DOCUMENT TEXT:\n"
            "```\n"
            f"{text}\n"
            "```\n\n"
            "Return JSON:\n"
        )

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
        try:
            parsed = json.loads(cleaned)
        except Exception:
            return []
        items = parsed.get("entities", parsed) if isinstance(parsed, dict) else parsed
        if isinstance(items, dict):
            items = [items]
        entities: list[Entity] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            value = str(item.get("value", "")).strip()
            if not key or not value:
                continue
            try:
                confidence = float(item.get("confidence", 0.7))
            except Exception:
                confidence = 0.7
            entities.append(
                Entity(
                    key=key,
                    value=value,
                    confidence=confidence,
                    metadata={"explicit": True, "source": source, "model": model_name},
                )
            )
        return entities

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
