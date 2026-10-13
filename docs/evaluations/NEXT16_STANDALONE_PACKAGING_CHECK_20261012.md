# Next 16 standalone packaging check — 12 October 2026

Build under check: `685565a` (`next@16.4.0`). This is a packaging diagnostic, not an extraction-quality evaluation.

- The successful production build emitted five Turbopack warnings about dynamic filesystem paths in the existing artifact, benchmark, and runner modules. Its standalone directory contained 2,471 files / 35.1 MiB, including `server.js`, the compiled job routes, `runner.config.docker.json`, and `scripts/product-worker-client.mjs`. No `.env*` file appeared in that local output.
- The Dockerfile explicitly copies the standalone output, static assets, public assets, Docker runner configuration as `/app/runner.config.json`, and the worker bridge script. The local standalone check temporarily used that Docker runner configuration and an isolated data directory.
- With a local mock `/api/auth/me`, the standalone server returned `200` and an empty list for authenticated `GET /api/jobs`; `POST /api/jobs` created an owner-scoped draft, and `GET /api/jobs/{id}/auto` returned `available: true` with no runs or documents. The packaged worker bridge returned success for `--health` and `--input ... --run-id ...` against a local mock HTTP socket.

No missing-file failure was reproduced on the tested product routes or bridge. The warnings still deserve a later trace-scope review because broad tracing can include unrelated frontend files in an image. A Linux Docker image build and a real product worker connection were not tested; the local Docker daemon was unavailable. No extraction implementation was changed.
