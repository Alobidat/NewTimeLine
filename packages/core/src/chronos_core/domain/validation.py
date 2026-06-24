"""Community source-validation math (Phase 4 trust layer).

Pure functions that turn reputation-weighted source votes (corroborate / dispute / irrelevant)
into a source ``quality_score`` and an event ``confidence`` — and the small reputation a user
earns for participating. No I/O; the DB gathering lives in ``chronos_core.validation_repo``.

Design:
- A voter's influence grows sub-linearly with reputation, so a few high-rep validators matter
  more than one drive-by vote but can't dominate (``vote_weight``).
- ``source_quality`` centres on 50 (unknown), rises with corroboration, falls with dispute /
  irrelevant, and is damped for small samples so one vote can't swing it fully.
- ``blended_confidence`` keeps the existing corroboration-by-source-count baseline but blends in
  the quality of the event's sources and the net verdict on them.
"""

from __future__ import annotations

import math

from chronos_core.domain.severity import normalize_corroboration

# Reputation a user earns per constructive source vote (capped elsewhere).
VOTE_REPUTATION = 1


def vote_weight(reputation: int) -> float:
    """A voter's influence from their reputation: 1.0 at rep 0, rising sub-linearly."""
    return 1.0 + math.log1p(max(0, reputation))


def source_quality(corroborate_w: float, dispute_w: float, irrelevant_w: float) -> int:
    """Reputation-weighted source quality in [0, 100]; 50 (neutral) when there are no votes.

    ``irrelevant`` counts as a half-weight negative (it questions relevance, not truth). Small
    samples are damped toward 50 so a single vote nudges rather than swings."""
    total = corroborate_w + dispute_w + irrelevant_w
    if total <= 0:
        return 50
    net = (corroborate_w - dispute_w - 0.5 * irrelevant_w) / total  # ~[-1.5, 1]
    damp = total / (total + 2.0)  # confidence in the sample
    score = 50.0 + 50.0 * net * damp
    return max(0, min(100, round(score)))


def blended_confidence(
    source_count: int,
    avg_source_quality: float,
    event_corroborate_w: float,
    event_dispute_w: float,
) -> int:
    """Event confidence in [0, 100]: the corroboration-by-source-count baseline blended with the
    quality of the event's sources, then nudged by the net verdict cast on *this* event."""
    base = normalize_corroboration(source_count) * 100.0
    blended = 0.6 * base + 0.4 * avg_source_quality
    decided = event_corroborate_w + event_dispute_w
    if decided > 0:
        sentiment = (event_corroborate_w - event_dispute_w) / decided  # [-1, 1]
        blended += 15.0 * sentiment
    return max(0, min(100, round(blended)))
