"""Synthetic uncertainty checks; no reserved document or label access."""

import json

import numpy as np
import pytest

from product_eval.paired_uncertainty import PairedCount, stratified_paired_recall


def test_identical_arms_have_exactly_zero_paired_difference():
    rows = [PairedCount("a", 1, 1, 1), PairedCount("b", 100, 20, 20)]
    report = stratified_paired_recall(rows, {"a": "forms", "b": "forms"}, macro_families=["forms"])
    assert report["families"]["forms"]["candidate_minus_text"] == {
        "estimate": 0.0, "percentile_95_interval": [0.0, 0.0], "estimable_replicates": 10_000}
    assert report["micro"]["reference"] == 101
    assert report["micro"]["text"]["estimate"] == 21 / 101


def test_paired_source_draws_agree_with_independent_small_calculation():
    rows = [PairedCount("a", 1, 0, 1), PairedCount("b", 9, 9, 0)]
    result = stratified_paired_recall(rows, {"a": "x", "b": "x"}, macro_families=["x"], replicates=99, seed=13)
    draws = np.random.default_rng(13).integers(0, 2, size=(99, 2))
    counts = np.array([[1, 0, 1], [9, 9, 0]])[draws].sum(axis=1)
    differences = (counts[:, 2] - counts[:, 1]) / counts[:, 0]
    assert result["micro"]["candidate_minus_text"]["percentile_95_interval"] == np.quantile(differences, [0.025, 0.975]).tolist()
    assert result["micro"]["candidate_minus_text"]["estimate"] == pytest.approx(-0.8)


def test_failed_source_stays_in_denominator_and_macro_weights_are_equal():
    rows = [PairedCount("failed", 100, 0, 0), PairedCount("good", 1, 0, 1)]
    result = stratified_paired_recall(rows, {"failed": "a", "good": "b"}, macro_families=["a", "b"], replicates=20)
    assert result["micro"]["candidate"]["estimate"] == 1 / 101
    assert result["macro"]["candidate"]["estimate"] == 0.5
    assert result["macro"]["candidate"]["percentile_95_interval"] == [0.5, 0.5]


def test_zero_target_families_are_undefined_and_can_be_excluded_explicitly():
    rows = [PairedCount("form", 0, 0, 0), PairedCount("receipt", 2, 1, 2)]
    source_map = {"form": "no_row_task", "receipt": "rows"}
    result = stratified_paired_recall(rows, source_map, macro_families=["rows"], replicates=20)
    assert result["families"]["no_row_task"]["text"] == {
        "estimate": None, "percentile_95_interval": None, "estimable_replicates": 0}
    assert result["macro"]["candidate_minus_text"]["estimate"] == 0.5
    json.dumps(result, allow_nan=False)
    all_families = stratified_paired_recall(rows, source_map, macro_families=["no_row_task", "rows"], replicates=20)
    assert all_families["macro"]["text"]["estimate"] is None


def test_zero_denominator_replicates_are_reported_not_changed_to_perfect():
    rows = [PairedCount("empty", 0, 0, 0), PairedCount("positive", 1, 0, 1)]
    report = stratified_paired_recall(rows, {"empty": "a", "positive": "a"}, macro_families=["a"], replicates=100)
    assert 0 < report["micro"]["candidate"]["estimable_replicates"] < 100
    assert report["micro"]["candidate"]["percentile_95_interval"] == [1.0, 1.0]
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("rows", [[], [PairedCount("a", 1, 0, 0)] * 2,
    [PairedCount("a", 1, 2, 0)], [PairedCount("a", True, 0, 0)], [PairedCount("unknown", 1, 0, 0)]])
def test_missing_duplicate_unknown_or_invalid_counts_fail(rows):
    with pytest.raises(ValueError):
        stratified_paired_recall(rows, {"a": "f"}, macro_families=["f"])


def test_input_order_does_not_change_paired_sampling():
    rows = [PairedCount("a", 3, 1, 2), PairedCount("b", 2, 1, 0)]
    args = {"source_families": {"b": "f", "a": "f"}, "macro_families": ["f"], "replicates": 31}
    assert stratified_paired_recall(rows, **args) == stratified_paired_recall(rows[::-1], **args)
