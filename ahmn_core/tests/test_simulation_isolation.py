"""Independent seeds and methods must start from the same drift schedule."""
from copy import deepcopy

import numpy as np
import pytest

from ahmn_core.experiments.run_experiments import (
    AHMNFullRunner,
    RandomRunner,
    ThompsonSamplingRunner,
    run_single,
)
from ahmn_core.experiments.synthetic_data import (
    DriftEvent,
    PolicyConfig,
    Scenario,
    VendorProfile,
    create_drift_scenario,
)


def tiny_drift():
    initial = {"a": PolicyConfig(0.9, 0.0), "b": PolicyConfig(0.1, 0.0)}
    changed = {"a": PolicyConfig(0.1, 0.0), "b": PolicyConfig(0.6, 0.0)}
    return Scenario(
        name="tiny_drift", description="One vendor changes after the first round",
        vendors=[VendorProfile("vendor", "synthetic", initial, np.array([1.0, 0.0]))],
        policy_ids=["a", "b"], n_rounds=2,
        drift_events=[DriftEvent("vendor", 1, changed)],
    )


def fingerprint(result):
    return (result.rewards, result.cumulative_regret, result.oracle_rewards,
            result.selected_policies, result.optimal_policies)


def test_drift_does_not_mutate_caller_scenario():
    scenario = tiny_drift()
    result = run_single(RandomRunner(scenario.policy_ids), scenario, seed=0)
    assert result.oracle_rewards == [0.9, 0.6]
    assert scenario.vendors[0].policies["a"].true_mean == 0.9
    assert scenario.vendors[0].policies["b"].true_mean == 0.1


def test_method_order_does_not_change_starting_environment():
    methods = [RandomRunner, ThompsonSamplingRunner]

    def execute(order):
        scenario = tiny_drift()
        return {method.__name__: fingerprint(run_single(method(scenario.policy_ids), scenario, seed=7))
                for method in order}

    assert execute(methods) == execute(reversed(methods))


@pytest.mark.parametrize("seed", [0, 3])
def test_reused_scenario_matches_fresh_scenario_after_both_real_drift_points(seed):
    scenario = create_drift_scenario(n_rounds=1002)
    pristine = deepcopy(scenario)
    method = AHMNFullRunner(scenario.policy_ids)
    first = run_single(method, scenario, seed)
    # Both 500 and 1000 are inside the run, unlike the earlier 300-round test.
    assert first.n_rounds == 1002
    assert first.oracle_rewards[500] in (0.82, 0.85)
    assert first.oracle_rewards[1000] in (0.82, 0.9)
    repeated = run_single(method, scenario, seed)
    fresh = run_single(AHMNFullRunner(pristine.policy_ids), pristine, seed)
    assert fingerprint(repeated) == fingerprint(first) == fingerprint(fresh)
    assert [v.policies for v in scenario.vendors] == [v.policies for v in pristine.vendors]
