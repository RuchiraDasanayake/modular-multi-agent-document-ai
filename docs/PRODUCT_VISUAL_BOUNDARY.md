# Optional image and OCR extraction boundary

Status: an explicit product workflow profile is implemented, disabled by default, 13 October 2026.
No model calls were made to validate this workflow integration. The earlier three-source
[vision diagnostic](evaluations/ICORE_VISION_DEV3_V2_RESULTS_20261013.md) established that bounded inline images can
reach the configured provider. It did not validate this strict visual schema or a general accuracy improvement.
A separate, frozen helper-only capability probe has since returned a valid strict visual response from Luna 6
for one previously inspected receipt; that is provider compatibility evidence, not a fresh product quality test.

These `idpo/product_auto` helpers are core candidate components with the primary action `keep`: retain a small,
explicit boundary for source provenance, complete coverage and review-only proposals. They do not add another
orchestrator or replace the existing text route. Existing text schema semantics remain unchanged.

## Integration contract

Call `process_auto(..., visual_document_profile="bounded_visual_v1", confirmed_schema=..., model=...)` to
explicitly select this route. The default is `disabled`, retaining the existing text behavior and artifact shape.
Before creating artifacts, enabled mode requires a confirmed schema and a model with both text/visual methods,
a model ID, and an integer output-token budget in 1–16,384.

Routing is deterministic after local parsing/OCR:

- A single-frame image uses the full original image.
- A PDF with any page requiring OCR uses **all original pages**, including native pages as context.
- An all-native PDF, ordinary text, JSON or Office file uses strict confirmed text extraction and the separately
  configured long-document policy. It does not send an image.
- Empty OCR text can remain an empty aid when the complete page enumeration exists. An OCR exception or missing
  pages cannot silently synthesize coverage. An invalid visual plan makes no model calls.

Enabled mode resolves the text fallback to `strict_confirmed_values_v1`. Artifacts preserve
`configured_response_format_profile`; each document's `response_format_profile`/hash records its actual strict
text or visual format. The run also records `effective_response_format_profiles` across all documents.

Every image and request is prepared before the first send. A provider error, refusal, non-stop completion,
invalid response or failed merge makes the **entire candidate failed**, with no extracted values exposed.
Earlier valid proposals remain only in the private sidecar. There is no model retry or text inference fallback.
The existing conservative segment merger appends linked rows with common group offsets and turns conflicting
scalars into null, review-required values with source-page alternatives. Text evidence offsets already refer to
complete source pages and are never segment-remapped in this route.

`visual_document` receipts in the private sidecar, manifest and run record the route/reason, source hash,
plan/request hashes, page coverage, request outcomes, usage, and planned/attempted/valid counts. A successful
adapter call is not proof of billable provider execution; unknown SDK attempts or tokens remain unknown.
Unattempted requests after a failure are explicit. `full_source_covered` is true only after all planned pages
produce locally valid responses and merging succeeds. It does not imply factual correctness or approval.

The lower-level helpers remain available for controlled diagnostics:

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

The application owns source admission/authorization, explicit profile selection, schema confirmation, durable
execution/cancellation and review/export state. The workflow implements complete planning, conservative row offsets,
page provenance and pending review. Row offsets across requests preserve order; they do not infer a semantic
relationship between physically repeated or continued rows on separate requests.

## Bounds and provenance

### Explicit JPEG95 candidate

`bounded_visual_selective_jpeg95_v1` is an opt-in, lossy candidate. It uses the same pre-call selection rules
as `bounded_visual_selective_v2`: eligible images/OCR PDFs with repeated fields, more than 24,000 text characters,
or no usable OCR text use visual extraction; other sources retain their text route. Every selected visual page
uses JPEG95. There is no automatic PNG-to-JPEG fallback after a failed plan or model call.

Select it with `--visual-document-profile bounded_visual_selective_jpeg95_v1`, the server environment variable
`IDPO_AUTO_VISUAL_DOCUMENT`, or native `autoVisualDocument`. New queue dispatches seal the explicit profile;
later configuration cannot change it. The default remains `disabled`. Existing PNG routing profiles are unchanged.

The new transform is `full_page_original_grid_rgb_jpeg95_444_lanczos_2048_v1`: complete original-orientation pages,
RGB, the same at-most-2048-edge Lanczos geometry, JPEG quality 95, subsampling 0 (4:4:4), `optimize=False`,
`progressive=False`, and stripped source metadata. Original OCR input PNG hashes, dimensions and source line
geometry are retained independently. Page receipts record `payload_sha256`, `payload_mime_type: image/jpeg`,
`payload_lossy: true`, encoder settings and scaled geometry. They do not mislabel JPEG bytes as PNG.
The historical `PreparedVisualPage.png` field remains available for PNG callers; new code uses `.payload`.

Preparation and packing require the same explicit `encoding_profile="jpeg95_v1"` when using the lower-level
helpers. Mismatched profiles, MIME/header identity, payload hashes, page enumeration or request bounds fail
before the first model call. All existing limits below still apply. New-profile size failures additionally record
content-free stage/page/dimension/byte-limit details in the private `visual_document.admission_failure` sidecar.
The existing PNG sidecar and request formats remain unchanged.

This option addresses an observed byte-budget limitation. The [local encoding evidence](evaluations/JPEG95_VISUAL_ENCODING_20261014.md)
does not establish provider JPEG support, readability equivalence, extraction accuracy or lower inference cost.
Every visual proposal still requires human review. No frozen study uses this new profile.

### Existing PNG profiles and shared bounds

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
- Existing PNG profiles convert full pages to RGB PNG and optionally downscale with Lanczos to at most 2048 pixels per edge.
  Version `full_page_original_grid_rgb_png_lanczos_2048_v2` preserves the decoded original pixel grid, matching
  RapidOCR rather than applying EXIF rotation only on the visual side. The receipt records the source EXIF
  orientation and that it was not transposed. The transmitted PNG strips metadata, including orientation tags,
  so a provider cannot apply an undeclared EXIF transform. Sideways source images may remain sideways; this is a
  quality limitation. Their boxes still refer to the documented pixel grid.
  Each encoded page is at most 3,000,000 bytes. The PNG profiles do not crop, tile, use lossy JPEG or retry. This
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
rejected locally. A provider's schema support does not replace these local checks.

All non-null results and linked cells are `needs_review` / `pending`, even with an exact OCR quote. Exact quotes
retain their source offsets as `text_match` evidence. They are not pixel-grounding proof or semantic validation.
Image-only values retain their source page with no invented quote, offset or box. Null fields remain missing.

## Local verification

```powershell
python -m pytest idpo/tests/test_product_visual_boundary.py idpo/tests/test_product_auto_strict_output.py `
  idpo/tests/test_product_auto_provider_format.py idpo/tests/test_product_visual_workflow.py `
  idpo/tests/test_product_auto_long_document.py idpo/tests/test_confirmed_schema_routing.py `
  idpo/tests/test_product_auto.py -q
```

106 tests passed in the configured product environment. Tests include real two-page scanned PDF rendering,
RGB source/resize/geometry hashes, malformed or foreign OCR metadata, changed sources and request bodies,
complete 48-page packing and 49-page refusal, request-byte limits, repeated values on distinct pages, null-quote
visual cells, unchanged text strictness, the real SDK against a local mock transport, one-attempt rejection,
and a changed SDK encoding stopped before the transport receives bytes. Product tests also exercise mixed PDFs,
native/text/Office and long-text routing, empty OCR aids with complete image coverage, no model fallback, failure
in a later request with private partial proposals, scalar conflicts, source changes after intake, pre-artifact
configuration validation, and EXIF-tagged JPEGs with source-matched OCR geometry and metadata-free payload PNGs.
No API request or new quality score is part of this validation. A frozen small development trial is the next
quality gate after this local integration validation.

An additional local compatibility check reused the two already inspected development receipt originals and their
corrected RapidOCR sidecars. Both raster hashes and all 12/25 line records matched; each planned one request
(1,864,926 / 1,103,262 bytes with a synthetic single-column schema). This made zero OCR/model calls, used no labels,
and provides no new extraction-quality result or additional unique document toward the final volume gate.
