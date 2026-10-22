#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
底栏 GIF —— 把 tools/ticker.py 生成的三层合成一段滚动的 GIF 预览。

用途：底栏改完参数后，出一张动图看实际效果（单看静态三层看不出滚动节奏）。

几何（1920×1080 下，来自 ticker.py）：
    正片 → 底栏底 → 滚动文字 → 词标块
底栏贴在画面最下沿，词标块压在滚动文字左侧。

GIF 体积的关键：**画面只有底栏那一小条在变**。
所以先合到 1920×1080（像素字原生锐利），再整体降到 1280×720；
存 GIF 时用「子矩形帧 + 共享调色板」，静态画面只写一次，
每帧只写底栏里真正变化的那几十行 —— 不然一张 11 秒的动图能到 70MB。

    python3 tools/ticker_gif.py 0930/00-素材.md -o 0930/out/底栏预览.gif \
        --bg 0930/assets/video/china.mp4 --at 6.0 --duration 134.3
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import ticker  # noqa: E402

W, H = 1920, 1080          # 合成用画布（与成片一致）
FONT = "pixel"             # 底栏定稿字体，见 ticker.FONTS


def _run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg 失败：\n" + "\n".join(p.stderr.strip().splitlines()[-20:]))


def background(video, at, dst):
    """抽一帧背景，按 build.py 同样的方式放大到 1920×1080（lanczos）。"""
    _run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", video, "-frames:v", "1",
          "-vf", f"scale={W}:{H}:flags=lanczos,setsar=1", "-y", dst])
    return dst


def make_gif(frames, out, fps):
    """帧序列 → GIF。用 PIL 的子矩形帧：只写与上一帧不同的那块矩形。"""
    tmp = tempfile.mkdtemp(prefix="tkgif_")
    try:
        for i, im in enumerate(frames):
            im.save(os.path.join(tmp, f"f_{i:04d}.png"))

        pal_png = os.path.join(tmp, "pal.png")
        _run(["ffmpeg", "-v", "error", "-framerate", str(fps),
              "-i", os.path.join(tmp, "f_%04d.png"),
              "-vf", "palettegen=max_colors=256:stats_mode=full", "-y", pal_png])

        # 所有帧必须共用同一张调色板，否则逐帧配色一变，
        # PIL 就判定「整张都不同」，子矩形优化失效、文件暴涨。
        pal = Image.open(pal_png).convert("P")
        base = frames[0].quantize(palette=pal)
        pframes = []
        for im in frames:
            pf = base.copy()
            # 底栏那一横条单独量化后贴上去，其余像素与 base 逐字节相同，
            # 于是 PIL 只把这一条写成「子矩形帧」。
            top = im.height - _bar_h[0]
            pf.paste(im.crop((0, top, im.width, im.height)).quantize(palette=pal), (0, top))
            pframes.append(pf)

        pframes[0].save(out, save_all=True, append_images=pframes[1:],
                        duration=int(round(1000 / fps)), loop=0,
                        optimize=True, disposal=1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_bar_h = [0]          # 合成画布上的底栏高度，make_gif 要用


def build(items, out, video, at, fps=12.5, width=1280, seconds=None, duration=None):
    work = tempfile.mkdtemp(prefix="tklayer_")
    try:
        meta = ticker.build(items, os.path.join(work, "layers"), font=FONT,
                            duration=duration)
        L = os.path.join(work, "layers")
        bar = Image.open(os.path.join(L, "bar.png")).convert("RGBA")
        chip = Image.open(os.path.join(L, "chip.png")).convert("RGBA")
        strip = Image.open(os.path.join(L, "strip.png")).convert("RGBA")

        BH, CHIP_W = meta["bar_h"], meta["chip_w"]
        PERIOD, SPEED = meta["period"], meta["speed"]
        _bar_h[0] = round(BH * width / W)          # 降采样后的底栏高度
        y0 = H - BH

        bg = Image.open(background(video, at, os.path.join(work, "bg.png"))).convert("RGB")

        # 一整个滚动周期 = 无缝循环。帧数取整会有不到 1 帧的误差（≈2px），肉眼看不出来。
        # 但条目多了周期会很长（8 条就 92.5s），整周期出 GIF 帧数爆掉，
        # 所以支持 --seconds 只截一段 —— 那段循环回来会有接缝，出图时说明就行。
        total = PERIOD / SPEED
        seamless = True
        if seconds and seconds < total:
            total, seamless = seconds, False
        n = max(1, int(round(total * fps)))
        frames = []
        for i in range(n):
            # 和 build.py 里成片的相位保持一致：正片开始那一刻带子在画面外（底栏是空的），
            # 之后从右往左滚。预览要是用别的相位，就失去"提前看效果"的意义了。
            x = W - (i * SPEED / fps) % PERIOD
            layer = Image.new("RGBA", (W, BH), (0, 0, 0, 0))
            layer.alpha_composite(bar, (0, 0))
            layer.alpha_composite(strip, (int(round(x)), 0))   # 负 x 自动裁左侧
            layer.alpha_composite(chip, (0, 0))
            frame = bg.copy()
            frame.paste(layer, (0, y0), layer)
            frames.append(frame.resize((width, round(width * 9 / 16)), Image.LANCZOS))

        make_gif(frames, out, fps)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    size = os.path.getsize(out)
    print(f"\n→ {out}")
    print(f"  {frames[0].width}×{frames[0].height} · {n} 帧 · {fps:g}fps · "
          f"{n / fps:.1f}s · {'一个滚动周期（无缝）' if seamless else '节选，循环会跳回'} · "
          f"{size / 1048576:.2f} MB")
    if not seamless:
        print(f"  整周期 {PERIOD / SPEED:.1f}s（{len(items)} 条），需要无缝就把 --seconds 去掉")
    return size


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("items", help="条目来源：这期的 00-素材.md（取「底栏」那一节）")
    ap.add_argument("-o", "--out", required=True, help="输出 gif")
    ap.add_argument("--bg", required=True, help="抽背景帧的录屏")
    ap.add_argument("--at", type=float, default=7.0, help="抽第几秒（默认 7.0）")
    ap.add_argument("--fps", type=float, default=12.5, help="默认 12.5（GIF 延迟能精确表示）")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--seconds", type=float, default=None,
                    help="只出这么多秒的节选。条目多、整周期太长时用；不去掉就是完整无缝循环")
    ap.add_argument("--duration", type=float, default=None,
                    help="正片时长，用来定滚动速度（跟成片保持一致）。不传就用默认速度")
    a = ap.parse_args()

    lines = ticker.load_items(a.items)
    if not lines:
        raise SystemExit("没有条目")
    d = os.path.dirname(os.path.abspath(a.out))
    if d:
        os.makedirs(d, exist_ok=True)
    build(lines, a.out, a.bg, a.at, a.fps, a.width, a.seconds, a.duration)
