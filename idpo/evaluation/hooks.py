"""Evaluation hooks for comparing preprocessing configurations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from idpo.core.config import load_config
from idpo.evaluation.runner import evaluate_documents
from idpo.pipeline.orchestrator import Pipeline

def compare_preprocessing_routes(
    docs,
    base_run_dir: str,
    config_paths: list[str],
) -> dict[str, Any]:
    results = []
    for config_path in config_paths:
        config = load_config(config_path)
        run_dir = str(Path(base_run_dir) / Path(config_path).stem)
        pipeline = Pipeline(config=config, run_dir=run_dir)
        metrics = evaluate_documents(docs, pipeline, run_dir)
        results.append({"config": config_path, "run_dir": run_dir, "metrics": metrics})
    return {"mode": "preprocessing_routes", "results": results}

def compare_retrieval_strategies(
    docs,
    base_run_dir: str,
    config_paths: list[str],
) -> dict[str, Any]:
    results = []
    for config_path in config_paths:
        config = load_config(config_path)
        run_dir = str(Path(base_run_dir) / f"retrieval_{Path(config_path).stem}")
        pipeline = Pipeline(config=config, run_dir=run_dir)
        metrics = evaluate_documents(docs, pipeline, run_dir)
        results.append({"config": config_path, "run_dir": run_dir, "metrics": metrics})
    return {"mode": "retrieval_strategies", "results": results}
