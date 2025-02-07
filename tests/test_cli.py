import math

import pytest
from pytest import approx

from respdiff.cli import get_stats_data


@pytest.mark.parametrize(
    "n, total, ref_n, expected",
    [
        (9, None, None, (9, None, None, None)),
        (9, 10, None, (9, 90, None, None)),
        (11, None, 10, (11, None, 1, 10)),
        (9, None, 10, (9, None, -1, -10)),
        (10, None, 10, (10, None, 0, 0)),
        (10, None, 0, (10, None, +10, float("inf"))),
        (0, None, 0, (0, None, 0, float("nan"))),
        (9, 10, 10, (9, 90, -1, -10)),
        (9, 10, 90, (9, 90, -81, -81 * 100.0 / 90)),
        (90, 100, 9, (90, 90, 81, 81 * 100.0 / 9)),
    ],
)
def test_get_stats_data(n, total, ref_n, expected):
    got_n, got_pct, got_diff, got_diff_pct = get_stats_data(n, total, ref_n)
    assert got_n == expected[0]
    assert got_diff == expected[2]

    def compare_float(got, exp):
        if got is None:
            return exp is None
        if math.isnan(got):
            return math.isnan(exp)
        return got == approx(exp)

    assert compare_float(got_pct, expected[1])
    assert compare_float(got_diff_pct, expected[3])
