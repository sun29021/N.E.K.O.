"""Weather from Open-Meteo (free, no account, no API key): https://open-meteo.com

* Location: ``app.location`` from settings (e.g. "Dhaka"), otherwise the city is estimated from your
  public IP address via ipwho.is (sends only your IP; cached for the session).
* Returns a compact, comparable summary for today and tomorrow so the answer can be short and smart:
  condition, min/max temperature, feels-like, rain chance, and how tomorrow compares to today.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from ..core.errors import ToolError
from ..core.types import RiskLevel
from .base import ToolContext, ToolRegistry, ToolResult, ToolSpec
from .web import http_get

WMO = {0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
       51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
       66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
       80: "rain showers", 81: "rain showers", 82: "violent rain showers", 95: "thunderstorms",
       96: "thunderstorms with hail", 99: "thunderstorms with hail"}
_cache: dict[str, Any] = {}


def _json(url: str) -> Any:
    _final, text = http_get(url, timeout=12)
    return json.loads(text)


def locate(place: str) -> tuple[str, float, float, str]:
    if place:
        if place in _cache:
            return _cache[place]
        data = _json("https://geocoding-api.open-meteo.com/v1/search?" +
                     urllib.parse.urlencode({"name": place, "count": 1, "language": "en", "format": "json"}))
        r = (data.get("results") or [None])[0]
        if not r:
            raise ToolError(f"I couldn't find a place called {place}")
        out = (f"{r['name']}, {r.get('country', '')}".strip(", "), r["latitude"], r["longitude"], r.get("timezone", "auto"))
        _cache[place] = out
        return out
    if "ip" not in _cache:
        d = _json("https://ipwho.is/")
        if not d.get("success", True) or "latitude" not in d:
            raise ToolError("I couldn't work out where you are - set app.location in settings (e.g. \"Dhaka\")")
        _cache["ip"] = (f"{d.get('city', '')}, {d.get('country', '')}".strip(", "), d["latitude"], d["longitude"],
                        (d.get("timezone") or {}).get("id", "auto"))
    return _cache["ip"]


def summarize(name: str, data: dict[str, Any]) -> dict[str, Any]:
    d = data["daily"]
    days = []
    for i, label in enumerate(("today", "tomorrow", "day after tomorrow")[: len(d["time"])]):
        days.append({
            "day": label, "date": d["time"][i], "condition": WMO.get(d["weather_code"][i], "mixed"),
            "min_c": round(d["temperature_2m_min"][i]), "max_c": round(d["temperature_2m_max"][i]),
            "feels_max_c": round(d["apparent_temperature_max"][i]),
            "rain_chance_pct": d["precipitation_probability_max"][i], "rain_mm": d["precipitation_sum"][i],
            "wind_kmh": round(d["wind_speed_10m_max"][i]), "uv_max": d.get("uv_index_max", [None] * 3)[i],
        })
    cur = data.get("current", {})
    out: dict[str, Any] = {"place": name, "now": {"temp_c": cur.get("temperature_2m"),
                                                  "feels_c": cur.get("apparent_temperature"),
                                                  "condition": WMO.get(cur.get("weather_code"), ""),
                                                  "humidity_pct": cur.get("relative_humidity_2m")}, "days": days}
    if len(days) >= 2:
        diff = days[1]["max_c"] - days[0]["max_c"]
        out["tomorrow_vs_today"] = ("about the same temperature" if abs(diff) <= 1 else
                                    f"{abs(diff)} °C {'warmer' if diff > 0 else 'cooler'} than today")
    return out


def _weather(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    settings = getattr(ctx, "settings", None)
    place = args.get("place") or getattr(getattr(settings, "app", None), "location", "") or ""
    name, lat, lon, tz = locate(place)
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": tz or "auto", "forecast_days": 3,
        "current": "temperature_2m,apparent_temperature,weather_code,relative_humidity_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,"
                 "precipitation_probability_max,precipitation_sum,wind_speed_10m_max,uv_index_max"})
    s = summarize(name, _json("https://api.open-meteo.com/v1/forecast?" + q))
    return ToolResult(True, f"Weather for {name}", json.dumps(s, ensure_ascii=False))


def register_weather_tool(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="get_weather", description="Weather now, today, tomorrow and the day after (Open-Meteo).",
        params={"place": {"type": "string", "default": "", "max_length": 100,
                          "description": "city; empty = the user's location"}},
        handler=_weather, risk=RiskLevel.READ_ONLY, category="network", needs_network=True, timeout_s=25,
    ))
