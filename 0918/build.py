#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
0918 成片拼装

流程：
  pass1  按口播裁剪各片段 → 放大到成片尺寸 → 插入图片卡 → concat 拼接（保留原声）
  pass2  叠左上角水印 → 在 4 个交界叠转场 → 输出

裁剪规则：每段按语音起止裁掉前后无口播部分，各留 0.5s 缓冲；
          有转场的交界再各加 0.5s（即 1.0s）。

转场放置：色带第 32 帧完全盖住画面，把这一帧对准切点，视频总长不变。

用法：
  python3 build.py                  # 1920x1080
  python3 build.py --draft          # 1280x720 快速预览
  python3 build.py --only pass1     # 只跑第一段
"""

import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ASSETS = os.path.join(HERE, "assets", "video")
CARDS = os.path.join(HERE, "_build", "cards")
WATERMARK = os.path.join(ROOT, "logo", "视频水印", "GEONEWS-水印-B版-200px.png")
DARK_SEQ = os.path.join(ROOT, "transition", "v3", "叠加序列", "转场_%04d.png")
LIGHT_SEQ = os.path.join(ROOT, "transition", "v5-暖米", "叠加序列", "转场_%04d.png")

# (文件, 缓冲入, 缓冲出, 插图时间(原片秒)|None, 卡片名|None)
SEGMENTS = [
    ("段1 阿拉斯加", [
        ("阿拉斯加红皮卡1.mp4", 0.5, 0.5, None, None),
        ("阿拉斯加红皮卡2.mp4", 0.5, 0.5, None, None)], None),
    ("段2 育空", [
        ("育空.mp4", 0.5, 1.0, None, None)], "dark"),
    ("段3 文档", [
        ("文档1.mp4", 1.0, 0.5, None, None),
        ("文档2（1）.mp4", 0.5, 0.5, None, None),
        ("文档2补充说明.mp4", 0.5, 0.5, None, None),
        ("文档2（2）.mp4", 0.5, 0.5, None, None),
        ("文档3.mp4", 0.5, 1.0, 22.14, "卡片-宇科君")], "dark"),
    ("段4 AWW", [
        ("AWW.mp4", 1.0, 1.0, 12.27, "卡片-奶茶")], "dark"),
    ("段5 赛事", [                      # ← 已调换：先猫猫杯，后极光杯
        ("猫猫杯.mp4", 1.0, 0.5, None, None),
        ("极光杯.mp4", 0.5, 1.0, None, None)], "light"),
    ("段6 geoguide", [
        ("geoguide.mp4", 1.0, 0.5, None, None)], None),
]

TR_HIT = 32
FPS = 30
# 水印位置用「占输出尺寸的比例」而不是固定像素。
# 原因：素材左右各带 62px 黑边（1280 宽下占 4.84%，上下没有），
# 这个黑边会跟着素材一起放大到 1080p（=93px）。
# 固定像素值会导致 720p 下勉强clear、1080p 下又被黑边压住。
WM_X_FRAC, WM_Y_FRAC = 0.0730, 0.0481
SIL_THR, SIL_D = -40, 0.25

# 片头 / 片尾（由 intro/ 和 outro/ 生成）
INTRO = os.path.join(ROOT, "intro", "片头-A.mp4")
OUTRO = os.path.join(HERE, "out", "片尾.mp4")


def dur(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path],
                       stdout=subprocess.PIPE, text=True).stdout.strip()
    return float(o or 0)


def stream_durs(path):
    """分别取视频流与音频流长度。两者常常不等——视频往往比录音长。"""
    def one(sel):
        o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", sel,
                            "-show_entries", "stream=duration",
                            "-of", "default=nw=1:nk=1", path],
                           stdout=subprocess.PIPE, text=True).stdout.strip().splitlines()
        try:
            return float(o[0])
        except (IndexError, ValueError):
            return None
    return one("v"), one("a")


def speech_bounds(path):
    """
    返回 (首段语音起点, 末段语音终点, 视频流长度)。
    注意：语音边界来自**音频流**，裁剪上界用**视频流长度**。
    早期版本用 format duration 当上界，导致视频尾部多出的空白剪不掉。
    """
    vd, ad = stream_durs(path)
    A = ad or vd                      # 音频流长度，用于截断静音区间
    V = vd or ad                      # 视频流长度，裁剪上界
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path,
                        "-af", f"silencedetect=n={SIL_THR}dB:d={SIL_D}", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    ss = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", r)]
    se = [float(x) for x in re.findall(r"silence_end:\s*(-?[\d.]+)", r)]
    sil = []
    for i, s in enumerate(ss):
        e = se[i] if i < len(se) else A
        sil.append((max(0.0, s), min(A, e)))
    sp, cur = [], 0.0
    for s, e in sil:
        if s > cur + 1e-6:
            sp.append((cur, s))
        cur = max(cur, e)
    if cur < A - 1e-6:
        sp.append((cur, A))
    if not sp:
        return 0.0, A, V
    return sp[0][0], sp[-1][1], V


def run(cmd):
    t = time.time()
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg 失败：\n" + "\n".join(p.stderr.strip().splitlines()[-25:]))
    return time.time() - t


def has_audio(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=index", "-of", "csv=p=0", path],
                       stdout=subprocess.PIPE, text=True).stdout.strip()
    return bool(o)


def ensure_audio(src, dst):
    """
    片头/片尾是无声的。直接与有声的正片 concat 会让音频整体错位
    （视频多了 7s+9s，音频没有对应段），所以补一条等长静音轨。
    """
    if has_audio(src):
        return src
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", src, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         "-shortest", "-movflags", "+faststart", dst])
    return dst


def build(draft=False, only=None, full=False):
    W, H = (1280, 720) if draft else (1920, 1080)
    # final 用 fast（不是 medium）：素材本来就是 720p 放大到 1080p，
    # 平板区域多，fast 与 medium 的观感差别看不出来，但耗时可降三分之一，
    # 能确保在单次调用时限内跑完。
    preset1, crf1 = ("ultrafast", 18) if draft else ("veryfast", 16)
    preset2, crf2 = ("veryfast", 20) if draft else ("fast", 19)

    out_dir = os.path.join(HERE, "out")
    tmp = os.path.join(HERE, "_build")
    os.makedirs(out_dir, exist_ok=True)

    # ---------- 规划：算裁剪点与切点 ----------
    plan, cut, cum = [], {}, 0.0
    print(f"{'片段':<22}{'原长':>7}{'裁入':>7}{'裁后':>7}  插图", flush=True)
    print("-" * 62, flush=True)
    for sname, clips, _kind in SEGMENTS:
        for f, bin_, bout, ins, card in clips:
            p = os.path.join(ASSETS, f)
            a, b, V = speech_bounds(p)          # b=语音末（音频），V=视频流长
            s = max(0.0, a - bin_)
            e = min(V, b + bout)                # 尾部多余画面在这里被剪掉
            keep = e - s
            ins_t = None
            if ins is not None and ins >= s:
                ins_t = ins - s          # 换算到裁剪后的时间轴
            plan.append(dict(file=p, name=f[:-4], s=s, e=e, keep=keep,
                             ins=ins_t, card=card, D=V))
            note = f"{card} @{ins_t:.2f}s" if ins_t is not None else ""
            print(f"{f[:-4]:<22}{V:>6.1f}s{s:>6.2f}s{keep:>6.2f}s  {note}", flush=True)
            cum += keep
        cut[sname] = cum
    total = cum
    print(f"\n裁剪后总长 {total:.2f}s ({int(total//60)}:{total%60:04.1f})", flush=True)
    for sname, _clips, kind in SEGMENTS:
        if kind:
            print(f"  {sname:<14} 结束 {cut[sname]:7.2f}s ← 转场({kind})", flush=True)

    # ---------- pass1 ----------
    # 做法：逐段渲染成独立文件（用 -t 锁定精确时长），再用 concat 分离器无损拼接。
    # 早期用单条 filter_complex 做 v=1:a=1 concat，视频比音频多出上百帧、
    # 总长漂移 4 秒，且图片卡会串到下一段。分段渲染后每段时长可控可验。
    seq_dir = os.path.join(tmp, "seg")
    base = os.path.join(tmp, f"base_{'draft' if draft else 'final'}.mp4")
    if only != "pass2":
        os.makedirs(seq_dir, exist_ok=True)
        segs = []
        for i, c in enumerate(plan):
            out = os.path.join(seq_dir, f"{i:02d}_{c['name']}.mp4")
            vf = (f"[0:v]trim=start={c['s']:.3f}:end={c['e']:.3f},setpts=PTS-STARTPTS,"
                  f"scale={W}:{H}:flags=lanczos,setsar=1,fps={FPS}[vr]")
            af = (f"[0:a]atrim=start={c['s']:.3f}:end={c['e']:.3f},asetpts=PTS-STARTPTS,"
                  f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[ao]")
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-i", c["file"]]
            if c["ins"] is not None and c["card"]:
                cardp = os.path.join(CARDS, c["card"] + ".png")
                cdur = c["keep"] - c["ins"]
                cmd += ["-loop", "1", "-framerate", str(FPS),
                        "-t", f"{cdur:.3f}", "-i", cardp]
                fc = (f"{vf};{af};"
                      f"[vr]trim=0:{c['ins']:.3f},setpts=PTS-STARTPTS[v1];"
                      f"[1:v]scale={W}:{H},setsar=1,fps={FPS},"
                      f"trim=duration={cdur:.3f},setpts=PTS-STARTPTS[v2];"
                      f"[v1][v2]concat=n=2:v=1:a=0[vo]")
            else:
                fc = f"{vf};{af};[vr]null[vo]"
            cmd += ["-filter_complex", fc, "-map", "[vo]", "-map", "[ao]",
                    "-t", f"{c['keep']:.3f}",
                    "-c:v", "libx264", "-preset", preset1, "-crf", str(crf1),
                    "-pix_fmt", "yuv420p", "-r", str(FPS),
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", out]
            run(cmd)
            segs.append(out)
        print(f"\n[pass1] 逐段渲染 {len(segs)} 段 …", flush=True)
        items = list(segs)
        if full:
            # 片头/片尾本身没有音轨。直接 concat 会让音频整体错位
            # （视频多了 7s + 9s，音频没有对应段），所以先补上等长静音轨。
            items = [ensure_audio(INTRO, os.path.join(tmp, "intro.mp4"))] + items \
                + [ensure_audio(OUTRO, os.path.join(tmp, "outro.mp4"))]
        lst = os.path.join(tmp, "concat.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for sP in items:
                f.write(f"file '{os.path.abspath(sP)}'\n")
        print(f"[pass1] 无损拼接 {len(items)} 段 …", flush=True)
        t0 = time.time()
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", lst,
             "-c", "copy", "-movflags", "+faststart", base])
        print(f"   完成，用时 {time.time()-t0:.0f}s", flush=True)
    else:
        print(f"\n[pass1] 跳过", flush=True)

    if only == "pass1":
        return base

    # ---------- pass2 ----------
    final = os.path.join(out_dir,
                         f"GeoNews-0918-{'draft-720p' if draft else '1080p'}"
                         f"{'-full' if full else ''}.mp4")
    # 片头若在，正片整体后移；水印只盖正片，不盖片头片尾
    intro_dur = dur(INTRO) if full else 0.0
    main_dur = cut[SEGMENTS[-1][0]]
    inputs = ["-i", base, "-i", WATERMARK]
    tr_meta = []

    if full:
        # 第 5 处：片头 → 第一幕。切点在片头结束处，用深色板
        # （片头是夜蓝深底，阿拉斯加偏中，按"偏深就用深色板"规则）
        t_cut = intro_dur
        tr_meta.append(("片头→正片", "dark", t_cut, t_cut - TR_HIT / FPS, None))
    for sname, _clips, kind in SEGMENTS:
        if not kind:
            continue
        t_cut = intro_dur + cut[sname]
        tr_meta.append((sname, kind, t_cut, t_cut - TR_HIT / FPS, None))
    if full:
        # 第 6 处：正片 → 片尾。正片末段是 geoguide（白底），片尾是夜蓝深底，
        # 不遮一下会从亮直接跳到黑，所以也走深色板。
        t_cut = intro_dur + main_dur
        tr_meta.append(("正片→片尾", "dark", t_cut, t_cut - TR_HIT / FPS, None))

    for i, (label, kind, t_cut, t_start, _) in enumerate(tr_meta):
        seq = DARK_SEQ if kind == "dark" else LIGHT_SEQ
        inputs += ["-framerate", str(FPS), "-itsoffset", f"{t_start:.4f}", "-i", seq]
        tr_meta[i] = (label, kind, t_cut, t_start, 2 + i)

    wx = int(W * WM_X_FRAC)
    wy = int(H * WM_Y_FRAC)
    if full:
        # 水印只在正片出现（片头有品牌动画、片尾自带词标，不必再加）
        wm_enable = f":enable='between(t,{intro_dur:.3f},{intro_dur + main_dur:.3f})'"
    else:
        wm_enable = ""
    fc2 = [f"[0:v][1:v]overlay={wx}:{wy}{wm_enable}[w0]"]
    prev = "w0"
    for (label, kind, t_cut, t_start, iidx) in tr_meta:
        nxt = f"w{iidx-1}"
        fc2.append(f"[{prev}][{iidx}:v]overlay=eof_action=pass:format=auto[{nxt}]")
        prev = nxt
    cmd2 = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + inputs + [
        "-filter_complex", ";".join(fc2), "-map", f"[{prev}]", "-map", "0:a",
        "-c:v", "libx264", "-preset", preset2, "-crf", str(crf2),
        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", final]
    print(f"[pass2] 水印 @({wx},{wy}) + {len(tr_meta)} 处转场 …", flush=True)
    for label, kind, t_cut, t_start, _ in tr_meta:
        print(f"   {label:<14} 切点 {t_cut:7.2f}s  转场 {t_start:7.2f}s 起（{kind}）", flush=True)
    print(f"   完成，用时 {run(cmd2):.0f}s", flush=True)
    print(f"\n输出: {final}", flush=True)
    return final


if __name__ == "__main__":
    argv = sys.argv[1:]
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    build(draft="--draft" in argv, only=only, full="--full" in argv)
