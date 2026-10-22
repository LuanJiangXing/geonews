# fonts/

项目自带字体。**SIL Open Font License 1.1**，可随项目自由分发。

**FusionPixel-12px-zh_hans.otf** — 缝合像素字体（Fusion Pixel Font）← 底栏在用
- 来源 https://github.com/TakWolf/fusion-pixel-font
- 12px 基准 × 4 = 48px。**像素字必须用基础字号的整数倍渲染**，否则边缘发虚。

## 为什么不用方舟像素体

方舟像素体（Ark Pixel）的 CJK 基本区只覆盖 18299/20992，缺 2000 多字，
其中包括「热」「旅」这种常用字，底栏里渲染成了方框。
**缺字时 PIL 不报错**，直接画 .notdef，会一路混进成片才被肉眼发现。

缝合像素体是同一作者的后续项目，以方舟为底把缺字补齐（覆盖 19219），
而且两者在常用字上**逐像素完全一致**（实测 37 字全同），换过去视觉上无感。

`ticker.missing_chars()` 会在生成时显式检查并报出缺字 —— 别再让方框悄悄出片。
