"""Air quality bands.

Singapore's PSI (from NEA) and the US AQI both run on a 0-500 scale where
anything above 100 is outside the healthy range. PHAZE shows PSI for
Singapore (official NEA readings) and US AQI for everywhere else.

Each band has a severity `level` from 0 (good) to 5 (hazardous), shared by
both scales, so the interface and the advice can treat them the same way.
"""

from __future__ import annotations

from dataclasses import dataclass

HEALTHY_LIMIT = 100  # PSI / US AQI above this is outside the healthy range


@dataclass(frozen=True)
class Band:
    label: str
    upper: float  # inclusive upper bound
    color_hex: str  # the band's colour (fills, bars, map dots)
    advice: str
    level: int = -1  # 0 good ... 5 hazardous, -1 no data
    deep: str = "#4B5660"  # darker shade of the colour, for text on a light tint
    short: str = ""  # short name for tight spaces

    @property
    def rgb(self) -> tuple[int, int, int]:
        h = self.color_hex.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    @property
    def name(self) -> str:
        return self.short or self.label


# Colours follow the familiar US EPA order (green, yellow, orange, red, purple, maroon)
GOOD = ("#3F9E62", "#1D6A3C")
MODERATE = ("#E2B13C", "#7D5A0A")
SENSITIVE = ("#EC8A35", "#8F4A0E")
UNHEALTHY = ("#DA4A3B", "#9C2318")
VERY_UNHEALTHY = ("#8C4BA0", "#5A2A6B")
HAZARDOUS = ("#7B2236", "#5C1426")

# NEA PSI bands (Singapore)
PSI_BANDS: list[Band] = [
    Band("Good", 50, GOOD[0], "Normal activities.", 0, GOOD[1]),
    Band("Moderate", 100, MODERATE[0],
         "Normal activities. Unusually sensitive people should watch for symptoms.", 1, MODERATE[1]),
    Band("Unhealthy", 200, UNHEALTHY[0],
         "Cut down on long or intense outdoor activity. Sensitive groups should avoid it.", 3, UNHEALTHY[1]),
    Band("Very unhealthy", 300, VERY_UNHEALTHY[0],
         "Avoid long or intense outdoor activity. Sensitive groups should stay indoors.", 4, VERY_UNHEALTHY[1]),
    Band("Hazardous", float("inf"), HAZARDOUS[0],
         "Stay indoors as much as possible and follow official advisories.", 5, HAZARDOUS[1]),
]

# US EPA AQI bands (rest of the world)
AQI_BANDS: list[Band] = [
    Band("Good", 50, GOOD[0], "Air quality is fine for everyone.", 0, GOOD[1]),
    Band("Moderate", 100, MODERATE[0],
         "Fine for most people. Unusually sensitive people should watch for symptoms.", 1, MODERATE[1]),
    Band("Unhealthy for sensitive groups", 150, SENSITIVE[0],
         "Sensitive groups should cut down on long or intense outdoor activity.", 2, SENSITIVE[1],
         "Sensitive groups"),
    Band("Unhealthy", 200, UNHEALTHY[0],
         "Everyone should cut down on long or intense outdoor activity.", 3, UNHEALTHY[1]),
    Band("Very unhealthy", 300, VERY_UNHEALTHY[0],
         "Avoid long or intense outdoor activity. Sensitive groups should stay indoors.", 4, VERY_UNHEALTHY[1]),
    Band("Hazardous", float("inf"), HAZARDOUS[0],
         "Stay indoors as much as possible and follow official advisories.", 5, HAZARDOUS[1]),
]

UNKNOWN = Band("No data", float("inf"), "#8A96A0", "No reading available right now.", -1, "#4B5660")


def bands_for(index: str = "aqi") -> list[Band]:
    return PSI_BANDS if index == "psi" else AQI_BANDS


def band_for(value: float | None, index: str = "aqi") -> Band:
    """Return the band for a PSI ('psi') or US AQI ('aqi') value."""
    if value is None:
        return UNKNOWN
    bands = bands_for(index)
    for band in bands:
        if value <= band.upper:
            return band
    return bands[-1]


def is_unhealthy(value: float | None, threshold: float = HEALTHY_LIMIT) -> bool:
    return value is not None and value > threshold


def index_name(index: str) -> str:
    return "PSI" if index == "psi" else "US AQI"


def scale_position(value: float | None, index: str = "aqi") -> float | None:
    """Where a value sits on an equal-width band scale, from 0.0 (left) to 1.0 (right).

    Each band gets the same width, so 'Good' (0-50) isn't squeezed next to
    'Hazardous' (301-500). Values above 500 pin to the right edge.
    """
    if value is None:
        return None
    bands = bands_for(index)
    lower = 0.0
    for i, band in enumerate(bands):
        upper = 500.0 if band.upper == float("inf") else band.upper
        if value <= upper or i == len(bands) - 1:
            frac = 0.0 if upper == lower else (min(value, upper) - lower) / (upper - lower)
            return round((i + max(0.0, min(1.0, frac))) / len(bands), 4)
        lower = upper
    return 1.0
