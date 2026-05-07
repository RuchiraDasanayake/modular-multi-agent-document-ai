# PHASE GOLD25-FUNSD-EVAL — Run DocAI against real FUNSD labeled forms

Goal:
Use this pack to evaluate DocAI extraction against human-labeled FUNSD ground truth.

Pack contents:
- funsd_gold25_schema.json
- funsd_gold25_expected_long.csv
- funsd_gold25_expected_wide.csv
- funsd_gold25_expected_values.json
- funsd_gold25_manifest.json
- documents/*.png
- annotations/*.json

Rules:
- Do not pass expected values into extraction.
- Allowed before extraction: schema field names, aliases, document images.
- Forbidden before extraction: expected_value values from CSV/JSON.
- Expected values are used only after extraction for comparison.
- Treat source as human_labeled_dataset, not in-app review evidence.
- Do not mutate review records, learning samples, adaptive routing, schemas, or profiles.

Suggested workflow:
1. Create an isolated temp DB and temp runs directory.
2. Import/create schema from funsd_gold25_schema.json.
3. Create extraction profile:
   name = FUNSD Gold25 Common Fields
   mode = local_text
   ocr_strategy = router_default
   validation_level = standard
4. Upload documents/*.png.
5. Execute extraction run.
6. Fetch final_output.json / validation_report.json / ocr_output.json for each document.
7. Compare extracted fields against funsd_gold25_expected_long.csv.
8. Produce report with:
   - document_count
   - expected_field_count
   - exact_matches
   - normalized_matches
   - missing
   - wrong_value
   - ungrounded
   - fake_values
   - stub_outputs
   - per-field metrics
   - per-document details

Expected result:
Current line-based KV may not score high on FUNSD because FUNSD is layout-heavy. That is fine. Report truthfully.
