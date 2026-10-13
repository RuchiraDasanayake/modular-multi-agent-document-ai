# Native production startup and reviewed export verification

Classification: supporting; action: keep.

On 13 October 2026, the native Windows stack ran PostgreSQL, the authentication
gateway, an independent extraction worker and the compiled Next.js production
server without Docker. The production build was tied to its frontend source
fingerprint, build ID, gateway port and checked filesystem junctions. Build output
and private runtime state stayed on the configured data drive.

## Observed checks

- Three native PowerShell test suites passed: process ownership, capability
  preflight and production build receipt validation.
- The real production build completed. Startup verified process identities,
  worker heartbeat and service readiness; `next start` reported ready in 369 ms.
- Authenticated login returned HTTP 200. Gateway health confirmed database and
  PostgreSQL token revocation readiness; frontend health returned HTTP 200.
- Existing synthetic preview and batch reviews survived restart. Both run-level
  JSONL downloads returned HTTP 200, one record each, with the proper media type.
  Decoded records exactly matched the earlier reviewed per-document exports;
  every field retained `human_verified` provenance and completed review status.
- The two JSONL payload SHA-256 digests were
  `e515d3e3a7bab123bde93d8a60cb06dcc2b527ef5a08b4688357f969ea4d1a1e`
  and `8323c5cb3486c24c368ac6b19fbf5fb945e9ca6326cf57486b6172ad683dd891`.
- No model calls were made during this restart/export check.

The private receipt is `native-production-smoke.json` under the configured runtime
directory. It records statuses, hashes and sizes; credentials are excluded.
Frontend server tests separately cover multi-document ordering, stale or partial
reviews, source changes, access control and export bounds (113 tests passed).

## Limits

This verifies local deployment and preservation of reviewed results. The live
export checks each contained one synthetic document. It is not a concurrency
benchmark, a multi-host deployment, a fresh extraction evaluation or evidence of
general-purpose accuracy. OCR/model improvements require separate frozen trials.
