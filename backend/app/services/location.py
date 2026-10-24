"""Reverse-geocode the browser's coordinates to a city (OpenStreetMap Nominatim, no key)."""

from __future__ import annotations

from typing import Any, Optional

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_cache: dict[tuple[float, float], dict[str, Any]] = {}


def reverse_geocode(lat: float, lon: float) -> Optional[dict[str, Any]]:
    key = (round(lat, 2), round(lon, 2))
    if key in _cache:
        return _cache[key]
    try:
        res = httpx.get(
            NOMINATIM,
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 10, "addressdetails": 1},
            headers={"User-Agent": "Fashionistas-hackathon/0.1 (local demo)"},
            timeout=6.0,
        )
        res.raise_for_status()
        a = res.json().get("address", {})
    except Exception:
        return None
    city = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("county")
    if not city:
        return None
    region = a.get("state") or a.get("region")
    out = {
        "city": city,
        "region": region,
        "country": a.get("country_code", "").upper() or None,
        "label": f"{city}, {region}" if region else city,
        "lat": lat,
        "lon": lon,
    }
    _cache[key] = out
    return out
