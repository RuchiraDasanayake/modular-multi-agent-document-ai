# Post-change v2 evaluation: operator pause and resume

Date: 17 October 2026. This is an operational audit note, not an accuracy report.

The user requested a processing pause, then explicitly requested continuation. An external, audited operator action cleared only that pause. The frozen extraction code, runtime, source inventory, schemas, model profile and request limits were unchanged.

## Evidence identity

- Frozen extraction commit: `a5ccea2fcf7c1a67c78e16449922fb4a87f9b012`.
- Protocol SHA-256: `4800e2279a1b1516a5f09c4631f5940ce643110a3095f95a2dfd2477457578b5`.
- Applied resume-intent receipt SHA-256: `1ccf748e873da9f531201a0727300f97851d5409fc28a8ef38918abd1d2d841a`.
- Frozen limits remain 2,500 requests globally, four per source and four workers.

## State preserved at resumption

| Ledger item | Count |
| --- | ---: |
| Selected distinct originals | 2,000 |
| Sealed sources | 694 |
| Uncertain sources | 3 |
| Unstarted sources | 1,303 |
| Started sources | 0 |
| Replied attempts | 703 |
| Uncertain attempts | 3 |
| Pending begun attempts | 0 |

There were 678 valid full-coverage outputs at the pause. This is a processing count, not measured accuracy. Every uncertain source and completed outcome was retained; none was made eligible for another request.

Three of the sealed sources retain `worker_execution_failed` outcomes caused by the pause. Their calls were blocked before a request began. The product recorded the `GateStopped` wrapper error, while the paid-attempt recorder correctly recorded no begun request. The runner subsequently rejected the differing call counts during product receipt verification. These sources remain failures with no valid metrics; they were not repaired, excluded or replayed. The one reply completed after the pause had one SDK attempt and no provider error.

## Operator procedure

The stock frozen runner does not accept `user_requested_pause` through its provider-stop acknowledgement option. A separate script therefore acquired the existing operating-system run lock, verified the frozen code/runtime/source bytes and existing sealed receipts, and asserted the exact stopped ledger state. It backed up the ledger and tested the proposed transaction on the copy before applying it.

The transaction appended `operator_user_pause_resume`, bound to the receipt hash above, and cleared only the matching `stop_reason`. It preserved all source and attempt rows, prior controls, request limits and the zero consecutive-transport-failure counter. A full before/after equality check verified those invariants. The unchanged runner then resumed only unstarted sources.

This action performed no inference and opened no gold annotations. It did not change the frozen analysis plan. The final campaign must reach a complete terminal seal and pass independent evidence verification before any scoring or paper update.

## Verification and interpretation

The existing final verifier retains the control event in the sealed summary and requires it to match the seal's controls. It does not independently authorize the custom event; the external intent/application receipts provide that audit trail. It verifies the failed sources' outcome and artifact hashes, leaves their metrics absent and does not count them as valid outputs. A completed campaign can be verified without passing its operational quality gate.

The preregistered recall scorer retains every selected source in the denominator. Failed and uncertain originals receive empty predictions. This run reuses an existing operational cohort, so any eventual recall result is a descriptive regression result, not evidence from a new unseen holdout. Processing time also includes the interruption and is not an isolated throughput benchmark. Until verification and scoring finish, the conference artifacts retain the previously completed studies.
