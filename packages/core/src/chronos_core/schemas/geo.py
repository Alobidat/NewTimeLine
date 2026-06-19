"""Shared geo DTO. Kept in its own module so both event and entity schemas can use it
without an import cycle."""

from __future__ import annotations

from pydantic import BaseModel


class GeoPoint(BaseModel):
    """WGS84 point."""

    lon: float
    lat: float
