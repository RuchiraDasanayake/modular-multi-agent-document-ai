"""Read-only freeze/preflight for a 2,000-original, confirmed-schema model gate.

This module never loads labels, performs OCR, or constructs a provider client.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import site
import subprocess
import sys
from pathlib import Path

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from product_eval.final_gate_ledger import Ledger

TARGET_SOURCES = 2000
FAMILY_COUNTS = {"registration-form": 897, "ad-buy-form": 305, "receipt": 798}
BASE_URL = "https://icore.innobothealth.us/innobot-api/v1"
MODEL = "innobot-luna-6"
ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[a-f0-9]{64}\Z")
DOC_ID = re.compile(r"[a-f0-9]{32}\Z")
DEFAULT_PROFILE = {
    "ocr_engine": "rapidocr", "response_format_profile": "strict_confirmed_values_v1",
    "long_document_profile": "bounded_text_segments_v1", "visual_document_profile": "disabled",
    "base_url": BASE_URL, "model": MODEL, "max_tokens": 8192, "timeout_s": 180,
    "max_calls": 2500, "max_calls_per_source": 4, "workers": 1, "batch_size": 25,
    "parallel_validation": None,
}


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def digest_json(value) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def write_new(path: Path, value) -> str:
    """Exclusive creation plus fsync; no receipt can replace an earlier result."""
    return write_new_bytes(path, encoded(value))


def write_new_bytes(path: Path, raw: bytes) -> str:
    """Persist exact preflighted wire bytes without changing JSON encoding."""
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def code_receipt() -> dict:
    def git(*args):
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Freeze/run requires a clean checkout")
    # Hash the executing source as well as Git's commit; ignored Python files
    # must not silently alter the product imported by a spawned worker.
    sources = {}
    for package in ("idpo", "product_eval"):
        for path in sorted((ROOT / package).rglob("*.py")):
            if path.is_symlink():
                raise ValueError("Python source symlinks are not supported")
            sources[path.relative_to(ROOT).as_posix()] = digest_file(path)
    return {"commit": git("rev-parse", "HEAD"), "python_source_sha256": sources}


def require_interfaces(profile: dict | None = None) -> None:
    from idpo.product_auto.provider import OpenAICompatibleChat
    from idpo.product_auto.strict_output import PROFILE
    from idpo.product_auto.workflow import process_auto
    required = {"confirmed_schema", "response_format_profile", "long_document_profile", "output_root"}
    if not required <= set(inspect.signature(process_auto).parameters):
        raise ValueError("Required product long-document/confirmed-schema interfaces are not implemented")
    from idpo.product_auto.long_document import PROFILE as LONG_PROFILE
    from idpo.product_auto.segments import MAX_SEGMENT_CHARS, MAX_SEGMENTS
    if LONG_PROFILE != DEFAULT_PROFILE["long_document_profile"] or (MAX_SEGMENT_CHARS, MAX_SEGMENTS) != (24000, 4):
        raise ValueError("Required bounded long-document profile is not implemented")
    if PROFILE != DEFAULT_PROFILE["response_format_profile"] or "response_format" not in inspect.signature(OpenAICompatibleChat.complete_json).parameters:
        raise ValueError("Required strict response interface is not implemented")
    if profile and profile["visual_document_profile"] != "disabled":
        from idpo.product_auto.visual_workflow import PROFILES as VISUAL_PROFILES
        from idpo.product_auto.visual_input import MAX_IMAGES, MAX_REQUESTS, MAX_REQUEST_BYTES, MAX_EDGE
        if (profile["visual_document_profile"] not in VISUAL_PROFILES or
                "visual_document_profile" not in inspect.signature(process_auto).parameters or
                not callable(getattr(OpenAICompatibleChat, "complete_visual_json", None)) or
                "request" not in inspect.signature(OpenAICompatibleChat.complete_visual_json).parameters or
                (MAX_IMAGES, MAX_REQUESTS, MAX_REQUEST_BYTES, MAX_EDGE) != (12, 4, 4 * 1024 * 1024, 2048)):
            raise ValueError("Required bounded visual interface is not implemented")


def validate_profile(raw: dict) -> dict:
    if not isinstance(raw, dict) or set(raw) != set(DEFAULT_PROFILE):
        raise ValueError("Profile must contain exactly the documented keys")
    for key in ("ocr_engine", "response_format_profile", "long_document_profile",
                "base_url", "model", "max_calls_per_source", "batch_size"):
        if raw[key] != DEFAULT_PROFILE[key] or type(raw[key]) is not type(DEFAULT_PROFILE[key]):
            raise ValueError(f"Unsupported profile field: {key}")
    if not isinstance(raw["visual_document_profile"], str) or raw["visual_document_profile"] not in {"disabled", "bounded_visual_v1", "bounded_visual_selective_v2"}:
        raise ValueError("Unsupported profile field: visual_document_profile")
    for key, low, high in (("max_tokens", 256, 8192), ("timeout_s", 1, 180),
                           ("max_calls", TARGET_SOURCES, 2500), ("workers", 1, 4)):
        if type(raw[key]) is not int or not low <= raw[key] <= high:
            raise ValueError(f"Invalid profile field: {key}")
    if raw["workers"] == 1 and raw["parallel_validation"] is not None:
        raise ValueError("Single-worker profile must not claim parallel validation")
    if raw["workers"] > 1 and not isinstance(raw["parallel_validation"], dict):
        raise ValueError("Parallel OCR requires a frozen resource validation receipt")
    return dict(raw)


def verify_sources(rows: list[dict]) -> None:
    from idpo.product_auto.workflow import _doc_id
    if len(rows) != TARGET_SOURCES:
        raise ValueError(f"Exactly {TARGET_SOURCES} original documents are required")
    ids, hashes, families = set(), set(), {}
    for row in rows:
        doc_id, sha = row.get("doc_id"), row.get("source_sha256")
        if not isinstance(doc_id, str) or not DOC_ID.fullmatch(doc_id) or doc_id in ids:
            raise ValueError("Unsafe or repeated document ID")
        if not isinstance(sha, str) or not SHA.fullmatch(sha) or sha in hashes:
            raise ValueError("Missing or repeated original source SHA-256")
        path = Path(row["source_path"])
        if not path.is_absolute() or path.is_symlink() or path.suffix.lower() not in {".pdf", ".png"}:
            raise ValueError("This gate requires original local PDF/PNG sources")
        if (type(row.get("source_size_bytes")) is not int or path.stat().st_size != row["source_size_bytes"]
                or digest_file(path) != sha):
            raise ValueError("Original source bytes differ from inventory")
        if _doc_id(path.name, sha, 0) != doc_id:
            raise ValueError("Inventory document ID differs from the original product intake ID")
        ids.add(doc_id)
        hashes.add(sha)
        family = row["family"]
        families[family] = families.get(family, 0) + 1
    if families != FAMILY_COUNTS:
        raise ValueError("The three-family mixed2000 allocation does not match")


# Probe metadata/model bytes only, using the exact interpreter used at runtime.
# RECORD hashes freeze installation manifests; they do not attest every wheel
# payload byte. The parser source, Python executable and OCR models are hashed.
_PROBE = r'''
import hashlib, importlib.metadata as md, json, platform, sys
from pathlib import Path
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()
packages = []
for d in md.distributions():
    records = [f for f in (d.files or []) if str(f).endswith('.dist-info/RECORD')]
    packages.append({'name': d.metadata['Name'], 'version': d.version,
                     'record_sha256': sha(Path(d.locate_file(records[0]))) if records else None})
result = {'python': sys.version, 'executable': str(Path(sys.executable).resolve()),
          'executable_sha256': sha(Path(sys.executable)), 'platform': platform.platform(),
          'packages': sorted(packages, key=lambda p:(p['name'].lower(),p['version']))}
if len(sys.argv) > 1:
    sys.path.insert(0, sys.argv[1])
    from rapid_ocr_worker import verify_runtime
    from rapid_ocr_protocol import MODEL_SHA256, REVISION
    models = verify_runtime()
    result.update(rapidocr_revision=REVISION, model_sha256={n:sha(models/n) for n in MODEL_SHA256})
print(json.dumps(result, sort_keys=True))
'''


def runtime_receipt() -> dict:
    from idpo.product_auto.rapid_ocr import RapidOcrConfig, worker_environment
    if site.ENABLE_USER_SITE or os.environ.get("PYTHONPATH"):
        raise ValueError("Use Python -s (or a virtual environment) with PYTHONPATH unset for a reproducible gate")
    config = RapidOcrConfig.from_env()
    if config.work_dir is None:
        raise ValueError("Set IDPO_RAPIDOCR_WORK_DIR to an existing directory on the data drive")
    env = worker_environment(config.python, config.work_dir)
    def probe(python, *args, environment=None):
        result = subprocess.run([str(python), "-I", "-c", _PROBE, *args],
                                capture_output=True, text=True, timeout=180, env=environment, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode:
            raise ValueError("Runtime metadata/model verification failed")
        return json.loads(result.stdout)
    product = probe(sys.executable)
    names = {item["name"].lower().replace("_", "-") for item in product["packages"]}
    if not {"openai", "pypdf", "pypdfium2", "pillow", "psutil", "numpy"} <= names:
        raise ValueError("Product parser/provider dependencies are missing")
    return {"product": product, "ocr": probe(config.python, str(ROOT / "idpo/product_auto"), environment=env),
            "ocr_config": {"python": str(config.python), "timeout_s": config.timeout_s,
                           "max_rss_mib": config.max_rss_mib, "work_dir": str(config.work_dir)},
            "ocr_environment": env}


def verify_parallel(profile: dict, code: dict, runtime: dict) -> None:
    if profile["workers"] == 1:
        return
    receipt = profile["parallel_validation"]
    baseline = {**profile, "parallel_validation": None}
    if (receipt.get("status") != "passed" or receipt.get("workers") != profile["workers"]
            or receipt.get("code_commit") != code["commit"]
            or receipt.get("runtime_sha256") != digest_json(runtime)
            or receipt.get("profile_sha256") != digest_json(baseline)
            or type(receipt.get("peak_tree_rss_bytes")) is not int or receipt["peak_tree_rss_bytes"] <= 0
            or type(receipt.get("minimum_available_memory_bytes")) is not int
            or receipt["minimum_available_memory_bytes"] < 1024 ** 3
            or type(receipt.get("completed_sources")) is not int or receipt["completed_sources"] < profile["workers"]
            or not isinstance(receipt.get("evidence_sha256"), str) or not SHA.fullmatch(receipt["evidence_sha256"])):
        raise ValueError("Parallel resource validation is missing or does not match this freeze")
    import psutil
    if psutil.virtual_memory().available < receipt["peak_tree_rss_bytes"] + 1024 ** 3:
        raise ValueError("Current available memory is below the validated parallel peak plus 1 GiB")


def freeze(cohort: Path, schema_protocol: Path, profile_path: Path, output: Path) -> str:
    profile = validate_profile(read_json(profile_path))
    require_interfaces(profile)
    code, runtime = code_receipt(), runtime_receipt()
    verify_parallel(profile, code, runtime)
    raw_rows = [json.loads(line) for line in cohort.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Carry no label paths, answers, expected-field presence or annotation text.
    keys = ("doc_id", "source_path", "source_sha256", "source_size_bytes", "family", "dataset_id", "gate_shard")
    rows = [{key: row[key] for key in keys} for row in raw_rows]
    rows.sort(key=lambda row: (row["gate_shard"], row["doc_id"]))
    verify_sources(rows)
    schemas = read_json(schema_protocol)["schemas"]
    if set(schemas) != set(FAMILY_COUNTS):
        raise ValueError("One frozen confirmed schema is required per family")
    frozen_schemas = {}
    for family, item in schemas.items():
        path = Path(item["path"])
        load_confirmed_schema(path, item["sha256"])
        frozen_schemas[family] = {"path": f"schemas/{family}.json", "sha256": item["sha256"]}
    protocol = {
        "version": 1, "mode": "model2000_original_operational", "labels_opened": False,
        "cohort_sha256": digest_file(cohort), "schema_protocol_sha256": digest_file(schema_protocol),
        "code": code, "runtime": runtime, "profile": profile, "schemas": frozen_schemas,
        "sources": rows, "target_distinct_originals": TARGET_SOURCES,
        "call_plan": {"minimum_for_model_gate": TARGET_SOURCES,
                      "configured_global_cap": profile["max_calls"], "worst_case_at_four_per_source": 4 * TARGET_SOURCES,
                      "exact_forecast_available": False,
                      "note": "Freeze does not OCR sources; actual segment counts may exceed the global call budget."},
        "scope": "confirmed-schema operational gate; not discovery, accuracy, or visual correctness",
    }
    # A complete protocol is only published after all preflight checks pass.
    output.mkdir(parents=True, exist_ok=False)
    (output / "schemas").mkdir()
    for family, item in schemas.items():
        path = output / frozen_schemas[family]["path"]
        with path.open("xb") as stream:
            stream.write(Path(item["path"]).read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        load_confirmed_schema(path, item["sha256"])
    sha = write_new(output / "protocol.json", protocol)
    Ledger(output / "ledger.sqlite3").initialize(rows, sha, profile["max_calls"])
    return sha


def verify_freeze(output: Path, expected_sha256: str) -> dict:
    if not SHA.fullmatch(expected_sha256) or digest_file(output / "protocol.json") != expected_sha256:
        raise ValueError("Frozen protocol SHA-256 differs")
    protocol = read_json(output / "protocol.json")
    if protocol.get("version") != 1 or protocol.get("mode") != "model2000_original_operational":
        raise ValueError("Unknown gate protocol")
    validate_profile(protocol["profile"])
    require_interfaces(protocol["profile"])
    if code_receipt() != protocol["code"] or runtime_receipt() != protocol["runtime"]:
        raise ValueError("Code or runtime changed; create a new arm")
    verify_parallel(protocol["profile"], protocol["code"], protocol["runtime"])
    verify_sources(protocol["sources"])
    for family, item in protocol["schemas"].items():
        if family not in FAMILY_COUNTS or item["path"] != f"schemas/{family}.json":
            raise ValueError("Unsafe frozen schema path")
        load_confirmed_schema(output / item["path"], item["sha256"])
    return protocol
