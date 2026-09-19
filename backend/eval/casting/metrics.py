"""Recall@k, MRR, and the confidence interval that says whether to believe them.

Stdlib only, like `eval/metrics.py` next door, and for the same reason: an
evaluation that needs a scientific stack to compute an average invites nobody to
check it.
"""
import math
import random
from typing import Optional


def rank_of(answer: int, ranked: list[int]) -> Optional[int]:
    """Where the right actor came, 1-based, or None if not retrieved at all."""
    for position, actor_id in enumerate(ranked, 1):
        if actor_id == answer:
            return position
    return None


def recall_at(ranks: list[Optional[int]], k: int) -> float:
    """The share of briefs whose right actor was in the top k."""
    if not ranks:
        return 0.0
    return sum(1 for rank in ranks if rank is not None and rank <= k) / len(ranks)


def mrr(ranks: list[Optional[int]]) -> float:
    """Mean reciprocal rank: 1.0 if always first, 0.5 if always second, 0 if never
    found. It rewards being near the top, which is what a casting list is."""
    if not ranks:
        return 0.0
    return sum(1 / rank if rank else 0.0 for rank in ranks) / len(ranks)


def chance_recall_at(k: int, corpus_size: int) -> float:
    """What a shuffle scores: k out of the whole pool. The line every other
    number has to clear before it means anything."""
    if corpus_size <= 0:
        return 0.0
    return min(1.0, k / corpus_size)


def wilson_interval(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """A 95% interval for a proportion, which on 50 briefs is wide.

    Wilson rather than the textbook normal interval because recall here sits near
    0 or 1 often enough that the normal one would run past the ends of the scale
    and quietly report an impossible bound.
    """
    if total <= 0:
        return (0.0, 0.0)
    share = hits / total
    denominator = 1 + z * z / total
    centre = share + z * z / (2 * total)
    spread = z * math.sqrt(share * (1 - share) / total + z * z / (4 * total * total))
    return (
        max(0.0, (centre - spread) / denominator),
        min(1.0, (centre + spread) / denominator),
    )


def paired_bootstrap(
    left: list[Optional[int]],
    right: list[Optional[int]],
    k: int,
    rounds: int = 10_000,
    seed: int = 20260920,
) -> dict[str, float]:
    """Is `left`'s recall@k really above `right`'s, or is it this sample?

    Resamples the briefs, keeping each brief's pair of ranks together, and
    reports the gap's interval and how often the gap came out at or below zero.
    Paired because the same brief is easy or hard for both, and comparing
    unpaired would charge that shared difficulty to the difference.
    """
    if len(left) != len(right) or not left:
        return {"gap": 0.0, "low": 0.0, "high": 0.0, "p": 1.0}

    observed = recall_at(left, k) - recall_at(right, k)
    generator = random.Random(seed)
    size = len(left)
    gaps = []
    for _ in range(rounds):
        picks = [generator.randrange(size) for _ in range(size)]
        gaps.append(
            recall_at([left[i] for i in picks], k) - recall_at([right[i] for i in picks], k)
        )
    gaps.sort()
    return {
        "gap": round(observed, 4),
        "low": round(gaps[int(0.025 * rounds)], 4),
        "high": round(gaps[int(0.975 * rounds)], 4),
        # A one-sided read: how often the resampled gap failed to favour `left`.
        "p": round(sum(1 for gap in gaps if gap <= 0) / rounds, 4),
    }
