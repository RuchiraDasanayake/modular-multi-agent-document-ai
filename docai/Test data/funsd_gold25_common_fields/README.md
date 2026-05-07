# FUNSD Gold25 Common Fields Pack

This pack contains 25 real FUNSD scanned form images and human-labeled expected values.

Use this for golden dataset evaluation:
1. Create/import schema from `funsd_gold25_schema.json`.
2. Upload the documents in `documents/`.
3. Run DocAI extraction.
4. Compare outputs to `funsd_gold25_expected_long.csv` or `funsd_gold25_expected_wide.csv`.

Important:
- Expected values are ground truth from human labels.
- Do not pass expected values into extraction.
- Use expected values only after extraction for comparison.
- Source should be treated as `human_labeled_dataset`, not in-app review evidence.

Summary:
- Documents: 25
- Expected field values: 109
- Schema fields with coverage: 18
