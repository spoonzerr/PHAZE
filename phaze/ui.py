"""PHAZE interface building blocks.

Small functions that return HTML strings (rendered with st.html), plus the
chart and map builders. Every piece of text that comes from data, the user or
a model is escaped before it goes into the page.
"""

from __future__ import annotations

import base64
import html
import random
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .bands import UNKNOWN, Band, band_for, bands_for, index_name, scale_position
from .guidance import Verdict

STYLE_PATH = Path(__file__).with_name("style.css")


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def css() -> str:
    return f"<style>{STYLE_PATH.read_text()}</style>"


def icon(name: str, extra: str = "") -> str:
    """A Material Symbols icon (the icon font ships with Streamlit)."""
    return f'<span class="ph-icon {extra}" aria-hidden="true">{esc(name)}</span>'


def svg_img(svg: str, cls: str, alt: str = "") -> str:
    """Inline SVG isn't allowed by st.html, so drawings go in as data-URI images."""
    uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    return f'<img class="{cls}" src="{uri}" alt="{esc(alt)}"{"" if alt else " aria-hidden=\"true\""}>'


def tint(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def fmt_value(value) -> str:
    return "–" if value is None else str(round(value))


def fmt_time(iso: str | None, with_day: bool = False) -> str:
    if not iso:
        return ""
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return str(iso)
    hour = t.strftime("%I").lstrip("0") or "12"
    minute = "" if t.minute == 0 else t.strftime(":%M")
    text = f"{hour}{minute} {t.strftime('%p')}"
    return f"{t.strftime('%a')} {text}" if with_day else text


def fmt_date(iso: str | None) -> str:
    try:
        t = datetime.fromisoformat(iso)
        return f"{t.day} {t.strftime('%b')}"
    except (TypeError, ValueError):
        return ""


# ------------------------------------------------------------------ headings

def page_head(title: str, intro: str = "") -> str:
    p = f"<p>{esc(intro)}</p>" if intro else ""
    return f'<div class="ph-pagehead"><h1>{esc(title)}</h1>{p}</div>'


def section(title: str, note: str = "") -> str:
    p = f"<p>{esc(note)}</p>" if note else ""
    return f'<div class="ph-section"><h2>{esc(title)}</h2>{p}</div>'


# ------------------------------------------------------------------ the sky

# How the sky looks at each severity level (-1 = no reading)
SKIES = {
    -1: dict(top="#9AA7B1", mid="#C5CED4", low="#E3E7EA", sun="#E6E9EB", sun_ink="#4B5660", glow="rgba(255,255,255,.4)",
             glow_k=1.5, haze="225, 230, 233", haze_a=.2, far="#AEB9C1", far_a=.6, near="#71808B", near_a=.8,
             ink="#1E2D3B", soft="rgba(30, 45, 59, .74)", scale_bg="rgba(255, 255, 255, .55)", bars=0),
    0: dict(top="#5D9FD5", mid="#A9CDEA", low="#E4EEF5", sun="#FFF2C2", sun_ink="#1E2D3B", glow="rgba(255, 240, 175, .9)",
            glow_k=2.1, haze="226, 234, 240", haze_a=0, far="#8DB0CA", far_a=.85, near="#3F5E78", near_a=1,
            ink="#14283A", soft="rgba(20, 40, 58, .74)", scale_bg="rgba(255, 255, 255, .55)", bars=0),
    1: dict(top="#8EB1CE", mid="#C3D3DE", low="#EAE6D9", sun="#FFE6AA", sun_ink="#1E2D3B", glow="rgba(255, 226, 160, .65)",
            glow_k=1.75, haze="234, 228, 210", haze_a=.2, far="#A1B3BF", far_a=.55, near="#4D6375", near_a=.92,
            ink="#14283A", soft="rgba(20, 40, 58, .74)", scale_bg="rgba(255, 255, 255, .55)", bars=1),
    2: dict(top="#A6B0B3", mid="#D2C9B5", low="#EBDBBC", sun="#FFC97F", sun_ink="#2E1E0E", glow="rgba(255, 196, 128, .42)",
            glow_k=1.45, haze="236, 215, 178", haze_a=.34, far="#B2AD9E", far_a=.3, near="#5D6670", near_a=.74,
            ink="#1E2D3B", soft="rgba(30, 45, 59, .76)", scale_bg="rgba(255, 255, 255, .5)", bars=2),
    3: dict(top="#A0958A", mid="#CBAE8B", low="#E3C094", sun="#F39A4E", sun_ink="#2E1608", glow="rgba(243, 140, 70, .26)",
            glow_k=1.2, haze="228, 192, 142", haze_a=.48, far="#B39C80", far_a=.12, near="#6A5A4E", near_a=.52,
            ink="#1E2219", soft="rgba(30, 34, 25, .78)", scale_bg="rgba(255, 248, 238, .5)", bars=2),
    4: dict(top="#7A685E", mid="#94755E", low="#B98E6B", sun="#DE6038", sun_ink="#FFF4EA", glow="rgba(222, 96, 56, .18)",
            glow_k=1.05, haze="176, 134, 100", haze_a=.6, far="#9C7D66", far_a=0, near="#4E3D35", near_a=.34,
            ink="#FFF6EE", soft="rgba(255, 246, 238, .84)", scale_bg="rgba(40, 24, 16, .26)", bars=3),
    5: dict(top="#4C3C3A", mid="#6C5248", low="#8A6A58", sun="#AE3A2E", sun_ink="#FFEDE5", glow="rgba(174, 58, 46, .1)",
            glow_k=1.0, haze="128, 94, 78", haze_a=.72, far="#6E5446", far_a=0, near="#3A2B27", near_a=.22,
            ink="#FFF2EA", soft="rgba(255, 242, 234, .84)", scale_bg="rgba(30, 16, 12, .3)", bars=3),
}

PHRASES = {
    -1: "has no reading right now",
    0: "good",
    1: "moderate",
    2: "unhealthy for sensitive groups",
    3: "unhealthy",
    4: "very unhealthy",
    5: "hazardous",
}


def _buildings(seed: int, width: int, base_y: float, min_h: float, max_h: float, min_w: int, max_w: int,
               spire_chance: float = .12) -> str:
    """A procedurally drawn skyline: a row of blocks, some stepped, a few with masts."""
    rnd = random.Random(seed)
    x, parts = 0.0, []
    while x < width:
        w = rnd.randint(min_w, max_w)
        # taller towers cluster around the middle of the view
        centre = 1 - abs((x + w / 2) / width - .58) * 1.3
        h = min_h + (max_h - min_h) * max(.15, min(1, rnd.random() * .75 + centre * .45))
        top = base_y - h
        parts.append(f"M{x:.0f} {base_y:.0f}V{top:.1f}H{x + w:.0f}V{base_y:.0f}Z")
        if rnd.random() < .35 and w > 26:  # stepped top
            sw = w * rnd.uniform(.35, .6)
            sx = x + (w - sw) * rnd.uniform(.2, .8)
            parts.append(f"M{sx:.1f} {top + 1:.1f}V{top - h * rnd.uniform(.08, .2):.1f}H{sx + sw:.1f}V{top + 1:.1f}Z")
        if rnd.random() < spire_chance:  # mast
            mx = x + w * rnd.uniform(.35, .65)
            parts.append(f"M{mx:.1f} {top + 1:.1f}V{top - h * .22:.1f}H{mx + 2.4:.1f}V{top + 1:.1f}Z")
        x += w + rnd.choice([0, 0, 2, 4, 6])
    return "".join(parts)


@lru_cache(maxsize=1)
def _skyline_paths() -> tuple[str, str]:
    far = _buildings(seed=7, width=1600, base_y=160, min_h=16, max_h=62, min_w=12, max_w=30, spire_chance=.06)
    near = _buildings(seed=21, width=1600, base_y=160, min_h=18, max_h=96, min_w=14, max_w=44, spire_chance=.16)
    return far, near


def sky(place: str, value: float | None, index: str, *, meta: str = "", note: str = "") -> str:
    """The hero: the sky above a place, drawn from its air quality.

    The sun holds the reading. As the air gets worse the sky warms and dims,
    haze thickens, the sun turns into a flat orange disc and the skyline fades.
    """
    band = band_for(value, index)
    level = band.level
    s = SKIES.get(level, SKIES[-1])
    sun_size = 196
    phrase = PHRASES.get(level, PHRASES[-1])
    headline = f"The air in {place} is {phrase}" if level >= 0 else f"{place} has no reading right now"
    long_cls = " ph-sky__headline--long" if len(headline) > 44 else ""
    far, near = _skyline_paths()

    # haze lines across the bottom of the sun, like the logo: none when clear, three when it's bad
    bars = ""
    for i in range(s["bars"]):
        top = 72 + i * 10
        left = [8, 24, 4][i]
        width = [66, 74, 62][i]
        bars += f'<span class="ph-sun__bar" style="top:{top}%;left:{left}%;width:{width}%"></span>'
    sun_cls = "ph-sun ph-sun--hazy" if s["bars"] else "ph-sun"

    def land(path: str, fill: str, opacity: float, z: int) -> str:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 160" width="1600" height="160" '
               f'preserveAspectRatio="xMidYMax slice"><path d="{path}" fill="{fill}" fill-opacity="{opacity}"/></svg>')
        return svg_img(svg, "ph-sky__land").replace("<img ", f'<img style="z-index:{z}" ', 1)

    glow = max(0.0, s["glow_k"] - 1)  # how far the sun's halo reaches, relative to its size
    style = (f"--sky-top:{s['top']};--sky-mid:{s['mid']};--sky-low:{s['low']};--sky-ink:{s['ink']};"
             f"--sky-soft-ink:{s['soft']};--sun:{s['sun']};--sun-ink:{s['sun_ink']};--sun-glow:{s['glow']};"
             f"--glow-blur:{glow * .95:.2f};--glow-spread:{glow * .28:.2f};"
             f"--haze:{s['haze']};--haze-a:{s['haze_a']};--scale-bg:{s['scale_bg']};--sun-size:{sun_size}px;")
    reading = f"{index_name(index)} {fmt_value(value)}, {band.label}" if value is not None else "no reading"
    note_html = f'<p class="ph-sky__meta">{esc(note)}</p>' if note else ""
    meta_html = f'<p class="ph-sky__meta">{esc(meta)}</p>' if meta else ""

    return (
        f'<section class="ph-sky" style="{style}" role="img" aria-label="{esc(place)}: {esc(reading)}">'
        f'{land(far, s["far"], s["far_a"], 3)}'
        f'<div class="ph-sky__haze" style="top:30%;height:26%"></div>'
        f'{land(near, s["near"], s["near_a"], 5)}'
        f'<div class="ph-sky__haze ph-sky__haze--b" style="top:52%;height:22%;z-index:6"></div>'
        f'<div class="ph-sky__haze ph-sky__haze--c" style="top:72%;height:34%;z-index:6"></div>'
        f'<div class="ph-sky__wash"></div>'
        f'<div class="ph-sky__body">'
        f'<div class="ph-sky__text">'
        f'<h1 class="ph-sky__headline{long_cls}">{esc(headline)}</h1>'
        f'<p class="ph-sky__advice">{esc(band.advice)}</p>'
        f'{scale(value, index)}{meta_html}{note_html}'
        f'</div>'
        f'<div class="{sun_cls}"><span class="ph-sun__value">{fmt_value(value)}</span>'
        f'<span class="ph-sun__index">{esc(index_name(index))}</span>{bars}</div>'
        f'</div></section>'
    )


def scale(value: float | None, index: str) -> str:
    bands = bands_for(index)
    here = band_for(value, index)
    pos = scale_position(value, index)
    segs = "".join(f'<span class="ph-scale__seg" style="background:{b.color_hex}"></span>' for b in bands)
    mark = f'<span class="ph-scale__mark" style="left:{pos * 100:.1f}%"></span>' if pos is not None else ""
    labels = "".join(
        f'<span class="{"is-here" if b.label == here.label else ""}">{esc(b.name)}</span>' for b in bands)
    return (f'<div class="ph-scale" role="img" aria-label="{esc(here.label)} on the {esc(index_name(index))} scale">'
            f'<div class="ph-scale__bar">{segs}{mark}</div><div class="ph-scale__labels">{labels}</div></div>')


# ------------------------------------------------------------------ today

def today(items: list[Verdict], note: str = "") -> str:
    if not items:
        return ""
    words = {"go": "Fine", "careful": "Take care", "avoid": "Avoid"}
    cells = "".join(
        f'<div class="ph-today__item ph-today__item--{esc(v.state)}">'
        f'<span class="ph-today__icon" title="{words.get(v.state, "")}">{icon(v.icon)}</span>'
        f'<div><p class="ph-today__what">{esc(v.activity)}</p>'
        f'<p class="ph-today__verdict">{esc(v.text)}</p></div></div>'
        for v in items)
    note_html = f'<p class="ph-today__note">{esc(note)}</p>' if note else ""
    return f'<div class="ph-today">{cells}</div>{note_html}'


# ------------------------------------------------------------------ Singapore regions

def regions(psi: dict) -> str:
    tiles = ""
    for name in ("north", "west", "central", "east", "south"):
        r = psi["regions"].get(name)
        if not r:
            continue
        b = band_for(r.get("psi"), "psi")
        style = f"--tint:{tint(b.color_hex, .17)};--edge:{tint(b.color_hex, .38)};--deep:{b.deep}"
        tiles += (f'<div class="ph-region ph-region--{name}" style="{style}">'
                  f'<span class="ph-region__name">{name.title()}</span>'
                  f'<span class="ph-region__value">{fmt_value(r.get("psi"))}</span>'
                  f'<span class="ph-region__band">{esc(b.label)}</span></div>')
    return f'<div class="ph-regions" role="list" aria-label="PSI by region">{tiles}</div>'


# ------------------------------------------------------------------ chips, sparklines, lists

def chip(value: float | None, index: str = "aqi", small: bool = False) -> str:
    b = band_for(value, index)
    style = f"--tint:{tint(b.color_hex, .18)};--deep:{b.deep}"
    cls = "ph-chip ph-chip--small" if small else "ph-chip"
    return (f'<span class="{cls}" style="{style}"><span class="ph-chip__value">{fmt_value(value)}</span>'
            f'<span class="ph-chip__band">{esc(b.name)}</span></span>')


def reading(value: float | None, index: str = "aqi") -> str:
    """A compact reading: the number, with its band underneath, both in the band's colour."""
    b = band_for(value, index)
    return (f'<div class="ph-reading" style="--deep:{b.deep};--band:{b.color_hex}">'
            f'<span class="ph-reading__value">{fmt_value(value)}</span><span class="ph-reading__band">{esc(b.name)}</span></div>')


def sparkline(values: list, color: str = "#1E2D3B", width: int = 120, height: int = 34) -> str:
    pts = [v for v in values if v is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts), max(pts)
    span = max(hi - lo, 12)  # don't exaggerate tiny wiggles
    mid = (hi + lo) / 2
    lo, hi = mid - span / 2, mid + span / 2
    step = width / (len(values) - 1)
    coords = []
    for i, v in enumerate(values):
        if v is None:
            continue
        y = height - 3 - (v - lo) / (hi - lo) * (height - 6)
        coords.append((i * step, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"M{coords[0][0]:.1f},{height} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in coords) + f" L{coords[-1][0]:.1f},{height} Z"
    x0, y0 = coords[0]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 {width + 8} {height + 8}" width="{width + 8}" '
           f'height="{height + 8}" preserveAspectRatio="none">'
           f'<path d="{area}" fill="{tint(color, .14)}"/>'
           f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round" '
           f'stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
           f'<circle cx="{x0:.1f}" cy="{y0:.1f}" r="3.2" fill="{color}"/></svg>')
    return svg_img(svg, "ph-spark")


TREND_WORDS = {
    "rising": ("trending_up", "Getting worse"),
    "easing": ("trending_down", "Getting better"),
    "steady": ("trending_flat", "Holding steady"),
    "unknown": ("help", "No forecast yet"),
}


def places(rows: list[dict]) -> str:
    """Watchlist rows: {name, where, value, index, forecast(list), trend(Trend), peak_text}."""
    if not rows:
        return ""
    out = ""
    for r in rows:
        b = band_for(r["value"], r["index"])
        ic, word = TREND_WORDS.get(r["trend"].direction, TREND_WORDS["unknown"])
        detail = f"<br>{esc(r['peak_text'])}" if r.get("peak_text") else ""
        spark_color = band_for(max([v for v in r["forecast"] if v is not None] or [0])).deep if r["forecast"] else b.deep
        out += (f'<div class="ph-place">'
                f'<div><div class="ph-place__name">{esc(r["name"])}</div><div class="ph-place__where">{esc(r["where"])}</div></div>'
                f'<div class="ph-place__spark" title="Next 24 hours">{sparkline(r["forecast"][:24], spark_color)}</div>'
                f'<div class="ph-place__trend">{icon(ic)}<b>{esc(word)}</b>{detail}</div>'
                f'{reading(r["value"], r["index"])}</div>')
    return f'<div class="ph-places">{out}</div>'


def ranking(rows: list[dict], limit: int = 8, scale_max: float = 300) -> str:
    """Rows: {name, country, us_aqi}. Bars are scaled so 300 fills the track."""
    items = [r for r in rows if r.get("us_aqi") is not None]
    items.sort(key=lambda r: -r["us_aqi"])
    lis = ""
    for i, r in enumerate(items[:limit], start=1):
        b = band_for(r["us_aqi"])
        pct = max(3, min(100, r["us_aqi"] / scale_max * 100))
        lis += (f'<li><span class="ph-rank__n">{i}</span>'
                f'<span class="ph-rank__name">{esc(r["name"])}<small>{esc(r.get("country", ""))}</small></span>'
                f'<span class="ph-rank__track" title="{esc(b.label)}"><span class="ph-rank__fill" style="width:{pct:.0f}%;background:{b.color_hex}"></span></span>'
                f'<span class="ph-rank__value">{fmt_value(r["us_aqi"])}</span></li>')
    return f'<ol class="ph-rank">{lis}</ol>'


def legend(index: str = "aqi") -> str:
    items = ""
    lower = 0
    for b in bands_for(index):
        rng = f"{lower}+" if b.upper == float("inf") else f"{lower}–{int(b.upper)}"
        items += f'<span><i style="background:{b.color_hex}"></i>{esc(b.label)} <small>({rng})</small></span>'
        lower = int(b.upper) + 1 if b.upper != float("inf") else lower
    return f'<div class="ph-legend">{items}</div>'


def band_list(index: str = "aqi") -> str:
    items, lower = "", 0
    for b in bands_for(index):
        rng = f"{lower}+" if b.upper == float("inf") else f"{lower} to {int(b.upper)}"
        items += f'<li><i style="background:{b.color_hex}"></i><span><b>{esc(b.label)}</b>{rng}</span></li>'
        if b.upper != float("inf"):
            lower = int(b.upper) + 1
    return f'<ul class="ph-bands">{items}</ul>'


# ------------------------------------------------------------------ the next 48 hours

def hours(times: list[str], values: list, threshold: float) -> str:
    if not times:
        return ""
    cells, ok_row, labels = "", "", ""
    n = len(times)
    clear_hours = 0
    for i, (t, v) in enumerate(zip(times, values)):
        b = band_for(v)
        try:
            dt = datetime.fromisoformat(t)
        except ValueError:
            dt = None
        day = " is-day-start" if dt is not None and dt.hour == 0 and i > 0 else ""
        within = v is not None and v <= threshold
        clear_hours += within
        tip = f"{fmt_time(t, with_day=True)}: US AQI {fmt_value(v)} ({b.label})"
        tip += ", within your limit" if within else ", above your limit" if v is not None else ""
        cells += f'<span class="ph-hours__cell{day}" style="background:{tint(b.color_hex, .8)}" title="{esc(tip)}"></span>'
        ok_row += f'<span class="ph-hours__ok{day}{" is-ok" if within else ""}"></span>'
        if dt is None:
            continue
        left = i / n * 100
        if i == 0:
            labels += f'<span style="left:0">Now</span>'
        elif dt.hour == 0:
            labels += f'<span class="is-day" style="left:{left:.2f}%">{dt.strftime("%a")}</span>'
        elif dt.hour in (6, 12, 18) and 3 < i < n - 3:
            text = "Noon" if dt.hour == 12 else fmt_time(t)
            labels += f'<span style="left:{left:.2f}%">{text}</span>'
    if clear_hours:
        key = (f'<b></b>Green underneath means that hour is within your limit of {round(threshold)}. '
               f'That\'s {clear_hours} of the next {n} hours.')
    else:
        key = f'None of the next {n} hours are forecast to be within your limit of {round(threshold)}.'
    return (f'<div class="ph-hours" role="img" aria-label="Hourly forecast for the next {n} hours">'
            f'<div class="ph-hours__row">{cells}</div><div class="ph-hours__oks">{ok_row}</div>'
            f'<div class="ph-hours__labels">{labels}</div><div class="ph-hours__key">{key}</div></div>')


# ------------------------------------------------------------------ AI output

def by(label: str, ai: bool = True) -> str:
    return f'<div class="ph-by">{icon("auto_awesome" if ai else "rule")}{esc(label)}</div>'


def plan(result: dict) -> str:
    wins = "".join(f'<div class="ph-window"><b>{esc(w.get("when", ""))}</b><span>{esc(w.get("why", ""))}</span></div>'
                   for w in result.get("windows", []))
    wins_html = f'<h3>Best times</h3><div class="ph-windows">{wins}</div>' if wins else ""
    tip = f'<div class="ph-tip">{icon("lightbulb")}<span>{esc(result["tip"])}</span></div>' if result.get("tip") else ""
    who = "Planned by Nemotron Super" if result.get("by") == "super" else "Standard plan (AI is off)"
    return (f'<div class="ph-answer"><p class="ph-answer__lead">{esc(result.get("summary", ""))}</p>'
            f'{wins_html}{tip}{by(who, result.get("by") == "super")}</div>')


def report(rep: dict) -> str:
    causes = "".join(f"<li>{esc(c)}</li>" for c in rep.get("causes", []))
    causes_html = f"<h3>What's causing it</h3><ul>{causes}</ul>" if causes else ""
    outlook = f"<h3>What happens next</h3><p>{esc(rep['outlook'])}</p>" if rep.get("outlook") else ""
    srcs = ""
    for i, s in enumerate(rep.get("sources", []), start=1):
        url = s.get("url", "")
        domain = url.split("/")[2].removeprefix("www.") if url.count("/") >= 2 else ""
        srcs += (f'<li><a href="{esc(url)}" target="_blank" rel="noopener">[{i}] {esc(s.get("title", "Untitled"))}</a>'
                 f'<small>{esc(domain)}</small></li>')
    srcs_html = f"<h3>Sources</h3><ul class='ph-sources'>{srcs}</ul>" if srcs else ""
    who = {"super": "Summarised by Nemotron Super from Tavily search results",
           "search only": "Search results from Tavily (AI summary is off)"}.get(rep.get("by"), "")
    by_html = by(who, rep.get("by") == "super") if who else ""
    return (f'<div class="ph-answer"><p class="ph-answer__lead">{esc(rep.get("summary", ""))}</p>'
            f'{causes_html}{outlook}{srcs_html}{by_html}</div>')


# ------------------------------------------------------------------ alerts

def alert_timeline(log: list[dict]) -> str:
    items = ""
    for a in log:
        b = band_for(a.get("value"), a.get("index", "aqi"))
        actions = "".join(f"<li>{esc(x)}</li>" for x in a.get("actions", []))
        actions_html = f'<ul class="ph-alert__actions">{actions}</ul>' if actions else ""
        who = "Written by Nemotron Nano" if a.get("by") == "nano" else "Standard message"
        sent = " Sent to Telegram." if a.get("pushed") else ""
        items += (f'<li class="ph-alert"><span class="ph-alert__time">{esc(a.get("at", ""))}</span>'
                  f'<span class="ph-alert__rail"><span class="ph-alert__dot" style="background:{b.color_hex}"></span></span>'
                  f'<div class="ph-alert__card"><div class="ph-alert__head"><p class="ph-alert__title">{esc(a.get("title", ""))}</p>'
                  f'{chip(a.get("value"), a.get("index", "aqi"), small=True)}</div>'
                  f'<p class="ph-alert__msg">{esc(a.get("message", ""))}</p>{actions_html}'
                  f'<div class="ph-alert__foot">{esc(who)}.{esc(sent)}</div></div></li>')
    return f'<ol class="ph-timeline">{items}</ol>'


def empty(title: str, body: str) -> str:
    return f'<div class="ph-empty"><b>{esc(title)}</b>{esc(body)}</div>'


def watch_rows(readings: list[dict], threshold: float) -> str:
    rows = ""
    for rd in sorted(readings, key=lambda r: -(r["value"] or 0)):
        over = rd["value"] is not None and rd["value"] > threshold
        state = "Above your limit" if over else "Within your limit"
        rows += (f'<div class="ph-watch__row"><span class="ph-watch__name">{esc(rd["place"])}'
                 f'<small>{esc(index_name(rd["index"]))}. {state}</small></span>{chip(rd["value"], rd["index"], small=True)}</div>')
    return f'<div class="ph-watch">{rows}</div>'


# ------------------------------------------------------------------ sidebar status

def status(items: list[tuple[str, str, str]]) -> str:
    """items: (state 'on' | 'off' | 'warn', bold label, detail)."""
    lis = "".join(f'<li><span class="ph-dot ph-dot--{esc(s)}"></span><span><b>{esc(label)}</b> {esc(detail)}</span></li>'
                  for s, label, detail in items)
    return f'<ul class="ph-status">{lis}</ul>'


# ------------------------------------------------------------------ how it works

def flow(rows: list[tuple[str, str, str, str]]) -> str:
    """rows: (agent, what it does, model 'nano' | 'super' | 'both', why)."""
    pills = {
        "nano": '<span class="ph-model ph-model--nano">Nemotron Nano</span>',
        "super": '<span class="ph-model ph-model--super">Nemotron Super</span>',
        "both": '<span class="ph-model ph-model--nano">Nano</span> <span class="ph-model ph-model--super">Super</span>',
    }
    out = ""
    for agent, does, model, why in rows:
        out += (f'<div class="ph-flow__row"><div class="ph-flow__agent">{esc(agent)}<small>{esc(does)}</small></div>'
                f'<div class="ph-flow__arrow">{icon("arrow_forward")}</div>'
                f'<div>{pills[model]}</div>'
                f'<div class="ph-flow__why">{esc(why)}</div></div>')
    return f'<div class="ph-flow">{out}</div>'


def split(nano: int, sup: int) -> str:
    total = nano + sup
    if not total:
        return ""
    n = nano / total * 100
    return (f'<div class="ph-split" role="img" aria-label="{nano} Nano calls, {sup} Super calls">'
            f'<span class="ph-split__nano" style="width:{n:.1f}%"></span><span class="ph-split__super" style="width:{100 - n:.1f}%"></span></div>'
            f'<div class="ph-split-key"><span><i style="background:#8DB6DA"></i>Nano {nano}</span>'
            f'<span><i style="background:#1E2D3B"></i>Super {sup}</span></div>')


def data_sources() -> str:
    items = [
        ("Singapore PSI", "National Environment Agency, via data.gov.sg"),
        ("World air quality and forecasts", "Copernicus CAMS, via Open-Meteo"),
        ("Haze news", "Tavily web search"),
        ("AI models", "NVIDIA Nemotron 3, served by Nebius Token Factory"),
    ]
    return '<div class="ph-sources-row">' + "".join(
        f'<div class="ph-source"><b>{esc(a)}</b>{esc(b)}</div>' for a, b in items) + "</div>"
