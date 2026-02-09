"""
Experiments router — run simulations, fetch stored results, interactive demos.
"""

import sys
import os
import json
import numpy as np
from typing import Any
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from psycopg import AsyncConnection

from ..deps import get_db, get_current_user

# Ensure ahmn_core is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from ahmn_core.services.drift_forgetting import DriftEstimator
from ahmn_core.services.rabi import RABIInitializer, NeighborInfo
from ahmn_core.experiments.synthetic_data import (
    create_stationary_scenario, create_cold_start_scenario,
    create_drift_scenario, create_combined_scenario,
    POLICY_IDS, VendorProfile, PolicyConfig, DriftEvent, Scenario,
    _make_cluster_embedding,
)
from ahmn_core.experiments.run_experiments import (
    ThompsonSamplingRunner, AHMNDAAFRunner, AHMNRABIRunner,
    AHMNFullRunner, UCB1Runner, EpsilonGreedyRunner, RandomRunner,
    run_single,
)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

# ── Pre-loaded JSON results ──
_RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ahmn_core" / "output"


def _load_json(name: str) -> dict | None:
    p = _RESULTS_DIR / name
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


@router.get("/results")
async def get_results(user: dict = Depends(get_current_user)):
    """Return pre-computed experiment results (from JSON)."""
    data = _load_json("experiment_results.json")
    if data is None:
        raise HTTPException(404, "Experiment results file not found")
    return data


@router.get("/robustness")
async def get_robustness(user: dict = Depends(get_current_user)):
    """Return robustness sweep results."""
    data = _load_json("robustness_results.json")
    if data is None:
        raise HTTPException(404, "Robustness results file not found")
    return data


@router.get("/db-results")
async def get_db_results(
    db: AsyncConnection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Return experiment results stored in database."""
    async with db.cursor() as cur:
        await cur.execute(
            """SELECT id, method, scenario, seed, total_regret,
                      final_accuracy, convergence_round, created_at
               FROM experiment_runs ORDER BY created_at DESC LIMIT 500"""
        )
        rows = await cur.fetchall()
    return [
        {
            "id": str(r[0]), "method": r[1], "scenario": r[2],
            "seed": r[3], "total_regret": r[4], "final_accuracy": r[5],
            "convergence_round": r[6], "created_at": r[7].isoformat() if r[7] else None,
        }
        for r in rows
    ]


# ── Interactive Demo Endpoints ──

@router.post("/demo/daaf")
async def run_daaf_demo(
    params: dict[str, Any],
    user: dict = Depends(get_current_user),
):
    """Run interactive DAAF drift detection demo and return chart data."""
    pre_mean = params.get("pre_drift_mean", 0.85)
    post_mean = params.get("post_drift_mean", 0.55)
    noise_std = params.get("noise_std", 0.06)
    drift_round = params.get("drift_round", 150)
    window_size = params.get("window_size", 50)
    n_rounds = params.get("n_rounds", 300)

    rng = np.random.RandomState(42)
    rewards = []
    for t in range(n_rounds):
        mean = pre_mean if t < drift_round else post_mean
        r = float(np.clip(rng.normal(mean, noise_std), 0.0, 1.0))
        rewards.append(r)

    estimator = DriftEstimator(
        window_size=window_size, min_samples=10,
        drift_threshold=0.05, abrupt_threshold=0.15,
    )

    drift_magnitudes, gammas, drift_types, recent_means = [], [], [], []
    for reward in rewards:
        metrics = estimator.update(reward)
        drift_magnitudes.append(metrics.drift_magnitude)
        gammas.append(metrics.optimal_gamma)
        drift_types.append(metrics.drift_type.value)
        recent_means.append(float(np.mean(list(estimator.recent_window))) if estimator.recent_window else reward)

    # Detection delay
    detected_at = None
    for t in range(drift_round, n_rounds):
        if drift_types[t] != "none":
            detected_at = t
            break

    return {
        "rewards": rewards,
        "recent_means": recent_means,
        "drift_magnitudes": drift_magnitudes,
        "gammas": gammas,
        "drift_types": drift_types,
        "detection_delay": (detected_at - drift_round) if detected_at else None,
        "peak_gamma": max(gammas[drift_round:]) if drift_round < len(gammas) else 0,
    }


@router.post("/demo/rabi")
async def run_rabi_demo(
    params: dict[str, Any],
    user: dict = Depends(get_current_user),
):
    """Run interactive RABI cold-start demo and return chart data."""
    temperature = params.get("temperature", 0.5)
    threshold = params.get("threshold", 0.3)
    k = params.get("k", 5)

    rabi = RABIInitializer(k=k, similarity_threshold=threshold, temperature=temperature)

    # Create mock neighbors
    neighbors = [
        NeighborInfo(context_hash=f"ctx_{i}", policy_id="ocr_tesseract",
                     alpha=15 + i * 3, beta=3 + i, similarity=0.9 - i * 0.1, n_samples=15 + i)
        for i in range(k)
    ]

    prior = rabi.initialize_prior(neighbors)
    weights = rabi.compute_weights([n.similarity for n in neighbors])

    # Generate beta distribution points
    from scipy.stats import beta as beta_dist
    x = np.linspace(0, 1, 200).tolist()
    flat_pdf = beta_dist.pdf(x, 1, 1).tolist()
    rabi_pdf = beta_dist.pdf(x, prior.alpha, prior.beta).tolist()

    return {
        "prior": {"alpha": prior.alpha, "beta": prior.beta, "mean": prior.mean,
                   "confidence": prior.confidence, "n_neighbors": prior.n_neighbors},
        "neighbors": [{"hash": n.context_hash, "similarity": n.similarity,
                        "alpha": n.alpha, "beta": n.beta, "mean": n.mean_reward} for n in neighbors],
        "weights": weights,
        "distribution": {"x": x, "flat_pdf": flat_pdf, "rabi_pdf": rabi_pdf},
    }


@router.post("/demo/comparison")
async def run_comparison_demo(
    params: dict[str, Any],
    user: dict = Depends(get_current_user),
):
    """Run TS vs DAAF comparison under drift."""
    drift_magnitude = params.get("drift_magnitude", 0.20)
    n_seeds = params.get("seeds", 10)

    vendors = [
        VendorProfile(
            vendor_id="vendor_drift", doc_type="invoice",
            policies={
                "ocr_tesseract": PolicyConfig(true_mean=0.88, noise_std=0.05),
                "ocr_easyocr": PolicyConfig(true_mean=0.70, noise_std=0.06),
                "ocr_azure_cv": PolicyConfig(true_mean=0.75, noise_std=0.05),
            },
            embedding=_make_cluster_embedding(1, 0), weight=1.0,
        ),
    ]

    scenario = Scenario(
        name="demo_drift",
        description=f"Drift demo with magnitude {drift_magnitude}",
        vendors=vendors, policy_ids=POLICY_IDS, n_rounds=1000,
        drift_events=[
            DriftEvent(
                vendor_id="vendor_drift", at_round=500,
                new_policies={
                    "ocr_tesseract": PolicyConfig(true_mean=0.88 - drift_magnitude, noise_std=0.05),
                    "ocr_easyocr": PolicyConfig(true_mean=0.70, noise_std=0.06),
                    "ocr_azure_cv": PolicyConfig(true_mean=0.75 + drift_magnitude, noise_std=0.05),
                },
            )
        ],
    )

    ts_results, daaf_results = [], []
    for seed in range(n_seeds):
        ts_results.append(run_single(ThompsonSamplingRunner(POLICY_IDS), scenario, seed))
        daaf_results.append(run_single(AHMNDAAFRunner(POLICY_IDS), scenario, seed))

    ts_regret_avg = np.mean([r.cumulative_regret for r in ts_results], axis=0).tolist()
    daaf_regret_avg = np.mean([r.cumulative_regret for r in daaf_results], axis=0).tolist()

    ts_rewards_avg = np.mean([r.rewards for r in ts_results], axis=0)
    daaf_rewards_avg = np.mean([r.rewards for r in daaf_results], axis=0)

    window = 50
    ts_rolling = np.convolve(ts_rewards_avg, np.ones(window) / window, mode="valid").tolist()
    daaf_rolling = np.convolve(daaf_rewards_avg, np.ones(window) / window, mode="valid").tolist()

    total_ts = float(np.mean([r.total_regret for r in ts_results]))
    total_daaf = float(np.mean([r.total_regret for r in daaf_results]))

    return {
        "ts_cumulative_regret": ts_regret_avg,
        "daaf_cumulative_regret": daaf_regret_avg,
        "ts_rolling_reward": ts_rolling,
        "daaf_rolling_reward": daaf_rolling,
        "rolling_start": window - 1,
        "total_ts_regret": total_ts,
        "total_daaf_regret": total_daaf,
        "improvement_pct": (total_ts - total_daaf) / total_ts * 100 if total_ts > 0 else 0,
    }
