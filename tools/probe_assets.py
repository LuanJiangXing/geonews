#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_assets.py —— 素材体检

在建 timeline 之前跑一遍，把素材的实际情况（分辨率、时长、有无音轨、画幅比例）
摊开来看。目的是提前发现"这条素材根本不够长/太糊/没有声音"这类问题，
而不是等渲染完才发现镜头是黑的。

用法：
  python3 probe_assets.py <project_dir>            # 体检 project_dir/assets
  python3 probe_assets.py <some_folder>
  python3 probe_assets.py <project_dir> --json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv", ".ts", ".mpg", ".mpeg"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus"}

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def probe(path: str) -> dict:
    """用 ffprobe 读取一个文件的完整信息。"""
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        return {"ok": False, "error": (p.stderr or "ffprobe 失败").strip()[:200]}
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "无法解析 ffprobe 输出"}

    out = {"ok": True, "path": path, "size": os.path.getsize(path)}
    fmt = data.get("format", {})
    out["duration"] = float(fmt.get("duration") or 0.0)

    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

    if v:
        out["width"] = int(v.get("width") or 0)
        out["height"] = int(v.get("height") or 0)
        out["vcodec"] = v.get("codec_name")
        fr = v.get("r_frame_rate") or "0/1"
        try:
            num, den = fr.split("/")
            out["fps"] = round(float(num) / float(den), 2) if float(den) else 0.0
        except Exception:
            out["fps"] = 0.0
        out["nb_frames"] = int(v.get("nb_frames") or 0)
        out["has_video"] = True
    else:
        out["has_video"] = False

    if a:
        out["acodec"] = a.get("codec_name")
        out["sample_rate"] = int(a.get("sample_rate") or 0)
        out["channels"] = int(a.get("channels") or 0)
        out["has_audio"] = True
    else:
        out["has_audio"] = False

    return out


def classify(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    return "other"


def analysis(info: dict, kind: str) -> list:
    """对单个素材给出可用性判断。"""
    notes = []
    if not info.get("ok"):
        return [f"{RED}读取失败{RESET}：{info.get('error', '')}"]

    if kind in ("video", "image"):
        w, h = info.get("width", 0), info.get("height", 0)
        if w and h:
            ar = w / h
            if ar > 2.4:
                notes.append(f"{YELLOW}超宽{RESET} {ar:.2f}:1，上 16:9 会有大黑边，建议裁切或做拼接")
            elif ar < 0.6:
                notes.append(f"{DIM}竖幅{RESET} {ar:.2f}:1，将用模糊背景填充两侧")
            if w < 1280:
                notes.append(f"{YELLOW}分辨率偏低{RESET} {w}×{h}，1080p 成片会显得糊")

    if kind == "video":
        d = info.get("duration", 0)
        if d < 3:
            notes.append(f"{YELLOW}素材过短{RESET} 仅 {d:.1f}s，需开 loop 或冻结补帧")
        if not info.get("has_audio"):
            notes.append(f"{DIM}无音轨{RESET} 无法作为「原声出镜」素材")
        fps = info.get("fps", 0)
        if fps and fps < 24:
            notes.append(f"{YELLOW}帧率偏低{RESET} {fps}fps，动作会卡")

    if kind == "audio":
        if info.get("duration", 0) < 3:
            notes.append(f"{YELLOW}音频过短{RESET}")

    return notes


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def main() -> None:
    ap = argparse.ArgumentParser(description="GeoNews 素材体检")
    ap.add_argument("path", help="素材目录")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--max-dur", type=float, default=0,
                    help="按最长时长筛选（秒），用于挑出够长的录屏，0 表示不筛选")
    a = ap.parse_args()

    root = os.path.abspath(a.path)
    if not os.path.isdir(root):
        print(f"{RED}目录不存在：{root}{RESET}")
        raise SystemExit(2)

    rows = []
    for dirpath, _, filenames in os.walk(root):
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            fp = os.path.join(dirpath, fn)
            kind = classify(fp)
            if kind == "other":
                continue
            info = probe(fp)
            info["kind"] = kind
            info["rel"] = os.path.relpath(fp, root)
            info["notes"] = analysis(info, kind)
            rows.append(info)

    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    if not rows:
        print(f"  在 {root} 下没有找到可用的素材文件。")
        print(f"  支持的格式：{', '.join(sorted(VIDEO_EXT | IMAGE_EXT | AUDIO_EXT))}")
        return

    groups = {"video": [], "image": [], "audio": []}
    for r in rows:
        groups[r["kind"]].append(r)

    print(f"\n{'=' * 78}")
    print(f"  素材体检 — {root}")
    print(f"{'=' * 78}")

    label = {"video": "视频", "image": "图片", "audio": "音频"}
    for k in ("video", "image", "audio"):
        items = groups[k]
        if not items:
            continue
        print(f"\n  【{label[k]}】{len(items)} 个")
        print(f"  {'-' * 74}")
        for r in items:
            if not r.get("ok"):
                print(f"    {r['rel']:<38} {RED}读取失败{RESET}")
                continue
            if k == "image":
                spec = f"{r.get('width')}×{r.get('height')}"
            elif k == "video":
                spec = (f"{r.get('width')}×{r.get('height')} "
                        f"{r.get('duration', 0):.1f}s {r.get('fps', 0):.0f}fps "
                        f"{'有声' if r.get('has_audio') else '无声'}")
            else:
                spec = f"{r.get('duration', 0):.1f}s {r.get('channels', 0)}ch"
            print(f"    {r['rel']:<38} {spec:<34} {human_size(r.get('size', 0)):>8}")
            for n in r.get("notes", []):
                print(f"        └─ {n}")

    # 汇总建议
    n_video = len(groups["video"])
    shorts = [r for r in groups["video"] if r.get("ok") and r.get("duration", 0) < 5]
    print(f"\n  {'-' * 74}")
    print(f"  合计：视频 {n_video}　图片 {len(groups['image'])}　音频 {len(groups['audio'])}")
    if n_video == 0 and groups["image"]:
        print(f"  {YELLOW}提示{RESET}：没有任何视频素材，成片将是静态图轮播。"
              f"补几段录屏能显著提升观感。")
    if shorts:
        print(f"  {YELLOW}提示{RESET}：{len(shorts)} 个视频短于 5s，"
              f"建 timeline 时记得设 \"loop\": true 或在脚本里控制镜头时长。")
    print()


if __name__ == "__main__":
    main()
