"""Synthetic HTTP408 incidents through real ledgers, coordinator and product IO."""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from idpo.product_auto.provider import ModelReply
from product_eval import quality_comparison as quality
from product_eval import quality_http408_resolution as resolution
from product_eval import quality_scoring as scoring
from product_eval import quality_scoring_verification as verification
from product_eval import quality_transport as transport
from product_eval.final_gate_ledger import Ledger
from product_eval.tests.test_quality_comparison import frozen, install_mocks  # noqa: F401
from product_eval.tests.test_quality_scoring import _gold, campaign  # noqa: F401
from product_eval.tests.test_quality_transport import amended  # noqa: F401


@pytest.fixture
def incident(amended, monkeypatch, request):  # noqa: F811
    campaign, amendment, old_stop, _ = amended
    kwargs = {"error": "http_408", "error_category": "request_rejected", "sdk_attempts": 1}
    kwargs.update(getattr(request, "param", {}))
    calls, _ = install_mocks(monkeypatch, campaign, first_reply=ModelReply("", 47_980, **kwargs))
    result = transport.run(campaign.output, campaign.sha, amendment, api_key_env="SYNTHETIC_KEY",
                           batches=1, acknowledge=old_stop)
    return campaign, amendment, result["stop_receipt_sha256"], calls


def prepare(incident):
    campaign, amendment, stop, _ = incident
    return resolution.prepare(campaign.output, campaign.sha, stop_sha=stop, transport_amendment_sha256=amendment)


def complete(incident, sha):
    campaign, amendment, _, _ = incident
    resolution.verify_all(campaign.output, [sha])
    return transport.run(campaign.output, campaign.sha, amendment, api_key_env="SYNTHETIC_KEY", batches=1)


def test_exact_408_resolution_preserves_failure_and_all_slots_without_replay(incident):
    campaign, amendment, stop, calls = incident
    before = {arm: Ledger(campaign.output / "arms" / arm / "ledger.sqlite3").snapshot() for arm in quality.ARMS}
    sha = prepare(incident)
    assert prepare(incident) == sha  # preparation is deterministic and leaves stop intact
    assert quality.current_stop(campaign.output)["sha256"] == stop
    assert len(calls) == 1
    with pytest.raises(ValueError, match="Exact resumable stop"):
        quality.acknowledge_stop(campaign.output, stop)
    assert resolution.apply(campaign.output, sha)["already_applied"] is False
    assert resolution.apply(campaign.output, sha)["already_applied"] is True
    assert quality.current_stop(campaign.output) is None
    for arm in quality.ARMS:
        now = Ledger(campaign.output / "arms" / arm / "ledger.sqlite3").snapshot()
        assert now["sources"] == before[arm]["sources"] and now["attempts"] == before[arm]["attempts"]
    result = complete(incident, sha)
    assert len(calls) == 11  # one earlier original-endpoint call is in the other fixture
    assert result["summary"]["selected_source_arm_slots"] == 12
    bundle = verification.verify_campaign(campaign.output, result["prediction_seal_sha256"],
        transport_amendment_sha256=amendment, http408_resolution_sha256=[sha])
    assert bundle["http408_execution_resolutions"][0]["metrics_reclassified"] is False
    failed_id = before["candidate"]["attempts"][-1]["doc_id"]
    failed = bundle["arms"]["candidate"][failed_id]
    assert failed["eligible"] is False and failed["attempts"][0]["error_category"] == "request_rejected"
    assert failed["attempts"][0]["prompt_tokens"] is None
    scores = scoring.assemble_scores(bundle, _gold(bundle))
    assert len(scores["paired_sources"]) == 6
    for arm in quality.ARMS:
        assert sum(row["documents"] for row in scores["families"][arm].values()) == 6
    with pytest.raises(ValueError, match="execution resolution is closed"):
        resolution.apply(campaign.output, sha)


@pytest.mark.parametrize("incident", [
    {"error": "http_400"}, {"error": "http_403"}, {"error": "http_409"}, {"error": "http_422"},
    {"error": "http_429"}, {"error": "http_500"}, {"error": "unknown"},
    {"error_category": "transport_timeout"}, {"sdk_attempts": 2}, {"prompt_tokens": 1},
], indirect=True)
def test_other_statuses_unknown_usage_contracts_and_failures_are_rejected(incident):
    _, _, _, calls = incident
    with pytest.raises(ValueError):
        prepare(incident)
    assert len(calls) == 1


@pytest.mark.parametrize("damage", ["wrong_stop_hash", "reply_bytes", "mixed_stop", "pending_source", "pending_attempt"])
def test_unknown_or_changed_incident_never_clears_stop(incident, damage):
    campaign, amendment, stop, calls = incident
    if damage == "wrong_stop_hash":
        stop = "0" * 64
    elif damage == "reply_bytes":
        (campaign.output / "arms/candidate/replies/000001.json").write_text("{}")
    elif damage == "mixed_stop":
        Ledger(campaign.output / "arms/text/ledger.sqlite3").stop("request_rejected")
    else:
        ledger = Ledger(campaign.output / "arms/text/ledger.sqlite3")
        source = next(row for row in ledger.snapshot()["sources"] if row["state"] == "unstarted")
        assert ledger.claim(source["doc_id"])
        if damage == "pending_attempt":
            ledger.begin_attempt(source["doc_id"], "a" * 64)
    with pytest.raises((ValueError, FileNotFoundError)):
        resolution.prepare(campaign.output, campaign.sha, stop_sha=stop, transport_amendment_sha256=amendment)
    assert len(calls) == 1


@pytest.mark.parametrize("damage", ["receipt_hash", "prior_attempt", "prior_source", "baseline", "implementation", "proof", "new_signal"])
def test_altered_prepared_evidence_blocks_resolution(incident, damage):
    campaign, _, stop, calls = incident
    sha = prepare(incident)
    folder = campaign.output / resolution.FOLDER / stop
    if damage == "receipt_hash":
        sha = "0" * 64
    elif damage in {"baseline", "implementation"}:
        (folder / ("baseline-text.json" if damage == "baseline" else "implementation.py")).write_text("changed")
    elif damage == "proof":
        (campaign.output / "analysis-plan.json").write_text("{}")
    else:
        ledger = Ledger(campaign.output / "arms/text/ledger.sqlite3")
        with ledger.transaction() as db:
            if damage == "prior_attempt":
                db.execute("UPDATE attempts SET latency_ms=9 WHERE attempt_id=1")
            elif damage == "prior_source":
                db.execute("UPDATE sources SET state='unstarted' WHERE ordinal=0")
            else:
                db.execute("UPDATE settings SET value='authentication' WHERE key='stop_reason'")
    with pytest.raises(ValueError):
        resolution.apply(campaign.output, sha)
    assert quality.current_stop(campaign.output)["sha256"] == stop and len(calls) == 1


def test_crash_after_ledger_commit_keeps_stop_until_same_pinned_resolution_is_reapplied(incident, monkeypatch):
    campaign, _, stop, calls = incident
    sha = prepare(incident)
    original = quality.append_event
    monkeypatch.setattr(quality, "append_event", lambda *a, **kw: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        resolution.apply(campaign.output, sha)
    assert quality.current_stop(campaign.output)["sha256"] == stop
    with pytest.raises(ValueError, match="journal acknowledgement is absent"):
        resolution.verify_all(campaign.output, [sha])
    assert len(calls) == 1
    monkeypatch.setattr(quality, "append_event", original)
    resolution.apply(campaign.output, sha)
    assert resolution.apply(campaign.output, sha)["already_applied"] is True
    assert quality.current_stop(campaign.output) is None
    assert len(Ledger(campaign.output / "arms/candidate/ledger.sqlite3").snapshot()["controls"]) == 1


def test_crash_inside_transaction_rolls_back_then_resolves_once(incident, monkeypatch):
    campaign, _, stop, _ = incident
    sha = prepare(incident)
    original = Ledger.transaction
    interrupted = False

    @contextmanager
    def interrupt_transaction(self):
        nonlocal interrupted
        with original(self) as db:
            yield db
            if not interrupted and db.execute("SELECT COUNT(*) FROM controls WHERE event=?", (resolution.EVENT,)).fetchone()[0]:
                interrupted = True
                raise KeyboardInterrupt()

    monkeypatch.setattr(Ledger, "transaction", interrupt_transaction)
    with pytest.raises(KeyboardInterrupt):
        resolution.apply(campaign.output, sha)
    state = Ledger(campaign.output / "arms/candidate/ledger.sqlite3").snapshot()
    assert state["settings"]["stop_reason"] == "request_rejected" and state["controls"] == []
    assert quality.current_stop(campaign.output)["sha256"] == stop
    assert resolution.apply(campaign.output, sha)["already_applied"] is False


def test_missing_or_wrong_resolution_pin_prevents_label_access(incident, monkeypatch, tmp_path):
    campaign, amendment, _, _ = incident
    sha = prepare(incident)
    resolution.apply(campaign.output, sha)
    result = complete(incident, sha)
    monkeypatch.setattr(scoring, "load_references", lambda *a, **kw: pytest.fail("Labels opened before incident verification"))
    for pins in ([], ["0" * 64]):
        with pytest.raises(ValueError, match="Explicit complete HTTP408"):
            scoring.run_analysis(campaign.output, result["prediction_seal_sha256"], tmp_path / "scores",
                vrdu_root=tmp_path, cord_gold=tmp_path / "gold", transport_amendment_sha256=amendment,
                http408_resolution_sha256=pins)
    assert not (tmp_path / "scores").exists()


def test_reset_failed_source_or_changed_old_attempt_rejected_after_resolution(incident):
    campaign, _, _, _ = incident
    sha = prepare(incident)
    resolution.apply(campaign.output, sha)
    ledger = Ledger(campaign.output / "arms/candidate/ledger.sqlite3")
    with ledger.transaction() as db:
        db.execute("UPDATE sources SET state='unstarted' WHERE ordinal=0")
    with pytest.raises(ValueError, match="Previously attempted source"):
        resolution.verify_all(campaign.output, [sha])


def test_unrecorded_resolution_artifact_blocks_dispatch_check(incident):
    campaign, _, stop, _ = incident
    sha = prepare(incident)
    resolution.apply(campaign.output, sha)
    (campaign.output / resolution.FOLDER / stop / "unrecorded.json").write_text("{}")
    with pytest.raises(ValueError, match="Unexpected resolution artifact"):
        resolution.verify_all(campaign.output, [sha])


def test_second_http408_requires_all_prior_pins_and_preserves_both_failed_sources(incident, monkeypatch):
    campaign, amendment, _, _ = incident
    first_sha = prepare(incident)
    resolution.apply(campaign.output, first_sha)
    calls, _ = install_mocks(monkeypatch, campaign,
        first_reply=ModelReply("", 47_980, error="http_408", error_category="request_rejected", sdk_attempts=1))
    second_stop = transport.run(campaign.output, campaign.sha, amendment, api_key_env="SYNTHETIC_KEY", batches=1)
    stop_sha = second_stop["stop_receipt_sha256"]
    assert len(calls) == 1
    with pytest.raises(ValueError, match="Explicit complete HTTP408"):
        resolution.prepare(campaign.output, campaign.sha, stop_sha=stop_sha, transport_amendment_sha256=amendment)
    second_sha = resolution.prepare(campaign.output, campaign.sha, stop_sha=stop_sha,
        transport_amendment_sha256=amendment, prior_resolution_sha256=[first_sha])
    with pytest.raises(ValueError, match="Explicit prior resolution hashes"):
        resolution.apply(campaign.output, second_sha)
    resolution.apply(campaign.output, second_sha, prior_resolution_sha256=[first_sha])
    assert resolution.apply(campaign.output, second_sha, prior_resolution_sha256=[first_sha])["already_applied"] is True
    pins = [first_sha, second_sha]
    resolution.verify_all(campaign.output, pins)
    result = transport.run(campaign.output, campaign.sha, amendment, api_key_env="SYNTHETIC_KEY", batches=1)
    bundle = verification.verify_campaign(campaign.output, result["prediction_seal_sha256"],
        transport_amendment_sha256=amendment, http408_resolution_sha256=pins)
    assert len(bundle["http408_execution_resolutions"]) == 2
    assert sum(len(items) for items in bundle["arms"].values()) == 12
    assert sum(row["eligible"] for items in bundle["arms"].values() for row in items.values()) == 9


@pytest.mark.parametrize("duplicate", ["control", "acknowledgement"])
def test_duplicate_resolution_control_or_acknowledgement_rejected(incident, duplicate):
    campaign, _, _, _ = incident
    sha = prepare(incident)
    resolution.apply(campaign.output, sha)
    if duplicate == "control":
        with Ledger(campaign.output / "arms/candidate/ledger.sqlite3").transaction() as db:
            db.execute("INSERT INTO controls(event, reason, updated) VALUES (?, ?, 0)", (resolution.EVENT, sha))
    else:
        receipt, _, _ = resolution._read(campaign.output, sha)
        quality.append_event(campaign.output, resolution._acknowledgement(receipt, sha))
    with pytest.raises(ValueError, match="Unpinned HTTP408 ledger|Duplicated or out-of-order"):
        resolution.verify_all(campaign.output, [sha])
