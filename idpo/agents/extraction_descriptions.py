from __future__ import annotations

import json
from typing import Callable

from idpo.agents.base import AgentContext
from idpo.agents.extraction_providers import ollama_generate, openai_chat_completion


def normalize_field_descriptions(
    field_descriptions: object,
    *,
    normalize_key: Callable[[str], str],
) -> dict[str, str]:
    if not isinstance(field_descriptions, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_key, raw_value in field_descriptions.items():
        key = normalize_key(str(raw_key))
        if not key:
            continue
        normalized[key] = str(raw_value or "").strip()
    return normalized


def refine_field_descriptions(
    explicit_keys: list[str],
    field_descriptions: dict[str, str],
    ctx: AgentContext,
    *,
    normalize_key: Callable[[str], str],
    parse_json_payload: Callable[[str], object | None],
    cache: dict[str, dict[str, str]],
    generate: Callable[..., str | None] = ollama_generate,
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
    selected_keys = [normalize_key(key) for key in explicit_keys if normalize_key(key)][:max_fields]
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

    use_cloud = bool(ctx.config.llm.description_refinement_use_cloud)
    if use_cloud:
        refinement_model = str(
            ctx.config.llm.description_refinement_model or ctx.config.llm.cloud_model or ""
        ).strip()
    else:
        if str(ctx.config.llm.provider or "").strip().lower() != "ollama":
            meta["error"] = "refinement_requires_local_ollama"
            merged = dict(field_descriptions)
            merged.update(base_map)
            return merged, meta
        refinement_model = str(
            ctx.config.llm.description_refinement_model or ctx.config.llm.local_model or ""
        ).strip()
    if not refinement_model:
        meta["error"] = "missing_refinement_model"
        merged = dict(field_descriptions)
        merged.update(base_map)
        return merged, meta

    model_name = refinement_model
    meta["model"] = model_name
    cache_key = f"{model_name}|{json.dumps(base_map, sort_keys=True)}"
    cached = cache.get(cache_key)
    if cached:
        merged = dict(field_descriptions)
        merged.update(cached)
        meta["cache_hit"] = True
        meta["succeeded"] = True
        return merged, meta

    meta["attempted"] = True
    prompt = (
        "Refine field descriptions for document extraction.\n"
        "Return a JSON object mapping each key to one concise extraction description.\n"
        "Each description should be 8-20 words and include synonyms/format hints.\n"
        "Do not add new keys.\n\n"
        f"Input map:\n{json.dumps(base_map, ensure_ascii=False)}"
    )
    try:
        if use_cloud:
            content, _cloud_meta = openai_chat_completion(
                model_name=model_name,
                prompt=prompt,
                api_key=ctx.config.llm.openai_api_key,
                base_url=ctx.config.llm.openai_api_url,
                timeout_s=int(ctx.config.llm.cloud_timeout_s),
                temperature=ctx.config.llm.description_refinement_temperature,
                max_tokens=ctx.config.llm.description_refinement_max_tokens,
                response_format={"type": "json_object"},
                retry_without_json_mode=bool(ctx.config.llm.cloud_retry_without_json_mode),
            )
        else:
            content = generate(
                ctx.config.llm.base_url,
                {
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": ctx.config.llm.description_refinement_temperature,
                    },
                },
                ctx.config.llm.timeout_s,
            )
        if not content:
            meta["error"] = "empty_or_unavailable"
            merged = dict(field_descriptions)
            merged.update(base_map)
            return merged, meta
        parsed = parse_json_payload(content or "")
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
            cache[cache_key] = dict(refined)
            meta["succeeded"] = True
        else:
            meta["error"] = "empty_refinement_output"
        return merged, meta
    except Exception as exc:
        meta["error"] = str(exc)[:220]
        merged = dict(field_descriptions)
        merged.update(base_map)
        return merged, meta
