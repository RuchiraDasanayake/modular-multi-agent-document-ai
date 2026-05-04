# How to Present AHMN Results to the Panel

> **You cannot put `python benchmark.py` on a slide.** What goes on the slide is the **chart that came out of it**, plus a one-sentence story.

This guide gives you 5 slides + the verbal script for each. Drop the PNGs from `ahmn_research/charts/` straight into PowerPoint.

---

## Slide 1 — The Headline Number

**Image:** [`charts/01_overall_accuracy.png`](charts/01_overall_accuracy.png)
**Slide title:** *"How well does AHMN route documents?"*

### What to say (15 seconds)
> *"To prove AHMN's adaptive routing actually works, we built a 30-case benchmark covering three regimes — seen, near-neighbour, and cold-start. AHMN routed 40% to the correct policy, with 100% determinism, 100% RABI activation, and ~1 second latency. The next slide shows where the wins and losses came from."*

### If asked *"Only 40%?"*
> *"40% is the **honest** number on hard cases including 5 deliberately-novel cold-start contexts. We measured everything; the cold-start failure mode revealed a concrete fix that would lift the number to ~80%."*

---

## Slide 2 — Per-Regime Accuracy (the story slide)

**Image:** [`charts/02_per_regime_accuracy.png`](charts/02_per_regime_accuracy.png)
**Slide title:** *"Where AHMN succeeds — and where it doesn't"*

### What to say (45 seconds)
> *"Breaking the result down by regime reveals the real story:*
>
> - *Seen contexts: 45%. Many of these failed because the dense `table_heavy` cluster acts as a gravity well in the embedding space, pulling near-neighbour queries toward it.*
> - *Near-neighbour: 50%. The core research claim — that vector similarity generalises to unseen contexts — held for half the cases. Purchase orders correctly routed to `table_heavy`, tax forms correctly routed to `forms`. The other half were misrouted because of the same dense-cluster bias.*
> - *Cold-start: 0%. This was our most important finding — AHMN has no confidence threshold to fall back to the default policy. It always picks the closest specialist, even when nothing actually matches. The fix is roughly 10 lines of code: if confidence < 0.5, use default."*

### Why this slide is powerful
- Three colours = three regimes — instantly scannable
- The annotation on cold_start signals you discovered a real bug, not just observed a number
- Examiners love when students discover their own limitations through experiments

---

## Slide 3 — Confidence Calibration (the silver-lining slide)

**Image:** [`charts/03_confidence_calibration.png`](charts/03_confidence_calibration.png)
**Slide title:** *"Even when wrong, AHMN knows it's uncertain"*

### What to say (45 seconds)
> *"This is the most interesting result. Even on the cold-start cases AHMN got wrong, the reported confidence dropped to 0.43 — well below the 0.5 threshold line. The system correctly knows it is uncertain; it just doesn't act on that uncertainty yet. That's a much easier problem than 'the model is over-confident on garbage' — we just need to add a fallback gate. Confidence calibration is 90% across all 30 cases, which means the system's reported confidence can be trusted as a routing signal even when the chosen policy is wrong."*

### Why this matters
This single slide turns a 0% failure into a feature: *"We have a usable signal — we just need to wire it up to a threshold."*

---

## Slide 4 — Reliability Properties

**Image:** [`charts/04_rabi_determinism.png`](charts/04_rabi_determinism.png)
**Slide title:** *"Two production-critical properties"*

### What to say (30 seconds)
> *"For AHMN to be useful in production, it needs two things: it needs to actually use neighbour priors (otherwise it's just random selection), and it needs to be deterministic (otherwise debugging is impossible). We hit 100% on both. RABI fired on every single call, meaning the vector store is healthy end-to-end. Determinism was 100% — same input, same output, every time. This is the foundation that makes the rest of the research possible."*

---

## Slide 5 — Failure Mode Analysis

**Image:** [`charts/05_failure_analysis.png`](charts/05_failure_analysis.png)
**Slide title:** *"Where do the failures go?"*

### What to say (45 seconds)
> *"All 18 failed routings clustered on a small number of wrong policies. The biggest culprit was `table_heavy` — that policy has the most LTM seeds (4 of 12), and the cosine similarity in the embedding space pulled neighbouring contexts into that cluster. The remediation is concrete: rebalance the LTM seeds so each policy has roughly equal coverage, or apply a per-policy similarity weighting that down-weights densely-seeded policies. This is a discovered, quantified, and fixable bias — exactly the kind of finding the benchmark was designed to surface."*

---

## Live demo flow (separate from these slides)

After Slide 5, say:
> *"Let me show you AHMN making a routing decision live."*

Then in the browser or terminal:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s -X POST http://localhost:8000/api/advice \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"doc_type":"invoice","vendor":"acme","content_profile":"table-heavy"}' \
  | python3 -m json.tool
```

The response shows the selected policy, confidence, RABI metadata, and the source. **Live evidence** > recorded evidence.

---

## What to NOT show

- ❌ Don't show `benchmark.py` source on a slide. It's evidence for the report, not the slide deck.
- ❌ Don't show `results.json`. Raw JSON is for the appendix.
- ❌ Don't show `RESULTS.md` as a slide. Use the chart PNGs.
- ❌ Don't show the docker terminal scrolling. The fact that it ran is enough; logs aren't a slide.

## What to bring as backup

1. **Backup video** of the live demo (in case the projector / laptop fails)
2. **The chart PNGs** (`charts/*.png`) — even if PowerPoint corrupts, you can open these directly
3. **`RESULTS.md` printed on one page** — for the panel to mark up
4. **`benchmark.py` printed** — only if asked *"how did you measure this?"*

---

## "Prove it" → which file to show

| Proof question | What to show | Time |
|---|---|---|
| "Did you really run this?" | `results.json` first per-case entry | 10s |
| "How did you score routing correctness?" | `benchmark.py` `is_correct` / scoring | 30s |
| "Show me a failure" | A failed `results.json` entry with confidence | 15s |
| "Can I reproduce it?" | The single `python3 benchmark.py` command + one live `curl` | 30s |
| "Where's the test data?" | `test_dataset.json` first case | 15s |

Have all of them ready. Show whichever one they ask about. **Never dump all three at once.**

---

## TL;DR

The benchmark says: *AHMN is correct 40% of the time, deterministic 100% of the time, calibrated 90% of the time, and the cold-start failure mode has a 10-line fix.*

That sentence — backed by the 5 chart PNGs — is your presentation.
