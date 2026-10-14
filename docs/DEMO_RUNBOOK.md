# Native Windows demo runbook

Classification: `supporting`; action: `keep`.

Use this guide to demonstrate the configured extraction workspace: upload files, confirm field meanings, preview,
review against the source, process a batch, and export reviewed data. The acceptance check is completing that flow
through the browser with visible source evidence and a readable export. First-time installation and configuration
remain in the [native launcher guide](../scripts/native_product.md); detailed limits are in the
[product quickstart](PRODUCT_QUICKSTART.md).

## Before the demonstration

From the repository root in PowerShell 7.2 or later:

```powershell
$nativeConfig = 'I:\DocAI-Runtime\native-product.json'
pwsh -NoProfile -File scripts/start_native_product.ps1 -ConfigPath $nativeConfig -Status
pwsh -NoProfile -File scripts/start_native_product.ps1 -ConfigPath $nativeConfig
```

This is the private configuration path for the current demo host. The launcher runs PostgreSQL, authentication,
the extraction worker and the frontend locally without Docker. Starting an already healthy tracked stack is safe.
Confirm all four services are healthy, then open [Document jobs](http://127.0.0.1:3000/dashboard/idpo/jobs).
Sign in with the configured administrator account; obtain its credentials from the operator, never from Git.
Model-backed suggestions and extraction currently require an administrator.

If startup reports a stale production build, follow the stop/build/start procedure in the launcher guide after
active extraction work has finished. Do not stop a running benchmark or extraction to prepare a demonstration.
If a resource check fails, unload heavy local model applications and recheck. Startup's offline capability check
does not verify provider availability. Keep the already reviewed example below available for a saved-results tour
if the cloud service is unavailable; identify it as a previous run.

## Live browser walkthrough

Use two small self-authored files with known values for the first demonstration. Supported formats and parser limits
are listed in the quickstart; an accepted extension does not mean that every embedded element is read.

1. Choose **New job**. In **Extract documents**, upload both files in **Files** and wait until both are listed.
2. Under **Set up your extraction**, describe the desired result in **What should the result contain?** For example:
   “Extract the invoice number and the amount due from each invoice. Use the amount explicitly labelled as due;
   leave an absent value empty.” Select one representative **Sample file**, leaving the other for the batch.
3. Add fields manually or choose **Save draft**, then **Suggest fields with AI**. The suggestion is a paid model
   action. Read any **Clarify before confirmation** questions, choose **Use these fields in draft** if appropriate,
   and edit the types and **Meaning** descriptions. Save the draft. For repeated tables, related column fields use
   `array[object]` and the same **Repeated row group**.
4. Choose **Confirm field meanings**. Confirmation pins the schema for extraction; an AI suggestion alone does
   not confirm it. Later field edits create a new draft and need confirmation again.
5. Choose **Preview sample files** once. Watch **Runs** and open the sample result when it finishes.
6. Compare each proposed value with the local page preview, **Open original** / **Download original**, source text and its page or source
   reference. Choose a **Human decision** for every field. Correct missing or wrong values and linked rows using
   the required source references, then choose **Save human review**. A text match alone does not prove the field
   meaning is correct. An image page reference is not a verified pixel location.
7. Return to the workspace and choose **Refresh review status**. After every preview document is reviewed, select
   the remaining files and choose **Extract N selected files**. Leave an existing active run to finish; clicking
   **Run preview again** or creating another batch is a separate potentially billable attempt.
8. Open and review every batch result in the same way. Show **Review history** and **Corrected structured result**
   to explain what changed from the preserved machine candidate. Leave active review minutes blank if unknown.
9. Export a document using **Download reviewed JSON** or **Copy reviewed JSON**. For a fully reviewed run, use
   **Download reviewed batch** or **Copy reviewed JSONL**. JSONL contains one JSON record per document in that run.
   A preview and a subsequent batch are separate runs; exporting the batch does not combine the preview into it.
10. Paste copied output into a text editor and inspect the values and review provenance. Save as `.json` or `.jsonl`
    when needed. Check the success message: if clipboard access is unavailable, try the download control in a
    browser that permits file saving. Embedded-browser file-save delivery has not been verified; do not equate a
    “Download requested” message with a saved file.

The batch export rejects incomplete, failed, stale or unreviewed results. For a one-file job, review and export the
preview; there is no remaining batch.

## Retained examples on the current demo host

Open [the browser walkthrough job](http://127.0.0.1:3000/dashboard/idpo/jobs/8205d3bbc1fb45e49cc874459b68b4aa/auto).
Select its preview or batch under **Runs**, then open the document.

| Run | Expected invoice number | Expected amount due |
| --- | --- | --- |
| Preview `auto_2a6cb70fe4a6459da68f299bc19c5432` | `UI-2001` | `42.5` |
| Batch `auto_d8c61d941bf640e688824a6e1c5741d2` | `UI-2002` | `73.25` |

Both results were reviewed through the UI with automated-test notes. These records demonstrate interaction and
integration; they do not measure independent human review effort. The earlier
[nine-format integration job](http://127.0.0.1:3000/dashboard/idpo/jobs/7ff3b4e1ee754cd78d038cb87f815466/auto)
is another retained example, described in the [nine-format report](evaluations/NATIVE_NINE_FORMAT_SCHEMA_FLOW_20261013.md).
These host-local links require a signed-in owner or administrator and are not portable dataset identifiers.

The [two-page PDF demonstration](http://127.0.0.1:3000/dashboard/idpo/jobs/443422cf736e40ec9bc1550df12847ea/auto)
shows AI-assisted schema setup, local source-page navigation and reviewed export. Its expected values are
`DEMO-2026-014` and `125.75`. Use **Zoom in** for small source text and **Fit width** to restore the page.
See the [browser verification record](evaluations/DEMO_UI_VERIFICATION_20261014.md) for what was actually checked.
The embedded browser's file chooser could not be automated; upload was verified through the authenticated API.
Check file selection and saved-file delivery in the intended presentation browser before the live demonstration.

## If something fails during the demo

| Symptom | Operator action |
| --- | --- |
| Upload response is lost | Use **Retry unconfirmed** to reconcile the original upload; do not immediately select and upload the same files again. |
| Start may already have been accepted | Choose **Check runs** and inspect its state before creating a separate attempt. |
| A run is queued/running | Wait and refresh review status. Do not restart services or submit a duplicate paid run. |
| Provider timeout, including HTTP 408 | Keep the failed attempt. Provider processing and charges may be unknown. Check service health and usage; make a new attempt only after explicitly deciding to incur a possible additional charge. No automatic retry is promised. |
| Invalid or incomplete model output | Read the failure cause and inspect the source. Correct the input/schema or provider setup before a deliberate new attempt. A failed result cannot be reviewed or exported. |
| Batch button/export unavailable | Confirm the current schema, finish every relevant review, refresh status, and check for failed or missing results. |
| Authentication/provider access fails | Ask the operator to check the configured account and matching ICORE endpoint/key category. Keep credentials and raw provider diagnostics out of the presentation. |

## Claims and remaining sign-off

Say: “This workspace proposes structured values, retains source evidence, and requires review before export.”
The synthetic walkthrough establishes usable integration, not universal accuracy, guaranteed extraction, measured
human productivity, or production certification. Local parsing/OCR and cloud inference have separate costs and
failure boundaries; unknown provider usage is not zero cost.

Keep the [2,000-original operational report](evaluations/MODEL2000_VERIFIED_OPERATIONAL_20261013.md) separate:
1,987 originals began model requests and 1,930 had strict/full-coverage outputs; its all-source gate did not pass,
and those counts do not measure value correctness. The [preregistered paired quality study](evaluations/QUALITY240_PREREGISTRATION_20261013.md)
must finish, seal and pass independent verification before its labels are opened and results reported. Frozen
campaigns require their own explicit incident procedures; the demo controls do not authorize replaying them.

Research/release thresholds, final camera-ready results and layout checks, author details, consent, signatures and
author-controlled conference submission remain separate sign-off items. Use the latest evidence record when
presenting their status; a successful demonstration does not close those gates.
