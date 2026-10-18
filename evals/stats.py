"""Small exact statistics, so the evaluation needs no new dependency."""

from __future__ import annotations

import math


def binom_cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson_upper(k: int, n: int, alpha: float = 0.05) -> float:
    """One-sided upper bound: the p at which seeing k or fewer in n has probability alpha."""
    if n == 0:
        return 1.0
    if k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if binom_cdf(k, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile, q in 0..100."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]
