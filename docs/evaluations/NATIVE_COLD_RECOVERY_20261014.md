# Native cold backup and passive recovery drill

Classification: `research_evidence`; action: `keep`.

Status: **completed on the same host**. The stopped PostgreSQL cluster and
product data were copied, restored to an isolated passive runtime, and checked
through authenticated original downloads and reviewed batch exports. This is
a cold-copy and readback result, not extraction failover or an availability
guarantee. The aggregate was recorded at 19:09 UTC on 13 October 2026
(14 October locally).

## Boundary and revisions

The backup and recovery checkout used the same clean source revision,
`c24eda8fe25ea773f9842b18b8f86b26a6d80759`. The successful backup receipt records
stopped-state checks before and after copying, followed by the private-tree
check. The manifest seals the entire supported PostgreSQL 16 cluster, product
data and private configuration/baseline. The restore requires that source
revision and preserves every product-data artifact except its explicitly
receipted job-upload path relocations.

The recovery runtime used separate loopback ports, a fresh session-signing
secret, an auth-only gateway, a production frontend and a separate PostgreSQL
copy. It started **zero extraction workers** and copied **no provider keys
into the passive configuration**. Its request boundary blocked extraction and
other non-allowlisted routes. This does not mean the private backup is free of
credentials: it preserves the original configuration and database state and
must remain private.

The [operator guide](../../scripts/native_recovery.md) defines the supported
cluster, path, ACL, dependency and ownership conditions. This drill reused
installed dependencies on the original host. Binaries, package installations
and OCR models are not included in the cold bundle.

## Copied state and permitted relocation

| State | Files | Bytes in sealed backup | Bytes in restored inventory |
|---|---:|---:|---:|
| PostgreSQL cluster | 2,680 | 97,099,183 | 97,099,183 |
| Product data | 224 | 12,387,608 | 12,388,128 |

The PostgreSQL inventory is identical in the backup and restore receipts.
Product-data membership is identical; exactly **13 job metadata files** differ.
Every change is the allowlisted `uploadsPath` field, with before/after hashes
recorded. All remaining 211 product-data file receipts are unchanged. Original
documents, extraction results, reviews and other historical evidence were not
rewritten to repair stored paths.

The aggregate field `copied_data_bytes` contains the restored total,
12,388,128 bytes. It is 520 bytes larger than the sealed backup's product-data
total because of those 13 path relocations. Both totals are reported here;
the original pinned aggregate is preserved unchanged.

## Passive HTTP readback

| Check | Observed result |
|---|---:|
| Selected readback cases | 10 |
| Unique original byte hashes | 10 |
| Unique reviewed batch-export byte hashes | 3 |
| Anonymous artifact requests rejected with HTTP 401 | 20 |
| Authenticated artifact requests requiring HTTP 200 | 20 |
| Separate blocked-route GET checks returning HTTP 423 | 3 |
| Extraction workers started | 0 |
| Model calls recorded by the route-boundary smoke | 0 |

Each selected case checked an original download and its reviewed batch export.
Thus ten cases produce twenty anonymous and twenty authenticated artifact
checks, but only **three distinct batch exports**. These are not ten distinct
export artifacts. A passing verifier requires nonempty HTTP 200 responses,
source hashes matching the copied upload root, and exact source/export hashes
matching the sealed pre-backup baseline. Login is separate from those twenty
authenticated artifact reads.

The passive verifier also requires the `X-DocAI-Recovery: read-only` marker.
All three separate route-denial checks used GET, returned HTTP 423 and carried
the same read-only marker. They are a bounded route smoke, not an exhaustive
authorization or network-isolation test. The readback receipt confirms that
the copied product-data inventory was unchanged before and after readback.
Normal authentication/startup activity can change the cloned database.

## Successful phase timings

| Phase | Recorded elapsed seconds |
|---|---:|
| Successful cold backup | 33.932 |
| Restore copy and receipt | 32.989 |
| Passive HTTP verification | 18.407 |

These are individual successful phase durations. They exclude earlier refused
backup attempts, failed frontend builds, dependency preparation, operator
interventions and other parts of the drill. Their sum is not total downtime,
recovery time objective (RTO), recovery point objective (RPO) or an end-to-end
recovery duration. No transaction-loss window was measured.

## Preparation failures retained

The operator's drill chronology includes these failures; the successful phase
receipts do not erase them:

1. Two earlier backup attempts were refused; neither produced a sealed bundle.
   The first stopped before creating its destination; the second retained an
   unsealed copy. The first invoked the
   helper through a Windows virtual-environment launcher, whose still-running
   wrapper was correctly detected as a configured runtime user. The other
   coincided with an independent runtime probe and was also correctly refused.
   The successful attempt used the resolved base interpreter after other users
   of the configured runtimes had exited. The stopped-state guard was retained.
2. The first frontend build used a dependency junction into another checkout
   on a different drive and failed package resolution.
3. Preserving that dependency link under the frontend with a different name
   still let type checking scan it. The preserved link was moved outside the
   frontend tree, and the clone received its own copied dependency directory.
   The final official production build completed and produced the pinned
   build receipt. The dependency-copy receipt records a successful copy and
   preservation of the original shared junction.

These preparation failures are described from the operator record; the hash
table below binds the successful phases and final aggregate, not separate
per-failure timing measurements. Existing failed directories were not silently
deleted or converted into successful sealed backups.

After readback, the operator reported that the owned passive clone was stopped
and the primary stack was healthy. This documentation audit did not repeat
live health checks, shutdowns or restarts.

## What was independently reconciled

This audit verified the aggregate hash and all eleven listed receipt hashes,
the manifest-to-seal-to-restore-to-HTTP chain, inventory file/byte totals,
all thirteen allowed relocation hashes, unique readback hash counts, passive
route-check counts and successful phase timings. The private baseline was
hashed without parsing its identities. Configuration files and credentials
were not opened. No source contents, reviewed-export bodies, database queries,
OCR or model requests were used to prepare this document.

This is receipt reconciliation of an already completed drill. It does not
independently recopy or rehash every backup payload file; that work belongs to
the sealed backup/restore/readback procedures represented by these receipts.

## Integrity pins

Only receipt identifiers and hashes are published. Private paths, account/job
identifiers, source bytes and credentials remain outside this document.

| Evidence | SHA-256 |
|---|---|
| Final drill aggregate | `37f847c76f77cc4b7443a5074bc474c618053b97fc3f744c15f392937ea87b0c` |
| Pre-backup baseline | `a73d5120cf4a453ce60ab3981f335a6cd16eb36ed88eb5f44010ca80c4d9eccf` |
| Cold-backup manifest | `42cd385e5504b62b7c49c2092babeb3f266e7e158eb79726f0cd86f59ebff73d` |
| Cold-backup seal | `f635e91ff52ac9d1182ab05c11b049e25c9d8416a7d0cb464d19a1a8f414edb5` |
| Restore receipt | `9149bc5097ac663e65739ff173a683e76124f4bdd0ded217a1db072033cbed9a` |
| Passive HTTP readback | `c4139c399128d88ac613cbb4c471ac538748fedaefc3ba4876a30582647e851b` |
| Passive route checks | `7f8aa952359518c1d272b3c76e096fed513a4e97a00d78ce699b0877d43651f4` |
| Final production frontend build | `bdf0924fcb81bb78fed19c7add029f7fc472bdd7f2fc27cf4b0234d60d716991` |
| Successful backup timing | `cad3239872eb07a48884b6dba8425db49ff5b426e70a1125f465f8bd905fa154` |
| Restore timing | `ebb617684c47e0a4090fe7faaa8d78096dd34ddf99b1d191d4992d9b625807ca` |
| HTTP readback timing | `98d0356de7d4cb710b14e8d130a69f4d147edb7c9f3f49ef66f29a7db667654b` |
| Clone dependency copy | `5531576dcff4584a671e3f1cfebe85b2fed1f121c0981fdd8126b8876218ad6c` |

## Limits

The result supports a stopped, complete copy and selected exact-byte passive
readback on this host with the tested source and installed dependencies. It
does not test resumed extraction, replay of paid attempts, execution of copied
queue jobs, loss of the original host, another machine's dependency compatibility,
multi-host failover, high availability, measured RTO/RPO or unrestricted
production readiness. The frozen extraction studies and their quality gates
remain separate evidence.
