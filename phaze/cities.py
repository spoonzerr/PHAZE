"""Default list of cities to track: haze hotspots in Southeast Asia plus major cities worldwide."""

from __future__ import annotations

# name, country, lat, lon, region
DEFAULT_CITIES: list[dict] = [
    {"name": "Singapore", "country": "Singapore", "lat": 1.3521, "lon": 103.8198, "region": "Southeast Asia"},
    {"name": "Johor Bahru", "country": "Malaysia", "lat": 1.4927, "lon": 103.7414, "region": "Southeast Asia"},
    {"name": "Kuala Lumpur", "country": "Malaysia", "lat": 3.1390, "lon": 101.6869, "region": "Southeast Asia"},
    {"name": "Kuching", "country": "Malaysia", "lat": 1.5535, "lon": 110.3593, "region": "Southeast Asia"},
    {"name": "Jakarta", "country": "Indonesia", "lat": -6.2088, "lon": 106.8456, "region": "Southeast Asia"},
    {"name": "Pekanbaru", "country": "Indonesia", "lat": 0.5071, "lon": 101.4478, "region": "Southeast Asia"},
    {"name": "Palembang", "country": "Indonesia", "lat": -2.9761, "lon": 104.7754, "region": "Southeast Asia"},
    {"name": "Pontianak", "country": "Indonesia", "lat": -0.0263, "lon": 109.3425, "region": "Southeast Asia"},
    {"name": "Bangkok", "country": "Thailand", "lat": 13.7563, "lon": 100.5018, "region": "Southeast Asia"},
    {"name": "Chiang Mai", "country": "Thailand", "lat": 18.7883, "lon": 98.9853, "region": "Southeast Asia"},
    {"name": "Hanoi", "country": "Vietnam", "lat": 21.0278, "lon": 105.8342, "region": "Southeast Asia"},
    {"name": "Ho Chi Minh City", "country": "Vietnam", "lat": 10.8231, "lon": 106.6297, "region": "Southeast Asia"},
    {"name": "Manila", "country": "Philippines", "lat": 14.5995, "lon": 120.9842, "region": "Southeast Asia"},
    {"name": "Yangon", "country": "Myanmar", "lat": 16.8409, "lon": 96.1735, "region": "Southeast Asia"},
    {"name": "Dhaka", "country": "Bangladesh", "lat": 23.8103, "lon": 90.4125, "region": "South Asia"},
    {"name": "Delhi", "country": "India", "lat": 28.6139, "lon": 77.2090, "region": "South Asia"},
    {"name": "Lahore", "country": "Pakistan", "lat": 31.5204, "lon": 74.3587, "region": "South Asia"},
    {"name": "Kathmandu", "country": "Nepal", "lat": 27.7172, "lon": 85.3240, "region": "South Asia"},
    {"name": "Beijing", "country": "China", "lat": 39.9042, "lon": 116.4074, "region": "East Asia"},
    {"name": "Seoul", "country": "South Korea", "lat": 37.5665, "lon": 126.9780, "region": "East Asia"},
    {"name": "Tokyo", "country": "Japan", "lat": 35.6762, "lon": 139.6503, "region": "East Asia"},
    {"name": "Sydney", "country": "Australia", "lat": -33.8688, "lon": 151.2093, "region": "Oceania"},
    {"name": "Los Angeles", "country": "United States", "lat": 34.0522, "lon": -118.2437, "region": "Americas"},
    {"name": "Mexico City", "country": "Mexico", "lat": 19.4326, "lon": -99.1332, "region": "Americas"},
    {"name": "Toronto", "country": "Canada", "lat": 43.6532, "lon": -79.3832, "region": "Americas"},
    {"name": "São Paulo", "country": "Brazil", "lat": -23.5505, "lon": -46.6333, "region": "Americas"},
    {"name": "Lagos", "country": "Nigeria", "lat": 6.5244, "lon": 3.3792, "region": "Africa and Middle East"},
    {"name": "Cairo", "country": "Egypt", "lat": 30.0444, "lon": 31.2357, "region": "Africa and Middle East"},
    {"name": "London", "country": "United Kingdom", "lat": 51.5074, "lon": -0.1278, "region": "Europe"},
]

REGIONS = sorted({c["region"] for c in DEFAULT_CITIES})


def city_key(city: dict) -> str:
    return f"{city['name']}, {city['country']}"


def find_city(key: str, cities: list[dict]) -> dict | None:
    for c in cities:
        if city_key(c) == key:
            return c
    return None
