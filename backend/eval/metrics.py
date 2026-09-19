"""Scoring metrics for the audience-simulator evaluation.

Pure standard library on purpose: the rest of the backend carries no numpy or
scipy, and an evaluation nobody can run because it needs a 90MB wheel is not an
evaluation. Every function here is a few lines and checkable by eye.

Two families:

  *level*  — MAE, RMSE, bias. Does the predictor land on the right number?
  *order*  — Spearman, Pearson. Does it rank films the way audiences did?

Both are reported because they fail independently. A predictor that always
answers 68 has a respectable MAE on a dataset whose mean is 68 and zero
ranking ability; a predictor that ranks perfectly but sits 15 points low has
useless levels and is one intercept away from being good. Reporting only the
flattering one is how model evaluations mislead, so the report prints both plus
the constant-predictor floor that makes MAE interpretable.
"""
import math
import random
import statistics
from typing import Sequence

Pairs = Sequence[tuple[float, float]]  # (predicted, actual)


# ------------------------------------------------------------------ level --


def mae(pairs: Pairs) -> float:
    """Mean absolute error, in points of the 0-100 rating."""
    return statistics.fmean(abs(p - a) for p, a in pairs)


def rmse(pairs: Pairs) -> float:
    """Root mean squared error. Punishes a few large misses harder than MAE,
    so a predictor that is usually close but occasionally wild shows up here."""
    return math.sqrt(statistics.fmean((p - a) ** 2 for p, a in pairs))


def bias(pairs: Pairs) -> float:
    """Mean signed error. Positive means the predictor is generous.

    Separated from MAE because they call for different fixes: bias is a
    calibration problem an offset corrects, scatter is not.
    """
    return statistics.fmean(p - a for p, a in pairs)


# ------------------------------------------------------------------ order --


def _ranks(values: Sequence[float]) -> list[float]:
    """Ranks, ties sharing their average rank (the standard Spearman fix).

    Without tie-averaging, equal predictions get arbitrary distinct ranks and
    the correlation depends on input order — which matters here because a
    cohort-driven predictor genuinely returns the same score for different
    films more often than a continuous one does.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        stop = position
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[position]]:
            stop += 1
        shared = (position + stop) / 2 + 1
        for index in order[position:stop + 1]:
            ranks[index] = shared
        position = stop + 1
    return ranks


def pearson(pairs: Pairs) -> float:
    """Linear correlation. 0.0 when either side has no variance at all."""
    xs = [p for p, _ in pairs]
    ys = [a for _, a in pairs]
    if len(xs) < 2:
        return 0.0
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denominator = math.sqrt(sum(d * d for d in dx) * sum(d * d for d in dy))
    return (sum(a * b for a, b in zip(dx, dy)) / denominator) if denominator else 0.0


def spearman(pairs: Pairs) -> float:
    """Rank correlation: Pearson over the tie-averaged ranks.

    The headline ordering metric. A producer asking "is this film going to play
    better than that one" needs the order right; whether the simulator says 71
    or 74 matters less than whether it puts the two films in the right order.
    """
    xr = _ranks([p for p, _ in pairs])
    yr = _ranks([a for _, a in pairs])
    return pearson(list(zip(xr, yr)))


def permutation_p(pairs: Pairs, rounds: int = 10_000, seed: int = 7) -> float:
    """Two-sided p-value for Spearman by shuffling the actuals.

    With 30-odd films, a rank correlation of 0.3 is well inside what chance
    produces, so quoting rho without this is quoting noise. Seeded, so the
    committed report reproduces exactly. No scipy needed: the null distribution
    is generated rather than looked up.
    """
    observed = abs(spearman(pairs))
    predicted = [p for p, _ in pairs]
    actual = [a for _, a in pairs]
    rng = random.Random(seed)
    hits = 0
    for _ in range(rounds):
        rng.shuffle(actual)
        if abs(spearman(list(zip(predicted, actual)))) >= observed:
            hits += 1
    # +1 on both sides: the observed arrangement is itself one draw from the
    # null, and it keeps a p-value of exactly 0 (which is never true) off the
    # report.
    return (hits + 1) / (rounds + 1)


# --------------------------------------------------------------- contrast --


def paired_bootstrap_mae(
    challenger: Pairs, baseline: Pairs, rounds: int = 10_000, seed: int = 7
) -> dict:
    """Is the challenger's MAE really lower than the baseline's?

    Paired and resampled by film, because the two predictors saw the same
    films: an easy film is easy for both, and pairing removes that shared
    difficulty from the comparison. Returns the observed gap, a 95% interval
    and the share of resamples where the challenger failed to win.

    A gap whose interval straddles zero means the evaluation cannot tell the
    two apart, which on a 30-film sample is a likely and publishable outcome.
    """
    assert len(challenger) == len(baseline), "paired comparison needs the same films"
    errors = [(abs(c - ca), abs(b - ba)) for (c, ca), (b, ba) in zip(challenger, baseline)]
    observed = statistics.fmean(c for c, _ in errors) - statistics.fmean(b for _, b in errors)

    rng = random.Random(seed)
    gaps = []
    size = len(errors)
    for _ in range(rounds):
        draw = [errors[rng.randrange(size)] for _ in range(size)]
        gaps.append(statistics.fmean(c for c, _ in draw) - statistics.fmean(b for _, b in draw))
    gaps.sort()
    return {
        "mae_gap": round(observed, 3),
        "ci95_low": round(gaps[int(0.025 * rounds)], 3),
        "ci95_high": round(gaps[int(0.975 * rounds)], 3),
        "p_not_better": round(sum(1 for g in gaps if g >= 0) / rounds, 4),
        "verdict": _contrast_verdict(observed, gaps[int(0.025 * rounds)], gaps[int(0.975 * rounds)]),
    }


def _contrast_verdict(observed: float, low: float, high: float) -> str:
    if low <= 0 <= high:
        return "no measurable difference on this sample"
    return "lower error than the baseline" if observed < 0 else "higher error than the baseline"


def score(pairs: Pairs, *, rounds: int = 10_000, seed: int = 7) -> dict:
    """Every metric for one predictor, rounded for the committed report."""
    return {
        "n": len(pairs),
        "mae": round(mae(pairs), 2),
        "rmse": round(rmse(pairs), 2),
        "bias": round(bias(pairs), 2),
        "spearman": round(spearman(pairs), 3),
        "spearman_p": round(permutation_p(pairs, rounds=rounds, seed=seed), 4),
        "pearson": round(pearson(pairs), 3),
        "predicted_mean": round(statistics.fmean(p for p, _ in pairs), 2),
        "predicted_spread": round(statistics.pstdev([p for p, _ in pairs]), 2) if len(pairs) > 1 else 0.0,
        "actual_mean": round(statistics.fmean(a for _, a in pairs), 2),
        "actual_spread": round(statistics.pstdev([a for _, a in pairs]), 2) if len(pairs) > 1 else 0.0,
    }
