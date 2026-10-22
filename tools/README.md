# tools/

共用的几个小工具。每期都会用到。

| 脚本 | 用途 |
|---|---|
| `probe_assets.py` | 素材体检 |
| `palette.py` | 配色唯一来源 |
| `ticker.py` | 底栏三层透明图生成 |
| `ticker_gif.py` | 底栏预览动图 |

> 环境：新会话的 Linux 沙箱可能**没装 `cairosvg`**（`ticker.py` 依赖它）。
> 报 `ModuleNotFoundError: No module named 'cairosvg'` 时先装：
> `python3 -m pip install --break-system-packages cairosvg`。

---

## probe_assets.py

```bash
python3 tools/probe_assets.py 0930
```

列出每条素材的真实分辨率、时长、帧率、有没有音轨、体积，并提前警告
"太糊 / 太短 / 没声音"。**渲染前跑一次，能拦掉大部分返工。**

⚠ 报的"有声"只代表有音轨，**不代表有口播**。

---

## palette.py

所有品牌物料的唯一取色来源。**换一期配色 = 改 `DARK` / `LIGHT` 两行。**

```bash
python3 tools/palette.py list   # 列出 11 套，标出本期在用
```

⚠ **换色后必须重新生成两份转场的叠加序列**——转场不是动态读颜色的，
是预先渲染好的 PNG。

```bash
python3 transition/v3/build.py        # 深色
python3 transition/v5-暖米/build.py   # 浅色
```

---

## ticker.py / ticker_gif.py

底栏（滚动新闻条）。条目来源是当期 `00-素材.md` 的「滚动底栏新闻条目」一节。

```bash
python3 tools/ticker.py 0930/00-素材.md /tmp/layers          # 只出三层
python3 tools/ticker_gif.py 0930/00-素材.md -o 出图.gif \
    --bg 0930/assets/video/china.mp4 --at 6.0 --duration 134.3
```

图层顺序、相位、速度、字体选型的理由都写在 `ticker.py` 顶部注释里。
字体为什么用缝合像素体（缺字问题）见 `fonts/README.md`。
