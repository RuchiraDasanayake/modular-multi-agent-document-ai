# One-source VRDU annotation trace: source grouping preserved

## Scope and conclusion

This audit traces only the previously used development ad-buy PDF
`73badb45-b62c-0c2e-1a2f-4b5fb4fda5b9.pdf`, document ID
`1bf0c61dbd517c9d5c1d2684c2788497`. Its original SHA-256 is
`0112d54415d968cd438207ddbd423fb64b636354f29c72f0c6defe3cef14729a`.
No holdout record was opened and no prediction was used to reconstruct gold.

**No importer grouping defect was found for this document.** Re-running the
unchanged `_gold_record` conversion on its original annotation record produces
an object exactly equal to the existing gold record, including all values,
row ordinals, field metadata and evidence. The truncated date strings and
inconsistent date-to-program associations originate in the published annotation
groups. No converter or historical gold changes are justified by this audit.

## Reproducible source chain

- Pinned dataset commit: `04a4df7ac5cc694e51c48115c03fe428f0e240cc`.
- Original relative path: `ad-buy-form/main/dataset.jsonl.gz`, line 329.
- Gzip SHA-256:
  `5fbf579a023e1068433f3115006da109145307cdd3e1b64346b92c959384ef36`.
- Decompressed record-line SHA-256, including its newline:
  `2f54629180c05c8e410462d7aa1084a7a83a33fee734dbb62ef6697c9441c893`.
- Original linked annotation indices 9 through 14 contain six nested groups.
  The converter zips each group's own field-name list to its entries, then
  assigns the group's global ordinal. Missing fields keep their row gaps;
  later values are not shifted up to fill them.
- Protected trace: `icore-luna6-vision-dev3-v2/annotation-audit.json`, SHA-256
  `edea64768894461689f574891b5c89a5f7287771df84b84a9dd101489e48a463`.
  It retains each original group's raw values, bounding boxes, OCR segments,
  imported row ordinal, metadata/gold hashes and exact-equality receipt.

## Source annotations versus the visible original

The following uses the source image for inspection, independently of model
output. Dates are illustrative audit evidence, not replacement benchmark labels.

| Published row / program | Published start-date string | Visible date interval |
| --- | --- | --- |
| 0 / Fox News Sunday | `10/11/20-10` | `10/11/20–10/11/20` |
| 1 / America Says | `10/10/` | `10/06/20–10/09/20` |
| 2 / Entertainment Tonight | `10/09/` | `10/10/20–10/10/20` |
| 3 / Fox 47 News At 9PM | `10/12/20-10` | `10/09/20–10/12/20` |
| 4 / 9-1-1-FOX | `10/06/` | `10/12/20–10/12/20` |
| 5 / Fox 47 News at 930p | no start-date annotation | `10/06/20–10/09/20` |

Scalar flight annotations are likewise truncated in the original record:
`10/06/` and `/12/20`. The visible schedule is `10/06/20–10/12/20`.
These findings apply to this one inspected source. They do not estimate the
prevalence of label problems across VRDU.

## Engineering validation and evaluation consequence

A source-free regression now covers partial rows, changing field-name order
between annotation groups, multiple rows inside a group and incomplete date
strings. It proves missing fields preserve their explicit group ordinal and
raw source strings are not guessed or reassigned. All seven VRDU adapter tests
pass; Ruff passes for the modified test. Production conversion is unchanged.

Preserve the existing strict results as scores against their exact annotation
profile. They cannot alone rank visual transcription quality here. Metadata also
declares official matchers such as `DateMatch` and `AddressMatch`; the strict
derived evaluator does not implement the official VRDU metric and should not be
presented as doing so.

The next quality evaluation should keep two explicit lanes: reproduction of the
published benchmark under its documented matching contract, and a separately
versioned source-faithfulness audit with independently adjudicated values and row
links. Freeze annotation rules and data selection before comparing candidates;
do not silently repair labels using model outputs. Any adjudication of these
already-inspected development documents remains development evidence.

The 2,000 distinct-document execution gate can verify completed original-file
processing separately. It does not turn noisy labels, skipped model calls or
review-only proposals into validated extraction accuracy.
