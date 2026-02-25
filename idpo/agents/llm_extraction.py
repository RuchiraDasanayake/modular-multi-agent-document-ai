from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from typing import Dict, List, Optional, Tuple

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
        policy: Optional[ExtractionPolicy] = payload.get("policy")
        model: Optional[ModelDecision] = payload.get("model")
        input_artifact_id = payload.get("input_artifact_id")
        explicit_override = payload.get("explicit_entities")
        field_descriptions = payload.get("field_descriptions")

        generic_entities = self._generic_kv_entities(doc)
        explicit_keys, explicit_source = self._explicit_keys(policy, ctx, generic_entities, explicit_override)

        explicit_entities = self._extract_explicit(doc, explicit_keys, generic_entities, ctx, policy, model)
        llm_entities: List[Entity] = []
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
        policy: Optional[ExtractionPolicy],
        ctx: AgentContext,
        generic_entities: List[Entity],
        explicit_override: Optional[List[str]] = None,
    ) -> Tuple[List[str], str]:
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
        explicit_keys: List[str],
        generic_entities: List[Entity],
        ctx: AgentContext,
        policy: Optional[ExtractionPolicy],
        model: Optional[ModelDecision],
    ) -> List[Entity]:
        rule_map = {self._normalize_key(rule.key): rule for rule in ctx.config.structuring.extraction_rules}
        explicit_map: Dict[str, Entity] = {}
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

    def _generic_kv_entities(self, doc: Document) -> List[Entity]:
        entities: List[Entity] = []
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
                    span = self._span_for_line(page.text, line, value)
                    entities.append(
                        Entity(
                            key=key,
                            value=value,
                            confidence=0.55,
                            page=page.number,
                            span=span,
                            metadata={"generic_kv": True, "evidence": value},
                        )
                    )
        return entities

    def _infer_explicit_keys(self, entities: List[Entity]) -> List[str]:
        if not entities:
            return []
        counts = Counter(self._normalize_key(entity.key) for entity in entities)
        ordered = [key for key, _ in counts.most_common()]
        return ordered[: min(5, len(ordered))]

    def _merge_entities(self, explicit: List[Entity], defaults: List[Entity]) -> List[Entity]:
        combined = {}
        for entity in defaults:
            combined[(entity.key, entity.value)] = entity
        for entity in explicit:
            combined[(entity.key, entity.value)] = entity
        return list(combined.values())

    def _merge_by_key(self, entities: List[Entity]) -> List[Entity]:
        selected: Dict[str, Entity] = {}
        for entity in entities:
            key = self._normalize_key(entity.key)
            current = selected.get(key)
            if not current or entity.confidence > current.confidence:
                selected[key] = entity
        return list(selected.values())

    def _dedupe_entities(self, entities: List[Entity]) -> List[Entity]:
        seen = set()
        deduped = []
        for entity in entities:
            key = (entity.key, entity.value)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(entity)
        return deduped

    def _pick_best(self, selected: Dict[str, Entity], candidate: Entity) -> None:
        current = selected.get(candidate.key)
        if not current or candidate.confidence > current.confidence:
            selected[candidate.key] = candidate

    def _normalize_key(self, raw: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")

    def _span_for_line(self, page_text: str, line: str, value: str) -> Optional[tuple[int, int]]:
        start = page_text.find(line)
        if start == -1:
            return None
        value_start = line.find(value)
        if value_start == -1:
            return None
        span_start = start + value_start
        return (span_start, span_start + len(value))

    def _parse_kv_line(self, line: str) -> Optional[tuple[str, str]]:
        cleaned = line.strip()
        if not cleaned:
            return None
        match = re.match(r"^([A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s*[:=\-]\s*(.+)$", cleaned)
        if not match:
            match = re.match(r"^([A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s{2,}(.+)$", cleaned)
        if not match:
            return None
        key_part = match.group(1).strip()
        value_part = match.group(2).strip()
        if not key_part or not value_part or len(value_part) > 200:
            return None
        return self._normalize_key(key_part), value_part

    def _parse_multi_kv_line(self, line: str) -> List[tuple[str, str]]:
        cleaned = line.strip()
        if not cleaned:
            return []
        pairs: List[tuple[str, str]] = []
        pattern = re.compile(
            r"(?P<label>[A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s*[:=]\s*"
            r"(?P<value>.*?)(?=(?:[A-Za-z][A-Za-z0-9 #/&()._-]{1,40}\s*[:=])|$)"
        )
        for match in pattern.finditer(cleaned):
            label = match.group("label").strip()
            value = match.group("value").strip().strip(".")
            if not label or not value:
                continue
            if len(value) > 200:
                continue
            pairs.append((self._normalize_key(label), value))
        return pairs

    def _parse_amount_line(self, line: str) -> Optional[tuple[str, str]]:
        cleaned = line.strip()
        if not cleaned:
            return None
        lowered = cleaned.lower()
        if not any(token in lowered for token in ["total", "amount", "balance", "due", "subtotal", "invoice total"]):
            return None
        match = re.search(r"((?:\\$|usd\\s*)?\\d{1,3}(?:,\\d{3})*(?:\\.\\d{2})?)", cleaned)
        if not match:
            return None
        value = match.group(1).strip()
        prefix = cleaned[: match.start()].strip()
        key = self._normalize_key(prefix) if prefix else "amount"
        return key, value

    def _match_rule_in_pages(self, doc: Document, pattern: str) -> Tuple[Optional[str], Optional[int], Optional[tuple[int, int]]]:
        for page in doc.pages:
            match = re.search(pattern, page.text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                return value, page.number, match.span(1)
        return None, None, None

    def _heuristic_schema_fill(
        self,
        doc: Document,
        explicit_keys: List[str],
        field_descriptions: Dict[str, str],
        generic_entities: List[Entity],
        existing: List[Entity],
    ) -> List[Entity]:
        if not explicit_keys:
            return []
        filled: List[Entity] = []
        existing_keys = {self._normalize_key(entity.key) for entity in existing}
        generic_by_key: Dict[str, List[Entity]] = {}
        for entity in generic_entities:
            key = self._normalize_key(entity.key)
            generic_by_key.setdefault(key, []).append(entity)

        text = "\n".join(page.text for page in doc.pages)
        for key in explicit_keys:
            if key in existing_keys:
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

    def _best_generic_match(self, tokens: List[str], generic_by_key: Dict[str, List[Entity]]) -> Optional[Entity]:
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
        if best_score >= 0.35:
            return best
        return None

    def _regex_fallback(self, key: str, tokens: List[str], text: str) -> Optional[Entity]:
        lowered = " ".join(tokens)
        if any(token in lowered for token in ["amount", "total", "balance", "due", "price", "cost"]):
            candidates = re.findall(
                r"(?:total|amount|balance|due|subtotal|tax|invoice\\s+total)[^\\d\\n]{0,18}"
                r"((?:\\$|usd\\s*)?\\d{1,3}(?:,\\d{3})*(?:\\.\\d{2})?)",
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
            currency = re.findall(r"(?:\\$|usd\\s*)\\d{1,3}(?:,\\d{3})*(?:\\.\\d{2})?", text, re.IGNORECASE)
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
            date_match = re.search(r"\\b\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}\\b", text)
            if date_match:
                return Entity(
                    key=key,
                    value=date_match.group(0),
                    confidence=0.45,
                    metadata={"explicit": True, "source": "schema_regex", "rule": "date"},
                )
        if any(token in lowered for token in ["invoice", "id", "number", "reference"]):
            id_match = re.search(r"\\b[A-Z0-9-]{5,}\\b", text)
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

    def _tokenize(self, text: str) -> List[str]:
        return [part for part in re.split(r"[^a-z0-9]+", text.lower()) if part]

    def _llm_extract(
        self,
        doc: Document,
        explicit_keys: List[str],
        model_name: str,
        ctx: AgentContext,
        field_descriptions: Optional[Dict[str, str]] = None,
    ) -> List[Entity]:
        text = "\n".join(page.text for page in doc.pages)
        if not text.strip():
            return []
        max_chars = 12000
        if len(text) > max_chars:
            text = text[:max_chars]
        prompt = self._build_prompt(text, explicit_keys, ctx, field_descriptions or {})
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        response = self._ollama_request(ctx.config.llm.base_url, payload, ctx.config.llm.timeout_s)
        if not response:
            return []
        return self._parse_entities_response(response, model_name, source="llm_local")

    def _cloud_extract(
        self,
        doc: Document,
        explicit_keys: List[str],
        model_name: str,
        ctx: AgentContext,
        field_descriptions: Optional[Dict[str, str]] = None,
    ) -> List[Entity]:
        text = "\n".join(page.text for page in doc.pages)
        if not text.strip():
            return []
        max_chars = 12000
        if len(text) > max_chars:
            text = text[:max_chars]
        prompt = self._build_prompt(text, explicit_keys, ctx, field_descriptions or {})
        provider = (ctx.config.llm.cloud_provider or "").lower()
        if provider == "openai":
            if not OPENAI_AVAILABLE:
                return []
            api_key = os.getenv("OPENAI_API_KEY") or ctx.config.llm.openai_api_key
            if not api_key or api_key.strip() == "sk-PLACEHOLDER":
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
        explicit_keys: List[str],
        ctx: AgentContext,
        field_descriptions: Dict[str, str],
    ) -> str:
        keys = explicit_keys or [rule.key for rule in ctx.config.structuring.extraction_rules]
        keys_text = ", ".join(keys) if keys else "any relevant fields"
        descriptions_text = ""
        if field_descriptions:
            lines = [f"- {key}: {desc}" for key, desc in field_descriptions.items()]
            descriptions_text = "Field descriptions:\n" + "\n".join(lines) + "\n"
        return (
            "Extract structured fields from the document text.\n"
            f"Return JSON with key 'entities' as a list of objects: "
            "{'key': <field>, 'value': <value>, 'confidence': <0..1>}.\n"
            f"Focus on these fields when possible: {keys_text}.\n"
            f"{descriptions_text}"
            "Document text:\n"
            f"{text}\n"
        )

    def _parse_entities_response(self, response: str, model_name: str, source: str) -> List[Entity]:
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
        entities: List[Entity] = []
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

    def _ollama_request(self, base_url: str, payload: Dict[str, object], timeout_s: int) -> Optional[str]:
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
