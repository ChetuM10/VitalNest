"""Tests for the evaluation metric helpers (pure functions, no network)."""
import pytest

from metrics import fact_coverage, first_rank, hit_rate, mean_reciprocal_rank, threshold_report


def test_first_rank_is_one_based_and_none_when_absent():
    assert first_rank(["A", "B", "C"], {"B"}) == 2
    assert first_rank(["A", "B", "C"], {"C", "B"}) == 2
    assert first_rank(["A"], {"Z"}) is None
    assert first_rank([], {"A"}) is None


def test_hit_rate_counts_questions_found_within_k():
    ranks = [1, 3, None, 7]
    assert hit_rate(ranks, 1) == 0.25
    assert hit_rate(ranks, 3) == 0.5
    assert hit_rate(ranks, 6) == 0.5
    assert hit_rate(ranks, 10) == 0.75
    assert hit_rate([], 3) == 0.0


def test_mean_reciprocal_rank_treats_misses_as_zero():
    assert mean_reciprocal_rank([1, 2, None]) == pytest.approx((1 + 0.5 + 0) / 3)
    assert mean_reciprocal_rank([]) == 0.0


def test_fact_coverage_matches_alternatives_ignoring_case():
    text = "Wheezing and a COUGH are common. Eat Spinach."
    assert fact_coverage([text], ["cough", "beans|spinach", "fever"]) == pytest.approx(2 / 3)
    assert fact_coverage([text], []) == 1.0
    assert fact_coverage([], ["cough"]) == 0.0


def test_threshold_report_finds_the_gap_between_answerable_and_unanswerable_scores():
    report = threshold_report(answerable=[0.90, 0.88, 0.87], unanswerable=[0.80, 0.75, 0.82])
    assert report["lowest_answerable"] == 0.87
    assert report["highest_unanswerable"] == 0.82
    assert report["separable"] is True
    assert 0.82 < report["suggested"] < 0.87


def test_threshold_report_flags_overlap():
    report = threshold_report(answerable=[0.90, 0.83], unanswerable=[0.85, 0.70])
    assert report["separable"] is False
    assert report["false_refusals_at_suggested"] >= 0
