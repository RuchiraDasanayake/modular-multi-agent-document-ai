"""Local OCR IPC, provenance and resource limits without provider calls."""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from idpo.product_auto import rapid_ocr as adapter
from idpo.product_auto.rapid_ocr_protocol import (
    LINE_SCORE_THRESHOLD, MODEL_SHA256, PROVIDERS, REVISION, RapidOcrError,
    validate_image_size, validate_payload,
)


def _payload():
    return {"schema_version": 1, "status": "ready", "revision": REVISION,
            "input_png_sha256": "0" * 64, "image_size": [200, 100],
            "model_sha256": MODEL_SHA256.copy(), "providers": deepcopy(PROVIDERS),
            "line_score_threshold": LINE_SCORE_THRESHOLD,
            "lines": [{"text": "  TOTAL \u00a320.00  ", "score": 0.95,
                       "polygon": [[1, 1], [150, 1], [150, 20], [1, 20]]},
                      {"text": "emoji \U0001f642", "score": 0.8,
                       "polygon": [[1, 30], [150, 30], [150, 50], [1, 50]]}]}


def _validate(payload):
    return validate_payload(payload, image_size=(200, 100), input_hash="0" * 64)


def test_text_offsets_are_verbatim_unicode_and_polygons_are_not_word_boxes():
    payload = _payload()
    text, lines = _validate(payload)
    assert text == "  TOTAL \u00a320.00  \nemoji \U0001f642"
    for line in lines:
        assert text[line["start"]:line["end"]] == line["text"]
        assert line["polygon"] == payload["lines"][line["line_index"]]["polygon"]


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(input_png_sha256="1" * 64),
    lambda p: p.update(image_size=[100, 200]),
    lambda p: p.update(revision="different"),
    lambda p: p.update(schema_version=True),
    lambda p: p.update(model_sha256={}),
    lambda p: p["providers"].update(text_rec=["CUDAExecutionProvider"]),
    lambda p: p.update(line_score_threshold=0.0),
    lambda p: p["lines"][0].update(score=float("nan")),
    lambda p: p["lines"][0].update(score=True),
    lambda p: p["lines"][0].update(score=0.49),
    lambda p: p["lines"][0].update(text=" "),
    lambda p: p["lines"][0].update(text="private\x00text"),
    lambda p: p["lines"][0].update(polygon=[[0, 0]] * 4),
    lambda p: p["lines"][0].update(polygon=[[0, 0], [20, 20], [20, 0], [0, 20]]),
    lambda p: p["lines"][0]["polygon"][0].__setitem__(0, -0.1),
    lambda p: p["lines"][0]["polygon"][0].__setitem__(1, float("inf")),
    lambda p: p["lines"][0]["polygon"][0].__setitem__(1, 101),
])
def test_result_cannot_reassign_source_models_execution_provider_or_geometry(mutate):
    payload = _payload()
    mutate(payload)
    with pytest.raises(RapidOcrError, match="rapidocr_result_invalid"):
        _validate(payload)


@pytest.mark.parametrize("size", [(4097, 1), (4000, 4000), (0, 100), (True, 1), (1.0, 2)])
def test_image_limit_rejects_before_conversion_or_model_import(size):
    with pytest.raises(RapidOcrError, match="rapidocr_image_size"):
        validate_image_size(size)


def test_opt_in_configuration_bounds_and_secret_free_environment(tmp_path, monkeypatch):
    with pytest.raises(RapidOcrError, match="rapidocr_not_configured"):
        adapter.RapidOcrConfig.from_env({})
    for env in ({"IDPO_RAPIDOCR_TIMEOUT_S": "nan"}, {"IDPO_RAPIDOCR_TIMEOUT_S": "181"},
                {"IDPO_RAPIDOCR_MAX_RSS_MIB": "2049"}):
        with pytest.raises(RapidOcrError, match="rapidocr_config_invalid"):
            adapter.RapidOcrConfig.from_env({"IDPO_RAPIDOCR_PYTHON": sys.executable, **env})
    for key in ("OPENAI_API_KEY", "ICORE_API_KEY", "DATABASE_URL", "HTTP_PROXY", "PYTHONPATH"):
        monkeypatch.setenv(key, "PRIVATE_MARKER")
    env = adapter.worker_environment(Path(sys.executable), tmp_path)
    assert "PRIVATE_MARKER" not in json.dumps(env)
    assert env["TEMP"] == str(tmp_path)
    assert env["USERPROFILE"] == str(tmp_path)


def test_adapter_keeps_provenance_and_cleans_source_ipc(tmp_path, monkeypatch):
    def worker(argv, _config, work_dir):
        assert "-I" in argv and "-B" in argv
        payload = _payload()
        payload["input_png_sha256"] = argv[argv.index("--input-sha256") + 1]
        (work_dir / "result.json").write_text(json.dumps(payload), encoding="utf-8")
        return 0, 1234, 100
    monkeypatch.setattr(adapter, "_run_worker", worker)
    config = adapter.RapidOcrConfig(Path(sys.executable), work_dir=tmp_path)
    result = adapter.recognize_image(Image.new("RGB", (200, 100), "white"), config=config)
    assert result.text == _validate(_payload())[0]
    provenance = result.metadata["ocr_provenance"]
    assert provenance["text_sha256"] == hashlib.sha256(result.text.encode()).hexdigest()
    assert provenance["coordinate_space"] == "input_raster_pixels"
    assert provenance["peak_tree_rss_bytes_sampled"] == 1234
    assert not list(tmp_path.iterdir())
    result.metadata["ocr_provenance"]["providers"]["text_det"].append("mutant")
    assert PROVIDERS["text_det"] == ["CPUExecutionProvider"]


@pytest.mark.parametrize("tamper", ["source_file", "source_hash", "invalid_json", "no_result"])
def test_parent_rejects_unbound_result_and_removes_temporary_source(tmp_path, monkeypatch, tamper):
    def worker(argv, _config, work_dir):
        payload = _payload()
        payload["input_png_sha256"] = argv[argv.index("--input-sha256") + 1]
        if tamper == "source_file":
            (work_dir / "input.png").write_bytes(b"changed input")
        elif tamper == "source_hash":
            payload["input_png_sha256"] = "1" * 64
        if tamper != "no_result":
            (work_dir / "result.json").write_text(
                "PRIVATE_MARKER" if tamper == "invalid_json" else json.dumps(payload))
        return 0, 1, 1
    monkeypatch.setattr(adapter, "_run_worker", worker)
    with pytest.raises(RapidOcrError, match="^rapidocr_result_invalid$"):
        adapter.recognize_image(Image.new("RGB", (200, 100)), config=adapter.RapidOcrConfig(
            Path(sys.executable), work_dir=tmp_path))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("reason,expected", [("rapidocr_model_mismatch", "rapidocr_model_mismatch"),
                                            ("PRIVATE_MARKER", "rapidocr_worker_failed")])
def test_only_enumerated_worker_failure_codes_reach_product(tmp_path, monkeypatch, reason, expected):
    def worker(_argv, _config, work_dir):
        (work_dir / "result.json").write_text(json.dumps({"status": "failed", "reason": reason}))
        return 1, 1, 1
    monkeypatch.setattr(adapter, "_run_worker", worker)
    with pytest.raises(RapidOcrError, match=f"^{expected}$"):
        adapter.recognize_image(Image.new("RGB", (200, 100)), config=adapter.RapidOcrConfig(
            Path(sys.executable), work_dir=tmp_path))
    assert not list(tmp_path.iterdir())


@pytest.fixture
def worker_module():
    old_path = sys.path[:]
    try:
        yield runpy.run_path(str(Path(adapter.__file__).with_name("rapid_ocr_worker.py")))
    finally:
        sys.path[:] = old_path


def test_pins_match_previously_verified_models_and_tampering_is_rejected(tmp_path, worker_module):
    fixture = Path(__file__).parents[2] / "product_eval/fixtures/tatr_rapidocr_word_lock.json"
    lock = json.loads(fixture.read_text())
    assert MODEL_SHA256 == {name: value["sha256"] for name, value in lock["models"].items()}
    name = next(iter(MODEL_SHA256))
    (tmp_path / name).write_bytes(b"wrong local model; must never download a replacement")
    with pytest.raises(RuntimeError, match="rapidocr_model_mismatch"):
        worker_module["verify_models"](tmp_path)


@pytest.mark.parametrize("event", ["socket.connect", "socket.getaddrinfo", "socket.bind",
                                    "subprocess.Popen", "os.system"])
def test_child_offline_policy_blocks_network_and_process_events(worker_module, event):
    with pytest.raises(RuntimeError, match="rapidocr_offline_policy"):
        worker_module["prohibit_network_and_children"](event, ())


def test_timeout_kills_real_process_and_descendant(tmp_path):
    import psutil
    script = tmp_path / "hang.py"
    script.write_text("import os, pathlib, subprocess, sys, time\n"
                      "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                      "pathlib.Path('pids.json').write_text(str(os.getpid()) + ',' + str(child.pid))\n"
                      "time.sleep(60)\n")
    config = adapter.RapidOcrConfig(Path(sys.executable), timeout_s=1)
    with pytest.raises(RapidOcrError, match="rapidocr_timeout"):
        adapter._run_worker([sys.executable, "-I", str(script)], config, tmp_path)
    for pid in (tmp_path / "pids.json").read_text().split(","):
        assert not psutil.pid_exists(int(pid))


def test_memory_monitor_stops_real_over_limit_worker(tmp_path):
    import psutil
    script = tmp_path / "memory.py"
    script.write_text("import os, pathlib, time\n"
                      "pathlib.Path('pid').write_text(str(os.getpid()))\n"
                      "allocation = bytearray(192 * 1024 * 1024)\n"
                      "time.sleep(60)\n")
    config = adapter.RapidOcrConfig(Path(sys.executable), timeout_s=10, max_rss_mib=128)
    with pytest.raises(RapidOcrError, match="rapidocr_memory_limit"):
        adapter._run_worker([sys.executable, "-I", str(script)], config, tmp_path)
    assert not psutil.pid_exists(int((tmp_path / "pid").read_text()))


def test_live_pinned_runtime_extracts_synthetic_image_with_exact_line_grounding(tmp_path):
    python = os.environ.get("TEST_RAPIDOCR_PYTHON")
    font = os.environ.get("TEST_RAPIDOCR_FONT")
    if not python or not font:
        pytest.skip("opt-in isolated OCR runtime and synthetic font not configured")
    image = Image.new("RGB", (1100, 340), "white")
    draw = ImageDraw.Draw(image)
    chosen_font = ImageFont.truetype(font, 58)
    draw.text((50, 60), "NORTH SOUTH", font=chosen_font, fill="black")
    draw.text((50, 190), "ALPHA BETA", font=chosen_font, fill="black")
    config = adapter.RapidOcrConfig(Path(python), work_dir=tmp_path)
    result = adapter.recognize_image(image, config=config)
    assert result.text == "NORTH SOUTH\nALPHA BETA"
    assert result.metadata["ocr_provenance"]["providers"] == PROVIDERS
    for line in result.metadata["ocr_lines"]:
        assert result.text[line["start"]:line["end"]] == line["text"]
    with pytest.raises(RapidOcrError, match="rapidocr_no_text"):
        adapter.recognize_image(Image.new("RGB", (200, 100), "white"), config=config)
    assert not list(tmp_path.iterdir())
