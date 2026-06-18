"""The structured result the enricher asks the LLM to produce (schema-validated).

Kept small and flat so even modest local models can satisfy it. ``references`` are the
deep-time subjects the event discusses → become event_references / the sub-timeline.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from chronos_core.models.enums import TimePrecision


class ExtractedReference(BaseModel):
    """A historical subject the event refers to (signed year)."""

    label: str
    year: float = Field(description="signed year; negative = BC, e.g. -4000000 for ~4 Mya")
    precision: TimePrecision = TimePrecision.ERA
    detail: str | None = None


class EnrichmentResult(BaseModel):
    """LLM enrichment output for one event."""

    summary: str = Field(description="neutral, source-grounded, 1-3 sentences")
    category: str | None = Field(default=None, description="e.g. conflict, disaster, science")
    tags: list[str] = Field(default_factory=list)
    impact: float = Field(
        default=0.0, description="rough magnitude proxy (casualties/area/economic), 0 if unknown"
    )
    references: list[ExtractedReference] = Field(default_factory=list)
