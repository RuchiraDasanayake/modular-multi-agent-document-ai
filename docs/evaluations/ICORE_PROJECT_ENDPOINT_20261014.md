# ICORE project endpoint and evaluation continuation

Date: 14 October 2026. Surfaces: native setup (`supporting`, `keep`), evaluation
coordinator and scoring verification (`research_evidence`, `keep`).

## Confirmed connection

The replacement credential is a project key. The user supplied its dedicated
base URL, `https://icore.innobothealth.us/innobot-project-api/v1`. The earlier
personal route returned HTTP 401 with `invalid_api_key`. On the project route,
authenticated model discovery, capability discovery and a synthetic Luna 6
chat request all returned HTTP 200. The synthetic response was `OK`, with 12
input tokens and five output tokens. No document was sent in that check.

This key exposed `innobot-luna-6`, `innobot-luna-mantle` and
`innobot-image-core`. Neither embeddings nor other administration-page entries
were exposed by its discovery response. No Sonnet request was made. The server
reported a 4 MiB request limit and no automatic retries. These observations
apply to this project at the check time, not all ICORE installations.

The private native configuration was rotated while the queue contained zero
active or queued dispatches. PostgreSQL, gateway, frontend and worker restarted
successfully. Credentials and the rollback configuration remain outside Git.

A one-document synthetic preview then went through authenticated app admission,
the durable queue and the production worker. It returned invoice number
`UI-2001` and amount `42.50`; both quotes matched exact source spans. It remains
unreviewed. This proves a small integration path, not general extraction
accuracy or human approval. The operator script first used an invalid request
key and received HTTP 400 before admission; it then used the required 32-character
hexadecimal idempotency key, after verifying that no run had been created.

## Frozen comparison: explicit transport amendment

The existing [240-source comparison](QUALITY240_PREREGISTRATION_20261013.md)
records the personal endpoint. Replacing that URL silently would misstate its
execution identity. The endpoint amendment therefore:

- preserves the original protocol, analysis registration, sources, schemas,
  model identifier, extraction code, token limits, OCR, routing and ordering;
- saves the complete pre-amendment ledgers, access receipt and exact amendment
  implementation, all bound by hashes before continuation;
- verifies every prior attempt and terminal source remains unchanged;
- writes a source-and-arm dispatch receipt containing the actual new profile
  before claiming any previously unstarted slot;
- retains the original four-attempt/source-arm and 960-attempt/arm limits,
  one worker, 25-pair checkpoints and explicit provider-stop acknowledgements;
- retains failed and uncertain results without replay, and leaves labels closed
  until all predictions are sealed and independently verified.

`scripts/quality240_project_transport.py` imports the original frozen checkout
and calls its unchanged extraction implementation. The new coordinator is
separately pinned; it does not edit or monkeypatch the frozen modules. Its
`prepare` command binds an exact resumable stop and a verified project access
receipt. Its `resume` command requires the amendment hash and reads the project
credential from a private plain-text file. No key is accepted as a command-line
argument or printed.

Scoring requires an explicit `--transport-amendment-sha256` when an amendment
exists. It verifies the immutable ledger prefix and all later transport receipts
before reference loading. The scoring receipt includes per-arm attempt counts
for each transport and the source-arm transport cohorts. All 480 original
slots remain in the primary analysis.

The endpoint/authentication change is a protocol amendment after inference began
and before reference access. It must be disclosed in the paper. Provider model
weight equivalence across the two routes is unverified; the same requested and
returned model name does not establish it. Report the transport cohorts and
counts alongside the primary paired result. This amendment supplies no new
accuracy or cost claim and changes no primary scoring definition.

## Validation

- 46 tests passed across the amendment, existing paired coordinator and scoring
  suites; two additional integrity regressions were added afterward, and all
  12 amendment tests passed in the final focused run (48 distinct tests total).
- Tests use self-authored inputs and mocked providers. They cover exact endpoint
  dispatch, explicit acknowledgement, unchanged historical failures, interruption
  after a paid marker, no replay, tampered baselines/code/receipts, and rejection
  before reference access when the amendment pin is missing.
- Ruff's `E9,F63,F7,F82` checks passed for the changed Python files.

The final paired outcome, priced cost and conference sign-off remain pending.
