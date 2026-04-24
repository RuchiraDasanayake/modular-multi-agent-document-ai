from __future__ import annotations

import json
import os
import re
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

_API_KEY_RE = re.compile(r"\b(?:sk|rk|api[_-]?key)[-_a-zA-Z0-9]{8,}\b", re.IGNORECASE)
_BEARER_RE = re.compile(r"(bearer\s+)[^\s'\"}]+", re.IGNORECASE)


def sanitize_provider_error(error: object) -> str:
    text = str(error or "").strip()
    if not text:
        return "provider_error"
    lowered = text.lower()
    if "incorrect api key" in lowered or "invalid api key" in lowered or "authentication" in lowered or "401" in lowered:
        return "authentication_failed"
    redacted = _API_KEY_RE.sub("[redacted]", text)
    redacted = _BEARER_RE.sub(r"\1[redacted]", redacted)
    return redacted[:220]


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
    """Thin Ollama /api/generate wrapper. Returns raw response string or None."""
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


def ollama_generate_detailed(
    base_url: str,
    payload: dict[str, object],
    timeout_s: int,
) -> tuple[str | None, dict[str, object]]:
    """Ollama wrapper that also returns timing, token counts, and error info.

    Ollama returns a JSON body with fields like:
      response, eval_count, prompt_eval_count, eval_duration, total_duration,
      load_duration, done_reason. We surface these as meta for monitoring.
    """
    meta: dict[str, object] = {"endpoint": "ollama.generate"}
    url = base_url.rstrip("/") + "/api/generate"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        meta["error"] = f"http_{exc.code}"
        return None, meta
    except urllib.error.URLError as exc:
        meta["error"] = f"unreachable:{str(exc.reason)[:120]}"
        return None, meta
    except TimeoutError:
        meta["error"] = "timeout"
        return None, meta
    except Exception as exc:
        meta["error"] = f"unknown:{str(exc)[:120]}"
        return None, meta

    try:
        parsed = json.loads(body)
    except Exception:
        meta["error"] = "bad_json_body"
        return None, meta

    response = parsed.get("response")
    # Ollama token counts are measured in tokens, not chars.
    meta.update({
        "prompt_tokens": int(parsed.get("prompt_eval_count", 0) or 0),
        "completion_tokens": int(parsed.get("eval_count", 0) or 0),
        "total_tokens": int(parsed.get("prompt_eval_count", 0) or 0)
        + int(parsed.get("eval_count", 0) or 0),
        # Ollama durations are nanoseconds; convert to ms for UI.
        "load_duration_ms": round(int(parsed.get("load_duration", 0) or 0) / 1e6, 2),
        "prompt_eval_duration_ms": round(int(parsed.get("prompt_eval_duration", 0) or 0) / 1e6, 2),
        "eval_duration_ms": round(int(parsed.get("eval_duration", 0) or 0) / 1e6, 2),
        "total_duration_ms": round(int(parsed.get("total_duration", 0) or 0) / 1e6, 2),
        "done_reason": str(parsed.get("done_reason") or ""),
    })
    return response, meta


def ollama_chat_detailed(
    base_url: str,
    messages: list[dict[str, str]],
    model: str,
    *,
    timeout_s: int,
    options: dict[str, object] | None = None,
    format_json: bool = True,
) -> tuple[str | None, dict[str, object]]:
    """Ollama /api/chat wrapper — better for instruction-tuned models (Qwen3, Llama3).

    The chat endpoint honours the model's instruction template, which gives
    significantly better structured-output adherence than /api/generate for
    models with a built-in chat format.
    """
    meta: dict[str, object] = {"endpoint": "ollama.chat"}
    payload: dict[str, object] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if options:
        payload["options"] = options
    if format_json:
        payload["format"] = "json"

    url = base_url.rstrip("/") + "/api/chat"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        meta["error"] = f"http_{exc.code}"
        return None, meta
    except urllib.error.URLError as exc:
        meta["error"] = f"unreachable:{str(exc.reason)[:120]}"
        return None, meta
    except TimeoutError:
        meta["error"] = "timeout"
        return None, meta
    except Exception as exc:
        meta["error"] = f"unknown:{str(exc)[:120]}"
        return None, meta

    try:
        parsed = json.loads(body)
    except Exception:
        meta["error"] = "bad_json_body"
        return None, meta

    message = parsed.get("message", {})
    response = message.get("content") if isinstance(message, dict) else None
    meta.update({
        "prompt_tokens": int(parsed.get("prompt_eval_count", 0) or 0),
        "completion_tokens": int(parsed.get("eval_count", 0) or 0),
        "total_tokens": int(parsed.get("prompt_eval_count", 0) or 0)
        + int(parsed.get("eval_count", 0) or 0),
        "load_duration_ms": round(int(parsed.get("load_duration", 0) or 0) / 1e6, 2),
        "prompt_eval_duration_ms": round(int(parsed.get("prompt_eval_duration", 0) or 0) / 1e6, 2),
        "eval_duration_ms": round(int(parsed.get("eval_duration", 0) or 0) / 1e6, 2),
        "total_duration_ms": round(int(parsed.get("total_duration", 0) or 0) / 1e6, 2),
        "done_reason": str(parsed.get("done_reason") or ""),
    })
    return response, meta


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
                meta["error"] = sanitize_provider_error(retry_exc)
                return "", meta
        else:
            meta["error"] = sanitize_provider_error(exc)
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
        meta["error"] = sanitize_provider_error(exc)
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
