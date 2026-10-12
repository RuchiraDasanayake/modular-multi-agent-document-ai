# ICORE public-document diagnostic stopped on connection failure

**Decision:** do not use this run to rank Luna 6 against Sonnet 5 or claim
real-document extraction quality. The source-locked product trial stopped
after its **first** ICORE chat attempt returned an ambiguous connection
failure with no HTTP status or usage receipt. The precommitted protocol
forbade retrying or sending later documents in that state. This is a
transport/accounting outcome, not a model-quality outcome.

## Frozen inputs and execution

The [protocol](ICORE_REAL_DEVELOPMENT_PILOT_PROTOCOL_20261012.md) and
[six-source lock](../../product_eval/fixtures/icore_real_dev_six_sources.json)
were committed before inference. Lock SHA-256:
`a64f14e737ae7fe2bda3a84458d996385db40b253a78175ec161a6175c82cb15`.
It fixed two VRDU registration PDFs, two VRDU ad-buy PDFs, and two CORD v2
**development** receipts, all with distinct verified raw-source hashes and
completed OCR sidecars. The 40 reserved CORD receipts were excluded. Luna 6
was assigned to all six, and Sonnet 5 to one per family: nine planned
document-model cells, up to 18 chat requests. No private document was sent.

The runner used the unchanged product `process_auto` route on the original
first PDF. Fresh Tesseract OCR yielded 6,612 characters and its page-text
hash **matched the locked prior OCR sidecar**. The product then attempted
the Luna 6 schema call. It returned `APIConnectionError`, classified as
`transport_connect`, after 12.375 seconds. There was no HTTP status,
finish reason, or reported token usage. The SDK made one attempt and zero
retries. The product marked this document `failed` with
`schema_provider_error`; no value call was made. The remaining eight
document-model cells were not attempted.

| Frozen arm | Planned documents | Product runs | Successful model replies |
| --- | ---: | ---: | ---: |
| Luna 6, registration | 2 | 1 failed after OCR | 0 |
| Luna 6, ad-buy | 2 | 0 | 0 |
| Luna 6, receipts | 2 | 0 | 0 |
| Sonnet 5, one per family | 3 | 0 | 0 |

The existing VRDU and CORD scorers retained every planned source in their
denominators. Consequently, the [sanitized score receipt](ICORE_REAL_DEVELOPMENT_SIX_RESULT_20261012.json)
shows zero exact fields, values, linked cells, and rows. Those zeros come from
one failed schema call and eight unattempted cells. They **cannot measure**
the models' extraction ability. Exact field IDs remain the primary score;
the previously frozen alias ontology appears as a separate secondary schema
view, with raw proposed names preserved. There were no proposals to compare.
The VRDU registration pair has 12 reference fields, the ad-buy pair 28;
the CORD pair has seven positive summary scalars, 21 linked cells, and seven
complete rows. These are denominators, not achieved predictions.

## Provider and cost interpretation

No provider error body or underlying cause chain was retained, so this
failure cannot be localized to DNS, TCP, TLS, proxy, or provider socket
handling. A **read-only** check after the stop resolved two host addresses
and completed TCP and verified TLS 1.3 handshakes (DNS 468 ms, TCP 499 ms,
TLS 610 ms). It sent no HTTP request, credential, or document. That later
success rules out a persistent basic connection outage at that moment; it
does not explain or negate the failed chat POST.

The failed call reported no tokens. Its settled charge is unknown; it would
be wrong to label it free or to count it as zero cost. ICORE pricing,
settled-charge access, account-level hard cap, and data terms remain
unverified. The report keeps `api_cost_usd: null`. No further ICORE call was
made under this protocol, even though the numeric call cap had room.

Full product sidecars, raw candidate and score files, and the append-only
call ledger remain outside Git at
`E:\DocAI-Benchmarks\icore-real-dev-six-20261012`. The sanitized JSON records
their SHA-256 hashes, the one credential-free request hash, source hash,
stop reason, scorer denominators, and connectivity receipt. It contains no
API key, prompt, response, OCR text, provider body, or raw document data.

The next ICORE investigation should first obtain reliable transport traces
with safely redacted exception causes and a verified billing/usage ledger.
Any new model or document trial needs a new frozen protocol and explicit
attempt accounting; this stopped run must not be silently resumed.
