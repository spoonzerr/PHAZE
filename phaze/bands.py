"""Air quality bands.

Singapore's PSI (from NEA) and the US AQI both run on a 0-500 scale where
anything above 100 is outside the healthy range. PHAZE shows PSI for
Singapore (official NEA readings) and US AQI for everywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass

HEALTHY_LIMIT = 100  # PSI / US AQI above this is outside the healthy range


@dataclass(frozen=True)
class Band:
    label: str
    upper: float  # inclusive upper bound
    color_hex: str
    rgb: tuple[int, int, int]
    advice: str


# NEA PSI bands (Singapore)
PSI_BANDS: list[Band] = [
    Band("Good", 50, "#2f9e44", (47, 158, 68), "Normal activities."),
    Band("Moderate", 100, "#d4a017", (212, 160, 23),
         "Normal activities. Unusually sensitive people should watch for symptoms."),
    Band("Unhealthy", 200, "#e8590c", (232, 89, 12),
         "Cut down on long or intense outdoor activity. Sensitive groups should avoid it."),
    Band("Very unhealthy", 300, "#c92a2a", (201, 42, 42),
         "Avoid long or intense outdoor activity. Sensitive groups should stay indoors."),
    Band("Hazardous", float("inf"), "#7b2cbf", (123, 44, 191),
         "Stay indoors as much as possible and follow official advisories."),
]

# US EPA AQI bands (rest of the world)
AQI_BANDS: list[Band] = [
    Band("Good", 50, "#2f9e44", (47, 158, 68), "Air quality is fine for everyone."),
    Band("Moderate", 100, "#d4a017", (212, 160, 23),
         "Fine for most people. Unusually sensitive people should watch for symptoms."),
    Band("Unhealthy for sensitive groups", 150, "#f08c00", (240, 140, 0),
         "Sensitive groups should cut down on long or intense outdoor activity."),
    Band("Unhealthy", 200, "#e8590c", (232, 89, 12),
         "Everyone should cut down on long or intense outdoor activity."),
    Band("Very unhealthy", 300, "#c92a2a", (201, 42, 42),
         "Avoid long or intense outdoor activity. Sensitive groups should stay indoors."),
    Band("Hazardous", float("inf"), "#7b2cbf", (123, 44, 191),
         "Stay indoors as much as possible and follow official advisories."),
]

UNKNOWN = Band("No data", float("inf"), "#868e96", (134, 142, 150), "No reading available right now.")


def band_for(value: float | None, index: str = "aqi") -> Band:
    """Return the band for a PSI ('psi') or US AQI ('aqi') value."""
    if value is None:
        return UNKNOWN
    bands = PSI_BANDS if index == "psi" else AQI_BANDS
    for band in bands:
        if value <= band.upper:
            return band
    return bands[-1]


def is_unhealthy(value: float | None, threshold: float = HEALTHY_LIMIT) -> bool:
    return value is not None and value > threshold


def index_name(index: str) -> str:
    return "PSI" if index == "psi" else "US AQI"
