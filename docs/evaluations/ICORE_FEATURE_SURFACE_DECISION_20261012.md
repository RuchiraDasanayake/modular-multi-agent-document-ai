# ICORE feature surface and transport decision, 2026-10-12

## Decision

Keep ICORE as an **explicitly configured text-chat option** for bounded public or synthetic evaluation. Continue local JSON parsing, exact source-span verification, abstention, and human approval of proposed schemas. Do not enable strict provider schema enforcement, image inputs, embeddings, automatic retries, a USD cost estimate, or private-document submission based on the current evidence. Do not scale this provider to a corpus run yet.

This is a feature and reliability decision, not an extraction-quality comparison. The saved synthetic pilot has two fictional documents. The six-public-PDF pilot was connectivity-limited. Neither establishes a world-class or low-cost extraction claim.

## Evidence and its limits

| Evidence level | Source | What it establishes | What it does not establish |
| --- | --- | --- | --- |
| Provider-advertised | Two earlier authenticated ICORE `GET /models` responses, summarized in [the synthetic pilot](ICORE_SYNTHETIC_PILOT.json) | Nine model IDs and their advertised operations/modalities/format metadata at the time of the requests | That each advertised operation succeeds, enforces its contract, has a known price, or has suitable data terms |
| Empirically observed | Eight synthetic text-chat calls in [the synthetic pilot](ICORE_SYNTHETIC_PILOT.json) | `chat/completions` returned HTTP 200 and token usage for MiniMax M2.5 and Luna 6 without `response_format` | Strict JSON Schema, vision, embeddings, charge in USD, or general reliability |
| Empirically observed | [Six-public-PDF pilot](ICORE_VRDU_SIX_PILOT.json) and [transport follow-up](ICORE_CONNECTION_FOLLOWUP_20261012.md) | One successful schema call, five `APIConnectionError` failures without HTTP status, then one later tiny synthetic Luna call succeeded | The precise cause of the five failures or a failure-rate estimate |
| Public endpoint observation | Unauthenticated `GET` to `/innobot-api/v1/openapi.json`, `/innobot-api/docs`, and `/innobot-api/v1/models` returned HTTP 401 JSON; a public search found no ICORE-specific API/pricing/data-terms reference | Those paths did not provide public documentation during this audit | That authenticated documentation or private terms do not exist |
| Reference protocol only | [OpenAI Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat), [embeddings reference](https://developers.openai.com/api/reference/resources/embeddings/methods/create) | The wire shapes that an OpenAI-compatible service might implement | Any ICORE-specific support or guarantee |

The existing [product provider adapter](../../idpo/product_auto/provider.py) sends text-only `chat.completions.create` requests with `model`, `messages`, and `max_tokens`. It does not send `response_format`, image content parts, or embedding requests. It disables SDK retries and redacts exception messages. A provider feature should not be inferred from the SDK's ability to serialize it.

## Feature decision matrix

| Feature | Current ICORE evidence | Decision and validation gate |
| --- | --- | --- |
| Plain text schema/value chat | MiniMax M2.5 and Luna 6 returned valid JSON in the tiny synthetic pilot. Luna had 2/2 usable value replies; MiniMax had 1/2 because one reply hit `finish_reason=length`. The later six-public-PDF run had 5/6 transport failures. | Keep opt-in for bounded public/synthetic tests with strict parser, source spans, and review. Do not assume stable availability. |
| `response_format: {"type":"json_schema", ...}` | ICORE `/models` advertised `json_schema` and provider schema validation for `innobot-minimax-m2-5`. The pilot never sent `response_format`; the Luna 6 catalog did not advertise a schema guarantee. OpenAI documents this parameter and distinguishes strict schema adherence from older `json_object` mode, but that is not an ICORE guarantee. | **Disabled.** First use an offline mocked-wire test, then an authorized tiny synthetic MiniMax request with a strict schema, local independent JSON Schema validation, `finish_reason` and error recording. Test an extra-key temptation so prompt following alone cannot be mistaken for enforcement. Repeat once before claiming reliability. Never skip local type/evidence validation. |
| Vision input to chat | Catalog metadata advertised image input for Luna 6 and inline base64 JPEG/PNG for Luna Mantle, Terra Mantle, and Sonnet 5. OpenAI's chat reference allows `image_url` content parts with URL or base64 data. No ICORE image request was run. | **Disabled.** A future bounded test must use a newly generated synthetic image, explicit byte/page limits, and a model whose ICORE catalog advertises the exact image form. Check transport, output structure, and visual fact accuracy independently. No private PDFs while data terms remain unverified. |
| Text embeddings | Catalog advertised `/embeddings` for `innobot-titan-embed-v2` and `innobot-nova-embed`, one text input and 8,000 input bytes per request; Titan dimensions 256/512/1024 and Nova 256/384/1024/3072. No embedding call was run. OpenAI's reference describes `input`, optional `dimensions`, vector data, and token usage, but model-specific dimensions and behavior belong to ICORE. | **Disabled.** Only add retrieval if a measured evaluation shows benefit. A future one-input synthetic probe per selected model/dimension must check vector length, finite numbers, stable response shape, and usage. Cache/version vectors; do not assume cross-model comparability. |
| Image generation | ICORE catalog lists Core and Ultra image-generation models. | Exclude from document extraction; no accuracy or cost rationale exists for this workflow. |
| USD cost | Neither saved catalog model items nor chat response receipts contained a per-model USD rate or settled charge. Token usage was returned. No public ICORE rate card or billing export was verified. | Preserve `api_cost_usd: null`. Do not label provider calls free or convert tokens using upstream model prices. Obtain ICORE's current rate card or settled per-request ledger before a cost comparison or routing threshold. |
| Data handling | The catalog advertises client-managed conversation state and no stored-response operation for tested chat models. Retention, training use, and residency terms were not verified. | Keep private or regulated documents out of ICORE until provider terms are reviewed. Client-managed state does not prove the provider does not log requests. |

OpenAI's [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat) also notes refusals and incomplete generations as cases requiring application handling. Even successful ICORE strict-format testing would leave the product's source-grounding and review gates necessary.

## Transport finding

The six-public-PDF pilot used a 90-second timeout and zero SDK retries. Its five failures had no HTTP status: two ended after 76.923 and 81.054 seconds; three ended in 1.771, 1.297, and 3.660 milliseconds. Because the old pilot did not retain sanitized exception-cause classes, the evidence cannot isolate DNS, TLS, network, server socket closure, or response timeout. There was no observed HTTP 429 or 401 in those model-call failures. A later DNS/TLS check and one 1.639-second synthetic chat success rule out a *permanently* wrong base path, key class, or model ID; they do not prove reliable service. See the [transport follow-up](ICORE_CONNECTION_FOLLOWUP_20261012.md) for receipts.

Keep `max_retries=0` until ICORE documents idempotency and billing behavior for a request whose response is lost. On a future naturally occurring failure, record only the exception and cause **class names**, phase, elapsed time, HTTP status if any, and retry count. Do not log exception messages, credentials, prompts, provider reply text, or document content. A same-time DNS/TLS check may help distinguish host transport from application failure. Do not turn a one-off successful probe into a bulk reliability claim.

## Smallest future acceptance sequence

No model requests were made for this decision record. Any later probe is a separate, explicitly bounded run using synthetic data:

1. Mock the OpenAI SDK transport locally and assert exact request payloads for strict schema, base64 image, and embedding paths. Validate candidate responses with an independent JSON Schema library and the existing source-span rules. This verifies our client only.
2. If pricing and data terms are available, send at most two synthetic strict-schema MiniMax calls. Require HTTP success, `finish_reason=stop`, exact local schema validation, correct typed value, and zero unsupported fields. A failed or ignored `response_format` ends that branch.
3. If vision is still needed, send one tiny synthetic image to an image-capable advertised model. If retrieval is still needed, send one short synthetic embedding input per selected model. Keep each feature disabled until its own receipt passes.
4. Before changing routing or claiming lower cost, compare candidate quality on a frozen public holdout and reconcile token counts with ICORE rates or settled charges. Include latency, failures, reviews, and abstentions in the denominator.

The current recommendation is to spend the next product effort on source-grounded extraction and selective local parsing. ICORE remains a bounded optional model source, with its unverified features and unknown price represented as unknowns.
