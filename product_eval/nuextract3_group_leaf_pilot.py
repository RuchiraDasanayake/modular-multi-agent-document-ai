"""Source-disjoint NuExtract3 grouped-leaf follow-on, outside the product path.

The --check mode performs no inference and never parses gold. --run requires
the later code-lock receipt and a separately started pinned loopback server.
Raw prompts, images, replies and scores remain outside Git.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError
from product_eval.graph_schema_diagnostic import ALIAS_PATH, LOCK_PATH, load_aliases, load_jsonl, score_schema, sha256_file
from product_eval.nuextract3_dev_diagnostic import (
    ALIAS_SHA256,
    CONTEXT_TOKENS,
    JPEG_QUALITY,
    MAX_IMAGE_DIMENSION,
    MAX_SOURCE_CHARS,
    MODEL_SHA256,
    MODEL_REVISION,
    MMPROJ_SHA256,
    OUTPUT_TOKENS,
    SERVER_SHA256,
    ResourceSampler,
    _loopback_base,
    _render_images,
    _resource_guard,
    _source_content,
    _verify_server,
    _verify_template_modes,
    _verified_local_files,
    template_to_graph_spec,
)
from product_eval.nuextract3_group_leaf_scorer import (
    _no_duplicate_keys,
    canonical_sha256,
    load_rule,
    score_grouped_leaf,
    score_self_template_values,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs" / "evaluations"
SOURCES_PATH = DOCS / "nuextract3_group_leaf_dev12_sources.json"
RULE_PATH = DOCS / "nuextract3_group_leaf_alias_v1.json"
PROFILE_PATH = DOCS / "nuextract3_group_leaf_run_profile_v1.json"
CODE_LOCK_PATH = DOCS / "nuextract3_group_leaf_code_lock_v1.json"
SOURCE_SHA256 = "846d3bcc4cf1d02a2dcb10d1e5233b6881c2ec23d57d0a100936430972748a80"
RULE_SHA256 = "343e6c2403d97c27d4cdf4207e005eb6d800397ff19d426474d6970d3b51d95b"
PROFILE_SHA256 = "c72c0c4e86499796a188c660ce0de03d04be25abe90d0ca3e469812c2eddcd62"
GRAPH_LOCK_SHA256 = "61bef64cafb35739eba3a087fe5a742c57e68c340834325a8f77e49f63c5b047"
MAX_CALLS = 24
MAX_TOTAL_TOKENS = 240000
CALL_TIMEOUT_SECONDS = 300


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ContractError(f"invalid lock JSON {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"lock JSON is not an object: {path.name}")
    return value


def load_frozen_assets() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = _load_json(SOURCES_PATH)
    profile = _load_json(PROFILE_PATH)
    rule = load_rule(RULE_PATH, RULE_SHA256)
    if canonical_sha256(manifest) != SOURCE_SHA256 or canonical_sha256(profile) != PROFILE_SHA256:
        raise ContractError("grouped-leaf source or run profile canonical SHA256 differs")
    if manifest.get("rule_commit") != "819d62e" or manifest.get("rule_canonical_sha256") != RULE_SHA256:
        raise ContractError("grouped-leaf rule precommit differs")
    if manifest.get("run_profile_canonical_sha256") != PROFILE_SHA256:
        raise ContractError("grouped-leaf run profile in source lock differs")
    if profile["model"]["q4_weights_sha256"] != MODEL_SHA256 or profile["model"]["vision_projector_sha256"] != MMPROJ_SHA256:
        raise ContractError("pinned model or projector differs from tested loader")
    if profile["model"]["llama_server_sha256"] != SERVER_SHA256 or profile["model"]["llama_server_build"] != 11425:
        raise ContractError("pinned server differs from tested loader")
    if profile["model"]["repo_revision"] != MODEL_REVISION:
        raise ContractError("pinned model revision differs from tested loader")
    if profile["chat"]["context_tokens"] != CONTEXT_TOKENS or profile["chat"]["max_output_tokens_per_call"] != OUTPUT_TOKENS:
        raise ContractError("context/output token settings differ from tested loader")
    if profile["input"]["ocr_prompt_character_cap"] != MAX_SOURCE_CHARS or profile["input"]["longest_dimension_cap_px"] != MAX_IMAGE_DIMENSION:
        raise ContractError("render/OCR settings differ from tested loader")
    if {key: profile["input"][key] for key in ("all_pages", "render_dpi", "image_format", "jpeg_quality")} != {
            "all_pages": True, "render_dpi": 120, "image_format": "RGB JPEG", "jpeg_quality": JPEG_QUALITY}:
        raise ContractError("rendering profile differs from tested loader")
    if (profile["chat"]["temperature"], profile["chat"]["seed"], profile["chat"]["slots"],
            profile["chat"]["schema_kwargs"], profile["chat"]["value_kwargs"]) != (
            0.2, 42, 1, {"mode": "template-generation", "enable_thinking": False},
            {"template": "the same source's valid model-generated schema JSON only", "enable_thinking": False}):
        raise ContractError("chat profile differs from tested loader")
    if (profile["limits"]["max_schema_calls"], profile["limits"]["max_conditional_value_calls"],
            profile["limits"]["max_total_accounted_tokens"], profile["limits"]["max_seconds_per_call"],
            profile["limits"]["retries"]) != (12, 12, MAX_TOTAL_TOKENS, CALL_TIMEOUT_SECONDS, 0):
        raise ContractError("frozen request limits differ")
    if sha256_file(ALIAS_PATH) != ALIAS_SHA256:
        raise ContractError("original alias ontology changed")
    return manifest, profile, rule


def verify_inventory(paths: dict[str, Path], runs_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Verify bytes and source-only selection. Gold files are hashed, not parsed."""
    expected = manifest["corpus_sha256"]
    for key in ("vrdu_cohort", "vrdu_gold", "cord_development_cohort", "cord_development_gold", "cord_reserved_cohort"):
        if not paths[key].is_file() or sha256_file(paths[key]) != expected[key]:
            raise ContractError(f"frozen corpus SHA256 differs: {key}")
    if sha256_file(LOCK_PATH) != manifest["prior_graph_source_lock_sha256"] or sha256_file(LOCK_PATH) != GRAPH_LOCK_SHA256:
        raise ContractError("prior Graph source lock changed")
    vrdu = load_jsonl(paths["vrdu_cohort"])
    cord = load_jsonl(paths["cord_development_cohort"])
    reserved = load_jsonl(paths["cord_reserved_cohort"])
    if len(vrdu) != 2000 or len(cord) != 60 or len(reserved) != 40:
        raise ContractError("source cohort counts changed")
    if any(row.get("evaluation_split") != "development" for row in cord):
        raise ContractError("CORD selection contains a non-development source")
    graph = _load_json(LOCK_PATH)["sources"]
    excluded_ids = {row["doc_id"] for row in graph + reserved}
    excluded_hashes = {row["source_sha256"] for row in graph + reserved}
    selected: list[dict[str, Any]] = []
    for family in ("registration-form", "ad-buy-form"):
        pool = sorted((row for row in vrdu if row["family"] == family),
                      key=lambda row: (row["source_sha256"], row["doc_id"]))
        if len(pool) < 16:
            raise ContractError(f"VRDU {family} lacks rank 16")
        selected.extend(pool[12:16])
    cord_run = runs_root / "cord_v2_development_v1"
    eligible_cord = []
    for row in sorted(cord, key=lambda item: (item["source_sha256"], item["doc_id"])):
        if row["doc_id"] in excluded_ids or row["source_sha256"] in excluded_hashes:
            continue
        sidecar = cord_run / "docs" / row["doc_id"] / "result.json"
        if not sidecar.is_file():
            raise ContractError(f"missing completed CORD sidecar: {row['doc_id']}")
        pages = _load_json(sidecar).get("pages", [])
        if sum(len(page.get("text", "")) for page in pages) >= 200:
            eligible_cord.append(row)
    if len(eligible_cord) < 4:
        raise ContractError("fewer than four OCR-eligible CORD development sources")
    selected.extend(eligible_cord[:4])
    pinned = manifest.get("sources")
    if not isinstance(pinned, list) or len(pinned) != 12 or len(selected) != 12:
        raise ContractError("source lock must contain twelve entries")
    if len({row["source_sha256"] for row in pinned}) != 12:
        raise ContractError("source lock contains duplicate raw hashes")
    v8_runs = sorted(runs_root.glob("vrdu_v8_provenance_*"))
    if len(v8_runs) != 8:
        raise ContractError("expected eight completed v8 OCR run shards")
    inventory = []
    for row, lock in zip(selected, pinned, strict=True):
        for key in ("family", "doc_id", "source_sha256"):
            if row[key] != lock.get(key):
                raise ContractError(f"deterministic selection differs: {key}")
        if row["doc_id"] in excluded_ids or row["source_sha256"] in excluded_hashes:
            raise ContractError("source overlaps prior model development or reserved CORD")
        source = Path(row["source_path"])
        if not source.is_file() or sha256_file(source) != lock["source_sha256"]:
            raise ContractError(f"raw source SHA256 changed: {row['doc_id']}")
        candidate_runs = [run for run in (v8_runs if row["family"] != "receipt" else [cord_run])
                          if (run / "docs" / row["doc_id"] / "result.json").is_file()]
        if len(candidate_runs) != 1 or candidate_runs[0].name != lock["run_id"]:
            raise ContractError(f"completed OCR run changed: {row['doc_id']}")
        run = candidate_runs[0]
        if not (run / "run.json").is_file():
            raise ContractError(f"incomplete OCR run: {run.name}")
        sidecar_path = run / "docs" / row["doc_id"] / "result.json"
        if sha256_file(sidecar_path) != lock["sidecar_sha256"]:
            raise ContractError(f"OCR sidecar SHA256 changed: {row['doc_id']}")
        sidecar = _load_json(sidecar_path)
        pages = sidecar.get("pages", [])
        if sidecar.get("source_sha256") != row["source_sha256"] or not pages or any(
                not isinstance(page.get("text"), str) for page in pages):
            raise ContractError(f"OCR sidecar source/pages invalid: {row['doc_id']}")
        ocr_text = "\n\n".join(f"[page {page['page']}]\n{page['text']}" for page in pages)
        if (len(ocr_text) != lock["ocr_chars"] or len(ocr_text[:MAX_SOURCE_CHARS]) != lock["ocr_prompt_chars"]
                or _sha_bytes(ocr_text.encode("utf-8")) != lock["ocr_text_sha256"]
                or _sha_bytes(ocr_text[:MAX_SOURCE_CHARS].encode("utf-8")) != lock["ocr_prompt_text_sha256"]):
            raise ContractError(f"OCR text/prompt prefix changed: {row['doc_id']}")
        inventory.append({"family": row["family"], "doc_id": row["doc_id"],
                          "source_sha256": row["source_sha256"], "source_path": source,
                          "ocr_text": ocr_text})
    return inventory


def verify_code_lock(path: Path = CODE_LOCK_PATH) -> dict[str, Any]:
    lock = _load_json(path)
    if (lock.get("version") != 1 or lock.get("source_lock_canonical_sha256") != SOURCE_SHA256
            or lock.get("rule_canonical_sha256") != RULE_SHA256
            or lock.get("run_profile_canonical_sha256") != PROFILE_SHA256):
        raise ContractError("grouped-leaf code lock version/assets differ")
    commit = lock.get("code_commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ContractError("grouped-leaf code commit is not a full Git SHA")
    files = lock.get("files")
    required = {"product_eval/nuextract3_group_leaf_pilot.py", "product_eval/nuextract3_group_leaf_scorer.py",
                "product_eval/nuextract3_dev_diagnostic.py", "product_eval/graph_schema_diagnostic.py",
                "product_eval/contracts.py", "product_eval/oracle_schema_diagnostic.py"}
    if not isinstance(files, dict) or set(files) != required:
        raise ContractError("grouped-leaf code lock file set differs")
    try:
        lock_relative = path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ContractError("grouped-leaf code lock must be inside Git") from exc
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", lock_relative],
                             cwd=REPO_ROOT, capture_output=True, check=False)
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                              cwd=REPO_ROOT, capture_output=True, check=False)
    if tracked.returncode != 0 or ancestor.returncode != 0:
        raise ContractError("grouped-leaf code lock is untracked or code commit is not an ancestor")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", lock_relative, *sorted(required)],
                           cwd=REPO_ROOT, capture_output=True, check=False)
    if dirty.returncode != 0 or dirty.stdout:
        raise ContractError("grouped-leaf sealed files have uncommitted changes")
    for relative, expected in files.items():
        file = REPO_ROOT / relative
        if not file.is_file() or sha256_file(file) != expected:
            raise ContractError(f"grouped-leaf code changed after seal: {relative}")
        committed = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=REPO_ROOT,
                                   capture_output=True, check=False)
        if committed.returncode != 0 or _sha_bytes(committed.stdout) != expected:
            raise ContractError(f"grouped-leaf code lock is not attested by Git: {relative}")
    return {"code_commit": commit, "code_lock_sha256": sha256_file(path)}


def _flag_value(arguments: list[str], flag: str) -> str | None:
    values: list[str] = []
    for position, item in enumerate(arguments):
        if item == flag and position + 1 < len(arguments):
            values.append(arguments[position + 1])
        elif item.startswith(flag + "="):
            values.append(item[len(flag) + 1:])
    return values[0] if len(values) == 1 else None


def verify_server_command(base: str, server_exe: Path, mmproj_file: Path,
                          profile: dict[str, Any]) -> dict[str, Any]:
    """Bind the HTTP preflight to a local process with the required vision flags."""
    import psutil

    port = urllib.parse.urlsplit(base).port
    required = profile["model"]["server_flags"]
    try:
        listener_pids = {connection.pid for connection in psutil.net_connections(kind="tcp")
                         if connection.status == psutil.CONN_LISTEN and connection.laddr
                         and connection.laddr.port == port
                         and connection.laddr.ip in {"127.0.0.1", "::1"}}
    except (psutil.AccessDenied, OSError) as exc:
        raise ContractError("cannot verify local server listener ownership") from exc
    for process in psutil.process_iter(["exe", "cmdline"]):
        try:
            executable = process.info["exe"]
            arguments = process.info["cmdline"] or []
            if not executable or Path(executable).resolve() != server_exe.resolve():
                continue
            if process.pid not in listener_pids:
                continue
            if _flag_value(arguments, "--port") != str(port):
                continue
            if _flag_value(arguments, "--host") not in {"127.0.0.1", "localhost"}:
                continue
            if _flag_value(arguments, "--mmproj") is None or Path(_flag_value(arguments, "--mmproj") or "").resolve() != mmproj_file.resolve():
                continue
            if arguments.count("--jinja") != 1:
                continue
            for flag in ("--reasoning", "--image-min-tokens", "--image-max-tokens"):
                index = required.index(flag)
                if _flag_value(arguments, flag) != required[index + 1]:
                    break
            else:
                return {"pid": process.pid, "command_sha256": _sha_bytes("\0".join(arguments).encode("utf-8"))}
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError, ValueError):
            continue
    raise ContractError("no pinned local server owns the loopback listener with required vision flags")


def _valid_template(value: Any, *, depth: int = 0) -> bool:
    if depth > 8:
        return False
    if isinstance(value, dict):
        # Projection uses dot-separated paths; a literal dot in a key would
        # make a self-template value path ambiguous.
        return bool(value) and all(isinstance(key, str) and 0 < len(key) <= 128 and "." not in key
                                   and _valid_template(item, depth=depth + 1) for key, item in value.items())
    if isinstance(value, list):
        return len(value) == 1 and isinstance(value[0], (dict, str)) and _valid_template(value[0], depth=depth + 1)
    return isinstance(value, str) and bool(value) and len(value) <= 128


def _chat_body(content: list[dict[str, Any]], kwargs: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    return {"model": "nuextract3-q4-pinned-local", "messages": [{"role": "user", "content": content}],
            "chat_template_kwargs": kwargs, "temperature": profile["chat"]["temperature"],
            "seed": profile["chat"]["seed"], "max_tokens": profile["chat"]["max_output_tokens_per_call"],
            "stream": False}


def _parse_reply_object(raw: str) -> dict[str, Any]:
    stripped = raw.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        stripped = stripped[7:-3].strip()
    value = json.loads(stripped, object_pairs_hook=_no_duplicate_keys)
    if not isinstance(value, dict):
        raise TypeError("response root is not an object")
    return value


def _post_json_with_deadline(base: str, raw: bytes, *, timeout_seconds: float = CALL_TIMEOUT_SECONDS) -> bytes:
    """Enforce one wall-clock deadline for connection, headers, and body."""
    parts = urllib.parse.urlsplit(base)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout_seconds)
    result: dict[str, Any] = {}
    finished = threading.Event()

    def work() -> None:
        try:
            connection.request("POST", "/v1/chat/completions", body=raw,
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            result["status"] = response.status
            result["body"] = response.read()
        except Exception as exc:
            result["error"] = exc
        finally:
            connection.close()
            finished.set()

    worker = threading.Thread(target=work, daemon=True, name="nuextract3-bounded-http")
    worker.start()
    if not finished.wait(timeout_seconds):
        connection.close()
        raise TimeoutError(f"model call exceeded {timeout_seconds:g}s wall-clock deadline")
    if "error" in result:
        raise result["error"]
    if result["status"] >= 400:
        detail = result["body"][:2000].decode("utf-8", errors="replace")
        raise ContractError(f"HTTP {result['status']}: {detail}")
    return result["body"]


class GuardedCalls:
    def __init__(self, base: str, output: Path):
        self.base = base
        self.output = output
        self.calls = 0
        self.accounted_tokens = 0

    def complete(self, label: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.calls >= MAX_CALLS or self.accounted_tokens + CONTEXT_TOKENS > MAX_TOTAL_TOKENS:
            raise ContractError("local model call/token cap reached before request")
        _resource_guard()
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.calls += 1
        # Reserve a full context for every attempted call. Failed transport or
        # malformed replies have no trustworthy usage record to refund it.
        self.accounted_tokens += CONTEXT_TOKENS
        request_path = self.output / f"request-{self.calls:02d}-{label}.json"
        request_path.write_bytes(raw)
        outcome: dict[str, Any] = {"label": label, "request_sha256": _sha_bytes(raw),
                                   "status": "failed", "accounted_tokens": CONTEXT_TOKENS}
        started = time.perf_counter()
        try:
            reply_bytes = _post_json_with_deadline(self.base, raw)
            reply_path = self.output / f"reply-{self.calls:02d}-{label}.json"
            reply_path.write_bytes(reply_bytes)
            payload = json.loads(reply_bytes, object_pairs_hook=_no_duplicate_keys)
            usage = payload.get("usage") or {}
            counted = usage.get("total_tokens")
            if type(counted) is not int or counted < 0:
                counted = CONTEXT_TOKENS
            self.accounted_tokens += counted - CONTEXT_TOKENS
            if self.accounted_tokens > MAX_TOTAL_TOKENS:
                raise ContractError("model reported token usage above the total cap")
            choice = payload["choices"][0]
            finish = choice.get("finish_reason")
            outcome.update({"reply_sha256": _sha_bytes(reply_bytes), "usage": usage,
                            "accounted_tokens": counted, "finish_reason": finish,
                            "status": "complete" if finish == "stop" else "truncated"})
            if finish == "stop":
                outcome["value"] = _parse_reply_object(choice["message"]["content"])
            else:
                outcome["error"] = "non-stop finish reason"
        except (http.client.HTTPException, urllib.error.URLError, TimeoutError, OSError) as exc:
            outcome["status"] = "failed"
            outcome["infrastructure_failure"] = True
            outcome["error"] = f"{type(exc).__name__}: {str(exc)[:1000]}"
        except (ValueError, KeyError, IndexError, TypeError, ContractError) as exc:
            outcome["status"] = "failed"
            outcome["infrastructure_failure"] = isinstance(exc, ContractError) and (
                str(exc).startswith("HTTP ") or "token" in str(exc).lower())
            outcome["error"] = f"{type(exc).__name__}: {str(exc)[:1000]}"
        outcome["elapsed_seconds"] = time.perf_counter() - started
        with (self.output / "calls.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({k: v for k, v in outcome.items() if k != "value"}, ensure_ascii=False) + "\n")
        return outcome


def _infrastructure_failure(outcome: dict[str, Any]) -> bool:
    if outcome.get("status") != "failed":
        return False
    if outcome.get("infrastructure_failure") is True:
        return True
    error = outcome.get("error", "").lower()
    return any(marker in error for marker in ("http ", "urlerror", "timeout", "context", "token cap"))


def _image_input_guard(source: Path) -> None:
    """Bound the old renderer, which holds all source pages before thumbnailing."""
    if source.suffix.lower() == ".pdf":
        import pypdfium2

        document = pypdfium2.PdfDocument(source)
        try:
            if not 1 <= len(document) <= 8:
                raise ContractError("PDF page count exceeds eight-page rendering guard")
            for index in range(len(document)):
                page = document[index]
                try:
                    width, height = page.get_size()
                    if width * height * (120 / 72) ** 2 > 12_000_000:
                        raise ContractError("PDF page exceeds twelve-megapixel rendering guard")
                finally:
                    page.close()
        finally:
            document.close()
    else:
        from PIL import Image

        with Image.open(source) as image:
            if image.width * image.height > 12_000_000:
                raise ContractError("image exceeds twelve-megapixel rendering guard")


def _prepare_schema_requests(inventory: list[dict[str, Any]], profile: dict[str, Any],
                             output: Path) -> dict[str, dict[str, Any]]:
    """Seal deterministic rendered inputs and schema request bytes before inference."""
    prepared: dict[str, dict[str, Any]] = {}
    receipt = []
    for row in inventory:
        _resource_guard()
        _image_input_guard(row["source_path"])
        images = _render_images(row["source_path"], output / "images" / row["doc_id"])
        content = _source_content(row, images, profile["instructions"]["schema"])
        body = _chat_body(content, profile["chat"]["schema_kwargs"], profile)
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        prepared[row["doc_id"]] = {"images": images, "schema_body": body}
        receipt.append({"doc_id": row["doc_id"], "source_sha256": row["source_sha256"],
                        "images": [{key: image[key] for key in ("page", "sha256", "bytes", "width", "height")}
                                   for image in images], "schema_request_sha256": _sha_bytes(raw)})
    _json(output / "preflight.json", {"source_lock_canonical_sha256": SOURCE_SHA256,
                                      "run_profile_canonical_sha256": PROFILE_SHA256, "sources": receipt})
    return prepared


def execute_arms(inventory: list[dict[str, Any]], profile: dict[str, Any], output: Path,
                 calls: GuardedCalls) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Run both no-reference-template arms. This function has no gold input."""
    outcomes: dict[str, dict[str, Any]] = {row["doc_id"]: {} for row in inventory}
    abort_reason: str | None = None
    try:
        prepared = _prepare_schema_requests(inventory, profile, output)
    except (ContractError, OSError, ValueError, RuntimeError) as exc:
        for row in inventory:
            outcomes[row["doc_id"]]["schema"] = {"status": "not_attempted", "reason": "input preflight failed"}
            outcomes[row["doc_id"]]["value"] = {"status": "not_attempted", "reason": "input preflight failed"}
        outcomes[inventory[0]["doc_id"]]["schema"] = {
            "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        return outcomes, "input rendering/resource preflight failure"
    for row in inventory:
        doc_id = row["doc_id"]
        try:
            _resource_guard()
            images = prepared[doc_id]["images"]
            outcomes[doc_id]["images"] = images
            reply = calls.complete(f"schema-{doc_id}", prepared[doc_id]["schema_body"])
            outcomes[doc_id]["schema"] = reply
            if reply["status"] == "complete" and not _valid_template(reply.get("value")):
                reply["status"] = "invalid_template"
                reply["error"] = "schema reply is not a bounded nested JSON template"
            if _infrastructure_failure(reply):
                abort_reason = "schema arm infrastructure or compatibility failure"
                break
        except (ContractError, OSError, ValueError) as exc:
            outcomes[doc_id]["schema"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            abort_reason = "schema arm render/resource/contract failure"
            break
    if abort_reason is None:
        for row in inventory:
            doc_id = row["doc_id"]
            schema_reply = outcomes[doc_id].get("schema") or {}
            if schema_reply.get("status") != "complete":
                outcomes[doc_id]["value"] = {"status": "not_attempted", "reason": "invalid or missing self-template"}
                continue
            try:
                images = outcomes[doc_id]["images"]
                content = _source_content(row, images, profile["instructions"]["self_template_values"])
                kwargs = {"template": json.dumps(schema_reply["value"], ensure_ascii=False),
                          "enable_thinking": False}
                reply = calls.complete(f"value-{doc_id}", _chat_body(content, kwargs, profile))
                outcomes[doc_id]["value"] = reply
                if _infrastructure_failure(reply):
                    abort_reason = "value arm infrastructure or compatibility failure"
                    break
            except (ContractError, OSError, ValueError) as exc:
                outcomes[doc_id]["value"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
                abort_reason = "value arm resource/contract failure"
                break
    return outcomes, abort_reason


def _load_gold_after_calls(paths: dict[str, Path], inventory: list[dict[str, Any]],
                           manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    for key in ("vrdu_gold", "cord_development_gold"):
        if sha256_file(paths[key]) != manifest["corpus_sha256"][key]:
            raise ContractError(f"gold manifest changed after model calls: {key}")
    ids = {row["doc_id"] for row in inventory}
    gold = {row["doc_id"]: row for row in load_jsonl(paths["vrdu_gold"])
            + load_jsonl(paths["cord_development_gold"]) if row["doc_id"] in ids}
    if set(gold) != ids:
        raise ContractError("gold manifest lacks a locked source")
    return gold


def _score_outcomes(inventory: list[dict[str, Any]], outcomes: dict[str, dict[str, Any]],
                    gold: dict[str, dict[str, Any]], rule: dict[str, Any]) -> dict[str, Any]:
    original = load_aliases()
    schema_scores: list[dict[str, Any]] = []
    value_scores: list[dict[str, Any]] = []
    for row in inventory:
        doc_id, family = row["doc_id"], row["family"]
        schema_reply = outcomes[doc_id].get("schema") or {}
        spec = template_to_graph_spec(schema_reply["value"]) if schema_reply.get("status") == "complete" else None
        for allow_aliases, mode in ((False, "original_exact_id"), (True, "original_predeclared_alias")):
            schema_scores.append({"doc_id": doc_id, "family": family, "mode": mode,
                                  **score_schema(spec, gold[doc_id]["gold_schema"], family=family,
                                                 definitions=original[family], allow_aliases=allow_aliases)})
        grouped = score_grouped_leaf(spec, gold[doc_id]["gold_schema"], rule)
        schema_scores.append({"doc_id": doc_id, "family": family, "mode": "grouped_leaf_v1", **grouped})
        value_reply = outcomes[doc_id].get("value") or {}
        value_scores.append({"doc_id": doc_id, "family": family, "status": value_reply.get("status", "not_attempted"),
                             **score_self_template_values(value_reply.get("value") if value_reply.get("status") == "complete" else None,
                                                         gold[doc_id], grouped)})
    grouped_rows = [row for row in schema_scores if row["mode"] == "grouped_leaf_v1"]
    summary = {}
    for family in ("registration-form", "ad-buy-form", "receipt", "all"):
        schema_family = [r for r in grouped_rows if family == "all" or r["family"] == family]
        value_family = [r for r in value_scores if family == "all" or r["family"] == family]
        mode_summary = {}
        for mode in ("original_exact_id", "original_predeclared_alias", "grouped_leaf_v1"):
            mode_rows = [r for r in schema_scores if r["mode"] == mode and
                         (family == "all" or r["family"] == family)]
            unavailable = any(r.get("linked_pair_unavailable", False) for r in mode_rows)
            mode_summary[mode] = {
                "matched": sum(r["matched"] for r in mode_rows),
                "gold_fields": sum(r["gold_fields"] for r in mode_rows),
                "linked_pair_hits": sum(r["linked_pair_hits"] for r in mode_rows),
                "linked_pair_total": None if unavailable else sum(r["linked_pair_total"] for r in mode_rows),
                "shape_hits": sum(r["shape_hits"] for r in mode_rows),
            }
        summary[family] = {
            "sources": len(schema_family),
            "schema_modes": mode_summary,
            "schema_matched": sum(r["matched"] for r in schema_family),
            "schema_gold_fields": sum(r["gold_fields"] for r in schema_family),
            "matched_linked_fields": sum(r["matched_linked_fields"] for r in schema_family),
            "linked_pair_hits": sum(r["linked_pair_hits"] for r in schema_family),
            "linked_pair_total": (None if any(r["linked_pair_unavailable"] for r in schema_family)
                                  else sum(r["linked_pair_total"] for r in schema_family)),
            "linked_pair_opportunities": sum(r["linked_pair_opportunities"] for r in schema_family),
            "linked_pair_unavailable_sources": sum(r["linked_pair_unavailable"] for r in schema_family),
            "alias_collisions": sum(len(r["collisions"]) for r in schema_family),
            "gold_scalar_positive": sum(r.get("gold_scalar_positive", 0) for r in value_family),
            "exact_scalar_positive": sum(r.get("exact_scalar_positive", 0) for r in value_family),
            "normalized_scalar_positive": sum(r.get("normalized_scalar_positive", 0) for r in value_family),
            "gold_scalar_list_positive": sum(r.get("gold_scalar_list_positive", 0) for r in value_family),
            "exact_scalar_list_positive": sum(r.get("exact_scalar_list_positive", 0) for r in value_family),
            "normalized_scalar_list_positive": sum(r.get("normalized_scalar_list_positive", 0) for r in value_family),
            "gold_linked_cells": sum(r.get("gold_linked_cells", 0) for r in value_family),
            "ordinal_exact_linked_cells": sum(r.get("ordinal_exact_linked_cells", 0) for r in value_family),
            "ordinal_normalized_linked_cells": sum(r.get("ordinal_normalized_linked_cells", 0) for r in value_family),
            "gold_complete_rows": sum(r.get("gold_complete_rows", 0) for r in value_family),
            "gold_sparse_rows": sum(r.get("gold_sparse_rows", 0) for r in value_family),
            "order_independent_raw_complete_rows": sum(r.get("order_independent_raw_complete_rows", 0) for r in value_family),
            "auto_accepted_values": 0,
        }
    return {"schema_scores": schema_scores, "value_scores": value_scores, "summary": summary}


def run(paths: dict[str, Path], runs_root: Path, model_file: Path, mmproj_file: Path,
        server_exe: Path, base: str, output: Path) -> dict[str, Any]:
    manifest, profile, rule = load_frozen_assets()
    inventory = verify_inventory(paths, runs_root, manifest)
    code = verify_code_lock()
    model = _verified_local_files(model_file, mmproj_file, server_exe)
    server = _verify_server(base, model_file)
    server["process"] = verify_server_command(base, server_exe, mmproj_file, profile)
    server["template_preflight"] = _verify_template_modes(base)
    _resource_guard()
    if output.exists() or output.resolve().is_relative_to(REPO_ROOT.resolve()):
        raise ContractError("raw output must be a new directory outside Git")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    calls = GuardedCalls(base, output)
    sampler = ResourceSampler(output)
    sampler.start()
    try:
        outcomes, abort_reason = execute_arms(inventory, profile, output, calls)
    finally:
        resources = sampler.finish()
    # This boundary is intentional: neither source selection nor either model
    # arm can access parsed gold. Gold is loaded only after every call ends.
    verify_code_lock()
    gold = _load_gold_after_calls(paths, inventory, manifest)
    scores = _score_outcomes(inventory, outcomes, gold, rule)
    report = {"version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "source_lock_canonical_sha256": SOURCE_SHA256, "rule_canonical_sha256": RULE_SHA256,
              "run_profile_canonical_sha256": PROFILE_SHA256, "code": code,
              "preflight_sha256": sha256_file(output / "preflight.json") if (output / "preflight.json").is_file() else None,
              "model": model, "server": server, "scored_sources": len(inventory),
              "attempted_calls": calls.calls, "accounted_tokens": calls.accounted_tokens,
              "elapsed_seconds": time.perf_counter() - started, "resources": resources,
              "abort_reason": abort_reason, "gold_loaded_after_model_calls": True,
              "outcomes": {doc_id: {arm: {k: v for k, v in data.items() if k != "value"}
                                    for arm, data in details.items() if arm in {"schema", "value"}}
                           for doc_id, details in outcomes.items()},
              **scores,
              "limitations": ["Tuned secondary development candidate; original 0/26 is unchanged.",
                              "No reference schema or gold content entered model prompts.",
                              "CORD labels are positive-only; VRDU reference ontology is narrow.",
                              "No verified model cell boxes or quote spans; zero auto-accepted values."]}
    _json(output / "run.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vrdu-cohort", required=True, type=Path)
    parser.add_argument("--vrdu-gold", required=True, type=Path)
    parser.add_argument("--cord-cohort", required=True, type=Path)
    parser.add_argument("--cord-gold", required=True, type=Path)
    parser.add_argument("--cord-reserved", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--model-file", type=Path)
    parser.add_argument("--mmproj-file", type=Path)
    parser.add_argument("--server-exe", type=Path)
    parser.add_argument("--server-url", default="http://127.0.0.1:18127")
    parser.add_argument("--output-dir", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    paths = {"vrdu_cohort": args.vrdu_cohort, "vrdu_gold": args.vrdu_gold,
             "cord_development_cohort": args.cord_cohort, "cord_development_gold": args.cord_gold,
             "cord_reserved_cohort": args.cord_reserved}
    if args.check:
        manifest, _, _ = load_frozen_assets()
        inventory = verify_inventory(paths, args.runs_root, manifest)
        print(json.dumps({"ready_sources": len(inventory), "source_lock_canonical_sha256": SOURCE_SHA256,
                          "rule_canonical_sha256": RULE_SHA256, "model_calls": 0}))
        return
    if not all((args.model_file, args.mmproj_file, args.server_exe, args.output_dir)):
        parser.error("--run requires --model-file, --mmproj-file, --server-exe and --output-dir")
    report = run(paths, args.runs_root, args.model_file, args.mmproj_file, args.server_exe,
                 _loopback_base(args.server_url), args.output_dir)
    print(json.dumps({"scored_sources": report["scored_sources"], "attempted_calls": report["attempted_calls"],
                      "output_dir": str(args.output_dir)}))


if __name__ == "__main__":
    main()
