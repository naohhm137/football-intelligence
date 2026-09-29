"""Generate the original stadium-night backdrop used by the web interface."""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


WIDTH, HEIGHT = 1920, 1080
OUTPUT = Path(__file__).parents[1] / "app" / "static" / "assets" / "stadium-night.png"


def vertical_gradient(top, bottom):
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    for y in range(HEIGHT):
        amount = y / (HEIGHT - 1)
        color = tuple(round(top[i] * (1 - amount) + bottom[i] * amount) for i in range(3))
        for x in range(WIDTH):
            pixels[x, y] = color
    return image


def radial_light(center, radius, color, strength):
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    pixels = layer.load()
    left = max(0, int(center[0] - radius))
    right = min(WIDTH, int(center[0] + radius))
    top = max(0, int(center[1] - radius))
    bottom = min(HEIGHT, int(center[1] + radius))
    for y in range(top, bottom):
        for x in range(left, right):
            distance = math.hypot(x - center[0], y - center[1]) / radius
            if distance < 1:
                alpha = int((1 - distance) ** 2.4 * strength)
                pixels[x, y] = (*color, alpha)
    return layer.filter(ImageFilter.GaussianBlur(radius=18))


def build():
    random.seed(19)
    image = vertical_gradient((5, 13, 15), (4, 31, 23)).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")

    draw.rectangle((0, 300, WIDTH, 640), fill=(4, 16, 17, 255))
    for tier, y in enumerate((330, 405, 480, 555)):
        shade = 21 + tier * 6
        draw.polygon(
            [(0, y), (WIDTH, y - 18), (WIDTH, y + 54), (0, y + 70)],
            fill=(5, shade, 24, 255),
        )
        for x in range(0, WIDTH, 20):
            brightness = random.randint(18, 56)
            draw.rectangle(
                (x, y + random.randint(5, 42), x + 3, y + random.randint(45, 58)),
                fill=(brightness, brightness + 10, brightness, random.randint(45, 100)),
            )

    pitch_top = 610
    draw.polygon(
        [(235, HEIGHT), (1685, HEIGHT), (1245, pitch_top), (675, pitch_top)],
        fill=(10, 72, 47, 255),
    )
    for stripe in range(10):
        t0 = stripe / 10
        t1 = (stripe + 1) / 10
        left0 = 675 + (235 - 675) * t0
        right0 = 1245 + (1685 - 1245) * t0
        left1 = 675 + (235 - 675) * t1
        right1 = 1245 + (1685 - 1245) * t1
        color = (19, 92, 59, 120) if stripe % 2 == 0 else (8, 62, 42, 90)
        draw.polygon(
            [(left0, pitch_top + (HEIGHT - pitch_top) * t0),
             (right0, pitch_top + (HEIGHT - pitch_top) * t0),
             (right1, pitch_top + (HEIGHT - pitch_top) * t1),
             (left1, pitch_top + (HEIGHT - pitch_top) * t1)],
            fill=color,
        )

    line = (188, 214, 188, 125)
    draw.line([(675, pitch_top), (235, HEIGHT)], fill=line, width=3)
    draw.line([(1245, pitch_top), (1685, HEIGHT)], fill=line, width=3)
    draw.line([(960, pitch_top), (960, HEIGHT)], fill=line, width=3)
    draw.ellipse((835, 740, 1085, 925), outline=line, width=3)
    draw.line([(675, pitch_top), (1245, pitch_top)], fill=line, width=3)

    for x in (350, 1570):
        image = Image.alpha_composite(
            image, radial_light((x, 250), 350, (255, 215, 139), 165)
        )
        draw = ImageDraw.Draw(image, "RGBA")
        for row in range(3):
            for col in range(7):
                px = x - 72 + col * 24
                py = 210 + row * 22
                draw.ellipse((px, py, px + 9, py + 9), fill=(255, 235, 187, 235))

    beams = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    beam_draw = ImageDraw.Draw(beams, "RGBA")
    beam_draw.polygon([(270, 235), (430, 235), (815, 930), (575, 930)], fill=(255, 226, 172, 16))
    beam_draw.polygon([(1490, 235), (1650, 235), (1345, 930), (1105, 930)], fill=(255, 226, 172, 14))
    image = Image.alpha_composite(image, beams.filter(ImageFilter.GaussianBlur(28)))

    draw = ImageDraw.Draw(image, "RGBA")
    draw.polygon([(0, 0), (470, 0), (675, 610), (235, HEIGHT), (0, HEIGHT)], fill=(2, 7, 8, 235))
    draw.polygon([(1450, 0), (WIDTH, 0), (WIDTH, HEIGHT), (1685, HEIGHT), (1245, 610)], fill=(2, 7, 8, 235))
    draw.polygon([(0, 0), (WIDTH, 0), (1450, 230), (470, 230)], fill=(2, 6, 7, 224))

    haze = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    haze_draw = ImageDraw.Draw(haze, "RGBA")
    for _ in range(42):
        x = random.randint(420, 1500)
        y = random.randint(420, 820)
        radius = random.randint(15, 70)
        haze_draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(112, 155, 125, random.randint(2, 10)))
    image = Image.alpha_composite(image, haze.filter(ImageFilter.GaussianBlur(35)))

    noise = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    noise_pixels = noise.load()
    for y in range(0, HEIGHT, 2):
        for x in range(0, WIDTH, 2):
            value = random.randint(0, 255)
            alpha = 8 if value > 120 else 4
            noise_pixels[x, y] = (value, value, value, alpha)
    image = Image.alpha_composite(image, noise)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(OUTPUT, quality=94, optimize=True)


if __name__ == "__main__":
    build()
