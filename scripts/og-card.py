#!/usr/bin/env python3
"""Generate public/og.png (1200x630) — the share card for X / LinkedIn.

Drawn with PIL from scratch: brand colours, serif headline with one magenta
italic word, mono taskmarket.dev sign-off. No brand-kit files are downloaded;
the colours and type roles come from the published brand-kit text.
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "public", "og.png")
W, H = 1200, 630

GROUND = (18, 16, 14)
MAROON = (58, 20, 32)
CREAM = (239, 233, 226)
MUTED = (176, 167, 157)
MAGENTA = (231, 64, 121)
SALMON = (217, 160, 151)
PAPER = (255, 246, 232)
LINE = (69, 62, 55)


def font(name, size):
    for p in (
        f"/usr/share/fonts/truetype/dejavu/{name}.ttf",
        f"/usr/share/fonts/{name}.ttf",
    ):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


SERIF = lambda s: font("DejaVuSerif", s)
SERIF_B = lambda s: font("DejaVuSerif-Bold", s)
SANS = lambda s: font("DejaVuSans", s)
MONO = lambda s: font("DejaVuSansMono", s)

img = Image.new("RGB", (W, H), GROUND)
d = ImageDraw.Draw(img, "RGBA")
# maroon glow, top right
for r in range(420, 0, -1):
    a = int(70 * (1 - r / 420))
    d.ellipse([W - 260 - r, -r, W - 260 + r, r], fill=MAROON + (a,))
# pixel-grid mark, top left (own 3x3 grid, magenta + paper)
gx, gy, cell, gap = 72, 64, 34, 8
cols = [MAGENTA, PAPER, MAGENTA, PAPER, MAGENTA, SALMON, MAGENTA, PAPER, MAGENTA]
for i, c in enumerate(cols):
    x = gx + (i % 3) * (cell + gap)
    y = gy + (i // 3) * (cell + gap)
    d.rounded_rectangle([x, y, x + cell, y + cell], radius=6, fill=c)
d.text((gx, gy + 3 * cell + 2 * gap + 22), "taskmarket", font=SERIF_B(44), fill=CREAM)
d.text((gx, gy + 3 * cell + 2 * gap + 78), "LIVE MARKET DATA", font=MONO(26), fill=MUTED)

# headline
d.text((72, 300), "The market,", font=SERIF(96), fill=CREAM)
d.text((72, 404), "live.", font=SERIF(96), fill=MAGENTA)
d.text((72, 520), "Tempo + Base  ·  trends, breakdowns, heatmap, live feed",
       font=SANS(28), fill=SALMON)
# bottom rule + sign-off
d.line([72, 580, W - 72, 580], fill=LINE, width=2)
d.text((72, 592), "taskmarket.dev", font=MONO(24), fill=MUTED)
d.text((W - 72 - 320, 592), "updated every 10 min", font=MONO(24), fill=MUTED)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(OUT, "PNG")
print(f"wrote {OUT} ({os.path.getsize(OUT)} bytes)")
