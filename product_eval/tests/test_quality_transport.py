"""Synthetic endpoint cutovers: real product artifacts, no network or labels."""
from __future__ import annotations

import json

import pytest

from idpo.product_auto.provider import ModelReply
from product_eval import quality_comparison as quality
from product_eval import quality_scoring as scoring
from product_eval import quality_scoring_verification as verification
from product_eval import quality_transport as transport
from product_eval.final_gate_freeze import digest_file, read_json, write_new
from product_eval.final_gate_ledger import Ledger
from product_eval.tests.test_quality_comparison import (  # noqa: F401 - shared fixtures
    InlinePool, frozen, install_mocks,
)
from product_eval.tests.test_quality_scoring import campaign  # noqa: F401 - shared fixture


@pytest.fixture
def amended(campaign, monkeypatch, tmp_path):
    failure = ModelReply("", 1, error="redacted", error_category="rate_limit", sdk_attempts=1)
    calls, _ = install_mocks(monkeypatch, campaign, first_reply=failure)
    report = quality.run(campaign.output, campaign.sha, api_key_env="SYNTHETIC_KEY")
    assert len(calls) == 1
    access = tmp_path / "access.json"
    write_new(access, {"base_url": transport.PROJECT_BASE, "document_content_sent": False,
        "models": {"status": 200}, "capabilities": {"status": 200},
        "chat": {"status": 200, "body": {"model": "openai.gpt-6-luna"}}})
    amendment_sha = transport.prepare(campaign.output, campaign.sha,
        stop_sha=report["stop_receipt_sha256"], access_receipt=access)
    monkeypatch.setattr(transport, "ProcessPoolExecutor", InlinePool)
    return campaign, amendment_sha, report["stop_receipt_sha256"], calls


def resume(amended, **kwargs):
    campaign, amendment_sha, _, _ = amended
    return transport.run(campaign.output, campaign.sha, amendment_sha, api_key_env="SYNTHETIC_KEY", batches=1, **kwargs)


def test_cutover_only_changes_endpoint_and_never_replays_original_failure(amended, monkeypatch):
    campaign, amendment_sha, stop_sha, calls = amended
    original = read_json(campaign.output / "transport-amendment/baseline-text.json")
    provider = quality.gate.OpenAICompatibleChat
    bases = []

    class ProjectProvider(provider):
        def __init__(self, **kwargs):
            bases.append(kwargs["base_url"])
            super().__init__(**kwargs)

    monkeypatch.setattr(quality.gate, "OpenAICompatibleChat", ProjectProvider)
    resume(amended)
    assert len(calls) == 1 and bases == []  # acknowledgement is never implicit
    result = resume(amended, acknowledge=stop_sha)
    assert len(calls) == 12 and bases == [transport.PROJECT_BASE] * 11
    assert Ledger(campaign.output / "arms/text/ledger.sqlite3").snapshot()["attempts"][0] == original["attempts"][0]
    bundle = verification.verify_campaign(campaign.output, result["prediction_seal_sha256"],
        transport_amendment_sha256=amendment_sha)
    receipt = bundle["transport_amendment"]
    assert receipt["request_begun_attempts_by_transport"] == {
        "text": {"personal": 1, "project": 5}, "candidate": {"personal": 0, "project": 6}}
    assert len(bundle["arms"]["text"]) == len(bundle["arms"]["candidate"]) == 6
    with pytest.raises(ValueError, match="permanently closed"):
        resume(amended)


@pytest.mark.parametrize("damage", ["amendment", "baseline", "implementation", "access", "analysis", "unexpected_file"])
def test_tampered_amendment_blocks_requests(amended, damage):
    campaign, _, stop_sha, calls = amended
    paths = {"amendment": "transport-amendment/amendment.json", "baseline": "transport-amendment/baseline-text.json",
        "implementation": "transport-amendment/implementation.py", "access": "transport-amendment/access-verification.json",
        "analysis": "analysis-plan.json", "unexpected_file": "transport-amendment/unrecorded.json"}
    (campaign.output / paths[damage]).write_text("{}")
    with pytest.raises(ValueError):
        resume(amended, acknowledge=stop_sha)
    assert len(calls) == 1


def test_new_provider_failure_stops_and_requires_new_exact_acknowledgement(amended, monkeypatch):
    campaign, _, stop_sha, _ = amended
    failure = ModelReply("", 1, error="redacted", error_category="authentication", sdk_attempts=1)
    calls, _ = install_mocks(monkeypatch, campaign, first_reply=failure)
    result = resume(amended, acknowledge=stop_sha)
    assert len(calls) == 1
    assert result["stop_receipt_sha256"] != stop_sha
    resume(amended)
    assert len(calls) == 1
    with pytest.raises(ValueError, match="Exact resumable stop"):
        resume(amended, acknowledge=stop_sha)


def test_interruption_after_paid_request_never_replays(amended, monkeypatch):
    campaign, _, stop_sha, _ = amended
    calls, _ = install_mocks(monkeypatch, campaign, first_reply=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        resume(amended, acknowledge=stop_sha)
    result = resume(amended)
    assert len(calls) == 1 and result["arms"]["candidate"]["uncertain_attempts"] == 1
    completed = resume(amended, acknowledge=result["stop_receipt_sha256"])
    assert len(calls) == 11 and completed["summary"]["arms"]["candidate"]["source_states"]["uncertain"] == 1


def test_scoring_requires_explicit_amendment_pin_before_reference_access(amended, monkeypatch, tmp_path):
    campaign, _, stop_sha, _ = amended
    result = resume(amended, acknowledge=stop_sha)
    monkeypatch.setattr(scoring, "load_references", lambda *a, **kw: pytest.fail("Labels opened without transport verification"))
    with pytest.raises(ValueError, match="Explicit endpoint amendment SHA"):
        scoring.run_analysis(campaign.output, result["prediction_seal_sha256"], tmp_path / "scores",
                             vrdu_root=tmp_path, cord_gold=tmp_path / "gold")
    with pytest.raises(ValueError, match="amendment hash"):
        verification.verify_campaign(campaign.output, digest_file(campaign.output / "prediction-seal.json"),
                                     transport_amendment_sha256="0" * 64)


def test_original_slot_cannot_be_reset_to_unstarted(amended):
    campaign, _, stop_sha, calls = amended
    with Ledger(campaign.output / "arms/text/ledger.sqlite3").transaction() as db:
        db.execute("UPDATE sources SET state='unstarted' WHERE ordinal=0")
    with pytest.raises(ValueError, match="Previously attempted source"):
        resume(amended, acknowledge=stop_sha)
    assert len(calls) == 1


def test_dispatch_profile_is_verified_independently_of_seal(amended):
    campaign, amendment_sha, stop_sha, calls = amended
    resume(amended, acknowledge=stop_sha)
    path = next((campaign.output / "transport-amendment/dispatches/candidate").glob("*.json"))
    record = read_json(path)
    record["profile"]["max_tokens"] = 16384
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="dispatch profile changed"):
        transport.verify_amendment(campaign.output, read_json(campaign.output / "protocol.json"), amendment_sha, sealed=True)
    assert len(calls) == 12
