# Opt-in full-page JPEG95 visual encoding

14 October 2026. Classification: core helpers and configuration, keep; this evidence note, research_evidence, keep.

## Decision and limits

An explicit `bounded_visual_selective_jpeg95_v1` profile preserves selective-v2 routing and encodes every selected
visual page as RGB JPEG at quality 95, subsampling 0, without progressive encoding, optimization or source metadata.
It retains complete pages, their original orientation and the existing Lanczos payload dimensions, at most 2048
pixels per edge. Its default is off. There is no per-page adaptive codec choice, crop, additional downscale,
page omission, provider retry or automatic fallback.

JPEG is lossy. Local packing success is not provider acceptance, readability equivalence, extraction accuracy,
or a cost-per-correct-document result. No model or OCR call was made for this implementation. The historical
operational and separate quality studies retain their original profiles and denominators.

## Completed offline engineering evidence

A separate private trial locally re-rendered/re-encoded 29 pages from seven previously rejected operational
sources. The trial verified each original source hash before/after, all reconstructed original OCR-raster hashes
and dimensions, and unchanged OCR text/geometry. It used the frozen runtime with Pillow 12.1.0. It made no
provider/OCR requests and opened no labels. The following are planned requests, not inference attempts:

| Encoding | Full sources locally packable | Total planned requests | Maximum requests/source | Largest request |
| --- | ---: | ---: | ---: | ---: |
| Existing PNG | 0/7 | None; pre-packing rejection | — | — |
| JPEG95 on every page | 7/7 | 12 | 3 | 3,965,161 bytes |
| Post-hoc PNG/JPEG95 mixture | 7/7 | 17 | 4 | 4,173,444 bytes |

All-JPEG95 was selected as a development candidate for greater measured request headroom and a deterministic
encoding policy. The mixture retained 22 PNG pages and changed seven to JPEG95; its largest request was only
20,860 bytes below the limit. Neither choice has measured extraction-quality equivalence. These selected prior
failures cannot estimate a general improvement rate. Changes to prompts or schemas require exact repacking;
the measured request counts cannot be transferred to another response contract.

The six separate raster-size rejections were not decoded in that trial and are not fixed by this profile.
The original 4096-edge/12-million-pixel admission limits remain in force.

## Implemented boundaries

- Preserve original source hash, original PNG OCR-raster hash and dimensions, source text/line hashes, and geometry.
- Record JPEG payload SHA-256, MIME, encoder settings, dimensions/scale, lossy flag and a new transform version.
- Reject mixed/altered encoding profiles, MIME/header mismatch, changed payload/OCR hashes and incomplete pages.
- Prepare every exact request before sending anything. Keep 3,000,000 bytes/page, 4 MiB/request, 12 images/request,
  four requests/source and the existing aggregate encoded-byte budget. The final prompt, schema and base64 bytes
  all count toward the request limit.
- Seal the explicit route in CLI/native/frontend dispatch configuration. Preserve prior defaults, PNG page/plan
  receipts and wire bytes. Keep the original PNG constructor/accessor compatible.
- Keep all visual results pending human review. New-profile admission failures include sanitized stage, page,
  dimensions and applicable size limits where available; no document text, source paths or raw exception messages.

## Verification

Synthetic tests cover deterministic settings, EXIF removal without rotation, original-raster/geometry identity,
real two-page PDF rendering, a dense authored image rejected as PNG but packable as JPEG95 without resizing,
codec/hash tampering, complete 48-page versus refused 49-page planning, exact byte boundaries and schema growth,
all page/aggregate limits, sealed workflow receipts, pre-model failure and a local fake SDK transport with one attempt.

Independent comparisons against base `d752805126c5905d950c5900779ca4d7bc248cf0` used authored original-size and
downscaled images. PNG payloads, OCR bytes, page receipts, exact request bodies and request receipts matched byte
for byte. This is a software compatibility check, not a comparison on study sources.

Validation: 57 focused Python tests (21 new, 36 existing), seven frontend profile tests, TypeScript, targeted ESLint,
and the native PowerShell fixture passed. New Python tests passed the configured full lint rules; touched runtime
files passed syntax/error and import checks. Existing broad-exception handling in those files was retained.

## Private evidence pins

Private source/payload assets remain private. The implementation reads only the completed report; it does not
reopen the trial snapshots, study inputs, predictions or labels.

| Artifact | SHA-256 |
| --- | --- |
| Trial report | `95b3814f4e81a034deb8e4a6e771872673fb48a57b2e32b731cdeef8bd4494f0` |
| Trial results | `69c2148ea72d5c5b4fae92eca03a278894ac17bc6b4bdad67534854feac8ba97` |
| Post-trial verification | `9c6374ace6c23a8e5f35734dd649668c15e20b2e7a14f8e91e5ede3b8fd770b3` |
| Artifact seal | `6b8ffb474c4f90563e4189119c2fac7cb14065b9ffcc40dfd32217f36d73784c` |

Next evidence needed: an independently frozen, bounded provider/quality comparison before any default change or
claim that JPEG preserves small text, numeric separators, extraction quality or total inference cost.
