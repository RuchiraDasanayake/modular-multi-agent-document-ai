from __future__ import annotations

import importlib
from pathlib import Path


def _reload_direct_advisor(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("IDPO_DATA_DIR", str(tmp_path / "idpo-data"))
    import ahmn_core.direct_advisor as advisor_module

    return importlib.reload(advisor_module)


def test_direct_advisor_persists_state_per_job_across_reload(tmp_path: Path, monkeypatch) -> None:
    advisor = _reload_direct_advisor(monkeypatch, tmp_path)
    payload = {"extra_context": {"metadata": {"job_id": "job-1", "run_id": "run-1"}}}

    advice = advisor.get_advice(payload)
    advisor.log_outcome(advice["advice_id"], advice["policy_id"], 1.0)
    scope_key = advisor.resolve_scope_key(job_id="job-1", run_id="run-1")
    first = advisor.get_state_snapshot(scope_key)

    advisor = importlib.reload(advisor)
    second = advisor.get_state_snapshot(scope_key)

    assert first["scope_key"] == second["scope_key"] == scope_key
    assert second["policies"][advice["policy_id"]]["alpha"] == first["policies"][advice["policy_id"]]["alpha"]
    assert Path(second["state_path"]).exists()


def test_direct_advisor_isolates_state_between_jobs(tmp_path: Path, monkeypatch) -> None:
    advisor = _reload_direct_advisor(monkeypatch, tmp_path)

    first_advice = advisor.get_advice({"extra_context": {"metadata": {"job_id": "job-a"}}})
    advisor.log_outcome(first_advice["advice_id"], first_advice["policy_id"], 1.0)
    first_scope = advisor.resolve_scope_key(job_id="job-a")
    first_snapshot = advisor.get_state_snapshot(first_scope)

    advisor.get_advice({"extra_context": {"metadata": {"job_id": "job-b"}}})
    second_scope = advisor.resolve_scope_key(job_id="job-b")
    second_snapshot = advisor.get_state_snapshot(second_scope)

    assert first_scope != second_scope
    assert first_snapshot["policies"][first_advice["policy_id"]]["alpha"] > second_snapshot["policies"][first_advice["policy_id"]]["alpha"]


def test_direct_advisor_persists_advice_scope_across_reload_for_feedback(tmp_path: Path, monkeypatch) -> None:
    advisor = _reload_direct_advisor(monkeypatch, tmp_path)

    advice = advisor.get_advice({"extra_context": {"metadata": {"job_id": "job-feedback"}}})
    scope_key = advice["scope_key"]
    initial_snapshot = advisor.get_state_snapshot(scope_key)
    assert initial_snapshot["policies"][advice["policy_id"]]["beta"] == 1.0

    advisor = importlib.reload(advisor)
    advisor.log_outcome(advice["advice_id"], advice["policy_id"], 0.0)

    scoped_snapshot = advisor.get_state_snapshot(scope_key)
    global_snapshot = advisor.get_state_snapshot("global")

    assert scoped_snapshot["policies"][advice["policy_id"]]["beta"] == 2.0
    assert global_snapshot["policies"].get(advice["policy_id"], {}).get("beta", 1.0) == 1.0


def test_direct_advisor_falls_back_to_run_scope_when_job_id_is_absent(tmp_path: Path, monkeypatch) -> None:
    advisor = _reload_direct_advisor(monkeypatch, tmp_path)

    advice = advisor.get_advice({"extra_context": {"metadata": {"run_id": "run-42"}}})

    assert advice["scope_key"] == advisor.resolve_scope_key(run_id="run-42")


def test_direct_advisor_only_samples_context_matching_candidates(tmp_path: Path, monkeypatch) -> None:
    advisor = _reload_direct_advisor(monkeypatch, tmp_path)
    policy_store_path = tmp_path / "policies.json"
    policy_store_path.write_text(
        """
{
  "default_policy_id": "default",
  "policies": [
    {"policy_id": "default", "name": "Default", "conditions": {}, "actions": {}},
    {"policy_id": "forms_policy", "name": "Forms", "conditions": {"content_profile": ["form-centric"]}, "actions": {}},
    {"policy_id": "table_policy", "name": "Table", "conditions": {"content_profile": ["table-heavy"], "route_bin": ["heavy"]}, "actions": {}}
  ]
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(advisor, "_POLICY_STORE_PATH", policy_store_path)

    advice = advisor.get_advice(
        {
            "doc_type": "table_document",
            "content_profile": "table-heavy",
            "extra_context": {
                "route_bin": "heavy",
                "metadata": {"job_id": "job-table"},
            },
        }
    )
    snapshot = advisor.get_state_snapshot(advisor.resolve_scope_key(job_id="job-table"))

    assert advice["policy_id"] in {"table_policy", "default"}
    assert set(snapshot["policies"]) == {"table_policy", "default"}
