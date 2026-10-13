"""Synthetic HTTP only: verify the verifier without creating real accounts."""

from __future__ import annotations

import hashlib
import io
import json
import types
import urllib.error
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import verify_native_owner_isolation as owner

CONTENT = b"Owner isolation synthetic fixture.\nTotal: 12.50\n"
EXPORT = b'{"synthetic": "reviewed"}'


def fixture_receipt():
    return {"contract": "synthetic_visual_hitl_v1", "job_id": "reviewed-job", "brief_confirmed_revision": 2,
            "batch_jsonl_line_count": 1, "batch_jsonl_sha256": "a" * 64,
            "runs": [{"phase": phase, "run_id": "auto_" + phase, "doc_id": "doc_" + phase,
                      "review_revision": 1, "reviewed_json_status": 200,
                      "reviewed_export_sha256": hashlib.sha256(EXPORT).hexdigest()} for phase in ("preview", "batch")]}


def compiled_module(optimize):
    path = Path(owner.__file__)
    module = types.ModuleType("synthetic_owner_verifier")
    exec(compile(path.read_bytes(), str(path), "exec", optimize=optimize), module.__dict__)  # noqa: S102 - trusted local source, explicit optimization regression
    return module


class Response:
    def __init__(self, raw, status):
        self.raw, self.status = raw, status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        return self.raw


class HttpFixture:
    def __init__(self, defect=None):
        self.defect, self.calls, self.accounts, self.disabled = defect, [], [], []
        self.job_reads, self.export_reads = 0, 0

    def __call__(self, request, timeout):
        from urllib.parse import urlsplit

        assert timeout == 30
        route, method, token = urlsplit(request.full_url).path, request.get_method(), request.get_header("Authorization", "")
        self.calls.append((method, route))
        status, value = 200, {}
        if route == "/api/auth/login":
            body = json.loads(request.data)
            value = {"access_token": "admin-token" if body["username"] == "admin" else f"viewer{len(self.accounts)}"}
        elif route == "/api/auth/register":
            self.accounts.append(str(len(self.accounts) + 1))
            status, value = 201, {"id": self.accounts[-1], "role": "admin" if self.defect == "role" else "viewer"}
        elif route.startswith("/api/auth/users/"):
            self.disabled.append(route.split("/")[-2])
            value = {"is_active": False}
        elif route == "/api/jobs" and method == "POST":
            status, value = 201, {"jobId": "synthetic-job"}
        elif route == "/api/jobs":
            value = {"jobs": [{"jobId": "synthetic-job"}] if self.defect == "listing" else []}
        elif not token:
            status = 401
        elif token == "Bearer viewer2" or (route.startswith("/api/jobs/reviewed-job/") and token == "Bearer viewer1"):
            status = 404
        elif route.endswith("/documents"):
            status, value = 201, {"documents": [{"fileId": "source"}]}
        elif route.endswith("/content"):
            value = b"wrong source" if self.defect == "source" else CONTENT
        elif route.endswith(("/auto/brief/suggest", "/auto")):
            status = 403
        elif route.endswith("/auto/brief"):
            revision = 2 if method == "GET" and self.defect == "draft" else 1
            status, value = (201 if method == "POST" else 200), {"brief": {"revision": revision, "payload_sha256": "a" * 64}}
        elif route.endswith("/export"):
            self.export_reads += 1
            value = (b"changed export" if self.defect == "export_changed" and self.export_reads > 1 else EXPORT)
        else:
            self.job_reads += 1
            value = {"jobId": "synthetic-job", "jobName": "changed" if self.defect == "job" and self.job_reads > 1 else "unchanged"}
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "synthetic", {}, io.BytesIO(raw))
        return Response(raw, status)


def inputs(tmp_path, receipt):
    cfg, fixture = tmp_path / "config.json", tmp_path / "fixture.json"
    cfg.write_text(json.dumps({"frontendPort": 3000, "gatewayPort": 8000, "adminPassword": "synthetic-secret"}))
    fixture.write_text(json.dumps(receipt))
    return cfg, fixture, tmp_path / "output"


@pytest.mark.parametrize("optimize", [0, 2])
@pytest.mark.parametrize("defect", [None, "source", "listing", "job", "draft", "export_hash", "export_changed"])
def test_all_invariants_execute_under_optimized_python(tmp_path, monkeypatch, optimize, defect):
    module, http, receipt = compiled_module(optimize), HttpFixture(defect), fixture_receipt()
    if defect == "export_hash":
        receipt["runs"][0]["reviewed_export_sha256"] = "f" * 64
    args = inputs(tmp_path, receipt)
    monkeypatch.setattr(module.urllib.request, "urlopen", http)
    if defect:
        with pytest.raises(AssertionError):
            module.verify(*args)
    else:
        assert module.verify(*args)["status"] == "passed"
    result = json.loads((args[2] / "result.json").read_text())
    assert result["status"] == ("failed" if defect else "passed")
    assert any(row["label"] == "owner reads exact uploaded bytes" for row in result["checks"])
    assert http.disabled == http.accounts == ["1", "2"]
    assert "synthetic-secret" not in json.dumps(result) and "admin-token" not in json.dumps(result)
    if defect is None:
        assert len(result["checks"]) == 52


@pytest.mark.parametrize("damage", ["empty", "one_phase", "duplicate_phase", "job_missing", "unsafe_id", "bad_hash", "unreviewed", "export_failed", "batch_incomplete"])
def test_incomplete_fixture_fails_before_config_or_http(tmp_path, monkeypatch, damage):
    receipt = deepcopy(fixture_receipt())
    if damage == "empty":
        receipt["runs"] = []
    elif damage == "one_phase":
        receipt["runs"].pop()
    elif damage == "duplicate_phase":
        receipt["runs"][1]["phase"] = "preview"
    elif damage == "job_missing":
        receipt.pop("job_id")
    elif damage == "unsafe_id":
        receipt["runs"][0]["doc_id"] = "../wrong"
    elif damage == "bad_hash":
        receipt["runs"][0]["reviewed_export_sha256"] = "invalid"
    elif damage == "unreviewed":
        receipt["runs"][0]["review_revision"] = 0
    elif damage == "export_failed":
        receipt["runs"][0]["reviewed_json_status"] = 500
    else:
        receipt["batch_jsonl_line_count"] = 0
    cfg, fixture, output = inputs(tmp_path, receipt)
    cfg.unlink()
    monkeypatch.setattr(owner.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("HTTP before valid fixture"))
    with pytest.raises(AssertionError):
        owner.verify(cfg, fixture, output)
    assert not output.exists()


def test_unexpected_account_role_is_recorded_and_disabled(tmp_path, monkeypatch):
    http = HttpFixture("role")
    args = inputs(tmp_path, fixture_receipt())
    monkeypatch.setattr(owner.urllib.request, "urlopen", http)
    with pytest.raises(AssertionError, match="must be a viewer"):
        owner.verify(*args)
    report = json.loads((args[2] / "result.json").read_text())
    assert report["created_viewer_ids"] == report["disabled_viewer_ids"] == http.accounts == http.disabled == ["1"]
    assert report["status"] == "failed"
