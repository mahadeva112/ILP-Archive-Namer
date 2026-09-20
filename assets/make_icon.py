"""Generate assets/ILP-Archive-Namer.ico (run once; needs: pip install pillow)."""
import os
from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]
BG_TOP = (79, 70, 229)      # indigo
BG_BOTTOM = (147, 51, 234)  # violet
INK = (255, 255, 255)

def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius, fill=255)
    return m

def gradient(size):
    g = Image.new("RGB", (1, size))
    px = g.load()
    for y in range(size):
        t = y / max(1, size - 1)
        px[0, y] = tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM))
    return g.resize((size, size), Image.NEAREST)

def render(size):
    """Draw a tag/label (naming) over an archive card, supersampled 4x."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(gradient(s), (0, 0), rounded_mask(s, int(s * 0.22)))
    d = ImageDraw.Draw(img)
    u = s / 100.0  # 1 unit == 1% of the icon

    # archive card behind
    d.rounded_rectangle([26 * u, 20 * u, 76 * u, 74 * u], int(6 * u),
                        fill=(255, 255, 255, 90))
    # tag body
    d.rounded_rectangle([20 * u, 34 * u, 62 * u, 80 * u], int(7 * u), fill=INK)
    # tag point (angled corner) + eyelet
    d.polygon([(62 * u, 34 * u), (82 * u, 57 * u), (62 * u, 80 * u)], fill=INK)
    d.ellipse([64 * u, 50 * u, 78 * u, 64 * u], fill=BG_TOP)

    # three "filename" lines on the tag, thinner as they go down
    for i, (x2, w) in enumerate(((54, 7), (49, 6), (44, 5))):
        y = (46 + i * 12) * u
        d.rounded_rectangle([29 * u, y, x2 * u, y + w * u], int(w * u / 2),
                            fill=BG_TOP)
    return img.resize((size, size), Image.LANCZOS)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ILP-Archive-Namer.ico")
frames = [render(n) for n in SIZES]
frames[-1].save(out, format="ICO", sizes=[(n, n) for n in SIZES],
                append_images=frames[:-1])
print("Wrote " + out)
