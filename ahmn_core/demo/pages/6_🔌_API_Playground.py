"""
Page 6: API Playground
Simulate the AHMN API without needing Docker/PostgreSQL/Redis.
"""

import streamlit as st
import numpy as np
import json
import uuid
import sys
import os
import random
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ahmn_core.services.rabi import RABIInitializer, NeighborInfo
from ahmn_core.services.drift_forgetting import DriftEstimator, AdaptiveForgettingBandit

st.set_page_config(page_title="AHMN — API Playground", page_icon="🔌", layout="wide")

st.title("🔌 API Playground")
st.markdown("*Simulate the production AHMN API — no Docker or database needed*")

st.markdown("---")

# ── Initialize session state ──
if "api_ltm" not in st.session_state:
    # Simulated LTM: context_hash -> {policy_id -> {alpha, beta}}
    st.session_state.api_ltm = {
        "invoice:acme": {
            "ocr_tesseract": {"alpha": 15.0, "beta": 3.0},
            "ocr_easyocr": {"alpha": 5.0, "beta": 8.0},
            "ocr_azure_cv": {"alpha": 10.0, "beta": 4.0},
        },
        "invoice:globex": {
            "ocr_tesseract": {"alpha": 8.0, "beta": 6.0},
            "ocr_easyocr": {"alpha": 18.0, "beta": 4.0},
            "ocr_azure_cv": {"alpha": 7.0, "beta": 5.0},
        },
        "receipt:initech": {
            "ocr_tesseract": {"alpha": 6.0, "beta": 7.0},
            "ocr_easyocr": {"alpha": 4.0, "beta": 6.0},
            "ocr_azure_cv": {"alpha": 20.0, "beta": 3.0},
        },
    }
    st.session_state.api_stm = {}  # advice_id -> context
    st.session_state.api_history = []
    st.session_state.api_drift_estimators = {}

ltm = st.session_state.api_ltm
stm = st.session_state.api_stm
history = st.session_state.api_history

# ── Show current LTM state ──
st.markdown("### 📦 Current Knowledge Base (LTM)")
st.markdown("*This simulates the PostgreSQL + pgvector storage with Beta parameters*")

ltm_display = []
for ctx, policies in ltm.items():
    for pid, params in policies.items():
        a, b = params["alpha"], params["beta"]
        total = a + b
        ltm_display.append({
            "Context": ctx,
            "Policy": pid,
            "α (successes+1)": f"{a:.1f}",
            "β (failures+1)": f"{b:.1f}",
            "E[reward]": f"{a/total:.3f}",
            "Samples": f"{int(a + b - 2)}",
            "Uncertainty": f"{(a * b) / (total**2 * (total+1)):.4f}",
        })

st.dataframe(ltm_display, use_container_width=True, hide_index=True)

st.markdown("---")

# ── API Endpoints ──
col1, col2 = st.columns(2)

# ── POST /advice ──
with col1:
    st.markdown("### 📤 POST /advice")
    st.markdown("*Get policy recommendation for a document*")
    
    doc_type = st.selectbox("doc_type", ["invoice", "receipt", "contract"])
    vendor = st.text_input("vendor", "acme", help="Try: acme, globex, initech, or a new name")
    
    use_rabi = st.checkbox("Enable RABI (cold-start transfer)", value=True)
    
    if st.button("Send Request", type="primary", key="advice_btn"):
        context_key = f"{doc_type}:{vendor}"
        advice_id = str(uuid.uuid4())
        
        # Check if context exists in LTM
        if context_key in ltm:
            # Known context → Thompson Sampling
            policies = ltm[context_key]
            best_sample = -1
            best_policy: str = list(policies.keys())[0]
            samples = {}
            
            for pid, params in policies.items():
                sample = random.betavariate(params["alpha"], params["beta"])
                samples[pid] = sample
                if sample > best_sample:
                    best_sample = sample
                    best_policy = pid
            
            a = policies[best_policy]["alpha"]
            b = policies[best_policy]["beta"]
            total = a + b
            variance = (a * b) / (total**2 * (total + 1))
            confidence = min(0.95, 1.0 - variance * 10)
            
            response = {
                "advice_id": advice_id,
                "policy_id": best_policy,
                "policy_data": {"engine": best_policy, "settings": "default"},
                "retrieval_source": "LTM",
                "confidence": round(confidence, 3),
                "rabi_used": False,
                "n_neighbors": None,
            }
            
            st.json(response)
            
            # Show Thompson Sampling visualization
            st.markdown("**Thompson Samples:**")
            for pid, sample in sorted(samples.items(), key=lambda x: -x[1]):
                marker = " ← SELECTED" if pid == best_policy else ""
                bar_len = int(sample * 30)
                st.text(f"  {pid:20s} θ={sample:.4f} {'█' * bar_len}{marker}")
        
        elif use_rabi:
            # New context → RABI transfer
            rabi = RABIInitializer(k=5, similarity_threshold=0.3, temperature=0.5)
            
            # Build fake neighbors from existing contexts
            neighbors = []
            sim_base = 0.75
            for ctx, policies in ltm.items():
                for pid, params in policies.items():
                    # Simulate similarity based on matching doc_type
                    ctx_doc = ctx.split(":")[0]
                    sim = sim_base if ctx_doc == doc_type else sim_base * 0.5
                    sim += random.uniform(-0.1, 0.1)
                    sim = max(0, min(1, sim))
                    
                    neighbors.append(NeighborInfo(
                        context_hash=ctx,
                        policy_id=pid,
                        alpha=params["alpha"],
                        beta=params["beta"],
                        similarity=sim,
                        n_samples=int(params["alpha"] + params["beta"] - 2),
                    ))
            
            # Group by policy and use RABI for each
            policy_priors = {}
            for pid in ["ocr_tesseract", "ocr_easyocr", "ocr_azure_cv"]:
                pid_neighbors = [n for n in neighbors if n.policy_id == pid]
                prior = rabi.initialize_prior(pid_neighbors)
                policy_priors[pid] = prior
            
            # Thompson Sampling with RABI priors
            best_sample = -1
            best_policy: str = list(policy_priors.keys())[0]
            samples = {}
            
            for pid, prior in policy_priors.items():
                sample = random.betavariate(max(0.1, prior.alpha), max(0.1, prior.beta))
                samples[pid] = sample
                if sample > best_sample:
                    best_sample = sample
                    best_policy = pid
            
            n_neighbors = max(p.n_neighbors for p in policy_priors.values())
            avg_conf = np.mean([p.confidence for p in policy_priors.values()])
            
            response = {
                "advice_id": advice_id,
                "policy_id": best_policy,
                "policy_data": {"engine": best_policy, "settings": "default"},
                "retrieval_source": "LTM",
                "confidence": round(avg_conf, 3),
                "rabi_used": True,
                "n_neighbors": n_neighbors,
            }
            
            st.json(response)
            
            st.markdown("**RABI-Initialized Priors:**")
            for pid, prior in policy_priors.items():
                marker = " ← SELECTED" if pid == best_policy else ""
                st.text(f"  {pid:20s} α={prior.alpha:.2f} β={prior.beta:.2f} "
                       f"E[θ]={prior.mean:.3f} (from {prior.n_neighbors} neighbors){marker}")
            
            # Add to LTM for future use
            ltm[context_key] = {
                pid: {"alpha": prior.alpha, "beta": prior.beta}
                for pid, prior in policy_priors.items()
            }
            st.info(f"New context '{context_key}' added to LTM via RABI transfer!")
        
        else:
            # New context, no RABI → flat prior
            response = {
                "advice_id": advice_id,
                "policy_id": "ocr_tesseract",
                "policy_data": {"engine": "ocr_tesseract", "settings": "default"},
                "retrieval_source": "DEFAULT",
                "confidence": 0.3,
                "rabi_used": False,
                "n_neighbors": None,
            }
            
            st.json(response)
            
            ltm[context_key] = {
                "ocr_tesseract": {"alpha": 1.0, "beta": 1.0},
                "ocr_easyocr": {"alpha": 1.0, "beta": 1.0},
                "ocr_azure_cv": {"alpha": 1.0, "beta": 1.0},
            }
            st.warning("New context with flat priors — no RABI transfer.")
        
        # Store in STM
        stm[advice_id] = {
            "doc_type": doc_type,
            "vendor": vendor,
            "context_key": context_key,
            "policy_id": response["policy_id"],
        }

# ── POST /log ──
with col2:
    st.markdown("### 📥 POST /log")
    st.markdown("*Log the outcome after processing*")
    
    if stm:
        advice_options = list(stm.keys())
        selected_advice = st.selectbox(
            "advice_id",
            advice_options,
            format_func=lambda x: f"{x[:8]}... ({stm[x]['context_key']} → {stm[x]['policy_id']})"
        )
        
        f1_score = st.slider("f1_score (reward)", 0.0, 1.0, 0.85, 0.01)
        cost = st.number_input("cost", value=0.003, format="%.4f")
        processing_time = st.number_input("processing_time_ms", value=450, step=50)
        
        use_daaf = st.checkbox("Enable DAAF (drift-aware forgetting)", value=True)
        
        if st.button("Log Outcome", type="primary", key="log_btn"):
            ctx_info = stm[selected_advice]
            context_key = ctx_info["context_key"]
            policy_id = ctx_info["policy_id"]
            
            # DAAF check
            gamma = 0.0
            drift_type = "none"
            
            if use_daaf:
                if context_key not in st.session_state.api_drift_estimators:
                    st.session_state.api_drift_estimators[context_key] = DriftEstimator(
                        window_size=50, min_samples=10,
                        drift_threshold=0.05, abrupt_threshold=0.15,
                    )
                
                estimator = st.session_state.api_drift_estimators[context_key]
                metrics = estimator.update(f1_score)
                gamma = metrics.optimal_gamma
                drift_type = metrics.drift_type.value
            
            # Update LTM
            if context_key in ltm and policy_id in ltm[context_key]:
                params = ltm[context_key][policy_id]
                
                old_alpha = params["alpha"]
                old_beta = params["beta"]
                
                if gamma > 0.001:
                    # DAAF forgetting
                    retention = 1.0 - gamma
                    params["alpha"] = 1.0 + retention * (params["alpha"] - 1.0) + f1_score
                    params["beta"] = 1.0 + retention * (params["beta"] - 1.0) + (1 - f1_score)
                else:
                    # Standard Bayesian update
                    params["alpha"] += f1_score
                    params["beta"] += (1 - f1_score)
                
                new_total = params["alpha"] + params["beta"]
                
                st.json({
                    "status": "logged",
                    "update": {
                        "context": context_key,
                        "policy": policy_id,
                        "alpha": f"{old_alpha:.2f} → {params['alpha']:.2f}",
                        "beta": f"{old_beta:.2f} → {params['beta']:.2f}",
                        "E[reward]": f"{params['alpha']/new_total:.4f}",
                        "daaf_gamma": round(gamma, 4),
                        "drift_type": drift_type,
                    }
                })
                
                if gamma > 0.001:
                    st.warning(f"DAAF applied forgetting: γ = {gamma:.4f} ({drift_type} drift)")
                else:
                    st.success("Standard Bayesian update applied.")
                
                # Add to history
                history.append({
                    "time": time.strftime("%H:%M:%S"),
                    "context": context_key,
                    "policy": policy_id,
                    "f1": f1_score,
                    "gamma": gamma,
                    "drift": drift_type,
                })
            else:
                st.error("Context or policy not found in LTM!")
    else:
        st.info("No advice requests yet. Send a /advice request first.")

st.markdown("---")

# ── History ──
if history:
    st.markdown("### 📜 Session History")
    st.dataframe(list(reversed(history[-20:])), use_container_width=True, hide_index=True)

# ── Updated LTM ──
st.markdown("### 📦 Updated Knowledge Base (after interactions)")

ltm_display2 = []
for ctx, policies in ltm.items():
    for pid, params in policies.items():
        a, b = params["alpha"], params["beta"]
        total = a + b
        ltm_display2.append({
            "Context": ctx,
            "Policy": pid,
            "α": f"{a:.2f}",
            "β": f"{b:.2f}",
            "E[reward]": f"{a/total:.4f}",
            "Samples": f"{int(a + b - 2)}",
        })

st.dataframe(ltm_display2, use_container_width=True, hide_index=True)

# Reset button
if st.button("🔄 Reset All State"):
    for key in ["api_ltm", "api_stm", "api_history", "api_drift_estimators"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

st.markdown("---")

st.markdown("""
### 💡 How to Demo This in Your Viva

1. **Show known vendor**: Select `invoice` + `acme` → see Thompson Sampling pick the best policy with high confidence
2. **Show RABI**: Type a NEW vendor name (e.g., `newcorp`) → see RABI transfer knowledge
3. **Log outcomes**: Submit F1 scores and watch α/β update in real-time
4. **Show DAAF**: Log several outcomes then suddenly drop the F1 → watch drift detection kick in
5. **Point out**: This is a real production API pattern — the dashboard is just simulating what PostgreSQL + Redis do

**The production system runs the exact same logic** via `POST /advice`, `POST /log`, and `POST /feedback` endpoints.
""")
