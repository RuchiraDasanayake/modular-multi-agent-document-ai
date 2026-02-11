"""
Page 3: RABI Cold-Start Demo
Interactive demonstration of Retrieval-Augmented Bandit Initialization.
"""

import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import random as py_random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ahmn_core.services.rabi import RABIInitializer, NeighborInfo, RABIPrior
from ahmn_core.services.selection_strategies import ThompsonSamplingStrategy, BanditArm
from ahmn_core.experiments.synthetic_data import (
    _make_cluster_embedding, cosine_similarity, POLICY_IDS,
    create_cold_start_scenario, VendorProfile, PolicyConfig,
)
from ahmn_core.experiments.run_experiments import (
    ThompsonSamplingRunner, AHMNRABIRunner, run_single,
)

st.set_page_config(page_title="AHMN — RABI Cold-Start", page_icon="🧊", layout="wide")

st.title("🧊 RABI: Retrieval-Augmented Bandit Initialization")
st.markdown("*Solving the cold-start problem by transferring knowledge from similar vendors*")

st.markdown("---")

# ── Section 1: The Problem ──
st.markdown("### ❄️ The Cold-Start Problem")

col1, col2 = st.columns(2)
with col1:
    st.markdown("""
    When a **new vendor** appears for the first time:
    - We have **zero history** — no data about what works
    - Standard Thompson Sampling starts from **flat Beta(1,1) prior**
    - Must explore all policies equally — **wastes ~50-100 rounds** before converging
    
    **But we have knowledge from similar vendors!** If Vendor A (invoices, similar layout) 
    works best with Azure CV, a new similar vendor probably does too.
    """)

with col2:
    st.markdown("""
    **RABI Solution**: Before any exploration, initialize the new vendor's prior 
    by transferring knowledge from similar established vendors:
    
    ```
    1. Find k nearest neighbors in embedding space
    2. Weight by cosine similarity (softmax)
    3. Transfer pseudocounts:
       α_init = 1 + Σᵢ wᵢ·(αᵢ - 1)
       β_init = 1 + Σᵢ wᵢ·(βᵢ - 1)
    ```
    
    This gives the new vendor a **warm start** — it already "knows" 
    which policies tend to work for similar documents.
    """)

st.markdown("---")

# ── Section 2: Interactive Prior Visualization ──
st.markdown("### 🔬 Interactive: Build a RABI Prior")
st.markdown("*Adjust parameters and see how the initialized prior changes*")

col1, col2, col3 = st.columns(3)

with col1:
    temperature = st.slider("Temperature (τ)", 0.1, 2.0, 0.5, 0.1,
                           help="Lower = sharper weighting toward most similar. Higher = more uniform.")

with col2:
    sim_threshold = st.slider("Similarity Threshold", 0.1, 0.9, 0.4, 0.05,
                             help="Minimum cosine similarity to include a neighbor.")

with col3:
    max_transfer = st.slider("Max Transfer Strength", 2.0, 20.0, 10.0, 1.0,
                            help="Cap on transferred pseudocounts (prevents over-confidence).")

st.markdown("#### Simulated Neighbors (Established Vendors)")

# Create interactive neighbor table
n_neighbors = st.slider("Number of available neighbors", 1, 6, 3)

neighbors = []
neighbor_cols = st.columns(min(n_neighbors, 3))

for i in range(n_neighbors):
    col_idx = i % 3
    with neighbor_cols[col_idx]:
        st.markdown(f"**Vendor {chr(65 + i)}**")
        sim = st.slider(f"Similarity (V{chr(65+i)})", 0.1, 0.99, 
                        0.85 - i * 0.15 if i < 4 else 0.3, 0.01, key=f"sim_{i}")
        alpha = st.slider(f"α (successes+1, V{chr(65+i)})", 1.0, 30.0, 
                         15.0 - i * 3 if i < 4 else 5.0, 0.5, key=f"alpha_{i}")
        beta = st.slider(f"β (failures+1, V{chr(65+i)})", 1.0, 20.0,
                        3.0 + i * 1.5 if i < 4 else 8.0, 0.5, key=f"beta_{i}")
        n_samples = int(alpha + beta - 2)
        
        neighbors.append(NeighborInfo(
            context_hash=f"vendor_{chr(65+i)}",
            policy_id="ocr_tesseract",
            alpha=alpha,
            beta=beta,
            similarity=sim,
            n_samples=max(0, n_samples),
        ))
        
        st.caption(f"Mean reward: {alpha/(alpha+beta):.3f} | Samples: {n_samples}")

# Run RABI
rabi = RABIInitializer(
    k=n_neighbors,
    similarity_threshold=sim_threshold,
    temperature=temperature,
    min_samples_for_transfer=5,
    max_transfer_strength=max_transfer,
)

prior = rabi.initialize_prior(neighbors)

# ── Visualize Prior ──
st.markdown("---")
st.markdown("### 📊 Result: RABI-Initialized Prior vs. Flat Prior")

col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    # Plot Beta distributions
    x = np.linspace(0.001, 0.999, 500)
    
    from scipy.stats import beta as beta_dist
    
    fig_prior = go.Figure()
    
    # Flat prior
    y_flat = beta_dist.pdf(x, 1.0, 1.0)
    fig_prior.add_trace(go.Scatter(
        x=x, y=y_flat,
        name="Flat Prior Beta(1, 1)",
        line=dict(color="#95a5a6", dash="dash", width=2),
        fill="tozeroy",
        fillcolor="rgba(149, 165, 166, 0.2)",
    ))
    
    # RABI prior
    y_rabi = beta_dist.pdf(x, prior.alpha, prior.beta)
    fig_prior.add_trace(go.Scatter(
        x=x, y=y_rabi,
        name=f"RABI Prior Beta({prior.alpha:.2f}, {prior.beta:.2f})",
        line=dict(color="#9b59b6", width=3),
        fill="tozeroy",
        fillcolor="rgba(155, 89, 182, 0.3)",
    ))
    
    # Mean markers
    fig_prior.add_vline(x=0.5, line_dash="dot", line_color="#95a5a6",
                       annotation_text="Flat mean: 0.500")
    fig_prior.add_vline(x=prior.mean, line_dash="dot", line_color="#9b59b6",
                       annotation_text=f"RABI mean: {prior.mean:.3f}")
    
    fig_prior.update_layout(
        title="Prior Distribution Comparison",
        xaxis_title="Reward (θ)",
        yaxis_title="Density",
        height=400,
        template="plotly_white",
    )
    st.plotly_chart(fig_prior, use_container_width=True)

with col2:
    # Weight visualization
    valid_neighbors = [n for n in neighbors 
                      if n.similarity >= sim_threshold 
                      and n.n_samples >= 5]
    
    if valid_neighbors:
        sims = [n.similarity for n in valid_neighbors]
        weights = rabi.compute_weights(sims)
        
        fig_weights = go.Figure()
        
        labels = [f"V{n.context_hash[-1].upper()}\n(sim={n.similarity:.2f})" for n in valid_neighbors]
        
        fig_weights.add_trace(go.Bar(
            x=labels, y=weights,
            marker_color=["#9b59b6" if w == max(weights) else "#c39bd3" for w in weights],
            text=[f"{w:.3f}" for w in weights],
            textposition="outside",
        ))
        
        fig_weights.update_layout(
            title=f"Softmax Weights (τ = {temperature})",
            yaxis_title="Weight",
            height=400,
            template="plotly_white",
            yaxis=dict(range=[0, max(weights) * 1.2]),
        )
        st.plotly_chart(fig_weights, use_container_width=True)
    else:
        st.warning("No neighbors pass the similarity threshold and minimum sample requirement!")

with col3:
    st.markdown("#### RABI Output")
    st.metric("α_init", f"{prior.alpha:.3f}")
    st.metric("β_init", f"{prior.beta:.3f}")
    st.metric("E[θ]", f"{prior.mean:.3f}")
    st.metric("Confidence", f"{prior.confidence:.3f}")
    st.metric("Neighbors Used", f"{prior.n_neighbors}")
    st.metric("Eff. Samples", f"{prior.effective_samples:.1f}")

st.markdown("---")

# ── Section 3: Cold-Start Race ──
st.markdown("### 🏁 Cold-Start Race: RABI vs. Flat Prior")
st.markdown("*A new vendor appears at round 300. Watch the first 200 rounds of learning.*")

col1, col2 = st.columns(2)
with col1:
    race_seeds = st.slider("Number of seeds (Race)", 5, 30, 15, key="race_seeds")
with col2:
    race_spread = st.slider("Embedding spread (controls neighbor similarity)", 
                           0.01, 1.0, 0.15, 0.01, key="race_spread",
                           help="Lower = more similar neighbors (RABI helps more)")

if st.button("▶️ Run Cold-Start Race", type="primary"):
    scenario = create_cold_start_scenario()
    
    # Adjust embedding spread
    for i, v in enumerate(scenario.vendors):
        cid = 1 if "inv" in v.vendor_id else 2
        wid = sum(1 for v2 in scenario.vendors[:i]
                  if (1 if "inv" in v2.vendor_id else 2) == cid)
        v.embedding = _make_cluster_embedding(cid, wid, spread=race_spread)
    
    progress = st.progress(0, text="Running race...")
    
    ts_results = []
    rabi_results = []
    
    for seed in range(race_seeds):
        ts_runner = ThompsonSamplingRunner(scenario.policy_ids)
        rabi_runner = AHMNRABIRunner(scenario.policy_ids)
        
        ts_results.append(run_single(ts_runner, scenario, seed))
        rabi_results.append(run_single(rabi_runner, scenario, seed))
        
        progress.progress((seed + 1) / race_seeds, 
                         text=f"Seed {seed+1}/{race_seeds}")
    
    progress.empty()
    
    # Compute metrics
    ts_regret = np.mean([r.total_regret for r in ts_results])
    rabi_regret = np.mean([r.total_regret for r in rabi_results])
    improvement = (ts_regret - rabi_regret) / ts_regret * 100
    
    col1, col2, col3 = st.columns(3)
    col1.metric("TS (flat prior) Regret", f"{ts_regret:.1f}")
    col2.metric("AHMN-RABI Regret", f"{rabi_regret:.1f}")
    col3.metric("Improvement", f"{improvement:.1f}%", delta=f"-{ts_regret - rabi_regret:.1f} regret")
    
    # Plot regret curves
    fig_race = go.Figure()
    
    ts_avg = np.mean([r.cumulative_regret for r in ts_results], axis=0)
    rabi_avg = np.mean([r.cumulative_regret for r in rabi_results], axis=0)
    
    rounds = list(range(len(ts_avg)))
    
    fig_race.add_trace(go.Scatter(
        x=rounds, y=ts_avg,
        name="TS (flat prior)",
        line=dict(color="#2ecc71", width=2),
    ))
    fig_race.add_trace(go.Scatter(
        x=rounds, y=rabi_avg,
        name="AHMN-RABI",
        line=dict(color="#9b59b6", width=2.5),
    ))
    
    # Mark cold-start events
    for de_round in [300, 500, 700]:
        fig_race.add_vline(x=de_round, line_dash="dash", line_color="orange",
                          annotation_text=f"New vendor @ {de_round}")
    
    fig_race.update_layout(
        title="Cumulative Regret: RABI vs Flat Prior in Cold-Start Scenario",
        xaxis_title="Round",
        yaxis_title="Cumulative Regret",
        height=450,
        template="plotly_white",
    )
    st.plotly_chart(fig_race, use_container_width=True)
    
    # Zoom into first 200 rounds after a cold-start
    st.markdown("#### 🔍 Zoom: First 200 Rounds After New Vendor Appears (Round 300-500)")
    
    fig_zoom = go.Figure()
    
    fig_zoom.add_trace(go.Scatter(
        x=list(range(300, min(500, len(ts_avg)))),
        y=ts_avg[300:500] - ts_avg[300],
        name="TS (flat prior)",
        line=dict(color="#2ecc71", width=2),
    ))
    fig_zoom.add_trace(go.Scatter(
        x=list(range(300, min(500, len(rabi_avg)))),
        y=rabi_avg[300:500] - rabi_avg[300],
        name="AHMN-RABI",
        line=dict(color="#9b59b6", width=2.5),
    ))
    
    fig_zoom.update_layout(
        title="Regret Accumulated During Cold-Start Period",
        xaxis_title="Round",
        yaxis_title="Regret (since round 300)",
        height=350,
        template="plotly_white",
    )
    st.plotly_chart(fig_zoom, use_container_width=True)
    
    st.success(f"""
    **Key Insight**: RABI reduces cold-start regret by **{improvement:.1f}%** 
    (embedding spread = {race_spread}, avg neighbor similarity ≈ {1.0 - race_spread:.2f}).
    
    The gap appears immediately when new vendors arrive — RABI doesn't need 
    to explore from scratch because it already has an informed prior from similar vendors.
    """)
