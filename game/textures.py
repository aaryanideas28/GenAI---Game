"""Procedurally generated textures (PIL) - original artwork, no external files.

Every function returns an RGBA ``PIL.Image``; results are cached so each texture
is only drawn once. ``to_ursina()`` converts to an Ursina ``Texture``.
"""

from __future__ import annotations

import math
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageOps
from game.asset_loader import custom_assets

_custom_tex_cache: dict = {}

def get_custom_texture(name: str):
    if name not in _custom_tex_cache:
        from pathlib import Path
        from ursina import Texture
        p = Path(__file__).resolve().parent / "assets" / "custom" / name
        if p.is_file():
            _custom_tex_cache[name] = Texture(str(p.resolve()))
        else:
            _custom_tex_cache[name] = None
    return _custom_tex_cache[name]


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _shade(rgb: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(v * f))) for v in rgb)


def _noise(w: int, h: int, dark: str, light: str, sigma: int = 60, blur: float = 0.6) -> Image.Image:
    img = Image.effect_noise((w, h), sigma).convert("L")
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return ImageOps.colorize(img, dark, light).convert("RGBA")


# --- Track / ground ----------------------------------------------------------
@lru_cache(maxsize=None)
def track() -> Image.Image:
    """One lane of railway: gravel, wooden sleepers, two steel rails. Tiles vertically."""
    w, h = 256, 256
    img = _noise(w, h, "#3d352e", "#a0968a", sigma=70)
    d = ImageDraw.Draw(img)
    rnd = random.Random(7)
    for i in range(4):                                   # sleepers every 64 px
        y = i * 64 + 20
        d.rectangle([18, y, 238, y + 22], fill=(104, 72, 46, 255))
        d.rectangle([18, y + 18, 238, y + 22], fill=(70, 48, 30, 255))  # bottom shadow
        for _ in range(6):                               # wood grain
            gy = y + rnd.randint(3, 16)
            d.line([(22, gy), (234, gy + rnd.randint(-1, 1))], fill=(84, 58, 36, 255), width=1)
    for x in (58, 186):                                  # rails
        d.rectangle([x, 0, x + 12, h], fill=(70, 72, 78, 255))
        d.rectangle([x + 3, 0, x + 9, h], fill=(150, 154, 160, 255))
        d.line([(x + 6, 0), (x + 6, h)], fill=(225, 228, 232, 255), width=2)
    return img


@lru_cache(maxsize=None)
def gravel() -> Image.Image:
    return _noise(128, 128, "#2e2924", "#7d746a", sigma=80)


@lru_cache(maxsize=None)
def concrete() -> Image.Image:
    img = _noise(128, 128, "#8c8a85", "#c9c6bf", sigma=30, blur=1.0)
    d = ImageDraw.Draw(img)
    d.line([(0, 0), (128, 0)], fill=(110, 108, 104, 255), width=3)
    d.line([(0, 64), (128, 64)], fill=(120, 118, 114, 255), width=2)
    return img


# --- Barriers ----------------------------------------------------------------
@lru_cache(maxsize=None)
def barrier() -> Image.Image:
    """Warning stripes: uses custom Subway Surfers asset if available, else procedural."""
    custom_b = custom_assets.get_barrier_stripes()
    if custom_b is not None:
        return custom_b
    w, h = 256, 96
    img = Image.new("RGBA", (w, h), (245, 245, 245, 255))
    d = ImageDraw.Draw(img)
    for x in range(-h, w + h, 48):
        d.polygon([(x, h), (x + 24, h), (x + 24 + h, 0), (x + h, 0)], fill=(214, 40, 40, 255))
    d.rectangle([0, 0, w - 1, h - 1], outline=(40, 40, 46, 255), width=6)
    return img


# --- Trains ------------------------------------------------------------------
def _scribble(d: ImageDraw.ImageDraw, rnd: random.Random, box: tuple[int, int, int, int]) -> None:
    """Random abstract spray-paint swooshes (original, procedurally generated)."""
    x0, y0, x1, y1 = box
    palette = [(255, 214, 0), (255, 90, 160), (60, 230, 255), (140, 255, 90), (255, 140, 30)]
    for _ in range(rnd.randint(1, 3)):
        col = rnd.choice(palette)
        cx, cy = rnd.randint(x0, x1), rnd.randint(y0, y1)
        pts = []
        for k in range(14):
            t = k / 13
            pts.append((cx + (t - 0.5) * rnd.randint(60, 140),
                        cy + math.sin(t * math.pi * rnd.uniform(1.5, 3)) * rnd.randint(6, 18)))
        d.line(pts, fill=(20, 20, 20, 255), width=13, joint="curve")
        d.line(pts, fill=col + (255,), width=8, joint="curve")


@lru_cache(maxsize=None)
def train_side(color_hex: str, seed: int = 0) -> Image.Image:
    """One carriage side: uses custom Subway Surfers train panel if available, else procedural."""
    custom_s = custom_assets.get_train_side()
    if custom_s is not None:
        return custom_s
    w, h = 512, 256
    body = _hex(color_hex)
    img = Image.new("RGBA", (w, h), (214, 219, 226, 255))
    d = ImageDraw.Draw(img)
    rnd = random.Random(seed)
    d.rectangle([0, 0, w, 26], fill=_shade(body, 0.75) + (255,))           # roof edge
    d.rectangle([0, 150, w, 190], fill=body + (255,))                       # colour band
    d.rectangle([0, 186, w, 192], fill=_shade(body, 0.6) + (255,))
    d.rectangle([0, 226, w, h], fill=(38, 38, 42, 255))                     # undercarriage
    for x in range(24, w, 84):                                              # windows
        if 200 < x < 290:
            continue
        d.rounded_rectangle([x, 48, x + 60, 128], radius=8, fill=(28, 44, 62, 255),
                            outline=(90, 96, 104, 255), width=3)
        d.polygon([(x + 8, 120), (x + 22, 120), (x + 52, 56), (x + 38, 56)], fill=(70, 100, 130, 255))
    d.rectangle([214, 40, 286, 224], fill=(190, 196, 204, 255), outline=(90, 96, 104, 255), width=3)
    d.line([(250, 40), (250, 224)], fill=(90, 96, 104, 255), width=3)       # door
    d.rectangle([222, 54, 244, 110], fill=(28, 44, 62, 255))
    d.rectangle([256, 54, 278, 110], fill=(28, 44, 62, 255))
    if rnd.random() < 0.8:
        _scribble(d, rnd, (40, 150, 470, 215))
    d.line([(0, 0), (0, h)], fill=(60, 60, 66, 255), width=6)               # carriage joints
    d.line([(w - 1, 0), (w - 1, h)], fill=(60, 60, 66, 255), width=6)
    return img


@lru_cache(maxsize=None)
def train_front(color_hex: str) -> Image.Image:
    """Train front: uses custom Subway Surfers front if available, else procedural."""
    custom_f = custom_assets.get_train_front()
    if custom_f is not None:
        return custom_f
    w, h = 256, 256
    body = _hex(color_hex)
    img = Image.new("RGBA", (w, h), body + (255,))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 30], fill=_shade(body, 0.7) + (255,))
    d.polygon([(30, 40), (226, 40), (236, 130), (20, 130)], fill=(26, 40, 58, 255),
              outline=(30, 30, 34, 255))
    d.polygon([(50, 50), (90, 50), (60, 120), (30, 120)], fill=(80, 112, 146, 255))
    d.rectangle([0, 150, w, 196], fill=(225, 228, 232, 255))
    for cx in (52, 204):
        d.ellipse([cx - 18, 155, cx + 18, 191], fill=(255, 236, 140, 255), outline=(60, 60, 60, 255), width=3)
    d.rectangle([98, 160, 158, 186], fill=(30, 30, 34, 255))
    d.text((112, 165), "R7", fill=(255, 200, 40, 255))
    d.rectangle([0, 226, w, h], fill=(38, 38, 42, 255))
    return img


@lru_cache(maxsize=None)
def ballast() -> Image.Image:
    """Terracotta railway ballast with gravel and moss."""
    im = custom_assets.load_image("ballast_ground.png")
    if im is not None:
        return im
    return gravel()


@lru_cache(maxsize=None)
def subway_city_sign() -> Image.Image:
    im = custom_assets.load_image("sign_subway_city.png")
    if im is not None:
        return im
    return Image.new("RGBA", (256, 64), (18, 120, 68, 255))


@lru_cache(maxsize=None)
def crossbuck_sign() -> Image.Image:
    im = custom_assets.load_image("crossbuck_sign.png")
    if im is not None:
        return im
    return barrier()


@lru_cache(maxsize=None)
def silver_train_front() -> Image.Image:
    im = custom_assets.load_image("silver_train_front.png")
    if im is not None:
        return im
    return train_front("#ccd2db")


@lru_cache(maxsize=None)
def container_side() -> Image.Image:
    im = custom_assets.load_image("red_container_side.png")
    if im is not None:
        return im
    return train_side("#b53b28")


@lru_cache(maxsize=None)
def train_roof() -> Image.Image:
    img = _noise(64, 64, "#92979e", "#d8dce2", sigma=20, blur=1.0)
    d = ImageDraw.Draw(img)
    for y in range(0, 64, 16):
        d.line([(0, y), (64, y)], fill=(120, 125, 132, 255), width=2)
    return img


# --- Buildings ---------------------------------------------------------------
@lru_cache(maxsize=None)
def building(color_hex: str, seed: int = 0) -> Image.Image:
    """Brick facade with a grid of windows (some lit). Tiles in both directions."""
    w, h = 256, 256
    base = _hex(color_hex)
    img = Image.new("RGBA", (w, h), base + (255,))
    d = ImageDraw.Draw(img)
    mortar = _shade(base, 0.82) + (255,)
    for row, y in enumerate(range(0, h, 16)):                   # bricks
        d.line([(0, y), (w, y)], fill=mortar, width=2)
        off = 16 if row % 2 else 0
        for x in range(off, w, 32):
            d.line([(x, y), (x, y + 16)], fill=mortar, width=2)
    rnd = random.Random(seed)
    for gx in range(2):
        for gy in range(2):
            x, y = 34 + gx * 128, 30 + gy * 128
            lit = rnd.random() < 0.35
            glass = (255, 226, 140, 255) if lit else (52, 74, 98, 255)
            d.rectangle([x - 6, y - 6, x + 66, y + 82], fill=(230, 226, 214, 255))
            d.rectangle([x, y, x + 60, y + 76], fill=glass)
            d.line([(x + 30, y), (x + 30, y + 76)], fill=(230, 226, 214, 255), width=4)
            d.line([(x, y + 38), (x + 60, y + 38)], fill=(230, 226, 214, 255), width=4)
            if not lit:
                d.polygon([(x + 4, y + 34), (x + 14, y + 34), (x + 26, y + 4), (x + 16, y + 4)],
                          fill=(96, 124, 150, 255))
    return img


# --- Sky ---------------------------------------------------------------------
@lru_cache(maxsize=None)
def sky_gradient(top_hex: str, bottom_hex: str) -> Image.Image:
    custom_sky = custom_assets.get_sky_panorama()
    if custom_sky is not None:
        return custom_sky
    top, bottom = _hex(top_hex), _hex(bottom_hex)
    h = 256
    img = Image.new("RGBA", (4, h))
    for y in range(h):
        t = min(1.0, max(0.0, (y / h - 0.35) / 0.3))   # bottom half = horizon colour
        c = tuple(int(bottom[i] + (top[i] - bottom[i]) * t) for i in range(3))
        for x in range(4):
            img.putpixel((x, h - 1 - y), c + (255,))
    return img


_URSINA_CACHE: dict = {}


def to_ursina(name: str, image: Image.Image):
    """Wrap a PIL image as an Ursina Texture (cached per name)."""
    from ursina import Texture
    if name not in _URSINA_CACHE:
        tex = Texture(image.convert("RGBA"))
        tex.filtering = "mipmap"
        tex._texture.setAnisotropicDegree(16)
        _URSINA_CACHE[name] = tex
    return _URSINA_CACHE[name]
