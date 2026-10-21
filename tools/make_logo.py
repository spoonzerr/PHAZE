"""Builds the PHAZE logo SVGs in static/. Run: python tools/make_logo.py

The wordmark is set in Parkinsans Bold and converted to outlines, so the logo
looks the same everywhere (an SVG used as an image can't load web fonts).
"""

from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
FONT = STATIC / "fonts" / "parkinsans-latin-wght-normal.woff2"

DUSK = "#1E2D3B"
SUN = "#F2A23A"


def icon_shapes(x=0.0, y=0.0, s=1.0) -> str:
    """Sun behind three bands of haze, drawn on a 64x64 grid.

    The haze bands are cut out of the sun with a small gap, so the mark reads
    on any background.
    """
    def t(v):  # scale helper
        return round(v * s, 2)

    bars = [(10, 37, 44), (20, 46, 54), (8, 55, 38)]  # x1, y, x2 on the 64 grid
    cut = "".join(
        f'<line x1="{t(a)}" y1="{t(b)}" x2="{t(c)}" y2="{t(b)}" stroke="black" stroke-width="{t(10)}" stroke-linecap="round"/>'
        for a, b, c in bars)
    lines = "".join(
        f'<line x1="{t(a)}" y1="{t(b)}" x2="{t(c)}" y2="{t(b)}" stroke="{DUSK}" stroke-width="{t(5)}" stroke-linecap="round"/>'
        for a, b, c in bars)
    return (
        f'<g transform="translate({x},{y})">'
        f'<mask id="haze-cut" maskUnits="userSpaceOnUse"><rect width="{t(64)}" height="{t(64)}" fill="white"/>{cut}</mask>'
        f'<circle cx="{t(33)}" cy="{t(30)}" r="{t(21)}" fill="{SUN}" mask="url(#haze-cut)"/>'
        f'{lines}</g>'
    )


def wordmark_paths(text: str, size: float, x0: float, baseline: float, tracking: float = 0.02):
    font = TTFont(str(FONT))
    if "fvar" in font:
        font = instantiateVariableFont(font, {"wght": 700}, inplace=False)
    upm = font["head"].unitsPerEm
    scale = size / upm
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    hmtx = font["hmtx"]
    parts, x = [], x0
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        parts.append(pen.getCommands())
        x += hmtx[name][0] * scale + tracking * size
    width = x - tracking * size - x0
    bp = BoundsPen(glyphs)
    glyphs[cmap[ord("H")]].draw(bp)
    cap_height = bp.bounds[3] * scale
    return " ".join(parts), width, cap_height


def main():
    STATIC.mkdir(exist_ok=True)
    # Icon only
    (STATIC / "phaze-icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
        f'<title>PHAZE</title>{icon_shapes()}</svg>\n')

    # Icon + wordmark, 64 units tall
    size = 40
    d, width, cap = wordmark_paths("PHAZE", size, x0=76, baseline=32 + 0 + 0)
    baseline = 32 + cap / 2  # centre the capitals on the sun
    d, width, cap = wordmark_paths("PHAZE", size, x0=76, baseline=baseline)
    total = round(76 + width + 4)
    (STATIC / "phaze-logo.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} 64" width="{total}" height="64">'
        f'<title>PHAZE</title>{icon_shapes()}<path d="{d}" fill="{DUSK}"/></svg>\n')
    print("wrote static/phaze-icon.svg and static/phaze-logo.svg", total)


if __name__ == "__main__":
    main()
