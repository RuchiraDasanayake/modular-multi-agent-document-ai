# Optional image and OCR extraction boundary

Status: local helpers and provider transport only, 13 October 2026. This is **not yet a product workflow route**.
No model calls were made to validate this implementation. The earlier three-source
[vision diagnostic](evaluations/ICORE_VISION_DEV3_V2_RESULTS_20261013.md) established that bounded inline images can
reach the configured provider. It did not validate this strict visual schema or a general accuracy improvement.

These `idpo/product_auto` helpers are core candidate components with the primary action `keep`: retain a small,
explicit boundary for source provenance, complete coverage and review-only proposals. They do not add another
orchestrator or replace the existing text route. Existing text schema semantics remain unchanged.

## Integration contract

```python
from pathlib import Path
from idpo.product_auto.visual_input import prepare_visual_document, plan_visual_requests
from idpo.product_auto.visual_output import parse_visual_values_reply

prepared = prepare_visual_document(
    Path(original_path), expected_source_sha256=admitted_file_sha256,
    pages=exact_product_pages,
)
requests = plan_visual_requests(
    prepared, fields=confirmed_fields, intent=confirmed_intent,
    model=model.model, max_tokens=model.max_tokens,
)
# Planning must finish successfully before the first send. Keep a terminal
# outcome for every planned request, even if a prior request fails.
for request in requests:
    receipt = request.receipt()
    reply = model.complete_visual_json(request)
    # The caller must reject provider errors, refusals and non-stop completion.
    # It must also record actual attempts, usage, latency and terminal failures.
    if reply.error or reply.refusal or reply.finish_reason != "stop":
        break
    batch_pages = [p for p in exact_product_pages if p["page"] in receipt["covered_pages"]]
    values = parse_visual_values_reply(reply.text, confirmed_fields, batch_pages)
    # None means structurally invalid. All non-null values require review.
```

`exact_product_pages` contains consecutive `page` numbers starting at 1, exact `text`, and, when available,
`ocr_lines` and `ocr_provenance`. RapidOCR geometry is accepted only when its input PNG hash, dimensions, text
hash, line text, offsets and bounded convex polygons match the freshly prepared source raster. A changed raster
or preprocessing transform is rejected rather than assigning its old boxes to a new image. Native text and
OCR without line geometry have no invented pixel boxes.

The application still owns source admission/authorization, choosing the explicit profile, freezing the schema,
planned-call budget admission, execution, cancellation, result merging and review/export state. Per-request
zero-based row IDs do **not** establish correspondence across different requests. A workflow must namespace or
deliberately reconcile rows across requests, preserve page provenance and keep them pending review.

## Bounds and provenance

- Input: one original PDF or single-frame raster, at most 100 MiB. Office and text files must use another route.
- The original's expected SHA-256 is required. Preparation renders a private byte snapshot and rechecks the
  original afterward. The provider rechecks the original again before each send. It sends only the immutable
  prepared body; changes to the upload cannot change those transmitted image bytes.
- Every actual page must have a corresponding text record. Up to 50 pages can be inspected, but at most four
  requests and 12 images per request mean 49–50 pages are explicitly unsupported by this version. Nothing is
  silently truncated or sampled. The 96,000-character source-text and four-request budgets are source-wide.
- PDF uses the existing shared renderer, including its PDFium lock, intrinsic scan resolution and 4096-edge /
  12-million-pixel raster bounds. Source images have the same raster bounds. Encrypted PDFs and multiframe images
  are explicitly unsupported. Rendering itself shares the existing renderer's execution-time limitations.
- Full pages are converted to RGB PNG and optionally downscaled with Lanczos to at most 2048 pixels per edge.
  Each encoded PNG is at most 3,000,000 bytes. There is no crop, tile, lossy JPEG rewrite or hidden retry. This
  limit can make small text illegible; it is an explicit quality limit, not a readability guarantee.
- The complete body, including images, text, geometry, schema, model and output-token budget, is at most 4 MiB.
  Packing uses actual compact UTF-8 JSON bytes. A single page that cannot fit fails before any calls. More than
  four necessary requests fails complete planning, before any calls.
- The provider compares the SDK's actual body hash and size immediately before transport. The tested SDK parameter
  order is pinned in the serializer. A future SDK serialization change fails closed and requires revalidation.
  The transport has no retries or redirect following, and provider errors retain the existing content-free form.
- Receipts contain source, original raster, payload PNG, OCR text, original/transformed geometry and request hashes;
  real page IDs, exact coverage, dimensions, scale factors and renderer plan; and pinned transform/packing versions.
  They contain no image URLs, document text or local source paths. Actual request bytes are private document data.
  Planned complete coverage does not mean every planned request executed successfully.

## Strict visual output

`strict_visual_confirmed_values_v1` retains the closed, complete confirmed-field envelope and local field/type
validation. It permits a null quote for linked cells readable only in the image. Every non-null value must name a
page in that request. Extra keys, missing fields, invalid types, duplicate field/row IDs, and malformed JSON are
rejected locally. Provider schema enforcement remains an unverified hint until a frozen provider test.

All non-null results and linked cells are `needs_review` / `pending`, even with an exact OCR quote. Exact quotes
retain their source offsets as `text_match` evidence. They are not pixel-grounding proof or semantic validation.
Image-only values retain their source page with no invented quote, offset or box. Null fields remain missing.

## Local verification

```powershell
python -m pytest idpo/tests/test_product_visual_boundary.py idpo/tests/test_product_auto_strict_output.py `
  idpo/tests/test_product_auto_provider_format.py idpo/tests/test_product_auto_linked.py `
  idpo/tests/test_product_auto_grounding.py -q
```

44 tests passed in the configured product environment. Tests include real two-page scanned PDF rendering,
RGB source/resize/geometry hashes, malformed or foreign OCR metadata, changed sources and request bodies,
complete 48-page packing and 49-page refusal, request-byte limits, repeated values on distinct pages, null-quote
visual cells, unchanged text strictness, the real SDK against a local mock transport, one-attempt rejection,
and a changed SDK encoding stopped before the transport receives bytes. No API request or new quality score is
part of this validation. A frozen small development trial is the next quality gate after workflow integration.

An additional local compatibility check reused the two already inspected development receipt originals and their
corrected RapidOCR sidecars. Both raster hashes and all 12/25 line records matched; each planned one request
(1,864,926 / 1,103,262 bytes with a synthetic single-column schema). This made zero OCR/model calls, used no labels,
and provides no new extraction-quality result or additional unique document toward the final volume gate.
