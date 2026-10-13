# Product quickstart and native operator handover

This guide covers the configured single-host Windows product. Open the frontend at the loopback address in your private native configuration (the example configuration uses `http://127.0.0.1:3000`). The product turns supported files into reviewed structured JSON; a proposed value is not a verified fact until a person checks it. See the [native installation and launcher](../scripts/native_product.md) for first-time setup.

## Extract a batch

1. **Sign In**, open **Document jobs**, choose **New job**, then **Upload files**. The job page shows upload progress. If it offers **Retry unconfirmed** after a lost response, use that control to check the original upload receipt before selecting those files again.
2. Open **Automatic schema extraction**. Under **Set up your extraction**, describe the desired result in **What should the result contain?** Choose one to five representative **Sample files**. Use **Add field** to specify field IDs, types, **Meaning**, and optional examples. For a repeated table, add one `array[object]` field per column and give related columns the same **Repeated row group**.
3. You can **Save draft** and ask an administrator to select **Suggest fields with AI**. This is a bounded model call that can cost money. Review the proposed fields and **Clarify before confirmation** questions. Select **Use these fields in draft** if helpful, edit missing or wrong meanings, and **Save draft** again. The AI proposal does not confirm the schema or start extraction.
4. Choose **Confirm field meanings** when every field is correct. Then choose **Preview sample files**. A later edit creates a new draft rather than silently changing the confirmed revision.
5. In **Runs**, open every preview result. Compare proposed values with **Open original** or **Download original** and the source text/page hints. **Text matched** only means that the value appears in extracted text; an image-derived page hint is not a verified pixel location. Choose a **Human decision** for each field, correct values or linked rows where needed, and select **Save human review**. Added values require the source reference requested on the page.
6. After every sample result has completed review, choose **Apply to N remaining files**. Review every remaining result. Use **Download reviewed JSON** for one document or **Download reviewed batch** for a run. The latter is JSONL with one result per selected document; it refuses partial, failed, missing, stale, or unreviewed runs. A one-file job may have no remaining batch, so export its reviewed preview instead.

### Supported inputs and limits

| Input | Product boundary |
| --- | --- |
| PDF | Native text or rendered/OCR pages; at most 50 pages. Model and rendering budgets also apply. |
| PNG, JPEG, TIFF, BMP | One image frame. Split multipage TIFFs and animated images into separate files, or use a multipage PDF. |
| TXT, JSON | UTF-8 text; JSON must follow the product's document text-page input shape rather than arbitrary nested data. |
| DOCX, XLSX, PPTX | Native paragraphs/tables, cells, or slide text/tables. Embedded images and some nested content are outside these readers; spreadsheet formulas are not evaluated. |
| HTML, EML | Local visible text or selected message body; remote resources, scripts and email attachments are not extracted. |

Each file must be 1 byte to 20 MiB. Uploads are sent in bounded browser batches. A supported extension does not guarantee complete parsing or accurate extraction. See the [current contract](SYSTEM_CONTRACT.md) for parser, segmentation and visual-input boundaries.

### If a run is interrupted or a result fails

| What you see | What to do |
| --- | --- |
| `queued` or `running` in **Runs** | Wait and use **Refresh review status**. Do not submit a second paid attempt while the first is unresolved. |
| **An extraction start may already have been accepted** | Choose **Check runs**. The browser retains the request identity for the same selection and schema. **Start a separate attempt** is a new potentially billable action; inspect the previous attempt first. |
| **Document could not be extracted** or **Extraction failed for this document** | Read its cause and action, inspect the original, then fix, split, or re-upload the source before starting a new run. A failed result cannot be reviewed or exported. Ask an operator to inspect logs if it repeats. |
| A missing or weakly supported field | Check the original. Correct the field or add a missed value with the required quote or human-observed image page. Do not mark ungrounded linked text cells “Correct.” |

An uncertain provider or worker outcome is retained or fails closed; it is not automatically retried. The queue and request key reduce duplicate admissions after a lost response; they cannot guarantee exactly one external provider charge across every failure. Model-backed suggestions and runs currently require an **administrator**. A nonadmin job owner can save a draft but cannot trigger paid work. Self-service password recovery is unavailable; contact an administrator. Jobs, reviews, and exports are accessible to the owner or an administrator.

## Operate the native installation

From the repository root in PowerShell 7.2 or later, use the **private** config for this installation:

```powershell
$nativeConfig = 'C:\path\to\private\native-product.json'
pwsh -NoProfile -File scripts/start_native_product.ps1 -ConfigPath $nativeConfig -Status
pwsh -NoProfile -File scripts/start_native_product.ps1 -ConfigPath $nativeConfig
pwsh -NoProfile -File scripts/stop_native_product.ps1 -ConfigPath $nativeConfig
```

The launcher starts PostgreSQL, the authentication gateway, an extraction worker, and the frontend on loopback; Docker is not required. A second start against its healthy tracked stack is safe. An occupied unowned port or stale production frontend build blocks startup. Check `-Status` and the runtime logs; never kill a port listener or delete a PID/process receipt to force a restart. After a frontend source or configuration change, stop the tracked stack, run `scripts/build_native_frontend.ps1 -ConfigPath $nativeConfig`, then start it again. Stopping during extraction can leave an uncertain paid attempt; queued work persists.

PostgreSQL holds authentication and durable queue state. The configured `dataDir` holds uploads, job metadata, extraction artifacts and reviews; the private runtime root also holds PostgreSQL data, logs and process receipts. Keep the config, data, and backups restricted to the operator, SYSTEM and Administrators. This deployment requires a shared local filesystem and does not provide multi-host availability, automatic failover, or per-document resume.

For a cold backup, follow the full [backup and passive recovery procedure](../scripts/native_recovery.md): record a private authenticated source/export baseline, arrange downtime, stop the entire tracked stack, copy the cleanly stopped PostgreSQL cluster and entire product data directory with the recovery helper, then verify the sealed bundle. Use the **base CPython interpreter** as documented there; a Windows venv launcher can correctly trigger the guard. Do not copy the live database, bypass a failed guard, or restore over the active runtime. Backups include credentials, password hashes, documents and reviews and are **not encrypted**. Preserve the matching source revision and dependencies separately, and test a restore in a new isolated location before claiming recovery.

## Verification boundary

An [authenticated synthetic nine-format API flow](evaluations/NATIVE_NINE_FORMAT_SCHEMA_FLOW_20261013.md) completed schema suggestion, preview, batch review and reviewed exports for simple self-authored documents. [Release readback](evaluations/NATIVE_RELEASE23_READBACK_20261013.md) checked existing source/export hashes and paid-request identity. Those checks do not establish browser usability end to end, accuracy on heterogeneous real documents, throughput, monetary cost per correct result, or universal extraction. Independent browser review and the planned larger quality evaluation remain separate work.
