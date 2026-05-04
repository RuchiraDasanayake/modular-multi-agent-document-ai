"""
Generate presentation-ready charts from results.json.

Outputs (PNG, 1920x1080 / 16:9, slide-ready):
    charts/01_overall_accuracy.png      — Big-number headline
    charts/02_per_category_accuracy.png — Bar chart of per-category accuracy
    charts/03_latency_breakdown.png     — Bar chart showing 12x speedup on rule handlers
    charts/04_handler_distribution.png  — Donut chart of which handler answered
    charts/05_failure_modes.png         — Stacked bar of failure-mode breakdown

All charts use a consistent SLIIT-style palette and large fonts (24pt+) so
they read at the back of an exam-room projector.
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT = Path(__file__).resolve().parent
CHARTS = ROOT / "charts"
CHARTS.mkdir(exist_ok=True)
RESULTS = json.loads((ROOT / "results.json").read_text())

# ── Style ──────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 14,
    "axes.titlesize": 22,
    "axes.labelsize": 16,
    "xtick.labelsize": 14,
    "ytick.labelsize": 14,
    "legend.fontsize": 14,
    "figure.dpi": 150,
})

PALETTE = {
    "yes_no_legal":        "#10b981",  # emerald — best performer
    "factual_extractive":  "#3b82f6",  # blue
    "synthesis":           "#8b5cf6",  # violet
    "numerical":           "#f59e0b",  # amber — has the bug
    "primary":             "#1e3a8a",  # SLIIT navy
    "accent":              "#ea580c",  # SLIIT orange
    "neutral":             "#64748b",
    "good":                "#10b981",
    "bad":                 "#ef4444",
}

CAT_LABEL = {
    "yes_no_legal":       "Yes/No Legal",
    "factual_extractive": "Factual Extractive",
    "synthesis":          "Synthesis",
    "numerical":          "Numerical",
}


def per_category_stats():
    counts: dict[str, dict[str, float]] = {}
    for r in RESULTS["per_question"]:
        c = r["category"]
        d = counts.setdefault(c, {"total": 0, "correct": 0, "latency_sum": 0.0,
                                  "conf_sum": 0.0, "rule_hits": 0, "bart_hits": 0})
        d["total"] += 1
        if r["is_correct"]:
            d["correct"] += 1
        d["latency_sum"] += r["latency_seconds"]
        if r["confidence"] >= 0:
            d["conf_sum"] += r["confidence"]
        if r["latency_seconds"] < 5:
            d["rule_hits"] += 1
        else:
            d["bart_hits"] += 1
    for d in counts.values():
        d["accuracy"] = d["correct"] / d["total"] * 100
        d["avg_latency"] = d["latency_sum"] / d["total"]
        d["avg_conf"] = d["conf_sum"] / d["total"]
    return counts


# ── 01. Overall accuracy headline ──────────────────────────────────────
def chart_overall():
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis("off")

    overall = RESULTS["overall"]
    acc = overall["accuracy_pct"]
    correct = overall["correct"]
    total = overall["total"]
    avg_lat = overall["avg_latency_seconds"]

    # Big number
    ax.text(0.5, 0.62, f"{acc:.1f}%", ha="center", va="center",
            fontsize=200, fontweight="bold", color=PALETTE["primary"])
    ax.text(0.5, 0.40, f"Answer Accuracy", ha="center", va="center",
            fontsize=36, color=PALETTE["neutral"])
    ax.text(0.5, 0.30,
            f"{correct} / {total} questions correct on the Financial Transactions Reporting Act benchmark",
            ha="center", va="center", fontsize=20, color=PALETTE["neutral"])
    ax.text(0.5, 0.18, f"Average response time: {avg_lat:.0f} seconds per question",
            ha="center", va="center", fontsize=18, color=PALETTE["neutral"], style="italic")

    # Footer
    ax.text(0.5, 0.05,
            "Source-grounded XAI Q&A System · Pathirana M.M. · IT4010 Research Project",
            ha="center", va="center", fontsize=14, color=PALETTE["neutral"])

    plt.tight_layout()
    out = CHARTS / "01_overall_accuracy.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved {out}")


# ── 02. Per-category accuracy ──────────────────────────────────────────
def chart_per_category_accuracy():
    stats = per_category_stats()
    order = ["yes_no_legal", "factual_extractive", "synthesis", "numerical"]

    fig, ax = plt.subplots(figsize=(16, 9))
    cats = [CAT_LABEL[c] for c in order]
    accs = [stats[c]["accuracy"] for c in order]
    colors = [PALETTE[c] for c in order]
    counts = [(stats[c]["correct"], stats[c]["total"]) for c in order]

    bars = ax.barh(cats, accs, color=colors, edgecolor="white", linewidth=2)
    ax.set_xlim(0, 110)
    ax.set_xlabel("Accuracy (%)", fontsize=18)
    ax.set_title("Accuracy by Question Category — Full System (n=30)",
                 fontsize=24, fontweight="bold", pad=20)

    # Value labels
    for bar, acc, (c, t) in zip(bars, accs, counts):
        ax.text(acc + 1, bar.get_y() + bar.get_height() / 2,
                f"  {acc:.0f}%   ({c}/{t})", va="center", fontsize=16, fontweight="bold")

    # Annotation: best vs problem area
    ax.annotate("Specialised handler\n→ deterministic answer",
                xy=(86, 0), xytext=(60, 0.55),
                fontsize=13, color=PALETTE["good"], fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=PALETTE["good"], lw=2))
    ax.annotate("Handler-ordering bug\n(documented finding)",
                xy=(46, 3), xytext=(58, 3.45),
                fontsize=13, color=PALETTE["bad"], fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=PALETTE["bad"], lw=2))

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.invert_yaxis()
    plt.tight_layout()
    out = CHARTS / "02_per_category_accuracy.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved {out}")


# ── 03. Latency breakdown — the speedup story ──────────────────────────
def chart_latency():
    stats = per_category_stats()
    order = ["yes_no_legal", "factual_extractive", "numerical", "synthesis"]

    fig, ax = plt.subplots(figsize=(16, 9))
    cats = [CAT_LABEL[c] for c in order]
    latencies = [stats[c]["avg_latency"] for c in order]
    colors = [PALETTE[c] for c in order]

    bars = ax.bar(cats, latencies, color=colors, edgecolor="white", linewidth=2, width=0.6)
    ax.set_ylabel("Average response time (seconds)", fontsize=18)
    ax.set_title("Latency by Category — Specialised Handlers Are 12× Faster",
                 fontsize=24, fontweight="bold", pad=20)

    for bar, lat in zip(bars, latencies):
        ax.text(bar.get_x() + bar.get_width() / 2, lat + 2,
                f"{lat:.1f}s", ha="center", fontsize=18, fontweight="bold")

    # Highlight the speedup
    speedup = stats["synthesis"]["avg_latency"] / stats["yes_no_legal"]["avg_latency"]
    ax.annotate("",
                xy=(0, stats["yes_no_legal"]["avg_latency"]),
                xytext=(3, stats["synthesis"]["avg_latency"]),
                arrowprops=dict(arrowstyle="<|-|>", color=PALETTE["accent"], lw=3))
    ax.text(1.5, (stats["synthesis"]["avg_latency"] + stats["yes_no_legal"]["avg_latency"]) / 2 + 5,
            f"{speedup:.1f}× speedup\nfor rule-handled\nquestions",
            ha="center", fontsize=16, fontweight="bold", color=PALETTE["accent"],
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor=PALETTE["accent"], linewidth=2))

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(0, max(latencies) * 1.25)
    plt.tight_layout()
    out = CHARTS / "03_latency_breakdown.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved {out}")


# ── 04. Handler distribution donut ─────────────────────────────────────
def chart_handler_distribution():
    # Infer handler from latency — < 5s = rule handler hit
    rule_count = sum(1 for r in RESULTS["per_question"] if r["latency_seconds"] < 5)
    bart_count = sum(1 for r in RESULTS["per_question"] if r["latency_seconds"] >= 5)

    fig, ax = plt.subplots(figsize=(16, 9))

    sizes = [rule_count, bart_count]
    labels = [f"Rule handlers\n(Numerical / Legal Yes-No)",
              f"BART generative model\n(with TF-IDF retrieval)"]
    colors = [PALETTE["good"], PALETTE["primary"]]
    explode = (0.05, 0)

    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, explode=explode,
        autopct=lambda p: f"{p:.0f}%\n({int(round(p * sum(sizes) / 100))} questions)",
        startangle=90, wedgeprops=dict(width=0.45, edgecolor="white", linewidth=4),
        textprops=dict(fontsize=16),
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontweight("bold")
        at.set_fontsize(15)

    ax.set_title("Which Pipeline Stage Answered Each Question?",
                 fontsize=24, fontweight="bold", pad=20)

    # Centre text
    ax.text(0, 0, f"30\nquestions", ha="center", va="center",
            fontsize=28, fontweight="bold", color=PALETTE["primary"])

    plt.tight_layout()
    out = CHARTS / "04_handler_distribution.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved {out}")


# ── 05. Hallucination examples — before/after ──────────────────────────
def chart_hallucination_examples():
    examples = [
        {
            "q": "How long can cash be detained without a court order?",
            "bad": "In the US, cash can be detained for up to 72 hours after a seizure without a court order…",
            "good": "5 working days.",
            "type": "Foreign-law hallucination"
        },
        {
            "q": "Can a customer open an anonymous bank account?",
            "bad": "Yes, you can open an anonymous bank account…",
            "good": "No. According to the document: 'No Institution shall open, operate or maintain… any anonymous account…'",
            "type": "Polarity inversion"
        },
        {
            "q": "What is the maximum penalty in rupees for non-compliance?",
            "bad": "105 rupees.",
            "good": "1 million rupees.",
            "type": "Fabricated number"
        },
    ]

    fig, axes = plt.subplots(len(examples), 1, figsize=(16, 12))
    fig.suptitle("Hallucination Examples — Before vs. After Source Grounding",
                 fontsize=22, fontweight="bold", y=0.995)

    for ax, ex in zip(axes, examples):
        ax.axis("off")
        ax.text(0.01, 0.85, f"Q: {ex['q']}", fontsize=15, fontweight="bold",
                color=PALETTE["primary"], wrap=True)

        # Bad answer
        ax.text(0.01, 0.55, "Vanilla BART (baseline):", fontsize=12,
                fontweight="bold", color=PALETTE["bad"])
        ax.text(0.01, 0.42, f"“{ex['bad']}”", fontsize=13,
                color=PALETTE["bad"], style="italic", wrap=True)
        ax.text(0.95, 0.42, "✗", fontsize=28, color=PALETTE["bad"], ha="right")

        # Good answer
        ax.text(0.01, 0.22, "Our system (source-grounded):", fontsize=12,
                fontweight="bold", color=PALETTE["good"])
        ax.text(0.01, 0.10, f"“{ex['good']}”", fontsize=13,
                color=PALETTE["good"], wrap=True)
        ax.text(0.95, 0.10, "✓", fontsize=28, color=PALETTE["good"], ha="right")

        # Tag
        ax.text(0.99, 0.85, ex["type"], fontsize=11, ha="right",
                color="white",
                bbox=dict(boxstyle="round,pad=0.4", facecolor=PALETTE["accent"]))

        # Divider
        ax.axhline(y=-0.02, color=PALETTE["neutral"], linewidth=1, alpha=0.3)

    plt.tight_layout()
    out = CHARTS / "05_hallucination_examples.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved {out}")


if __name__ == "__main__":
    chart_overall()
    chart_per_category_accuracy()
    chart_latency()
    chart_handler_distribution()
    chart_hallucination_examples()
    print(f"\nAll charts written to: {CHARTS}")
    print(f"Drop these PNGs straight into PowerPoint slides.")
