# -*- coding: utf-8 -*-
"""GEONEWS 转场 v5 — 浅色转场（目录名是历史遗留）

基于 v3 的节奏（2.4s：进1.07s / 停0.73s / 出0.60s），只换配色。
配色不写在这里，取自 tools/palette.py 的 LIGHT 那套。

注意：浅色色的转场扫过深色素材时会「闪白」，本演示特意把上一条新闻设为深色，
      方便判断这个副作用能否接受。

输出（按用户要求，不生成 .mov）：
  转场演示.mp4        带两条模拟新闻的完整演示
  转场叠加_预览.png   APNG 动图，带透明，Windows「照片」可开
"""
import math, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
DUR, N = 2.4, 72
SKEW = 280

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, "frames")

# 配色统一从 tools/palette.py 取（浅色转场用 LIGHT 那套）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
from palette import light as _palette         # noqa: E402

_PAL = _palette()
BAND, ACCENT = _PAL["bg"], _PAL["accent"]
os.makedirs(FR, exist_ok=True)

LOGO_SRC = os.path.join(HERE, "..", "logo", "logo-light.png")   # 深色字，配浅底
logo = Image.open(LOGO_SRC).convert("RGBA")
LW, LH = logo.size
LOGO_W = 880.0

def ease(t): return t * t * (3 - 2 * t)
def lerp(a, b, t): return a + (b - a) * t

F_IN, F_HOLD = 32, 54
S_FULL = W + SKEW

def phase(f):
    if f < F_IN:   return "in",   f / F_IN
    if f < F_HOLD: return "hold", (f - F_IN) / (F_HOLD - F_IN)
    return "out", (f - F_HOLD) / (N - F_HOLD)

def band_shape(S):
    return [(S - W - 2 * SKEW, 0), (S - SKEW, 0), (S, H), (S - W - SKEW, H)]

def draw_band(layer, S, frame):
    d = ImageDraw.Draw(layer)
    d.polygon(band_shape(S), fill=BAND + (255,))
    for i in range(22):
        x = S - W - 2 * SKEW + i * 148 + (frame * 13) % 148
        d.line([(x, -120), (x + 340, H + 120)], fill=ACCENT + (16,), width=8)
    d.line([(S - SKEW, 0), (S, H)], fill=ACCENT + (255,), width=16)             # 前缘
    d.line([(S - W - SKEW, 0), (S - W, H)], fill=ACCENT + (120,), width=8)      # 后缘

def logo_layer(scale, cx, cy, rot, alpha):
    lw = max(2, int(LOGO_W * scale))
    lh = max(1, int(LH * (lw / LW)))
    lg = logo.resize((lw, lh), Image.LANCZOS)
    if abs(rot) > 0.05:
        lg = lg.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        lg.putalpha(lg.getchannel("A").point(lambda v: int(v * max(0.0, alpha))))
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    L.alpha_composite(lg, (int(cx - lg.width / 2), int(cy - lg.height / 2)))
    return L

def content(frame):
    ph, t = phase(frame)
    if ph == "in":
        e = ease(t)
        S = lerp(0, S_FULL, e)
        lscale, lrot, lalpha = lerp(0.68, 1.0, e), lerp(-13, 0, e), min(1.0, 0.20 + e * 1.15)
    elif ph == "hold":
        b = math.sin(t * math.pi) * 0.026
        S, lscale, lrot, lalpha = S_FULL, 1.0 + b, 0, 1.0
    else:
        e = ease(t)
        S = lerp(S_FULL, W + SKEW + (W + 2 * SKEW), e)
        lscale, lrot, lalpha = lerp(1.0, 0.72, e), lerp(0, 9, e), 1.0
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_band(layer, S, frame)
    cx = S - W / 2 - 1.5 * SKEW
    return Image.alpha_composite(layer, logo_layer(lscale, cx, H / 2, lrot, lalpha)), ph

def mock_news(path, title, sub, bg, ink):
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    f1 = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 170)
    f2 = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 62)
    d.text((W / 2, H / 2 - 80), title, font=f1, fill=ink, anchor="mm")
    d.text((W / 2, H / 2 + 80), sub, font=f2, fill=ink, anchor="mm")
    for i in range(9):
        d.rectangle([100 + i * 200, H - 300, 220 + i * 200, H - 170], outline=ink, width=4)
    d.text((100, 90), "画面示意 · 非真实内容", font=f2, fill=ink)
    im.save(path)

if __name__ == "__main__":
    # 上一条特意用深色，用来暴露「浅色转场扫过深色素材会闪白」
    mock_news(os.path.join(HERE, "news_a.png"), "上一条新闻（深色素材）",
              "浅色色带扫过这里时，会明显闪一下", (28, 34, 46), (238, 238, 240))
    mock_news(os.path.join(HERE, "news_b.png"), "下一条新闻",
              "色带扫出后露出这一段", (96, 78, 62), (255, 250, 244))
    A = Image.open(os.path.join(HERE, "news_a.png")).convert("RGBA")
    B = Image.open(os.path.join(HERE, "news_b.png")).convert("RGBA")

    for f in range(N):
        comp, ph = content(f)
        base = A if ph == "in" else B
        Image.alpha_composite(base, comp).convert("RGB").save(os.path.join(FR, f"f{f:04d}.png"))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "30", "-i", f"{FR}/f%04d.png",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                    os.path.join(HERE, "转场演示.mp4")], check=True)

    # 带透明叠加版 → 只出 APNG（不出 .mov）
    AF = os.path.join(HERE, "_a")
    os.makedirs(AF, exist_ok=True)
    for f in range(N):
        content(f)[0].save(os.path.join(AF, f"f{f:04d}.png"))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "30", "-i", f"{AF}/f%04d.png",
                    "-vf", "scale=960:-1", "-plays", "0", "-f", "apng", "-pix_fmt", "rgba",
                    os.path.join(HERE, "转场叠加_预览.png")], check=True)
    # 完整透明 PNG 序列，需要透明素材时用这个（编辑器里可直接导入序列）
    SF = os.path.join(HERE, "叠加序列")
    os.makedirs(SF, exist_ok=True)
    for f in range(N):
        content(f)[0].save(os.path.join(SF, f"转场_{f:04d}.png"))
    subprocess.run(["rm", "-rf", AF])
    print("done", N)
