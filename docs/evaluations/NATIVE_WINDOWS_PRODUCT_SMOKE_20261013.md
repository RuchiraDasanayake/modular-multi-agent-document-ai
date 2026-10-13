# Native Windows product verification — 13 October 2026

Scope: supporting runtime simplification. Docker is optional; this native development path runs PostgreSQL 16,
gateway, Next.js and the existing on-demand Python extraction subprocess. Redis token revocation has an explicit
PostgreSQL alternative. The extraction algorithm, frozen research evidence and evaluation datasets were unchanged.

## Host setup and provenance

- Official PostgreSQL Windows page linked to the EDB binary archive; EDB file ID `1260623` redirected to
  `https://get.enterprisedb.com/postgresql/postgresql-16.15-5-windows-x64-binaries.zip`.
- Downloaded archive SHA-256: `43bb45f173a6f08cf1d29a97a6d8deb119e8e8093a24c00d2d1001a0ccaa8281`.
  This is an observed checksum, not an independently published vendor checksum. The executable reports
  PostgreSQL 16.15 and has no Authenticode signature; provenance is the official HTTPS distribution.
- Native runtime, database, logs, dependency cache and new document workspace: `I:\DocAI-Runtime`.
  Windows ACL restricted to the current operator, SYSTEM and Administrators. Credentials are outside Git.
- Node 22.20.0; separate Python 3.10 gateway environment. Installed gateway dependency versions are recorded in
  `I:\DocAI-Runtime\gateway-requirements.lock.txt`. Product extraction retains its existing repo environment.
- Database binds `127.0.0.1:55432` using SCRAM passwords; gateway binds `127.0.0.1:8000`; frontend binds
  `127.0.0.1:3000`. Application DB role is not a superuser. No Redis or Docker service was running for this check.

## Live checks

| Check | Observed result |
| --- | --- |
| Gateway deep health | Database and PostgreSQL token revocation healthy |
| Frontend health | HTTP 200, `status=ok` |
| Unauthenticated job request | HTTP 401 |
| Two concurrent requests with the same refresh token | One HTTP 200; one HTTP 401 |
| Synthetic text upload through frontend | HTTP 201 |
| Local product extraction through frontend | One document completed; three proposed fields, all initially requiring review |
| Export before completed review | HTTP 409 |
| Review against the synthetic source and export | Three reviewed fields; JSON attachment HTTP 200 |
| Full stack stop/start | Launcher reported ready; all process/port identities matched |
| Replay after restart | Spent refresh token still HTTP 401 |
| Export after restart | JSON exactly equal to the saved reviewed export |
| Model/API use | Zero model calls |

Local receipt: `I:\DocAI-Runtime\native-smoke-receipt.json`. Synthetic verification job:
`f7922e26e43f409f886350a2aef9079e`; run `auto_2e669591352d46d8b9e158433ae19690`.
The smoke script and private replay state remain inside the ACL-restricted runtime directory.

## Defects found and fixed by this run

- Windows PostgreSQL children inherited piped output, leaving bootstrap waiting after `pg_ctl` exited. Bootstrap now
  redirects to a file and waits on the direct process. The initial fresh cluster was completed explicitly using its
  saved credentials. A second isolated cluster on port 55433 then passed the corrected initializer and stopped cleanly.
- PowerShell JSON parsing converted receipt timestamps to DateTime, breaking signature verification. Receipts now
  normalize UTC timestamps before verification; a real process identity round-trip regression test covers this.
- Local-time versus UTC comparison hid Python child processes from ownership checks. Both sides now use UTC;
  a bounded real child-process regression test covers this.
- The Next.js instrumentation early-return pattern still bundled Node-only imports for Edge. A positive Node-runtime
  conditional, as shown in the installed Next.js documentation, fixed the live Webpack compilation failure.

## Additional validation and limits

46 gateway tests passed, native PowerShell regression checks passed, initializer Ruff passed, and the changed
instrumentation passed TypeScript/ESLint checks. Existing broader gateway lint findings remain outside this change.
The bootstrap refuses existing configurations/clusters instead of overwriting data.

This verifies a local development workflow. It does not establish extraction accuracy on real-world documents,
multi-user load, production hosting, distributed queue durability or bulk-export completeness. The fresh workspace
does not migrate existing jobs. This one synthetic smoke document does not count toward the requested fresh
2,000-original-document extraction evaluation after future substantive extraction changes.
