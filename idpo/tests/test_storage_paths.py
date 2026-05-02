from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from idpo.cli import main as cli_main
from idpo.core.storage import benchmark_reports_dir, default_data_root, migrate_legacy_runtime_data, repo_root, runs_root
from idpo.pipeline.inbox import process_inbox
from idpo.pipeline.orchestrator import Pipeline


def test_default_data_root_is_outside_repo_root() -> None:
    repo = repo_root().resolve()
    data = default_data_root().resolve()
    assert data != repo
    assert not data.is_relative_to(repo)


def test_pipeline_default_run_dir_uses_idpo_data_dir(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "idpo-data"
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))

    pipeline = Pipeline()

    assert pipeline.base_run_dir.parent == runs_root()
    assert pipeline.base_run_dir.parent == runtime_root / "runs"


def test_benchmark_reports_dir_uses_idpo_data_dir(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "idpo-data"
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))

    assert benchmark_reports_dir() == runtime_root / "runs" / "benchmarks"


def test_process_inbox_writes_runtime_state_under_data_root(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "idpo-data"
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))

    doc_path = workspace / "invoice.txt"
    doc_path.write_text("Invoice Number: INV-1\nTotal Amount: 10.00\n", encoding="utf-8")

    result = process_inbox(root=workspace, file_paths=[str(doc_path)])

    assert Path(result["run_dir"]).is_relative_to(runtime_root)
    assert (runtime_root / "inputs" / "processed" / "invoice.txt").exists()


def test_cli_process_inbox_accepts_input_dir(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "idpo-data"
    input_dir = tmp_path / "uploads"
    input_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))

    (input_dir / "invoice.txt").write_text("Invoice Number: INV-2\nTotal Amount: 25.00\n", encoding="utf-8")

    stdout = StringIO()
    monkeypatch.setattr(
        "sys.argv",
        [
            "idpo",
            "process-inbox",
            "--root",
            str(tmp_path),
            "--input-dir",
            str(input_dir),
        ],
    )
    with redirect_stdout(stdout):
        cli_main()

    payload = json.loads(stdout.getvalue())
    assert Path(payload["run_dir"]).is_relative_to(runtime_root)
    assert (runtime_root / "inputs" / "processed" / "invoice.txt").exists()


def test_cli_process_inbox_accepts_run_id_fields_file_and_full_output(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "idpo-data"
    input_dir = tmp_path / "uploads"
    input_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))

    (input_dir / "invoice.txt").write_text("Invoice Number: INV-3\nTotal Amount: 25.00\n", encoding="utf-8")
    fields_path = tmp_path / "fields.json"
    fields_path.write_text(
        json.dumps(
            [
                {"name": "invoice_number", "description": "Invoice identifier"},
                {"name": "total_amount", "description": "Total due amount"},
            ]
        ),
        encoding="utf-8",
    )

    stdout = StringIO()
    monkeypatch.setattr(
        "sys.argv",
        [
            "idpo",
            "process-inbox",
            "--root",
            str(tmp_path),
            "--input-dir",
            str(input_dir),
            "--run-id",
            "cli-run-1",
            "--fields-file",
            str(fields_path),
            "--output-mode",
            "full",
        ],
    )
    with redirect_stdout(stdout):
        cli_main()

    payload = json.loads(stdout.getvalue())
    assert payload["run_id"] == "cli-run-1"
    assert Path(payload["run_dir"]).name == "cli-run-1"
    assert payload["doc_records"][0]["structured_fields"]["invoice_number"] != ""


def test_process_inbox_persists_semantic_doc_type_in_doc_record_and_dae_output(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "idpo-data"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))

    doc_path = workspace / "receipt.txt"
    doc_path.write_text(
        "Invoice Number: INV-9\n"
        "Total Amount: $25.00\n"
        "Cash: $30.00\n"
        "2 x 12.50\n",
        encoding="utf-8",
    )

    result = process_inbox(root=workspace, file_paths=[str(doc_path)])

    doc_record = result["doc_records"][0]
    assert doc_record["semantic_doc_type"] == "receipt"

    dae_output = json.loads(Path(doc_record["dae_output_path"]).read_text(encoding="utf-8"))
    assert dae_output["semantic_doc_type"] == "receipt"


def test_migrate_storage_moves_runs_and_runtime_inputs(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy-repo"
    data_root = tmp_path / "idpo-data"

    (legacy_root / "runs" / "run-a").mkdir(parents=True, exist_ok=True)
    (legacy_root / "runs" / "run-a" / "results.json").write_text("{}", encoding="utf-8")

    (legacy_root / "inputs" / "processed").mkdir(parents=True, exist_ok=True)
    (legacy_root / "inputs" / "processed" / "done.txt").write_text("done", encoding="utf-8")

    (legacy_root / "inputs" / "failed").mkdir(parents=True, exist_ok=True)
    (legacy_root / "inputs" / "failed" / "bad.txt").write_text("bad", encoding="utf-8")

    (legacy_root / "inputs" / "inbox").mkdir(parents=True, exist_ok=True)
    (legacy_root / "inputs" / "inbox" / "keep.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    payload = migrate_legacy_runtime_data(source_repo_root=legacy_root, target_data_root=data_root)

    assert payload["moved_runs"] == ["run-a"]
    assert sorted(payload["moved_inputs"]) == ["failed/bad.txt", "inbox/keep.csv", "processed/done.txt"]
    assert (data_root / "runs" / "run-a" / "results.json").exists()
    assert (data_root / "inputs" / "inbox" / "keep.csv").exists()
    assert (data_root / "inputs" / "processed" / "done.txt").exists()
    assert (data_root / "inputs" / "failed" / "bad.txt").exists()
    assert not (legacy_root / "inputs" / "inbox" / "keep.csv").exists()
