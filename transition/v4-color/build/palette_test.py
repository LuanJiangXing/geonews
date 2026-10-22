# -*- coding: utf-8 -*-
"""配色方向对比：把"色带完全盖住"的那一帧，用 5 组配色渲出来比较"""
import os
from PIL import Image, ImageDraw, ImageFont

W,H = 1920,1080
HERE=os.path.dirname(os.path.abspath(__file__))
logo=Image.open(os.path.join(HERE,"..","..","v1","build","logo-dark.png")).convert("RGBA")
LW,LH=logo.size
LOGO_W=880.0
SKEW=280

PALETTES = {
 "P1-净黑":   dict(band=(14,14,17),  accent=(230,58,31),  streak=(230,58,31)),
 "P2-暖夜":   dict(band=(22,23,28),  accent=(255,77,36),  streak=(255,77,36)),
 "P3-深红":   dict(band=(74,19,16),  accent=(255,107,61), streak=(255,140,100)),
 "P4-石墨":   dict(band=(26,26,24),  accent=(232,86,46),  streak=(232,86,46)),
 "P5-深靛":   dict(band=(23,26,43),  accent=(255,90,43),  streak=(255,90,43)),
}

def band_layer(S, pal, frame=30):
    L=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(L)
    poly=[(S-W-2*SKEW,0),(S-SKEW,0),(S,H),(S-W-SKEW,H)]
    d.polygon(poly, fill=pal["band"]+(255,))
    for i in range(22):
        x=S-W-2*SKEW+i*148+(frame*13)%148
        d.line([(x,-120),(x+340,H+120)], fill=pal["streak"]+(30,), width=6)
    d.line([(S-SKEW,0),(S,H)], fill=pal["accent"]+(238,), width=16)
    d.line([(S-W-SKEW,0),(S-W,H)], fill=pal["accent"]+(110,), width=8)
    return L

def hold_frame(pal):
    S=W+SKEW
    im=Image.new("RGBA",(W,H),pal["band"]+(255,))
    im=Image.alpha_composite(im, band_layer(S,pal))
    lw=int(LOGO_W); lh=int(LH*(lw/LW))
    lg=logo.resize((lw,lh),Image.LANCZOS)
    im.alpha_composite(lg,(int(W/2-lg.width/2),int(H/2-lg.height/2)))
    return im.convert("RGB")

if __name__=="__main__":
    outs=[]
    for name,pal in PALETTES.items():
        f=hold_frame(pal)
        f.save(os.path.join(HERE,f"{name}.png"))
        outs.append((name,f))
    # 拼成对比图（每格缩到 620 宽）
    cw,ch=620,349; cols=2; rows=3
    sheet=Image.new("RGB",(cols*cw, rows*ch),(0,0,0))
    d=ImageDraw.Draw(sheet)
    ft=ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",30)
    for n,(name,im) in enumerate(outs):
        x,y=(n%cols)*cw,(n//cols)*ch
        sheet.paste(im.resize((cw,ch)),(x,y))
        d.rectangle([x,y,x+cw-1,y+ch-1],outline=(70,70,74))
        d.rectangle([x+8,y+8,x+250,y+52],fill=(0,0,0))
        d.text((x+18,y+15),name,font=ft,fill=(255,255,255))
    # 右下角那格写上当前版本做参照
    x,y=cw,2*ch
    cur=Image.open(os.path.join(HERE,"..","..","v3","frames","f0044.png")).convert("RGB").resize((cw,ch))
    sheet.paste(cur,(x,y)); d.rectangle([x,y,x+cw-1,y+ch-1],outline=(70,70,74))
    d.rectangle([x+8,y+8,x+330,y+52],fill=(0,0,0))
    d.text((x+18,y+15),"当前版本（藏蓝 #1B2430）",font=ft,fill=(255,255,255))
    sheet.save(os.path.join(HERE,"配色对比.png"))
    print("done", sheet.size)
