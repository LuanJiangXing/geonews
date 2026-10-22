#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
片头专用词标生成器

现有品牌词标是为「80px 左上角水印」优化的，用了三个小尺寸杠杆：
  condense 0.68   横向压扁字形 —— 大画面里显得被挤扁
  embolden 4.5    描边伪粗体   —— 大画面里显得过重
  track .005      极紧字距

片头有大画面，不需要这些。这里重新出一版：不压缩、不加伪粗、放开字距，
并测试 Light 与 Demi 两种字重。

用 cairosvg 按目标尺寸**原生渲染矢量**（ImageMagick 的 -resize 是先光栅化
再放大，越放大越糊）。

用法：python3 wordmark_variants.py
"""

import math
import os
import sys

import cairosvg

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(os.path.dirname(HERE), "logo", "versions")
sys.path.insert(0, LOGO)
import glyphpath as g  # noqa: E402

FONT_DEMI = "/usr/share/fonts/opentype/urw-base35/URWBookman-Demi.otf"
FONT_LIGHT = "/usr/share/fonts/opentype/urw-base35/URWBookman-Light.otf"

EMBER = "#E63A1F"
PAPER = "#F4EFE8"
C = 100.0


def arc(cx, cy, r, a0, a1, seg=72):
    P = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / seg)),
          cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / seg)))
         for i in range(seg + 1)]
    return "M" + f"{P[0][0]:.2f},{P[0][1]:.2f}" + "".join(
        f" L{q[0]:.2f},{q[1]:.2f}" for q in P[1:])


def lockup(font, word=PAPER, acc=EMBER, track=0.06, gapL=0.20, gapR=0.22,
           condense=1.0, embolden=0.0, barw=0.085, marksw=0.175, markmode="two"):
    dL, aL = g.text_caps(font, "GEO", cap=C, tracking=track)
    dR, aR = g.text_caps(font, "EWS", cap=C, tracking=track)
    bx = aL + gapL * C
    bw = barw * C
    cx = bx + bw / 2
    xR = cx + 0.60 * C + gapR * C
    st = (f' stroke="{word}" stroke-width="{embolden:.2f}" stroke-linejoin="round"'
          if embolden > 0 else "")
    p = [f'<path d="{dL}" fill="{word}"{st}/>',
         f'<rect x="{bx:.2f}" y="{-C:.2f}" width="{bw:.2f}" height="{C:.2f}" fill="{acc}"/>']
    if markmode == "two":
        p.append(f'<path d="{arc(cx, -C / 2, 0.32 * C, -50, 50)}" stroke="{acc}" '
                 f'stroke-width="{marksw * C:.2f}" stroke-linecap="round" fill="none"/>')
        p.append(f'<path d="{arc(cx, -C / 2, 0.58 * C, -50, 50)}" stroke="{acc}" '
                 f'stroke-width="{marksw * C * 0.85:.2f}" stroke-linecap="round" fill="none"/>')
    else:
        p.append(f'<path d="{arc(cx, -C / 2, 0.58 * C, -50, 50)}" stroke="{acc}" '
                 f'stroke-width="{marksw * C * 1.35:.2f}" stroke-linecap="round" fill="none"/>')
    p.append(f'<g transform="translate({xR:.2f},0)"><path d="{dR}" fill="{word}"{st}/></g>')
    body = "".join(p)
    W = xR + aR
    body = f'<g transform="scale({condense:.4f},1)">{body}</g>'
    return body, W * condense


def svg_doc(body, W, pad=0):
    Wp, Hp = W + 2 * pad, C + 2 * pad
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wp:.1f}" height="{Hp:.1f}" '
            f'viewBox="0 0 {Wp:.2f} {Hp:.2f}" fill="none">'
            f'<g transform="translate({pad},{pad + C})">{body}</g></svg>')


# cap=100 时的原始尺寸（供换算）：原始品牌候选
VARIANTS = {
    "现用水印版(基准)": dict(font=FONT_DEMI, track=0.005, gapL=0.16, gapR=0.18,
                              condense=0.68, embolden=4.5),
    "C1 Light·不压缩·宽字距": dict(font=FONT_LIGHT, track=0.06, gapL=0.20, gapR=0.22,
                                   condense=1.00, embolden=0.0),
    "C2 Light·轻压缩·宽字距": dict(font=FONT_LIGHT, track=0.08, gapL=0.22, gapR=0.24,
                                   condense=0.88, embolden=0.0),
    "C3 Demi·不压缩·宽字距": dict(font=FONT_DEMI, track=0.06, gapL=0.20, gapR=0.22,
                                  condense=1.00, embolden=0.0),
    "C4 Demi·轻压缩·宽字距": dict(font=FONT_DEMI, track=0.08, gapL=0.22, gapR=0.24,
                                  condense=0.88, embolden=0.0),
}

# 统一按「着墨宽度 1050px」出图，便于同尺寸比较
TARGET_W = 1050
OUT = os.path.join(HERE, "wordmark-候选")
os.makedirs(OUT, exist_ok=True)

print(f"{'候选':<26}{'原生宽(cap100)':>14}{'比例':>8}{'渲染尺寸':>14}")
print("-" * 66)
for name, kw in VARIANTS.items():
    body, W = lockup(**kw)
    svg = svg_doc(body, W)
    # SVG 用户单位 = cap 100；按目标着墨宽换算渲染宽度
    scale = TARGET_W / W
    px_w = int(round((W) * scale))
    px_h = int(round(C * scale))
    png = os.path.join(OUT, f"{name}.png")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=png,
                     output_width=px_w, output_height=px_h)
    print(f"{name:<26}{W:>13.0f}{W / C:>8.2f}{f'{px_w}x{px_h}':>14}")
print(f"\n输出目录：{OUT}")
