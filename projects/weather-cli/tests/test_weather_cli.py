"""Tests for weather-cli"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the weather_cli package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from weather_cli.main import (
    parse_args,
    get_weather,
    fetch_weather,
    format_weather,
    get_cache,
    save_cache,
    is_cache_valid,
    main,
)


# Sample weather data from wttr.in
SAMPLE_WEATHER_DATA = {
    "current_condition": [
        {
            "temp_C": "22",
            "temp_F": "72",
            "FeelsLikeC": "21",
            "FeelsLikeF": "70",
            "humidity": "65",
            "windspeedKmph": "15",
            "windspeedMiles": "9",
            "winddir16Point": "SW",
            "weatherDesc": [{"value": "Partly Cloudy"}],
            "pressure": "1015",
            "visibility": "10",
            "uvIndex": "5",
            "cloudcover": "50",
        }
    ],
    "nearest_area": [
        {
            "areaName": [{"value": "London"}],
            "country": [{"value": "United Kingdom"}],
        }
    ],
    "request": [{"query": "London, United Kingdom", "type": "City"}],
}


def test_format_weather():
    """Test formatting weather data for human-readable output."""
    output = format_weather(SAMPLE_WEATHER_DATA, "London")

    assert "Weather for London, United Kingdom" in output
    assert "Temperature:     22°C / 72°F" in output
    assert "Feels like:      21°C / 70°F" in output
    assert "Condition:       Partly Cloudy" in output
    assert "Humidity:        65%" in output
    assert "Wind:            15 km/h / 9 mph (SW)" in output
    assert "Pressure:        1015 mb" in output
    assert "Visibility:      10 km" in output
    assert "UV Index:        5" in output
    assert "Cloud Cover:     50%" in output


def test_is_cache_valid():
    """Test cache validity checking."""
    # Test with mock time
    import time
    current_time = time.time()
    assert is_cache_valid({"timestamp": current_time - 100}) is True  # 100 seconds old
    assert is_cache_valid({"timestamp": current_time - 200}) is True  # 200 seconds old
    assert is_cache_valid({"timestamp": current_time - 400}) is False  # 400 seconds old (over 300)
    assert is_cache_valid({}) is False  # No timestamp
    assert is_cache_valid({"timestamp": "invalid"}) is False  # Invalid timestamp


def test_get_cache_and_save_cache(tmp_path):
    """Test cache loading and saving."""
    cache_file = tmp_path / "cache.json"

    # Test empty cache
    with patch("weather_cli.main.CACHE_FILE", cache_file):
        assert get_cache() == {}

    # Test saving and loading
    test_cache = {"london": {"data": SAMPLE_WEATHER_DATA, "timestamp": 1000.0}}
    with patch("weather_cli.main.CACHE_FILE", cache_file):
        save_cache(test_cache)
        loaded = get_cache()
        assert loaded == test_cache


def test_get_weather_uses_cache(monkeypatch):
    """Test that get_weather uses cache when valid."""
    mock_cache = {
        "london": {
            "data": SAMPLE_WEATHER_DATA,
            "timestamp": 1000.0,  # Recent enough
        }
    }

    def mock_get_cache():
        return mock_cache

    def mock_save_cache(cache):
        pass

    monkeypatch.setattr("weather_cli.main.get_cache", mock_get_cache)
    monkeypatch.setattr("weather_cli.main.save_cache", mock_save_cache)
    monkeypatch.setattr("weather_cli.main.is_cache_valid", lambda x: True)
    monkeypatch.setattr("weather_cli.main.CACHE_TTL", 300)

    # Should not call fetch_weather if cache is valid
    with patch("weather_cli.main.fetch_weather") as mock_fetch:
        result = get_weather("London", use_cache=True)
        mock_fetch.assert_not_called()
        assert result == SAMPLE_WEATHER_DATA


def test_get_weather_fetches_when_cache_invalid(monkeypatch):
    """Test that get_weather fetches fresh data when cache is invalid."""
    mock_cache = {
        "london": {
            "data": SAMPLE_WEATHER_DATA,
            "timestamp": 100.0,  # Too old
        }
    }

    def mock_get_cache():
        return mock_cache

    def mock_save_cache(cache):
        pass

    monkeypatch.setattr("weather_cli.main.get_cache", mock_get_cache)
    monkeypatch.setattr("weather_cli.main.save_cache", mock_save_cache)
    monkeypatch.setattr("weather_cli.main.is_cache_valid", lambda x: False)

    with patch("weather_cli.main.fetch_weather", return_value=SAMPLE_WEATHER_DATA) as mock_fetch:
        result = get_weather("London", use_cache=True)
        mock_fetch.assert_called_once_with("London")
        assert result == SAMPLE_WEATHER_DATA


def test_get_weather_fetches_when_no_cache(monkeypatch):
    """Test that get_weather fetches when no cache exists."""
    def mock_get_cache():
        return {}

    def mock_save_cache(cache):
        pass

    monkeypatch.setattr("weather_cli.main.get_cache", mock_get_cache)
    monkeypatch.setattr("weather_cli.main.save_cache", mock_save_cache)

    with patch("weather_cli.main.fetch_weather", return_value=SAMPLE_WEATHER_DATA) as mock_fetch:
        result = get_weather("London", use_cache=True)
        mock_fetch.assert_called_once_with("London")
        assert result == SAMPLE_WEATHER_DATA


def test_get_weather_no_cache_flag(monkeypatch):
    """Test that --no-cache flag bypasses cache."""
    mock_cache = {
        "london": {
            "data": SAMPLE_WEATHER_DATA,
            "timestamp": 1000.0,
        }
    }

    def mock_get_cache():
        return mock_cache

    def mock_save_cache(cache):
        pass

    monkeypatch.setattr("weather_cli.main.get_cache", mock_get_cache)
    monkeypatch.setattr("weather_cli.main.save_cache", mock_save_cache)

    with patch("weather_cli.main.fetch_weather", return_value=SAMPLE_WEATHER_DATA) as mock_fetch:
        result = get_weather("London", use_cache=False)
        mock_fetch.assert_called_once_with("London")
        assert result == SAMPLE_WEATHER_DATA


def test_fetch_weather_success(monkeypatch):
    """Test successful weather fetch."""
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(SAMPLE_WEATHER_DATA)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = fetch_weather("London")
        mock_run.assert_called_once()
        assert result == SAMPLE_WEATHER_DATA


def test_fetch_weather_failure(monkeypatch):
    """Test weather fetch failure handling."""
    from subprocess import CalledProcessError

    mock_error = CalledProcessError(1, "curl", stderr="Failed to connect")
    with patch("subprocess.run", side_effect=mock_error):
        with pytest.raises(RuntimeError, match="Failed to fetch weather data"):
            fetch_weather("London")


def test_fetch_weather_invalid_json(monkeypatch):
    """Test handling of invalid JSON response."""
    mock_result = MagicMock()
    mock_result.stdout = "not valid json"
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="Failed to parse weather data"):
            fetch_weather("London")


def test_main_json_output(capsys, monkeypatch):
    """Test --json flag outputs raw JSON."""
    with patch("weather_cli.main.get_weather", return_value=SAMPLE_WEATHER_DATA):
        from weather_cli.main import main
        main(["London", "--json"])

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output == SAMPLE_WEATHER_DATA


def test_main_formatted_output(capsys, monkeypatch):
    """Test default formatted output."""
    with patch("weather_cli.main.get_weather", return_value=SAMPLE_WEATHER_DATA):
        from weather_cli.main import main
        main(["London"])

    captured = capsys.readouterr()
    assert "Weather for London, United Kingdom" in captured.out
    assert "Temperature:     22°C / 72°F" in captured.out


def test_main_no_cache_flag(capsys, monkeypatch):
    """Test --no-cache flag."""
    with patch("weather_cli.main.get_weather") as mock_get:
        from weather_cli.main import main
        main(["London", "--no-cache"])

    mock_get.assert_called_once_with("London", use_cache=False)


def test_main_clear_cache(capsys, monkeypatch, tmp_path):
    """Test --clear-cache flag."""
    cache_file = tmp_path / "cache.json"
    cache_file.write_text('{"london": {"data": {}, "timestamp": 1000}}')

    with patch("weather_cli.main.CACHE_FILE", cache_file):
        from weather_cli.main import main
        result = main(["--clear-cache"])

    assert result == 0
    assert not cache_file.exists()
    captured = capsys.readouterr()
    assert "Cache cleared" in captured.out


def test_main_clear_cache_empty(capsys, monkeypatch, tmp_path):
    """Test --clear-cache when cache is already empty."""
    cache_file = tmp_path / "cache.json"

    with patch("weather_cli.main.CACHE_FILE", cache_file):
        from weather_cli.main import main
        result = main(["--clear-cache"])

    assert result == 0
    captured = capsys.readouterr()
    assert "Cache is already empty" in captured.out


def test_main_error_handling(capsys, monkeypatch):
    """Test error handling in main."""
    with patch("weather_cli.main.get_weather", side_effect=RuntimeError("API error")):
        from weather_cli.main import main
        result = main(["London"])

    assert result == 1
    captured = capsys.readouterr()
    assert "Error: API error" in captured.err


def test_main_empty_city(capsys, monkeypatch):
    """Test error when city name is empty."""
    from weather_cli.main import main
    result = main(["   "])

    assert result == 1
    captured = capsys.readouterr()
    assert "Error: City name is required" in captured.err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])