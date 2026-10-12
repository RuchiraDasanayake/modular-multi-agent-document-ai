# Product review result receipts

The product worker writes `docs/<doc_id>/result.json`, then records the SHA-256 of its exact bytes as `result_sha256` in `manifest.jsonl`. When the frontend completes a run, it verifies that digest and pins it in the terminal run record. Later reads and review saves compare `result.json` to that pinned digest. Editing the manifest after completion cannot authorize a changed candidate.

Each new review revision also records `machine_result_sha256` in its event and review snapshot, alongside the original source-container and OCR-page digests. Reads and saves check every available historical result receipt. A newer event missing its receipt can use an earlier sealed event only while the exact result still matches. The run list reports a reviewed document as pending if its result or original source no longer matches; document reads and saves return a conflict. This adds source/result hashing work to run-list reads for reviewed documents.

Older runs without a pinned result digest remain viewable before review, but cannot accept a new review. Older reviewed runs with no sealed audit revision return a conflict and require a new extraction run. This is deliberate: a previously approved machine value cannot be reconstructed securely from mutable files. A reviewer should re-extract and review the replacement run.

These receipts detect changes to the machine result, source file, and OCR pages within the product storage boundary. They do not authenticate against an actor who can rewrite the worker manifest, frontend terminal record, and audit history before any frontend validation. That stronger threat model needs external append-only or signed storage.
