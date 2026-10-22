#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GEONEWS 片尾生成器

把本期新闻对应的链接排成片尾。默认静止展示；内容超高时自动改为从下往上滚动。

设计：深色底（与片头一致）· 序号 + 标签 + 完整链接 · 末尾接品牌词标。

**每期独立**：链接文件与输出都放在该期目录下，互不覆盖。

用法：
  python3 build.py --links ../0918/05-片尾链接.md --out ../0918/out/片尾.mp4

链接文件格式：
  ## 文档1                      ← 标题行作为标签
  https://docs.google.com/...

  或同行：  文档1  https://...

  **无标签的链接行会挂在上一条下面**（用于"同一标签下并列多条链接"）：
  ## 杯赛报名
  https://docs.qq.com/doc/aaa
  https://docs.qq.com/doc/bbb     ← 不另起编号，紧挨着上一条
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

W, H, FPS = 1920, 1080, 30
MAX_DUR = 15.0
# 片尾时长一律 15s（用户 2026-09-30 定：**除非明说秒数，否则一律 15s**）。
# 链接少的时候不再缩短，多出来的时间摊到揭示过程里，避免画面死定。
TARGET_DUR = 15.0
FADE_OUT = 1.5          # 结尾整体淡出，让最后几秒也有动静
MAX_STRETCH = 4.0       # 内容偏少时，揭示过程最多拉长到几倍

# 配色统一从 tools/palette.py 取
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from palette import dark as _palette          # noqa: E402

_PAL = _palette()
NIGHT, EMBER, PAPER = _PAL["bg"], _PAL["accent"], _PAL["text"]
MUTE = _PAL["mute"]

F_LABEL = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
F_URL = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
F_NUM = "/usr/share/fonts/opentype/urw-base35/URWBookman-Light.otf"

WORDMARK = Image.open(os.path.join(ASSETS, "wordmark-c2.png")).convert("RGBA")

# 版面
MARGIN_X = 150
MARGIN_TOP = 60
MARGIN_BOT = 70
WM_GAP = 36              # 列表末尾与底部词标之间至少要留的空隙
SIZE_LABEL = 46
SIZE_URL = 34
SIZE_NUM = 40
SIZE_TITLE = 44
GAP_LABEL_URL = 8
GAP_ENTRY = 26
WM_CAP = 78
TITLE_GAP = 46

# 时间轴
LINE_START = 0.20
LINE_STAGGER = 0.40
LINE_FADE = 0.80
T_WM_DUR = 0.90
T_HOLD = 2.50
PAUSE_BEFORE_WM = 0.40


# ---------------------------------------------------------------- 解析

def parse_links(path):
    """
    返回 [{"label": str, "urls": [str, ...]}, ...]

    无标签、也无新标题的链接行，视为上一条的并列链接，挂到上一条的 urls 里
    （不另起序号）。
    """
    entries, cur = [], None
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("<!--"):
            continue
        if s.startswith("#"):
            cur = s.lstrip("#").strip()
            continue
        m = re.search(r"https?://\S+", s)
        if not m:
            continue
        lab = re.sub(r"[：:]\s*$", "", s[:m.start()].strip())
        if not lab and not cur and entries:
            entries[-1]["urls"].append(m.group(0))       # 并列链接
        else:
            entries.append({"label": lab or (cur or ""), "urls": [m.group(0)]})
        cur = None
    return entries


# ---------------------------------------------------------------- 排版

def fit_url_size(all_urls, avail_w, hi=44, lo=20):
    """选一个尽量大、但最长链接仍放得下的字号。"""
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    longest = max(all_urls, key=len)
    for s in range(hi, lo - 1, -1):
        if d.textlength(longest, font=ImageFont.truetype(F_URL, s)) <= avail_w:
            return s
    return lo


def layout(entries, title):
    avail_w = W - 2 * MARGIN_X
    all_urls = [u for e in entries for u in e["urls"]]
    u = fit_url_size(all_urls, avail_w)

    f_lab = ImageFont.truetype(F_LABEL, SIZE_LABEL)
    f_url = ImageFont.truetype(F_URL, u)
    f_num = ImageFont.truetype(F_NUM, SIZE_NUM)
    f_tit = ImageFont.truetype(F_LABEL, SIZE_TITLE)

    lh_lab = int(SIZE_LABEL * 1.25)
    lh_url = int(u * 1.35)
    entry_hs = [lh_lab + GAP_LABEL_URL + len(e["urls"]) * lh_url for e in entries]
    block_h = sum(entry_hs) + (len(entries) - 1) * GAP_ENTRY

    tit_h = int(SIZE_TITLE * 1.3) if title else 0
    head_h = tit_h + TITLE_GAP if title else 0
    content_h = head_h + block_h

    # 竖直排布：内容排布在「上边距」到「底部词标之上」这块带里，并在带内居中。
    # 早先的公式把上下边距重复计入 need，导致明明放得下却判定要滚动。
    wm_top = H - MARGIN_BOT - WM_CAP
    band = (wm_top - WM_GAP) - MARGIN_TOP
    fits = content_h <= band
    y0 = MARGIN_TOP + max(0, (band - content_h) / 2.0)
    need = MARGIN_TOP + content_h + WM_GAP + WM_CAP + MARGIN_BOT

    return dict(url_size=u, f_lab=f_lab, f_url=f_url, f_num=f_num, f_tit=f_tit,
                lh_lab=lh_lab, lh_url=lh_url, entry_hs=entry_hs,
                block_h=block_h, tit_h=tit_h, head_h=head_h,
                content_h=content_h, y0=y0, band=band, wm_top=wm_top,
                needs_scroll=not fits, need=need)


def make_bg():
    img = Image.new("RGBA", (W, H), NIGHT + (255,))
    glow = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(glow)
    for i in range(26):
        r = 940 - i * 34
        a = int(9 * (i / 26.0) ** 1.6)
        d.ellipse([W / 2 - r * 1.45, H / 2 - r, W / 2 + r * 1.45, H / 2 + r], fill=a)
    glow = glow.filter(__import__("PIL.ImageFilter", fromlist=["ImageFilter"]).GaussianBlur(80))
    tint = Image.merge("RGBA", (Image.new("L", (W, H), 44),
                                Image.new("L", (W, H), 62),
                                Image.new("L", (W, H), 90), glow))
    return Image.alpha_composite(img, tint)


BG = make_bg()


def line_alpha(t, idx, stagger):
    if stagger <= 0:
        return 1.0
    return min(1.0, max(0.0, (t - LINE_START - stagger * idx) / LINE_FADE))


def draw_entry(layer, i, e, x, y, L, t, line0, stagger):
    """
    画一条：序号 + 标签，下面依次是各条链接（并列的链接紧挨着排）。

    注意：ImageDraw 不做 alpha 混合——它把 RGBA 值原样写进像素，
    之后 convert("RGB") 会丢掉 alpha，文字就变成满亮度。
    所以必须画在独立透明层上，再 alpha_composite。
    """
    a_lab = line_alpha(t, line0, stagger)
    a_urls = [line_alpha(t, line0 + 1 + k, stagger) for k in range(len(e["urls"]))]
    if a_lab <= 0.004 and max(a_urls or [0]) <= 0.004:
        return
    tmp = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)

    def A(c, a):
        return c + (max(0, min(255, int(round(255 * a)))),)

    num = f"{i:02d}"
    nw = d.textlength(num, font=L["f_num"])
    if a_lab > 0.004:
        d.text((x, y), num, font=L["f_num"], fill=A(EMBER, a_lab), anchor="lt")
        if e["label"]:
            d.text((x + nw + 22, y - 2), e["label"], font=L["f_lab"],
                   fill=A(PAPER, a_lab), anchor="lt")
    uy0 = y + L["lh_lab"] + GAP_LABEL_URL
    for k, (url, au) in enumerate(zip(e["urls"], a_urls)):
        if au > 0.004:
            d.text((x + nw + 22, uy0 + k * L["lh_url"]), url,
                   font=L["f_url"], fill=A(MUTE, au), anchor="lt")
    layer.alpha_composite(tmp)


def render_credits(entries, title, out, scroll_speed=110.0, target=TARGET_DUR):
    # 这些揭示节奏常量在"内容偏少"时要整体拉长，所以得能改（见下面的 k）
    global LINE_FADE, LINE_STAGGER, PAUSE_BEFORE_WM, T_HOLD
    L = layout(entries, title)
    n_urls = sum(len(e["urls"]) for e in entries)
    print(f"{len(entries)} 条 / {n_urls} 个链接　链接字号 {L['url_size']}px　"
          f"内容高 {L['need']}px / 可用 {H}px　→ "
          f"{'滚动' if L['needs_scroll'] else '静止'}")

    # ---- 时间轴 ----
    if not L["needs_scroll"]:
        stagger = LINE_STAGGER
        scroll_px, scroll_t, t_in = 0.0, 0.0, 0.0
        n_lines = sum(1 + len(e["urls"]) for e in entries)
        content_end = LINE_START + stagger * (n_lines - 1) + LINE_FADE
        t_wm = content_end + PAUSE_BEFORE_WM
    else:
        stagger = 0.0                 # 滚动模式靠滚入揭示，不再逐行淡入
        t_in = 1.0
        start_top = float(H) + 20.0
        end_top = max(float(MARGIN_TOP), (H - L["block_h"]) / 2.0)
        scroll_px = start_top - end_top
        scroll_t = max(6.0, scroll_px / scroll_speed)
        t_wm = t_in + scroll_t + PAUSE_BEFORE_WM

    total = t_wm + T_WM_DUR + T_HOLD
    if total > MAX_DUR:               # 内容太多：压滚动速度，上限 15s
        over = total - MAX_DUR
        if L["needs_scroll"]:
            scroll_t = max(3.0, scroll_t - over)
            t_wm = t_in + scroll_t + PAUSE_BEFORE_WM
        else:
            t_wm = max(3.0, t_wm - over)
        total = t_wm + T_WM_DUR + T_HOLD
    if total < target:
        # 内容偏少：多出来的时间**摊到揭示过程里**，让十几秒里画面一直在动，
        # 而不是前 7 秒演完、后 8 秒干等。用户明确要求"屏幕不要一直死定着"。
        room = max(0.0, target - T_WM_DUR - T_HOLD - FADE_OUT)
        k = min(MAX_STRETCH, room / t_wm) if t_wm > 0 else 1.0
        if k > 1.0:
            LINE_FADE *= k
            LINE_STAGGER *= k
            PAUSE_BEFORE_WM *= k
            t_in *= k
            scroll_t *= k
            t_wm *= k
    # 时长是硬指标：揭示过程拉长到头还差，就补在停留时间上
    T_HOLD = max(T_HOLD, target - t_wm - T_WM_DUR - FADE_OUT)
    total = t_wm + T_WM_DUR + T_HOLD + FADE_OUT

    N = int(total * FPS)
    print(f"时长 {total:.1f}s（{N} 帧）　目标 {target:.1f}s　词标 {t_wm:.1f}s 淡入"
          + (f"　滚动 {scroll_t:.1f}s / {scroll_px:.0f}px" if L["needs_scroll"] else "")
          + f"　结尾 {FADE_OUT:.1f}s 淡出")

    tmp = os.path.join(HERE, "_frames")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)   # 残留旧帧会让成片时长出错
    os.makedirs(tmp, exist_ok=True)

    if not L["needs_scroll"]:
        y0 = L["y0"]
        block_top = y0 + L["head_h"]
    else:
        block_top = float(H) + 20.0

    _d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    nw_max = max(_d.textlength(f"{i:02d}", font=L["f_num"])
                 for i in range(1, len(entries) + 1))
    line_w = max(nw_max + 22 + _d.textlength(u, font=L["f_url"])
                 for e in entries for u in e["urls"])
    x = (W - line_w) / 2

    for f in range(N):
        t = f / FPS
        # 内容画在独立透明层上，最后整体套一个淡出包络再合到底色上 ——
        # 直接画在底色上的话没法整体淡出（底色会被一起淡掉）。
        content = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        if L["needs_scroll"]:
            if t < t_in:
                off = 0.0
            elif t < t_in + scroll_t:
                off = -scroll_px * (t - t_in) / scroll_t
            else:
                off = -scroll_px
            bt = block_top + off
        else:
            bt = block_top

        if title and not L["needs_scroll"]:
            a = line_alpha(t, 0, stagger)
            if a > 0.004:
                tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(tl).text(
                    (W / 2, y0 + L["tit_h"] / 2), title, font=L["f_tit"],
                    fill=PAPER + (max(0, min(255, int(210 * a))),), anchor="mm")
                content.alpha_composite(tl)

        ey = bt
        for i, e in enumerate(entries, 1):
            if -100 < ey < H + 100:
                draw_entry(content, i, e, x, ey, L, t, (i - 1) * 2, stagger)
            ey += L["entry_hs"][i - 1] + GAP_ENTRY

        # 词标：等内容全部出完后才淡入，之后固定在底部不再动
        wa = min(1.0, max(0.0, (t - t_wm) / T_WM_DUR))
        if wa > 0.004:
            wmr = WORDMARK.resize(
                (int(WORDMARK.width * (WM_CAP / WORDMARK.height)), WM_CAP),
                Image.LANCZOS)
            wmr.putalpha(wmr.getchannel("A").point(lambda v: int(v * wa)))
            content.alpha_composite(wmr, (int(W / 2 - wmr.width / 2),
                                          int(H - MARGIN_BOT - WM_CAP)))

        ga = min(1.0, max(0.0, (total - t) / FADE_OUT)) if FADE_OUT > 0 else 1.0
        if ga < 0.999:
            content.putalpha(content.getchannel("A").point(lambda v: int(v * ga)))

        Image.alpha_composite(BG.copy(), content).convert("RGB").save(
            os.path.join(tmp, f"f{f:04d}.png"))

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-framerate", str(FPS), "-i", os.path.join(tmp, "f%04d.png"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
    print("成片:", out, f"  {total:.1f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--links", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="本期链接")
    ap.add_argument("--duration", type=float, default=TARGET_DUR,
                    help=f"片尾时长（秒）。默认 {TARGET_DUR:g}，不指定就一律用默认值")
    a = ap.parse_args()
    ents = parse_links(a.links)
    if not ents:
        raise SystemExit(f"没解析出链接：{a.links}")
    render_credits(ents, a.title, a.out, target=a.duration)
