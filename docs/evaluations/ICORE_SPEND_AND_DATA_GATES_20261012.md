# ICORE spend and data-control audit, 2026-10-12

> **Status update — 13 October 2026:** The spend decision below is a preserved
> historical decision, superseded for the explicitly authorized Luna evaluation.
> The account owner authorized Luna 6 or Luna 5.6, offered to replenish credits,
> and prohibited Sonnet 5. The [new 2,000-source protocol](MODEL2000_SELECTIVE_V2_EXECUTION_20261013.md)
> therefore uses a fixed public-source cohort, a 2,500-attempt maximum, bounded
> concurrency, explicit provider-failure stops and no automatic replay of
> uncertain paid attempts. The [240-source paired protocol](QUALITY240_PREREGISTRATION_20261013.md)
> has its own 1,920-attempt cap and first-provider-error stop. These are separate
> authorized campaigns, not an accumulation of the old small pilots. Prices,
> settled charges and API data terms are still unverified; cost in USD remains
> unknown. This authorization does not establish data-use guarantees for future
> customers' private documents.

## Decision

**No ICORE-backed 2,000-document run yet.** I could not verify a current ICORE API rate card, settled charge ledger, account balance, usage/quota endpoint, or provider-enforced dollar ceiling. An application call/token limit can bound the experiment's requests, but it cannot guarantee a USD maximum when prices and the billing treatment of failed or timed-out calls are unknown. Run the required 2,000 distinct-document gate locally while these cloud conditions are unresolved. Keep ICORE limited to small, explicitly bounded synthetic or public-document diagnostics with `api_cost_usd: null`.

This is a spend/data-policy decision, not an assessment of ICORE extraction quality or a claim that the provider has no private billing controls.

## Evidence checked

| Source | Observation | Limit |
| --- | --- | --- |
| Saved authenticated [ICORE synthetic pilot](ICORE_SYNTHETIC_PILOT.json) and [six-public-PDF pilot](ICORE_VRDU_SIX_PILOT.json) | The model catalog advertised capabilities and successful chat responses reported token counts. Neither receipt contained a model USD rate or settled charge. Five of six public-PDF chat attempts failed without a response usage record; whether any were processed or billed remotely is unknown. | Token usage on successful responses is not an invoice, account balance, or ceiling. Upstream vendors' model prices cannot be substituted for ICORE's prices. |
| Unauthenticated `GET /innobot-api/v1/openapi.json` and `GET /innobot-api/v1/models` at the user-supplied ICORE host, repeated 2026-10-12 | Both returned HTTP 401 JSON. No credential, prompt, or document was sent for this audit. | These responses do not establish whether authenticated billing documentation or quota APIs exist. No such endpoint has been verified here. |
| [Innobot Health platform page](https://innobothealth.com/platform) | Describes ICORE as part of the platform and contains an *illustrative* revenue-cycle transaction price. | The transaction illustration is not an ICORE model-token/API price. |
| [Innobot Health privacy policy](https://innobothealth.com/privacy-policy) | Its stated scope is the `innobothealth.com` website and its subdomains; it describes website contact/analytics retention and says contracted health-data processing is governed by a separate BAA. | It does not specify retention, training use, subprocessors, region, or deletion for requests to the separate `.us` API host. Do not infer those guarantees from website terms or client-managed chat state. |
| [Innobot Health terms](https://innobothealth.com/terms-and-conditions/) | The public terms cover the site and public demos; commercial subscriptions, services, and BAAs are governed by separate executed agreements. | They are not an API rate card, data-processing agreement, or proof of a hard quota. |

Public searches targeted at ICORE API pricing, billing, usage, quota, and data terms produced no verifiable ICORE-specific document on 2026-10-12. The account owner's private dashboard or contract may contain information unavailable to this audit. The user-provided connection screen and saved pilot mention a shared allowance and ICORE rates, but provide no per-model numbers, billing basis, remaining balance, or statement that spending is rejected at a ceiling.

## Small diagnostic guardrail

Until the missing terms are supplied, keep each *synthetic/public-data* diagnostic small and precommitted. The completed capability diagnostic had **six** calls with at most 1,024 requested output tokens per call. The separately frozen public-document development pilot authorized in this task may attempt at most **18** calls, each with at most **12,000 prompt characters / 14,000 UTF-8 prompt bytes** and **1,536 requested output tokens**, a 100,000 *reported* prompt-plus-completion-token ceiling, one in-flight call, and zero automatic retries. These limits bound attempted requests and requested output, **not actual billed tokens or USD**. Stop on the first ambiguous timeout/connection loss, missing usage receipt, unexpected model, or cap breach. Record attempts, response usage, latency, failures, and unknown charges. Do not silently retry a request whose response was lost. Neither diagnostic is authorization to aggregate repeated pilots into an uncapped corpus run.

## Conditions for a cloud corpus gate

Before starting any ICORE-backed 2,000-document evaluation, require all of the following and preserve their dated evidence with the run manifest:

1. The account owner's **current ICORE rate card or contract** for the exact model IDs and modalities, including input/output units, minimums, surcharges, and charges for failures, timeouts, and retries; plus a **settled usage/charge export or read-only account billing view** to reconcile a small pilot. Keep the reported cost unknown until reconciliation succeeds.
2. A **provider-enforced hard USD cap** on that credential/account, with rejection at the ceiling, or a provider-confirmed prepaid balance that cannot overdraft. A notification threshold, local estimated-token cap, or dashboard graph is not a hard ceiling. Set the ceiling to the user's chosen budget, reserve headroom for in-flight requests, and keep concurrency and retries bounded. Verify the control's scope and behavior before the corpus run.
3. For private or regulated documents, the applicable **API data-processing terms** covering retention/deletion, model training, subprocessors, processing location, and any required BAA/DPA and tenant authorization. Public benchmark documents still need appropriate dataset-use rights and should be the first cloud quality set.
4. A frozen evaluation plan and small pilot showing acceptable transport reliability and source-grounded extraction. The old six-PDF run's five connection failures cannot justify bulk traffic.

**Blocking condition:** if any of the rate/billing evidence, enforceable ceiling, applicable data rights, or reliability gate is missing, the ICORE 2,000-document cloud gate stays disabled. The local 2,000-document gate can continue. The next practical step is for the account owner to export the ICORE model price/billing and spend-limit details and the API data terms from the account or contract; no credential should be placed in a report or repository.
