# ADR 0004: Single-host recovery for product extraction runs

## Context

The frontend launches `process-auto` as a child process (or invokes the private Docker worker through a Node bridge). A frontend restart can leave a run marked `running` indefinitely. A read request must not change that run merely because another frontend process owns it. A completed `run.json` is useful for displaying a verified result, but an HTTP GET should not perform the terminal state transition or delete staged input.

## Decision

Each new product run writes an owner lease beside its run record. The owning frontend process renews it every 15 seconds; it expires after five minutes without a renewal. The run record remains the immutable start record. Completion publishes a separate terminal JSON file with an exclusive hard link, so a child exit callback and a recovery scan cannot overwrite each other's terminal decision. The frontend reads the terminal file when present. It may display a fully validated `run.json` result before terminal publication, without writing anything during GET.

A recovery scan runs every 30 seconds in the Node frontend process, started by Next.js instrumentation. The scan also runs at the start of a new extraction POST before checking for an existing run. It validates completed artifacts and publishes success if they are complete. After a lease expires, it publishes failed for an incomplete or invalid run, allowing a new run to be started. GET routes never invoke recovery. An expired run's staged input is retained because a surviving child or private worker may still be reading it; a completed or normally exited run removes its staged input.

## Limits

- This is single-host filesystem coordination, not a durable queue or distributed scheduler. The shared data volume must support atomic hard links and rename. Recovery requires a running frontend process and executes no sooner than the five-minute lease plus the scan interval after a crash.
- A frontend process stalled for over five minutes can lose its lease even if its child is still doing work. The old process cannot overwrite a published terminal record, but the still-running worker may occupy the private worker slot and cause a retried run to fail busy. Operators must treat this as an execution failure, not a document result.
- A successful completion marker remains subject to the existing artifact and source-hash validation. Invalid artifacts are never marked successful. A failed expired run keeps its staged input for later bounded cleanup; retention and quota enforcement remain future work.
- Starting two runs simultaneously for the same job is still not protected by a job-wide lock. This change only makes recovery and terminal decisions safe across frontend processes.

## Verification

Focused tests start a separate Node process that renews a foreign lease, verify GET and recovery leave its run untouched, stop that process, expire the lease, and verify explicit recovery creates one immutable failed terminal record. Existing artifact and review tests verify that a completed marker is displayed through a read-only GET and invalid artifacts remain inaccessible.
