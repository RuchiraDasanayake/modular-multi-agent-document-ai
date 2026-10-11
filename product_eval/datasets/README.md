# VRDU cohort and derived gold

`vrdu.py` builds a fixed 2,000-PDF execution cohort from the creator's
[VRDU repository](https://github.com/google-research-datasets/vrdu) at commit
`04a4df7ac5cc694e51c48115c03fe428f0e240cc`. It selects 1,500
registration-form and 500 ad-buy-form PDFs by the lowest SHA256 ranks of
`vrdu-v1-cohort\0<family>/<filename>`, before reading labels. This fixed rank
avoids selecting registration forms only from the earliest filename dates.
Selection is independent of annotation quality.
The adapter checks one annotation row per PDF filename, hashes the raw PDFs,
and rejects duplicate source content or document IDs in the selected cohort.

From the repository root, using a checked-out creator Git repository:

```powershell
python -m product_eval.datasets.vrdu --dataset-root 'E:\DocAI-Benchmarks\vrdu-checkout' --output-dir 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7'
```

For a codeload ZIP extracted into that directory, pass the downloaded archive:

```powershell
python -m product_eval.datasets.vrdu --dataset-root 'E:\DocAI-Benchmarks\vrdu-extracted\vrdu-04a4df7ac5cc694e51c48115c03fe428f0e240cc' --source-archive 'E:\DocAI-Benchmarks\vrdu-04a4df7.zip' --output-dir 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7'
```

The ZIP mode requires every extracted file to match a member under the exact
pinned commit prefix and records the ZIP SHA256. Bare extracted directories are
not accepted by the CLI. The output directory must be new.

Outputs:

| File | Meaning |
| --- | --- |
| `cohort.jsonl` | One source receipt per selected PDF. Includes `dataset_id`, `source_id`, `family`, absolute `source_path`, raw `source_sha256`, byte count, and the candidate runtime's stable `doc_id`. The execution harness should read only this file. |
| `gold.jsonl` | `product_eval` v1 gold for every structurally mappable selected document. It is separate from candidate execution. |
| `exclusions.jsonl` | A reason for each selected PDF whose published annotations cannot map honestly to v1. The PDF **remains** in `cohort.jsonl` and in the execution denominator. |
| `metadata.json` | Pin, selection rule, family counts, exact file hashes, gold coverage, annotation shape counts, and interpretation limits. |

The gold uses VRDU's published field IDs and raw OCR surface values. Only
leading and trailing whitespace is removed. Identical repeated scalar values
collapse to one value; divergent repeated values remain ordered string arrays.
VRDU's linked line-item annotations become row-indexed arrays under their
published field IDs, preserving which values belong to the same row. Absent
fields are JSON `null`. Dates and amounts remain strings: the creator's
`meta.json` matcher name is retained as `source_match_func`, but the v1 scorer
does not apply that matcher. `critical` is false because the creator does not
publish business criticality labels.

This is a **derived product evaluation format**, not the official VRDU
benchmark. Exact-value scores cannot be compared with published VRDU scores.
The v1 scorer also cannot evaluate row alignment separately, so linked fields
are scored as complete ordered arrays. Gold evidence spans index VRDU's OCR
text; an independent PDF OCR pass can have different text and offsets. Report
evidence metrics separately and do not interpret an offset mismatch as an
extraction error without OCR alignment.

The 2,000-document cohort checks execution volume within two related form
families. It does not demonstrate universal document support or field quality
by itself. After a run, verify that every cohort source was processed once,
including failures and unsupported results, with `product_eval.verify_execution`.
Score only with a joined, complete gold/candidate set. If any gold exclusions
remain, report them and the reduced quality denominator; never present the
2,000 execution count as 2,000 scored documents. Keep the source PDFs and
generated gold outside the application repository.

## Family-wise analysis

After both product run shards finish, verify their source receipts and break
the unchanged `product_eval` metrics down by VRDU family:

```powershell
python -m product_eval.datasets.vrdu_analysis --cohort 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl' --gold 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl' --run-dir 'PATH_TO_REGISTRATION_RUN' --run-dir 'PATH_TO_ADBUY_RUN' --output 'PATH_TO_FAMILY_REPORT'
```

`--run-dir` verifies completed run manifests, source bytes, and an exact join
to the frozen cohort before scoring. For already verified candidate JSONL,
`--candidate` can be repeated instead. `--full-report` is optional; when
supplied, the utility recomputes the complete scorer output and rejects a
report that does not match. Each family's score is produced by the same
scorer on that family's exact document IDs. Companion diagnostics show strict
value outcomes, missed published field IDs, extra candidate IDs, linked-row
array outcomes, abstentions and evidence text comparisons. They do not infer
semantic aliases or per-row alignment. `--run-dir` also verifies each accepted
quote against the runtime's own OCR sidecar, separately from the VRDU gold OCR.
Exact source anchoring does not prove field relevance. A candidate quote that
differs from the official OCR at its numeric span is marked as an ambiguous
cross-OCR comparison, not a grounding failure. No values or page text appear
in the analysis report. Missing candidate documents stay in the family
denominator.
