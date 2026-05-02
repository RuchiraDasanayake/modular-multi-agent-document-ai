"""Inspect DAE output and policy matching for one or more documents.

Usage:
  python scripts/inspect_policy_matches.py --input path/to/file --config configs/idpo_research_config.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from idpo.agents.doc_analysis import DocumentAnalysisAgent
from idpo.agents.intake import IntakeAgent
from idpo.agents.base import AgentContext
from idpo.core.artifacts import ArtifactStore
from idpo.core.budget import BudgetManager
from idpo.core.config import load_config
from idpo.core.policy_store import PolicyStore
from idpo.core.provenance import ProvenanceRecorder
from idpo.core.types import SystemConstraints
from idpo.pipeline.planning import PlanRouter
from idpo.pipeline.policy_advisor import PolicyAdvisor


def _ctx(config, run_dir: Path):
    return AgentContext(
        config=config,
        artifact_store=ArtifactStore(str(run_dir / "artifacts")),
        provenance=ProvenanceRecorder(str(run_dir / "provenance.jsonl")),
        run_id="policy-inspect",
        budget_manager=BudgetManager(config.budget),
        calibrator=None,
    )


def inspect_file(input_path: Path, config_path: str | None) -> dict[str, Any]:
    config = load_config(config_path)
    intake = IntakeAgent()
    docs = intake.ingest(str(input_path))
    if not docs:
        raise ValueError(f"No documents could be ingested from {input_path}")

    store = PolicyStore(
        config.knowledge.policy_store_path,
        default_policy_id=config.knowledge.default_policy_id,
    )
    router = PlanRouter(config, store)
    advisor = PolicyAdvisor(config)
    analysis = DocumentAnalysisAgent()
    constraints = SystemConstraints(
        max_cost_units=config.plan.max_total_budget_units,
        max_latency_ms=config.rollback.latency_p95_ms,
        rate_limit=None,
    )
    run_dir = Path(".codex_tmp_policy_inspect")
    run_dir.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(config, run_dir)

    documents: list[dict[str, Any]] = []
    for doc in docs:
        analysis_result = analysis.run({"document": doc}, ctx)
        dae_output = analysis_result.artifacts["dae_output"]
        advice = advisor.advise(dae_output, constraints, store, doc.metadata)
        decision = router.route(dae_output, constraints, doc_metadata=doc.metadata, doc=doc)
        matching = store.matching_policies(dae_output, doc)
        documents.append(
            {
                "doc_id": doc.doc_id,
                "path": doc.path,
                "dae_output": dae_output.__dict__,
                "matching_policy_ids": [policy.policy_id for policy in matching],
                "advisor_recommendations": [
                    {
                        "policy_id": item.policy_id,
                        "score": item.score,
                        "reason": item.reason,
                        "source": item.source,
                    }
                    for item in advice.recommendations
                ],
                "fallback_recommendations": [
                    {
                        "policy_id": item.policy_id,
                        "score": item.score,
                        "reason": item.reason,
                        "source": item.source,
                    }
                    for item in advice.fallback_recommendations
                ],
                "baseline_policy_id": decision.baseline_policy.policy_id,
                "selected_policy_id": decision.policy.policy_id,
                "route_specialization": decision.route_specialization,
                "plan_source": decision.plan_source,
                "advice_source": decision.advice_source,
                "fallback_reason": decision.fallback_reason,
                "plan_operators": [step.operator for step in decision.plan.steps],
            }
        )
    return {"input": str(input_path), "documents": documents}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    payload = inspect_file(Path(args.input), args.config)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
