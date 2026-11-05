#!/usr/bin/env python3
"""Render a fully animated source-grounded SVG explainer locally."""
from __future__ import annotations
import html
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRAMES = ROOT / "frames-svg"
RASTER = ROOT / "frames-png"
OUT = ROOT / "renders"
W, H, FPS = 960, 540, 24
INK, PAPER, TEAL, MUTED, LINE = "#1c3038", "#f3f0e8", "#60757b", "#66757a", "#067f8c"
GOLD, RUST, MINT, DEEP = "#d8a54c", "#b6553c", "#5e998c", "#12232b"
FONT = "/System/Library/Fonts/SFCompact.ttf"


def esc(s): return html.escape(str(s), quote=True)
def clamp(x): return max(0.0, min(1.0, x))
def ease(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3

def txt(x, y, value, size=22, fill=INK, weight=500, anchor="start", family="sans", opacity=1, spacing=None):
    ff = "Menlo" if family == "mono" else "SF Compact"
    ls = f' letter-spacing="{spacing}"' if spacing is not None else ""
    return f'<text x="{x:.2f}" y="{y:.2f}" font-family="{ff}" font-size="{size}" font-weight="{weight}" fill="{fill}" opacity="{opacity:.3f}" text-anchor="{anchor}"{ls}>{esc(value)}</text>'

def rect(x, y, w, h, fill="none", stroke="none", rx=0, sw=1, opacity=1):
    return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity:.3f}"/>'

def circ(cx, cy, r, fill, stroke="none", sw=1, opacity=1):
    return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{max(0,r):.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity:.3f}"/>'

def ln(x1,y1,x2,y2,stroke=LINE,sw=1,opacity=1,dash=None):
    d=f' stroke-dasharray="{dash}"' if dash else ""
    return f'<path d="M{x1:.2f} {y1:.2f} L{x2:.2f} {y2:.2f}" fill="none" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity:.3f}"{d}/>'

def path(d, stroke=LINE, sw=1, fill="none", opacity=1, dash=None):
    dash_attr=f' stroke-dasharray="{dash}"' if dash else ""
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity:.3f}"{dash_attr}/>'

def frame_base(n, section, source):
    return [
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">',
        f'<rect width="960" height="540" fill="{PAPER}"/>',
        rect(0,494,960,46,DEEP),
        txt(52, 36, "DRAXIS  /  ADMINISTRATION MACROCRAFT ARCHIVE", 10, TEAL, 600, family="mono", spacing=1.1),
        txt(908, 36, f"{n:02d} / 06", 10, MUTED, 400, "end", "mono", spacing=.8),
        ln(52, 50, 908, 50, LINE, 1),
        txt(52, 78, section.upper(), 11, TEAL, 600, family="mono", spacing=1),
        ln(52, 493, 908, 493, "#586d74", 1),
        txt(52, 515, source, 9, "#d6ddd9", 400, family="mono"),
        txt(908, 515, "SOURCE EXPLANATION  /  NOT A CANON UPDATE", 8, "#d6ddd9", 400, "end", "mono", spacing=.3),
    ]

def scene1(p):
    s=frame_base(1,"read the system","SOURCE: PDF PREFACE + FIELD PROTOCOL, PP. 2-3")
    q=ease(p)
    s += [txt(52,145,"THE DRAKKEN",15,TEAL,600,family="mono",opacity=ease(p*2),spacing=2),
          txt(52,204,"Terraforming",51,INK,700,opacity=ease(p*1.3)),
          txt(52,259,"is a rewrite.",51,INK,700,opacity=ease((p-.12)*1.7)),
          txt(54,308,"Read the archive by function,",18,MUTED,450,opacity=ease((p-.25)*2)),
          txt(54,335,"evidence, and consequence.",18,MUTED,450,opacity=ease((p-.36)*2))]
    cx=736-24*(1-q); cy=311
    # Original planetary strata and rotating atmospheric scan arc.
    s += [circ(cx,cy,142,"#e0d0ae","#6b7e7b",1.5), circ(cx,cy,112,"#82a99a"), circ(cx,cy,78,"#d5ad65"), circ(cx,cy,43,"#b9694d")]
    for a in range(0,360,30):
        theta=math.radians(a+p*90); x=cx+130*math.cos(theta); y=cy+130*math.sin(theta)
        s.append(circ(x,y,2.3,TEAL,opacity=.8))
    angle=p*65
    s += [f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="174" ry="74" fill="none" stroke="{TEAL}" stroke-width="2.5" opacity=".85" transform="rotate({angle:.2f} {cx:.2f} {cy:.2f})"/>',
          f'<ellipse cx="{cx:.2f}" cy="{cy-12:.2f}" rx="165" ry="68" fill="none" stroke="{GOLD}" stroke-width="1.4" opacity=".8" transform="rotate({-angle:.2f} {cx:.2f} {cy:.2f})"/>',
          circ(cx+174*math.cos(math.radians(angle)),cy+74*math.sin(math.radians(angle)),5,GOLD),
          ln(cx-100,cy-62,cx-190,cy-95,TEAL,1.2,ease((p-.25)*2)),
          txt(cx-199,cy-98,"CRUST",9,TEAL,600,"end","mono",ease((p-.25)*2)),
          ln(cx+72,cy-94,cx+130,cy-139,TEAL,1.2,ease((p-.4)*2)),
          txt(cx+138,cy-142,"WEATHER",9,TEAL,600,"start","mono",ease((p-.4)*2)),
          ln(cx+73,cy+96,cx+144,cy+131,TEAL,1.2,ease((p-.55)*2)),
          txt(cx+152,cy+136,"BIOSPHERE",9,TEAL,600,"start","mono",ease((p-.55)*2))]
    return s+["</svg>"]

def scene2(p):
    s=frame_base(2,"105 subjects / four evidence states","SOURCE: PDF FIELD PROTOCOL, P. 3; SOURCE GUIDE, CLASSIFICATION")
    s += [txt(52,126,"105 numbered subjects.",31,INK,700), txt(52,157,"Four different evidence states.",17,MUTED,450)]
    items=[("DOCUMENTED OPERATIONAL",58,TEAL,"strains"),("GENESIS",2,GOLD,"Egg + Mother"),("ARCHIVAL PROPOSALS",35,RUST,"not approved canon"),("CONTEXT PLATES",10,MINT,"not species")]
    for i,(label,total,color,note) in enumerate(items):
        y=210+i*59; delay=i*.11; r=clamp((p-delay)/.55); amount=total;
        s += [txt(52,y,label,12,INK,600,family="mono",opacity=ease(r*2),spacing=.5),
              txt(790,y+1,f"{amount:02d}",23,color,700,"end","mono",ease(r*2)),
              txt(908,y+1,note,10,MUTED,450,"end","mono",ease(r*2)),
              rect(52,y+12,856,9,"#e0ded5",rx=5), rect(52,y+12,856*total/105*ease(r),9,color,rx=5)]
    s += [txt(52,454,"58",35,TEAL,700,family="mono"),txt(116,454,"+",24,MUTED,400),
          txt(144,454,"2",35,GOLD,700,family="mono"),txt(177,454,"+",24,MUTED,400),
          txt(205,454,"35",35,RUST,700,family="mono"),txt(265,454,"+",24,MUTED,400),
          txt(293,454,"10",35,MINT,700,family="mono"),
          txt(415,454,"=",26,MUTED,400),txt(467,454,"105",35,INK,700,family="mono"),
          txt(531,454,"SUBJECTS",10,MUTED,600,family="mono",spacing=1)]
    return s+["</svg>"]

def scene3(p):
    s=frame_base(3,"58 operational folios / eight families","SOURCE: PDF SPECIMEN INDEX, PP. 5-6")
    s += [txt(52,126,"One dossier. Eight functional families.",29,INK,700),
          txt(52,156,"The family labels group the 58 documented operational records.",15,MUTED,450)]
    fam=["CRUST-BINDERS","ATMOS-ENGINES","SEEDCARRIERS","FLUXBORNE","ORBITAL-WYRMS","CIVIFORMERS","NOOSPHERE-CANTORS","GLITCH-TOUCHED"]
    colors=[RUST,TEAL,MINT,"#4776a0",GOLD,"#806e9e","#a45465","#687e82"]
    center=(480,323)
    for i,name in enumerate(fam):
        col=i//4; row=i%4; x=66 if col==0 else 516; y=220+row*55
        start=clamp((p-i*.055)/.38); e=ease(start)
        s += [rect(x,y-20,375,38,"#fbfaf6",LINE,5,1,e),
              rect(x,y-20,5+18*e,3,colors[i],"none",1,1,e),
              circ(x+18,y,5,colors[i],opacity=e),
              txt(x+34,y+5,name,13,INK,600,family="mono",opacity=e),
              txt(x+355,y+4,f"FAMILY {i+1:02d}",8,MUTED,450,"end","mono",e)]
    s += [circ(center[0],center[1],27,DEEP,TEAL,2), circ(center[0],center[1],7,GOLD),
          txt(center[0],center[1]+48,"FUNCTION",8,TEAL,600,"middle","mono",ease((p-.1)*2),1)]
    return s+["</svg>"]

def scene4(p):
    s=frame_base(4,"what terraforming means","SOURCE: PDF AUTHOR'S PREFACE + FIELD PROTOCOL, P. 2")
    s += [txt(52,126,"The target is a world system.",30,INK,700),
          txt(52,157,"Each function changes what the next form of life can survive.",15,MUTED,450)]
    # Split world starts coherent; colored trajectories sweep into a changed system.
    left=(255,330); right=(700,330); q=ease(p)
    s += [txt(255,216,"LOCAL CONDITIONS",10,MUTED,600,"middle","mono",1,1),
          txt(700,216,"REFORMATTED CONDITIONS",10,TEAL,600,"middle","mono",q,1)]
    for cx,cy,scale in [(left[0],left[1],1),(right[0]+(1-q)*80,right[1],.72+.28*q)]:
        s += [circ(cx,cy,91*scale,"#bfd0bb","#607b78",1.2),circ(cx,cy,62*scale,"#dbbd7f"),circ(cx,cy,31*scale,"#b97955")]
    # Migrate three system traces; the right system acquires distinct layers.
    for i,color in enumerate([TEAL,GOLD,RUST]):
        y=273+i*43
        xstart=left[0]+84
        xend=(right[0]-110)*q + xstart*(1-q)
        s.append(ln(xstart,y,xend,y+(i-1)*18*q,color,2.5,opacity=ease((p-i*.08)/.5)))
    s += [ln(413,330,530,330,TEAL,2.4,ease((p-.05)*2)),
          f'<path d="M530 330 l-14 -8 v16 z" fill="{TEAL}" opacity="{ease((p-.05)*2):.3f}"/>',
          txt(471,304,"FUNCTION",9,TEAL,600,"middle","mono",ease((p-.1)*2),.6),
          txt(92,447,"CRUST   /   WEATHER   /   BIOSPHERE",10,TEAL,600,family="mono",spacing=.6),
          txt(547,447,"CIVIC AND INSTITUTIONAL STRUCTURE",10,TEAL,600,family="mono",spacing=.35)]
    return s+["</svg>"]

def scene5(p):
    s=frame_base(5,"blood-eclipse war / corrected chronology","SOURCE: PDF WAR OVERVIEW, P. 4; SOURCE GUIDE, CORRECTED TIMELINE")
    s += [txt(52,126,"170 years. Then containment.",31,INK,700),
          txt(52,157,"The source explicitly supersedes the older 17-year summary.",15,MUTED,450)]
    x0,x1,y=98,861,303
    s += [ln(x0,y,x1,y,"#a7ada6",3),ln(x0,y,x0+(x1-x0)*ease(p),y,TEAL,4)]
    events=[(0,"YEAR 0","fringe strikes"),(3,"YEAR 3","first Blood Ring / Fallenstar Prime"),(121,"YEAR 121","Ruby Eclipse / Pharos Nebula"),(170,"YEAR 170","Aureal Gate / first Starsilk use")]
    for i,(year,label,note) in enumerate(events):
        x=x0+(x1-x0)*year/170; phase=clamp((p-i*.18)/.22); color=TEAL if i<2 else RUST if i==2 else GOLD
        labelx=(90 if i==0 else 218 if i==1 else x)
        s += [ln(x,y-17,x,y+17,color,2,phase),circ(x,y,7*phase,color,PAPER,2,phase),
              txt(labelx,251,label,11,color,650,"middle","mono",phase),
              txt(labelx,340,note,9,INK,500,"middle","mono",phase)]
    # Starsilk strike: pinpoint collapse and draw the irregular black-hole containment wall.
    collapse=clamp((p-.68)/.17); wall=clamp((p-.78)/.19)
    s += [circ(846,396,24*(1-collapse)+4,DEEP,GOLD,1.5,collapse),
          txt(846,440,"STAR COLLAPSE",8,RUST,600,"middle","mono",collapse)]
    holes=[(601,405),(650,381),(703,414),(757,386),(812,418),(872,392)]
    for i,(x,yh) in enumerate(holes):
        shown=clamp((wall-i*.09)/.28)
        s += [circ(x,yh,11,DEEP,GOLD,.8,shown),circ(x,yh,2,GOLD,opacity=shown)]
        if i<len(holes)-1:
            x2,y2=holes[i+1]
            s.append(ln(x,yh,x2,y2,RUST,1.1,opacity=shown*.6))
    s += [txt(562,463,"AFTER: HAL'VEN HELIOCIDE -> SIEGE WALL",10,"#f0c1a7",600,family="mono",opacity=wall)]
    return s+["</svg>"]

def scene6(p):
    s=frame_base(6,"how to read the evidence","SOURCE: PDF FIELD PROTOCOL, P. 3; SOURCE GUIDE, AUTHORITY NOTES")
    s += [txt(52,126,"Keep the evidence labels intact.",30,INK,700),
          txt(52,157,"The compendium preserves proposals and illustrations without promoting them to canon.",14,MUTED,450)]
    cards=[(52,"35","ARCHIVAL PROPOSALS","UNAPPROVED",RUST),(342,"10","CONTEXT PLATES","NOT STRAINS",TEAL),(632,"105","ILLUSTRATIONS","NOT CANON PROOF",GOLD)]
    for i,(x,n,label,status,color) in enumerate(cards):
        reveal=ease((p-i*.1)/.45); lift=24*(1-reveal)
        s += [rect(x,230+lift,276,137,"#fbfaf6",LINE,7,1,reveal),
              rect(x,230+lift,276*reveal,5,color,"none",2,1,reveal),
              txt(x+18,284+lift,n,39,color,700,family="mono",opacity=reveal),
              txt(x+18,316+lift,label,10,INK,600,family="mono",opacity=reveal,spacing=.35),
              txt(x+18,345+lift,status,11,color,700,family="mono",opacity=reveal)]
    stamp=clamp((p-.57)/.3)
    s += [ln(52,401,908,401,LINE,1),
          txt(52,437,"A surviving image is a visual reading,",18,INK,550,opacity=ease((p-.32)*2)),
          txt(52,464,"not proof of a specimen or canonical appearance.",18,INK,550,opacity=ease((p-.43)*2)),
          rect(661,417,247,47,"#e6eee8",TEAL,6,1,stamp),
          txt(784,447,"SOURCE SUMMARY  /  NOT CANON",10,TEAL,650,"middle","mono",stamp,spacing=.5)]
    return s+["</svg>"]

SCENES=[scene1,scene2,scene3,scene4,scene5,scene6]

def run(args):
    proc=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if proc.returncode: raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(map(str,args))}\n{proc.stderr[-3000:]}")
    return proc.stdout

def main():
    for cmd in ("magick","ffmpeg","ffprobe"):
        if shutil.which(cmd) is None: raise SystemExit(f"Required local executable unavailable: {cmd}")
    if not Path(FONT).is_file(): raise SystemExit(f"Required local font unavailable: {FONT}")
    FRAMES.mkdir(parents=True,exist_ok=True); RASTER.mkdir(parents=True,exist_ok=True); OUT.mkdir(parents=True,exist_ok=True)
    per_scene=132; input_png=[]; reuse_raster="--reuse-raster" in sys.argv[1:]
    for si,make_scene in enumerate(SCENES,1):
        svgs=[]
        for fi in range(per_scene):
            p=fi/(per_scene-1)
            svg=FRAMES/f"v2-scene-{si:02d}-{fi:03d}.svg"
            svg.write_text("\n".join(make_scene(p))+"\n",encoding="utf-8")
            svgs.append(svg)
        pattern=RASTER/f"v2-scene-{si:02d}-%03d.png"
        raster_files=[RASTER/f"v2-scene-{si:02d}-{fi:03d}.png" for fi in range(per_scene)]
        if reuse_raster and all(path.is_file() for path in raster_files):
            pass
        else:
            run(["magick","-font",FONT,*map(str,svgs),"-depth","8",str(pattern)])
        input_png.append(str(pattern))
    inputs=[]
    for pattern in input_png:
        inputs += ["-framerate",str(FPS),"-start_number","0","-i",pattern]
    graph=[]
    for i in range(len(SCENES)):
        graph.append(f"[{i}:v]scale={W}:{H},setsar=1,fps={FPS},trim=end_frame=132,setpts=PTS-STARTPTS[v{i}]")
    last="v0"
    for i in range(1,len(SCENES)):
        out=f"xf{i}"; offset=(132*i-12*(i-1))/FPS-.5
        graph.append(f"[{last}][v{i}]xfade=transition=fade:duration=0.5:offset={offset:.6f}[{out}]")
        last=out
    graph.append(f"[{last}]trim=end_frame=720,setpts=PTS-STARTPTS,format=yuv420p[outv]")
    video=OUT/"drakken-compendium-explainer-30s-v2.mp4"
    run(["ffmpeg","-y","-hide_banner","-loglevel","error",*inputs,"-filter_complex",";".join(graph),
         "-map","[outv]","-an","-c:v","libx264","-preset","medium","-crf","19","-movflags","+faststart","-t","30",str(video)])
    probe=json.loads(run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(video)]))
    stream=next((x for x in probe.get("streams",[]) if x.get("codec_type")=="video"),None)
    if not stream or stream.get("codec_name")!="h264" or stream.get("width")!=W or stream.get("height")!=H:
        raise SystemExit("Encoded video failed codec/dimension checks.")
    if abs(float(probe["format"]["duration"])-30)>.03 or stream.get("r_frame_rate")!="24/1" or any(x.get("codec_type") in ("audio","subtitle") for x in probe.get("streams",[])):
        raise SystemExit("Encoded video failed duration/FPS/audio/subtitle checks.")
    print(json.dumps({"video":str(video),"bytes":video.stat().st_size,"duration_seconds":probe["format"]["duration"],"frame_rate":stream["r_frame_rate"],"frames":stream.get("nb_frames"),"streams":[(x["codec_type"],x.get("codec_name")) for x in probe["streams"]]},indent=2))

if __name__=="__main__": main()
