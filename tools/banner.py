#!/usr/bin/env python3
"""Render the README banner (also the GitHub social preview) from the library screenshot:

    python3 tools/banner.py [docs/library.png] [docs/banner.png] [github|xhs]

github = 1280 x 640; xhs = 1600 x 1200 (4:3, padded, repo address at the foot). Needs Pillow (`pip install pillow`) and a
sans + mono TrueType font (DejaVu on Linux, Arial / Menlo / Consolas elsewhere). The left column is text, the right side
the whole Zotero window with the item pane's tag block repeated at actual size."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "library.png")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "docs" / "banner.png")
KIND = sys.argv[3] if len(sys.argv) > 3 else "github"
S, W, H, OY = {"github": (1.0, 1280, 640, 0), "xhs": (1.25, 1600, 1200, 150)}[KIND]
BG, FG, SOFT, MUTED, LINE, ACCENT = (15, 23, 42), (248, 250, 252), (226, 232, 240), (148, 163, 184), (71, 85, 105), (204, 41, 54)


def font_file(*names):
    dirs = ["/usr/share/fonts/truetype/dejavu", "/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "/Library/Fonts",
            "C:/Windows/Fonts", str(Path.home() / ".fonts"), str(Path.home() / "Library/Fonts")]
    for n in names:
        for d in dirs:
            p = Path(d) / n
            if p.exists(): return str(p)
    sys.exit(f"no font found among {names}; install DejaVu or edit tools/banner.py")


SANS_B = font_file("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "Helvetica.ttc")
SANS = font_file("DejaVuSans.ttf", "Arial.ttf", "arial.ttf", "Helvetica.ttc")
MONO = font_file("DejaVuSansMono.ttf", "Menlo.ttc", "consola.ttf", "Courier New.ttf")
f = lambda p, s: ImageFont.truetype(p, round(s * S))
X = lambda v: round(v * S)             # composition coordinate (1280 x 640) -> canvas
Y = lambda v: round(v * S) + OY

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def text(x, y, s, font, fill): d.text((X(x), Y(y)), s, font=font, fill=fill)


def framed(im, x, y, radius=10):
    """paste with rounded corners, a hairline border and a soft shadow; returns the canvas position"""
    x, y, r = X(x), Y(y), X(radius)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((x + X(4), y + X(10), x + im.width + X(4), y + im.height + X(10)), radius=r, fill=(0, 0, 0, 170))
    sh = sh.filter(ImageFilter.GaussianBlur(X(14)))
    img.paste(sh, (0, 0), sh)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=r, fill=255)
    img.paste(im, (x, y), mask)
    d.rounded_rectangle((x, y, x + im.width - 1, y + im.height - 1), radius=r, outline=LINE, width=max(1, X(1)))
    return x, y


# left column: name, tagline, tag pills, agents, platforms
x0 = 52
text(x0, 84, "zotero-librarian", f(SANS_B, 50), FG)
d.rectangle((X(x0), Y(154), X(x0 + 56), Y(158)), fill=ACCENT)
for i, line in enumerate(("Your coding agent files", "papers into Zotero.", "The scripts judge;", "the agent only runs them.")):
    text(x0, 182 + 35 * i, line, f(SANS, 26), SOFT if i < 2 else MUTED)
pills = [("status:to-read", (30, 58, 95)), ("method:vla", (60, 40, 90)), ("embod:dex-hand", (20, 70, 60)),
         ("tech:diffusion", (90, 45, 30)), ("modality:tactile", (70, 55, 20))]
px, py, mono = x0, 352, f(MONO, 17)
for t, col in pills:
    tw = d.textlength(t, font=mono) / S
    if px + tw + 24 > 520: px, py = x0, py + 40
    d.rounded_rectangle((X(px), Y(py), X(px + tw + 22), Y(py + 30)), radius=X(15), fill=col, outline=LINE)
    text(px + 11, py + 5, t, mono, SOFT)
    px += tw + 34
text(x0, 482, "with the sentence that justifies each tag", f(SANS, 18), MUTED)
d.line((X(x0), Y(524), X(500), Y(524)), fill=LINE, width=max(1, X(1)))
text(x0, 540, "Claude Code  ·  Codex", f(SANS_B, 18), SOFT)
text(x0, 570, "Ubuntu · macOS · Windows  ·  Ollama  ·  MIT", f(SANS, 17), MUTED)

# right: the whole window (menu bar dropped), then the item pane's tag block at actual size, boxed and connected
src = Image.open(SRC).convert("RGB")
win = src.crop((0, 75, 1920, 1048))
scale = X(690) / win.width
win = win.resize((X(690), round(win.height * scale)), Image.LANCZOS)
wx, wy = framed(win, 556, 64)
box = (1568, 400, 1890, 582)
inset = src.crop(box)
if S != 1: inset = inset.resize((X(inset.width), X(inset.height)), Image.LANCZOS)
IX, IY = 1280 - 40 - inset.width / S, 442
ix, iy = framed(inset, IX, IY, radius=8)
bx0, by0 = wx + round(box[0] * scale), wy + round((box[1] - 75) * scale)
bx1, by1 = wx + round(box[2] * scale), wy + round((box[3] - 75) * scale)
d.rectangle((bx0, by0, bx1, by1), outline=ACCENT, width=X(2))
d.line(((bx0 + bx1) // 2, by1 + 2, (bx0 + bx1) // 2, iy - 1), fill=ACCENT, width=X(2))
text(IX, IY - 24, "the item pane, actual size", f(SANS, 14), MUTED)
text(556, IY + 8, "[date] [venue] Title", f(SANS_B, 16), SOFT)
for i, s in enumerate(("project page in the URL field", "one reading status per paper", "PDFs synced by Zotero itself", "every write logged, nothing deleted")):
    text(556, IY + 32 + 22 * i, s, f(SANS, 15), MUTED)

if KIND == "xhs":                       # links are not clickable there: the address goes on the picture
    url, fu = "github.com/jxxsteven7/zotero-librarian", f(MONO, 22)
    d.line((X(52), H - OY + X(40), W - X(52), H - OY + X(40)), fill=LINE, width=1)
    d.text(((W - d.textlength(url, font=fu)) / 2, H - OY + X(64)), url, font=fu, fill=SOFT)
    sub, fs = "open source · MIT · issues and PRs welcome", f(SANS, 15)
    d.text(((W - d.textlength(sub, font=fs)) / 2, H - OY + X(100)), sub, font=fs, fill=MUTED)

img.save(OUT, optimize=True)
print(OUT, img.size)
