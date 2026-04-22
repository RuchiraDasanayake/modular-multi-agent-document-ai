# Start Here

This file is for the team, not just for AI tools.

## Current Problem

The repo has grown to the point where code is being added faster than the team understands it. That is the main risk now, not coding speed.

## What To Do First

Before anyone adds new code, agree on these three things for the current task:

1. Which service owns the task.
2. Which teammate is responsible.
3. What output proves the task works.

If those three are not clear, do not start coding yet.

## Service Map

- `ahmn_core/`: policy learning and memory logic
- `guardrails/`: hallucination and schema validation
- `xai_hitl/`: explainability and human feedback
- `idpo/`: document processing orchestration
- `gateway/`: auth and API routing
- `frontend/`: web UI

## Team Rule For AI Coding

Use AI to accelerate implementation, not to decide architecture blindly.

For every task, write a short task note before prompting Codex:

```text
Task:
Owner service:
Files expected to change:
Input:
Expected output:
How we will test it:
```

That note is the contract. If the AI starts changing unrelated files, stop and reset the task.

If the team changes the project goal or phase, update these docs before starting the next major coding task:

1. `docs/PROJECT_DIRECTION.md`
2. `docs/SYSTEM_CONTRACT.md`
3. the active cleanup or plan doc
4. `docs/SYSTEMATIC_REDUCTION_PLAN.md` if the cleanup order or decision method changed

## Minimum Workflow

1. Read `README.md`.
2. Read `CONTRIBUTING.md`.
3. Read `AGENTS.md`.
4. Open only the service folder relevant to the task.
5. Read existing tests in that service before writing new code.
6. Make the change.
7. Run the smallest test that proves it works.
8. Commit with a clear message.

## Good First Tasks

Start with one small task in one service only. Good examples:

- fix one failing test
- document one API route
- trace one frontend page to its backend endpoint
- add one missing validation test
- clean one duplicated function

Do not start with a major redesign.

## Suggested Next Step

Pick one service and create a short ownership and backlog note for it. If you want, Codex can help generate that next.

## If Goals Change

Before coding against a new direction, write this down:

```text
Date:
What changed:
Why it changed:
What is now in scope:
What is now out of scope:
Which docs were updated:
Which files are likely affected next:
```

## Reduction Rule

During the current phase, do not start a cleanup task with only a vague statement like:

- "make it better"
- "simplify this"
- "clean up the UI"

Write the section note in this stricter form:

```text
Section:
Owner service:
Cleanup type:
Files in scope:
Classification:
Primary action:
Acceptance check:
```

If the task note does not say whether the target should be kept, simplified, quarantined, or removed, the task is not ready.
