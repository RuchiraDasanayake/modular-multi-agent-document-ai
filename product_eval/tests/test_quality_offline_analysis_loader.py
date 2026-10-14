"""Offline-loader isolation using synthetic registrations, never reserved data."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/quality240_offline_analysis.py"
spec = importlib.util.spec_from_file_location("offline_loader_test_target", SCRIPT)
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


@pytest.fixture
def registered(tmp_path):
    """Real package code under a synthetic hash registration and separate root."""
    frozen, run = tmp_path / "frozen", tmp_path / "campaign"
    hashes = {}
    for package in ("idpo", "product_eval"):
        for source in (ROOT / package).rglob("*.py"):
            name = source.relative_to(ROOT).as_posix()
            if name in loader.ANALYSIS_MODULES:
                continue
            raw = source.read_bytes()
            if name == "idpo/product_auto/logic.py":
                raw += b"\n# Synthetic frozen source marker; differs from the current checkout.\n"
            target = frozen / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            hashes[name] = loader.digest(raw)
    run.mkdir()
    protocol = {"version": 1, "mode": "paired_quality240", "labels_opened": False,
                "code": {"commit": "a" * 40, "python_source_sha256": hashes}}
    sha = loader.write_new(run / "protocol.json", loader.encoded(protocol))
    return SimpleNamespace(frozen=frozen, run=run, sha=sha, root=tmp_path / "analysis", protocol=protocol)


def stage(registered):
    return loader.prepare(registered.frozen, registered.run, registered.sha, registered.root)["analysis_tree_sha256"]


def cli(registered, sha, action="preflight", *extra):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), action,
        "--run", str(registered.run), "--analysis-root", str(registered.root),
        "--protocol-sha256", registered.sha, "--analysis-sha256", sha, *extra],
        capture_output=True, text=True, timeout=30, check=False)


def test_registered_stage_passes_original_guard_with_exact_raw_bytes_and_no_labels(registered):
    sha = stage(registered)
    result = cli(registered, sha)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert len(receipt["verified_frozen_modules"]) == 14
    assert {item["comparison"] for item in receipt["verified_frozen_modules"].values()} == {"exact_bytes"}
    assert receipt["labels_opened"] is False and receipt["prediction_contents_read"] is False
    assert receipt["model_calls"] == 0
    expected = registered.protocol["code"]["python_source_sha256"]["idpo/product_auto/logic.py"]
    assert loader.digest((ROOT / "idpo/product_auto/logic.py").read_bytes()) != expected
    assert loader.digest((registered.root / "idpo/product_auto/logic.py").read_bytes()) == expected
    # Imports cannot leave unregistered bytecode artifacts behind.
    loader.validate_tree(registered.root, sha, registered.run, registered.sha)


def test_changed_product_checkout_rejected_before_creating_analysis_tree(registered):
    (registered.frozen / "idpo/product_auto/logic.py").write_bytes((ROOT / "idpo/product_auto/logic.py").read_bytes())
    with pytest.raises(ValueError, match="Frozen source bytes differ"):
        stage(registered)
    assert not registered.root.exists()


@pytest.mark.parametrize("damage", ["missing", "extra", "wrong_root"])
def test_unregistered_frozen_tree_rejected(registered, damage):
    if damage == "missing":
        (registered.frozen / "idpo/product_auto/logic.py").unlink()
    elif damage == "extra":
        (registered.frozen / "idpo/unregistered.py").write_text("raise RuntimeError('must not import')")
    else:
        registered.frozen = registered.run
    with pytest.raises(ValueError, match="missing or additional"):
        stage(registered)
    assert not registered.root.exists()


def test_analysis_overlay_cannot_replace_a_registered_product_source(registered):
    name = loader.ANALYSIS_MODULES[0]
    registered.protocol["code"]["python_source_sha256"][name] = "0" * 64
    raw = loader.encoded(registered.protocol)
    (registered.run / "protocol.json").write_bytes(raw)
    registered.sha = loader.digest(raw)
    with pytest.raises(ValueError, match="replace a frozen source"):
        stage(registered)


@pytest.mark.parametrize("damage", ["product", "analysis", "extra", "manifest_hash", "protocol_hash", "loader_hash"])
def test_changed_stage_or_registration_fails_before_reference_access(registered, damage):
    sha = stage(registered)
    if damage in {"product", "analysis"}:
        name = "idpo/product_auto/logic.py" if damage == "product" else loader.ANALYSIS_MODULES[0]
        with (registered.root / name).open("ab") as handle:
            handle.write(b"\n# changed\n")
    elif damage == "extra":
        (registered.root / "idpo/unregistered.py").write_text("raise RuntimeError('must not import')")
    elif damage == "manifest_hash":
        sha = "0" * 64
    elif damage == "protocol_hash":
        registered.sha = "0" * 64
    else:
        manifest = loader.read_json(registered.root / loader.MANIFEST)
        manifest["loader_sha256"] = "0" * 64
        raw = loader.encoded(manifest)
        (registered.root / loader.MANIFEST).write_bytes(raw)
        sha = loader.digest(raw)
    result = cli(registered, sha)
    assert result.returncode != 0 and "must not import" not in result.stderr
    assert "Traceback" in result.stderr


def test_importing_current_product_before_isolation_is_refused(registered):
    # pytest has already imported this test's product_eval package.
    with pytest.raises(ValueError, match="before isolation"):
        loader.activate(registered.root)


def test_verify_requires_a_real_seal_and_never_publishes_partial_receipt(registered):
    sha = stage(registered)
    output = registered.root.parent / "verification.json"
    result = cli(registered, sha, "verify", "--prediction-seal-sha256", "0" * 64, "--output", str(output))
    assert result.returncode != 0 and not output.exists()
    assert "prediction-seal.json" in result.stderr


@pytest.mark.parametrize("damage", ["hash", "context", "unsealed_campaign"])
def test_score_requires_independent_verification_and_rechecks_seal_before_labels(registered, damage):
    sha = stage(registered)
    context = {"analysis_tree_sha256": sha, "protocol_sha256": registered.sha,
               "prediction_seal_sha256": "0" * 64, "transport_amendment_sha256": None, "http408_resolution_sha256": []}
    if damage == "context":
        context["protocol_sha256"] = "f" * 64
    receipt = registered.root.parent / "verification.json"
    receipt_sha = loader.write_new(receipt, loader.encoded({"version": 1,
        "type": "quality240_independent_prediction_verification", "context": context,
        "verification": {}, "labels_opened": False}))
    if damage == "hash":
        receipt_sha = "f" * 64
    output = registered.root.parent / "scores"
    result = cli(registered, sha, "score", "--prediction-seal-sha256", "0" * 64, "--output", str(output),
        "--verification-receipt", str(receipt), "--verification-sha256", receipt_sha,
        "--vrdu-root", str(registered.root.parent / "never-opened-vrdu"),
        "--cord-gold", str(registered.root.parent / "never-opened-cord"))
    assert result.returncode != 0 and not output.exists()
    assert "never-opened" not in result.stderr
    expected = {"hash": "receipt hash differs", "context": "context differs", "unsealed_campaign": "prediction-seal.json"}
    assert expected[damage] in result.stderr
