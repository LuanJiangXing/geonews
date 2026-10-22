# GeoNews 视频工作流

把 GeoGuessr 社区的新闻趣闻做成 3–5 分钟视频。
**全程只用你提供的素材，不额外生成任何视频或图片。**

**项目位置：本仓库根目录（`git clone` 到哪儿就在哪儿）**

**→ 完整流程见 [WORKFLOW.md](WORKFLOW.md)**　
**→ 品牌看 [logo/README.md](logo/README.md)，转场看 [transition/README.md](transition/README.md)**

---

## 你怎么用：一期一个文件夹

```
geonews/
├── 0918/                    ← 一期（月日命名）
│   ├── 00-素材.md           ★ 你写新闻的地方，只写这一个
│   ├── 03-素材进度.md       ★ 还缺什么素材
│   ├── 05-片尾链接.md       ★ 片尾要展示的链接
│   ├── assets/             你录的素材
│   └── out/                成片
│
├── intro/ outro/            片头片尾生成器（共用）
├── transition/ logo/ fonts/ 转场、品牌资产、底栏字体（共用）
├── tools/                   素材体检、配色表、底栏生成
└── templates/_project/      新一期从这里复制
```

**开新一期**：复制 `templates/_project/` → 改名成月日 → 按里面说明填。

---

## 三个阶段

| 阶段 | 你做什么 | 我做什么 |
|---|---|---|
| **1 素材与叙事** | 写新闻（格式随意）；**随时**把录好的画面丢进 `assets/` | 归类、排叙事；每批素材到就跑体检、更新缺什么 |
| **2 拼装** | —— | 填 `build.py` 的段落表，渲染出成片 |
| **3 完善** | 给反馈 | 改脚本重渲，改一段只重渲一段 |

**写新闻和给素材不分先后**——录屏单独进行、不影响归类，所以素材可以边写边给，
不必等我归类完。缺什么看 `03-素材进度.md`（每条标 已到 / 还缺）。

---

## 社区投稿

新闻不一定都要你自己写。三条通道见 **[投稿指南.md](投稿指南.md)**：

- **你自己写** — 填当期的 `00-素材.md`（三个区）
- **别人一句话** — 能收，但规矩是**我不猜、只追问**，问到时间/主体/出处/事实边界/量级/敏感性六项填满为止
- **别人详细写** — 把 `templates/投稿模板.docx` 发给他，填完发回来

---

## 命令速查

```bash
python3 tools/probe_assets.py 0930                     # 素材体检（每批素材到就跑）

cd 0930 && python3 build.py --full --only pass1         # 裁切+放大+拼片头片尾
cd 0930 && python3 build.py --full --only pass2         # 成片（干净：无水印、无底栏）
cd 0930 && python3 build.py --full --bar-only --bar-span 116  # 底栏叠加层（单独出）

cd intro && python3 build.py --render A --title 第二期 --range 26.09.20-26.09.29
cd outro && python3 build.py --links ../0930/05-片尾链接.md --out ../0930/out/片尾.mp4
```

底栏相关（改条目后重出预览）：

```bash
python3 tools/ticker_gif.py 0930/00-素材.md -o 0930/out/底栏预览.gif \
    --bg 0930/assets/video/china.mp4 --at 6.0 --duration 134.3
```

> **渲染必须分两段跑。** 一次跑完 1080p 会超过工具调用时限、进程被杀、
> 产出残缺文件。原因和另外几个坑见 [templates/README.md](templates/README.md)。

---

## 一个实测数据

第 1 期（0918）：片头 7s + 正片 195s + 片尾 8.8s = **3 分 31 秒**，
1920×1080，6 处转场。首次全量渲染约 4 分钟。
