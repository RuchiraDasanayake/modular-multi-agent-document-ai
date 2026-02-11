"""
Page 4: DAAF Drift Detection Demo
Interactive demonstration of Drift-Aware Adaptive Forgetting.
"""

import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import random as py_random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ahmn_core.services.drift_forgetting import (
    DriftEstimator, AdaptiveForgettingBandit, DriftType, DriftMetrics,
)
from ahmn_core.services.selection_strategies import ThompsonSamplingStrategy, BanditArm
from ahmn_core.experiments.synthetic_data import (
    create_drift_scenario, POLICY_IDS,
    VendorProfile, PolicyConfig, DriftEvent, Scenario,
    _make_cluster_embedding,
)
from ahmn_core.experiments.run_experiments import (
    ThompsonSamplingRunner, AHMNDAAFRunner, run_single,
)

st.set_page_config(page_title="AHMN — DAAF Drift", page_icon="🌊", layout="wide")

st.title("🌊 DAAF: Drift-Aware Adaptive Forgetting")
st.markdown("*Detecting when document formats change and adapting in real-time*")

st.markdown("---")

# ── Section 1: The Problem ──
st.markdown("### 🔄 The Concept Drift Problem")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **What happens when a vendor changes their document template?**
    
    - The best OCR policy might shift (e.g., Tesseract was best → now Azure CV is best)
    - Standard Thompson Sampling has accumulated strong beliefs from the OLD distribution
    - It takes **hundreds of rounds** to override those beliefs with new data
    - Meanwhile, you're using the WRONG policy
    
    **The challenge**: How do you know it's *drift* (real change) vs *noise* (random fluctuation)?
    """)

with col2:
    st.markdown("""
    **DAAF Solution**: Two-window comparison that separates drift from noise:

    ```
    Recent window:  last 50 observations
    Older window:   previous 50 observations
    
    Drift magnitude: Δ = |mean(recent) - mean(older)|
    Noise variance:  σ² = Var(recent)  ← ignored!
    
    Optimal forgetting: γ* = √(Δ² / ln(t))
    
    Apply:
      α_new = 1 + (1-γ)(α - 1)   ← shrink toward flat
      β_new = 1 + (1-γ)(β - 1)   ← shrink toward flat
    ```
    
    **Key insight**: Use Δ (between-window shift) for γ*, NOT σ² (within-window noise).
    """)

st.markdown("---")

# ── Section 2: Interactive Drift Detector ──
st.markdown("### 🔬 Interactive: Watch the Drift Detector in Action")
st.markdown("*Generate a synthetic reward stream with a drift event and watch DAAF detect it*")

col1, col2, col3, col4 = st.columns(4)

with col1:
    pre_drift_mean = st.slider("Pre-drift reward mean", 0.3, 0.95, 0.85, 0.05)
    
with col2:
    post_drift_mean = st.slider("Post-drift reward mean", 0.3, 0.95, 0.55, 0.05)
    
with col3:
    noise_std = st.slider("Noise (σ)", 0.01, 0.20, 0.06, 0.01)
    
with col4:
    drift_round = st.slider("Drift at round", 50, 250, 150, 10)

n_rounds_demo = 300
window_size = st.slider("DAAF window size", 10, 100, 50, 5)

if st.button("▶️ Run Drift Detection Demo", type="primary"):
    # Generate synthetic data
    rng = np.random.RandomState(42)
    rewards = []
    for t in range(n_rounds_demo):
        if t < drift_round:
            r = rng.normal(pre_drift_mean, noise_std)
        else:
            r = rng.normal(post_drift_mean, noise_std)
        rewards.append(max(0.0, min(1.0, r)))
    
    # Run drift estimator
    estimator = DriftEstimator(
        window_size=window_size,
        min_samples=10,
        drift_threshold=0.05,
        abrupt_threshold=0.15,
    )
    
    drift_magnitudes = []
    gammas = []
    drift_types = []
    confidences = []
    recent_means = []
    
    for t, reward in enumerate(rewards):
        metrics = estimator.update(reward)
        drift_magnitudes.append(metrics.drift_magnitude)
        gammas.append(metrics.optimal_gamma)
        drift_types.append(metrics.drift_type.value)
        confidences.append(metrics.confidence)
        
        recent_data = list(estimator.recent_window)
        recent_means.append(np.mean(recent_data) if recent_data else reward)
    
    rounds = list(range(n_rounds_demo))
    
    # ── Multi-panel plot ──
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=(
            "Raw Reward Stream",
            "Drift Magnitude (Δ) — Between-Window Mean Shift",
            "Optimal Forgetting Rate (γ*)",
            "Drift Type Classification",
        ),
        row_heights=[0.3, 0.25, 0.25, 0.2],
    )
    
    # Panel 1: Raw rewards
    fig.add_trace(go.Scatter(
        x=rounds, y=rewards,
        name="Observed Reward",
        line=dict(color="#3498db", width=1),
        opacity=0.5,
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=rounds, y=recent_means,
        name="Window Mean",
        line=dict(color="#e74c3c", width=2),
    ), row=1, col=1)
    
    # True means
    fig.add_hline(y=pre_drift_mean, line_dash="dot", line_color="green",
                 annotation_text=f"Pre-drift: {pre_drift_mean}", row="1", col="1")
    fig.add_hline(y=post_drift_mean, line_dash="dot", line_color="orange",
                 annotation_text=f"Post-drift: {post_drift_mean}", row="1", col="1")
    
    # Panel 2: Drift magnitude
    fig.add_trace(go.Scatter(
        x=rounds, y=drift_magnitudes,
        name="Drift Magnitude (Δ)",
        line=dict(color="#e74c3c", width=2),
        fill="tozeroy",
        fillcolor="rgba(231, 76, 60, 0.2)",
    ), row=2, col=1)
    
    fig.add_hline(y=0.05, line_dash="dash", line_color="orange",
                 annotation_text="Gradual threshold", row="2", col="1")
    fig.add_hline(y=0.15, line_dash="dash", line_color="red",
                 annotation_text="Abrupt threshold", row="2", col="1")
    
    # Panel 3: Gamma
    fig.add_trace(go.Scatter(
        x=rounds, y=gammas,
        name="γ* (forgetting rate)",
        line=dict(color="#9b59b6", width=2),
        fill="tozeroy",
        fillcolor="rgba(155, 89, 182, 0.2)",
    ), row=3, col=1)
    
    # Panel 4: Drift type
    type_map = {"none": 0, "gradual": 1, "abrupt": 2}
    type_colors = {"none": "#2ecc71", "gradual": "#f39c12", "abrupt": "#e74c3c"}
    type_values = [type_map[dt] for dt in drift_types]
    type_color_list = [type_colors[dt] for dt in drift_types]
    
    fig.add_trace(go.Bar(
        x=rounds, y=[1] * len(rounds),
        marker_color=type_color_list,
        name="Drift Type",
        showlegend=False,
    ), row=4, col=1)
    
    # Drift event marker on all panels
    for row in range(1, 5):
        fig.add_vline(x=drift_round, line_dash="dash", line_color="red",
                     annotation_text="DRIFT EVENT" if row == 1 else None,
                     row=str(row), col="1")
    
    fig.update_layout(
        height=900,
        template="plotly_white",
        showlegend=True,
        legend=dict(yanchor="top", y=1.02, xanchor="left", x=0.01),
    )
    
    fig.update_yaxes(title_text="Reward", row=1, col=1)
    fig.update_yaxes(title_text="Δ", row=2, col=1)
    fig.update_yaxes(title_text="γ*", row=3, col=1)
    fig.update_yaxes(title_text="Type", tickvals=[0, 1, 2], 
                    ticktext=["None", "Gradual", "Abrupt"], row=4, col=1)
    fig.update_xaxes(title_text="Round", row=4, col=1)
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Detection summary
    drift_detected_at = None
    for t in range(n_rounds_demo):
        if t > drift_round and drift_types[t] != "none":
            drift_detected_at = t
            break
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("True Drift Magnitude", 
                  f"{abs(pre_drift_mean - post_drift_mean):.3f}")
    with col2:
        if drift_detected_at:
            delay = drift_detected_at - drift_round
            st.metric("Detection Delay", f"{delay} rounds",
                     help="How many rounds after drift before DAAF detects it")
        else:
            st.metric("Detection Delay", "Not detected")
    with col3:
        max_gamma = max(gammas[drift_round:]) if drift_round < len(gammas) else 0
        st.metric("Peak γ* After Drift", f"{max_gamma:.4f}")
    
    st.markdown("""
    **Legend**:
    - 🟢 **Green bars**: No drift detected (standard Bayesian update)
    - 🟡 **Yellow bars**: Gradual drift (moderate forgetting)
    - 🔴 **Red bars**: Abrupt drift (aggressive forgetting + reset)
    """)

st.markdown("---")

# ── Section 3: DAAF vs plain TS under drift ──
st.markdown("### 🏁 DAAF vs. Plain TS Under Concept Drift")

col1, col2 = st.columns(2)
with col1:
    drift_magnitude = st.slider("Reward shift magnitude", 0.05, 0.35, 0.20, 0.05,
                               key="drift_mag",
                               help="How much the best policy's reward drops at drift point")
with col2:
    drift_seeds = st.slider("Seeds", 5, 30, 15, key="drift_seeds_2")

if st.button("▶️ Run Drift Comparison", type="primary", key="drift_comp"):
    # Build custom drift scenario
    vendors = [
        VendorProfile(
            vendor_id="vendor_drift", doc_type="invoice",
            policies={
                "ocr_tesseract": PolicyConfig(true_mean=0.88, noise_std=0.05),
                "ocr_easyocr":   PolicyConfig(true_mean=0.70, noise_std=0.06),
                "ocr_azure_cv":  PolicyConfig(true_mean=0.75, noise_std=0.05),
            },
            embedding=_make_cluster_embedding(1, 0),
            weight=1.0,
        ),
    ]
    
    # After drift: Tesseract drops, Azure rises
    drift_event = DriftEvent(
        vendor_id="vendor_drift",
        at_round=500,
        new_policies={
            "ocr_tesseract": PolicyConfig(true_mean=0.88 - drift_magnitude, noise_std=0.05),
            "ocr_easyocr":   PolicyConfig(true_mean=0.70, noise_std=0.06),
            "ocr_azure_cv":  PolicyConfig(true_mean=0.75 + drift_magnitude, noise_std=0.05),
        },
    )
    
    scenario = Scenario(
        name="custom_drift",
        description=f"Single vendor with drift magnitude {drift_magnitude}",
        vendors=vendors,
        policy_ids=POLICY_IDS,
        n_rounds=1000,
        drift_events=[drift_event],
    )
    
    progress = st.progress(0, text="Running comparison...")
    
    ts_results = []
    daaf_results = []
    
    for seed in range(drift_seeds):
        ts_results.append(run_single(ThompsonSamplingRunner(scenario.policy_ids), scenario, seed))
        daaf_results.append(run_single(AHMNDAAFRunner(scenario.policy_ids), scenario, seed))
        progress.progress((seed + 1) / drift_seeds)
    
    progress.empty()
    
    # Metrics
    ts_regret = np.mean([r.total_regret for r in ts_results])
    daaf_regret = np.mean([r.total_regret for r in daaf_results])
    improvement = (ts_regret - daaf_regret) / ts_regret * 100
    
    col1, col2, col3 = st.columns(3)
    col1.metric("TS Regret", f"{ts_regret:.1f}")
    col2.metric("DAAF Regret", f"{daaf_regret:.1f}")
    col3.metric("Improvement", f"{improvement:.1f}%", delta=f"-{ts_regret - daaf_regret:.1f}")
    
    # Plot
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=(
            "Cumulative Regret",
            "Rolling Average Reward (window=50)",
        ),
    )
    
    ts_regret_avg = np.mean([r.cumulative_regret for r in ts_results], axis=0)
    daaf_regret_avg = np.mean([r.cumulative_regret for r in daaf_results], axis=0)
    
    rounds = list(range(len(ts_regret_avg)))
    
    fig.add_trace(go.Scatter(
        x=rounds, y=ts_regret_avg,
        name="TS (no forgetting)",
        line=dict(color="#2ecc71", width=2),
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=rounds, y=daaf_regret_avg,
        name="AHMN-DAAF",
        line=dict(color="#e74c3c", width=2.5),
    ), row=1, col=1)
    
    # Rolling reward
    window = 50
    ts_rewards = np.mean([r.rewards for r in ts_results], axis=0)
    daaf_rewards = np.mean([r.rewards for r in daaf_results], axis=0)
    
    ts_rolling = np.convolve(ts_rewards, np.ones(window)/window, mode='valid')
    daaf_rolling = np.convolve(daaf_rewards, np.ones(window)/window, mode='valid')
    x_rolling = list(range(window - 1, len(ts_rewards)))
    
    fig.add_trace(go.Scatter(
        x=x_rolling, y=ts_rolling,
        name="TS Reward",
        line=dict(color="#2ecc71", width=2),
        showlegend=False,
    ), row=2, col=1)
    
    fig.add_trace(go.Scatter(
        x=x_rolling, y=daaf_rolling,
        name="DAAF Reward",
        line=dict(color="#e74c3c", width=2.5),
        showlegend=False,
    ), row=2, col=1)
    
    # Drift marker
    for row in [1, 2]:
        fig.add_vline(x=500, line_dash="dash", line_color="red",
                     annotation_text="DRIFT EVENT" if row == 1 else None,
                     row=str(row), col="1")
    
    fig.update_layout(
        height=700,
        template="plotly_white",
    )
    fig.update_yaxes(title_text="Cumulative Regret", row=1, col=1)
    fig.update_yaxes(title_text="Reward (F1)", row=2, col=1)
    fig.update_xaxes(title_text="Round", row=2, col=1)
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.success(f"""
    **Key Insight**: After the drift event at round 500, plain TS (green) keeps using 
    the old best policy while DAAF (red) detects the shift and forgets stale beliefs.
    
    - **Drift magnitude**: ±{drift_magnitude:.2f} (Tesseract drops, Azure rises)
    - **DAAF improvement**: {improvement:.1f}% regret reduction
    - The gap widens after drift — DAAF adapts, TS doesn't
    """)

st.markdown("---")

# ── Section 4: Why σ² ≠ drift ──
st.markdown("### 🧮 Key Insight: Why Noise ≠ Drift")

st.markdown("""
Most drift detection methods confuse **noise** with **drift**. DAAF explicitly separates them:

| | Noise (σ²) | Drift (Δ) |
|---|---|---|
| **Source** | Within-window variance | Between-window mean shift |
| **Meaning** | Random fluctuation in rewards | Real change in environment |
| **Action** | Ignore (it's inherent) | Adjust forgetting rate |
| **Formula** | Var(recent window) | |mean(recent) - mean(older)| |

**Why this matters**:
- High noise + no drift → σ² high, Δ ≈ 0 → γ* stays small → **no unnecessary forgetting**  
- Low noise + drift → σ² low, Δ high → γ* increases → **fast adaptation**
- High noise + drift → σ² high, Δ high → γ* scales with Δ not σ² → **correct response**

This prevents the catastrophic error of forgetting learned knowledge just because rewards are noisy.
""")
