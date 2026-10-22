# -*- coding: utf-8 -*-
import base64, os
HERE=os.path.dirname(os.path.abspath(__file__))
def b64(p):
    with open(p,"rb") as f: return "data:image/png;base64,"+base64.b64encode(f.read()).decode()

DARK=[("P1 净黑","对比最强，不挑素材，扫过时不会闪","#0E0E11","#E63A1F","P1-净黑.png"),
      ("P2 暖夜","比纯黑柔和，现代感强","#16171C","#FF4D24","P2-暖夜.png"),
      ("P3 深红","最重、冲击力最大","#4A1310","#FF6B3D","P3-深红.png"),
      ("P4 石墨","中性微暖，很耐看","#1A1A18","#E8562E","P4-石墨.png"),
      ("P5 深靛","保留你原来的藏蓝路线，但提纯不发灰","#171A2B","#FF5A2B","P5-深靛.png")]
LIGHT=[("L1 品牌纸白","与 logo 纸白一致","#F4EFE8","#C42A12","L1-品牌纸白.png"),
       ("L2 纯白","最亮，对比最弱","#FFFFFF","#D6341B","L2-纯白.png"),
       ("L3 暖米","偏暖，纸感强","#EFE7DA","#B8290F","L3-暖米.png"),
       ("L4 冷浅灰","中性，偏冷","#EDEFF1","#C0301C","L4-冷浅灰.png"),
       ("L5 浅橙调","浅色里对比最好","#FBEFE9","#A8200B","L5-浅橙调.png")]

def card(name,desc,bg,ac,img):
    src=b64(img)
    return f"""
    <div class="c">
      <div class="head">
        <span class="dot" style="background:{ac}"></span>
        <b>{name}</b><span class="desc">{desc}</span>
        <span class="hex">{bg} / {ac}</span>
      </div>
      <img src="{src}">
      <div class="sw">
        <div class="chip" style="background:{bg}">底 {bg}</div>
        <div class="chip" style="background:{ac}">强调 {ac}</div>
      </div>
    </div>"""

html=f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GEONEWS 转场配色</title><style>
:root{{color-scheme:light}}
*{{box-sizing:border-box}}
body{{margin:0;background:#F4EFE8;color:#17120F;
 font-family:-apple-system,"PingFang SC","Noto Sans SC","Microsoft YaHei",Arial,sans-serif}}
.wrap{{max-width:1000px;margin:0 auto;padding:48px 26px 80px}}
h1{{font-size:34px;margin:0;letter-spacing:-.02em}}
.lede{{color:#4B423B;font-size:15px;line-height:1.75;max-width:680px;margin:12px 0 0}}
h2{{font-size:13px;letter-spacing:.24em;color:#8C8178;font-weight:700;
 margin:44px 0 16px;padding-bottom:9px;border-bottom:1px solid #E3DAD0}}
.c{{background:#fff;border:1px solid #E3DAD0;border-radius:14px;padding:16px;margin:14px 0}}
.head{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}}
.dot{{width:14px;height:14px;border-radius:50%;flex:0 0 auto}}
.head b{{font-size:16px}}
.desc{{color:#8C8178;font-size:12.5px}}
.hex{{margin-left:auto;font-family:"SF Mono",Consolas,monospace;font-size:12px;color:#8C8178}}
.c img{{width:100%;display:block;border-radius:8px}}
.sw{{display:flex;gap:10px;margin-top:10px}}
.chip{{flex:1;border-radius:8px;padding:12px;font-size:12px;color:#fff;
 font-family:"SF Mono",Consolas,monospace;border:1px solid rgba(0,0,0,.08)}}
.chip:last-child{{}}
.warn{{background:#fff;border:1px solid #E3DAD0;border-left:4px solid #E63A1F;border-radius:10px;
 padding:18px 22px;font-size:14.5px;line-height:1.8;max-width:800px;margin:18px 0}}
</style></head><body><div class="wrap">
<h1>GEONEWS 转场 · 配色对比</h1>
<p class="lede">同一画面（色带盖住 + logo 居中）的实渲。每张下面是底色和强调色的色块。</p>

<h2>深色方案 · 适合当转场</h2>
{''.join(card(*d[:4], os.path.join(HERE,d[4])) for d in DARK)}

<h2>浅色方案</h2>
<div class="warn"><b>先说个问题：</b>这个转场是"色带扫过盖住旧画面"。色带若是浅色，
扫过深色素材时会<b>突然闪白</b>，扫出时再闪一次。深色底没这个问题——
这是浅色在转场场合的天然短板，不是配色能解决的。<br>
<b>所以浅色更适合当"片头定格"或"信息卡"，深色更适合当两个新闻之间的转场。</b></div>
{''.join(card(*d[:4], os.path.join(HERE,d[4])) for d in LIGHT)}
</div></body></html>"""
open(os.path.join(HERE,"配色方案.html"),"w").write(html)
print("HTML OK", len(html), "bytes")
