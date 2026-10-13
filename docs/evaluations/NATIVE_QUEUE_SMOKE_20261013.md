# Native queue integration verification — 13 October 2026

Surface classification: queue/dispatch code is **core / keep**; native launchers and regression tests are
**supporting / keep**; this record is **research_evidence / keep**.

The product now admits extraction through PostgreSQL/pg-boss and executes it in a separate Node worker, which
launches the existing Python extractor. The web app is not the extraction process owner in native mode.

## Verified

- Nine live PostgreSQL behavior cases (ten tests including the parent suite) passed on a fresh disposable database:
  concurrent cold startup and idempotent admission, owner isolation, immutable run identity, per-job conflict,
  per-owner quotas, transaction rollback on broker failure, persistence across broker restart with competing workers,
  terminal execution failure without retry, and missing-broker reconciliation.
- Those tests reproduced and then verified fixes for cross-process schema creation and cross-owner duplicate-ID
  admission races. Tests never used the product database or made model calls.
- The integrated frontend server suite passed 83/83; TypeScript and touched queue/worker lint checks passed.
- Native launcher regression checks passed, including worker PID receipt integrity and timestamp round-tripping.
- Live authenticated product API smoke: synthetic text upload → queued dispatch → Python extraction → source-linked
  human review → reviewed export. Three fields were reviewed; export before review returned 409. No model calls.
- Full native stack stop/start retained the exact reviewed export and rejected the already-used refresh token.
  PostgreSQL, gateway, frontend and independent worker were all verified healthy after restart.

## Limits

This proves a synthetic operational path, not general extraction quality. It does not count toward the final
2,000-original-document evaluation. External API calls cannot be made transactional with queue commits; an
interrupted or uncertain attempt is terminal and requires explicit user action. Active runs do not resume at a
document checkpoint. Filesystem artifacts and owner job metadata still need shared storage on additional hosts;
multi-host deployment and production capacity were not tested. Native web startup remains development mode.

Local verification receipts and logs are stored privately beneath the configured runtime root. Credentials and
authentication tokens are excluded from this repository.
