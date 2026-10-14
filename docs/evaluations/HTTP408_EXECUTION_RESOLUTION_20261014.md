# HTTP 408 execution resolution

Date: 14 October 2026. Classification: provider handling (`core`, `simplify`),
frozen comparison coordination (`research_evidence`, `keep`).

## Incident and product fix

The 240-source paired comparison stopped at candidate attempt 54 with HTTP 408.
The request was 217,767 bytes, contained one image, and made one SDK attempt.
Its provider token usage is unknown. The old adapter classified every HTTP 4xx
other than 401/429 as `request_rejected`, which made this timeout a nonresumable
study stop. No failed request was replayed.

The current product now classifies HTTP 408 as `transport_timeout`, while
preserving `http_408`, unknown usage and one SDK attempt. Automatic SDK retries
remain disabled. This correction does not modify the frozen product or its
historical metrics.

## Explicit execution amendment

The isolated incident was reviewed before continuation. Its proof bundle pins
1,514 existing campaign files, both complete ledgers, the original stop, and
the exact resolution implementation. Only this HTTP 408 stop is acknowledged;
its failed outcome, attempt and reply remain byte-for-byte unchanged. Future
dispatch is limited to previously unstarted source-arm slots. All 480 original
slots remain in the primary analysis, including failures and uncertain usage.
Labels remain closed until prediction sealing and independent verification.

| Artifact | SHA-256 |
| --- | --- |
| Original stop | `8cc265d565244efe1f99ee0ac679ea7e62c9fd42aff4b6d6d18e8245ae77be8f` |
| HTTP 408 reply | `b594bd6672cc8beb9c36f8b916002ae51090f75a506b4b5cfe53ce8a981f7756` |
| Resolution receipt | `c82620c2432953f3d7b4463935987826d6740d369e3431076bc4ad501a052595` |
| Resolution implementation | `ce186fc00ece75a8a93bfc06f38c2d24c39544a7464338891ee2a5acb90d9116` |

`prepare-http408` writes proof without clearing a stop. `apply-http408` requires
the independently checked receipt hash. A transaction followed by the existing
control journal makes interruption recoverable without dispatching a request.
Resume and scoring require every resolution hash explicitly; prior resolutions
must also be pinned when preparing or applying a later incident. Unknown/mixed
stops, pending calls, altered artifacts and repeated acknowledgements fail closed.

This is an execution amendment after inference began, alongside the earlier
[project endpoint amendment](ICORE_PROJECT_ENDPOINT_20261014.md). The paper must
disclose both. Original `request_rejected` outcome accounting remains unchanged;
the amendment creates no new accuracy, human-review or USD-cost claim.

## Validation

- Provider regression reproduced the classification bug before the change;
  22 provider/adapter boundary tests then passed with mocked HTTP responses.
- 31 final resolution tests passed, including interruption, sequential incidents,
  exact historical-prefix preservation, no replay, and hash checks before labels.
- An earlier combined coordinator/transport/scoring/resolution run passed 76 tests;
  the final focused run includes three additional hardening cases.
- Ruff `E9,F63,F7,F82,F401` and whitespace checks passed for the resolution files.
- Preparation and application each made zero model calls and opened no labels.

The original frozen transport implementation is unchanged. Its extraction code,
schemas, OCR settings, model identifier, budgets and primary scoring definitions
are unchanged. The correction is not evidence of better extraction accuracy.
