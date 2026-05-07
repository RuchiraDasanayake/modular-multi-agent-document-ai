"""Tests to verify production runtime is isolated from dataset harness.

Confirms that the dataset evaluation harness is test-only and the production
application does not depend on it.
"""

from __future__ import annotations

import sys
from pathlib import Path


def test_production_routes_do_not_import_dataset_harness() -> None:
    """Verify routes.py does not import from datasets or dev_evaluate_labeled_dataset."""
    routes_path = Path(__file__).resolve().parents[2] / "docai_core" / "api" / "routes.py"
    routes_content = routes_path.read_text(encoding="utf-8")

    assert "from docai_core.datasets" not in routes_content
    assert "import docai_core.datasets" not in routes_content
    assert "dev_evaluate_labeled_dataset" not in routes_content
    assert "scripts.dev_evaluate" not in routes_content


def test_production_job_run_service_does_not_import_dataset_harness() -> None:
    """Verify job_run_service does not import from datasets or harness."""
    jrs_path = (
        Path(__file__).resolve().parents[2]
        / "docai_core"
        / "application"
        / "job_run_service.py"
    )
    jrs_content = jrs_path.read_text(encoding="utf-8")

    assert "from docai_core.datasets" not in jrs_content
    assert "import docai_core.datasets" not in jrs_content
    assert "dev_evaluate_labeled_dataset" not in jrs_content


def test_production_runtime_orchestrator_does_not_import_dataset_harness() -> None:
    """Verify runtime_orchestrator does not import from datasets or harness."""
    ro_path = (
        Path(__file__).resolve().parents[2]
        / "docai_core"
        / "orchestration"
        / "runtime_orchestrator.py"
    )
    ro_content = ro_path.read_text(encoding="utf-8")

    assert "from docai_core.datasets" not in ro_content
    assert "import docai_core.datasets" not in ro_content
    assert "dev_evaluate_labeled_dataset" not in ro_content


def test_dataset_harness_not_in_production_application_paths() -> None:
    """Verify dataset harness is in scripts/ and tests/, not in application paths."""
    repo_root = Path(__file__).resolve().parents[2]
    datasets_module = repo_root / "docai_core" / "datasets"
    harness_script = repo_root / "scripts" / "dev_evaluate_labeled_dataset.py"

    # Datasets module should exist (used by tests)
    assert datasets_module.exists()
    assert (datasets_module / "__init__.py").exists()
    assert (datasets_module / "manifest.py").exists()

    # Harness script should exist (for user invocation)
    assert harness_script.exists()

    # But no production application code should import them
    app_module = repo_root / "docai_core" / "application"
    for py_file in app_module.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "from docai_core.datasets" not in content, f"{py_file} imports datasets"
        assert "import docai_core.datasets" not in content, f"{py_file} imports datasets"
