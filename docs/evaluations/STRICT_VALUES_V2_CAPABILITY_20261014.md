# Keyed values v2: bounded provider capability check

Status: completed synthetic engineering check, 2026-10-14 local time. Classification: `research_evidence`, keep. This is not a real-document accuracy result or a default-profile change.

## Motivation and change

The verified 2,000-original operational campaign included 25 visual receipt replies that omitted requested fields. Its v1 provider schema allowed a subset of array entries, while the product correctly rejected incomplete local results. The explicit `strict_confirmed_values_v2` profile instead requires every confirmed field ID as an object property. Missing information uses null. Field-specific types, null-only linked-column wrapper metadata and complete keyed prompt examples agree with the local decoder.

The internal review representation is preserved. Missing/extra keys, duplicate JSON properties, invalid types, nonfinite values, invalid page references and invalid linked cells are rejected before projection. Raw-reply hashes refer to the actual provider response. V1 and default behavior are preserved.

## Frozen synthetic check

The protocol, self-authored receipt image and text, eight-field schema, expected values, exact request arguments and harness were pinned before two ICORE `innobot-luna-6` attempts. Settings: 4,096 output tokens, 180-second timeout, SDK retries zero, at most two attempts, exclusive durable reservation before each call, stop on uncertainty or invalid output. One request used the product text prompt/schema; the other used the exact prepared full-page visual request. The visual body was 47,034 bytes.

| Route | SDK attempts | Finish | Local v2 parser | Synthetic field matches | Input / output tokens |
| --- | ---: | --- | --- | ---: | ---: |
| Text | 1 | stop | valid | 8 / 8 | 1,163 / 347 |
| Visual | 1 | stop | valid | 8 / 8 | 2,063 / 385 |

Both included the absent discount as null and two linked columns with matching fixture rows. No provider errors, refusals or retries occurred. Currency cost is unknown. The field examples contain fixture values, and the image request also contains its exact self-authored transcript. These checks establish acceptance of these two requests and successful schema/parser round trips; they do not independently test inference, vision accuracy, general schema enforcement or improvement on real documents.

## Verification and limits

Independent read-only verification regenerated both requests from the pinned code, rehashed both raw replies, reran the actual parsers and fixture comparisons, and checked both reservation records. No further API calls were made. Independent code review checked three v1 text prompts and three full v1 visual requests/receipts against their pre-v2 versions byte-for-byte. Relevant root integration checks passed: 90 Python tests, 33 frontend tests, TypeScript compilation and the native launcher fixture.

Real-document omission rate and semantic quality remain separate development measurements. Required keys can still hold incorrect values or unjustified nulls. All visual outputs still require human review. The completed operational campaign and running paired quality study retain their original profiles and denominators.

## Pins

| Artifact | SHA-256 or Git commit |
| --- | --- |
| Tested implementation | `cee051bb759968f776ec7a57e4dbfa04e8c7ccd7` |
| Protocol | `c80cdcee292571c4d77b465d064b7624c0fed239452c78a6a1db7c5e42aa1d14` |
| Harness | `38f5547bd945d5165baebd14610cce3dd597074d451bd17801d97c496c54da81` |
| Summary | `bb8f6a6d507c2b713a997c4297820760a9844cda9075fceed6ef5059fc836c26` |
| Text request | `5f91c91a825526948efa96659c825520771eaa16a35fe7ba3d3966f3406737ea` |
| Visual request | `7ca3bf5c83d0ae422a7d919abd14f5ef81335f7e38dc20818e513539d7e3f75d` |
| Text reply | `4b056128a922e79bfd14a2e4833c684dbeba6875597719ebeed3c680b37fe26d` |
| Visual reply | `8cbc1e9ba908ce41e43074010bf3713c81512c84a22fec40bea47607cb52fbde` |

The private synthetic bundle is retained at the configured runtime evidence root under `handover-v1/strict-v2-capability-v1`; credentials and authentication headers are excluded.
