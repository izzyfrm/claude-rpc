"""Generates the pixel Claude Code mascot (assets/logo.png + assets/logo.ico)."""
from PIL import Image, ImageDraw

GRID = [
    "..XXXXXXXXXX..",
    "..XXXXXXXXXX..",
    "..XX.XXXX.XX..",
    "XXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXX",
    "..XXXXXXXXXX..",
    "..XXXXXXXXXX..",
    "...X.X..X.X...",
    "...X.X..X.X...",
]
ORANGE = (217, 119, 87, 255)
BG = (38, 38, 36, 255)

def render(size, bg=True):
    img = Image.new("RGBA", (size, size), BG if bg else (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cols, rows = len(GRID[0]), len(GRID)
    px = size * 0.72 / cols
    ox, oy = (size - px * cols) / 2, (size - px * rows) / 2
    for y, row in enumerate(GRID):
        for x, c in enumerate(row):
            if c == "X":
                d.rectangle([ox + x * px, oy + y * px, ox + (x + 1) * px - 1, oy + (y + 1) * px - 1], fill=ORANGE)
    if bg:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 6, fill=255)
        img.putalpha(mask)
    return img

if __name__ == "__main__":
    render(512).save("assets/logo.png")
    render(256, bg=False).save("assets/logo.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
