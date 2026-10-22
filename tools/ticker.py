#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
底栏滚动新闻条（跑马灯）—— 生成三个图层

模仿新闻频道的底栏：左侧固定品牌词标块，右侧文字从右向左持续滚动。

**图层顺序很重要**，合成时必须是：
    正片 → 水印 → [底栏底 → 滚动文字 → 词标块] → 转场
底栏夹在水印和转场之间——放转场之后的话，色带扫过时底栏会浮在色带上，穿帮。

**无缝循环**：文字条按「分隔符＋条目」拼成周期，滚动位移对周期取模。
两个要点：(a) 周期取整数像素且逐份按整数位置绘制；(b) 分隔符只放每条前面。

字体：中文用 Noto Serif CJK（衬线，呼应 logo 的 Bookman），
拉丁/数字可换 Bookman——见 --font。
"""

import argparse
import json
import os
import sys

import cairosvg
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from palette import dark as _palette          # noqa: E402

# ── 几何（1920×1080 下）────────────────────────────────
W = 1920
BAR_H = 84          # 底栏高度
TEXT_PX = 40        # 滚动文字字号
SPEED = 160.0       # 默认滚动速度 px/s。**由可读性决定，跟片长无关**
# 「整片正好滚一遍」只在一种情况下才需要凑：默认速度下片子差不多刚好一圈
# （也就是底栏内容长度和片长比较接近）。那种情况下差一点会让观众觉得"重复了一遍"，
# 才微调速度凑整。**其余情况一律用默认速度**——把速度跟片长绑死会矫枉过正：
# 条目多的时候算出来极慢、条目爬得没法读，条目少的时候又飞快。
FIT_BAND = (0.7, 1.6)   # 默认速度下的圈数落在这个区间，才微调成正好一圈
SEP = "　●　"       # 条目分隔符
PAD_L = 40          # 文字条左内边距

# ── 品牌词标块 ────────────────────────────────────────
WM_SVG = os.path.join(ROOT, "logo", "versions", "单色用-纯白.svg")   # 白字，配橙底
WM_H = 44           # 词标渲染高度（含内边距，实际字高约 39）
CHIP_PAD = 22       # 词标左右留白

# ── 字体 ──────────────────────────────────────────────
# 定稿：缝合像素字体（Fusion Pixel Font，OFL）。
# 它是方舟像素体同一作者的后续项目，以方舟为底、把缺字用其它开源像素字补齐。
#
# ⚠ **别用方舟像素体本身**：它 CJK 基本区只覆盖 18299/20992，缺 2000 多字，
#   其中包括「热」「旅」这种常用字。而且缺字时 PIL **不报错**，直接画成 .notdef
#   方框，会一路混进成片才被肉眼发现（用户就是先在成片里看到「热」是个方框）。
#   缝合版覆盖 19219，且与方舟在常用字上**逐像素完全一致**（实测 37 字全同），
#   换过去视觉上无感，只是把洞补上。
#
# ⚠ 像素字必须用**基础字号的整数倍**渲染，否则边缘发虚。
#   12px 基准 × 4 = 48px（实测 48px 抗锯齿 0%，40/44px 则高达 35%+）。
#
# 想换别的字体：从这些地址下载后放进 fonts/ 再改下面这张表——
#   得意黑   https://github.com/atelier-anchor/smiley-sans/releases
#   霞鹜文楷 https://github.com/lxgw/LxgwWenKai/releases
#   未来荧黑 https://github.com/welai/glow-sans/releases
#   霞鹜漫黑 https://github.com/lxgw/LxgwMarkerGothic/releases
NOTO_DIR = "/usr/share/fonts/opentype/noto"
FONTS_DIR = os.path.join(ROOT, "fonts")
BOOKMAN = "/usr/share/fonts/opentype/urw-base35/URWBookman-Demi.otf"
FONTS = {
    # (中文字体, 拉丁字体或None沿用中文, 强制字号或None)
    "pixel":  (f"{FONTS_DIR}/FusionPixel-12px-zh_hans.otf", None, 48),       # 定稿
    # 系统自带，仅作对照
    "serif-bold": (f"{NOTO_DIR}/NotoSerifCJK-Bold.ttc", None, None),
    "sans-bold":  (f"{NOTO_DIR}/NotoSansCJK-Bold.ttc", None, None),
    "mixed":      (f"{NOTO_DIR}/NotoSerifCJK-Regular.ttc", BOOKMAN, None),
}


def missing_chars(items, font_path):
    """
    列出条目里**字体没有的字**。

    PIL 遇到缺字不报错，直接画成 .notdef（方框），会一路混进成片才被肉眼发现。
    所以这里显式查一遍，让脚本自己喊出来 —— 别再让方框悄悄出片。
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return []
    cmap = TTFont(font_path).getBestCmap()
    seen, miss = set(), []
    for s in items:
        for ch in s:
            if ch <= " " or ch in seen:
                continue
            seen.add(ch)
            if ord(ch) not in cmap:
                miss.append(ch)
    return miss


def is_cjk(ch):
    return ord(ch) >= 0x2E80


def load_items(path):
    """
    读底栏条目。**唯一事实来源是这期的 `00-素材.md`**，别再单独维护一份条目文件
    （建过一份 `底栏条目.txt`，用户加了条目却没同步，白跑一轮）。

    - `.md`：取标题里含「底栏」的那一节
    - 其他：一行一条

    两种格式都跳过空行和 `#` 开头的行。
    """
    out, on = [], None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.lstrip().startswith("#"):
                on = "底栏" in line          # 只在「滚动底栏新闻条目」这类标题下才算数
                continue
            if on is False:
                continue
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if len(s) >= 3 and set(s) <= set("-*_"):
                continue          # markdown 分隔线（--- / *** / ___），不是条目
            out.append(s)
    return out


def fit_speed(period, chip_w, duration, speed=SPEED, band=FIT_BAND, width=W):
    """
    定滚动速度。

    默认就是 SPEED（可读性优先）。**只有**在"按默认速度滚，整片差不多正好一圈"
    的时候，才微调速度让它正好一圈 —— 那种情况下差一点观众会明显觉得重复或者看不全。

    底栏内容比片子长得多（条目很多）或短得多（条目很少）时，一律用默认速度：
    前者硬凑会慢到读不下去，后者硬凑会快到看不清。

    ⚠ 凑一圈的分母是**整条文字带的长度**，不是"周期减可视宽度"。
    因为底栏是从右边缘滚入的（正片开始时底栏是空的），
    要在这段时间里把整条带子推过去，走的距离就是整条带的长度。
    早期用"周期 − 可视宽度"算，导致带子最后那 1600 多像素永远没机会露脸。

    duration 传正片时长（底栏只在正片出现）；不传就返回默认速度。
    """
    if not duration or duration <= 0:
        return speed
    cycle = period / speed                      # 默认速度下一圈要多久
    laps = duration / cycle                     # 整片会滚几圈
    if band[0] <= laps <= band[1]:
        return period / duration                # 正好走完整条带子一遍
    return speed


def measure(d, text, cjk, lat):
    lat = lat or cjk
    return sum(d.textlength(ch, font=(cjk if is_cjk(ch) else lat)) for ch in text)


def draw_text(d, x, y, text, cjk, lat, fill):
    lat = lat or cjk
    for ch in text:
        f = cjk if is_cjk(ch) else lat
        d.text((x, y), ch, font=f, fill=fill, anchor="lm")
        x += d.textlength(ch, font=f)
    return x


def build(items, out_dir, font="serif-bold", bar_h=BAR_H, text_px=TEXT_PX, duration=None,
          speed=None):
    os.makedirs(out_dir, exist_ok=True)
    P = _palette()
    BG, ACC, TXT = P["bg"], P["accent"], P["text"]
    cjk_path, lat_path, size_override = FONTS[font]
    px = size_override or text_px

    _d = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    # ── 1) 底栏底（静态）：实底，不加装饰线
    bar = Image.new("RGBA", (W, bar_h), (0, 0, 0, 0))
    ImageDraw.Draw(bar).rectangle([0, 0, W, bar_h], fill=BG + (238,))
    bar.save(os.path.join(out_dir, "bar.png"))

    # ── 2) 品牌词标块（静态）：橙底 + 白色 GEONEWS，压在滚动文字之上
    tmp_png = os.path.join(out_dir, "_wm.png")
    cairosvg.svg2png(url=WM_SVG, write_to=tmp_png, output_height=WM_H * 2)  # 2x 渲染再降采样
    wm = Image.open(tmp_png).convert("RGBA")
    wm = wm.resize((int(wm.width * WM_H / wm.height), WM_H), Image.LANCZOS)
    os.remove(tmp_png)

    chip_w = wm.width + CHIP_PAD * 2
    chip = Image.new("RGBA", (chip_w, bar_h), (0, 0, 0, 0))
    ImageDraw.Draw(chip).rectangle([0, 0, chip_w - 1, bar_h], fill=ACC + (255,))
    chip.alpha_composite(wm, (CHIP_PAD, (bar_h - wm.height) // 2))
    chip.save(os.path.join(out_dir, "chip.png"))

    # ── 3) 滚动文字条
    miss = missing_chars(items, cjk_path)
    if miss:
        print(f"  ⚠ 字体缺字 {len(miss)} 个，会被画成方框：{''.join(miss)}")
        print(f"     字体 {os.path.basename(cjk_path)} —— 换覆盖面更全的（见 fonts/README.md）")

    cjk = ImageFont.truetype(cjk_path, px)
    lat = ImageFont.truetype(lat_path, px) if lat_path else None
    one = SEP + SEP.join(items)
    period = int(round(measure(_d, one, cjk, lat)))
    need = period + (W - chip_w) + 40
    copies = max(1, -(-need // period))
    sw = period * copies + PAD_L * 2

    strip = Image.new("RGBA", (sw, bar_h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(strip)
    for k in range(copies):
        draw_text(sd, PAD_L + k * period, bar_h // 2, one, cjk, lat, TXT + (255,))
    strip.save(os.path.join(out_dir, "strip.png"))

    # 速度：显式指定就直接用它（用户可要求固定值，如 120px/s）；否则按 fit_speed 定。
    speed = speed if speed else fit_speed(period, chip_w, duration)
    meta = dict(bar_h=bar_h, chip_w=chip_w, period=period, speed=speed,
                strip_w=sw, strip_h=bar_h, text_px=text_px, font=font,
                items=len(items), palette=P["key"], palette_label=P["label"],
                duration=duration, pad_l=PAD_L)
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"条目 {len(items)} 条　配色 {P['label']}　字体 {font}")
    print(f"底栏 {W}×{bar_h}　字号 {px}px　词标块宽 {chip_w}")
    print(f"周期 {period}px　文字条 {sw}×{bar_h}　循环一轮 {period / speed:.1f}s")
    if duration:
        print(f"速度 {speed:.1f}px/s（默认 {SPEED:g}，正片 {duration:.1f}s 下约 "
              f"{duration / (period / speed):.2f} 圈）")
    # 相位公式给的是"从右边缘滚入"的写法，和 build.py 里成片用的一致。
    # （早期这里印的是从左边起滚的旧公式，跟成片对不上，改掉。）
    print(f"\n  x = {W} - mod((t - 出现时刻) * {speed:g}, {period})")
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("items", help="条目来源：这期的 00-素材.md（取「底栏」那一节）或一行一条的文本")
    ap.add_argument("out_dir")
    ap.add_argument("--font", default="pixel", choices=list(FONTS))
    a = ap.parse_args()
    lines = load_items(a.items)
    if not lines:
        raise SystemExit("没有条目")
    build(lines, a.out_dir, a.font)
