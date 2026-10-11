"""Boundary checks for the Docker product worker request."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from idpo.product_auto.worker_server import validate_request


def staged_run(tmp_path: Path) -> tuple[str, Path]:
    run_id = "auto_" + "a" * 32
    staged = tmp_path / "frontend" / "auto_inputs" / run_id
    staged.mkdir(parents=True)
    (staged / "invoice.txt").write_text("Invoice 123", encoding="utf-8")
    return run_id, staged


def test_worker_accepts_only_matching_staged_run(tmp_path: Path) -> None:
    run_id, staged = staged_run(tmp_path)
    assert validate_request({"run_id": run_id, "input_dir": str(staged)}, root=tmp_path) == (
        staged, run_id, None, None,
    )

    with pytest.raises(ValueError, match="staging area"):
        validate_request({"run_id": "auto_" + "b" * 32, "input_dir": str(staged)}, root=tmp_path)
    with pytest.raises(ValueError, match="staging area"):
        validate_request({"run_id": run_id, "input_dir": str(tmp_path)}, root=tmp_path)


def test_worker_rejects_invalid_model_pair_and_existing_run(tmp_path: Path) -> None:
    run_id, staged = staged_run(tmp_path)
    with pytest.raises(ValueError, match="together"):
        validate_request({"run_id": run_id, "input_dir": str(staged), "model": "test"}, root=tmp_path)
    (tmp_path / "product_runs" / run_id).mkdir(parents=True)
    with pytest.raises(ValueError, match="already exists"):
        validate_request({"run_id": run_id, "input_dir": str(staged)}, root=tmp_path)


def test_worker_rejects_non_file_entries_and_missing_input(tmp_path: Path) -> None:
    run_id, staged = staged_run(tmp_path)
    (staged / "nested").mkdir()
    with pytest.raises(ValueError, match="invalid entry"):
        validate_request({"run_id": run_id, "input_dir": str(staged)}, root=tmp_path)
    with pytest.raises((FileNotFoundError, ValueError)):
        validate_request({"run_id": run_id, "input_dir": str(staged / "missing")}, root=tmp_path)


def test_worker_request_contract_is_json_safe(tmp_path: Path) -> None:
    run_id, staged = staged_run(tmp_path)
    payload = json.loads(json.dumps({"run_id": run_id, "input_dir": str(staged)}))
    assert validate_request(payload, root=tmp_path)[1] == run_id
