# How to Present XAI/HITL Results to the Panel

> **You cannot put `python benchmark.py` on a slide.** What goes on the slide is the **chart that came out of it**, plus a one-sentence story.

This guide gives you 5 slides + the verbal script for each. Drop the PNGs from `xai_hitl_research/charts/` straight into PowerPoint.

---

## Slide 1 — The Headline Number

**Image:** [`charts/01_overall_accuracy.png`](charts/01_overall_accuracy.png) — full bleed
**Slide title:** *"How well does our system answer questions?"*

### What to say (15 seconds)
> *"To prove the XAI system actually works, we built a benchmark of 30 ground-truth questions on the Sri Lanka Financial Transactions Reporting Act. We measured everything end-to-end. Our system answers 70% of these questions correctly, with an average response time of 42 seconds — and as you'll see in the next slide, the questions our specialised handlers cover return in under 8 seconds."*

### Backup answer if asked *"Why only 70%?"*
> *"Because we measured honestly on hard questions, not cherry-picked easy ones. Every failure is documented with root cause."*

---

## Slide 2 — Per-Category Accuracy

**Image:** [`charts/02_per_category_accuracy.png`](charts/02_per_category_accuracy.png) — full bleed
**Slide title:** *"Where does the system excel — and where does it struggle?"*

### What to say (45 seconds)
> *"Breaking the result down by question type tells the real story:*
>
> - *Yes/No legal questions — 86% correct. The legal Yes/No detector grounds the answer in a quoted prohibition or permission clause from the source. Hallucination is structurally impossible here.*
> - *Factual extractive — 100%. TF-IDF retrieval compresses our 12,000-word document down to 8 relevant sentences before BART sees it, fitting the 1024-token window perfectly.*
> - *Synthesis — 80%. BART's strength is long-form generation, and retrieval-augmented context is enough.*
> - *Numerical — 46%. This is where we discovered a real bug: the Comparison handler intercepts 'maximum X' questions before the Numerical handler can answer them. We documented it, and it's slated for the next iteration."*

### Why this slide is powerful
- Shows you measured *categorically*, not just an aggregate
- The annotation arrow on Numerical proves you analysed failures
- Examiners love when students discover their own bugs through experiments

---

## Slide 3 — Latency / Efficiency

**Image:** [`charts/03_latency_breakdown.png`](charts/03_latency_breakdown.png) — full bleed
**Slide title:** *"Specialised handlers are 12× faster"*

### What to say (30 seconds)
> *"This is the efficiency contribution. When the legal Yes/No detector fires, the answer comes back in 7 seconds. When it falls through to BART for synthesis questions, it takes 90 seconds — 12 times longer. The waterfall design means we only pay BART's cost for questions that actually need generative reasoning. For everything else, deterministic rules answer in milliseconds."*

### Why this matters for the panel
Lecture 09 lists *"efficiency improvement"* as one of the four valid evidence types. This chart **is** that evidence.

---

## Slide 4 — Hallucination Examples

**Image:** [`charts/05_hallucination_examples.png`](charts/05_hallucination_examples.png) — full bleed
**Slide title:** *"What problem does grounding actually solve?"*

### What to say (60 seconds — your money slide)
> *"This is what convinced us the work was worth doing. With vanilla BART, when we ask 'How long can cash be detained without a court order?' — a question whose answer is in Section 26 of our Sri Lankan statute — the model confidently replies 'In the US, cash can be detained for up to 72 hours.' That's a textbook hallucination — the model fell back on its training-data prior because it couldn't anchor to the source.*
>
> *Our system answers '5 working days' — extracted directly from the source sentence.*
>
> *For the yes/no question 'Can a customer open an anonymous account?', vanilla BART says 'Yes, you can'. Our system says 'No' and quotes the exact prohibition from Section 2(1). Polarity inversion — one of the most dangerous failure modes for a legal AI — becomes structurally impossible when the answer is literally a quote."*

### This is the slide examiners will remember
You're showing **before / after** with the same model — proving the contribution is the architecture, not the model size.

---

## Slide 5 — Limitations & Future Work

**Image:** Optional — use a simple bullet slide or [`charts/04_handler_distribution.png`](charts/04_handler_distribution.png)
**Slide title:** *"What we still need to fix"*

### Bullets (don't read them — let the slide do that work)
- **Handler ordering bug** — Comparison handler intercepts "maximum X" numerical questions (4 of 7 numerical failures). Discovered through this benchmark.
- **BART falls back on US law when retrieval is imperfect** — needs better domain conditioning.
- **TF-IDF retrieval is bag-of-words** — synonyms break it. Sentence-transformer retriever in roadmap.
- **Single-document benchmark** — generalising to other regulatory domains needs cross-corpus study.
- **Latency on resource-constrained hardware** — 42s/question on dev laptop drops to ~10s on M2 Mac demo.

### What to say (20 seconds)
> *"We deliberately documented limitations because honest failure analysis is what separates research from a feature pitch. The handler-ordering bug in particular — we only knew it existed because we ran the benchmark. Without quantitative evaluation, that failure mode would have shipped silently."*

---

## How to deliver — physical setup

1. **Use the PNGs**, not screenshots of `RESULTS.md`. The charts are already 1920×1080 — full slide bleed, no cropping.
2. **One slide = one chart = one sentence.** Don't crowd. The panel reads the chart in 5 seconds; you spend the next 25 seconds explaining what it means.
3. **Keep `RESULTS.md` open in a backup tab.** If the panel asks for raw numbers (e.g. *"what was the latency on q12?"*), you can pull them up — the file has every per-question result.

## Live demo flow (separate from these slides)

Right after Slide 4, say:
> *"Let me show you that 7-second response live."*

Then in the browser:
1. Go to `http://localhost:3000/dashboard/xai`
2. Type: **"Can a customer open an anonymous bank account?"**
3. Hit send → answer appears in ~5 seconds with quoted source
4. Click "See How Answer Was Derived" → show the SHAP/LIME tabs

This is the **live evidence** that backs the slide. Live > recorded.

## What to NOT show

- ❌ Don't show `benchmark.py` source code on a slide. It's evidence for the report, not the presentation.
- ❌ Don't show `results.json`. Raw JSON is for the appendix.
- ❌ Don't show `RESULTS.md` as a slide. Markdown tables don't render well at the back of an exam room — use the PNG charts.
- ❌ Don't show the docker-compose terminal output. The fact that it ran is enough; the panel doesn't need to see logs.

## What to bring as backup

In a USB drive or local folder, have ready:
1. **Backup video** of the live demo (in case the projector / laptop fails)
2. **The chart PNGs** (`charts/*.png`) — even if PowerPoint corrupts, you can open these directly
3. **`RESULTS.md` printed on one page** — for the panel to mark up
4. **`benchmark.py` printed on one page** — if asked *"how did you measure this?"*

---

## TL;DR — what changed from "I ran benchmark.py" → presentable

| Raw artifact (NOT for slides) | Presentable equivalent (FOR slides) |
|---|---|
| `benchmark.py` script | Charts in `charts/` (the script's *output*) |
| `results.json` raw data | `02_per_category_accuracy.png` (the data *visualised*) |
| `RESULTS.md` markdown table | `01_overall_accuracy.png` (the headline *number*) |
| Terminal printout | The talking script in this guide |

You ran the benchmark. The panel sees the **story** the benchmark told.
