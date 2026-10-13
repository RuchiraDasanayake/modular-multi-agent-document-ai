# Native production upload verification — 13 October 2026

The native Windows production stack was rebuilt from `53fb14f` and restarted
using the existing private runtime configuration. PostgreSQL, the gateway,
the production Next application and its separate worker were healthy. No
Docker service or model call was used in this verification.

## Reproduced defect and repair

Next's request proxy cloned request bodies with a default 10 MiB limit. An
11 MiB upload could therefore reach the upload handler incomplete even
though the product admits individual files up to 20 MiB. The upload route
now receives the original stream directly; it performs fresh authentication
and owner authorization before reading the body or creating temporary files.
Adjacent document, review and job routes retain their proxy protection.

The multipart parser streams files to bounded temporary files, validates
actual bytes, cleans up failed requests and commits completed uploads using
the latest job metadata. This avoids losing one request's documents when
two uploads complete concurrently in the same application process.

## Running application checks

| Check | Observed result |
| --- | --- |
| Anonymous upload | HTTP 401 |
| Authenticated multipart text file | All 11,534,336 bytes stored unchanged |
| Two simultaneous uploads to the same job | Both 20,000-byte files retained |
| Invalid JSON byte array containing 256 | HTTP 400 |
| Completed job inventory | Exactly three valid uploads |
| Temporary files after completion | Zero |
| Existing reviewed preview export | HTTP 200; bytes unchanged |
| Existing reviewed batch export | HTTP 200; bytes unchanged |
| Gateway database and token revocation | Healthy, PostgreSQL backend |

The large file's stored SHA-256 was
`b3bfb4ab49d869a577d2280ebba9fef2ea547f24a60175890c0532ec55177483`.
The private receipt is
`I:\DocAI-Runtime\native-upload-verification.json`; the verification job is
`5c992e7840ca40679f9d8c6362570851`. Its files contain generated test text.
The reviewed exports matched the earlier
[production export verification](NATIVE_PRODUCTION_REVIEWED_EXPORT_20261013.md).

## Relevant regression checks

- Frontend server and review suites: **143 passed**, zero failures.
- TypeScript: `tsc --noEmit` passed.
- Production Next build: passed with a matching source fingerprint.
- Python visual, long-document, final-gate and paired-development suites:
  **125 passed**.

These checks establish upload integrity and preserve existing reviewed
exports. They do not establish extraction accuracy, simultaneous metadata
writers across multiple web processes, or a completed visual browser review.
The visual proposal contract additionally passed synthetic Python-to-Node
review/export tests; real-document quality is evaluated separately.
