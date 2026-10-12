"""One synthetic ICORE transport call with a metadata-only receipt.

This research diagnostic is deliberately separate from the product route.
Pass a credential through non-interactive stdin; never pass it as an argument.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


BASE_URL = "https://icore.innobothealth.us/innobot-api/v1"
MODEL = "innobot-luna-6"
OPENAI_VERSION = "2.14.0"
HTTPX_VERSION = "0.28.1"
MAX_TOKENS = 32
TIMEOUT_SECONDS = 30.0
REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPT = "Reply with the single word pong."
_ERROR_CLASSES = frozenset({
    "APIConnectionError", "APITimeoutError", "APIStatusError", "BadRequestError",
    "AuthenticationError", "PermissionDeniedError", "RateLimitError",
    "InternalServerError", "ConnectError", "ConnectTimeout", "ReadTimeout",
    "WriteTimeout", "PoolTimeout", "RemoteProtocolError", "LocalProtocolError",
    "ProtocolError", "TimeoutError", "OSError", "ConnectionRefusedError",
    "gaierror", "SSLError", "JSONDecodeError", "ValidationError", "ValueError",
    "PackageNotFoundError", "ImportError", "FileExistsError", "PermissionError",
})
_FINISH_REASONS = frozenset({"stop", "length", "content_filter", "tool_calls", "function_call"})
_REQUEST_ID = re.compile(r"(?:req_[A-Za-z0-9_-]{6,64}|[a-fA-F0-9]{8}-[a-fA-F0-9-]{27,38})\Z")
_KEY_LIKE = re.compile(r"iba_[A-Za-z0-9_-]{8,}", re.IGNORECASE)


def _count(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 1_000_000 else None


def _status(value: Any) -> int | None:
    return value if type(value) is int and 100 <= value <= 599 else None


def _request_id(value: Any) -> str | None:
    if type(value) is not str or _KEY_LIKE.search(value):
        return None
    return value if _REQUEST_ID.fullmatch(value) else None


def _class_name(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if name in _ERROR_CLASSES else "OtherError"


def _cause_classes(exc: BaseException) -> list[str]:
    names: list[str] = []
    seen: set[int] = {id(exc)}
    current = exc.__cause__ or exc.__context__
    for _ in range(4):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        names.append(_class_name(current))
        current = current.__cause__ or current.__context__
    return names


def _receipt(*, elapsed_ms: int) -> dict[str, Any]:
    return {
        "exception_class": None,
        "cause_classes": [],
        "http_status": None,
        "finish_reason": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "elapsed_ms": elapsed_ms,
        "request_id": None,
    }


def sanitized_exception(exc: BaseException, *, elapsed_ms: int, raw: Any = None) -> dict[str, Any]:
    """Never format an exception, response body, header collection, or credential."""
    receipt = _receipt(elapsed_ms=elapsed_ms)
    receipt["exception_class"] = _class_name(exc)
    receipt["cause_classes"] = _cause_classes(exc)
    receipt["http_status"] = _status(getattr(exc, "status_code", None))
    receipt["request_id"] = _request_id(getattr(exc, "request_id", None))
    if raw is not None:
        receipt["http_status"] = receipt["http_status"] or _status(getattr(raw, "status_code", None))
        receipt["request_id"] = receipt["request_id"] or _request_id(raw.headers.get("x-request-id"))
    return receipt


def probe(client: Any) -> tuple[dict[str, Any], int]:
    """Perform exactly one SDK create call; return sanitized metadata and exit code."""
    started = time.perf_counter()
    raw = None
    try:
        raw = client.chat.completions.with_raw_response.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=MAX_TOKENS,
            timeout=TIMEOUT_SECONDS,
        )
        reply = raw.parse()
        receipt = _receipt(elapsed_ms=round((time.perf_counter() - started) * 1000))
        receipt["http_status"] = _status(getattr(raw, "status_code", None))
        receipt["request_id"] = _request_id(raw.headers.get("x-request-id"))
        choices = getattr(reply, "choices", None)
        reason = getattr(choices[0], "finish_reason", None) if choices else None
        receipt["finish_reason"] = reason if reason in _FINISH_REASONS else None
        usage = getattr(reply, "usage", None)
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            receipt[name] = _count(getattr(usage, name, None))
        # Missing usage makes the one-call observation incomplete. Never retry.
        return receipt, 0 if all(receipt[name] is not None for name in (
            "prompt_tokens", "completion_tokens", "total_tokens")) else 2
    except Exception as exc:  # noqa: BLE001 - exception messages may contain credential or prompt
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        return sanitized_exception(exc, elapsed_ms=elapsed_ms, raw=raw), 1


def _read_key() -> str:
    if sys.stdin.isatty():
        raise ValueError("credential input requires non-interactive stdin")
    raw = sys.stdin.buffer.read(4097)
    if not raw or len(raw) > 4096:
        raise ValueError("credential input is empty or oversized")
    key = raw.rstrip(b"\r\n").decode("ascii")
    if not key or len(key) > 512 or any(not 33 <= ord(char) <= 126 for char in key):
        raise ValueError("credential input is malformed")
    return key


def _receipt_path(path: Path) -> Path:
    if not path.is_absolute() or path.resolve().is_relative_to(REPO_ROOT):
        raise ValueError("receipt must be an absolute path outside Git")
    if not path.parent.is_dir() or path.exists():
        raise ValueError("receipt parent must exist and receipt must be new")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = _receipt_path(args.receipt)
        if (importlib.metadata.version("openai") != OPENAI_VERSION
                or importlib.metadata.version("httpx") != HTTPX_VERSION):
            raise ValueError("transport version differs from frozen protocol")
        key = _read_key()
    except Exception as exc:  # noqa: BLE001 - preflight messages may mention credential input
        print(json.dumps(sanitized_exception(exc, elapsed_ms=0), separators=(",", ":")))
        return 3

    # Prevent SDK/httpx debug logs, which may contain request headers or bodies.
    os.environ.pop("OPENAI_LOG", None)
    for logger_name in ("openai", "httpx", "httpcore"):
        logging.getLogger(logger_name).disabled = True
    try:
        from httpx import Client
        from openai import OpenAI
        with output.open("x", encoding="utf-8") as handle:
            with Client(follow_redirects=False, timeout=TIMEOUT_SECONDS) as transport:
                with OpenAI(api_key=key, base_url=BASE_URL, max_retries=0,
                            timeout=TIMEOUT_SECONDS, http_client=transport) as client:
                    receipt, exit_code = probe(client)
            serialized = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
            handle.write(serialized + "\n")
        print(serialized)
        return exit_code
    except Exception as exc:  # noqa: BLE001 - preserve only sanitized exception types
        print(json.dumps(sanitized_exception(exc, elapsed_ms=0), separators=(",", ":")))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
