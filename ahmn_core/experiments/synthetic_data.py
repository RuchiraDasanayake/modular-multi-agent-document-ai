"""
Synthetic environment for AHMN experimental evaluation.

Simulates document processing scenarios with:
- Multiple vendors, each with different true reward rates per OCR policy
- Cold-start events (new vendors appearing mid-experiment)
- Concept drift (vendor template changes shifting true rewards)
- Structured embedding space so RABI neighbor similarity is meaningful

Design Decisions:
- Embeddings are crafted (not random) to control cosine similarity
- Cold-start scenarios concentrate evaluation on new vendors
- Drift scenarios focus on few vendors so DAAF accumulates clear signal
"""

import numpy as np
from dataclasses import dataclass, field

@dataclass
class PolicyConfig:
    """True (hidden) reward parameters for one policy on one vendor."""
    true_mean: float       # True expected reward (F1 score)
    noise_std: float       # Noise around true mean (within-trial variance)

@dataclass
class VendorProfile:
    """
    Simulated vendor with per-policy true reward distributions.
    
    The bandit algorithms do NOT see true_means — they must learn them.
    """
    vendor_id: str
    doc_type: str
    policies: dict[str, PolicyConfig]  # policy_id -> true reward config
    embedding: np.ndarray              # synthetic embedding for similarity
    appears_at_round: int = 0          # When this vendor first appears (cold-start)
    weight: float = 1.0                # Sampling weight (higher = more frequent)
    
    @property
    def best_policy(self) -> str:
        """Oracle: the truly best policy (unknown to algorithms)."""
        return max(self.policies, key=lambda p: self.policies[p].true_mean)
    
    @property
    def best_mean(self) -> float:
        """Oracle: best achievable mean reward."""
        return self.policies[self.best_policy].true_mean
    
    def sample_reward(self, policy_id: str, rng: np.random.RandomState) -> float:
        """Sample a noisy reward from the true distribution."""
        cfg = self.policies[policy_id]
        reward = rng.normal(cfg.true_mean, cfg.noise_std)
        return float(np.clip(reward, 0.0, 1.0))

@dataclass
class DriftEvent:
    """Specifies a change in a vendor's true reward landscape."""
    vendor_id: str
    at_round: int
    new_policies: dict[str, PolicyConfig]  # Replacement reward configs

@dataclass
class Scenario:
    """
    Complete experimental scenario.
    
    Defines vendors, policies, drift events, and simulation parameters.
    """
    name: str
    description: str
    vendors: list[VendorProfile]
    policy_ids: list[str]
    n_rounds: int
    drift_events: list[DriftEvent] = field(default_factory=list)
    
    def get_active_vendors(self, round_num: int) -> list[VendorProfile]:
        """Vendors available at this round (for cold-start simulation)."""
        return [v for v in self.vendors if v.appears_at_round <= round_num]

# ═══════════════════════════════════════════════════════════════════════════════
# EMBEDDING UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

DIM = 32  # Synthetic embedding dimension

def _unit_vec(v: np.ndarray) -> np.ndarray:
    """Normalize to unit vector."""
    n = np.linalg.norm(v)
    return v / max(n, 1e-10)

def _make_cluster_embedding(cluster_id: int, within_id: int,
                            spread: float = 0.15) -> np.ndarray:
    """
    Create an embedding in a structured space.
    
    Same cluster_id → high cosine similarity
    Different cluster_id → low cosine similarity
    within_id and spread control intra-cluster variation.
    """
    rng = np.random.RandomState(cluster_id * 1000)
    base = rng.randn(DIM)
    base = _unit_vec(base)
    
    rng2 = np.random.RandomState(cluster_id * 1000 + within_id + 1)
    noise = rng2.randn(DIM) * spread
    
    return _unit_vec(base + noise)

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / max(norm, 1e-10))

POLICY_IDS = ["table_heavy", "forms", "scanned_text", "mixed_content", "default"]

# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1: STATIONARY (baseline)
# ═══════════════════════════════════════════════════════════════════════════════

def create_stationary_scenario(n_rounds: int = 1000) -> Scenario:
    """
    Stationary environment — no drift, no cold-start.

    Tests pure bandit learning. 4 vendors with different document types,
    each best served by the policy whose extraction surface matches the
    document structure. RABI and DAAF should have minimal (neutral) impact.

    True-mean calibration rationale:
    - A policy whose expected fields/preprocessing match the doc type scores ~0.85-0.92
    - A mismatched but generic policy (default) scores ~0.55-0.70
    - A mismatched specialized policy scores ~0.45-0.65
    """
    vendors = [
        # Invoice vendor → table_heavy wins (tabular line items, totals, tax)
        VendorProfile(
            vendor_id="vendor_A", doc_type="invoice",
            policies={
                "table_heavy":    PolicyConfig(true_mean=0.88, noise_std=0.05),
                "forms":          PolicyConfig(true_mean=0.62, noise_std=0.07),
                "scanned_text":   PolicyConfig(true_mean=0.55, noise_std=0.07),
                "mixed_content":  PolicyConfig(true_mean=0.72, noise_std=0.06),
                "default":        PolicyConfig(true_mean=0.68, noise_std=0.06),
            },
            embedding=_make_cluster_embedding(1, 0),
        ),
        # Form vendor → forms wins (structured key-value layout)
        VendorProfile(
            vendor_id="vendor_B", doc_type="form_document",
            policies={
                "table_heavy":    PolicyConfig(true_mean=0.65, noise_std=0.06),
                "forms":          PolicyConfig(true_mean=0.90, noise_std=0.04),
                "scanned_text":   PolicyConfig(true_mean=0.58, noise_std=0.07),
                "mixed_content":  PolicyConfig(true_mean=0.70, noise_std=0.06),
                "default":        PolicyConfig(true_mean=0.66, noise_std=0.06),
            },
            embedding=_make_cluster_embedding(2, 0),
        ),
        # Receipt vendor → table_heavy wins (tabular item lists)
        VendorProfile(
            vendor_id="vendor_C", doc_type="receipt",
            policies={
                "table_heavy":    PolicyConfig(true_mean=0.86, noise_std=0.05),
                "forms":          PolicyConfig(true_mean=0.60, noise_std=0.07),
                "scanned_text":   PolicyConfig(true_mean=0.64, noise_std=0.06),
                "mixed_content":  PolicyConfig(true_mean=0.72, noise_std=0.06),
                "default":        PolicyConfig(true_mean=0.67, noise_std=0.06),
            },
            embedding=_make_cluster_embedding(3, 0),
        ),
        # Contract vendor → mixed_content wins (multi-section legal text)
        VendorProfile(
            vendor_id="vendor_D", doc_type="contract",
            policies={
                "table_heavy":    PolicyConfig(true_mean=0.55, noise_std=0.07),
                "forms":          PolicyConfig(true_mean=0.52, noise_std=0.07),
                "scanned_text":   PolicyConfig(true_mean=0.78, noise_std=0.05),
                "mixed_content":  PolicyConfig(true_mean=0.87, noise_std=0.04),
                "default":        PolicyConfig(true_mean=0.65, noise_std=0.06),
            },
            embedding=_make_cluster_embedding(4, 0),
        ),
    ]
    
    return Scenario(
        name="stationary",
        description="Stationary environment — no drift, no cold-start. Tests pure bandit learning.",
        vendors=vendors,
        policy_ids=POLICY_IDS,
        n_rounds=n_rounds,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2: COLD-START (highlights RABI)
# ═══════════════════════════════════════════════════════════════════════════════

def create_cold_start_scenario(n_rounds: int = 1500) -> Scenario:
    """
    Cold-start with frequent new vendor arrivals.
    
    Design: 3 established vendors form a "knowledge base." Then 6 new vendors
    arrive in waves. New vendors are in the same cluster as established ones
    so RABI can transfer knowledge. New vendors get higher sampling weight (3x)
    to concentrate evaluation on the cold-start period.
    """
    # Invoice cluster (cluster_id=1) → table_heavy best
    invoice_policies = lambda: {
        "table_heavy":    PolicyConfig(true_mean=0.87, noise_std=0.04),
        "forms":          PolicyConfig(true_mean=0.62, noise_std=0.07),
        "scanned_text":   PolicyConfig(true_mean=0.55, noise_std=0.07),
        "mixed_content":  PolicyConfig(true_mean=0.71, noise_std=0.06),
        "default":        PolicyConfig(true_mean=0.66, noise_std=0.06),
    }
    # Receipt cluster (cluster_id=2) → table_heavy best (tabular items)
    receipt_policies = lambda: {
        "table_heavy":    PolicyConfig(true_mean=0.85, noise_std=0.05),
        "forms":          PolicyConfig(true_mean=0.60, noise_std=0.07),
        "scanned_text":   PolicyConfig(true_mean=0.64, noise_std=0.06),
        "mixed_content":  PolicyConfig(true_mean=0.72, noise_std=0.06),
        "default":        PolicyConfig(true_mean=0.67, noise_std=0.06),
    }

    vendors = [
        # ── Established vendors (knowledge base) ──
        VendorProfile(
            vendor_id="established_inv_1", doc_type="invoice",
            policies=invoice_policies(),
            embedding=_make_cluster_embedding(1, 0, spread=0.05),
            weight=1.0,
        ),
        VendorProfile(
            vendor_id="established_inv_2", doc_type="invoice",
            policies=invoice_policies(),
            embedding=_make_cluster_embedding(1, 1, spread=0.05),
            weight=1.0,
        ),
        VendorProfile(
            vendor_id="established_rct_1", doc_type="receipt",
            policies=receipt_policies(),
            embedding=_make_cluster_embedding(2, 0, spread=0.05),
            weight=1.0,
        ),

        # ── New vendors (cold-start, similar to established) ──
        VendorProfile(
            vendor_id="new_inv_1", doc_type="invoice",
            policies=invoice_policies(),
            embedding=_make_cluster_embedding(1, 2, spread=0.05),
            appears_at_round=300,
            weight=3.0,
        ),
        VendorProfile(
            vendor_id="new_inv_2", doc_type="invoice",
            policies=invoice_policies(),
            embedding=_make_cluster_embedding(1, 3, spread=0.05),
            appears_at_round=450,
            weight=3.0,
        ),
        VendorProfile(
            vendor_id="new_rct_1", doc_type="receipt",
            policies=receipt_policies(),
            embedding=_make_cluster_embedding(2, 1, spread=0.05),
            appears_at_round=600,
            weight=3.0,
        ),
        VendorProfile(
            vendor_id="new_inv_3", doc_type="invoice",
            policies=invoice_policies(),
            embedding=_make_cluster_embedding(1, 4, spread=0.05),
            appears_at_round=750,
            weight=3.0,
        ),
        VendorProfile(
            vendor_id="new_rct_2", doc_type="receipt",
            policies=receipt_policies(),
            embedding=_make_cluster_embedding(2, 2, spread=0.05),
            appears_at_round=900,
            weight=3.0,
        ),
        VendorProfile(
            vendor_id="new_inv_4", doc_type="invoice",
            policies=invoice_policies(),
            embedding=_make_cluster_embedding(1, 5, spread=0.05),
            appears_at_round=1050,
            weight=3.0,
        ),
    ]
    
    return Scenario(
        name="cold_start",
        description="Cold-start: 6 new vendors arrive in waves. RABI transfers from 3 established vendors.",
        vendors=vendors,
        policy_ids=POLICY_IDS,
        n_rounds=n_rounds,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3: CONCEPT DRIFT (highlights DAAF)
# ═══════════════════════════════════════════════════════════════════════════════

def create_drift_scenario(n_rounds: int = 1500) -> Scenario:
    """
    Concept drift — single primary vendor with template changes.
    
    Design: One drifting vendor (90% of rounds) + one stable vendor (10%).
    This gives DAAF clean signal to detect drift with enough per-vendor samples.
    
    Drift events:
    - Round 500: Gradual drift (Tesseract degrades slightly)
    - Round 1000: Abrupt drift (best policy completely shifts)
    """
    vendors = [
        # Drifting vendor: starts as invoice (table_heavy best), templates
        # redesigned to narrative layout (mixed_content best), then fully
        # scanned noisy forms (scanned_text best).
        VendorProfile(
            vendor_id="drifting_vendor", doc_type="invoice",
            policies={
                "table_heavy":    PolicyConfig(true_mean=0.88, noise_std=0.04),
                "forms":          PolicyConfig(true_mean=0.62, noise_std=0.07),
                "scanned_text":   PolicyConfig(true_mean=0.55, noise_std=0.07),
                "mixed_content":  PolicyConfig(true_mean=0.72, noise_std=0.06),
                "default":        PolicyConfig(true_mean=0.68, noise_std=0.06),
            },
            embedding=_make_cluster_embedding(5, 0),
            weight=9.0,  # 90% of rounds
        ),
        VendorProfile(
            vendor_id="stable_vendor", doc_type="invoice",
            policies={
                "table_heavy":    PolicyConfig(true_mean=0.82, noise_std=0.05),
                "forms":          PolicyConfig(true_mean=0.65, noise_std=0.06),
                "scanned_text":   PolicyConfig(true_mean=0.60, noise_std=0.06),
                "mixed_content":  PolicyConfig(true_mean=0.75, noise_std=0.05),
                "default":        PolicyConfig(true_mean=0.70, noise_std=0.06),
            },
            embedding=_make_cluster_embedding(6, 0),
            weight=1.0,
        ),
    ]

    drift_events = [
        # Gradual drift at round 500: tables deteriorate, layout goes mixed
        DriftEvent(
            vendor_id="drifting_vendor",
            at_round=500,
            new_policies={
                "table_heavy":    PolicyConfig(true_mean=0.72, noise_std=0.06),
                "forms":          PolicyConfig(true_mean=0.60, noise_std=0.07),
                "scanned_text":   PolicyConfig(true_mean=0.65, noise_std=0.06),
                "mixed_content":  PolicyConfig(true_mean=0.85, noise_std=0.04),
                "default":        PolicyConfig(true_mean=0.72, noise_std=0.06),
            },
        ),
        # Abrupt drift at round 1000: documents are now low-quality scanned narrative text
        DriftEvent(
            vendor_id="drifting_vendor",
            at_round=1000,
            new_policies={
                "table_heavy":    PolicyConfig(true_mean=0.50, noise_std=0.08),
                "forms":          PolicyConfig(true_mean=0.55, noise_std=0.07),
                "scanned_text":   PolicyConfig(true_mean=0.90, noise_std=0.04),
                "mixed_content":  PolicyConfig(true_mean=0.72, noise_std=0.06),
                "default":        PolicyConfig(true_mean=0.64, noise_std=0.07),
            },
        ),
    ]
    
    return Scenario(
        name="concept_drift",
        description="Concept drift: gradual at 500, abrupt at 1000. Single-vendor focus for DAAF.",
        vendors=vendors,
        policy_ids=POLICY_IDS,
        n_rounds=n_rounds,
        drift_events=drift_events,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4: COMBINED (full AHMN system test)
# ═══════════════════════════════════════════════════════════════════════════════

def create_combined_scenario(n_rounds: int = 2000) -> Scenario:
    """
    Combined: cold-start + drift + multi-vendor.
    
    2 established vendors, 3 new arrivals, and drift on one established vendor.
    Tests the full system: RABI handles cold-start, DAAF handles drift.
    """
    invoice_policies = lambda: {
        "table_heavy":    PolicyConfig(true_mean=0.87, noise_std=0.04),
        "forms":          PolicyConfig(true_mean=0.62, noise_std=0.07),
        "scanned_text":   PolicyConfig(true_mean=0.55, noise_std=0.07),
        "mixed_content":  PolicyConfig(true_mean=0.72, noise_std=0.06),
        "default":        PolicyConfig(true_mean=0.66, noise_std=0.06),
    }
    receipt_policies = lambda: {
        "table_heavy":    PolicyConfig(true_mean=0.85, noise_std=0.05),
        "forms":          PolicyConfig(true_mean=0.60, noise_std=0.07),
        "scanned_text":   PolicyConfig(true_mean=0.64, noise_std=0.06),
        "mixed_content":  PolicyConfig(true_mean=0.72, noise_std=0.06),
        "default":        PolicyConfig(true_mean=0.67, noise_std=0.06),
    }

    vendors = [
        # ── Established ──
        VendorProfile(
            vendor_id="corp_A", doc_type="invoice",
            policies=invoice_policies(),
            embedding=_make_cluster_embedding(1, 0, spread=0.05),
            weight=3.0,
        ),
        VendorProfile(
            vendor_id="corp_B", doc_type="receipt",
            policies=receipt_policies(),
            embedding=_make_cluster_embedding(2, 0, spread=0.05),
            weight=2.0,
        ),

        # ── Cold-start arrivals ──
        VendorProfile(
            vendor_id="new_C", doc_type="invoice",
            policies=invoice_policies(),
            embedding=_make_cluster_embedding(1, 1, spread=0.05),
            appears_at_round=400,
            weight=4.0,
        ),
        VendorProfile(
            vendor_id="new_D", doc_type="receipt",
            policies=receipt_policies(),
            embedding=_make_cluster_embedding(2, 1, spread=0.05),
            appears_at_round=800,
            weight=4.0,
        ),
        VendorProfile(
            vendor_id="new_E", doc_type="invoice",
            policies=invoice_policies(),
            embedding=_make_cluster_embedding(1, 2, spread=0.05),
            appears_at_round=1200,
            weight=4.0,
        ),
    ]

    drift_events = [
        # corp_A redesigns templates at round 600 to narrative mixed-content form
        DriftEvent(
            vendor_id="corp_A",
            at_round=600,
            new_policies={
                "table_heavy":    PolicyConfig(true_mean=0.60, noise_std=0.07),
                "forms":          PolicyConfig(true_mean=0.58, noise_std=0.07),
                "scanned_text":   PolicyConfig(true_mean=0.70, noise_std=0.06),
                "mixed_content":  PolicyConfig(true_mean=0.86, noise_std=0.04),
                "default":        PolicyConfig(true_mean=0.70, noise_std=0.06),
            },
        ),
    ]
    
    return Scenario(
        name="combined",
        description="Combined: cold-start arrivals + drift. Tests full RABI + DAAF system.",
        vendors=vendors,
        policy_ids=POLICY_IDS,
        n_rounds=n_rounds,
        drift_events=drift_events,
    )

def get_all_scenarios() -> list[Scenario]:
    """Return all predefined experimental scenarios."""
    return [
        create_stationary_scenario(),
        create_cold_start_scenario(),
        create_drift_scenario(),
        create_combined_scenario(),
    ]
