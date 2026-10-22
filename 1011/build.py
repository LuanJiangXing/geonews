#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GEONEWS 成片拼装（每期一份，从 templates/_project/ 复制后改 SEGMENTS）

流程：
  pass1  按裁剪点切片 → 放大到成片尺寸 → 插图片卡 → 必要时拼片头片尾
  pass2  叠底栏/水印 → 在各交界叠转场 → 输出

**必须分两段跑**：一次跑完 1080p 会超过工具调用时限、进程被杀、产出残缺文件。
  python3 build.py --full --only pass1
  python3 build.py --full --only pass2

裁剪规则：**整段静音则不裁**；大部分有口播才按语音起止裁掉首尾
          （判据是口播覆盖率，门槛 NARRATION_COVER，不是首尾跨度）。
          留 0.5s 缓冲，转场交界处留 1.0s。

水印与底栏默认都不叠 —— 成片保持干净，底栏单独出。详见 WORKFLOW.md 的硬规矩。

转场放置：色带第 32 帧完全盖住画面，把这一帧对准切点，视频总长不变。

用法：
  python3 build.py                  # 只正片，1920x1080
  python3 build.py --full           # 片头 + 正片 + 片尾
  python3 build.py --draft          # 1280x720 快速预览
  python3 build.py --only pass1     # 只跑第一段
  python3 build.py --only pass2 --ticker    # 烘焙底栏（默认不用）
  python3 build.py --wm             # 加回左上角水印（默认不加）
  python3 build.py --bar-only [--bar-span 秒]   # 只出底栏叠加层
"""

import os
import re
import subprocess
import sys
import time

from PIL import Image          # 只给 bar_only 裁单程带子用

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ASSETS = os.path.join(HERE, "assets", "video")
CARDS = os.path.join(HERE, "_build", "cards")
WATERMARK = os.path.join(ROOT, "logo", "视频水印", "GEONEWS-水印-B版-200px.png")
DARK_SEQ = os.path.join(ROOT, "transition", "v3", "叠加序列", "转场_%04d.png")
LIGHT_SEQ = os.path.join(ROOT, "transition", "v5-暖米", "叠加序列", "转场_%04d.png")
IMAGES = os.path.join(HERE, "assets", "image")

# 图片段：剪辑表里给一张图（.png/.jpg…）就是「图片段」——整张图按比例缩放居中，
# 不裁不拉伸，底色用 IMG_BG（= 片头片尾那套配色的深色底）。停留 IMG_HOLD 秒。
# 音轨补等长静音（用户口播自己剪，脚本只管拼接对齐）。
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
IMG_BG = 0x0E0E11       # 净黑（palette DARK 的底色）
IMG_HOLD = 11.0         # 图片停留秒数（用户定 10–12s）

# (文件, 缓冲入, 缓冲出, 插图时间(原片秒)|None, 卡片名|None)
#   缓冲入/出 = 按语音起止裁剪时前后各留多少秒（0.5 常规，转场处 1.0）
#   插图时间   = 在这一段第几秒切成图片卡（原片时间轴，脚本自动换算到裁剪后）
#   卡片名     = _build/cards/<卡片名>.png，需外部先生成
#   图片文件   = 整条当静帧；第 6 个元素 = 停留秒数（不填用 IMG_HOLD 默认 11）
#   段末字段   = 该段结束后用哪种转场色板："dark" / "light" / None(不转)
#                规则：交界两侧有一侧偏深就用 dark；两侧都浅才用 light
SEGMENTS = [
    ("段1 美加极北", [
        ("美加极北新街景概况.png", 0, 0, None, None, 6.0),  # 开场图 6s，无缝接 yukon smallcam
        ("yukon-smallcam-1.mp4", 0.5, 0.5, None, None),   # 例1 育空 smallcam
        ("yukon-smallcam-2.mp4", 0.5, 0.5, None, None),   # 例1
        ("alaska.mp4",           0.5, 0.5, None, None),   # 例2 阿拉斯加 + Top of the World Hwy
        ("yukon.mp4",            0.5, 1.0, None, None)], "dark"),  # 例3 育空+BC 北部
    ("段2 高中月考", [
        ("月考文章.png", 0, 0, None, None, 11.0)], "dark"),
    ("段3 蒙大拿", [
        ("montana-smallcam.mp4", 1.0, 1.0, None, None)], "dark"),
    ("段4 厄瓜多尔", [
        ("ecuador-guide.mp4", 1.0, 0.5, None, None)], None),
]

EPISODE = "1011"        # 期号，用于输出文件名


def clip_path(f):
    """视频在 assets/video/，图片在 assets/image/。"""
    return os.path.join(IMAGES if f.lower().endswith(IMG_EXT) else ASSETS, f)

TR_HIT = 32
FPS = 30
# 水印位置用「占输出尺寸的比例」而不是固定像素。
# 原因：素材左右各带 62px 黑边（1280 宽下占 4.84%，上下没有），
# 这个黑边会跟着素材一起放大到 1080p（=93px）。
# 固定像素值会导致 720p 下勉强clear、1080p 下又被黑边压住。
WM_X_FRAC, WM_Y_FRAC = 0.0730, 0.0481
SIL_THR, SIL_D = -40, 0.25
# 口播覆盖率门槛：语音总时长 ÷ 片长 ≥ 这个比例，才认为这条素材"大部分都在讲"，
# 才按语音起止裁掉首尾空白。**没到这个比例就整条保留、一点不裁**——
# 录屏素材的音轨常常几乎是静的，按语音起止硬裁会把片子裁没
# （实测 49.2s 的素材被裁到 0.54s，六段合计 134s 缩成 51s）。
NARRATION_COVER = 0.5

# 片头 / 片尾（由 intro/ 和 outro/ 生成）
INTRO = os.path.join(ROOT, "intro", "片头-A.mp4")
OUTRO = os.path.join(HERE, "out", "片尾.mp4")

# 底栏（滚动新闻条）。条目直接从这期的素材文件里取，
# 不要再单独维护一份条目列表——建过一次，用户加了条目没同步，白跑一轮。
TICKER_SRC = os.path.join(HERE, "00-素材.md")


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
    返回 (首段语音起点, 末段语音终点, 视频流长度, 语音总时长)。

    注意：语音边界来自**音频流**，裁剪上界用**视频流长度**。
    早期版本用 format duration 当上界，导致视频尾部多出的空白剪不掉。

    语音总时长（不是首尾跨度）用来判断这条素材到底有没有口播 —— 见 SEGMENTS 处的用法。
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
        return 0.0, A, V, 0.0
    return sp[0][0], sp[-1][1], V, sum(e - s for s, e in sp)


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


def ensure_audio(src, dst, size=None):
    """
    片头/片尾是无声的。直接与有声的正片 concat 会让音频整体错位
    （视频多了 7s+9s，音频没有对应段），所以补一条等长静音轨。

    size=(W,H) 时顺便把画面缩到该尺寸（draft 用）——**不然 720p 的 draft 里接的
    是 1080p 的片头片尾，拼出来的 base 会被标成 1080p、正片段却还是 720p**
    （2026-10-11 踩过，见 geonews-project 长期坑 ⑦）。
    """
    if has_audio(src) and not size:
        return src
    vf = (["-vf", f"scale={size[0]}:{size[1]},setsar=1"] if size else [])
    vc = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p"] if size else ["-c:v", "copy"])
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", src, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-map", "0:v", "-map", "1:a"] + vf + vc + [
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         "-shortest", "-movflags", "+faststart", dst])
    return dst


def ticker_layers(duration=None, speed=None):
    """
    生成底栏三层（底栏底 / 滚动文字 / 词标块），返回图片路径 + 几何参数。

    几何参数从 tools/ticker.py 写的 meta.json 读回来，这边不另抄一份常量，
    改底栏参数只需改 ticker.py。duration 传正片时长，用于定滚动速度（见 fit_speed）；
    speed 显式给定时直接用它，不走 fit_speed。
    """
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import ticker                                        # noqa: E402
    items = ticker.load_items(TICKER_SRC)
    if not items:
        raise RuntimeError(f"底栏没有条目：{TICKER_SRC}")
    d = os.path.join(HERE, "_build", "ticker")
    meta = ticker.build(items, d, font="pixel", duration=duration, speed=speed)
    return (os.path.join(d, "bar.png"), os.path.join(d, "strip.png"),
            os.path.join(d, "chip.png"), meta)


def build(draft=False, only=None, full=False, ticker_on=False, wm=None):
    W, H = (1280, 720) if draft else (1920, 1080)
    # final 用 fast（不是 medium）：素材本来就是 720p 放大到 1080p，
    # 平板区域多，fast 与 medium 的观感差别看不出来，但耗时可降三分之一，
    # 能确保在单次调用时限内跑完。
    preset1, crf1 = ("ultrafast", 18) if draft else ("veryfast", 16)
    # 成品也用 veryfast：主机单次工具调用上限 177s，而 1080p 用 fast 编一遍要 150s 上下，
    # 两版分开跑也会被掐断。素材本身是清晰画面，crf 相同下 fast→veryfast 的观感差别很小。
    preset2, crf2 = ("veryfast", 20) if draft else ("veryfast", 19)

    out_dir = os.path.join(HERE, "out")
    tmp = os.path.join(HERE, "_build")
    os.makedirs(out_dir, exist_ok=True)

    # ---------- 规划：算裁剪点与切点 ----------
    plan, cut, cum = [], {}, 0.0
    print(f"{'片段':<22}{'原长':>7}{'裁入':>7}{'裁后':>7}  插图", flush=True)
    print("-" * 62, flush=True)
    for sname, clips, _kind in SEGMENTS:
        for clip in clips:
            f, bin_, bout, ins, card = clip[:5]
            hold = clip[5] if len(clip) > 5 else IMG_HOLD
            p = clip_path(f)
            if f.lower().endswith(IMG_EXT):
                # 图片：整条当一段静帧，停留 hold 秒，不裁、不查语音
                keep = hold
                plan.append(dict(file=p, name=os.path.splitext(f)[0], s=0.0, e=keep,
                                 keep=keep, ins=None, card=None, D=keep, image=True))
                print(f"{os.path.splitext(f)[0]:<22}{'--':>7}{'--':>7}{keep:>6.2f}s"
                      f"  图片（净黑底·居中·不裁）", flush=True)
                cum += keep
                continue
            a, b, V, sp_t = speech_bounds(p)    # V=视频流长，sp_t=语音总时长
            # 口播覆盖得够多才按语音起止裁；否则整条保留。理由见 NARRATION_COVER。
            cover = sp_t / V if V else 0.0
            mute = cover < NARRATION_COVER
            if mute:
                s, e = 0.0, V
            else:
                s = max(0.0, a - bin_)
                e = min(V, b + bout)            # 尾部多余画面在这里被剪掉
            keep = e - s
            ins_t = None
            if ins is not None and ins >= s:
                ins_t = ins - s          # 换算到裁剪后的时间轴
            plan.append(dict(file=p, name=f[:-4], s=s, e=e, keep=keep,
                             ins=ins_t, card=card, D=V, image=False))
            note = (f"口播 {cover*100:>5.1f}% → 不裁" if mute
                    else (f"{card} @{ins_t:.2f}s" if ins_t is not None else ""))
            print(f"{f[:-4]:<22}{V:>6.1f}s{s:>6.2f}s{keep:>6.2f}s  {note}", flush=True)
            cum += keep
        cut[sname] = cum
    total = cum
    print(f"\n裁剪后总长 {total:.2f}s ({int(total//60)}:{total%60:04.1f})", flush=True)
    for sname, _clips, kind in SEGMENTS:
        if kind:
            print(f"  {sname:<14} 结束 {cut[sname]:7.2f}s ← 转场({kind})", flush=True)
    if only == "plan":
        return None

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
            if c.get("image"):
                # 图片段：按比例缩放居中（不裁不拉伸），底色 IMG_BG，补等长静音
                vfI = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                       f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x{IMG_BG:06X},"
                       f"setsar=1,fps={FPS},format=yuv420p[vo]")
                run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                     "-loop", "1", "-framerate", str(FPS), "-i", c["file"],
                     "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                     "-filter_complex", vfI, "-map", "[vo]", "-map", "1:a",
                     "-t", f"{c['keep']:.3f}",
                     "-c:v", "libx264", "-preset", preset1, "-crf", str(crf1),
                     "-pix_fmt", "yuv420p", "-r", str(FPS),
                     "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", out])
                segs.append(out)
                continue
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
            sz = (W, H) if (W, H) != (1920, 1080) else None   # draft 时把片头片尾也缩到同尺寸
            items = [ensure_audio(INTRO, os.path.join(tmp, "intro.mp4"), sz)] + items \
                + [ensure_audio(OUTRO, os.path.join(tmp, "outro.mp4"), sz)]
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
                         f"GeoNews-{EPISODE}-{'draft-720p' if draft else '1080p'}"
                         f"{'-full' if full else ''}{'-带底栏' if ticker_on else ''}.mp4")
    # 片头若在，正片整体后移；水印只盖正片，不盖片头片尾
    intro_dur = dur(INTRO) if full else 0.0
    main_dur = cut[SEGMENTS[-1][0]]
    inputs = ["-i", base, "-i", WATERMARK]
    nidx = 2                       # 下一个输入的下标（0=正片 1=水印）
    tk = None
    if ticker_on:
        # 底栏三层夹在水印和转场之间。放转场之后的话，
        # 色带扫过时底栏会浮在色带上，穿帮。
        bar_p, strip_p, chip_p, tk = ticker_layers(main_dur)
        for p in (bar_p, strip_p, chip_p):
            inputs += ["-i", p]
        tk["i0"] = nidx
        nidx += 3
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
        tr_meta[i] = (label, kind, t_cut, t_start, nidx + i)

    wx = int(W * WM_X_FRAC)
    wy = int(H * WM_Y_FRAC)
    if full:
        # 水印只在正片出现（片头有品牌动画、片尾自带词标，不必再加）
        wm_enable = f":enable='between(t,{intro_dur:.3f},{intro_dur + main_dur:.3f})'"
    else:
        wm_enable = ""
    bar_enable = wm_enable               # 底栏同样只压正片
    # **成片默认不叠左上角水印**（用户 2026-09-30 定）：频道标识已经由底栏左侧的
    # 词标块承担，成片保持干净。要水印得显式加 --wm。
    use_wm = False if wm is None else wm
    if use_wm:
        fc2 = [f"[0:v][1:v]overlay={wx}:{wy}{wm_enable}[w0]"]
        prev = "w0"
    else:
        fc2, prev = [], "0:v"
    if ticker_on:
        # 底栏跟水印一样只压正片（片头有品牌动画、片尾自带词标）
        k = W / 1920.0                       # 底栏几何是按 1920 定的
        bh = int(round(tk["bar_h"] * k))
        y = H - bh
        chip_w, period, speed = tk["chip_w"] * k, tk["period"] * k, tk["speed"] * k
        i0 = tk["i0"]
        sc = f"scale=iw*{k}:ih*{k}" if k != 1.0 else "null"
        for tag, i in (("bars", i0), ("strs", i0 + 1), ("chs", i0 + 2)):
            fc2.append(f"[{i}:v]{sc}[{tag}]")
        # 底栏从**右边缘滚入**：正片开始那一刻整条带子还在画面外（底栏是空的），
        # 之后往左滚。相位必须从「正片开始」算起，不能从视频 0 秒算起 ——
        # 从 0 秒算的话，片头那 7 秒里带子已经偷偷滚掉一截，第一条会缺头。
        # 词标块最后压上去，盖住文字左端。
        fc2.append(f"[{prev}][bars]overlay=0:{y}{bar_enable}[bar0]")
        fc2.append(f"[bar0][strs]overlay="
                   f"x='{W}-mod((t-{intro_dur:.3f})*{speed:.4f},{period:.2f})'"
                   f":y={y}{bar_enable}[bar1]")
        fc2.append(f"[bar1][chs]overlay=0:{y}{bar_enable}[bar2]")
        prev = "bar2"
    tr_sc = "null" if (W, H) == (1920, 1080) else f"scale={W}:{H},setsar=1"
    for (label, kind, t_cut, t_start, iidx) in tr_meta:
        nxt = f"w{iidx-1}"
        # 转场序列是 1920×1080 的 PNG；draft 下必须缩到 base 尺寸，否则 overlay
        # 只取左上角一块、词标会跑到偏下（2026-10-11 踩过）。
        fc2.append(f"[{iidx}:v]{tr_sc}[tr{iidx}]")
        fc2.append(f"[{prev}][tr{iidx}]overlay=eof_action=pass:format=auto[{nxt}]")
        prev = nxt
    cmd2 = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + inputs + [
        "-filter_complex", ";".join(fc2), "-map", f"[{prev}]", "-map", "0:a",
        "-c:v", "libx264", "-preset", preset2, "-crf", str(crf2),
        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", final]
    print(f"[pass2] {'水印 @(%d,%d)' % (wx, wy) if use_wm else '无水印'}"
          + (" + 底栏" if ticker_on else "") + f" + {len(tr_meta)} 处转场 …", flush=True)
    for label, kind, t_cut, t_start, _ in tr_meta:
        print(f"   {label:<14} 切点 {t_cut:7.2f}s  转场 {t_start:7.2f}s 起（{kind}）", flush=True)
    print(f"   完成，用时 {run(cmd2):.0f}s", flush=True)
    print(f"\n输出: {final}", flush=True)
    return final


def bar_only(full=False, draft=False, span=None, speed=None):
    """
    只渲底栏，输出**带 alpha 通道的 MOV**，方便在剪辑软件里直接叠上去。

    默认跟成片完全一致（同样的相位、速度、出现时间），拖到正片开始的位置就能复现。
    给 `span`（秒）则只出底栏那一段：整段可见、从右滚进滚出，
    速度按这段时间重算（走完整条文字带，条目一个字不改）。

    用 qtrle（QuickTime Animation）而不是 ProRes 4444：整帧九成以上是全透明，
    qtrle 的行程编码能把那块压到几乎为零，ProRes 4444 则会输出上百 Mbps、文件上 GB。

    **只出底栏那一条（1920×84）**，不出整幅画面：全画幅 1080p 要编 4000+ 帧透明画面，
    单次工具调用编不完；而且剪辑软件里只需要把它贴到画面最下沿。
    """
    W2, H2 = (1280, 720) if draft else (1920, 1080)
    base = os.path.join(HERE, "_build", f"base_{'draft' if draft else 'final'}.mp4")
    if not os.path.exists(base):
        raise SystemExit(f"先跑 pass1 生成 {base}")
    total = dur(base)

    if span:
        # 只要底栏那一段（从进到出）：全程可见，相位从 0 起，速度按这段时长重算
        intro_dur, layout, out_dur = 0.0, span, span
        en = ""
    else:
        intro_dur = dur(INTRO) if full else 0.0
        layout = total - intro_dur - (dur(OUTRO) if full else 0.0)   # 正片时长
        out_dur = total
        en = f":enable='between(t,{intro_dur:.3f},{intro_dur + layout:.3f})'"

    bar_p, strip_p, chip_p, tk = ticker_layers(layout, speed=speed)
    k = W2 / 1920.0
    bh = int(round(tk["bar_h"] * k))
    y_top = H2 - bh                       # 这一条在整幅画面里贴的位置
    period, speed = tk["period"] * k, tk["speed"] * k
    chip_w = tk["chip_w"] * k
    if span:
        # 「从进到出」= **一次性播放**，不能循环。
        # 位移表达式里带 mod 的话，调快速度只是让它更快绕回开头，最后一条永远出不去。
        # 所以要裁一条"单程带子"（一条内容 + 尾随留白），并且丢掉 mod：
        #   t=0 时带子在画面右侧外（底栏是空的）→ 往左走 → 走光后不再回来。
        strip_img = Image.open(strip_p).convert("RGBA")
        one_w = int(round(tk.get("pad_l", 40) + tk["period"]))      # 1920 尺度
        one_p = os.path.join(HERE, "_build", "ticker", "strip_oneshot.png")
        strip_img.crop((0, 0, min(one_w, strip_img.width), strip_img.height)).save(one_p)
        strip_p = one_p
        # 走的距离 = 从画面右边缘外，一路走到词标块后面看不见
        speed = (W2 - chip_w + one_w) / span
        x_expr = f"{W2}-t*{speed:.4f}"
    else:
        x_expr = (f"{W2}-mod((t-{intro_dur:.3f})*{speed:.4f},{period:.2f})")
    sc = f"scale=iw*{k}:ih*{k}" if k != 1.0 else "null"

    fc = [f"[1:v]{sc}[bars]", f"[2:v]{sc}[strs]", f"[3:v]{sc}[chs]",
          f"[0:v][bars]overlay=0:0{en}[b0]",
          f"[b0][strs]overlay=x='{x_expr}':y=0{en}[b1]",
          f"[b1][chs]overlay=0:0{en}[out]"]
    tag = f"-{span:g}s" if span else ""
    out = os.path.join(HERE, "out", f"GeoNews-{EPISODE}-底栏叠加层{tag}.mov")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i",
         f"color=c=black@0.0:s={W2}x{bh}:r={FPS}:d={out_dur:.3f},format=yuva444p10le",
         "-i", bar_p, "-i", strip_p, "-i", chip_p,
         "-filter_complex", ";".join(fc), "-map", "[out]",
         "-c:v", "qtrle", "-pix_fmt", "argb", out])
    mb = os.path.getsize(out) / 1048576
    print(f"\n→ {out}")
    print(f"  {W2}×{bh} · {out_dur:.1f}s · 带 alpha · {mb:.1f} MB")
    print(f"  速度 {speed:.1f}px/s（"
          + (f"一次性：{layout:.1f}s 内从右滚进、再滚出" if span
             else f"循环：底栏在 {layout:.1f}s 内约滚 {layout / (period / speed):.2f} 圈") + "）")
    if span:
        print(f"  整段可见，拖到时间线最下沿（{W2}×{H2} 下即 y={y_top}）即可")
    else:
        print(f"  拖到时间线最下沿（{W2}×{H2} 下即 y={y_top}）；"
              f"底栏只在正片出现（{intro_dur:.1f}s → {intro_dur + layout:.1f}s）")
    return out


if __name__ == "__main__":
    argv = sys.argv[1:]
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    if "--plan" in argv:
        # 只列计划（时长/裁剪/转场），不渲染 —— 开渲前核对用
        build(draft="--draft" in argv, only="plan", full="--full" in argv)
    elif "--bar-only" in argv:
        # 只渲底栏，不重跑 pass1/pass2（否则等于白编一遍正片）
        # --bar-span 秒数：只出底栏那一段（从进到出），速度按这段时间重算
        # --bar-speed px/s：显式指定滚动速度，覆盖默认/fit_speed（用户口径）
        sp = float(argv[argv.index("--bar-span") + 1]) if "--bar-span" in argv else None
        spd = float(argv[argv.index("--bar-speed") + 1]) if "--bar-speed" in argv else None
        bar_only(full="--full" in argv, draft="--draft" in argv, span=sp, speed=spd)
    else:
        build(draft="--draft" in argv, only=only, full="--full" in argv,
              ticker_on="--ticker" in argv, wm=True if "--wm" in argv else None)
