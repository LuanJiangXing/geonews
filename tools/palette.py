#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GeoNews 配色表 —— 所有品牌物料的唯一取色来源

片头、片尾、转场都从这里取色。**换一期配色 = 改下面 DARK / LIGHT 两行。**

    DARK  —— 片头 + 深色转场（正片里用于画面偏深的交界）
    LIGHT —— 浅色转场（用于两侧都浅的交界）

两套是并存的：同一期里深色和浅色转场会同时用到，所以是两个独立选择。

配色清单与对比图见 `transition/v4-color/`。**相邻期不要用同一套。**

注意：转场不是动态读颜色的——它的透明叠加序列是预先渲染好的 PNG。
换色后必须重新生成 `transition/*/叠加序列/`，否则成片还是旧色。
"""

import os
import sys

# ══════════════════════════════════════════════════════════════
#  这一期用哪两套  ← 每期只改这两行
# ══════════════════════════════════════════════════════════════
DARK = "P3"           # 片头 + 深色转场（深红 #4A1310 / #FF6B3D）
LIGHT = "L2"          # 浅色转场（纯白 #FFFFFF / #D6341B）
# ══════════════════════════════════════════════════════════════


PAPER = "#F4EFE8"     # 深色底上的文字色（品牌纸白）
INK = "#17120F"       # 浅色底上的文字色（品牌墨黑）

# 代号: (名字, 类型, 底色, 强调色, 次级文字色)
#   mute 显式给出而不是推导——两套在用的值是当初逐张对比图定下来的，
#   推导会丢掉底色该有的冷暖倾向。深底偏冷、浅底偏灰。
PALETTES = {
    # —— 深色：片头 / 正片转场 ——
    "night":    ("夜蓝",     "dark",  "#1B2430", "#E63A1F", "#969EAC"),
    "P1":       ("净黑",     "dark",  "#0E0E11", "#E63A1F", "#9A9A9C"),
    "P2":       ("暖夜",     "dark",  "#16171C", "#FF4D24", "#9B9CA0"),
    "P3":       ("深红",     "dark",  "#4A1310", "#FF6B3D", "#B0928E"),
    "P4":       ("石墨",     "dark",  "#1A1A18", "#E8562E", "#A29E98"),
    "P5":       ("深靛",     "dark",  "#171A2B", "#FF5A2B", "#969CAC"),
    # —— 浅色：偏片头/信息卡；做转场扫过深色素材会"闪白" ——
    "warmrice": ("暖米",     "light", "#EFE7DA", "#B8290F", "#8A8578"),
    "L1":       ("品牌纸白", "light", "#F4EFE8", "#C42A12", "#8C8780"),
    "L2":       ("纯白",     "light", "#FFFFFF", "#D6341B", "#8A8A8A"),
    "L4":       ("冷浅灰",   "light", "#EDEFF1", "#C0301C", "#838A8E"),
    "L5":       ("浅橙调",   "light", "#FBEFE9", "#A8200B", "#8C837B"),
}


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def load(key):
    """
    取一套配色，返回各类物料要用的颜色（均为 RGB 三元组）。

    bg      底色 / 转场色带
    accent  强调色（信号标、序号、线条）
    text    主文字色
    mute    次级文字色（片尾链接用）
    grid    网格线色（片头用，很淡）
    """
    if key not in PALETTES:
        raise KeyError(f"没有这套配色：{key}（可选：{', '.join(PALETTES)}）")
    label, mode, bg_hex, accent_hex, mute_hex = PALETTES[key]
    bg, accent, mute = _rgb(bg_hex), _rgb(accent_hex), _rgb(mute_hex)
    text_hex = PAPER if mode == "dark" else INK
    text = _rgb(text_hex)
    return dict(
        key=key, label=label, mode=mode,
        bg=bg, accent=accent, text=text, mute=mute,
        grid=_mix(bg, text, 0.14),
        hex=dict(bg=bg_hex, accent=accent_hex, text=text_hex, mute=mute_hex),
    )


def dark():
    return load(DARK)


def light():
    return load(LIGHT)


def _cli():
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        print(f"{'代号':<10}{'名字':<10}{'类型':<7}{'底色':<10}{'强调色':<10}{'次级文字'}")
        for k, (label, mode, bg, ac, mu) in PALETTES.items():
            mark = " ← 本期深色" if k == DARK else (" ← 本期浅色" if k == LIGHT else "")
            print(f"{k:<10}{label:<10}{mode:<7}{bg:<10}{ac:<10}{mu}{mark}")
        return
    d, l = dark(), light()
    print(f"本期配色：深色 {d['label']} ({d['hex']['bg']}) ／ 浅色 {l['label']} ({l['hex']['bg']})")


if __name__ == "__main__":
    _cli()
