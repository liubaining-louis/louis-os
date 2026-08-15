#!/usr/bin/env python3
import argparse
import math
import random
import struct
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W = H = 540
FPS = 30
DURATION = 6
FRAMES = FPS * DURATION
BLUE = (0, 82, 255)


def lerp(a, b, t):
    return int(a + (b - a) * t)


def gradient(size, top, bottom):
    w, h = size
    img = Image.new('RGB', size)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(lerp(top[i], bottom[i], t) for i in range(3))
        d.line((0, y, w, y), fill=c)
    return img


def paper_grain(size, seed=2030):
    rng = random.Random(seed)
    w, h = size
    buf = bytes(max(0, min(255, 128 + rng.randint(-18, 18))) for _ in range(w * h))
    return Image.frombytes('L', size, buf).filter(ImageFilter.GaussianBlur(0.35))


def draw_static_scene():
    img = gradient((W, H), (248, 232, 177), (140, 202, 205))
    d = ImageDraw.Draw(img)
    skyline = [
        (0,222,48,356,(88,119,126)),(38,190,92,356,(104,132,132)),
        (86,238,134,356,(74,107,117)),(126,164,177,356,(115,139,136)),
        (169,212,228,356,(83,112,120)),(218,179,276,356,(99,126,128)),
        (269,228,320,356,(72,104,114)),(312,150,370,356,(111,134,132)),
        (362,205,418,356,(79,108,117)),(411,174,469,356,(102,127,127)),
        (461,226,540,356,(68,100,111)),
    ]
    for x0,y0,x1,y1,c in skyline:
        d.rectangle((x0,y0,x1,y1), fill=c)
        d.polygon([(x0,y0),(x0+7,y0+8),(x0+7,y1),(x0,y1)], fill=tuple(min(255,v+18) for v in c))
    for x,y in [(55,218),(150,197),(243,205),(338,183),(438,207),(491,252)]:
        d.rectangle((x,y,x+7,y+5), fill=(221,223,175))
    d.polygon([(0,351),(540,326),(540,540),(0,540)], fill=(204,174,132))
    d.polygon([(0,356),(540,331),(540,351),(0,376)], fill=(145,126,104))
    d.polygon([(58,399),(240,393),(274,431),(85,443)], fill=(171,143,112))
    d.polygon([(336,363),(510,358),(540,386),(360,392)], fill=(171,143,112))
    d.rectangle((62,309,69,447), fill=(72,75,71)); d.rectangle((190,303,197,432), fill=(72,75,71))
    d.rectangle((59,304,201,312), fill=(72,75,71))
    d.rectangle((101,319,153,371), fill=BLUE)
    d.rectangle((106,372,158,379), fill=(116,111,93))
    d.polygon([(331,321),(397,312),(435,344),(354,352)], fill=(190,224,205))
    d.line([(331,321),(354,352),(435,344),(397,312),(331,321)], fill=(76,104,99), width=3)
    d.line([(370,317),(394,349)], fill=(94,119,111), width=2)
    for x,y in [(236,351),(283,347)]:
        d.polygon([(x,y),(x+39,y-4),(x+44,y+21),(x+5,y+25)], fill=(56,83,99))
        d.line([(x+6,y+8),(x+40,y+5)], fill=(123,161,164), width=2)
        d.line([(x+15,y-2),(x+20,y+23)], fill=(123,161,164), width=1)
    for x0,y0,x1,y1 in [(28,407,101,458),(212,421,291,470),(372,403,472,463)]:
        d.polygon([(x0,y0),(x1,y0-5),(x1-4,y1),(x0+5,y1+4)], fill=(155,79,57))
        d.line([(x0+6,y0+10),(x1-7,y0+5)], fill=(191,116,75), width=3)
    d.ellipse((133,416,224,447), fill=(113,83,62)); d.rectangle((173,439,182,492), fill=(88,70,59))
    d.ellipse((156,399,180,416), fill=(102,112,100)); d.rectangle((160,402,178,412), fill=(112,119,105))
    d.line([(178,405),(188,399)], fill=(80,83,76), width=3)
    d.ellipse((302,420,356,450), fill=(73,138,151)); d.ellipse((309,425,349,444), outline=(166,212,205), width=2)
    d.rectangle((485,343,488,434), fill=(76,76,69))
    d.line([(350,267),(501,256)], fill=(86,93,91), width=2)
    return img


def draw_leaf(draw,cx,cy,angle,scale,fill):
    ca,sa=math.cos(angle),math.sin(angle)
    pts=[(-7*scale,0),(0,-3.8*scale),(8*scale,0),(0,3.8*scale)]
    draw.polygon([(cx+x*ca-y*sa,cy+x*sa+y*ca) for x,y in pts], fill=fill)


def foliage(draw,phase):
    plants=[(50,404,8,(61,116,72)),(78,400,7,(73,132,76)),(230,418,8,(63,122,69)),(259,414,9,(78,138,76)),(396,398,9,(58,115,69)),(431,396,8,(80,136,74)),(455,397,7,(69,125,74))]
    for idx,(cx,base,count,color) in enumerate(plants):
        sway=math.sin(phase+idx*.73)*.16
        draw.line([(cx,base+7),(cx+sway*18,base-43)], fill=(68,93,60), width=3)
        for j in range(count):
            y=base-7-j*(35/max(1,count-1)); side=-1 if j%2==0 else 1
            x=cx+side*(7+(j%3)*2)+sway*(j+4); ang=side*.62+sway*.8
            draw_leaf(draw,x,y,ang,.88+.05*(j%3),color)


def steam(draw,phase):
    for j in range(4):
        t=((phase/(2*math.pi))+j/4.0)%1.0; y=398-t*53; x=169+math.sin(t*math.pi*2+j)*4
        r=3+5*t; shade=int(230-25*t)
        draw.ellipse((x-r,y-r*.7,x+r,y+r*.7), fill=(shade,shade,int(shade*.94)))
        if math.sin(math.pi*t)>.35:
            draw.arc((x-r-3,y-r,x+r+3,y+r),210,345,fill=(246,235,205),width=1)


def moving_details(draw,phase):
    cx,cy=487,343
    for k in range(4):
        a=phase+k*math.pi/2; ex=cx+math.cos(a)*16; ey=cy+math.sin(a)*16
        draw.line([(cx,cy),(ex,ey)], fill=(208,110,73), width=3); draw.ellipse((ex-3,ey-3,ex+3,ey+3), fill=(235,178,104))
    draw.ellipse((cx-4,cy-4,cx+4,cy+4), fill=(73,79,74))
    pos=(1-math.cos(phase))/2; x=360+pos*125; y=267-pos*9
    draw.rounded_rectangle((x-9,y-4,x+9,y+7), radius=3, fill=(214,159,86), outline=(86,93,91), width=1)
    for j in range(3):
        ofs=math.sin(phase+j*1.9)*4
        draw.arc((310+j*5+ofs,428+j*3,348-j*4+ofs,443-j*2),190,340,fill=(194,229,214),width=1)
    draw.line([(73,388),(122,382)], fill=(92,88,75), width=1)
    for j,c in enumerate([(231,196,132),(181,100,79),(236,222,184)]):
        x=80+j*16; wavev=math.sin(phase*2+j)*2.2
        draw.polygon([(x,387),(x+10,386+wavev),(x+9,397+wavev),(x+1,398)], fill=c)


def render_frames(out_dir):
    out_dir=Path(out_dir); out_dir.mkdir(parents=True,exist_ok=True)
    base=draw_static_scene(); grain=paper_grain((W,H)); grain_rgb=Image.merge('RGB',(grain,grain,grain))
    warm=Image.new('RGB',(W,H),(255,244,199)); cool=Image.new('RGB',(W,H),(105,131,136))
    for i in range(FRAMES):
        phase=2*math.pi*i/FRAMES; frame=base.copy(); d=ImageDraw.Draw(frame)
        foliage(d,phase); steam(d,phase); moving_details(d,phase)
        glow=.035*math.sin(phase)
        if glow: frame=Image.blend(frame,warm if glow>0 else cool,abs(glow))
        frame=Image.blend(frame,grain_rgb,.045)
        frame.save(out_dir/f'frame_{i:04d}.png', compress_level=1)


def write_audio(path):
    sr=48000; n=sr*DURATION; harmonics=[60.0,90.0,126.0,222.0,318.0,522.0,702.0]
    samples=[]; peak=0.0
    for i in range(n):
        t=i/sr; phase=2*math.pi*t/DURATION; wind_env=.82+.18*math.sin(phase)
        hum=.11*math.sin(2*math.pi*60*t)+.045*math.sin(2*math.pi*90*t)
        rustle=sum((.008/(1+j*.35))*math.sin(2*math.pi*f*t+j*.83) for j,f in enumerate(harmonics[2:]))
        bell=0.0
        for center,freq in [(1.5,660.0),(4.5,528.0)]:
            dt=t-center
            if abs(dt)<.42:
                env=.5*(1+math.cos(math.pi*dt/.42)); bell+=.035*env*math.sin(2*math.pi*freq*dt)+.014*env*math.sin(2*math.pi*freq*1.5*dt)
        sig=wind_env*(hum+rustle)+bell
        left=sig*(.98+.02*math.sin(phase)); right=sig*(.98-.02*math.sin(phase))
        peak=max(peak,abs(left),abs(right)); samples.append((left,right))
    scale=.66/(peak or 1.0); pcm=bytearray(4*n); off=0
    for l,r in samples:
        struct.pack_into('<hh',pcm,off,int(max(-1,min(1,l*scale))*32767),int(max(-1,min(1,r*scale))*32767)); off+=4
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(pcm)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--frames',required=True); ap.add_argument('--audio',required=True); args=ap.parse_args()
    render_frames(args.frames); write_audio(args.audio)
    print(f'FRAMES_GENERATED={FRAMES}'); print(f'FPS={FPS}'); print(f'DURATION={DURATION}')
    print('LANE=2'); print('SETTING=rooftop gardens above the city'); print('STYLE=mid-century gouache cut-paper diorama')
    print('BLUE_SQUARE=#0052FF diegetic awning panel')
    print('MOTION_ELEMENTS=foliage_sway,steam,wind_spinner,cable_pod,water_shimmer,laundry_ribbon')

if __name__=='__main__': main()
