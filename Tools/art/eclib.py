"""
eclib.py - shared pixel-art toolkit for EVIL CATS.

Every sprite in the game is produced by Python code in Tools/art (no downloaded or
AI-generated images), so the art is original, reproducible and editable: change the
code, run `python Tools/art/build_all.py`, and the atlases in the Unity project update.

Conventions (see docs/ASSET_SPEC.md for the full contract):
  * Images are numpy uint8 arrays shaped (H, W, 4) RGBA, origin top-left, y down.
  * 16 pixels = 1 Unity world unit (PPU 16). Draw at 1:1 pixel scale, never resample.
  * Hard pixels only: no anti-aliasing on characters/props. Soft alpha is allowed for FX.
  * Light comes from the top-left. Outlines use PAL['outline'] unless a sprite needs a
    coloured outline (glowing FX).
  * All randomness must go through random.Random(seed) so output is deterministic.
"""
from __future__ import annotations

import inspect
import json
import math
import os
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

Color = Tuple[int, int, int, int]
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ART_OUT = os.path.join(ROOT, "EvilCats", "Assets", "_EvilCats", "Art", "Resources", "ECArt")
ICON_OUT = os.path.join(ROOT, "EvilCats", "Assets", "_EvilCats", "Art", "Icons")
STORE_OUT = os.path.join(ROOT, "store")
PREVIEW_OUT = os.path.join(os.path.dirname(__file__), "previews")
FONT_DIR = os.path.join(ROOT, "EvilCats", "Assets", "_EvilCats", "UI", "Resources", "ECUI", "Fonts")
PPU = 16


def hexc(h: str, a: int = 255) -> Color:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


# --------------------------------------------------------------------------------------
# Master palette. Ramps go dark -> light. Keep backgrounds on the *_bg ramps (quieter,
# less saturated) and threats on the saturated ramps so enemies read above terrain.
# --------------------------------------------------------------------------------------
PAL: Dict[str, Color] = {
    "clear": (0, 0, 0, 0),
    "outline": hexc("#140c1c"),
    "outline_soft": hexc("#241a30"),
    "black": hexc("#0b0710"),
    "white": hexc("#f4f4f8"),
    # Arc Light Cat
    "fur0": hexc("#16141c"), "fur1": hexc("#24222c"), "fur2": hexc("#34313e"), "fur3": hexc("#4a4656"),
    "silver0": hexc("#6f7688"), "silver1": hexc("#9aa3b4"), "silver2": hexc("#c9d1dc"), "silver3": hexc("#eef2f7"),
    "cyan0": hexc("#0b4f66"), "cyan1": hexc("#1590b3"), "cyan2": hexc("#35d0f0"), "cyan3": hexc("#8ff6ff"), "cyan4": hexc("#e6ffff"),
    "violet0": hexc("#241036"), "violet1": hexc("#3d1f5c"), "violet2": hexc("#5a2f86"), "violet3": hexc("#7b46b0"), "violet4": hexc("#a57ad6"),
    # rewards / gold
    "gold0": hexc("#6b4210"), "gold1": hexc("#9c6a14"), "gold2": hexc("#e0a526"), "gold3": hexc("#ffd24a"), "gold4": hexc("#fff0a8"),
    # danger
    "red0": hexc("#4d0a14"), "red1": hexc("#8f1426"), "red2": hexc("#d42a3a"), "red3": hexc("#ff5d5d"), "red4": hexc("#ffa3a0"),
    # elements
    "fire0": hexc("#7a1d0a"), "fire1": hexc("#c2410c"), "fire2": hexc("#ff7a1a"), "fire3": hexc("#ffb347"), "fire4": hexc("#fff0b0"),
    "frost0": hexc("#1d4d7a"), "frost1": hexc("#3f8fc4"), "frost2": hexc("#7fcaee"), "frost3": hexc("#c4f0ff"), "frost4": hexc("#f2fdff"),
    "bone0": hexc("#5e5244"), "bone1": hexc("#8f7f68"), "bone2": hexc("#c2b08f"), "bone3": hexc("#e8dcc0"), "bone4": hexc("#fff8e6"),
    "ward0": hexc("#1e4a44"), "ward1": hexc("#2f7a6c"), "ward2": hexc("#56b89c"), "ward3": hexc("#a6ecd0"), "ward4": hexc("#fff4c2"),
    "grav0": hexc("#2a0f52"), "grav1": hexc("#4b1f94"), "grav2": hexc("#7a3fe0"), "grav3": hexc("#b07cff"), "grav4": hexc("#e2ccff"),
    # neutral materials
    "stone0": hexc("#1f1d29"), "stone1": hexc("#2e2b3b"), "stone2": hexc("#433f55"), "stone3": hexc("#5d5872"), "stone4": hexc("#7c7794"),
    "wood0": hexc("#2a1a14"), "wood1": hexc("#44291c"), "wood2": hexc("#653f28"), "wood3": hexc("#8a5a38"),
    "iron0": hexc("#1c1f26"), "iron1": hexc("#2f3440"), "iron2": hexc("#4a5263"), "iron3": hexc("#6f7a8f"), "iron4": hexc("#a4afc2"),
    "leather0": hexc("#2e1c16"), "leather1": hexc("#4d2e22"), "leather2": hexc("#6e4431"),
    "orange0": hexc("#6b2a08"), "orange1": hexc("#a8480f"), "orange2": hexc("#e0761e"), "orange3": hexc("#ffa24a"), "orange4": hexc("#ffd29a"),
    "tabby0": hexc("#3c3f4a"), "tabby1": hexc("#646a78"), "tabby2": hexc("#9199a8"), "tabby3": hexc("#c3cad6"),
    "snow0": hexc("#8c9ab0"), "snow1": hexc("#c2cedd"), "snow2": hexc("#e6eef7"), "snow3": hexc("#ffffff"),
    "brown0": hexc("#3a2418"), "brown1": hexc("#5c3a26"), "brown2": hexc("#86573a"), "brown3": hexc("#b07c52"),
    "rat0": hexc("#2c2530"), "rat1": hexc("#4a3f4e"), "rat2": hexc("#6d6072"), "rat3": hexc("#9a8b9c"),
    "pink0": hexc("#8c4a5e"), "pink1": hexc("#c77a8e"), "pink2": hexc("#f0aabb"),
    "crow0": hexc("#120f1a"), "crow1": hexc("#1f1a2e"), "crow2": hexc("#332b4a"), "crow3": hexc("#4d4270"),
    # terrain (quiet, desaturated)
    "gw_grass0": hexc("#141c1d"), "gw_grass1": hexc("#1a2626"), "gw_grass2": hexc("#20302d"), "gw_grass3": hexc("#2a3d38"),
    "gw_moon": hexc("#3a5a7a"), "gw_path0": hexc("#2a2530"), "gw_path1": hexc("#35303d"), "gw_path2": hexc("#433d4c"),
    "mf_stone0": hexc("#1c1a26"), "mf_stone1": hexc("#262334"), "mf_stone2": hexc("#312d42"), "mf_stone3": hexc("#3d3852"),
    "mf_sky": hexc("#2a1f45"), "mf_storm": hexc("#8fa8ff"), "mf_path0": hexc("#34304a"), "mf_path1": hexc("#403b58"), "mf_path2": hexc("#4d4768"),
}

# Named ramps for shading helpers (dark -> light)
RAMPS: Dict[str, List[Color]] = {
    "fur": [PAL["fur0"], PAL["fur1"], PAL["fur2"], PAL["fur3"]],
    "silver": [PAL["silver0"], PAL["silver1"], PAL["silver2"], PAL["silver3"]],
    "cyan": [PAL["cyan0"], PAL["cyan1"], PAL["cyan2"], PAL["cyan3"], PAL["cyan4"]],
    "violet": [PAL["violet0"], PAL["violet1"], PAL["violet2"], PAL["violet3"], PAL["violet4"]],
    "gold": [PAL["gold0"], PAL["gold1"], PAL["gold2"], PAL["gold3"], PAL["gold4"]],
    "red": [PAL["red0"], PAL["red1"], PAL["red2"], PAL["red3"], PAL["red4"]],
    "fire": [PAL["fire0"], PAL["fire1"], PAL["fire2"], PAL["fire3"], PAL["fire4"]],
    "frost": [PAL["frost0"], PAL["frost1"], PAL["frost2"], PAL["frost3"], PAL["frost4"]],
    "bone": [PAL["bone0"], PAL["bone1"], PAL["bone2"], PAL["bone3"], PAL["bone4"]],
    "ward": [PAL["ward0"], PAL["ward1"], PAL["ward2"], PAL["ward3"], PAL["ward4"]],
    "grav": [PAL["grav0"], PAL["grav1"], PAL["grav2"], PAL["grav3"], PAL["grav4"]],
    "stone": [PAL["stone0"], PAL["stone1"], PAL["stone2"], PAL["stone3"], PAL["stone4"]],
    "wood": [PAL["wood0"], PAL["wood1"], PAL["wood2"], PAL["wood3"]],
    "iron": [PAL["iron0"], PAL["iron1"], PAL["iron2"], PAL["iron3"], PAL["iron4"]],
    "orange": [PAL["orange0"], PAL["orange1"], PAL["orange2"], PAL["orange3"], PAL["orange4"]],
    "tabby": [PAL["tabby0"], PAL["tabby1"], PAL["tabby2"], PAL["tabby3"]],
    "snow": [PAL["snow0"], PAL["snow1"], PAL["snow2"], PAL["snow3"]],
    "brown": [PAL["brown0"], PAL["brown1"], PAL["brown2"], PAL["brown3"]],
    "rat": [PAL["rat0"], PAL["rat1"], PAL["rat2"], PAL["rat3"]],
    "crow": [PAL["crow0"], PAL["crow1"], PAL["crow2"], PAL["crow3"]],
    "leather": [PAL["leather0"], PAL["leather1"], PAL["leather2"]],
    "pink": [PAL["pink0"], PAL["pink1"], PAL["pink2"]],
}

FAMILY_COLORS: Dict[str, str] = {  # UI accent ramp per perk family / module element
    "arc": "cyan", "ember": "fire", "frost": "frost", "bone": "bone", "ward": "ward", "gravity": "grav",
}


# --------------------------------------------------------------------------------------
# Image basics
# --------------------------------------------------------------------------------------
def new(w: int, h: int, color: Color = (0, 0, 0, 0)) -> np.ndarray:
    img = np.zeros((h, w, 4), dtype=np.uint8)
    if color[3]:
        img[:, :] = color
    return img


def copy(img: np.ndarray) -> np.ndarray:
    return img.copy()


def size(img: np.ndarray) -> Tuple[int, int]:
    return img.shape[1], img.shape[0]


def inb(img: np.ndarray, x: int, y: int) -> bool:
    return 0 <= x < img.shape[1] and 0 <= y < img.shape[0]


def px(img: np.ndarray, x: int, y: int, c: Color) -> None:
    """Set one pixel (alpha-composited if c is translucent)."""
    x, y = int(x), int(y)
    if not inb(img, x, y):
        return
    if c[3] >= 255 or img[y, x, 3] == 0:
        img[y, x] = c
    elif c[3] > 0:
        _blend_px(img, x, y, c)


def _blend_px(img, x, y, c):
    a = c[3] / 255.0
    dst = img[y, x].astype(np.float32)
    da = dst[3] / 255.0
    oa = a + da * (1 - a)
    if oa <= 0:
        return
    rgb = (np.array(c[:3], np.float32) * a + dst[:3] * da * (1 - a)) / oa
    img[y, x] = [int(round(v)) for v in rgb] + [int(round(oa * 255))]


def get(img: np.ndarray, x: int, y: int) -> Color:
    if not inb(img, x, y):
        return (0, 0, 0, 0)
    return tuple(int(v) for v in img[int(y), int(x)])  # type: ignore


def rect(img, x, y, w, h, c: Color) -> None:
    for yy in range(int(y), int(y + h)):
        for xx in range(int(x), int(x + w)):
            px(img, xx, yy, c)


def rect_outline(img, x, y, w, h, c: Color) -> None:
    for xx in range(int(x), int(x + w)):
        px(img, xx, y, c)
        px(img, xx, y + h - 1, c)
    for yy in range(int(y), int(y + h)):
        px(img, x, yy, c)
        px(img, x + w - 1, yy, c)


def line(img, x0, y0, x1, y1, c: Color) -> None:
    """Bresenham line (pixel-perfect)."""
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        px(img, x0, y0, c)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def ellipse(img, cx, cy, rx, ry, c: Color, fill: bool = True) -> None:
    """Pixel ellipse centred on (cx, cy) (float centres allowed, e.g. 7.5 for even widths)."""
    if rx <= 0 or ry <= 0:
        px(img, cx, cy, c)
        return
    x0, x1 = int(math.floor(cx - rx)), int(math.ceil(cx + rx))
    y0, y1 = int(math.floor(cy - ry)), int(math.ceil(cy + ry))
    inside = np.zeros((y1 - y0 + 1, x1 - x0 + 1), bool)
    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            nx = (xx + 0.5 - (cx + 0.5)) / (rx + 0.25)
            ny = (yy + 0.5 - (cy + 0.5)) / (ry + 0.25)
            inside[yy - y0, xx - x0] = nx * nx + ny * ny <= 1.0
    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            if not inside[yy - y0, xx - x0]:
                continue
            if fill:
                px(img, xx, yy, c)
            else:
                edge = False
                for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ix, iy = xx + ox - x0, yy + oy - y0
                    if not (0 <= ix < inside.shape[1] and 0 <= iy < inside.shape[0]) or not inside[iy, ix]:
                        edge = True
                        break
                if edge:
                    px(img, xx, yy, c)


def circle(img, cx, cy, r, c: Color, fill: bool = True) -> None:
    ellipse(img, cx, cy, r, r, c, fill)


def polygon(img, pts: Sequence[Tuple[float, float]], c: Color) -> None:
    """Scanline polygon fill (even-odd), pixel centres sampled."""
    if len(pts) < 3:
        return
    ys = [p[1] for p in pts]
    for yy in range(int(math.floor(min(ys))), int(math.ceil(max(ys))) + 1):
        sy = yy + 0.5
        xs = []
        n = len(pts)
        for i in range(n):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            if (ay <= sy < by) or (by <= sy < ay):
                xs.append(ax + (sy - ay) * (bx - ax) / (by - ay))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            for xx in range(int(math.ceil(xs[i] - 0.5)), int(math.floor(xs[i + 1] - 0.5)) + 1):
                px(img, xx, yy, c)


def flood(img, x, y, c: Color) -> None:
    target = get(img, x, y)
    if target == c:
        return
    stack = [(x, y)]
    while stack:
        xx, yy = stack.pop()
        if not inb(img, xx, yy) or get(img, xx, yy) != target:
            continue
        img[yy, xx] = c
        stack.extend(((xx + 1, yy), (xx - 1, yy), (xx, yy + 1), (xx, yy - 1)))


def paste(dst: np.ndarray, src: np.ndarray, x: int, y: int) -> None:
    """Alpha-composite src onto dst at (x, y) (top-left)."""
    sh, sw = src.shape[:2]
    for yy in range(sh):
        ty = y + yy
        if ty < 0 or ty >= dst.shape[0]:
            continue
        for xx in range(sw):
            a = src[yy, xx, 3]
            if a == 0:
                continue
            tx = x + xx
            if 0 <= tx < dst.shape[1]:
                if a == 255:
                    dst[ty, tx] = src[yy, xx]
                else:
                    _blend_px(dst, tx, ty, tuple(int(v) for v in src[yy, xx]))


def ascii_art(rows: Sequence[str], legend: Dict[str, Optional[Color]]) -> np.ndarray:
    """Build an image from rows of characters. '.' and ' ' are transparent by default."""
    h = len(rows)
    w = max(len(r) for r in rows)
    img = new(w, h)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in ".  ":
                continue
            col = legend.get(ch)
            if col is None:
                raise KeyError(f"ascii_art: no colour for '{ch}' (row {y})")
            img[y, x] = col
    return img


def flip_x(img: np.ndarray) -> np.ndarray:
    return img[:, ::-1].copy()


def flip_y(img: np.ndarray) -> np.ndarray:
    return img[::-1].copy()


def shift(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
    out = new(*size(img))
    paste(out, img, dx, dy)
    return out


def crop(img: np.ndarray, x, y, w, h) -> np.ndarray:
    out = new(w, h)
    paste(out, img, -x, -y)
    return out


def pad_to(img: np.ndarray, w: int, h: int, anchor: str = "bottom") -> np.ndarray:
    """Place img centred horizontally in a w*h canvas. anchor bottom|center|top."""
    iw, ih = size(img)
    out = new(w, h)
    ox = (w - iw) // 2
    oy = {"bottom": h - ih, "center": (h - ih) // 2, "top": 0}[anchor]
    paste(out, img, ox, oy)
    return out


def recolor(img: np.ndarray, mapping: Dict[Color, Color]) -> np.ndarray:
    out = img.copy()
    for src, dst in mapping.items():
        m = np.all(img == np.array(src, np.uint8), axis=-1)
        out[m] = dst
    return out


def ramp_swap(img: np.ndarray, src_ramp: Sequence[Color], dst_ramp: Sequence[Color]) -> np.ndarray:
    """Recolour every colour of src_ramp to the matching index of dst_ramp (clamped)."""
    mapping = {}
    for i, c in enumerate(src_ramp):
        mapping[c] = dst_ramp[min(i, len(dst_ramp) - 1)]
    return recolor(img, mapping)


def silhouette(img: np.ndarray, color: Color = (255, 255, 255, 255)) -> np.ndarray:
    out = new(*size(img))
    m = img[:, :, 3] > 0
    out[m] = color[:3] + (255,)
    out[m, 3] = img[m, 3]
    return out


def outline(img: np.ndarray, color: Color = PAL["outline"], diagonal: bool = False,
            only_where_empty: bool = True) -> np.ndarray:
    """Add a 1px outline around the opaque region. Returns a new image the same size
    (make sure the source has 1px of transparent margin)."""
    a = img[:, :, 3] > 0
    grown = a.copy()
    grown[1:, :] |= a[:-1, :]
    grown[:-1, :] |= a[1:, :]
    grown[:, 1:] |= a[:, :-1]
    grown[:, :-1] |= a[:, 1:]
    if diagonal:
        grown[1:, 1:] |= a[:-1, :-1]
        grown[1:, :-1] |= a[:-1, 1:]
        grown[:-1, 1:] |= a[1:, :-1]
        grown[:-1, :-1] |= a[1:, 1:]
    ring = grown & ~a if only_where_empty else grown
    out = img.copy()
    out[ring] = color
    return out


def inner_outline(img: np.ndarray, color: Color) -> np.ndarray:
    """Recolour the outermost opaque pixels (useful for rim lights)."""
    a = img[:, :, 3] > 0
    er = a.copy()
    er[1:, :] &= a[:-1, :]
    er[:-1, :] &= a[1:, :]
    er[:, 1:] &= a[:, :-1]
    er[:, :-1] &= a[:, 1:]
    rim = a & ~er
    out = img.copy()
    out[rim] = color
    return out


def mask_of(img: np.ndarray) -> np.ndarray:
    return img[:, :, 3] > 0


def fill_mask(img: np.ndarray, mask: np.ndarray, c: Color) -> None:
    img[mask] = c


def shade_mask(img: np.ndarray, mask: np.ndarray, ramp: Sequence[Color], light=(-0.6, -0.8),
               levels: Optional[Sequence[float]] = None, dither: bool = True, seed: int = 0) -> None:
    """Fill `mask` with a ramp shaded as a rounded volume lit from `light` (dx, dy; y down).
    Uses the distance-to-edge and light direction to choose ramp steps. Deterministic."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return
    cx, cy = xs.mean(), ys.mean()
    rx = max(1.0, (xs.max() - xs.min() + 1) / 2)
    ry = max(1.0, (ys.max() - ys.min() + 1) / 2)
    lx, ly = light
    ln = math.hypot(lx, ly) or 1
    lx, ly = lx / ln, ly / ln
    n = len(ramp)
    levels = levels or [i / n for i in range(1, n)]
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0
    for x, y in zip(xs, ys):
        nx, ny = (x - cx) / rx, (y - cy) / ry
        d = min(1.0, math.hypot(nx, ny))
        nz = math.sqrt(max(0.0, 1 - d * d))
        lam = max(0.0, -(nx * lx + ny * ly) * 0.75 + nz * 0.55 + 0.1)
        lam = min(0.999, lam)
        if dither:
            lam = lam + (bayer[y % 4, x % 4] - 0.5) * 0.12
        idx = 0
        for i, t in enumerate(levels):
            if lam >= t:
                idx = i + 1
        img[y, x] = ramp[max(0, min(n - 1, idx))]


def dither_mask(mask: np.ndarray, level: float, pattern: str = "bayer") -> np.ndarray:
    """Return a boolean mask keeping ~level fraction of `mask` using an ordered pattern."""
    h, w = mask.shape
    if pattern == "checker":
        yy, xx = np.mgrid[0:h, 0:w]
        pat = ((xx + yy) % 2 == 0).astype(float) * 0.5 + 0.25
    else:
        bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0 + 1 / 32
        pat = np.tile(bayer, (h // 4 + 1, w // 4 + 1))[:h, :w]
    return mask & (pat < level)


def glow(img: np.ndarray, color: Color, radius: int = 2, strength: float = 0.6) -> np.ndarray:
    """Soft additive-looking halo behind opaque pixels (for FX only). Returns new image."""
    h, w = img.shape[:2]
    a = (img[:, :, 3] > 0).astype(np.float32)
    acc = np.zeros_like(a)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            d = math.hypot(dx, dy)
            if d > radius:
                continue
            wgt = (1 - d / (radius + 1))
            sh = np.zeros_like(a)
            ys0, ys1 = max(0, dy), min(h, h + dy)
            xs0, xs1 = max(0, dx), min(w, w + dx)
            sh[ys0:ys1, xs0:xs1] = a[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
            acc = np.maximum(acc, sh * wgt)
    halo = new(w, h)
    alpha = np.clip(acc * strength * 255, 0, 255).astype(np.uint8)
    halo[:, :, 0], halo[:, :, 1], halo[:, :, 2] = color[0], color[1], color[2]
    halo[:, :, 3] = alpha
    paste(halo, img, 0, 0)
    return halo


def scale_nearest(img: np.ndarray, k: int) -> np.ndarray:
    return np.repeat(np.repeat(img, k, axis=0), k, axis=1)


def to_pil(img: np.ndarray) -> Image.Image:
    return Image.fromarray(img, "RGBA")


def from_pil(im: Image.Image) -> np.ndarray:
    return np.array(im.convert("RGBA"), dtype=np.uint8)


def count_colors(img: np.ndarray) -> int:
    m = img[:, :, 3] > 0
    return len({tuple(v) for v in img[m].reshape(-1, 4)})


def trim_box(img: np.ndarray) -> Tuple[int, int, int, int]:
    ys, xs = np.nonzero(img[:, :, 3] > 0)
    if len(xs) == 0:
        return 0, 0, 0, 0
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


# --------------------------------------------------------------------------------------
# Registry + atlas packing
# --------------------------------------------------------------------------------------
@dataclass
class SpriteEntry:
    name: str
    img: np.ndarray
    pivot: Tuple[float, float] = (0.5, 0.5)  # normalised, from the sprite's BOTTOM-left
    border: Tuple[int, int, int, int] = (0, 0, 0, 0)  # left, bottom, right, top (9-slice)
    source: str = ""
    anchors: Dict[str, Tuple[float, float]] = field(default_factory=dict)  # px from pivot, +y up


@dataclass
class AnimEntry:
    name: str
    frames: List[str]
    fps: float
    loop: bool


class Atlas:
    def __init__(self, name: str, flash: bool = False, max_size: int = 2048):
        self.name = name
        self.flash = flash  # also emit <name>_flash.png: white silhouettes, identical layout
        self.max_size = max_size
        self.sprites: Dict[str, SpriteEntry] = {}
        self.anims: Dict[str, AnimEntry] = {}


class Registry:
    """Collects sprites/animations into named atlases, then packs and writes them."""

    def __init__(self):
        self.atlases: Dict[str, Atlas] = {}
        self.provenance: List[Dict[str, str]] = []

    def atlas(self, name: str, flash: bool = False) -> Atlas:
        if name not in self.atlases:
            self.atlases[name] = Atlas(name, flash)
        elif flash:
            self.atlases[name].flash = True
        return self.atlases[name]

    def _caller(self) -> str:
        for fr in inspect.stack()[2:6]:
            fn = os.path.basename(fr.filename)
            if fn != "eclib.py":
                return f"Tools/art/{fn}:{fr.function}"
        return "Tools/art"

    def sprite(self, atlas: str, name: str, img: np.ndarray, pivot=(0.5, 0.5), border=(0, 0, 0, 0),
               anchors: Optional[Dict[str, Tuple[float, float]]] = None) -> str:
        at = self.atlas(atlas)
        if name in at.sprites:
            raise ValueError(f"duplicate sprite name '{name}' in atlas '{atlas}'")
        if img.dtype != np.uint8 or img.ndim != 3 or img.shape[2] != 4:
            raise ValueError(f"sprite '{name}' must be uint8 HxWx4")
        src = self._caller()
        at.sprites[name] = SpriteEntry(name, img, tuple(pivot), tuple(border), src, dict(anchors or {}))
        self.provenance.append({"asset": f"{atlas}:{name}", "source": src})
        return name

    def anim(self, atlas: str, name: str, frames: Sequence[np.ndarray], fps: float, loop: bool = True,
             pivot=(0.5, 0.1), anchors: Optional[Dict[str, Tuple[float, float]]] = None) -> List[str]:
        names = []
        for i, f in enumerate(frames):
            names.append(self.sprite(atlas, f"{name}/{i}", f, pivot, anchors=anchors))
        at = self.atlas(atlas)
        if name in at.anims:
            raise ValueError(f"duplicate anim '{name}' in atlas '{atlas}'")
        at.anims[name] = AnimEntry(name, names, float(fps), bool(loop))
        return names

    # ---- packing -------------------------------------------------------------------
    @staticmethod
    def _pack(entries: List[SpriteEntry], max_size: int, pad: int = 2):
        items = sorted(entries, key=lambda e: (-e.img.shape[0], -e.img.shape[1], e.name))
        size_w = 128
        while size_w <= max_size:
            for size_h in sorted({size_w // 2, size_w} if size_w > 128 else {size_w}):
                pos = Registry._try_pack(items, size_w, size_h, pad)
                if pos is not None:
                    return size_w, size_h, pos
            size_w *= 2
        raise RuntimeError("atlas too large; split it into several atlases")

    @staticmethod
    def _try_pack(items, W, H, pad):
        x = y = pad
        shelf_h = 0
        pos = {}
        for e in items:
            h, w = e.img.shape[:2]
            if w + 2 * pad > W:
                return None
            if x + w + pad > W:
                x = pad
                y += shelf_h + pad
                shelf_h = 0
            if y + h + pad > H:
                return None
            pos[e.name] = (x, y)
            x += w + pad
            shelf_h = max(shelf_h, h)
        return pos

    def write(self, out_dir: str = ART_OUT, preview_dir: str = PREVIEW_OUT, only: Optional[Iterable[str]] = None) -> None:
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs(preview_dir, exist_ok=True)
        for name, at in sorted(self.atlases.items()):
            if only and name not in only:
                continue
            if not at.sprites:
                continue
            W, H, pos = self._pack(list(at.sprites.values()), at.max_size)
            sheet = new(W, H)
            flash = new(W, H) if at.flash else None
            meta_sprites = {}
            for sname, e in sorted(at.sprites.items()):
                x, y = pos[sname]
                paste(sheet, e.img, x, y)
                if flash is not None:
                    paste(flash, silhouette(e.img), x, y)
                h, w = e.img.shape[:2]
                d = {"x": x, "y": y, "w": w, "h": h, "pivot": [round(e.pivot[0], 4), round(e.pivot[1], 4)]}
                if any(e.border):
                    d["border"] = list(e.border)
                if e.anchors:
                    d["anchors"] = {k: [round(v[0], 3), round(v[1], 3)] for k, v in e.anchors.items()}
                meta_sprites[sname] = d
            meta = {
                "atlas": name,
                "texture": f"{name}.png",
                "flashTexture": f"{name}_flash.png" if flash is not None else None,
                "width": W, "height": H, "ppu": PPU,
                "coordinateOrigin": "top-left",
                "sprites": meta_sprites,
                "anims": {a.name: {"frames": a.frames, "fps": a.fps, "loop": a.loop} for a in sorted(at.anims.values(), key=lambda a: a.name)},
            }
            to_pil(sheet).save(os.path.join(out_dir, f"{name}.png"), optimize=True)
            if flash is not None:
                to_pil(flash).save(os.path.join(out_dir, f"{name}_flash.png"), optimize=True)
            with open(os.path.join(out_dir, f"{name}_atlas.json"), "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=1, sort_keys=False)
            self._preview(at, preview_dir)
            print(f"[atlas] {name}: {len(at.sprites)} sprites, {len(at.anims)} anims -> {W}x{H}")

    def _preview(self, at: Atlas, preview_dir: str, scale: int = 3, cols: int = 10) -> None:
        """Contact sheet for human review: every sprite at `scale`x on a checkerboard with its name."""
        names = sorted(at.sprites)
        cell_w = max(e.img.shape[1] for e in at.sprites.values()) * scale + 8
        cell_h = max(e.img.shape[0] for e in at.sprites.values()) * scale + 18
        cell_w = max(cell_w, 90)
        cols = max(1, min(cols, 1600 // cell_w))
        rows = (len(names) + cols - 1) // cols
        im = Image.new("RGBA", (cols * cell_w, rows * cell_h), (36, 30, 44, 255))
        dr = ImageDraw.Draw(im)
        font = ImageFont.load_default()
        for i, n in enumerate(names):
            e = at.sprites[n]
            cx, cy = (i % cols) * cell_w, (i // cols) * cell_h
            big = to_pil(scale_nearest(e.img, scale))
            bw, bh = big.size
            ox, oy = cx + (cell_w - bw) // 2, cy + 2
            for yy in range(0, bh, 6):
                for xx in range(0, bw, 6):
                    shade = (58, 52, 70, 255) if ((xx // 6 + yy // 6) % 2) else (48, 42, 60, 255)
                    dr.rectangle([ox + xx, oy + yy, ox + min(xx + 5, bw - 1), oy + min(yy + 5, bh - 1)], fill=shade)
            im.alpha_composite(big, (ox, oy))
            # pivot marker
            pvx = ox + int(e.pivot[0] * bw)
            pvy = oy + bh - int(e.pivot[1] * bh)
            dr.line([pvx - 2, pvy, pvx + 2, pvy], fill=(255, 60, 60, 255))
            dr.line([pvx, pvy - 2, pvx, pvy + 2], fill=(255, 60, 60, 255))
            dr.text((cx + 2, cy + cell_h - 14), n[-24:], fill=(220, 220, 230, 255), font=font)
        im.save(os.path.join(preview_dir, f"{at.name}_preview.png"))

    def write_provenance(self, path: str) -> None:
        import csv
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["asset", "source"])
            for row in sorted(self.provenance, key=lambda r: r["asset"]):
                w.writerow([row["asset"], row["source"]])


def rng(seed: int) -> random.Random:
    return random.Random(seed)


def font(size_px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Pixelify Sans (SIL OFL 1.1) for store/marketing images only; in-game text is TMP."""
    fn = "PixelifySans-Bold.ttf" if bold else "PixelifySans-Regular.ttf"
    return ImageFont.truetype(os.path.join(FONT_DIR, fn), size_px)


def preview_images(images: Sequence[np.ndarray], path: str, scale: int = 4, bg=(40, 34, 50, 255)) -> None:
    """Quick ad-hoc preview of a row of frames (for iterating on a single sprite)."""
    if not images:
        return
    w = sum(i.shape[1] for i in images) * scale + 4 * (len(images) + 1)
    h = max(i.shape[0] for i in images) * scale + 8
    im = Image.new("RGBA", (w, h), bg)
    x = 4
    for img in images:
        big = to_pil(scale_nearest(img, scale))
        im.alpha_composite(big, (x, 4))
        x += big.size[0] + 4
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)
