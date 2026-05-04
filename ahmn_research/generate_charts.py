"""
Generate presentation-ready charts from results.json for AHMN.

Outputs (PNG, 1920x1080 / 16:9, slide-ready):
    charts/01_overall_accuracy.png        — Big-number headline
    charts/02_per_regime_accuracy.png     — Bar chart: seen vs near_neighbor vs cold_start
    charts/03_confidence_calibration.png  — Shows AHMN correctly lowers confidence on unknowns
    charts/04_rabi_determinism.png        — RABI usage + determinism summary
    charts/05_failure_analysis.png        — Confusion-style breakdown of failures
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
CHARTS = ROOT / "charts"
CHARTS.mkdir(exist_ok=True)
RESULTS = json.loads((ROOT / "results.json").read_text())

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
    "seen":          "#10b981",  # emerald
    "near_neighbor": "#3b82f6",  # blue
    "cold_start":    "#f59e0b",  # amber
    "primary":       "#1e3a8a",  # navy
    "accent":        "#ea580c",  # orange
    "neutral":       "#64748b",
    "good":          "#10b981",
    "bad":           "#ef4444",
}

REGIME_LABEL = {
    "seen":          "Seen contexts\n(LTM exact match)",
    "near_neighbor": "Near-neighbour\n(unseen but similar)",
    "cold_start":    "Cold-start\n(no LTM neighbour)",
}


# ── 01. Headline number ────────────────────────────────────────────────
def chart_overall():
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis("off")

    o = RESULTS["overall"]
    ax.text(0.5, 0.66, f"{o['accuracy_pct']:.0f}%", ha="center", va="center",
            fontsize=200, fontweight="bold", color=PALETTE["primary"])
    ax.text(0.5, 0.42, f"Routing Accuracy", ha="center", va="center",
            fontsize=36, color=PALETTE["neutral"])
    ax.text(0.5, 0.32,
            f"{o['correct']} / {o['total']} document contexts routed to the correct policy",
            ha="center", va="center", fontsize=20, color=PALETTE["neutral"])
    ax.text(0.5, 0.22,
            f"RABI activation: {o['rabi_activation_pct']:.0f}%   ·   "
            f"Determinism: {o['determinism_pct']:.0f}%   ·   "
            f"Latency: {o['avg_latency_ms']:.0f} ms",
            ha="center", va="center", fontsize=18, color=PALETTE["neutral"], style="italic")
    ax.text(0.5, 0.06,
            "AHMN — Adaptive Hierarchical Memory Network · Pathirana M.M. and team · IT4010",
            ha="center", va="center", fontsize=14, color=PALETTE["neutral"])

    plt.tight_layout()
    out = CHARTS / "01_overall_accuracy.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved {out}")


# ── 02. Per-regime accuracy ────────────────────────────────────────────
def chart_per_regime():
    order = ["seen", "near_neighbor", "cold_start"]
    fig, ax = plt.subplots(figsize=(16, 9))

    regimes = [REGIME_LABEL[r] for r in order]
    accs, totals, corrects = [], [], []
    for r in order:
        m = RESULTS["per_regime"][r]
        accs.append(m["correct"] / m["total"] * 100)
        totals.append(m["total"])
        corrects.append(m["correct"])

    colors = [PALETTE[r] for r in order]
    bars = ax.bar(regimes, accs, color=colors, edgecolor="white", linewidth=2, width=0.55)
    ax.set_ylabel("Routing accuracy (%)", fontsize=18)
    ax.set_ylim(0, 110)
    ax.set_title("Routing Accuracy by Context Regime (n=30)",
                 fontsize=24, fontweight="bold", pad=20)

    for bar, acc, c, t in zip(bars, accs, corrects, totals):
        ax.text(bar.get_x() + bar.get_width() / 2, acc + 3,
                f"{acc:.0f}%", ha="center", fontsize=22, fontweight="bold")
        ax.text(bar.get_x() + bar.get_width() / 2, acc / 2,
                f"{c}/{t}", ha="center", color="white",
                fontsize=18, fontweight="bold")

    # Annotation: cold-start finding
    ax.annotate("Limitation discovered:\nAHMN lacks a confidence\nthreshold to fall back\nto default",
                xy=(2, 5), xytext=(1.1, 50),
                fontsize=12, color=PALETTE["bad"], fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=PALETTE["bad"], lw=2),
                bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                          edgecolor=PALETTE["bad"], linewidth=2))

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    out = CHARTS / "02_per_regime_accuracy.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved {out}")


# ── 03. Confidence calibration — the silver-lining slide ──────────────
def chart_confidence_calibration():
    order = ["seen", "near_neighbor", "cold_start"]
    fig, ax = plt.subplots(figsize=(16, 9))

    regimes = [REGIME_LABEL[r] for r in order]
    confs = [RESULTS["per_regime"][r]["avg_confidence"] for r in order]
    colors = [PALETTE[r] for r in order]

    bars = ax.bar(regimes, confs, color=colors, edgecolor="white", linewidth=2, width=0.55)
    ax.set_ylabel("Average reported confidence", fontsize=18)
    ax.set_ylim(0, 1.0)
    ax.set_title("Confidence Calibration — AHMN Correctly Lowers Confidence on Unknown Inputs",
                 fontsize=22, fontweight="bold", pad=20)

    # Threshold line
    ax.axhline(y=0.5, color=PALETTE["accent"], linestyle="--", linewidth=2.5,
               label="Suggested fallback threshold (0.5)")
    ax.text(2.4, 0.51, "0.50", color=PALETTE["accent"], fontsize=12, fontweight="bold")

    for bar, c in zip(bars, confs):
        ax.text(bar.get_x() + bar.get_width() / 2, c + 0.02,
                f"{c:.2f}", ha="center", fontsize=22, fontweight="bold")

    ax.text(0.5, 0.93,
            "Even when AHMN picks the wrong policy on cold-start inputs,\n"
            "its confidence drops below 0.5 — a usable signal for downstream gating.",
            transform=ax.transAxes, ha="center", fontsize=14,
            color=PALETTE["primary"], style="italic")

    ax.legend(loc="upper right", frameon=True, fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    out = CHARTS / "03_confidence_calibration.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved {out}")


# ── 04. RABI activation and determinism ───────────────────────────────
def chart_rabi_determinism():
    fig, axes = plt.subplots(1, 2, figsize=(16, 9))
    o = RESULTS["overall"]

    # Donut 1 — RABI activation
    sizes = [o["rabi_activation_pct"], 100 - o["rabi_activation_pct"]]
    labels = ["RABI used\n(neighbour priors)", "Flat prior\n(no neighbours)"]
    colors = [PALETTE["good"], PALETTE["neutral"]]
    axes[0].pie(sizes, labels=labels, colors=colors, autopct="%.0f%%",
                startangle=90, wedgeprops=dict(width=0.4, edgecolor="white", linewidth=4),
                textprops=dict(fontsize=14, fontweight="bold"))
    axes[0].set_title("RABI Activation Rate", fontsize=20, fontweight="bold", pad=15)
    axes[0].text(0, 0, f"{o['rabi_activation_pct']:.0f}%", ha="center", va="center",
                 fontsize=32, fontweight="bold", color=PALETTE["primary"])

    # Donut 2 — Determinism
    sizes = [o["determinism_pct"], 100 - o["determinism_pct"]]
    labels = ["Same input → same\npolicy on repeat", "Non-deterministic"]
    colors = [PALETTE["good"], PALETTE["bad"]]
    axes[1].pie(sizes, labels=labels, colors=colors, autopct="%.0f%%",
                startangle=90, wedgeprops=dict(width=0.4, edgecolor="white", linewidth=4),
                textprops=dict(fontsize=14, fontweight="bold"))
    axes[1].set_title("Determinism Rate", fontsize=20, fontweight="bold", pad=15)
    axes[1].text(0, 0, f"{o['determinism_pct']:.0f}%", ha="center", va="center",
                 fontsize=32, fontweight="bold", color=PALETTE["primary"])

    fig.suptitle("Two Reliability Properties — Reproducibility for the Panel",
                 fontsize=22, fontweight="bold", y=0.98)
    plt.tight_layout()
    out = CHARTS / "04_rabi_determinism.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved {out}")


# ── 05. Failure mode analysis ──────────────────────────────────────────
def chart_failure_analysis():
    failures = [r for r in RESULTS["per_case"] if not r["policy_correct"]]
    # Group: which policy was selected when wrong?
    wrong_picks: dict[str, int] = {}
    for f in failures:
        p = f["selected_policy"] or "(empty)"
        wrong_picks[p] = wrong_picks.get(p, 0) + 1

    fig, ax = plt.subplots(figsize=(16, 9))
    items = sorted(wrong_picks.items(), key=lambda x: -x[1])
    policies = [p for p, _ in items]
    counts = [c for _, c in items]
    colors = [PALETTE["bad"] if p == "table_heavy" else PALETTE["neutral"] for p in policies]

    bars = ax.barh(policies, counts, color=colors, edgecolor="white", linewidth=2)
    ax.set_xlabel("Number of incorrect routings", fontsize=16)
    ax.set_title(f"Failure Mode Analysis — Where Did Wrong Routings Go? (n={len(failures)} failures)",
                 fontsize=22, fontweight="bold", pad=20)

    for bar, c in zip(bars, counts):
        ax.text(c + 0.1, bar.get_y() + bar.get_height() / 2,
                f"  {c}", va="center", fontsize=18, fontweight="bold")

    ax.text(0.99, 0.05,
            "Insight: failures cluster on 'table_heavy' — the densest LTM seed cluster\n"
            "pulls neighbouring contexts toward it. A vendor-aware similarity weighting\n"
            "or per-policy similarity threshold would help.",
            transform=ax.transAxes, ha="right", fontsize=12,
            color=PALETTE["primary"], style="italic",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#f1f5f9",
                      edgecolor=PALETTE["primary"], linewidth=1))

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.invert_yaxis()
    plt.tight_layout()
    out = CHARTS / "05_failure_analysis.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved {out}")


if __name__ == "__main__":
    chart_overall()
    chart_per_regime()
    chart_confidence_calibration()
    chart_rabi_determinism()
    chart_failure_analysis()
    print(f"\nAll charts written to: {CHARTS}")
