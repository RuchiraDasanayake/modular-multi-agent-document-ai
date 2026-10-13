# Native production upload replay verification

The running Windows production application was rebuilt from `dcf2439`, with
RapidOCR, strict confirmed values, bounded text and selective image routing
explicitly enabled in its private configuration. Startup capability checks
passed. The previous private configuration was retained outside the repository.

Actual HTTP checks used generated text and made **zero model calls**:

- Sending an upload again with the same idempotency key returned the original
  document identity. The endpoint preserves its original HTTP 201 response.
- Two simultaneous requests with one key created exactly one document.
- Reusing the key with changed file bytes returned HTTP 409.
- Anonymous replay returned HTTP 401.
- The two distinct batches retained exactly two files with matching content
  hashes and no leftover temporary files.
- Existing reviewed preview and batch JSONL exports remained byte-identical.

The initial verification script incorrectly expected HTTP 200 for a replay;
it stopped on the status assertion. Inspection confirmed that the documented
route and its unit tests preserve 201, and the corrected verification checked
document identities and stored bytes through the running application.

Private receipt: `I:\DocAI-Runtime\native-upload-retry-verification.json`.
Verification job: `fd6df447c9404ac796d9cfbd7b01b835`.

The merged frontend server/review suite passed **153/153**, and the production
build and native launcher/build regression scripts passed. The quality240
coordinator also passed 18 focused synthetic tests after integration.

This verifies replay behavior in the current single-web-process deployment.
It does not establish cross-process transactional safety for the filesystem
job metadata or human review quality.
