from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
from pathlib import Path

import pytest

from product_eval.run_gate import run_gate

gate_module = importlib.import_module("product_eval.run_gate")


def _gold_record(path: Path, value: str) -> dict[str, object]:
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    doc_id = hashlib.sha256(f"{path.name}\0{source_hash}\0{0}".encode()).hexdigest()[:32]
    return {
        "contract_version": 1,
        "doc_id": doc_id,
        "pages": [{"page": 1, "text": path.read_text(encoding="utf-8").strip()}],
        "gold_schema": [{"field_id": "invoice", "type": "string", "critical": False}],
        "gold_values": [{"field_id": "invoice", "value": value}],
    }


def test_gate_runs_distinct_shards_and_scores_only_after_source_verification(tmp_path: Path) -> None:
    shards = [tmp_path / "shard_a", tmp_path / "shard_b"]
    records = []
    for shard, value in zip(shards, ("A-1", "B-2")):
        shard.mkdir()
        source = shard / "invoice.txt"
        source.write_text(f"Invoice: {value}\n", encoding="utf-8")
        records.append(_gold_record(source, value))
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    cohort_path = tmp_path / "cohort.jsonl"
    cohort_path.write_text("".join(
        json.dumps({"doc_id": record["doc_id"], "family": shard.name,
                    "source_sha256": hashlib.sha256((shard / "invoice.txt").read_bytes()).hexdigest()}) + "\n"
        for shard, record in zip(shards, records)
    ), encoding="utf-8")

    data_dir = tmp_path / "data"
    report_dir = tmp_path / "report"
    result = run_gate(
        shards, gold_path=gold_path, cohort_path=cohort_path, data_dir=data_dir, report_dir=report_dir,
        gate_id="small_gate", min_unique=2, max_workers=2,
    )

    assert result["execution"]["documents"] == 2
    assert result["execution"]["distinct_sources"] == 2
    assert result["execution"]["source_hashes_verified"] is True
    assert result["quality"]["schema"]["tp"] == 2
    assert result["provenance"]["model_configured"] is False
    assert result["provenance"]["ocr_required"] is False
    assert result["provenance"]["ocr_preflight"] is None
    family = json.loads((report_dir / "family-report.json").read_text(encoding="utf-8"))
    assert set(family["by_family"]) == {"shard_a", "shard_b"}
    assert len((report_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert len(list(report_dir.glob("small_gate_*.log"))) == 2

    with pytest.raises(ValueError, match="must be new"):
        run_gate(
            shards, gold_path=gold_path, data_dir=data_dir, report_dir=report_dir,
            gate_id="small_gate", min_unique=2,
        )


def test_gate_rejects_repeated_or_unsafe_shards_before_start(tmp_path: Path) -> None:
    shard = tmp_path / "shard"
    shard.mkdir()
    (shard / "source.txt").write_text("x", encoding="utf-8")
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text("{}\n", encoding="utf-8")
    kwargs = {"gold_path": gold_path, "data_dir": tmp_path / "data", "report_dir": tmp_path / "report"}

    with pytest.raises(ValueError, match="distinct"):
        run_gate([shard, shard], gate_id="repeat", **kwargs)
    with pytest.raises(ValueError, match="gate_id must be safe"):
        run_gate([shard], gate_id="bad id", **kwargs)
    assert not (tmp_path / "report").exists()


def test_image_gate_rejects_missing_ocr_before_creating_run_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    shard = tmp_path / "shard"
    shard.mkdir()
    (shard / "scan.png").write_bytes(b"not parsed before preflight")
    gold = tmp_path / "gold.jsonl"
    gold.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(gate_module, "find_tesseract_cmd", lambda: None)

    with pytest.raises(ValueError, match="Tesseract is unavailable"):
        run_gate(
            [shard], gold_path=gold, data_dir=tmp_path / "data", report_dir=tmp_path / "report",
            gate_id="image_gate", min_unique=1,
        )
    assert not (tmp_path / "report").exists()
    assert not (tmp_path / "data").exists()


def test_ocr_preflight_smokes_english_and_records_traineddata_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytesseract = pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"fake executable")
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    traineddata = tessdata / "eng.traineddata"
    traineddata.write_bytes(b"fake English language data")
    monkeypatch.setenv("TESSDATA_PREFIX", str(tessdata))
    monkeypatch.setattr(gate_module, "find_tesseract_cmd", lambda: str(executable))
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *args, **kwargs: "DOCUMENT OCR 12345\n")

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[1] == "--version":
            return subprocess.CompletedProcess(args, 0, "tesseract 5.5.3\n", "")
        assert args == [str(executable), "--list-langs", "--tessdata-dir", str(tessdata)]
        return subprocess.CompletedProcess(args, 0, f'List of available languages in "{tessdata}" (1):\neng\n', "")

    monkeypatch.setattr(gate_module.subprocess, "run", fake_run)
    previous_command = pytesseract.pytesseract.tesseract_cmd
    result = gate_module._preflight_ocr()

    assert result["tesseract_executable"] == str(executable)
    assert result["tesseract_version"] == "tesseract 5.5.3"
    assert result["eng_traineddata_sha256"] == hashlib.sha256(traineddata.read_bytes()).hexdigest()
    assert result["ocr_smoke_passed"] is True
    assert pytesseract.pytesseract.tesseract_cmd == previous_command

    monkeypatch.setattr(pytesseract, "image_to_string", lambda *args, **kwargs: "")
    with pytest.raises(ValueError, match="no recognizable text"):
        gate_module._preflight_ocr()
    assert pytesseract.pytesseract.tesseract_cmd == previous_command


def test_ocr_shard_uses_preflighted_executable_and_traineddata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    shard = tmp_path / "shard"
    shard.mkdir()
    report = tmp_path / "report"
    report.mkdir()
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(gate_module.subprocess, "run", fake_run)
    monkeypatch.setenv("ICORE_API_KEY", "test-key")
    result = gate_module._run_shard(
        shard, "image_gate", tmp_path / "data", report, tmp_path,
        {"tesseract_executable": "C:/tools/tesseract.exe", "tessdata_dir": "C:/tools/tessdata"},
    )

    environment = captured["env"]
    assert result == 0
    assert environment["TESSERACT_CMD"] == "C:/tools/tesseract.exe"
    assert environment["TESSDATA_PREFIX"] == "C:/tools/tessdata"
    assert "ICORE_API_KEY" not in environment
