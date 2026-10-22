"""Font -> SVG outline helper. Keeps logo files font-independent.

Two sizing models:
  text_path(..., size=)   -> size is the em scale (font-native units)
  text_caps(..., cap=)    -> cap is the target CAP HEIGHT (what designers mean)
"""
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.misc.transform import Transform

_cache = {}


def _font(path):
    if path not in _cache:
        f = TTFont(path, lazy=True)
        _cache[path] = (f, f.getGlyphSet(), f["head"].unitsPerEm, f["hmtx"], f.getBestCmap())
    return _cache[path]


def caps_height(font_path):
    f, gs, upem, hmtx, cmap = _font(font_path)
    bp = BoundsPen(gs)
    gs[cmap[ord("H")]].draw(bp)
    return (bp.bounds[3] - bp.bounds[1]) / upem


def em_for_cap(font_path, cap):
    return cap / caps_height(font_path)


def glyph_bounds(font_path, ch):
    """Bounding box of one glyph in em units -> (x0, y0, x1, y1)."""
    f, gs, upem, hmtx, cmap = _font(font_path)
    bp = BoundsPen(gs)
    gs[cmap[ord(ch)]].draw(bp)
    x0, y0, x1, y1 = bp.bounds
    return x0 / upem, y0 / upem, x1 / upem, y1 / upem


def text_path(font_path, text, size=100.0, tracking=0.0, x=0.0, y=0.0):
    f, gs, upem, hmtx, cmap = _font(font_path)
    scale = size / upem
    parts, cursor = [], 0.0
    for ch in text:
        gname = cmap.get(ord(ch), ".notdef")
        spen = SVGPathPen(gs)
        gs[gname].draw(TransformPen(spen, Transform(scale, 0, 0, -scale, x + cursor * scale, y)))
        d = spen.getCommands()
        if d:
            parts.append(d)
        cursor += hmtx[gname][0] + tracking * upem
    return " ".join(parts), (cursor - tracking * upem) * scale


def text_caps(font_path, text, cap=100.0, tracking=0.0, x=0.0, y=0.0):
    return text_path(font_path, text, size=em_for_cap(font_path, cap),
                     tracking=tracking, x=x, y=y)
