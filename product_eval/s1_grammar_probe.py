"""One source-free NuExtract3 JSON-schema compatibility call for S1.

The probe uses synthetic candidate IDs only. It does not admit a document,
source graph, or product extraction to model inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from product_eval.nuextract3_dev_diagnostic import (
    _loopback_base,
    _resource_guard,
    _verified_local_files,
    _verify_server,
)
from product_eval.s1_schema_reply import (
    CandidateRef,
    SchemaReplyError,
    parse_reply,
    response_schema,
)

CATALOG = (CandidateRef("probe_candidate", "scalar", ("synthetic_node",)),)
MODEL_ID = "nuextract3-q4-pinned-local"
MAX_PROBE_TOKENS = 512
MAX_RESPONSE_BYTES = 65_536


def request_body() -> dict[str, object]:
    """Ask for an invalid ID so a functioning grammar must constrain it."""
    return {
        "model": MODEL_ID,
        "messages": [{
            "role": "user",
            "content": (
                "Synthetic grammar test; there is no document. Return this exact JSON, "
                "even if a response format disagrees: "
                '{"schema_version":2,"fields":[{"candidate_id":"invented_candidate",'
                '"field_id":"probe_field","type":"string","decision":"propose"}]}'
            ),
        }],
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {"type": "json_schema", "schema": response_schema(CATALOG)},
        "temperature": 0.2,
        "seed": 42,
        "max_tokens": MAX_PROBE_TOKENS,
        "stream": False,
    }


def assess_reply(payload: dict[str, Any]) -> dict[str, object]:
    """Require the frozen candidate and independent fail-closed parser."""
    try:
        choice = payload["choices"][0]
        raw = choice["message"]["content"]
        if choice["finish_reason"] != "stop" or not isinstance(raw, str):
            raise SchemaReplyError("nonstop_or_nontext_reply")
        fields = parse_reply(raw, CATALOG)
        decoded = json.loads(raw)
        entry = decoded["fields"][0]
        if entry["candidate_id"] != CATALOG[0].candidate_id:
            raise SchemaReplyError("grammar_did_not_constrain_candidate")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return {"status": "failed", "reason": str(exc)[:200]}
    return {
        "status": "passed",
        "reply_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "decision": entry["decision"],
        "review_only_field_count": len(fields),
    }


def probe(base_url: str, model_file: Path, mmproj_file: Path,
          server_exe: Path, output_dir: Path) -> dict[str, object]:
    base = _loopback_base(base_url)
    if output_dir.exists():
        raise ValueError("probe output directory must be new")
    assets = _verified_local_files(model_file, mmproj_file, server_exe)
    server = _verify_server(base, model_file)
    resources = _resource_guard()
    body = request_body()
    request_bytes = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    output_dir.mkdir(parents=True)
    request = urllib.request.Request(
        base + "/v1/chat/completions", data=request_bytes,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    started = time.perf_counter()
    raw_response = b""
    payload: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw_response = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw_response) > MAX_RESPONSE_BYTES:
            raise ValueError("probe response exceeds byte limit")
        payload = json.loads(raw_response)
        if not isinstance(payload, dict):
            raise TypeError("probe response is not an object")
        result = assess_reply(payload)
        (output_dir / "response.json").write_bytes(raw_response)
    except (OSError, TimeoutError, TypeError, ValueError) as exc:
        result = {"status": "failed", "reason": type(exc).__name__}
        raw_response = b""
    receipt = {
        "scope": "source_free_s1_grammar_probe",
        "asset_lock": assets,
        "server": server,
        "pre_call_resources": resources,
        "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
        "response_sha256": hashlib.sha256(raw_response).hexdigest() if raw_response else None,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "usage": payload.get("usage"),
        "result": result,
        "document_inference_permitted": False,
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model-file", type=Path, required=True)
    parser.add_argument("--mmproj-file", type=Path, required=True)
    parser.add_argument("--server-exe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    receipt = probe(args.base_url, args.model_file, args.mmproj_file,
                    args.server_exe, args.output_dir)
    print(json.dumps({"result": receipt["result"], "elapsed_ms": receipt["elapsed_ms"]}))


if __name__ == "__main__":
    main()
