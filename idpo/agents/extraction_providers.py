from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

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


def normalize_openai_base_url(base_url: str) -> str:
    if not base_url:
        return "https://api.openai.com/v1"
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/chat/completions"):
        cleaned = cleaned[: -len("/chat/completions")]
    if cleaned.endswith("/v1"):
        return cleaned
    return cleaned


def ollama_generate(base_url: str, payload: dict[str, object], timeout_s: int) -> str | None:
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


def openai_chat_completion(
    *,
    model_name: str,
    prompt: str,
    api_key: str,
    base_url: str,
    timeout_s: int,
    temperature: float,
    max_tokens: int,
    response_format: dict[str, object] | None,
    retry_without_json_mode: bool,
) -> tuple[str, dict[str, object]]:
    meta: dict[str, object] = {"endpoint": "chat.completions"}
    if not OPENAI_AVAILABLE:
        meta["error"] = "openai_sdk_unavailable"
        return "", meta
    key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
    normalized_key = key.lower()
    if (
        not normalized_key
        or normalized_key == "sk-placeholder"
        or normalized_key.startswith("${")
        or "your" in normalized_key and "key" in normalized_key
        or normalized_key in ("sk-", "sk-xxx", "sk-test", "changeme", "replace-me")
    ):
        meta["error"] = "missing_or_placeholder_key"
        return "", meta

    client = OpenAI(
        api_key=key,
        base_url=normalize_openai_base_url(base_url or os.getenv("OPENAI_API_URL") or ""),
        timeout=timeout_s,
    )
    kwargs: dict[str, object] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Return only valid JSON with extracted entities."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        if response_format and retry_without_json_mode:
            kwargs.pop("response_format", None)
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as retry_exc:
                meta["error"] = str(retry_exc)[:220]
                return "", meta
        else:
            meta["error"] = str(exc)[:220]
            return "", meta

    content = response.choices[0].message.content if response.choices else ""
    usage = getattr(response, "usage", None)
    meta.update(
        {
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "total_tokens": int(
                getattr(
                    usage,
                    "total_tokens",
                    int(getattr(usage, "prompt_tokens", 0) or 0) + int(getattr(usage, "completion_tokens", 0) or 0),
                )
                or 0
            ),
        }
    )
    return content or "", meta


def anthropic_messages_completion(
    *,
    model_name: str,
    prompt: str,
    api_key: str,
    max_tokens: int,
) -> tuple[str, dict[str, object]]:
    meta: dict[str, object] = {"endpoint": "messages.create"}
    if not ANTHROPIC_AVAILABLE:
        meta["error"] = "anthropic_sdk_unavailable"
        return "", meta
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or ""
    if not api_key:
        meta["error"] = "missing_anthropic_key"
        return "", meta
    client = Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        meta["error"] = str(exc)[:220]
        return "", meta

    content = response.content[0].text if response.content else ""
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    meta.update(
        {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    )
    return content or "", meta
