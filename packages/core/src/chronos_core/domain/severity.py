"""Severity scoring — composite 0..100 (impact + social + corroboration).

Pure functions (stdlib only) so they are cheap to test and the weights are config-driven.
See docs/ai-agents.md §2.7. In Phase 1 only corroboration (source count) is non-zero;
impact/social arrive with the enricher (Phase 3) and live engagement (Phase 4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SeverityWeights:
    """Blend weights; defaults match docs/ai-agents.md. Loaded from the Config Service."""

    impact: float = 0.5
    social: float = 0.2
    corroboration: float = 0.3

    @classmethod
    def from_config(cls, value: dict | None) -> SeverityWeights:
        """Build from a config dict, falling back to defaults for missing keys."""
        value = value or {}
        return cls(
            impact=float(value.get("impact", cls.impact)),
            social=float(value.get("social", cls.social)),
            corroboration=float(value.get("corroboration", cls.corroboration)),
        )


def _log_saturate(value: float, half: float) -> float:
    """Map ``[0, ∞)`` to ``[0, 1)`` with diminishing returns; ``half`` ≈ the 0.5 point."""
    if value <= 0:
        return 0.0
    return 1.0 - math.exp(-math.log(2.0) * (value / half))


def normalize_corroboration(source_count: int, half: float = 4.0) -> float:
    """Distinct-source count → [0,1]. Saturates so a few good sources already score high."""
    return _log_saturate(source_count, half)


def normalize_social(engagement: float, half: float = 50.0) -> float:
    """Time-decayed engagement velocity → [0,1] (caller applies the decay)."""
    return _log_saturate(engagement, half)


def normalize_impact(impact_raw: float, half: float = 1000.0) -> float:
    """Extracted impact magnitude (casualties/area/$ proxy) → [0,1], log-saturated."""
    return _log_saturate(impact_raw, half)


@dataclass(frozen=True)
class SeverityResult:
    """The score plus its components, stored for transparency (severity_breakdown)."""

    score: int  # 0..100
    impact: float
    social: float
    corroboration: float


def compute_severity(
    *,
    source_count: int = 0,
    engagement: float = 0.0,
    impact_raw: float = 0.0,
    weights: SeverityWeights | None = None,
) -> SeverityResult:
    """Combine normalized components into a 0..100 score with its breakdown."""
    w = weights or SeverityWeights()
    impact = normalize_impact(impact_raw)
    social = normalize_social(engagement)
    corroboration = normalize_corroboration(source_count)
    blended = w.impact * impact + w.social * social + w.corroboration * corroboration
    score = max(0, min(100, round(blended * 100)))
    return SeverityResult(
        score=score, impact=impact, social=social, corroboration=corroboration
    )
