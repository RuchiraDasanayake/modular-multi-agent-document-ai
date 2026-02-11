"""
Page 2: Live Experiment Demo
Run bandit experiments in real-time and watch algorithms compete.
"""

import streamlit as st
import numpy as np
import random as py_random
import time
import sys
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ahmn_core.services.selection_strategies import (
    BanditArm, ThompsonSamplingStrategy, UCB1Strategy,
    EpsilonGreedyStrategy, RandomStrategy,
)
from ahmn_core.services.rabi import RABIInitializer, NeighborInfo
from ahmn_core.services.drift_forgetting import DriftEstimator, DriftType
from ahmn_core.experiments.synthetic_data import (
    get_all_scenarios, create_stationary_scenario,
    create_cold_start_scenario, create_drift_scenario,
    create_combined_scenario, cosine_similarity, POLICY_IDS,
)
from ahmn_core.experiments.run_experiments import (
    RandomRunner, EpsilonGreedyRunner, UCB1Runner,
    ThompsonSamplingRunner, AHMNRABIRunner, AHMNDAAFRunner,
    AHMNFullRunner, run_single,
)

st.set_page_config(page_title="AHMN — Live Experiments", page_icon="🎯", layout="wide")

st.title("🎯 Live Experiment Demo")
st.markdown("*Watch 7 algorithms compete in real-time across different scenarios*")

st.markdown("---")

# ── Controls ──
col1, col2, col3 = st.columns(3)

with col1:
    scenario_name = st.selectbox(
        "Scenario",
        ["stationary", "cold_start", "concept_drift", "combined"],
        format_func=lambda x: {
            "stationary": "📊 Stationary — Pure bandit learning",
            "cold_start": "🧊 Cold-Start — New vendors appear",
            "concept_drift": "🌊 Concept Drift — Rewards shift",
            "combined": "🔀 Combined — Drift + Cold-Start"
        }[x]
    )

with col2:
    n_seeds = st.slider("Number of seeds (more = more reliable)", 1, 30, 10)

with col3:
    selected_methods = st.multiselect(
        "Methods to compare",
        ["Random", "ε-Greedy", "UCB1", "TS (base)", "AHMN-RABI", "AHMN-DAAF", "AHMN-Full"],
        default=["Random", "TS (base)", "AHMN-Full"]
    )

# Method color mapping
METHOD_COLORS = {
    "Random": "#95a5a6",
    "ε-Greedy": "#e67e22",
    "UCB1": "#3498db",
    "TS (base)": "#2ecc71",
    "AHMN-RABI": "#9b59b6",
    "AHMN-DAAF": "#e74c3c",
    "AHMN-Full": "#f39c12",
}

# ── Scenario description ──
scenario_descriptions = {
    "stationary": """
    **No drift, no cold-start.** Tests pure bandit learning ability. 
    4 vendors with fixed reward distributions. RABI and DAAF should be neutral here — 
    this proves they don't hurt when not needed.
    """,
    "cold_start": """
    **New vendors appear mid-experiment.** 3 established vendors form a knowledge base, 
    then 6 new vendors arrive in waves. RABI should shine here by transferring 
    knowledge from similar established vendors.
    """,
    "concept_drift": """
    **Document formats change.** Vendor A's optimal OCR shifts from Tesseract to Azure CV 
    at round 500. DAAF should detect this drift and adapt, while plain TS slowly relearns.
    """,
    "combined": """
    **Everything at once.** Drift events + cold-start vendors. This is the realistic scenario 
    where AHMN-Full (RABI + DAAF) should demonstrate the biggest advantage.
    """
}

st.info(scenario_descriptions.get(scenario_name, ""))

# ── Run Experiment ──
if st.button("▶️ Run Experiment", type="primary", use_container_width=True):
    
    # Create scenario
    scenarios_map = {
        "stationary": create_stationary_scenario,
        "cold_start": create_cold_start_scenario,
        "concept_drift": create_drift_scenario,
        "combined": create_combined_scenario,
    }
    scenario = scenarios_map[scenario_name]()
    
    # Build method runners
    runner_map = {
        "Random": lambda: RandomRunner(scenario.policy_ids),
        "ε-Greedy": lambda: EpsilonGreedyRunner(scenario.policy_ids),
        "UCB1": lambda: UCB1Runner(scenario.policy_ids),
        "TS (base)": lambda: ThompsonSamplingRunner(scenario.policy_ids),
        "AHMN-RABI": lambda: AHMNRABIRunner(scenario.policy_ids),
        "AHMN-DAAF": lambda: AHMNDAAFRunner(scenario.policy_ids),
        "AHMN-Full": lambda: AHMNFullRunner(scenario.policy_ids),
    }
    
    progress = st.progress(0, text="Running experiments...")
    
    # Run all seeds for all methods
    all_results = {}
    total_tasks = len(selected_methods) * n_seeds
    completed = 0
    
    for method_name in selected_methods:
        method_results = []
        for seed in range(n_seeds):
            runner = runner_map[method_name]()
            result = run_single(runner, scenario, seed)
            method_results.append(result)
            completed += 1
            progress.progress(completed / total_tasks, 
                            text=f"Running {method_name} (seed {seed+1}/{n_seeds})...")
        all_results[method_name] = method_results
    
    progress.progress(1.0, text="Done!")
    time.sleep(0.3)
    progress.empty()
    
    # ── Summary Metrics ──
    st.markdown("### 📊 Summary")
    
    metric_cols = st.columns(len(selected_methods))
    for i, method_name in enumerate(selected_methods):
        results = all_results[method_name]
        avg_regret = np.mean([r.total_regret for r in results])
        avg_reward = np.mean([r.final_avg_reward for r in results])
        avg_acc = np.mean([r.policy_accuracy for r in results])
        
        with metric_cols[i]:
            st.markdown(f"**{method_name}**")
            st.metric("Cumulative Regret", f"{avg_regret:.1f}")
            st.metric("Final F1", f"{avg_reward:.3f}")
            st.metric("Policy Accuracy", f"{avg_acc:.1%}")
    
    st.markdown("---")
    
    # ── Plot 1: Cumulative Regret ──
    st.markdown("### 📈 Cumulative Regret Over Time")
    st.markdown("*Lower is better. The gap between curves = AHMN's advantage.*")
    
    fig_regret = go.Figure()
    
    for method_name in selected_methods:
        results = all_results[method_name]
        # Average regret curve across seeds
        n_rounds = len(results[0].cumulative_regret)
        avg_regret_curve = np.mean(
            [r.cumulative_regret for r in results], axis=0
        )
        std_regret_curve = np.std(
            [r.cumulative_regret for r in results], axis=0
        )
        
        rounds = list(range(n_rounds))
        color = METHOD_COLORS.get(method_name, "#333")
        
        fig_regret.add_trace(go.Scatter(
            x=rounds, y=avg_regret_curve,
            name=method_name,
            line=dict(color=color, width=2.5 if "AHMN" in method_name else 1.5),
            mode="lines",
        ))
        
        # Confidence band
        fig_regret.add_trace(go.Scatter(
            x=rounds + rounds[::-1],
            y=list(avg_regret_curve + std_regret_curve) + list((avg_regret_curve - std_regret_curve)[::-1]),
            fill="toself",
            fillcolor=color.replace(")", ",0.1)").replace("rgb", "rgba") if "rgb" in color else color + "15",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False,
            hoverinfo="skip",
        ))
    
    # Add drift event markers
    if scenario.drift_events:
        for de in scenario.drift_events:
            fig_regret.add_vline(
                x=de.at_round, line_dash="dash", line_color="red",
                annotation_text=f"Drift @ {de.at_round}",
                annotation_position="top right"
            )
    
    fig_regret.update_layout(
        xaxis_title="Round",
        yaxis_title="Cumulative Regret",
        height=500,
        template="plotly_white",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    st.plotly_chart(fig_regret, use_container_width=True)
    
    # ── Plot 2: Rolling Average Reward ──
    st.markdown("### 📈 Rolling Average Reward (F1 Score)")
    st.markdown("*Higher is better. Watch how quickly each method learns.*")
    
    fig_reward = go.Figure()
    window = 50
    
    for method_name in selected_methods:
        results = all_results[method_name]
        n_rounds = len(results[0].rewards)
        
        avg_rewards = np.mean([r.rewards for r in results], axis=0)
        
        # Rolling average
        if len(avg_rewards) >= window:
            rolling = np.convolve(avg_rewards, np.ones(window)/window, mode='valid')
            x_vals = list(range(window - 1, n_rounds))
        else:
            rolling = avg_rewards
            x_vals = list(range(n_rounds))
        
        color = METHOD_COLORS.get(method_name, "#333")
        
        fig_reward.add_trace(go.Scatter(
            x=x_vals, y=rolling,
            name=method_name,
            line=dict(color=color, width=2.5 if "AHMN" in method_name else 1.5),
            mode="lines",
        ))
    
    # Oracle line
    results_ref = all_results[selected_methods[0]]
    oracle_mean = np.mean([np.mean(r.oracle_rewards) for r in results_ref])
    fig_reward.add_hline(
        y=oracle_mean, line_dash="dot", line_color="gray",
        annotation_text=f"Oracle: {oracle_mean:.3f}",
        annotation_position="bottom right"
    )
    
    if scenario.drift_events:
        for de in scenario.drift_events:
            fig_reward.add_vline(
                x=de.at_round, line_dash="dash", line_color="red",
                annotation_text=f"Drift @ {de.at_round}",
            )
    
    fig_reward.update_layout(
        xaxis_title="Round",
        yaxis_title=f"Rolling Average Reward (window={window})",
        height=500,
        template="plotly_white",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    st.plotly_chart(fig_reward, use_container_width=True)
    
    # ── Plot 3: Policy Selection Accuracy ──
    st.markdown("### 📊 Policy Selection Accuracy by Method")
    
    method_names = []
    accuracies = []
    colors = []
    
    for method_name in selected_methods:
        results = all_results[method_name]
        avg_acc = np.mean([r.policy_accuracy for r in results])
        method_names.append(method_name)
        accuracies.append(avg_acc)
        colors.append(METHOD_COLORS.get(method_name, "#333"))
    
    fig_acc = go.Figure(go.Bar(
        x=method_names, y=accuracies,
        marker_color=colors,
        text=[f"{a:.1%}" for a in accuracies],
        textposition="outside",
    ))
    
    fig_acc.update_layout(
        yaxis_title="Policy Accuracy (% optimal selections)",
        height=400,
        template="plotly_white",
        yaxis=dict(range=[0, max(accuracies) * 1.15]),
    )
    st.plotly_chart(fig_acc, use_container_width=True)
    
    # ── Convergence Table ──
    st.markdown("### ⏱️ Convergence Speed")
    st.markdown("*First round where rolling-50 average exceeds 95% of oracle reward*")
    
    conv_data = []
    for method_name in selected_methods:
        results = all_results[method_name]
        convs = [r.convergence_round for r in results if r.convergence_round is not None]
        regrets = [r.total_regret for r in results]
        rewards = [r.final_avg_reward for r in results]
        
        conv_data.append({
            "Method": method_name,
            "Regret (mean ± std)": f"{np.mean(regrets):.1f} ± {np.std(regrets):.1f}",
            "Final F1 (mean ± std)": f"{np.mean(rewards):.4f} ± {np.std(rewards):.4f}",
            "Policy Accuracy": f"{np.mean([r.policy_accuracy for r in results]):.1%}",
            "Convergence Round": f"{int(np.mean(convs))}" if convs else "Did not converge",
            "Converged Seeds": f"{len(convs)}/{len(results)}",
        })
    
    st.dataframe(conv_data, use_container_width=True, hide_index=True)
    
    # ── Key Takeaway ──
    if "AHMN-Full" in selected_methods and len(selected_methods) > 1:
        ahmn_regret = np.mean([r.total_regret for r in all_results["AHMN-Full"]])
        
        for baseline in ["Random", "TS (base)", "UCB1"]:
            if baseline in all_results:
                base_regret = np.mean([r.total_regret for r in all_results[baseline]])
                improvement = (base_regret - ahmn_regret) / base_regret * 100
                if improvement > 0:
                    st.success(
                        f"**AHMN-Full reduces regret by {improvement:.1f}% vs {baseline}** "
                        f"({ahmn_regret:.1f} vs {base_regret:.1f})"
                    )

else:
    st.markdown("""
    ### How This Works
    
    1. **Select a scenario** — each tests a different challenge
    2. **Choose methods** to compare (AHMN-Full vs baselines)
    3. **Click Run** — experiments execute in real-time
    4. **Watch the curves diverge** — lower regret = better learning
    
    > **Tip for viva**: Start with "stationary" to show AHMN doesn't hurt, 
    > then switch to "cold_start" or "concept_drift" to show where it shines.
    """)
