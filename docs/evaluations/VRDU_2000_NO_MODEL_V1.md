# VRDU 2,000-document no-model baseline (2026-10-11)

This is a **product development baseline**, not a score for the submitted paper or the official VRDU benchmark. It tests the opt-in `idpo.cli process-auto` route with local Tesseract OCR and its deterministic key/value discovery. The run made **zero model calls**. It does not measure AI-generated schema quality.

## Reproduction boundary

- Source: [VRDU](https://github.com/google-research-datasets/vrdu) repository commit `04a4df7ac5cc694e51c48115c03fe428f0e240cc`, archive SHA-256 `6e0e21582113fb74765c4cd339e29d5dd5a36162c2e559e39e1e748918e91b8a`.
- Cohort: 1,500 registration forms and 500 ad-buy forms selected by deterministic filename SHA-256 rank, with 2,000 distinct raw PDF hashes. The frozen cohort manifest SHA-256 is `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`; derived gold SHA-256 is `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Eight disjoint 250-PDF shards used run IDs `vrdu_2000_shard_{ad_00,ad_01,reg_00,reg_01,reg_02,reg_03,reg_04,reg_05}_v1`. `product_eval.verify_execution --min-unique 2000` rehashed the actual inputs and confirmed 2,000 documents, 2,000 distinct sources, no duplicates, and no missing candidate record.
- Candidate JSONL SHA-256: `578921d8298393d170bb7d35a2da2f5855aee3460b96278082061f23305675f6`. Execution report SHA-256: `d44644c5996720acb71a5ce7d2819db3883ecfabbcc6156c086389c41096ab0f`. Strict quality report SHA-256: `37f593deb345bac9cfdd7c3a52505f8d485b4924bf73e05f7cd4f5e30dc2296c`. Family analysis SHA-256: `952b9303698c87150f8f39fbc45bd54ec0ad9f94fa708fb4ee00cfd806c22e23`.

## Measured outcomes

| Family | Documents | Schema TP / FP / FN | Schema F1 | Value TP / FP / FN | Value F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Registration | 1,500 | 749 / 16,815 / 8,251 | 5.64% | 116 / 8,666 / 6,798 | 1.48% |
| Ad-buy | 500 | 67 / 4,083 / 6,933 | 1.20% | 3 / 3,357 / 5,961 | 0.064% |
| Total | 2,000 | 816 / 20,898 / 15,184 | **4.33%** | 119 / 12,023 / 12,759 | **0.95%** |

The pipeline labeled 997 documents `processed`, 968 `needs_review`, and 35 `unsupported`; none failed to emit an output. The `processed` label was unsafe: it meant only that every *discovered* field had a grounded value. It did not check whether the fields were useful or complete. Among 12,878 present gold fields, 12,064 were missed, and 693 accepted values on matching field IDs were wrong. All 2,500 ad-buy linked-row field records were missing or unresolved. The baseline only proposes scalar fields.

All 12,142 accepted value quotes matched an exact span in this pipeline's own OCR text. That verifies text anchoring, **not field relevance**. The strict scorer found 0/794 candidate spans valid against the separate OCR stream supplied by VRDU; those offsets are not aligned, so this is not evidence that the pipeline's own source anchors failed. The reported sum of document durations was 1,824,685.744 ms. API cost, compute cost, total cost, and human review time had **0/2,000 coverage**, so this run supports no cost-per-correct-document claim. VRDU has no criticality labels for our release metric.

## Decision

This baseline fails the product quality gate. The extractor must not auto-release an unapproved, dynamically discovered schema. A model-produced schema must be allowed to remove heuristic noise, and value extraction must run against the final schema. Test schema utility by human semantic adjudication and value extraction separately against a fixed field contract, then run a new 2,000-unique-source gate for each reviewable extraction candidate. Preserve this strict score unchanged; additional semantic, row, normalized-value, and OCR-aligned evidence metrics must be reported as separate views. Two document families do not establish arbitrary-document generalization.
