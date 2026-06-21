"""Unit tests for the Geocoder domain helpers (Nominatim lookup + geom assembly).

These tests mock httpx at the transport layer via respx so no real network calls are made
and no database is needed.
"""

from __future__ import annotations

import pytest
import httpx
import respx

from chronos_agents.geocode import _lookup, _NOMINATIM_URL


@respx.mock
async def test_lookup_returns_lat_lon_on_success():
    """_lookup should parse the first result's lat/lon."""
    respx.get(_NOMINATIM_URL).mock(
        return_value=httpx.Response(
            200,
            json=[{"lat": "35.6762", "lon": "139.6503", "display_name": "Tokyo, Japan"}],
        )
    )
    async with httpx.AsyncClient() as client:
        result = await _lookup(client, "Tokyo")
    assert result == pytest.approx((35.6762, 139.6503), rel=1e-4)


@respx.mock
async def test_lookup_returns_none_on_empty():
    """_lookup should return None when Nominatim returns an empty array."""
    respx.get(_NOMINATIM_URL).mock(
        return_value=httpx.Response(200, json=[])
    )
    async with httpx.AsyncClient() as client:
        result = await _lookup(client, "NoSuchPlaceXYZABC")
    assert result is None


@respx.mock
async def test_lookup_returns_none_on_http_error():
    """_lookup should swallow HTTP errors and return None."""
    respx.get(_NOMINATIM_URL).mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )
    async with httpx.AsyncClient() as client:
        result = await _lookup(client, "Anywhere")
    assert result is None


@respx.mock
async def test_lookup_sends_correct_query_params():
    """_lookup must pass q, format=json, limit=1 to Nominatim."""
    route = respx.get(_NOMINATIM_URL).mock(
        return_value=httpx.Response(
            200,
            json=[{"lat": "51.5074", "lon": "-0.1278", "display_name": "London, UK"}],
        )
    )
    async with httpx.AsyncClient() as client:
        await _lookup(client, "London")

    req = route.calls[0].request
    assert "q=London" in str(req.url)
    assert "format=json" in str(req.url)
    assert "limit=1" in str(req.url)
