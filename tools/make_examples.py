"""Regenerate illustrative 1024px demo assets (requires Pillow, demo only)."""
from pathlib import Path
import math
import random
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

DEST = Path(__file__).resolve().parents[1] / "examples" / "images"


def landscape(kind):
    size = 1024
    rng = random.Random(kind)
    im = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(im)
    sky = ((173, 199, 203), (240, 220, 188)) if kind == "coast" else ((110, 146, 170), (242, 206, 159))
    for y in range(size):
        t = min(y / 650, 1)
        color = tuple(round(a * (1 - t) + b * t) for a, b in zip(*sky))
        draw.line((0, y, size, y), fill=color)
    draw.ellipse((725, 155, 815, 245), fill=(255, 237, 192))
    if kind == "coast":
        draw.rectangle((0, 480, size, size), fill=(58, 117, 130))
        for y in range(490, size, 6):
            for _ in range(18):
                x = rng.randrange(size)
                draw.line((x, y, x + rng.randrange(5, 48), y), fill=rng.choice([(79, 140, 149), (113, 164, 165), (51, 107, 122)]), width=rng.choice([1, 2]))
        for offset, color in [(0, (62, 81, 77)), (100, (83, 102, 83)), (210, (115, 127, 92))]:
            points = [(0, 480 + offset)] + [(x, 470 + offset + 50 * math.sin(x / 173) - x * .32) for x in range(0, 690, 4)] + [(0, 890)]
            draw.polygon(points, fill=color)
        shore = [(x, 730 + .33 * x + 60 * math.sin(x / 250)) for x in range(size)]
        draw.polygon(shore + [(size, size), (0, size)], fill=(212, 188, 144))
        draw.line(shore, fill=(235, 234, 209), width=8)
        for _ in range(6000):
            x, y = rng.randrange(size), rng.randrange(750, size)
            if y > 730 + .33 * x + 60 * math.sin(x / 250):
                draw.point((x, y), fill=rng.choice([(180, 162, 125), (235, 213, 170)]))
    else:
        for layer in range(6):
            base = 440 + layer * 110
            points = [(x, base + 95 * math.sin(x / 390 + layer * 1.3)) for x in range(size)]
            color = [(190, 141, 98), (212, 165, 116), (230, 185, 130), (200, 146, 93), (227, 174, 113), (171, 119, 78)][layer]
            draw.polygon(points + [(size, size), (0, size)], fill=color)
            draw.line(points, fill=tuple(min(255, c + 22) for c in color), width=3)
        for y in range(720, 1024, 7):
            points = [(x, y + 11 * math.sin(x / 90 + y / 120)) for x in range(size)]
            draw.line(points, fill=(183, 130, 82), width=1)
    return im


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for kind in ("coast", "dunes"):
        original = landscape(kind)
        original.save(DEST / f"{kind}-ours.png")
        original.filter(ImageFilter.GaussianBlur(3.0)).save(DEST / f"{kind}-baseline.png")
        ImageEnhance.Contrast(original.filter(ImageFilter.GaussianBlur(7))).enhance(.72).save(DEST / f"{kind}-input.png")
    print(f"Wrote six illustrative images to {DEST}")


if __name__ == "__main__":
    main()
