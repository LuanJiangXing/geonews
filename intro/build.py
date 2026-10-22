#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GEONEWS 片头生成器

深色底（品牌夜蓝 #1B2430）· 7 秒 · 母题＝信号波扩散 · 收尾＝词标 + 「第一期」+ 日期区间

三个方向（先出故事板对比，选定后渲全片）：
  A 脉冲扩散   同心圆波从信号标向外扩散，扫过的网格交点亮起定位点
  B 横向扫描   一道斜亮带从左扫到右（呼应新闻间转场的横扫），扫过处点亮
  C 点阵汇聚   散落在网格上的定位点向中心汇聚，聚成信号标

用法：
  python3 build.py                                   # 三方向故事板
  python3 build.py --render A                        # 渲 A 的完整 7 秒
  python3 build.py --render A --title 第一期 --range 26.09.06-26.09.19
"""

import math
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

W, H, FPS = 1920, 1080, 30
DUR = 7.0
N = int(DUR * FPS)                      # 210 帧

# 配色统一从 tools/palette.py 取，改那一处即可（换期配色改 DARK/LIGHT 两行）
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from palette import dark as _palette          # noqa: E402

_PAL = _palette()
NIGHT, EMBER, PAPER = _PAL["bg"], _PAL["accent"], _PAL["text"]

CX = 960.0                              # 画面水平中心
EMBLEM_C = (CX, 470.0)                  # 信号标中心
EMBLEM_S = 285.0                        # 信号标边长
# 收尾用「片头专用词标」：Light 字重 / 不压扁 / 宽字距，字高 150px
WM_CY = 462.0                           # 词标中心
WM_W = 1111.0                           # 词标宽（着墨宽，字高 150）
TITLE_CY = 624.0                        # 「第一期」
RANGE_CY = 700.0                        # 日期区间

FONT_DEMI = "/usr/share/fonts/opentype/urw-base35/URWBookman-Demi.otf"
FONT_CJK = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def seg(t, a, b):
    if b <= a:
        return 1.0 if t >= b else 0.0
    return max(0.0, min(1.0, (t - a) / (b - a)))


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- 静态底图

def make_base():
    """夜蓝底 + 中心柔光（不画网格线）。生成一次逐帧复用。"""
    img = Image.new("RGBA", (W, H), NIGHT + (255,))
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    for i in range(30):
        r = 980 - i * 32
        a = int(13 * (i / 30.0) ** 1.6)
        gd.ellipse([CX - r * 1.45, 470 - r, CX + r * 1.45, 470 + r], fill=a)
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    tint = Image.merge("RGBA", (Image.new("L", (W, H), 46),
                                Image.new("L", (W, H), 66),
                                Image.new("L", (W, H), 96), glow))
    return Image.alpha_composite(img, tint)


BASE = make_base()


def scatter_points(n=14, min_d=180, seed=7):
    """
    随机散布的定位点：不在网格上，彼此保持最小间距，避开中心信号标。
    r 用真实欧氏距离——波是正圆，这样波锋才会真的扫过每个点。
    固定 seed 保证每次渲染一致。
    """
    import random
    rng = random.Random(seed)
    pts, tries = [], 0
    while len(pts) < n and tries < 6000:
        tries += 1
        x = rng.uniform(110, W - 110)
        y = rng.uniform(90, H - 90)
        r = math.hypot(x - CX, y - 470)
        if r < 250:
            continue
        if all(math.hypot(x - px, y - py) >= min_d for px, py, _ in pts):
            pts.append((x, y, r))
    return pts


PTS = scatter_points()

EMBLEM = Image.open(os.path.join(ASSETS, "square.png")).convert("RGBA")
WORDMARK = Image.open(os.path.join(ASSETS, "wordmark-c2.png")).convert("RGBA")


# ---------------------------------------------------------------- 绘制工具

def paste_center(dst, src, cx, cy, alpha=1.0):
    if alpha <= 0.008:
        return
    im = src
    if alpha < 0.995:
        im = src.copy()
        im.putalpha(src.getchannel("A").point(lambda v: int(v * alpha)))
    dst.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def emblem_scaled(scale):
    s = max(2, int(EMBLEM_S * scale))
    return EMBLEM.resize((s, s), Image.LANCZOS)


def _tmp(layer):
    """
    返回一个与 layer 同尺寸的透明层。

    必须这样画：ImageDraw **不做 alpha 混合**，它把 RGBA 值原样写进像素，
    之后 convert("RGB") 会丢掉 alpha 通道，带透明度的笔触就变成满亮度——
    表现就是"硬跳"而不是淡入。画在独立层上再 alpha_composite 才正确。
    """
    return Image.new("RGBA", layer.size, (0, 0, 0, 0))


def draw_pin(layer, x, y, k):
    """定位点：中心实点 + 一圈扩散余晖。k=0..1"""
    if k <= 0.012:
        return
    t = _tmp(layer)
    d = ImageDraw.Draw(t)
    if k < 1.0:
        gr = 7 + 24 * k
        ga = int(150 * k * (1 - k) * 4)
        if ga > 0:
            d.ellipse([x - gr, y - gr, x + gr, y + gr],
                      outline=EMBER + (min(130, ga),), width=2)
    r = 4.0 + 3.0 * k
    d.ellipse([x - r, y - r, x + r, y + r], fill=EMBER + (int(235 * k),))
    layer.alpha_composite(t)


def ring(layer, cx, cy, radius, width, alpha):
    if alpha <= 0.005 or radius <= 1:
        return
    t = _tmp(layer)
    ImageDraw.Draw(t).ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        outline=EMBER + (int(255 * min(1.0, alpha)),), width=width)
    layer.alpha_composite(t)


# ---------------------------------------------------------------- 三个方向

WAVES = (0.95, 1.30, 1.65)              # 三圈错峰起点
WAVE_LEN = 1.85
R0, R1 = 60.0, 1030.0


def variant_A(t, layer):
    """脉冲扩散"""
    es = lerp(0.80, 1.0, ease(seg(t, 0.15, 1.05)))
    ea = ease(seg(t, 0.15, 1.00)) * (1 - ease(seg(t, 3.20, 4.05)))
    if ea > 0.01:
        paste_center(layer, emblem_scaled(es), EMBLEM_C[0], EMBLEM_C[1], ea)

    for st in WAVES:
        u = (t - st) / WAVE_LEN
        if 0 < u < 1:
            ring(layer, EMBLEM_C[0], EMBLEM_C[1], lerp(R0, R1, ease(u)),
                 max(2, int(7 * (1 - u))), (1 - u) ** 1.5 * 0.85)

    fade = 1 - ease(seg(t, 3.20, 3.95))
    for (x, y, r) in PTS:
        lit = 0.0
        for st in WAVES:
            u = (t - st) / WAVE_LEN
            if 0 < u < 1 and lerp(R0, R1, ease(u)) >= r:
                lit = max(lit, 1.0 - u)
        draw_pin(layer, x, y, lit * fade)


def variant_B(t, layer):
    """横向扫描"""
    es = lerp(0.82, 1.0, ease(seg(t, 1.10, 2.10)))
    ea = ease(seg(t, 1.10, 2.00)) * (1 - ease(seg(t, 3.90, 4.80)))
    if ea > 0.01:
        paste_center(layer, emblem_scaled(es), EMBLEM_C[0], EMBLEM_C[1], ea)

    if 0.15 <= t <= 3.95:
        u = ease(seg(t, 0.15, 3.90))
        S = lerp(-380.0, W + 380.0, u)
        SK = 240
        tl = _tmp(layer)
        d = ImageDraw.Draw(tl)
        d.polygon([(S - 150 - SK, 0), (S + 150 - SK, 0),
                   (S + 150 + SK, H), (S - 150 + SK, H)], fill=EMBER + (32,))
        d.line([(S + 150 - SK, 0), (S + 150 + SK, H)], fill=EMBER + (150,), width=5)
        d.line([(S - 150 - SK, 0), (S - 150 + SK, H)], fill=EMBER + (70,), width=2)
        layer.alpha_composite(tl)

    Sx = lerp(-380.0, W + 380.0, ease(seg(t, 0.15, 3.90)))
    fade = 1 - ease(seg(t, 3.90, 4.90))
    for (x, y, r) in PTS:
        draw_pin(layer, x, y, (1.0 if x <= Sx else 0.0) * fade)


def variant_C(t, layer):
    """点阵汇聚"""
    conv = ease(seg(t, 1.00, 3.50))
    fade = ease(seg(t, 3.60, 4.70))
    for (x, y, r) in PTS:
        px = lerp(x, EMBLEM_C[0], conv * 0.92)
        py = lerp(y, EMBLEM_C[1], conv * 0.92)
        draw_pin(layer, px, py, (1 - fade) * (0.35 + 0.65 * conv))
    ea = ease(seg(t, 3.00, 4.30))
    if ea > 0.01:
        paste_center(layer, emblem_scaled(lerp(0.70, 1.0, ea)),
                     EMBLEM_C[0], EMBLEM_C[1], ea)


# ---------------------------------------------------------------- 收尾（共用）

def outro(t, layer, title, rng):
    # 时序要求：内容须在 5.93s 前出完（新闻间转场会在片头第 5.93s 开始扫入），
    # 之后留一段干净停顿，再由转场带出正片。
    wi = ease(seg(t, 3.45, 4.85))
    if wi > 0.01:
        scale = lerp(0.965, 1.0, wi)
        wm = WORDMARK.resize((int(WM_W * scale),
                              int(WM_W * scale * WORDMARK.height / WORDMARK.width)),
                             Image.LANCZOS)
        paste_center(layer, wm, CX, WM_CY, wi)

    ta = ease(seg(t, 4.65, 5.50))
    if ta > 0.01:
        f = ImageFont.truetype(FONT_CJK, 58)
        box = Image.new("RGBA", (W, 90), (0, 0, 0, 0))
        ImageDraw.Draw(box).text((CX, 45), title, font=f,
                                 fill=PAPER + (int(235 * ta),), anchor="mm")
        layer.alpha_composite(box, (0, int(TITLE_CY - 45)))

    ra = ease(seg(t, 4.95, 5.85))
    if ra > 0.01:
        f = ImageFont.truetype(FONT_DEMI, 42)
        txt = rng
        d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        advance = 0
        widths = []
        for ch in txt:
            bb = d0.textbbox((0, 0), ch, font=f)
            widths.append(bb[2] - bb[0])
            advance += (bb[2] - bb[0]) + 5
        box = Image.new("RGBA", (advance + 20, 60), (0, 0, 0, 0))
        db = ImageDraw.Draw(box)
        x = 10
        for ch, wch in zip(txt, widths):
            db.text((x, 30), ch, font=f, fill=PAPER + (int(140 * ra),), anchor="lm")
            x += wch + 5
        layer.alpha_composite(box, (int(CX - box.width / 2), int(RANGE_CY - 30)))

    # 收尾：两侧细横线
    la = ease(seg(t, 5.45, 6.05))
    if la > 0.01:
        d = ImageDraw.Draw(layer)
        y = int(TITLE_CY)
        d.line([(CX - 330, y), (CX - 250, y)], fill=PAPER + (int(120 * la),), width=2)
        d.line([(CX + 250, y), (CX + 330, y)], fill=PAPER + (int(120 * la),), width=2)


def frame(variant, i, title, rng):
    t = i / FPS
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gi = ease(seg(t, 0.0, 1.0))
    gl = BASE.copy()
    gl.putalpha(BASE.getchannel("A").point(lambda v: int(v * gi)))
    layer.alpha_composite(gl)
    {"A": variant_A, "B": variant_B, "C": variant_C}[variant](t, layer)
    outro(t, layer, title, rng)
    return layer.convert("RGB")


# ---------------------------------------------------------------- 输出

def storyboard(title, rng):
    ts = [0.4, 1.6, 2.6, 3.5, 4.4, 5.2, 6.0, 6.9]
    cw, ch, pad = 470, 264, 10
    f = ImageFont.truetype(FONT_CJK, 28)
    names = {"A": "A 脉冲扩散", "B": "B 横向扫描", "C": "C 点阵汇聚"}
    row_h = ch * 2 + 40 + 20
    sheet = Image.new("RGB", (4 * cw + 5 * pad, 60 + 3 * row_h), (16, 20, 26))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 18), "GEONEWS 片头 · 三方向关键帧（7 秒 · 1920×1080 缩放显示）",
           font=f, fill=(232, 228, 222))
    for r, v in enumerate(("A", "B", "C")):
        y0 = 60 + r * row_h
        d.text((pad, y0), names[v], font=f, fill=(236, 110, 70))
        for c, t in enumerate(ts):
            im = frame(v, int(t * FPS), title, rng).resize((cw, ch), Image.LANCZOS)
            x = pad + (c % 4) * (cw + pad)
            y = y0 + 40 + (c // 4) * (ch + pad)
            sheet.paste(im, (x, y))
    out = os.path.join(HERE, "out-故事板.png")
    sheet.save(out)
    print("故事板:", out, sheet.size)


def render(variant, title, rng):
    tmp = os.path.join(HERE, "_frames")
    # 先清空：残留旧帧会被 ffmpeg 一起读进去，成片时长和内容都会错
    if os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    for i in range(N):
        frame(variant, i, title, rng).save(os.path.join(tmp, f"f{i:04d}.png"))
    out = os.path.join(HERE, f"片头-{variant}.mp4")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-framerate", str(FPS), "-i", os.path.join(tmp, "f%04d.png"),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
    print("成片:", out)


if __name__ == "__main__":
    a = sys.argv[1:]
    title = a[a.index("--title") + 1] if "--title" in a else "第一期"
    rng = a[a.index("--range") + 1] if "--range" in a else "26.09.06-26.09.19"
    if "--render" in a:
        render(a[a.index("--render") + 1], title, rng)
    else:
        storyboard(title, rng)
