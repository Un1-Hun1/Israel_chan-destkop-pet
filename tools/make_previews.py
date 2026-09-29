"""Render README images into docs/: a sprite sheet and an animated GIF."""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sprites  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "docs")
BG = (206, 228, 255)
SCALE = 5


def on_bg(img, size=None):
    size = size or img.size
    out = Image.new("RGB", size, BG)
    mask = Image.eval(img.convert("L"), lambda v: 255)
    px, mpx = img.load(), mask.load()
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y] == sprites.KEY:
                mpx[x, y] = 0
    out.paste(img, ((size[0] - img.width) // 2, size[1] - img.height), mask)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    fr = sprites.frames(SCALE)

    names = ["idle", "walk1", "happy1", "sleep1", "rocket1", "para1"]
    h = max(fr[n].height for n in names) + 20
    w = sum(fr[n].width for n in names) + 20 * (len(names) + 1)
    sheet = Image.new("RGB", (w, h), BG)
    x = 20
    for n in names:
        sheet.paste(on_bg(fr[n]), (x, h - fr[n].height - 10))
        x += fr[n].width + 20
    sheet.save(os.path.join(OUT, "preview.png"))

    seq = ["walk1", "walk2"] * 4 + ["happy1", "happy2"] * 3 + \
          ["rocket1", "rocket2"] * 6 + ["para1", "para2"] * 3
    size = (max(fr[n].width for n in seq) + 40, max(fr[n].height for n in seq) + 20)
    gif = [on_bg(fr[n], size) for n in seq]
    gif[0].save(os.path.join(OUT, "demo.gif"), save_all=True, append_images=gif[1:],
                duration=180, loop=0)


if __name__ == "__main__":
    main()
