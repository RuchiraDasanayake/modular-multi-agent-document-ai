"""Exercise native HTTP ownership gates using two temporary, then disabled viewers.

Supporting verification: uses an existing synthetic reviewed-result receipt. It
never requests extraction as an admin or sends email. Credentials stay in memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def require(condition: bool, message: str) -> None:
    """Verification checks must execute even when Python optimization is enabled."""
    if not condition:
        raise AssertionError(message)


def validate_fixture(fixture: object) -> dict:
    """Reject incomplete or unsafe positive controls before any HTTP mutation."""
    def identifier(value):
        return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is not None

    def digest(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    def positive_integer(value):
        return type(value) is int and value > 0

    require(isinstance(fixture, dict) and fixture.get("contract") == "synthetic_visual_hitl_v1",
            "Use the completed synthetic visual workflow receipt")
    require(identifier(fixture.get("job_id")) and positive_integer(fixture.get("brief_confirmed_revision")),
            "Fixture requires a valid job and confirmed brief")
    runs = fixture.get("runs")
    require(isinstance(runs, list) and len(runs) == 2 and all(isinstance(run, dict) for run in runs),
            "Fixture requires completed preview and batch runs")
    require({run.get("phase") for run in runs if isinstance(run.get("phase"), str)} == {"preview", "batch"},
            "Fixture requires distinct preview and batch phases")
    for run in runs:
        require(identifier(run.get("run_id")) and identifier(run.get("doc_id"))
                and digest(run.get("reviewed_export_sha256")), "Fixture result identity or export hash is invalid")
        require(positive_integer(run.get("review_revision")) and run.get("reviewed_json_status") == 200,
                "Fixture result has not completed review and export")
    require(len({run["run_id"] for run in runs}) == len({run["doc_id"] for run in runs}) == 2,
            "Fixture must identify two distinct runs and documents")
    require(type(fixture.get("batch_jsonl_line_count")) is int and fixture["batch_jsonl_line_count"] == 1
            and digest(fixture.get("batch_jsonl_sha256")), "Fixture batch export is incomplete")
    return fixture


def verify(config_path: Path, fixture_path: Path, output: Path) -> dict:
    fixture_bytes = fixture_path.read_bytes()
    fixture = validate_fixture(json.loads(fixture_bytes))
    cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    output.mkdir(parents=True, exist_ok=False)
    web = f"http://127.0.0.1:{int(cfg['frontendPort'])}"
    gateway = f"http://127.0.0.1:{int(cfg['gatewayPort'])}"
    report: dict = {"contract": "native_owner_isolation_v1", "status": "running",
                    "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
                    "checks": [], "created_viewer_ids": [], "disabled_viewer_ids": []}
    admin_token = None
    viewer_tokens = {}

    def persist() -> None:
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def call(label, base, route, token=None, method="GET", body=None, expected=200,
             headers=None, sensitive=False):
        request_headers = dict(headers or {})
        if token:
            request_headers["Authorization"] = "Bearer " + token
        data = body
        if body is not None and not isinstance(body, bytes):
            data = json.dumps(body).encode()
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(base + route, data=data, method=method, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as response:
            status, raw = response.code, response.read()
        check = {"label": label, "method": method, "status": status, "expected": expected}
        # Even token hashes are unnecessary in the audit artifact.
        if not sensitive:
            check["response_sha256"] = hashlib.sha256(raw).hexdigest()
        report["checks"].append(check)
        persist()
        if status != expected:
            raise AssertionError(f"{label}: expected HTTP {expected}, got {status}")
        return raw

    def login(username, password, label):
        raw = call(label, gateway, "/api/auth/login", method="POST", sensitive=True,
                   body={"username": username, "password": password})
        return json.loads(raw)["access_token"]

    def upload(job_id, token, expected=201, label="owner upload"):
        boundary = "DocAIIsolation" + uuid.uuid4().hex
        content = b"Owner isolation synthetic fixture.\nTotal: 12.50\n"
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="owner.txt"\r\n'
                'Content-Type: text/plain\r\n\r\n').encode() + content + f"\r\n--{boundary}--\r\n".encode()
        raw = call(label, web, f"/api/jobs/{job_id}/documents", token, "POST", body, expected,
                   {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        return raw, content

    try:
        admin_token = login(cfg.get("adminUsername", "admin"), cfg["adminPassword"], "administrator login")
        for name in ("a", "b"):
            username = "access_" + name + "_" + uuid.uuid4().hex[:16]
            password = secrets.token_urlsafe(32)
            raw = call(f"create viewer {name}", gateway, "/api/auth/register", admin_token, "POST",
                       {"username": username, "password": password,
                        "email": username + "@example.com", "role": "viewer"}, 201)
            account = json.loads(raw)
            report["created_viewer_ids"].append(account["id"])
            persist()
            require(account.get("role") == "viewer", "Fixture account must be a viewer")
            viewer_tokens[name] = login(username, password, f"viewer {name} login")
        a, b = viewer_tokens["a"], viewer_tokens["b"]
        raw = call("owner creates job", web, "/api/jobs", a, "POST",
                   {"jobName": "HTTP owner-isolation verification"}, 201)
        job_id = json.loads(raw)["jobId"]
        report["fixture_job_id"] = job_id
        raw, content = upload(job_id, a)
        job = json.loads(raw)
        source = job["documents"][0]
        job_route = f"/api/jobs/{job_id}"
        source_route = job_route + f"/docs/{source['fileId']}/content"
        require(call("owner reads exact uploaded bytes", web, source_route, a) == content, "Owner source bytes differ")
        call("other viewer cannot read source", web, source_route, b, expected=404)
        call("anonymous cannot read source", web, source_route, expected=401)
        upload(job_id, b, 404, "other viewer cannot append upload")
        call("other viewer cannot rename job", web, job_route, b, "PATCH", {"jobName": "changed"}, 404)
        listed = json.loads(call("other viewer lists jobs", web, "/api/jobs", b))["jobs"]
        require(job_id not in {item["jobId"] for item in listed}, "Other viewer listed the owner's job")
        before = call("owner reads job before denied requests", web, job_route, a)
        brief_body = {"expectedRevision": 0, "intent": "Extract the final amount",
                      "sampleFileIds": [source["fileId"]], "fields": []}
        draft = json.loads(call("owner saves draft", web, job_route + "/auto/brief", a,
                               "POST", brief_body, 201))["brief"]
        pin = {"expectedRevision": draft["revision"], "expectedPayloadSha256": draft["payload_sha256"]}
        call("viewer cannot spend on schema suggestion", web, job_route + "/auto/brief/suggest", a,
             "POST", pin, 403)
        call("viewer cannot spend on extraction", web, job_route + "/auto", a, "POST",
             {"selectedFileIds": [source["fileId"]]}, 403)
        for method, suffix, body in [
            ("GET", "", None), ("GET", "/auto", None), ("POST", "/auto", {}),
            ("GET", "/auto/brief", None), ("POST", "/auto/brief", brief_body),
            ("PATCH", "/auto/brief", pin), ("POST", "/auto/brief/suggest", pin),
            ("GET", "/auto/recipes", None), ("POST", "/auto/recipes", {}),
            ("GET", "/auto/recipes/unknown", None), ("POST", "/auto/recipes/unknown", {}),
        ]:
            call("cross-owner " + method + " " + (suffix or "/job"), web,
                 job_route + suffix, b, method, body, 404)
        require(call("owner job remains unchanged", web, job_route, a) == before, "Denied requests changed the owner's job")
        after = json.loads(call("owner draft remains unchanged", web, job_route + "/auto/brief", a))["brief"]
        require(after == draft, "Denied requests changed the owner's draft")
        # Use real, previously reviewed artifacts so a missing file cannot mask
        # accidental authorization. The administrator's exports must still match.
        for run in fixture["runs"]:
            route = f"/api/jobs/{fixture['job_id']}/auto/{run['run_id']}"
            detail = route + f"/docs/{run['doc_id']}"
            original = call("administrator reads reviewed export", web, detail + "/export", admin_token)
            require(hashlib.sha256(original).hexdigest() == run["reviewed_export_sha256"], "Reviewed export fixture hash differs")
            for name, token in viewer_tokens.items():
                for method, suffix, body in [("GET", detail, None), ("POST", detail, {}),
                                             ("GET", detail + "/export", None),
                                             ("GET", route + "/export", None)]:
                    call(f"viewer {name} denied existing {run['phase']} " + method + " " +
                         ("export" if suffix.endswith("/export") else "review"),
                         web, suffix, token, method, body, 404)
            require(call("administrator export unchanged", web, detail + "/export", admin_token) == original,
                    "Denied requests changed the reviewed export")
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["failure_type"] = type(exc).__name__
        # Exception messages may contain URLs or response details; retain only
        # the safe assertion messages written in this verification script.
        if isinstance(exc, AssertionError):
            report["failure_check"] = str(exc)
        raise
    finally:
        if admin_token:
            for user_id in report["created_viewer_ids"]:
                try:
                    raw = call("disable temporary viewer", gateway, f"/api/auth/users/{user_id}/toggle",
                               admin_token, "PATCH")
                    if json.loads(raw).get("is_active") is not False:
                        raise AssertionError("Temporary account did not become inactive")
                    report["disabled_viewer_ids"].append(user_id)
                except Exception as exc:  # noqa: BLE001 - attempt cleanup for every created account and report failures
                    report["status"] = "failed"
                    report.setdefault("cleanup_errors", []).append(type(exc).__name__)
        persist()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--reviewed-fixture-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.config, args.reviewed_fixture_receipt, args.output)
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]),
                      "temporary_viewers_disabled": len(result["disabled_viewer_ids"])}))
    raise SystemExit(0 if result["status"] == "passed" else 1)
