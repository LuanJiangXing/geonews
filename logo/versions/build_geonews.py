"""GEONEWS v6 - 80px pixel-optimised. Same design (GEO + signal + EWS), tuned for small size.
Levers: (1) trim whitespace/gaps  (2) stroke-embolden the glyphs so hairlines survive at small px."""
import math, os, subprocess
import glyphpath as g
BOOK="/usr/share/fonts/opentype/urw-base35/URWBookman-Demi.otf"
C=100.0
EMB="#E63A1F"; DEEP="#A8210B"; INK="#17120F"; PAPER="#F4EFE8"; NIGHT="#1B2430"

def arc(cx,cy,r,a0,a1,seg=72):
    P=[(cx+r*math.cos(math.radians(a0+(a1-a0)*i/seg)),cy+r*math.sin(math.radians(a0+(a1-a0)*i/seg))) for i in range(seg+1)]
    return "M"+f"{P[0][0]:.2f},{P[0][1]:.2f}"+"".join(f" L{q[0]:.2f},{q[1]:.2f}" for q in P[1:])

def lockup(word, acc, track=0.005, gapL=0.16, gapR=0.18, condense=0.68,
           embolden=4.5, barw=0.09, marksw=0.19, markmode="two"):
    dL,aL=g.text_caps(BOOK,"GEO",cap=C,tracking=track)
    dR,aR=g.text_caps(BOOK,"EWS",cap=C,tracking=track)
    bx=aL+gapL*C; bw=barw*C; cx=bx+bw/2
    xR=cx+0.60*C+gapR*C
    st=f' stroke="{word}" stroke-width="{embolden:.2f}" stroke-linejoin="round"'
    p=[f'<path d="{dL}" fill="{word}"{st}/>',
       f'<rect x="{bx:.2f}" y="{-C:.2f}" width="{bw:.2f}" height="{C:.2f}" fill="{acc}"/>']
    if markmode=="two":
        p.append(f'<path d="{arc(cx,-C/2,0.32*C,-50,50)}" stroke="{acc}" stroke-width="{marksw*C:.2f}" stroke-linecap="round" fill="none"/>')
        p.append(f'<path d="{arc(cx,-C/2,0.58*C,-50,50)}" stroke="{acc}" stroke-width="{marksw*C*0.85:.2f}" stroke-linecap="round" fill="none"/>')
    else:
        p.append(f'<path d="{arc(cx,-C/2,0.58*C,-50,50)}" stroke="{acc}" stroke-width="{marksw*C*1.35:.2f}" stroke-linecap="round" fill="none"/>')
    p.append(f'<g transform="translate({xR:.2f},0)"><path d="{dR}" fill="{word}"{st}/></g>')
    body="".join(p); W=xR+aR
    body=f'<g transform="scale({condense:.4f},1)">{body}</g>'; W*=condense
    return body, W

def svg(body,W,pad):
    Wp,Hp=W+2*pad,C+2*pad
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wp:.1f}" height="{Hp:.1f}" '
            f'viewBox="0 0 {Wp:.2f} {Hp:.2f}" fill="none">'
            f'<g transform="translate({pad},{pad+C})">{body}</g></svg>')

def avatar(side, bg, fg):
    r=0.22*side; bx=0.30*side; bw=0.075*side
    p=[f'<rect width="{side}" height="{side}" rx="{r:.2f}" fill="{bg}"/>',
       f'<rect x="{bx:.2f}" y="{0.22*side:.2f}" width="{bw:.2f}" height="{0.56*side:.2f}" fill="{fg}"/>']
    cx=bx+bw/2
    for rr,sw in ((0.19*side,0.068*side),(0.33*side,0.058*side)):
        p.append(f'<path d="{arc(cx,side/2,rr,-50,50)}" stroke="{fg}" stroke-width="{sw:.2f}" stroke-linecap="round" fill="none"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{side}" height="{side}" viewBox="0 0 {side} {side}" fill="none">{"".join(p)}</svg>'

O="dist"; os.makedirs(O,exist_ok=True)
jobs={}
# P2 = primary
b,W=lockup(PAPER,EMB); jobs["GEONEWS_watermark-dark.svg"]=svg(b,W,6)
b,W=lockup(INK,EMB);   jobs["GEONEWS_watermark-light.svg"]=svg(b,W,6)
b,W=lockup(PAPER,EMB); jobs["GEONEWS_dark.svg"]=svg(b,W,18)
b,W=lockup(INK,EMB);   jobs["GEONEWS_light.svg"]=svg(b,W,18)
b,W=lockup("#000","#000"); jobs["GEONEWS_mono-black.svg"]=svg(b,W,6)
b,W=lockup("#FFF","#FFF"); jobs["GEONEWS_mono-white.svg"]=svg(b,W,6)
# alternates
b,W=lockup(PAPER,EMB,gapL=0.18,gapR=0.20,condense=0.75,embolden=3.0,marksw=0.17)
jobs["alt-P1_watermark-dark.svg"]=svg(b,W,6)
b,W=lockup(PAPER,EMB,gapL=0.16,gapR=0.18,condense=0.70,embolden=4.0,marksw=0.17,markmode="one")
jobs["alt-P4_watermark-dark.svg"]=svg(b,W,6)
jobs["avatar_ember.svg"]=avatar(200,EMB,"#FFFFFF")
jobs["avatar_ink.svg"]=avatar(200,INK,"#FFFFFF")
jobs["avatar_light.svg"]=avatar(200,PAPER,INK)

for n,s in jobs.items():
    open(f"{O}/{n}","w").write(s)
    ok=subprocess.run(["convert","-background","none","-density","300",f"{O}/{n}",f"{O}/{n}.png"],capture_output=True).returncode==0
    print(f"{n:34s} {len(s):6d}B render={'ok' if ok else 'FAIL'}")
