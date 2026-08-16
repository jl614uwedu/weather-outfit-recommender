from src.config import PipelineConfig
from src.consistency import check_consistency
from tests.fakes import make_weather

config = PipelineConfig()


def test_cold_weather_requires_warm_language():
    weather = make_weather(temperature_f=30.0, condition="clear")
    result = check_consistency(weather, "Wear shorts and a tank top today.", config)
    assert not result.passed
    assert result.reasons


def test_cold_weather_with_jacket_passes():
    weather = make_weather(temperature_f=30.0, condition="clear")
    result = check_consistency(weather, "Bundle up in a warm jacket and layers.", config)
    assert result.passed


def test_hot_weather_rejects_heavy_coat():
    weather = make_weather(temperature_f=90.0, condition="clear")
    result = check_consistency(weather, "Wear a heavy winter coat and a parka.", config)
    assert not result.passed


def test_hot_weather_light_clothes_passes():
    weather = make_weather(temperature_f=90.0, condition="clear")
    result = check_consistency(weather, "Go light and breathable, shorts are fine.", config)
    assert result.passed


def test_rain_requires_rain_protection():
    weather = make_weather(temperature_f=60.0, condition="rain", precipitation_chance=0.7)
    result = check_consistency(weather, "A light layer should do the trick.", config)
    assert not result.passed


def test_rain_with_umbrella_passes():
    weather = make_weather(temperature_f=60.0, condition="rain", precipitation_chance=0.7)
    result = check_consistency(weather, "Bring an umbrella and a light jacket.", config)
    assert result.passed


def test_snow_requires_snow_gear():
    weather = make_weather(temperature_f=28.0, condition="snow", precipitation_chance=0.8)
    result = check_consistency(weather, "Wear a warm coat.", config)
    assert not result.passed  # cold check passes but snow-specific gear is missing


def test_mild_weather_is_flexible():
    weather = make_weather(temperature_f=62.0, condition="clear", precipitation_chance=0.1)
    result = check_consistency(weather, "A t-shirt and jeans will be comfortable today.", config)
    assert result.passed
