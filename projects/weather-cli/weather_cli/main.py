"""Main CLI module for weather-cli"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional


CACHE_DIR = Path.home() / ".cache" / "weather-cli"
CACHE_FILE = CACHE_DIR / "cache.json"
CACHE_TTL = 300  # 5 minutes in seconds
WTTR_URL = "https://wttr.in/{city}?format=j1"


def get_cache() -> Dict[str, Any]:
    """Load cache from JSON file."""
    if not CACHE_FILE.exists():
        return {}

    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: Dict[str, Any]) -> None:
    """Save cache to JSON file."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except OSError:
        pass  # Silently fail if we can't write cache


def is_cache_valid(cache_entry: Dict[str, Any]) -> bool:
    """Check if cache entry is still valid (within TTL)."""
    if "timestamp" not in cache_entry:
        return False
    try:
        return (time.time() - cache_entry["timestamp"]) < CACHE_TTL
    except (TypeError, ValueError):
        return False


def fetch_weather(city: str) -> Dict[str, Any]:
    """Fetch weather data from wttr.in using curl."""
    encoded_city = urllib.parse.quote(city)
    url = WTTR_URL.format(city=encoded_city)
    try:
        result = subprocess.run(
            ["curl", "-s", "-f", "--max-time", "10", url],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to fetch weather data: {e.stderr.strip() or e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse weather data: {e}") from e


def get_weather(city: str, use_cache: bool = True) -> Dict[str, Any]:
    """Get weather data for a city, using cache if available and valid."""
    cache = get_cache()
    city_lower = city.lower()

    if use_cache and city_lower in cache and is_cache_valid(cache[city_lower]):
        return cache[city_lower]["data"]

    data = fetch_weather(city)

    if use_cache:
        cache[city_lower] = {
            "data": data,
            "timestamp": time.time(),
        }
        save_cache(cache)

    return data


def format_weather(data: Dict[str, Any], city: str) -> str:
    """Format weather data for human-readable output."""
    current = data.get("current_condition", [{}])[0]
    nearest = data.get("nearest_area", [{}])[0]

    area_name = nearest.get("areaName", [{}])[0].get("value", city)
    country = nearest.get("country", [{}])[0].get("value", "")
    location = f"{area_name}, {country}" if country else area_name

    temp_c = current.get("temp_C", "N/A")
    temp_f = current.get("temp_F", "N/A")
    feels_like_c = current.get("FeelsLikeC", "N/A")
    feels_like_f = current.get("FeelsLikeF", "N/A")
    humidity = current.get("humidity", "N/A")
    wind_kph = current.get("windspeedKmph", "N/A")
    wind_mph = current.get("windspeedMiles", "N/A")
    wind_dir = current.get("winddir16Point", "N/A")
    condition = current.get("weatherDesc", [{}])[0].get("value", "N/A")
    pressure = current.get("pressure", "N/A")
    visibility = current.get("visibility", "N/A")
    uv_index = current.get("uvIndex", "N/A")
    cloud_cover = current.get("cloudcover", "N/A")

    output = [
        f"Weather for {location}",
        "─" * 40,
        f"Temperature:     {temp_c}°C / {temp_f}°F",
        f"Feels like:      {feels_like_c}°C / {feels_like_f}°F",
        f"Condition:       {condition}",
        f"Humidity:        {humidity}%",
        f"Wind:            {wind_kph} km/h / {wind_mph} mph ({wind_dir})",
        f"Pressure:        {pressure} mb",
        f"Visibility:      {visibility} km",
        f"UV Index:        {uv_index}",
        f"Cloud Cover:     {cloud_cover}%",
    ]

    return "\n".join(output)


def parse_args(args: Optional[list] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="weather",
        description="Fetch weather data from wttr.in",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  weather London
  weather "New York" --json
  weather Tokyo --no-cache
        """,
    )
    parser.add_argument(
        "city",
        nargs="?",
        help="City name to fetch weather for (optional with --clear-cache)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip cache and fetch fresh data",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the cache and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )
    return parser.parse_args(args)


def clear_cache() -> None:
    """Clear the cache file."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        print(f"Cache cleared: {CACHE_FILE}")
    else:
        print("Cache is already empty")


def main(args: Optional[list] = None) -> int:
    """Main entry point."""
    parsed = parse_args(args)

    if parsed.clear_cache:
        clear_cache()
        return 0

    city = parsed.city
    if city is None or not city.strip():
        print("Error: City name is required", file=sys.stderr)
        return 1

    city = city.strip()

    try:
        data = get_weather(city, use_cache=not parsed.no_cache)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if parsed.json:
        print(json.dumps(data, indent=2))
    else:
        print(format_weather(data, city))

    return 0


if __name__ == "__main__":
    sys.exit(main())