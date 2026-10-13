# Staged product extraction: synthetic API smoke (13 October 2026)

Classification: `research_evidence`; action: `keep`.

This is a live, authenticated product-path smoke on two **synthetic UTF-8 text invoices**. The second file uses the same layout with different values. It tests the path from upload through AI-assisted draft, human schema confirmation, sample preview, source-linked review, pinned batch extraction, and structured export. It is not a document-quality benchmark.

## Attempt ledger

| Version | Luna 6 requests attempted | Outcome | Reported tokens |
| --- | ---: | --- | ---: |
| v1 | 1 | Schema suggestion returned HTTP 502 before diagnostics were available; cause unknown. No preview or batch request. | Unknown |
| v2 | 1 | Schema suggestion returned HTTP 502. Content-free receipt: `provider/transport_connect`; no HTTP response, finish reason, or usage. No retry, preview, or batch request. | Unknown |
| v3 | 3 | Schema suggestion, one-file preview, and one-file batch extraction succeeded. | 1,715 |

The five attempted requests across all versions remain in the denominator. No automatic SDK retry was enabled. The two failed attempts have no verified token usage or charge; the total bill is unknown. An unauthenticated provider-model-list probe returned the expected HTTP 401 before v3, but that does not establish provider reliability.

| v3 request | Prompt tokens | Completion tokens | Result |
| --- | ---: | ---: | --- |
| Draft field suggestion | 235 | 542 | Suggested `invoice_number`, `amount_due`, `currency`, and one clarification question. |
| Sample invoice value extraction | 348 | 105 | `SYN-1001`, `123.45`. |
| Remaining invoice value extraction | 348 | 137 | `SYN-1002`, `456.78`. |

An operator retained and clarified the two requested fields, omitted `currency`, and explicitly confirmed immutable brief revision 3 before preview. The preview and batch each selected one distinct file. Both runs recorded the same confirmed brief ID, revision, payload digest, and snapshot digest; the batch also pinned the reviewed preview run ID.

Both machine results contained the expected two values and evidence quotes matching exact spans of the extracted source text. The invoice number required review in each run; the amount was initially accepted. The operator reviewed both values as correct on each file. Each completed export contains two `human_verified` fields, and each exported source SHA-256 equals its uploaded fixture's bytes. A separate viewer account received HTTP 404 for the job, confirmed brief, and reviewed export, then was deactivated. Administrators have broader access by design, so this does not test isolation between administrators.

## Limits of this evidence

- Two short, nearly identical text files do not establish accuracy on real invoices, PDFs, scans, tables, or arbitrary document types.
- No 2,000-document run, concurrency, throughput, sustained reliability, or dollar-cost measurement was performed here.
- Two earlier suggestion failures show that the cloud-provider path needs a separately measured availability and recovery policy. v3 success does not erase them.
- Private source receipts and request diagnostics are retained outside Git. No credentials, raw provider replies, or user documents are committed with this note.
