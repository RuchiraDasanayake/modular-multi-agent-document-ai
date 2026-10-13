# Luna 6 vision diagnostic v1: image-size rejection

The [three-source protocol](ICORE_VISION_DEV3_PROTOCOL_20261013.md) stopped after
its first request, as specified. It produced no model values. This result tests
the provider request contract, not extraction quality.

- Frozen code: `c402be5`; protocol SHA-256:
  `1e2e2eb38be7f7011ddc622cbff7844c7c3302e79afbaa5ec2487c5b59a91414`.
- External protected output: `icore-luna6-vision-dev3-v1`.
- One request attempted; HTTP 400 `invalid_image_input`; 7.108 seconds API
  latency, 7.457 seconds run time. Token usage and cost were not returned.
- The two CORD calls were skipped by the stop rule. There were no retries,
  Sonnet calls, automatic releases or labels opened by this runner.
- All 18 files listed by the output seal verified against their SHA-256 hashes.
  Source/image/request/schema hashes and the sanitized full HTTP body are retained.

## Actual cause

The provider response requires inline JPEG/PNG still images no larger than
2,048 by 2,048 pixels, at most 12 images, and a JSON request no larger than 4 MiB.
It disallows remote URLs and file IDs. This is more restrictive than the
diagnostic's assumed 3,072-pixel and eight-million-byte limits.

The first request contained one complete ad-buy page at 2,201 by 1,700 pixels.
Its width exceeded the provider limit. The PNG was 1,195,596 bytes and the
serialized request 1,600,415 bytes, so the recorded byte sizes were within the
provider limit. The prepared receipt images also fit the newly disclosed bounds,
but were not submitted after the error.

No evidence here establishes that Luna 6 lacks vision support, that it reads the
images correctly, or that accuracy improves. Failed/unsent candidates retain the
three-source denominator for execution accounting; interpreting their null values
as model extraction errors would be misleading. No quality score is reported.

## Next bounded diagnostic

Prepare a new immutable protocol with a 2,048-pixel edge limit and an enforced
4-MiB serialized request limit. Keep complete pages, aspect ratio, existing
schemas, cached OCR and review-only output. Reuse the preserved originals and
seal a separate arm; do not overwrite this failed arm or retry its run marker.
