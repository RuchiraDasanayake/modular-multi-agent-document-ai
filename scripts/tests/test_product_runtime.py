"""Offline runtime capability classification and redaction regressions."""
from __future__ import annotations

import contextlib
import json
import os
import sys
import types
from pathlib import Path

import pytest

from scripts import check_product_runtime as runtime


def ready_checks(**changes: bool) -> list[dict[str, object]]:
    return [{"id": name, "ready": changes.get(name, True)} for name in runtime.REMEDIES]


def test_optional_rapidocr_is_only_probed_when_explicit_and_failure_blocks_readiness(monkeypatch):
    probes = []
    def check(check_id, _probe):
        probes.append(check_id)
        return {"id": check_id, "ready": check_id != "rapidocr_ocr", "code": "fixture"}
    monkeypatch.setattr(runtime, "run_check", check)
    monkeypatch.delenv("IDPO_AUTO_MODEL", raising=False)
    monkeypatch.delenv("IDPO_AUTO_API_BASE_URL", raising=False)
    default = runtime.check_runtime()
    assert "rapidocr_ocr" not in probes and "optional_ocr" not in default
    assert default["status"] == "ready"
    selected = runtime.check_runtime("rapidocr")
    assert probes.count("rapidocr_ocr") == 1
    assert selected["optional_ocr"]["ready"] is False
    assert selected["status"] == "unavailable"
    assert "tesseract_ocr" in probes and "scan_sample" in probes


def test_missing_pdf_reader_is_not_masked_by_a_working_rasterizer(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "native.pdf"
    runtime._write_pdf(pdf)
    monkeypatch.setitem(sys.modules, "pypdf", None)
    result = runtime.run_check("pdf_native", lambda: runtime._pdf_probe(pdf))
    assert result["ready"] is False
    report = runtime.build_report(ready_checks(pdf_native=False), {})
    assert report["status"] == "unavailable"
    assert report["capabilities"]["pdf_native_text"]["ready"] is False
    assert report["capabilities"]["pdf_scan_extraction"]["ready"] is False
    assert report["capabilities"]["text_json"]["ready"] is True


def test_poppler_extraction_fallback_does_not_advertise_pdfium_schema_sampling() -> None:
    report = runtime.build_report(ready_checks(pdfium=False, scan_sample=False), {})
    assert report["capabilities"]["pdf_scan_extraction"]["ready"] is True
    assert report["capabilities"]["pdf_scan_schema_sampling"]["ready"] is False
    assert report["status"] == "unavailable"


def test_importable_but_broken_native_library_is_unavailable_and_redacted(tmp_path: Path, monkeypatch) -> None:
    secret = "private-document-or-credential-value"

    def broken_document(_):
        print(secret)
        print(secret, file=sys.stderr)
        raise OSError(secret)

    monkeypatch.setitem(sys.modules, "pypdfium2", types.SimpleNamespace(PdfDocument=broken_document))
    result = runtime.run_check("pdfium", lambda: runtime._pdfium_probe(tmp_path / "probe.pdf"))
    assert result["ready"] is False
    assert secret not in json.dumps(result)


def test_existing_ocr_executable_does_not_pass_when_bounded_ocr_fails(tmp_path: Path, monkeypatch) -> None:
    from idpo.core import preflight

    executable = tmp_path / "fake-tesseract.exe"
    executable.touch()
    monkeypatch.setenv("TESSERACT_CMD", str(executable))
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    monkeypatch.setattr(preflight, "find_tesseract_cmd", lambda: str(executable))
    monkeypatch.setattr(runtime, "_image_fixture", lambda: contextlib.nullcontext(object()))
    attempts = []

    def broken_ocr(*args, **kwargs):
        attempts.append(kwargs)
        raise RuntimeError("OCR timed out: private path or content")

    monkeypatch.setitem(sys.modules, "pytesseract", types.SimpleNamespace(
        pytesseract=types.SimpleNamespace(tesseract_cmd=""), image_to_string=broken_ocr))
    result = runtime.run_check("tesseract_ocr", runtime._ocr_probe)
    assert result["ready"] is False
    assert len(attempts) == 1 and attempts[0]["timeout"] == 10
    assert "private path" not in json.dumps(result)


def test_native_office_failure_does_not_hide_other_format_availability() -> None:
    report = runtime.build_report(ready_checks(docx=False), {})
    assert report["status"] == "unavailable"
    assert report["capabilities"]["docx"]["missing_checks"] == ["docx"]
    assert report["capabilities"]["xlsx"]["ready"] is True


@pytest.mark.parametrize("environment,client_ready,state,valid", [
    ({}, False, "not_configured", True),
    ({"IDPO_AUTO_MODEL": "fixture"}, True, "unavailable", False),
    ({"IDPO_AUTO_MODEL": "fixture", "IDPO_AUTO_API_BASE_URL": "http://127.0.0.1:1/v1"}, True, "configured_unverified", True),
    ({"IDPO_AUTO_MODEL": "fixture", "IDPO_AUTO_API_BASE_URL": "http://remote.invalid/v1"}, True, "unavailable", False),
    ({"IDPO_AUTO_MODEL": "fixture", "IDPO_AUTO_API_BASE_URL": "https://cloud.invalid/v1"}, True, "unavailable", False),
    ({"IDPO_AUTO_MODEL": "fixture", "IDPO_AUTO_API_BASE_URL": "https://cloud.invalid/v1", "ICORE_API_KEY": "private-key"}, False, "unavailable", False),
    ({"IDPO_AUTO_MODEL": "fixture", "IDPO_AUTO_API_BASE_URL": "https://cloud.invalid/v1", "ICORE_API_KEY": "private-key"}, True, "configured_unverified", True),
    ({"IDPO_AUTO_MODEL": "fixture", "IDPO_AUTO_API_BASE_URL": "https://user:private-key@cloud.invalid/v1"}, True, "unavailable", False),
])
def test_model_configuration_is_optional_but_never_claims_endpoint_health(environment, client_ready, state, valid) -> None:
    report = runtime.provider_report(client_ready, environment)
    assert report["state"] == state
    assert report["configuration_valid"] is valid
    assert report["network_checked"] is False
    assert "private-key" not in json.dumps(report)
    assert "cloud.invalid" not in json.dumps(report)
    assert "fixture" not in json.dumps(report)


def test_model_disabled_needs_no_client_but_configured_model_requires_one() -> None:
    assert runtime.build_report(ready_checks(model_client=False), {})["status"] == "ready"
    environment = {"IDPO_AUTO_MODEL": "fixture", "IDPO_AUTO_API_BASE_URL": "http://localhost:1/v1"}
    assert runtime.build_report(ready_checks(model_client=False), environment)["status"] == "unavailable"


def test_private_config_uses_selected_runtime_and_restores_environment(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "native.json"
    source.write_text(json.dumps({"pythonPath": sys.executable, "icoreApiKey": "new-private-key",
                                  "autoModel": "fixture", "tesseractPath": "test-tesseract"}))
    monkeypatch.setenv("ICORE_API_KEY", "old-private-key")
    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    with pytest.raises(RuntimeError):
        with runtime.native_environment(source):
            assert os.environ["ICORE_API_KEY"] == "new-private-key"
            assert os.environ["TESSERACT_CMD"] == "test-tesseract"
            raise RuntimeError("probe failed")
    assert os.environ["ICORE_API_KEY"] == "old-private-key"
    assert "TESSERACT_CMD" not in os.environ


def test_wrong_interpreter_cannot_certify_the_configured_runtime(tmp_path: Path, capsys) -> None:
    source = tmp_path / "native.json"
    source.write_text(json.dumps({"pythonPath": str(tmp_path / "other-python"), "icoreApiKey": "private-key"}))
    assert runtime.main(["--json", "--native-config", str(source)]) == 1
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["code"] == "wrong_python_runtime"
    assert "private-key" not in output


def test_private_rapidocr_settings_are_bounded_and_restored(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "native.json"
    settings = {"pythonPath": sys.executable, "rapidOcrPythonPath": "fixture-python",
                "rapidOcrWorkDir": "fixture-scratch", "rapidOcrTimeoutSeconds": 90, "rapidOcrMaxRssMiB": 1024}
    source.write_text(json.dumps(settings))
    monkeypatch.setenv("IDPO_RAPIDOCR_TIMEOUT_S", "1")
    monkeypatch.delenv("IDPO_RAPIDOCR_PYTHON", raising=False)
    with runtime.native_environment(source):
        assert os.environ["IDPO_RAPIDOCR_PYTHON"] == "fixture-python"
        assert os.environ["IDPO_RAPIDOCR_WORK_DIR"] == "fixture-scratch"
        assert os.environ["IDPO_RAPIDOCR_TIMEOUT_S"] == "90"
        assert os.environ["IDPO_RAPIDOCR_MAX_RSS_MIB"] == "1024"
    assert os.environ["IDPO_RAPIDOCR_TIMEOUT_S"] == "1"
    assert "IDPO_RAPIDOCR_PYTHON" not in os.environ
    for invalid in (0, 181, True, "90", 1.5):
        source.write_text(json.dumps({**settings, "rapidOcrTimeoutSeconds": invalid}))
        with pytest.raises(runtime.ConfigurationError):
            with runtime.native_environment(source):
                pass
        assert os.environ["IDPO_RAPIDOCR_TIMEOUT_S"] == "1"
        assert "IDPO_RAPIDOCR_PYTHON" not in os.environ


def test_invalid_json_is_reported_without_printing_private_config(tmp_path: Path, capsys) -> None:
    source = tmp_path / "native.json"
    source.write_text('{"icoreApiKey":"private-key",broken')
    assert runtime.main(["--json", "--native-config", str(source)]) == 1
    output = capsys.readouterr().out
    assert json.loads(output)["code"] == "invalid_native_config"
    assert "private-key" not in output


def test_cli_fails_when_advertised_format_unavailable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(runtime, "check_runtime", lambda: runtime.build_report(ready_checks(pdf_native=False), {}))
    assert runtime.main(["--json"]) == 1
    assert json.loads(capsys.readouterr().out)["capabilities"]["pdf_native_text"]["ready"] is False
