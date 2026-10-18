"""The evaluation: exact bounds, and the month decided to gold from the labels."""

import json

import pytest

from evals.run_eval import main, pick
from evals.stats import clopper_pearson_upper, percentile


@pytest.mark.parametrize(
    ("k", "n", "upper"),
    [(0, 7, 0.3482), (0, 62, 0.0472), (1, 10, 0.3942), (3, 3, 1.0), (0, 0, 1.0)],
)
def test_clopper_pearson_one_sided_upper(k, n, upper):
    assert clopper_pearson_upper(k, n) == pytest.approx(upper, abs=1e-4)


def test_percentile_nearest_rank():
    assert percentile([5, 1, 3, 2, 4], 50) == 3 and percentile([1, 2, 3], 95) == 3
    assert percentile([], 50) is None


def test_pick_prefers_coverage_at_zero_improper():
    curve = [
        {"threshold": 0.3, "coverage": 0.6, "error": 0, "improper": 0},
        {"threshold": 0.5, "coverage": 0.8, "error": 0, "improper": 0},
        {"threshold": 0.6, "coverage": 0.8, "error": 0, "improper": 0},
        {"threshold": 0.9, "coverage": 0.9, "error": 0.1, "improper": 1},
    ]
    assert pick(curve) == 0.5 and pick(curve[3:]) is None


def test_the_month_decides_to_gold_from_gold_facts(tmp_path):
    assert main(["--gold", "--split", "showcase", "--out", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["improper_approvals"]["k"] == 0 and report["invoices"] == 30
    assert report["autonomy"]["ceiling_count"] == 23
    assert report["unexplained_disagreements"] == 0
    assert (tmp_path / "EVAL_REPORT.md").read_text().startswith("# Evaluation report")
