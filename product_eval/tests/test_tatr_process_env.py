"""The bounded PDF workers must never inherit host API credentials."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from product_eval.tatr_process_env import environment_sha256, isolated_worker_env


def test_isolated_worker_environment_omits_credentials_and_ambient_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    python = tmp_path / "python.exe"
    python.write_bytes(b"source-free-test")
    for name in ("ICORE_API_KEY", "OPENAI_API_KEY", "HTTP_PROXY", "HF_HOME",
                 "PYTHONSTARTUP", "PYTHONPATH"):
        monkeypatch.setenv(name, "SHOULD_NOT_REACH_CHILD")
    environment = isolated_worker_env(python, tmp_path)
    assert not any("SHOULD_NOT_REACH_CHILD" in value for value in environment.values())
    assert all(name not in environment for name in
               ("ICORE_API_KEY", "OPENAI_API_KEY", "HTTP_PROXY", "HF_HOME", "PYTHONSTARTUP"))
    assert environment["PYTHONPATH"] == str(tmp_path.resolve())
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert str(python.parent) in environment["PATH"]
    assert len(environment_sha256(environment)) == 64
    assert os.environ["ICORE_API_KEY"] == "SHOULD_NOT_REACH_CHILD"
