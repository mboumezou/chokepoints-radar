from __future__ import annotations

import requests

from core.config import Chokepoint


REQUEST_TIMEOUT_SECONDS = 12


def fetch_marine_weather(chokepoint: Chokepoint) -> dict:
    """Fetch wave and marine data. Raises on API error."""
    params = {
        "latitude": chokepoint.latitude,
        "longitude": chokepoint.longitude,
        "current": "wave_height,wave_direction,wave_period,wind_wave_height,swell_wave_height",
        "timezone": "UTC",
    }
    response = requests.get(
        "https://marine-api.open-meteo.com/v1/marine",
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    current = data.get("current", {}) or {}
    units = data.get("current_units", {}) or {}
    weather = {
        "time": current.get("time", ""),
        "wave_height": current.get("wave_height"),
        "wave_height_unit": units.get("wave_height", "m"),
        "wave_direction": current.get("wave_direction"),
        "wave_direction_unit": units.get("wave_direction", "deg"),
        "wave_period": current.get("wave_period"),
        "wave_period_unit": units.get("wave_period", "s"),
        "wind_wave_height": current.get("wind_wave_height"),
        "swell_wave_height": current.get("swell_wave_height"),
    }
    weather.update(fetch_wind_weather(chokepoint))
    return weather


def fetch_wind_weather(chokepoint: Chokepoint) -> dict:
    """Fetch wind speed, gusts and weather code. Returns {} on any error."""
    params = {
        "latitude": chokepoint.latitude,
        "longitude": chokepoint.longitude,
        "current": "wind_speed_10m,wind_gusts_10m,weather_code",
        "timezone": "UTC",
    }
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception:
        return {}
    data = response.json()
    current = data.get("current", {}) or {}
    units = data.get("current_units", {}) or {}
    return {
        "wind_time": current.get("time", ""),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_speed_unit": units.get("wind_speed_10m", "km/h"),
        "wind_gusts": current.get("wind_gusts_10m"),
        "wind_gusts_unit": units.get("wind_gusts_10m", "km/h"),
        "weather_code": current.get("weather_code"),
    }


def fetch_weather_safe(chokepoint: Chokepoint) -> dict:
    """Try marine + wind; fall back to wind-only; return {} if both fail.

    The marine API only covers ocean areas. Inland chokepoints (Panama Canal)
    or narrow straits may return errors — wind data is always available.
    """
    try:
        return fetch_marine_weather(chokepoint)
    except Exception:
        pass
    try:
        return fetch_wind_weather(chokepoint)
    except Exception:
        return {}
