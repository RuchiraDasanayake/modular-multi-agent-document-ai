"""Allowlisted authenticated recovery readback. No extraction or review mutations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

from native_recovery_files import (RecoveryError, digest, guard, inventory, read_json, safe_path,
                                   verify_bundle, write_new)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RecoveryError("Recovery HTTP redirects are forbidden.")


def request(base: str, path: str, *, token: str | None = None, login: dict | None = None) -> tuple[int, bytes, str]:
    headers = {"Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if login is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(login).encode()
    req = urllib.request.Request(base + path, data=body, headers=headers,
                                 method="POST" if login is not None else "GET")
    # No environment proxy, redirects, retries or exception-body logging.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=30) as response:
            data = response.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise RecoveryError("HTTP readback exceeds the bounded response limit.")
            return response.status, data, response.headers.get("X-DocAI-Recovery", "")
    except urllib.error.HTTPError as exc:
        return exc.code, b"", exc.headers.get("X-DocAI-Recovery", "")


def checked_case(case: dict) -> tuple[str, str]:
    for key in ("job_id", "document_id", "run_id"):
        if not isinstance(case.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", case[key]):
            raise RecoveryError("Invalid HTTP case identity.")
    job, doc, run = case["job_id"], case["document_id"], case["run_id"]
    source = case.get("source_relative_path")
    if not isinstance(source, str) or not re.fullmatch(
            rf"frontend/uploads/job_{re.escape(job)}/[A-Za-z0-9_.-]+", source):
        raise RecoveryError("HTTP source path must identify exactly one copied job upload.")
    return f"/api/jobs/{job}/docs/{doc}/content", f"/api/jobs/{job}/auto/{run}/export"


def readback(config: dict, cases: list[dict], *, http=request) -> list[dict]:
    if not cases or len(cases) > 20:
        raise RecoveryError("The recovery drill requires 1–20 explicit reviewed cases.")
    base = f"http://127.0.0.1:{int(config['frontendPort'])}"
    def checked_http(path, **kwargs):
        status, body, mode = http(base, path, **kwargs)
        if config.get("recoveryPassive") and mode != "read-only":
            raise RecoveryError("HTTP endpoint does not expose the passive recovery boundary.")
        return status, body
    for case in cases:
        source_url, export_url = checked_case(case)
        for url in (source_url, export_url):
            if checked_http(url)[0] != 401:
                raise RecoveryError("An anonymous artifact request did not fail with 401.")
    status, payload = checked_http("/api/auth/login", login={
        "username": config.get("adminUsername", "admin"), "password": config["adminPassword"]})
    if status != 200:
        raise RecoveryError("Recovery authentication failed.")
    try:
        token = json.loads(payload)["access_token"]
        if not isinstance(token, str) or not token:
            raise ValueError()
    except (ValueError, KeyError, TypeError) as exc:
        raise RecoveryError("Recovery authentication returned an invalid response.") from exc
    outcomes = []
    for case in cases:
        source_url, export_url = checked_case(case)
        source = safe_path(Path(config["dataDir"]) / case["source_relative_path"])
        source_status, source_data = checked_http(source_url, token=token)
        export_status, export_data = checked_http(export_url, token=token)
        if source_status != 200 or export_status != 200 or not source_data or not export_data:
            raise RecoveryError("An authenticated artifact readback failed.")
        source_hash = hashlib.sha256(source_data).hexdigest()
        if source_hash != digest(source):
            raise RecoveryError("HTTP source differs from the configured data root.")
        outcomes.append({key: case[key] for key in ("job_id", "document_id", "run_id", "source_relative_path")} |
            {"source_sha256": source_hash, "reviewed_export_sha256": hashlib.sha256(export_data).hexdigest(),
             "source_bytes": len(source_data), "reviewed_export_bytes": len(export_data), "anonymous_status": 401})
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "verify"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--cases", type=Path, help="Capture only: private JSON with explicit cases array")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        guard("Private", safe_path(args.config))
        guard("Private", safe_path(args.out.parent))
        config = read_json(args.config)
        if args.action == "capture":
            if args.cases is None or config.get("recoveryPassive"):
                raise RecoveryError("Capture requires original configuration and explicit cases.")
            outcomes = readback(config, read_json(args.cases)["cases"])
            result = {"version": 1, "kind": "docai_recovery_http_baseline", "dataDir": config["dataDir"], "cases": outcomes}
        else:
            if config.get("recoveryPassive") is not True:
                raise RecoveryError("Verification requires a restored passive configuration.")
            guard("PassiveRunning", args.config)
            root = safe_path(Path(config["runtimeRoot"]))
            receipt = read_json(root / "restore-receipt.json")
            if receipt.get("config_sha256") != digest(args.config) or config["dataDir"] != str(root / "data"):
                raise RecoveryError("Recovery configuration differs from the verified copy.")
            bundle = safe_path(Path(receipt["bundle"]))
            verify_bundle(bundle)
            if receipt["backup_manifest_sha256"] != digest(bundle / "manifest.json"):
                raise RecoveryError("Recovery points to a different backup.")
            baseline = read_json(bundle / "private" / "http-baseline.json")
            if inventory(root / "data") != receipt.get("restored_data"):
                raise RecoveryError("Copied product evidence changed before readback.")
            outcomes = readback(config, baseline["cases"])
            if outcomes != baseline["cases"]:
                raise RecoveryError("Restored HTTP artifacts differ from the sealed original baseline.")
            if inventory(root / "data") != receipt.get("restored_data"):
                raise RecoveryError("Readback changed copied product evidence.")
            result = {"version": 1, "kind": "docai_passive_http_drill", "status": "passed",
                      "baseline_sha256": digest(bundle / "private" / "http-baseline.json"),
                      "restore_receipt_sha256": digest(root / "restore-receipt.json"), "cases": outcomes,
                      "limits": "Readback only; no extraction worker, queue execution or failover was tested."}
        write_new(args.out, result)
        print(json.dumps({"status": "passed", "cases": len(outcomes), "receipt_sha256": digest(args.out)}))
        return 0
    except (RecoveryError, OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        print(json.dumps({"status": "refused", "message": "Recovery HTTP readback failed; no response bodies or credentials were logged."}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
