from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import importlib
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_recovery_files as recovery
import native_recovery_http as readback


JOB = "a" * 32


@pytest.fixture
def source(tmp_path, monkeypatch):
    pg, data, repo, clone_repo = [tmp_path / name for name in ("pg", "data", "repo", "clone-repo")]
    for path in (pg, data, repo, clone_repo):
        path.mkdir()
    for name in ("base", "global", "pg_wal", "pg_xact", "pg_tblspc"):
        (pg / name).mkdir()
    (pg / "PG_VERSION").write_text("16\n")
    (pg / "global" / "pg_control").write_bytes(b"fixture control only")
    (pg / "pg_wal" / "wal-segment").write_bytes(b"full WAL included")
    (pg / "postgresql.conf").write_text("# no external config\nshared_buffers = '128MB'\n")
    upload = data / "frontend" / "uploads" / f"job_{JOB}"
    upload.mkdir(parents=True)
    (upload / "source.pdf").write_bytes(b"fixture original document bytes")
    jobs = data / "frontend" / "jobs"
    jobs.mkdir()
    recovery.write_new(jobs / f"{JOB}.json", {"jobId": JOB, "uploadsPath": str(upload), "runPath": None,
        "runs": [], "documents": [{"fileId": "doc1", "storedName": "source.pdf"}]})
    results = data / "product_runs" / "run1"
    results.mkdir(parents=True)
    (results / "sealed.json").write_text(json.dumps({"source_path": str(upload / "source.pdf"), "value": "preserve"}))
    (data / "empty").mkdir()
    config = {"pgData": str(pg), "dataDir": str(data), "repoRoot": str(repo),
        "postgresPort": 55432, "gatewayPort": 8000, "frontendPort": 3000,
        "databaseUrl": "postgresql://fixture:password@127.0.0.1:55432/docai",
        "jwtSecret": "original session secret", "adminPassword": "fixture-password-only",
        "icoreApiKey": "DO-NOT-COPY-TO-CLONE", "autoModel": "provider-model"}
    config_path = tmp_path / "native.json"
    recovery.write_new(config_path, config)
    monkeypatch.setattr(recovery, "code_revision", lambda _: "1" * 40)
    return {"pg": pg, "data": data, "config": config_path, "clone_repo": clone_repo, "root": tmp_path}


def noop(*_args):
    pass


def make_backup(source):
    bundle = source["root"] / "bundle"
    recovery.backup(source["config"], bundle, check=noop, create=lambda p: p.mkdir())
    return bundle


def restore(source, bundle):
    destination = source["root"] / "restored"
    recovery.restore(bundle, destination, source["clone_repo"], (55433, 8001, 3001),
                     check=noop, create=lambda p: p.mkdir())
    return destination


def test_full_round_trip_preserves_all_nonrelocated_bytes_and_rotates_secret(source):
    before = recovery.inventory(source["data"])
    bundle = make_backup(source)
    clone = restore(source, bundle)
    assert recovery.inventory(source["data"]) == before
    assert recovery.inventory(clone / "pgdata") == recovery.inventory(source["pg"])
    result = clone / "data/product_runs/run1/sealed.json"
    assert result.read_bytes() == (source["data"] / "product_runs/run1/sealed.json").read_bytes()
    job = recovery.read_json(clone / f"data/frontend/jobs/{JOB}.json")
    assert job["uploadsPath"] == str(clone / f"data/frontend/uploads/job_{JOB}")
    config = recovery.read_json(clone / "passive-config.json")
    assert "icoreApiKey" not in config and "autoModel" not in config
    assert config["jwtSecret"] != "original session secret"
    assert config["databaseUrl"].endswith("127.0.0.1:55433/docai")
    receipt = recovery.read_json(clone / "restore-receipt.json")
    assert len(receipt["relocations"]) == 1
    assert "DO-NOT-COPY" not in json.dumps(receipt)
    assert recovery.verify_restore(clone, check=noop)["verified"]
    with pytest.raises(FileExistsError):
        recovery.restore(bundle, clone, source["clone_repo"], (55433, 8001, 3001), check=noop, create=lambda p: p.mkdir())


@pytest.mark.parametrize("tamper", ["change", "extra", "missing-empty-directory", "missing-seal"])
def test_backup_verification_refuses_tampering(source, tamper):
    bundle = make_backup(source)
    if tamper == "change":
        (bundle / "pgdata/global/pg_control").write_bytes(b"changed")
    elif tamper == "extra":
        (bundle / "data/unlisted").write_bytes(b"extra")
    elif tamper == "missing-empty-directory":
        (bundle / "data/empty").rmdir()
    else:
        (bundle / "seal.json").unlink()
    with pytest.raises(recovery.RecoveryError):
        recovery.verify_bundle(bundle, check=noop)


def test_source_change_during_copy_leaves_unsealed_partial_destination(source):
    calls = 0
    def check(action, _):
        nonlocal calls
        if action == "Stopped":
            calls += 1
            if calls == 2:
                (source["data"] / "changed").write_bytes(b"writer escaped the cold-stop window")
    destination = source["root"] / "partial"
    with pytest.raises(recovery.RecoveryError, match="changed"):
        recovery.backup(source["config"], destination, check=check, create=lambda p: p.mkdir())
    assert destination.exists() and not (destination / "seal.json").exists()


def test_stop_failure_never_creates_destination(source):
    def check(action, _):
        if action == "Stopped":
            raise recovery.RecoveryError("still running")
    destination = source["root"] / "none"
    with pytest.raises(recovery.RecoveryError):
        recovery.backup(source["config"], destination, check=check, create=lambda p: p.mkdir())
    assert not destination.exists()


@pytest.mark.parametrize("case", ["pid", "tablespace", "config-include", "external-log", "standby", "wrong-version"])
def test_cluster_scope_fails_closed(source, case):
    if case == "pid":
        (source["pg"] / "postmaster.pid").write_text("123")
    elif case == "tablespace":
        (source["pg"] / "pg_tblspc/123").mkdir()
    elif case == "config-include":
        (source["pg"] / "postgresql.auto.conf").write_text("include 'elsewhere.conf'\n")
    elif case == "external-log":
        (source["pg"] / "postgresql.conf").write_text("log_directory = 'outside'\n")
    elif case == "standby":
        (source["pg"] / "standby.signal").touch()
    else:
        (source["pg"] / "PG_VERSION").write_text("17")
    with pytest.raises(recovery.RecoveryError):
        make_backup(source)


def test_overlap_and_hardlink_refused(source):
    with pytest.raises(recovery.RecoveryError, match="overlap"):
        recovery.backup(source["config"], source["data"] / "backup", check=noop, create=lambda p: p.mkdir())
    os.link(source["data"] / "product_runs/run1/sealed.json", source["data"] / "hardlink.json")
    with pytest.raises(recovery.RecoveryError, match="hardlinks"):
        make_backup(source)


@pytest.mark.parametrize("field,value", [("uploadsPath", "C:/original-or-other-data"), ("jobId", "wrong"), ("runPath", "C:/legacy/run")])
def test_unsupported_job_paths_fail_without_rewriting_source(source, field, value):
    path = source["data"] / f"frontend/jobs/{JOB}.json"
    record = recovery.read_json(path)
    record[field] = value
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    bundle = make_backup(source)
    with pytest.raises(recovery.RecoveryError):
        restore(source, bundle)
    assert path.read_bytes() == before
    assert (bundle / f"data/frontend/jobs/{JOB}.json").read_bytes() == before
    assert not (source["root"] / "restored/restore-receipt.json").exists()


def test_original_ports_and_source_revision_mismatch_are_refused(source, monkeypatch):
    bundle = make_backup(source)
    with pytest.raises(recovery.RecoveryError, match="ports"):
        recovery.restore(bundle, source["root"] / "clone", source["clone_repo"], (55432, 8001, 3001), check=noop)
    monkeypatch.setattr(recovery, "code_revision", lambda _: "2" * 40)
    with pytest.raises(recovery.RecoveryError, match="revision"):
        restore(source, bundle)


def test_first_start_private_audit_does_not_traverse_required_build_junction(source):
    clone = restore(source, make_backup(source))
    (clone / "frontend-build").mkdir()
    seen = []
    recovery.verify_restore(clone, check=lambda action, path: seen.append((action, path)))
    assert ("Private", clone) in seen
    assert ("PrivateTree", clone / "data") in seen
    assert not any(path == clone / "frontend-build" or (action == "PrivateTree" and path == clone) for action, path in seen)


def test_http_readback_requires_anonymous_denial_auth_and_exact_local_source(source):
    config = recovery.read_json(source["config"])
    config["recoveryPassive"] = True
    config["frontendPort"] = 3001
    case = {"job_id": JOB, "document_id": "doc1", "run_id": "run1",
            "source_relative_path": f"frontend/uploads/job_{JOB}/source.pdf"}
    calls = []
    def http(base, path, *, token=None, login=None):
        calls.append((base, path, bool(token), bool(login)))
        if login:
            return 200, b'{"access_token":"private-token"}', "read-only"
        if not token:
            return 401, b"", "read-only"
        if path.endswith("/content"):
            return 200, (source["data"] / case["source_relative_path"]).read_bytes(), "read-only"
        return 200, b'{"human_verified":true}\n', "read-only"
    outcomes = readback.readback(config, [case], http=http)
    assert len(calls) == 5 and all(call[0] == "http://127.0.0.1:3001" for call in calls)
    assert "private-token" not in json.dumps(outcomes)
    assert outcomes[0]["anonymous_status"] == 401
    with pytest.raises(recovery.RecoveryError, match="passive"):
        readback.readback(config, [case], http=lambda *args, **kwargs: (401, b"", ""))
    with pytest.raises(recovery.RecoveryError, match="401"):
        readback.readback(config, [case], http=lambda *args, **kwargs: (200, b"wrong", "read-only"))


@pytest.mark.parametrize("relative", ["../source.pdf", f"frontend/uploads/job_{JOB}/../source.pdf", "C:/source.pdf"])
def test_http_protocol_rejects_path_escape(relative):
    with pytest.raises(recovery.RecoveryError):
        readback.checked_case({"job_id": JOB, "document_id": "doc1", "run_id": "run1", "source_relative_path": relative})


@pytest.mark.parametrize("line", ['include "C:/not-copied/auth.conf"',
    "host all @C:/not-copied/users 127.0.0.1/32 scram-sha-256",
    "host all person,@C:/not-copied/users 127.0.0.1/32 scram-sha-256"])
def test_external_auth_configuration_is_rejected(source, line):
    (source["pg"] / "pg_hba.conf").write_text("# include 'ignored.conf'\n" + line + "\n")
    with pytest.raises(recovery.RecoveryError, match="authentication"):
        make_backup(source)


def test_auth_comments_do_not_create_false_external_dependency(source):
    (source["pg"] / "pg_hba.conf").write_text("# include 'ignored.conf'\nhost all all 127.0.0.1/32 scram-sha-256 # @ignored\n")
    make_backup(source)


def test_passive_gateway_refuses_model_and_auth_mutations_without_calling_application(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    reached = []
    @app.api_route("/{path:path}", methods=["GET", "POST", "DELETE"])
    async def downstream(path: str):
        reached.append(path)
        return {"ok": True}
    monkeypatch.setitem(sys.modules, "gateway.main", types.SimpleNamespace(app=app))
    sys.modules.pop("native_recovery_gateway", None)
    boundary = importlib.import_module("native_recovery_gateway")
    try:
        with TestClient(boundary.app) as client:
            for method, path in [("POST", "/api/idpo/process"), ("GET", "/api/services"),
                ("POST", "/api/auth/register"), ("GET", "/health?redirect=1")]:
                assert client.request(method, path).status_code == 423
            assert reached == []
            assert client.post("/api/auth/login", json={}).status_code == 200
            assert client.get("/api/auth/me").headers["X-DocAI-Recovery"] == "read-only"
            assert reached == ["api/auth/login", "api/auth/me"]
    finally:
        sys.modules.pop("native_recovery_gateway", None)
