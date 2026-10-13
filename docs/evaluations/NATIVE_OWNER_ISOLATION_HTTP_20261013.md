# Native HTTP ownership verification — 13 October 2026

## Scope and result

**52 HTTP checks passed** against the running native production frontend and
gateway. The product code was `928d351` (the merge of the native recovery,
startup, and schema-preview fixes). This is a bounded access-control check,
not a security certification or browser usability test.

The supporting verifier creates two random-password viewer accounts through the
administrator API, creates a synthetic text-file job owned by the first viewer,
and disables both accounts in its cleanup block. It also checks real, previously
reviewed image results from the [visual HITL smoke](NATIVE_VISUAL_HITL_WORKFLOW_20261013.md).
No password, token, private configuration or response body is saved in its report.

| Check | Observed result |
| --- | --- |
| Owner uploads and reads a source | 201 upload; 200 read with identical bytes |
| Other viewer reads source or appends an upload | 404 |
| Anonymous source read | 401 |
| Other viewer renames the job or accesses its brief, confirmation, suggestion, extraction and recipe routes | 404 |
| Other viewer lists jobs | Owner's job absent |
| Owner saves a draft | 201; revision and content preserved after denied requests |
| Viewer requests model suggestion or extraction on own job | 403; current administrator-only spending gate enforced |
| Both viewers read, edit or export the administrator's existing preview/batch results | 404 |
| Administrator exports before and after denied writes | 200; bytes match the earlier sealed smoke receipt |
| Temporary account cleanup | Both accounts inactive |

No administrator extraction or suggestion request was made. All attempted model
operations were denied by the viewer role gate. No research service, real user
account, original reviewed result or benchmark source was changed. The small
synthetic job and disabled fixture accounts remain as audit artifacts.

## Reproduce

Use a completed `synthetic_visual_hitl_v1` receipt from this installation and a
new output directory. The verifier deliberately refuses to overwrite a report.
The private configuration must select a model so the current viewer spending
gate is exercised.

```powershell
python scripts/verify_native_owner_isolation.py `
  --config I:\DocAI-Runtime\native-product.json `
  --reviewed-fixture-receipt I:\DocAI-Runtime\visual-hitl-smoke-v1\receipt.json `
  --output I:\DocAI-Runtime\owner-isolation-http-v1
```

Local report: `I:\DocAI-Runtime\owner-isolation-http-v1\result.json`.
SHA-256: `e64756ee93e76d110ffcba9ebe9cc7b44c3b2757b67accf89669ea7e7d955183`.

## Subsequent verifier hardening

An independent offline review found three defects in the supporting verifier.
Python `assert` removed critical checks, including HTTP reads inside assertions,
under `-O` or `PYTHONOPTIMIZE`. A receipt with the correct contract but no runs
could omit all existing-result/export controls. An unexpected registration role
raised before recording the newly created account ID, preventing its cleanup.

The verifier now uses explicit checks under optimized Python, requires completed
preview and batch receipts with safe distinct IDs, export hashes and review/export
completion markers before reading configuration or making HTTP requests, and
records each created ID before checking its role. The surfaces remain
`supporting`, with action `keep`. No product authorization policy changed.

Twenty-four offline tests use self-authored receipts and a mocked HTTP transport.
They cover all six value-preservation checks under normal and optimized Python,
incomplete/unsafe fixtures before HTTP, and cleanup after an unexpected account
role. The complete mocked path executes the same 52 checks. No extra live HTTP,
provider or OCR call was made. These tests harden future verification; the prior
52-check result and its recorded hash above are unchanged.

## Limits

This does not audit every legacy route, filesystem races, session expiry, CSRF,
dependency vulnerabilities, or multiple frontend writers. Missing recipe IDs
test the early ownership boundary only; they do not exercise a successful recipe
lifecycle. Previously completed exports provide positive controls for the review
and export checks. Ordinary viewers still cannot run model extraction; per-user
spend authorization is separate product work.
