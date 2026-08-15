#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
from pathlib import Path

W, H = 1500, 500
OUT = Path('deliverables/rustchain_rip302_banner/rustchain_banner_1500x500.png')
OUT.parent.mkdir(parents=True, exist_ok=True)

img = Image.new('RGBA', (W, H), (7, 13, 18, 255))
d = ImageDraw.Draw(img)

# Dark terminal gradient.
for y in range(H):
    t = y / max(1, H - 1)
    c = (7 + int(7*t), 13 + int(7*t), 18 + int(5*t), 255)
    d.line((0, y, W, y), fill=c)

# Grid + scanlines.
for x in range(0, W, 75):
    d.line((x, 0, x, H), fill=(22, 42, 43, 255), width=1)
for y in range(0, H, 50):
    d.line((0, y, W, y), fill=(22, 42, 43, 255), width=1)
for y in range(0, H, 5):
    d.line((0, y, W, y), fill=(4, 8, 10, 170), width=1)

# Warm glow beneath vintage machines.
glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse((50, 345, 720, 535), fill=(225, 125, 35, 45))
glow = glow.filter(ImageFilter.GaussianBlur(30))
img = Image.alpha_composite(img, glow)
d = ImageDraw.Draw(img)

orange = (217, 126, 38, 255)
green = (97, 213, 122, 255)
panel = (19, 31, 34, 255)

# Circuit traces.
for yy in (80, 145, 350, 420):
    d.line((0, yy, 250, yy), fill=(54, 106, 92, 255), width=2)
    d.line((250, yy, 290, yy + 25), fill=(54, 106, 92, 255), width=2)
    d.ellipse((286, yy + 21, 294, yy + 29), fill=orange)

# Vintage CRT computer.
d.rounded_rectangle((105, 145, 310, 365), radius=22, fill=panel, outline=orange, width=5)
d.rounded_rectangle((130, 175, 285, 285), radius=12, fill=(13, 25, 27, 255), outline=(83, 136, 110, 255), width=3)
for yy in range(205, 260, 14):
    d.line((153, yy, 258, yy), fill=(84, 171, 105, 255), width=3)
d.rectangle((185, 315, 230, 325), fill=orange)
d.ellipse((270, 320, 282, 332), fill=(89, 182, 108, 255))
d.polygon([(150, 365), (265, 365), (305, 410), (115, 410)], fill=(16, 27, 31, 255), outline=orange)
for k in range(7):
    d.line((145 + k*20, 380, 155 + k*20, 380), fill=(80, 120, 105, 255), width=3)

# PowerPC-style tower.
d.rounded_rectangle((330, 120, 470, 405), radius=16, fill=panel, outline=orange, width=5)
for i in range(4):
    d.rounded_rectangle((355, 155 + i*48, 445, 183 + i*48), radius=7,
                        fill=(10, 20, 23, 255), outline=(73, 115, 102, 255), width=2)
d.ellipse((390, 355, 412, 377), fill=(88, 188, 112, 255))
d.line((350, 395, 450, 395), fill=(62, 100, 88, 255), width=2)

# Vintage laptop with signal waveform.
d.rounded_rectangle((500, 195, 690, 330), radius=10, fill=(21, 31, 34, 255), outline=orange, width=4)
d.rectangle((520, 215, 670, 305), fill=(11, 25, 26, 255), outline=(79, 134, 106, 255), width=2)
pts = [(x, 260 + int(18 * math.sin((x - 535)/14))) for x in range(535, 655, 4)]
d.line(pts, fill=green, width=3)
d.polygon([(485, 330), (705, 330), (740, 385), (460, 385)], fill=(17, 27, 31, 255), outline=orange)
d.line((520, 350, 680, 350), fill=(72, 105, 92, 255), width=2)

# Floating CPU chips.
for cx, cy, s in ((85, 90, 38), (605, 90, 34), (735, 110, 28)):
    d.rounded_rectangle((cx-s/2, cy-s/2, cx+s/2, cy+s/2), radius=5,
                        fill=(26, 44, 42, 255), outline=orange, width=2)
    for off in (-10, 0, 10):
        d.line((cx-s/2-8, cy+off, cx-s/2, cy+off), fill=orange, width=2)
        d.line((cx+s/2, cy+off, cx+s/2+8, cy+off), fill=orange, width=2)

# Typography panel.
d.line((790, 75, 790, 425), fill=(218, 143, 44, 210), width=2)
font_bold = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
font_mono = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
title = ImageFont.truetype(font_bold, 74)
tag = ImageFont.truetype(font_bold, 46)
sub = ImageFont.truetype(font_mono, 18)
small = ImageFont.truetype(font_mono, 19)

d.text((835, 95), 'RUSTCHAIN', font=title, fill=(240, 242, 236, 255))
d.rounded_rectangle((840, 185, 1310, 192), radius=3, fill=orange)
d.text((840, 225), 'EVERY CPU', font=tag, fill=(224, 146, 50, 255))
d.text((840, 278), 'HAS A VOICE', font=tag, fill=(224, 146, 50, 255))
d.rounded_rectangle((825, 337, 1498, 388), radius=8, fill=(8, 18, 20, 255), outline=(42, 78, 69, 220), width=1)
d.text((842, 353), 'PROOF OF ANTIQUITY  •  REAL HARDWARE  •  AI AGENTS', font=sub, fill=(114, 190, 143, 255))
d.rounded_rectangle((840, 397, 1160, 444), radius=10, fill=(20, 39, 35, 255), outline=(84, 151, 116, 255), width=2)
d.text((866, 409), 'rustchain.org', font=small, fill=(228, 234, 224, 255))
d.text((1190, 410), 'VINTAGE SILICON\nSTILL COMPUTES.', font=small, fill=(132, 145, 137, 255), spacing=4)

img.convert('RGB').save(OUT, 'PNG', optimize=True)
print(OUT)
