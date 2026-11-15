"""Scientific safeguards: a constant proxy is not validation, and rank reversals count."""

import importlib.util
import math
from pathlib import Path

p = Path(__file__).resolve().parents[2] / "tools/proxy_study/analyze.py"
spec = importlib.util.spec_from_file_location("proxy_analysis", p)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def test_constant_proxy_cannot_establish_ranking():
    r = analysis.compare({"a": 0.2, "b": 0.4, "c": 0.8}, {"a": 0, "b": 0, "c": 0})
    assert r["spearman_rho"] is None


def test_perfect_six_arm_order_has_exact_permutation_p():
    x = {str(i): i / 5 for i in range(6)}
    r = analysis.compare(x, x)
    assert abs(r["spearman_rho"] - 1) < 1e-12
    assert r["exact_permutation_p_two_sided"] == 2 / math.factorial(6)
    assert r["pairwise_directional_agreement"] == 1
    assert r["full_winner_in_lite_top2"]


def test_inversion_is_not_success_despite_two_sided_significance():
    x = {str(i): i / 5 for i in range(6)}
    y = {str(i): 1 - i / 5 for i in range(6)}
    r = analysis.compare(x, y)
    assert r["spearman_rho"] < -0.99
    assert r["pairwise_directional_agreement"] == 0
    assert not r["full_winner_in_lite_top2"]


def test_top2_tie_is_not_guaranteed_retention():
    x = {"a": 0.1, "b": 0.3, "c": 0.5, "d": 0.8}
    y = {"a": 0.0, "b": 1.0, "c": 1.0, "d": 1.0}
    r = analysis.compare(x, y)
    assert not r["full_winner_in_lite_top2"]
    assert len(r["lite_top2_including_ties"]) == 3
