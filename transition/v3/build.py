# -*- coding: utf-8 -*-
"""GEONEWS 转场 v2 — 横扫遮罩式（真正的转场）

色带从左扫入 → 完全盖住上一条 → 停顿（logo 居中）→ 右移退出、露出下一条

关键做法：色带完全盖住画面的那一刻，把底层从上一条切成下一条（此时全遮住，
切换不可见），所以退出时露出的自然是下一条。

输出：
  转场演示.mp4    带两条模拟新闻的完整演示（先看这个）
  转场叠加.mov    带 Alpha 的叠加版（自己叠在片子上）
"""
import math, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
DUR, N = 2.4, 72
SKEW = 280

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, "frames")
os.makedirs(FR, exist_ok=True)

# 配色统一从 tools/palette.py 取（深色转场用 DARK 那套）
# 注意：这里必须在 HERE 定义之后——导入路径要用到它。
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
from palette import dark as _palette          # noqa: E402

_PAL = _palette()
NIGHT, EMBER = _PAL["bg"], _PAL["accent"]

logo = Image.open(os.path.join(HERE, "..", "logo", "logo-dark.png")).convert("RGBA")
LW, LH = logo.size
LOGO_W = 880.0

def ease(t): return t * t * (3 - 2 * t)      # smoothstep：起步慢、收尾也慢
def lerp(a, b, t): return a + (b - a) * t

F_IN, F_HOLD = 32, 54            # 扫入结束帧 / 停顿结束帧  → 进1.07s 停0.73s 出0.60s
S_FULL = W + SKEW                # 完全覆盖时，色带右缘的位置

def phase(f):
    if f < F_IN:   return "in",   f / F_IN
    if f < F_HOLD: return "hold", (f - F_IN) / (F_HOLD - F_IN)
    return "out", (f - F_HOLD) / (N - F_HOLD)

def band_shape(S):
    """斜边色带。S=W+SKEW 时正好盖满整屏（含左下角）。"""
    return [(S - W - 2 * SKEW, 0), (S - SKEW, 0), (S, H), (S - W - SKEW, H)]

def draw_band(layer, S, frame):
    d = ImageDraw.Draw(layer)
    d.polygon(band_shape(S), fill=NIGHT + (255,))
    for i in range(22):
        x = S - W - 2 * SKEW + i * 148 + (frame * 13) % 148
        d.line([(x, -120), (x + 340, H + 120)], fill=EMBER + (30,), width=6)
    d.line([(S - SKEW, 0), (S, H)], fill=EMBER + (238,), width=16)              # 前缘
    d.line([(S - W - SKEW, 0), (S - W, H)], fill=EMBER + (110,), width=8)      # 后缘

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
    mock_news(os.path.join(HERE, "news_a.png"), "上一条新闻", "这一段会被色带盖住",
              (232, 226, 214), (28, 30, 38))
    mock_news(os.path.join(HERE, "news_b.png"), "下一条新闻", "色带扫出后露出这一段",
              (176, 46, 34), (255, 246, 240))
    A = Image.open(os.path.join(HERE, "news_a.png")).convert("RGBA")
    B = Image.open(os.path.join(HERE, "news_b.png")).convert("RGBA")

    for f in range(N):
        comp, ph = content(f)
        base = A if ph == "in" else B      # 全遮住时切换底层，切换不可见
        out = Image.alpha_composite(base, comp)
        out.convert("RGB").save(os.path.join(FR, f"f{f:04d}.png"))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "30", "-i", f"{FR}/f%04d.png",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                    os.path.join(HERE, "转场演示.mp4")], check=True)

    AF = os.path.join(HERE, "_a")
    os.makedirs(AF, exist_ok=True)
    for f in range(N):
        comp, _ = content(f)
        comp.save(os.path.join(AF, f"f{f:04d}.png"))
    # APNG：Windows「照片」可直接打开，且保住透明通道（半尺寸，仅供查看）
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "30", "-i", f"{AF}/f%04d.png",
                    "-vf", "scale=960:-1", "-plays", "0", "-f", "apng", "-pix_fmt", "rgba",
                    os.path.join(HERE, "转场叠加_预览.png")], check=True)
    # 完整透明 PNG 序列 —— 成片实际用的就是它（编辑器可直接导入序列）
    SF = os.path.join(HERE, "叠加序列")
    os.makedirs(SF, exist_ok=True)
    for f in range(N):
        content(f)[0].save(os.path.join(SF, f"转场_{f:04d}.png"))
    subprocess.run(["rm", "-rf", AF])
    print("done", N)
