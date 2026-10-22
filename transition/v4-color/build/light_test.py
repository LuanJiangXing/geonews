# -*- coding: utf-8 -*-
"""浅色底配色对比"""
import os
from PIL import Image, ImageDraw, ImageFont
W,H=1920,1080
HERE=os.path.dirname(os.path.abspath(__file__))
# 浅底 → 用深色字的 logo
logo=Image.open(os.path.join(HERE,"..","..","v1","build","logo-light.png")).convert("RGBA")
LW,LH=logo.size; LOGO_W=880.0; SKEW=280

# 浅底方案：底色亮，强调色必须更深才跳得出来
PALETTES = {
 "L1-品牌纸白": dict(band=(244,239,232), accent=(196,42,18),  streak=(196,42,18)),
 "L2-纯白":     dict(band=(255,255,255), accent=(214,52,27),  streak=(214,52,27)),
 "L3-暖米":     dict(band=(239,231,218), accent=(184,41,15),  streak=(184,41,15)),
 "L4-冷浅灰":   dict(band=(237,239,241), accent=(192,48,28),  streak=(192,48,28)),
 "L5-浅橙调":   dict(band=(251,239,233), accent=(168,32,11),  streak=(168,32,11)),
}

def stripes(L, S, pal, frame=30):
    d=ImageDraw.Draw(L)
    for i in range(22):
        x=S-W-2*SKEW+i*148+(frame*13)%148
        # 浅底上的条纹用“更浅+半透明”，靠加深前缘线提示方向
        d.line([(x,-120),(x+340,H+120)], fill=pal["streak"]+(18,), width=8)

def hold_frame(pal):
    S=W+SKEW
    im=Image.new("RGBA",(W,H),pal["band"]+(255,))
    band=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(band)
    poly=[(S-W-2*SKEW,0),(S-SKEW,0),(S,H),(S-W-SKEW,H)]
    d.polygon(poly, fill=pal["band"]+(255,))
    stripes(band,S,pal)
    d.line([(S-SKEW,0),(S,H)], fill=pal["accent"]+(255,), width=16)
    d.line([(S-W-SKEW,0),(S-W,H)], fill=pal["accent"]+(150,), width=8)
    im=Image.alpha_composite(im,band)
    lw=int(LOGO_W); lh=int(LH*(lw/LW))
    lg=logo.resize((lw,lh),Image.LANCZOS)
    im.alpha_composite(lg,(int(W/2-lg.width/2),int(H/2-lg.height/2)))
    return im.convert("RGB")

if __name__=="__main__":
    outs=[]
    for name,pal in PALETTES.items():
        f=hold_frame(pal); f.save(os.path.join(HERE,f"{name}.png")); outs.append((name,f))
    cw,ch=620,349; cols=2; rows=3
    sheet=Image.new("RGB",(cols*cw,rows*ch),(0,0,0))
    d=ImageDraw.Draw(sheet)
    ft=ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",30)
    for n,(name,im) in enumerate(outs):
        x,y=(n%cols)*cw,(n//cols)*ch
        sheet.paste(im.resize((cw,ch)),(x,y))
        d.rectangle([x,y,x+cw-1,y+ch-1],outline=(70,70,74))
        d.rectangle([x+8,y+8,x+300,y+52],fill=(0,0,0))
        d.text((x+18,y+15),name,font=ft,fill=(255,255,255))
    # 右下放深色系最好的一版做对照
    x,y=cw,2*ch
    cur=Image.open(os.path.join(HERE,"P1-净黑.png")).convert("RGB").resize((cw,ch))
    sheet.paste(cur,(x,y)); d.rectangle([x,y,x+cw-1,y+ch-1],outline=(70,70,74))
    d.rectangle([x+8,y+8,x+300,y+52],fill=(0,0,0))
    d.text((x+18,y+15),"对照：P1-净黑（深色）",font=ft,fill=(255,255,255))
    sheet.save(os.path.join(HERE,"浅色配色对比.png"))
    print("done",sheet.size)
