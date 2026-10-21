"""Plain-language guidance: what a reading means for everyday plans, and where it's heading.

The verdicts follow the official band advice (NEA for PSI, US EPA for AQI):
cut down on long or intense outdoor activity as levels rise, and stay
indoors when it's hazardous. They're general guidance, not medical advice.
"""

from __future__ import annotations

from dataclasses import dataclass

GO, CAREFUL, AVOID = "go", "careful", "avoid"


@dataclass(frozen=True)
class Verdict:
    activity: str
    icon: str  # Material Symbols name
    state: str  # go / careful / avoid
    text: str


# For each activity: one (state, text) per severity level 0-5, for the general public and for sensitive groups
_ACTIVITIES = {
    "Exercise outdoors": {
        "icon": "directions_run",
        "general": [(GO, "Go for it"), (GO, "Go for it"), (CAREFUL, "Keep it light"),
                    (AVOID, "Move it indoors"), (AVOID, "Indoors only"), (AVOID, "Skip it today")],
        "sensitive": [(GO, "Go for it"), (CAREFUL, "Keep it light"), (AVOID, "Move it indoors"),
                      (AVOID, "Move it indoors"), (AVOID, "Indoors only"), (AVOID, "Skip it today")],
    },
    "Walk or commute": {
        "icon": "directions_walk",
        "general": [(GO, "No problem"), (GO, "No problem"), (GO, "Fine"),
                    (CAREFUL, "Fine for short trips"), (CAREFUL, "Keep it short"),
                    (AVOID, "Only if you must, with an N95")],
        "sensitive": [(GO, "No problem"), (GO, "No problem"), (CAREFUL, "Keep it short"),
                      (CAREFUL, "Keep trips short"), (AVOID, "Wear an N95 if you must go"),
                      (AVOID, "Only if you must, with an N95")],
    },
    "Open windows": {
        "icon": "window",
        "general": [(GO, "Let the air in"), (GO, "Fine"), (CAREFUL, "Close them if it smells smoky"),
                    (AVOID, "Keep them closed"), (AVOID, "Keep them closed"),
                    (AVOID, "Keep closed, run a purifier")],
        "sensitive": [(GO, "Let the air in"), (GO, "Fine"), (CAREFUL, "Close them if it smells smoky"),
                      (AVOID, "Keep them closed"), (AVOID, "Keep them closed"),
                      (AVOID, "Keep closed, run a purifier")],
    },
    "Kids playing outside": {
        "icon": "toys",
        # children count as a sensitive group whoever is reading
        "general": [(GO, "Let them play"), (GO, "Let them play"), (CAREFUL, "Shorter playtime"),
                    (AVOID, "Play indoors today"), (AVOID, "Play indoors today"), (AVOID, "Keep them indoors")],
        "sensitive": [(GO, "Let them play"), (GO, "Let them play"), (CAREFUL, "Shorter playtime"),
                      (AVOID, "Play indoors today"), (AVOID, "Play indoors today"), (AVOID, "Keep them indoors")],
    },
}


def is_sensitive(profile: str) -> bool:
    return profile != "General public"


def verdicts(level: int, profile: str = "General public") -> list[Verdict]:
    """Everyday activity verdicts for a severity level (0-5). Returns [] when there's no reading."""
    if level is None or level < 0:
        return []
    level = min(level, 5)
    who = "sensitive" if is_sensitive(profile) else "general"
    out = []
    for activity, spec in _ACTIVITIES.items():
        state, text = spec[who][level]
        out.append(Verdict(activity, spec["icon"], state, text))
    return out


@dataclass(frozen=True)
class Trend:
    direction: str  # "rising", "easing", "steady" or "unknown"
    peak: float | None  # highest value in the look-ahead window
    peak_index: int | None  # position of the peak in the values list


def trend(values: list, hours: int = 12, tolerance: float = 0.12) -> Trend:
    """Compare the next few hours of a forecast with the first hour.

    'rising' if the average ahead is more than `tolerance` (12%) above now,
    'easing' if it's that much below, otherwise 'steady'.
    """
    clean = [v for v in values[: hours + 1] if v is not None]
    if len(clean) < 3:
        return Trend("unknown", None, None)
    now = clean[0]
    ahead = clean[1:]
    avg = sum(ahead) / len(ahead)
    base = max(now, 1)
    change = (avg - now) / base
    direction = "rising" if change > tolerance else "easing" if change < -tolerance else "steady"
    window = [v if v is not None else float("-inf") for v in values[:24]]
    peak_i = max(range(len(window)), key=lambda i: window[i]) if window else None
    peak = values[peak_i] if peak_i is not None and values[peak_i] is not None else None
    return Trend(direction, peak, peak_i)
