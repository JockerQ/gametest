"""
gen_fx.py - effects, projectiles and indicators for EVIL CATS (atlas "fx").

Rules followed here (see docs/ASSET_SPEC.md section 3.7):
  * Readable but restrained: enemy attacks must stay visible beneath effects, so large area
    effects (barrier_ring, winter_ring, gravity_well, range_ring, telegraph_circle,
    priest_heal_ring) are edge-lit with transparent centres.
  * Colour language: Arc = cyan, Ember = orange, Frost = ice-blue, Bone = ivory,
    Ward = teal/gold, Gravity = purple, rewards = gold, telegraphs/danger = red.
  * Cores, sparks and projectiles are crisp palette pixels; soft alpha is used only for
    glows, smoke and translucent fills.
  * Projectiles (arrow, ballista_bolt, shell, feather) and telegraph_chevron point RIGHT
    (+x) so the game can rotate them to the travel direction.

Every anim is registered as fx/<name>/<i>; single sprites as fx/<name>.
Run directly for iteration previews:  python3 Tools/art/gen_fx.py  -> /tmp/claude-0/world_iter/
"""
from __future__ import annotations

import math
import os
import sys
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import eclib as E  # noqa: E402
from eclib import PAL  # noqa: E402

ATLAS = "fx"
ITER_DIR = "/tmp/claude-0/world_iter"
OUT = PAL["outline"]
CENTER = (0.5, 0.5)

C = PAL  # short alias


# ======================================================================================
# Float compositor (premultiplied RGBA in 0..1) for soft layers
# ======================================================================================
class Layer:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.c = np.zeros((h, w, 3))
        self.a = np.zeros((h, w))
        yy, xx = np.mgrid[0:h, 0:w]
        self.X, self.Y = xx + 0.5, yy + 0.5

    def over(self, color, alpha) -> None:
        """Composite a colour with a per-pixel alpha map (0..1) over the layer."""
        alpha = np.clip(alpha, 0, 1)
        col = np.array(color[:3], float) / 255.0
        self.c = col[None, None, :] * alpha[..., None] + self.c * (1 - alpha[..., None])
        self.a = alpha + self.a * (1 - alpha)

    def px(self, x: int, y: int, color, alpha: float = 1.0) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            m = np.zeros((self.h, self.w))
            m[y, x] = alpha
            self.over(color, m)

    def dist(self, cx, cy, sx=1.0, sy=1.0):
        return np.hypot((self.X - cx) / sx, (self.Y - cy) / sy)

    def img(self, alpha_steps: int = 0) -> np.ndarray:
        a = np.clip(self.a, 0, 1)
        if alpha_steps:
            a = np.round(a * alpha_steps) / alpha_steps
        rgb = np.where(self.a[..., None] > 1e-6, self.c / np.maximum(self.a[..., None], 1e-6), 0)
        out = np.zeros((self.h, self.w, 4), np.uint8)
        out[..., :3] = np.clip(np.round(rgb * 255), 0, 255).astype(np.uint8)
        out[..., 3] = np.clip(np.round(a * 255), 0, 255).astype(np.uint8)
        out[out[..., 3] == 0] = 0
        return out


def hard(img: np.ndarray, pts, color) -> None:
    for (x, y) in pts:
        x, y = int(round(x)), int(round(y))
        if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
            img[y, x] = color


def comp(bottom: np.ndarray, top: np.ndarray) -> np.ndarray:
    out = bottom.copy()
    E.paste(out, top, 0, 0)
    return out


def glow_of(img: np.ndarray, color, radius: int, strength: float) -> np.ndarray:
    """Halo only (no source pixels) around the opaque pixels of img."""
    g = E.glow(img, color, radius=radius, strength=strength)
    g[img[:, :, 3] > 0] = 0
    return g


def with_glow(img: np.ndarray, color, radius: int = 2, strength: float = 0.5) -> np.ndarray:
    out = glow_of(img, color, radius, strength)
    E.paste(out, img, 0, 0)
    return out


def ring_alpha(L: Layer, cx, cy, r, width, sx=1.0, sy=1.0, soft=1.0):
    d = L.dist(cx, cy, sx, sy)
    return np.clip(1 - np.abs(d - r) / (width / 2 + soft) , 0, 1) ** 1.5


def star_pts(cx, cy, r, diag=0):
    pts = [(cx, cy)]
    for i in range(1, r + 1):
        pts += [(cx + i, cy), (cx - i, cy), (cx, cy + i), (cx, cy - i)]
    for i in range(1, diag + 1):
        pts += [(cx + i, cy + i), (cx - i, cy - i), (cx + i, cy - i), (cx - i, cy + i)]
    return pts


def sparkle(img, cx, cy, size, c_core, c_ray):
    """Tiny 4-point sparkle: size 0 = dot, 1 = plus, 2 = long plus."""
    hard(img, [(cx, cy)], c_core)
    if size >= 1:
        hard(img, [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)], c_ray)
    if size >= 2:
        hard(img, [(cx + 2, cy), (cx - 2, cy), (cx, cy + 2), (cx, cy - 2)], c_ray)


# ======================================================================================
# Hit sparks / impacts
# ======================================================================================
def spark_hit() -> List[np.ndarray]:
    frames = []
    rnd = E.rng(1)
    rays = [(math.cos(a), math.sin(a)) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False) + 0.2]
    for f in range(5):
        img = E.new(16, 16)
        cx, cy = 7.5, 7.5
        if f == 0:
            hard(img, star_pts(7, 7, 2), C["cyan3"])
            hard(img, star_pts(7, 7, 1), C["cyan4"])
        elif f == 1:
            hard(img, star_pts(7, 7, 4, 2), C["cyan2"])
            hard(img, star_pts(7, 7, 2, 1), C["cyan3"])
            hard(img, star_pts(7, 7, 1), C["cyan4"])
        else:
            r0, r1 = [(0, 0), (0, 0), (3, 6), (5, 7), (6, 7)][f]
            for k, (dx, dy) in enumerate(rays):
                if f == 4 and k % 2:
                    continue
                for t in np.arange(r0, r1, 0.5):
                    col = C["cyan3"] if t > r1 - 1.5 else C["cyan2"]
                    hard(img, [(cx + dx * t - 0.5, cy + dy * t - 0.5)], col)
            if f == 2:
                hard(img, star_pts(7, 7, 1), C["cyan3"])
        frames.append(with_glow(img, C["cyan1"], 2, [0.7, 0.6, 0.45, 0.3, 0.2][f]))
    return frames


def impact() -> List[np.ndarray]:
    """Generic hit: white flash star, then a fast ring with debris flying out."""
    frames = []
    rnd = E.rng(3)
    debris = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(0.8, 1.2)) for _ in range(7)]
    for f in range(4):
        L = Layer(24, 24)
        img = E.new(24, 24)
        cx = cy = 12
        if f == 0:
            L.over(C["white"], np.clip(1 - L.dist(cx, cy) / 6, 0, 1) ** 0.8 * 0.8)
            hard(img, star_pts(11, 11, 4, 2), C["silver3"])
            hard(img, star_pts(11, 11, 2, 1), C["white"])
        else:
            r = [0, 5.5, 8, 10][f]
            L.over(C["silver2"], ring_alpha(L, cx, cy, r, 1.0, soft=0.6) * [0, 0.95, 0.6, 0.25][f])
            if f == 1:
                hard(img, star_pts(11, 11, 1), C["silver3"])
            for (a, s_) in debris:
                t = [0, 6, 9, 11][f] * s_
                x, y = cx - 0.5 + math.cos(a) * t, cy - 0.5 + math.sin(a) * t
                hard(img, [(x, y)], C["white"] if f == 1 else C["silver2"] if f == 2 else C["silver1"])
                if f < 3:
                    hard(img, [(x - math.cos(a), y - math.sin(a))], C["silver1"])
        frames.append(comp(L.img(), img))
    return frames


def dust() -> List[np.ndarray]:
    frames = []
    col_hi, col, col_lo = E.hexc("#a89fac"), E.hexc("#857c8c"), E.hexc("#5f5868")
    for f in range(4):
        L = Layer(12, 8)
        a = [0.95, 0.85, 0.6, 0.3][f]
        for (dx, s_) in ((-2.6, 1.0), (2.6, 0.95), (0.0, 0.8)):
            r = [1.6, 2.3, 2.7, 2.8][f] * s_
            cx = 6 + dx * [0.55, 0.85, 1.05, 1.15][f]
            cy = [5.6, 5.0, 4.5, 4.0][f]
            L.over(col_lo, np.clip(r - L.dist(cx, cy) + 0.5, 0, 1) * a)
            L.over(col, np.clip(r - 0.7 - L.dist(cx - 0.4, cy - 0.4) + 0.5, 0, 1) * a)
            L.over(col_hi, np.clip(r - 1.6 - L.dist(cx - 0.8, cy - 0.8) + 0.5, 0, 1) * a)
        frames.append(L.img(8))
    return frames


def death_poof() -> List[np.ndarray]:
    frames = []
    rnd = E.rng(7)
    puffs = [(rnd.uniform(0, 6.28), rnd.uniform(0.6, 1.0)) for _ in range(7)]
    smoke = [E.hexc("#b8b0c4"), E.hexc("#8e8599"), E.hexc("#5f586c")]
    for f in range(5):
        L = Layer(24, 24)
        cx, cy = 12, 13
        img = E.new(24, 24)
        if f == 0:
            L.over(C["white"], np.clip(1 - L.dist(cx, cy) / 4.5, 0, 1))
            hard(img, star_pts(11, 12, 3), C["white"])
        spread = [2, 5, 7, 8.5, 9.5][f]
        alpha = [0.8, 0.85, 0.7, 0.45, 0.2][f]
        for (a, s) in puffs:
            px_, py_ = cx + math.cos(a) * spread * s, cy + math.sin(a) * spread * s * 0.8 - f * 0.8
            r = [2.0, 3.2, 3.6, 3.6, 3.2][f] * s
            d = L.dist(px_, py_)
            L.over(smoke[2], np.clip(r - d + 0.5, 0, 1) * alpha)
            L.over(smoke[1], np.clip(r - 0.8 - np.hypot(L.X - px_ + 0.6, L.Y - py_ + 0.6), 0, 1) * alpha)
            L.over(smoke[0], np.clip(r - 2.0 - np.hypot(L.X - px_ + 1.0, L.Y - py_ + 1.0), 0, 1) * alpha)
        if f in (2, 3, 4):
            for k, (a, s) in enumerate(puffs[:4]):
                sx = int(cx + math.cos(a + 1) * (spread + 2))
                sy = int(cy + math.sin(a + 1) * (spread + 1) - f)
                sparkle(img, sx, sy, 1 if f < 4 else 0, C["white"], C["gold3"] if k % 2 else C["cyan3"])
        frames.append(comp(L.img(8), img))
    return frames


# ======================================================================================
# Arc lightning
# ======================================================================================
def _bolt_path(rnd, x0, y0, x1, y1, seg=7, jit=3.0):
    pts = [(x0, y0)]
    n = max(2, int(abs(y1 - y0) / seg))
    for i in range(1, n):
        t = i / n
        pts.append((x0 + (x1 - x0) * t + rnd.uniform(-jit, jit), y0 + (y1 - y0) * t + rnd.uniform(-1.5, 1.5)))
    pts.append((x1, y1))
    return pts


def _draw_poly(img, pts, color, width=1):
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        E.line(img, xa, ya, xb, yb, color)
        if width >= 2:
            E.line(img, xa + 1, ya, xb + 1, yb, color)


def arc_storm_strike() -> List[np.ndarray]:
    W_, H_ = 24, 96
    gy = 91                              # impact row (pivot)
    frames = []
    rnd = E.rng(21)
    main_a = _bolt_path(rnd, 13, 0, 11, gy, seg=8, jit=3.2)
    main_b = _bolt_path(rnd, 10, 0, 12, gy, seg=7, jit=3.6)
    br = [_bolt_path(rnd, p[0], p[1], p[0] + rnd.choice((-7, 7)), p[1] + rnd.randint(10, 16), seg=4, jit=1.5)
          for p in (main_a[3], main_a[6], main_a[9])]
    for f in range(6):
        img = E.new(W_, H_)
        L = Layer(W_, H_)
        if f == 0:                       # faint leader creeping down
            _draw_poly(img, main_a[:6], C["cyan1"])
        elif f in (1, 2):
            path = main_a if f == 1 else main_b
            for b in br[: (3 if f == 1 else 2)]:
                _draw_poly(img, b, C["cyan2"])
            _draw_poly(img, path, C["cyan3"], 2)
            _draw_poly(img, path, C["cyan4"])
            L.over(C["cyan3"], np.clip(1 - L.dist(12, gy, 1.0, 0.45) / (9 if f == 1 else 11), 0, 1) ** 1.2 * 0.8)
            L.over(C["white"], np.clip(1 - L.dist(12, gy, 1.0, 0.5) / 4.5, 0, 1))
        elif f == 3:
            _draw_poly(img, main_b, C["cyan2"])
            L.over(C["cyan2"], ring_alpha(L, 12, gy, 8, 1.2, 1.0, 0.45) * 0.8)
            L.over(C["cyan3"], np.clip(1 - L.dist(12, gy, 1.0, 0.5) / 4, 0, 1) * 0.7)
        elif f == 4:
            for i in range(0, len(main_b) - 1, 2):
                _draw_poly(img, main_b[i:i + 2], C["cyan1"])
            L.over(C["cyan1"], ring_alpha(L, 12, gy, 10.5, 1.0, 1.0, 0.45) * 0.5)
        else:
            L.over(C["cyan1"], np.clip(1 - L.dist(12, gy, 1.0, 0.5) / 5, 0, 1) * 0.35)
        if f in (3, 4, 5):
            for k in range(5):
                a = -math.pi * (0.1 + 0.8 * k / 4)
                rr = [0, 0, 0, 5, 8, 10][f]
                sparkle(img, int(12 + math.cos(a) * rr * 1.1), int(gy + math.sin(a) * rr * 0.5), 0,
                        C["cyan3"] if f < 5 else C["cyan2"], C["cyan2"])
        base = L.img()
        top = with_glow(img, C["cyan1"], 2, [0.3, 0.55, 0.55, 0.4, 0.25, 0.1][f])
        frames.append(comp(base, top))
    return frames


def lightning_tex() -> np.ndarray:
    img = E.new(16, 8)
    prof = {0: None, 1: (C["cyan1"], 70), 2: (C["cyan2"], 190), 3: (C["cyan4"], 255), 4: (C["cyan4"], 255),
            5: (C["cyan2"], 190), 6: (C["cyan1"], 70), 7: None}
    for y, v in prof.items():
        if v is None:
            continue
        col, a = v
        img[y, :] = col[:3] + (a,)
    img[3, :] = C["white"][:3] + (255,)
    return img


def target_reticle() -> List[np.ndarray]:
    """Arc Storm aim: cyan ring with cross-hair ticks and corner brackets (2 frames pulse)."""
    frames = []
    for f in range(2):
        img = E.new(32, 32)
        r = 11 if f == 0 else 10
        E.circle(img, 15.5, 15.5, r, C["cyan2"], fill=False)
        for d in range(4):                                  # cross-hair ticks through the ring
            a = d * math.pi / 2
            for t in range(r - 3, r + 3):
                hard(img, [(15.5 + math.cos(a) * t - 0.5, 15.5 + math.sin(a) * t - 0.5)], C["cyan3"])
        c0 = 15.5 - (6 if f == 0 else 5)                     # corner brackets closing in
        c1 = 15.5 + (6 if f == 0 else 5)
        for (bx, by, sx, sy) in ((c0, c0, 1, 1), (c1, c0, -1, 1), (c0, c1, 1, -1), (c1, c1, -1, -1)):
            hard(img, [(bx - 0.5, by - 0.5), (bx - 0.5 + sx, by - 0.5), (bx - 0.5, by - 0.5 + sy)], C["cyan4"])
        hard(img, [(15, 15), (16, 16), (15, 16), (16, 15)], C["cyan4"] if f == 0 else C["cyan3"])
        frames.append(E.outline(img, C["cyan0"]))
    return frames


def mark() -> np.ndarray:
    rows = [
        "...oo...",
        "..o22o..",
        ".o2.42o.",
        "o2.44.2o",
        "o2.44.2o",
        ".o24.2o.",
        "..o22o..",
        "...oo...",
    ]
    return E.ascii_art(rows, {"o": C["cyan0"], "2": C["cyan2"], "4": C["cyan4"]})


def stun() -> List[np.ndarray]:
    frames = []
    for f in range(4):
        img = E.new(16, 8)
        L = Layer(16, 8)
        for k in range(3):
            a = (f / 4 + k / 3) * 2 * math.pi
            x = 7.5 + 6.0 * math.cos(a)
            y = 3.8 + 2.2 * math.sin(a)
            front = math.sin(a) > 0
            sz = 1 if front else 0
            sparkle(img, int(x), int(y), sz, C["white"] if front else C["cyan3"], C["cyan3"] if front else C["cyan2"])
        frames.append(with_glow(img, C["cyan1"], 1, 0.45))
    return frames


# ======================================================================================
# Ember (fire) and enemy powder
# ======================================================================================
def _puffs(S, rnd, n, spread, rmin, rmax):
    """Random puffs around the centre, evenly spread in angle so the cluster stays centred."""
    out = []
    for i in range(n):
        a = (i + rnd.uniform(-0.3, 0.3)) * 2 * math.pi / n
        out.append(dict(a=a, d=rnd.uniform(0.35, 1.0) * spread, r=rnd.uniform(rmin, rmax), drift=rnd.uniform(0.6, 1.3)))
    rnd.shuffle(out)
    return out


def _draw_puffs(L: Layer, puffs, cx, cy, t, grow, rise, tone_fn, alpha):
    """Hard-edged shaded puffs (lit top-left) composited back-to-front."""
    items = []
    for p in puffs:
        x = cx + math.cos(p["a"]) * p["d"] * (1 + t * p["drift"])
        y = cy + math.sin(p["a"]) * p["d"] * 0.85 * (1 + t * p["drift"]) - rise * t
        items.append((y, x, p["r"] * grow))
    items.sort()
    for (y, x, r) in items:
        lo, mid, hi = tone_fn(r)
        d0 = L.dist(x, y)
        L.over(lo, (d0 <= r) * alpha)
        L.over(mid, (np.hypot(L.X - x + r * 0.22, L.Y - y + r * 0.22) <= r * 0.78) * alpha)
        L.over(hi, (np.hypot(L.X - x + r * 0.42, L.Y - y + r * 0.42) <= r * 0.42) * alpha)


def explosion() -> List[np.ndarray]:
    """Ember explosion: flash -> fire puffs -> smoke that thins out (never a solid disc late)."""
    frames = []
    rnd = E.rng(31)
    puffs = _puffs(40, rnd, 8, 6.0, 3.0, 5.0)
    embers = [(rnd.uniform(0, 6.28), rnd.uniform(0.7, 1.2)) for _ in range(10)]
    smoke = (E.hexc("#2b2427"), E.hexc("#3d3437"), E.hexc("#554a4c"))
    fire_hot = (C["fire2"], C["fire3"], C["fire4"])
    fire_mid = (C["fire1"], C["fire2"], C["fire3"])
    ember_dark = (E.hexc("#4a1c10"), C["fire1"], C["fire2"])
    for f in range(7):
        L = Layer(40, 40)
        img = E.new(40, 40)
        cx, cy = 20, 21
        if f == 0:
            L.over(C["fire2"], np.clip(1 - L.dist(cx, cy) / 8, 0, 1) ** 0.7 * 0.9)
            L.over(C["fire4"], L.dist(cx, cy) <= 3.2)
            hard(img, star_pts(19, 20, 5, 3), C["fire4"])
        else:
            t = f / 6
            grow = [0, 1.0, 1.35, 1.55, 1.6, 1.6, 1.5][f]
            alpha = [0, 1, 1, 0.95, 0.75, 0.5, 0.25][f]
            tones = [None, fire_hot, fire_mid, ember_dark, smoke, smoke, smoke][f]
            if f >= 3:     # smoke puffs outside, a little fire left inside
                _draw_puffs(L, puffs, cx, cy, t * 1.6, grow, 3 * t, lambda r: smoke, alpha)
                if f <= 4:
                    inner = sorted(puffs, key=lambda q: q["d"])[:5]
                    core = [dict(q, d=q["d"] * 0.4) for q in inner]
                    _draw_puffs(L, core, cx, cy, t, grow * 0.62, 2 * t, lambda r: tones if f == 3 else ember_dark, alpha)
            else:
                _draw_puffs(L, puffs, cx, cy, t, grow, 2 * t, lambda r: tones, alpha)
            if f == 1:
                L.over(C["fire4"], L.dist(cx, cy) <= 3.0)
        if 2 <= f <= 5:
            for (a, s_) in embers:
                tt = [0, 0, 11, 14, 16, 17.5][f] * s_
                x, y = cx + math.cos(a) * tt, cy + math.sin(a) * tt - (f - 2)
                hard(img, [(x, y)], C["fire3"] if f < 4 else C["fire2"])
        base = L.img(10)
        if f <= 2:
            base = comp(glow_of(base, C["fire1"], 2, 0.35), base)
        frames.append(comp(base, img))
    return frames


def powder_blast() -> List[np.ndarray]:
    """Enemy powder-keg blast: hotter red core, black soot, red shockwave, flying planks."""
    frames = []
    rnd = E.rng(41)
    puffs = _puffs(48, rnd, 10, 8.0, 3.5, 6.0)
    planks = [(rnd.uniform(0, 6.28), rnd.uniform(0.8, 1.2)) for _ in range(6)]
    soot = (E.hexc("#141012"), E.hexc("#231c1e"), E.hexc("#352b2d"))
    hot = (C["red2"], C["fire2"], C["fire4"])
    mid = (C["red1"], C["red2"], C["fire2"])
    for f in range(6):
        L = Layer(48, 48)
        img = E.new(48, 48)
        cx, cy = 24, 25
        if f == 0:
            L.over(C["fire3"], np.clip(1 - L.dist(cx, cy) / 10, 0, 1) ** 0.7 * 0.9)
            L.over(C["white"], L.dist(cx, cy) <= 3.5)
            hard(img, star_pts(23, 24, 6, 4), C["fire4"])
        else:
            t = f / 5
            grow = [0, 1.0, 1.3, 1.45, 1.5, 1.45][f]
            alpha = [0, 1, 1, 0.9, 0.65, 0.35][f]
            L.over(C["red3"], ring_alpha(L, cx, cy, [0, 13, 18, 21, 23, 23][f], 1.2, soft=0.6) * [0, 1, 0.75, 0.45, 0.2, 0][f])
            if f >= 2:
                _draw_puffs(L, puffs, cx, cy, t * 1.5, grow, 3 * t, lambda r: soot, alpha)
            if f <= 3:
                # fire stays in a burning core: the innermost puffs, pulled toward the centre
                inner = sorted(puffs, key=lambda q: q["d"])[:7]
                core = [dict(q, d=q["d"] * (1.0 if f == 1 else 0.45)) for q in inner]
                _draw_puffs(L, puffs if f == 1 else core, cx, cy, t, grow * (1 if f == 1 else 0.75), 2 * t,
                            lambda r: hot if f < 3 else mid, 1.0 if f < 3 else 0.85)
        if f >= 1:
            for (a, s_) in planks:
                tt = [0, 10, 15, 19, 22, 24][f] * s_
                x, y = cx + math.cos(a) * tt, cy + math.sin(a) * tt - f
                pts = [(x, y), (x + math.cos(a + f) * 1.5, y + math.sin(a + f) * 1.5)]
                hard(img, pts, PAL["wood3"] if f < 4 else PAL["wood2"])
        base = L.img(10)
        if f <= 2:
            base = comp(glow_of(base, C["red1"], 2, 0.3), base)
        frames.append(comp(base, img))
    return frames


def burn() -> List[np.ndarray]:
    frames = []
    shapes = [
        ["....y.....", "...yf.....", "..yff..y..", "..fFf.yf..", ".fFhFfff..", ".fFhhFFf..", "..fFFFf..."],
        [".....y....", "....fy....", "..y.ff....", "..fyfFf...", ".ffFhFf...", ".fFhhFFf..", "..fFFFf..."],
        ["...y......", "...fy.y...", "..ffy.f...", "..fFffF...", ".ffFhFFf..", ".fFhhhFf..", "..fFFFf..."],
        ["......y...", "..y..fy...", "..fy.ff...", ".ffFfFf...", ".fFFhFff..", ".fFhhFFf..", "..fFFFf..."],
    ]
    leg = {"y": C["fire2"], "f": C["fire2"], "F": C["fire3"], "h": C["fire4"]}
    for f in range(4):
        art = E.ascii_art(shapes[f], leg)
        art = E.recolor(art, {})
        img = E.new(12, 12)
        E.paste(img, art, 1, 3)
        # darker red tips on the outer edge
        edge = (img[:, :, 3] > 0) & ~np.roll(img[:, :, 3] > 0, 1, axis=0)
        img[edge] = C["fire1"]
        frames.append(with_glow(img, C["fire1"], 1, 0.45))
    return frames


def shell() -> List[np.ndarray]:
    frames = []
    for f in range(2):
        img = E.new(10, 10)
        # ember trail (left), iron shell with glowing cracks (right)
        trail = [(1, 5), (2, 4), (2, 5), (3, 5)] if f == 0 else [(1, 4), (2, 5), (2, 4), (3, 4)]
        hard(img, trail, C["fire2"])
        hard(img, [(3, 5) if f == 0 else (3, 4)], C["fire3"])
        E.circle(img, 6, 4.5, 2.6, PAL["iron1"])
        hard(img, [(5, 3), (6, 3), (5, 4)], PAL["iron3"])
        hard(img, [(7, 5), (6, 6)] if f == 0 else [(7, 4), (6, 6), (7, 6)], C["fire3"])
        hard(img, [(7, 3)], PAL["iron2"])
        img = E.outline(img)
        frames.append(with_glow(img, C["fire1"], 1, 0.35))
    return frames


# ======================================================================================
# Frost
# ======================================================================================
def frost_burst() -> List[np.ndarray]:
    frames = []
    rnd = E.rng(51)
    n = 8
    shards = [(i * 2 * math.pi / n + rnd.uniform(-0.15, 0.15), rnd.uniform(0.8, 1.15)) for i in range(n)]
    for f in range(6):
        L = Layer(40, 40)
        img = E.new(40, 40)
        cx = cy = 20
        if f == 0:
            L.over(C["frost2"], np.clip(1 - L.dist(cx, cy) / 7, 0, 1) * 0.8)
            L.over(C["frost4"], L.dist(cx, cy) <= 3.0)
        else:
            rr = [0, 7, 11, 14, 16.5, 18][f]
            L.over(C["frost2"], ring_alpha(L, cx, cy, rr, 1.4) * [0, 0.9, 0.75, 0.55, 0.35, 0.15][f])
            L.over(C["frost4"], ring_alpha(L, cx, cy, rr, 0.4, soft=0.3) * [0, 0.8, 0.6, 0.35, 0.2, 0][f])
        if 1 <= f <= 4:
            for (a, s_) in shards:
                t0 = [0, 1.5, 4.5, 7.5, 10][f] * s_
                t1 = t0 + [0, 6, 6, 5, 3][f] * s_
                ca, sa = math.cos(a), math.sin(a)
                for t in np.arange(t0, t1, 0.5):
                    col = C["frost4"] if t > t1 - 1.2 else C["frost3"]
                    hard(img, [(cx - 0.5 + ca * t, cy - 0.5 + sa * t)], col)
                    if (t1 - t) > 2.5 and f < 4:
                        hard(img, [(cx - 0.5 + ca * t - sa, cy - 0.5 + sa * t + ca)], C["frost2"])
        if f >= 3:
            for k in range(7):
                a = k * 0.9 + f
                t = [0, 0, 0, 12, 15, 17][f] + (k % 3)
                sparkle(img, int(cx + math.cos(a) * t), int(cy + math.sin(a) * t), 1 if (k + f) % 3 == 0 else 0,
                        C["frost4"], C["frost2"])
        frames.append(comp(L.img(10), with_glow(img, C["frost1"], 1, 0.25)))
    return frames


def winter_ring() -> List[np.ndarray]:
    frames = []
    rnd = E.rng(61)
    S = 96
    shards = [rnd.uniform(0, 2 * math.pi) for _ in range(28)]
    for f in range(6):
        L = Layer(S, S)
        img = E.new(S, S)
        c = S / 2
        r = [10, 20, 29, 36, 41, 44][f]
        a_main = [0.9, 0.95, 0.85, 0.7, 0.5, 0.28][f]
        L.over(C["frost1"], ring_alpha(L, c, c, r - 2.5, 5.0, soft=2.0) * a_main * 0.35)   # inner frosty haze band
        L.over(C["frost2"], ring_alpha(L, c, c, r, 2.0) * a_main)
        L.over(C["frost4"], ring_alpha(L, c, c, r, 0.6, soft=0.4) * a_main)
        for k, a in enumerate(shards):
            if (k + f) % 2:
                continue
            ca, sa = math.cos(a), math.sin(a)
            ln = 2 + (k % 3)
            for t in range(ln):
                hard(img, [(c - 0.5 + ca * (r + 1 + t), c - 0.5 + sa * (r + 1 + t))], C["frost3"] if t < ln - 1 else C["frost4"])
        if f >= 2:
            for k in range(10):
                a = k * 0.63 + f * 0.4
                t = r - 4 - (k % 4) * 2
                sparkle(img, int(c + math.cos(a) * t), int(c + math.sin(a) * t), 1 if k % 3 == 0 else 0, C["frost4"], C["frost2"])
        frames.append(comp(L.img(12), img))
    return frames


def chill() -> np.ndarray:
    """Frost status icon: crisp 8-arm snowflake."""
    rows = [
        "....4....",
        ".4..3..4.",
        "..3.3.3..",
        "...323...",
        "433242334",
        "...323...",
        "..3.3.3..",
        ".4..3..4.",
        "....4....",
    ]
    art = E.ascii_art(rows, {"2": C["frost4"], "3": C["frost3"], "4": C["frost4"]})
    img = E.new(12, 12)
    E.paste(img, art, 1, 1)
    img = E.outline(img, C["frost0"])
    return with_glow(img, C["frost1"], 1, 0.2)


def frozen() -> np.ndarray:
    """Translucent ice block that encases an enemy (pivot at the base)."""
    S = 24
    L = Layer(S, S)
    img = E.new(S, S)
    x0, x1, y0, y1 = 3, 21, 3, 23
    body = (L.X > x0) & (L.X < x1) & (L.Y > y0 + 4) & (L.Y < y1)
    topf = (L.X > x0 + 2) & (L.X < x1 + 0) & (L.Y > y0) & (L.Y < y0 + 4.5) & ((L.X - x0) > (y0 + 4 - L.Y) * 0.5)
    # chamfered corners
    body &= ~((L.X < x0 + 1.5) & (L.Y > y1 - 1.5))
    L.over(C["frost2"], body * 0.42)
    L.over(C["frost3"], topf * 0.55)
    L.over(C["frost1"], (body & (L.X > x1 - 5)) * 0.25)
    blk = L.img()
    # crisp edges, highlights and a crack
    for y in range(y0 + 4, y1):
        hard(img, [(x0, y)], C["frost3"])
        hard(img, [(x1 - 1, y)], C["frost1"])
    for x in range(x0, x1):
        hard(img, [(x, y1 - 1)], C["frost1"])
        hard(img, [(x, y0 + 4)], C["frost4"])
    for x in range(x0 + 2, x1):
        hard(img, [(x, y0)], C["frost4"])
    for i in range(4):
        hard(img, [(x0 + 1 + i // 2 * 0, y0 + 4 - i), (x1 - 1, y0 + i + 1)], C["frost3"])
    hard(img, [(6, 9), (6, 10), (7, 11), (7, 12), (6, 14)], C["frost4"])
    hard(img, [(15, 16), (16, 17), (16, 18), (17, 19)], C["frost4"])
    hard(img, [(17, 8), (18, 8), (17, 9)], C["white"])
    out = comp(blk, img)
    return out


def shatter() -> List[np.ndarray]:
    frames = []
    rnd = E.rng(71)
    pieces = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(0.7, 1.2), rnd.choice((2, 3))) for _ in range(9)]
    for f in range(5):
        img = E.new(32, 32)
        L = Layer(32, 32)
        cx, cy = 16, 17
        if f == 0:
            L.over(C["frost3"], np.clip(1 - L.dist(cx, cy) / 8, 0, 1) * 0.6)
            hard(img, [(15, 12), (16, 13), (16, 14), (15, 15), (17, 16), (16, 17), (14, 18), (18, 19)], C["frost4"])
        for k, (a, s, sz) in enumerate(pieces):
            t = [3, 6, 9, 11.5, 13][f] * s
            x, y = cx + math.cos(a) * t, cy + math.sin(a) * t + f * f * 0.3
            ang = a + f * 0.8 * (1 if k % 2 else -1)
            pts = [(x + math.cos(ang) * i, y + math.sin(ang) * i) for i in range(sz)]
            hard(img, pts, C["frost3"] if f < 3 else C["frost2"])
            hard(img, pts[:1], C["frost4"])
        top = E.outline(img, C["frost0"]) if f < 3 else img
        frames.append(comp(L.img(8), top))
    return frames


# ======================================================================================
# Gravity, ward, heal, level-up
# ======================================================================================
def gravity_well() -> List[np.ndarray]:
    frames = []
    S = 48
    c = S / 2
    rnd = E.rng(81)
    motes = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(8, 21)) for _ in range(12)]
    for f in range(6):
        L = Layer(S, S)
        img = E.new(S, S)
        d = L.dist(c, c)
        ang = np.arctan2(L.Y - c, L.X - c)
        # faint dark core (transparent-ish centre) + edge-lit rim
        L.over(C["grav0"], np.clip(1 - d / 20, 0, 1) * 0.28)
        L.over(C["grav2"], ring_alpha(L, c, c, 20.5, 1.6) * 0.75)
        L.over(C["grav3"], ring_alpha(L, c, c, 20.5, 0.5, soft=0.4) * 0.5)
        # three spiral arms rotating inward
        rot = f * (2 * math.pi / 6) / 3
        for arm in range(3):
            phase = ang + rot + arm * 2 * math.pi / 3
            spiral = (np.mod(phase - np.log(np.maximum(d, 1)) * 2.2, 2 * math.pi / 3 * 3))
            band = np.clip(1 - np.abs(np.mod(phase - np.log(np.maximum(d, 1)) * 2.2, 2 * math.pi) - math.pi) / 0.55, 0, 1)
            L.over(C["grav3"], band * np.clip((d - 6) / 8, 0, 1) * np.clip((20 - d) / 5, 0, 1) * 0.5)
        # motes spiralling in
        for k, (a0, r0) in enumerate(motes):
            t = (f / 6 + k / 12) % 1.0
            r = r0 * (1 - t) + 2
            a = a0 + t * 3.0
            x, y = c + math.cos(a) * r, c + math.sin(a) * r
            hard(img, [(x - 0.5, y - 0.5)], C["grav4"] if r > 10 else C["grav3"])
        frames.append(comp(L.img(12), with_glow(img, C["grav2"], 1, 0.4)))
    return frames


def barrier_ring() -> List[np.ndarray]:
    """Translucent cyan-silver dome rim with a hex shimmer near the edge; centre clear."""
    frames = []
    S = 128
    c = S / 2
    R = 60.0
    yy, xx = np.mgrid[0:S, 0:S]
    X, Y = xx + 0.5 - c, yy + 0.5 - c
    # hex lattice (pointy-top), cell size 8
    size = 5.0
    q = (math.sqrt(3) / 3 * X - Y / 3) / size
    r_ = (2 / 3 * Y) / size

    def hex_round(q, r):
        x_, z_ = q, r
        y_ = -x_ - z_
        rx, ry, rz = np.round(x_), np.round(y_), np.round(z_)
        dx, dy, dz = np.abs(rx - x_), np.abs(ry - y_), np.abs(rz - z_)
        cond1 = (dx > dy) & (dx > dz)
        cond2 = ~cond1 & (dy > dz)
        rx = np.where(cond1, -ry - rz, rx)
        ry = np.where(cond2, -rx - rz, ry)
        rz = np.where(~cond1 & ~cond2, -rx - ry, rz)
        return rx, rz, np.maximum(np.maximum(dx, dy), dz)
    hq, hr, _ = hex_round(q, r_)
    # distance to the hex cell edge ~ via the fractional offsets
    cx_ = size * math.sqrt(3) * (hq + hr / 2)
    cy_ = size * 1.5 * hr
    ddx, ddy = X - cx_, Y - cy_
    hexd = np.maximum(np.abs(ddx) * 2 / math.sqrt(3), np.abs(ddx) / math.sqrt(3) + np.abs(ddy))
    hex_edge = np.clip(1 - np.abs(hexd - size * 0.98) / 0.7, 0, 1)
    d = np.hypot(X, Y)
    band = np.clip(1 - (R - d) / 16, 0, 1) * (d <= R)
    cell_id = (hq * 7 + hr * 13) % 5
    for f in range(4):
        L = Layer(S, S)
        # inner soft sheen near the rim (fades to fully transparent in the middle)
        L.over(C["cyan1"], band ** 2.2 * 0.22)
        # hex lines, only near the rim; a few cells light up per frame
        lit = (cell_id == f) | (cell_id == (f + 2) % 5)
        L.over(C["cyan3"], hex_edge * band ** 1.6 * (0.35 + 0.35 * lit))
        # rim: silver line + cyan glow either side
        L.over(C["cyan2"], ring_alpha(L, c, c, R, 3.5, soft=1.5) * 0.55)
        L.over(C["silver3"], ring_alpha(L, c, c, R, 1.0, soft=0.4) * 0.9)
        # travelling highlight arc
        ang = np.arctan2(Y, X)
        hl = np.clip(1 - np.abs(((ang - f * math.pi / 2 + math.pi) % (2 * math.pi)) - math.pi) / 0.5, 0, 1)
        L.over(C["cyan4"], ring_alpha(L, c, c, R, 1.4, soft=0.5) * hl)
        frames.append(L.img(16))
    return frames


def priest_heal_ring() -> List[np.ndarray]:
    frames = []
    S = 48
    c = S / 2
    for f in range(5):
        L = Layer(S, S)
        img = E.new(S, S)
        r = [5, 10, 15, 19, 22][f]
        a = [0.9, 1.0, 0.85, 0.6, 0.3][f]
        L.over(C["gold1"], ring_alpha(L, c, c, r - 1.5, 3.0, soft=1.5) * a * 0.4)
        L.over(C["gold3"], ring_alpha(L, c, c, r, 1.2) * a)
        L.over(C["gold4"], ring_alpha(L, c, c, r, 0.4, soft=0.3) * a)
        for k in range(8):
            ang = k * math.pi / 4 + f * 0.25
            if (k + f) % 2 == 0:
                sparkle(img, int(c + math.cos(ang) * r), int(c + math.sin(ang) * r) - 1, 1 if f < 3 else 0, C["gold4"], C["gold3"])
        frames.append(comp(L.img(12), img))
    return frames


def heal() -> List[np.ndarray]:
    frames = []
    spots = [(4, 12, 0), (10, 13, 1), (7, 10, 2), (12, 9, 3), (5, 7, 1)]
    for f in range(5):
        img = E.new(16, 16)
        for k, (x, y, ph) in enumerate(spots):
            age = f - ph
            if age < 0 or age > 3:
                continue
            yy = y - age * 2
            size = [1, 2, 1, 0][age]
            sparkle(img, x, yy, size, C["white"] if age < 2 else C["gold4"], C["gold3"] if age < 3 else C["gold2"])
        frames.append(with_glow(img, C["gold2"], 1, 0.4))
    return frames


def level_up() -> List[np.ndarray]:
    """Rising column of cyan-gold light with a ground ring (pivot near the base)."""
    frames = []
    S = 48
    cx, base = 24, 41
    rnd = E.rng(91)
    motes = [(rnd.uniform(-9, 9), rnd.uniform(0, 1), rnd.choice((0, 1))) for _ in range(12)]
    for f in range(6):
        L = Layer(S, S)
        img = E.new(S, S)
        h = [10, 22, 34, 40, 40, 40][f]
        colA = [1.0, 1.0, 0.9, 0.7, 0.45, 0.2][f]
        w = [3, 5, 6, 5, 4, 3][f]
        col = np.clip(1 - np.abs(L.X - cx) / w, 0, 1) * ((L.Y > base - h) & (L.Y < base + 1))
        col *= np.clip((L.Y - (base - h)) / 8, 0, 1)
        L.over(C["cyan2"], col * colA * 0.6)
        L.over(C["cyan4"], np.clip(1 - np.abs(L.X - cx) / 1.5, 0, 1) * ((L.Y > base - h) & (L.Y < base + 1)) * colA * 0.8)
        rr = [4, 8, 12, 15, 17, 18][f]
        L.over(C["gold3"], ring_alpha(L, cx, base, rr, 1.2, 1.0, 0.45) * [1, 1, 0.9, 0.7, 0.45, 0.2][f])
        for k, (dx, ph, gold) in enumerate(motes):
            t = (f / 6 + ph) % 1.0
            y = base - 4 - t * 36
            if f >= 1 and y > 4:
                sparkle(img, int(cx + dx * (0.6 + t * 0.5)), int(y), 1 if k % 3 == 0 else 0,
                        C["gold4"] if gold else C["cyan4"], C["gold3"] if gold else C["cyan3"])
        frames.append(comp(L.img(12), img))
    return frames


# ======================================================================================
# Pickups and projectiles
# ======================================================================================
def coin() -> List[np.ndarray]:
    frames = []
    widths = [6, 4, 2, 4]
    for f in range(4):
        img = E.new(8, 8)
        w = widths[f]
        x0 = 4 - w / 2
        L = Layer(8, 8)
        m = (np.abs(L.X - 4) <= w / 2) & (np.abs(L.Y - 4) <= 3) & (((L.X - 4) / (w / 2 + 0.01)) ** 2 + ((L.Y - 4) / 3.2) ** 2 <= 1.05)
        img[m] = C["gold2"]
        # rim shading: left lit, right dark
        ys, xs = np.nonzero(m)
        for (y, x) in zip(ys, xs):
            if x == xs[ys == y].min():
                img[y, x] = C["gold3"] if f != 2 else C["gold4"]
            if x == xs[ys == y].max() and w > 2:
                img[y, x] = C["gold1"]
        if f == 0:                      # spark emblem
            hard(img, [(4, 2), (3, 3), (4, 3), (4, 4), (3, 5)], C["gold4"])
        elif f in (1, 3):
            hard(img, [(4, 3), (4, 4)] if f == 1 else [(3, 3), (3, 4)], C["gold4"])
        img = E.outline(img)
        frames.append(img)
    return frames


def xp_orb() -> List[np.ndarray]:
    frames = []
    base = ["..vv..", ".vVVv.", "vVccVv", "vVccVv", ".vVVv.", "..vv.."]
    for f in range(4):
        leg = {"v": C["violet2"], "V": C["violet3"] if f % 2 == 0 else C["violet4"],
               "c": C["cyan2"] if f in (0, 3) else C["cyan3"]}
        img = E.ascii_art(base, leg)
        hard(img, [(2, 2)], C["cyan4"] if f in (1, 2) else C["cyan3"])
        hard(img, [(1, 2)] if f < 2 else [(4, 3)], C["violet4"])
        L = Layer(6, 6)
        L.over(C["violet2"], np.clip(1 - L.dist(3, 3) / 3.3, 0, 1) * [0.35, 0.5, 0.6, 0.5][f])
        frames.append(comp(L.img(8), img))
    return frames


def ballista_bolt() -> np.ndarray:
    rows = [
        "...................",
        "oo...........oo....",
        "o2ooooooooooo43o...",
        "o21222222222333444o",
        "o2ooooooooooo43o...",
        "oo...........oo....",
    ]
    leg = {"o": OUT, "1": C["bone1"], "2": C["bone2"], "3": C["bone3"], "4": C["bone4"]}
    art = E.ascii_art([r.ljust(19, ".") for r in rows], leg)
    img = E.new(20, 6)
    E.paste(img, art, 1, 0)
    return img


def arrow() -> np.ndarray:
    rows = [
        "kc.......o..",
        ".kwwwwwwwsS.",
        "kc.......o..",
        "............",
    ]
    leg = {"k": C["crow2"], "c": C["crow3"], "w": PAL["wood3"], "s": C["silver1"], "S": C["silver3"], "o": C["silver0"]}
    img = E.ascii_art(rows, leg)
    return img


def feather() -> List[np.ndarray]:
    """Crow feather dart (enemy): dark vane with a pale quill and a faint red danger glow."""
    frames = []
    designs = [
        ["..........",
         "..........",
         "...oooo...",
         ".oo2332oo.",
         "oq22221qqo",
         ".oo1111oo.",
         "...oooo...",
         ".........."],
        ["..........",
         "......oo..",
         "....oo32o.",
         "..oo2231o.",
         ".o22221qo.",
         "oq1111oo..",
         ".oooooo...",
         ".........."],
    ]
    leg = {"o": OUT, "1": C["crow2"], "2": C["crow3"], "3": E.hexc("#76689e"), "q": C["bone3"]}
    for f in range(2):
        art = E.ascii_art(designs[f], leg)
        img = E.new(10, 10)
        E.paste(img, art, 0, 1)
        frames.append(with_glow(img, C["red2"], 1, 0.4))
    return frames


def bleed() -> List[np.ndarray]:
    frames = []
    drops = [(2, 1, 0), (5, 2, 2)]
    for f in range(4):
        img = E.new(8, 8)
        for (x, y0, ph) in drops:
            t = (f + ph) % 4
            y = y0 + t
            if y + 2 >= 8:
                continue
            hard(img, [(x, y)], C["red3"])
            hard(img, [(x, y + 1), (x - 1, y + 1), (x + 1, y + 1)], C["red2"])
            hard(img, [(x, y + 2)], C["red1"])
            hard(img, [(x - 1, y + 1)], C["red4"])
        frames.append(img)
    return frames


# ======================================================================================
# Indicators, auras, telegraphs
# ======================================================================================
def armour_break() -> np.ndarray:
    rows = [
        ".oooooo.",
        "o3322o1o",
        "o32r2o1o",
        "o322ro1o",
        ".o2r.21o",
        ".o2o221o",
        "..o21oo.",
        "...oo...",
    ]
    leg = {"o": OUT, "1": PAL["iron1"], "2": PAL["iron3"], "3": PAL["iron4"], "r": C["red3"]}
    return E.ascii_art(rows, leg)


def shadow() -> np.ndarray:
    L = Layer(16, 6)
    d = L.dist(8, 3, 8, 3)
    L.over(OUT, np.clip(1 - d, 0, 1) ** 0.6 * 0.55)
    return L.img(8)


def elite_aura() -> List[np.ndarray]:
    frames = []
    for f in range(2):
        L = Layer(32, 12)
        r = [0.86, 0.92][f]
        L.over(C["gold1"], np.clip(1 - L.dist(16, 6, 15, 5.5), 0, 1) ** 1.2 * 0.25)
        L.over(C["gold3"], np.clip(1 - np.abs(L.dist(16, 6, 15, 5.5) - r) / 0.12, 0, 1) * [0.75, 0.9][f])
        img = L.img(10)
        for k in range(4):
            a = k * math.pi / 2 + f * math.pi / 4
            sparkle(img, int(16 + math.cos(a) * 13 * r), int(6 + math.sin(a) * 4.7 * r), 0, C["gold4"], C["gold3"])
        frames.append(img)
    return frames


def boss_aura() -> List[np.ndarray]:
    frames = []
    for f in range(2):
        L = Layer(64, 20)
        d = L.dist(32, 10, 30.5, 9.2)
        ang = np.arctan2((L.Y - 10) / 9.2, (L.X - 32) / 30.5)
        L.over(C["red0"], np.clip(1 - d, 0, 1) ** 1.3 * 0.3)
        L.over(C["red2"], np.clip(1 - np.abs(d - 0.9) / 0.09, 0, 1) * [0.8, 0.95][f])
        L.over(C["gold3"], np.clip(1 - np.abs(d - 0.9) / 0.03, 0, 1) * [0.55, 0.8][f])
        # small flame tongues licking outward along the ring
        tongues = np.clip(np.cos(ang * 12 + f * math.pi) , 0, 1) ** 6
        L.over(C["red3"], np.clip(1 - np.abs(d - 0.97) / 0.06, 0, 1) * tongues * 0.8)
        frames.append(L.img(12))
    return frames


def range_ring() -> np.ndarray:
    S = 128
    img = E.new(S, S)
    c = S / 2 - 0.5
    r = 62
    n = 0
    # crisp 1 px dashes (6 on, 4 off) along the circle, plus a very faint halo
    steps = int(2 * math.pi * r * 2)
    for i in range(steps):
        a = i / steps * 2 * math.pi
        arc = a * r
        if (arc % 10) < 6:
            x, y = int(round(c + math.cos(a) * r)), int(round(c + math.sin(a) * r))
            img[y, x] = C["white"][:3] + (230,)
    L = Layer(S, S)
    L.over(C["white"], ring_alpha(L, S / 2, S / 2, r + 0.5, 3.0, soft=1.0) * 0.1)
    return comp(L.img(16), img)


def telegraph_circle() -> np.ndarray:
    S = 64
    img = E.new(S, S)
    c = S / 2 - 0.5
    r = 29.5
    steps = int(2 * math.pi * r * 3)
    for i in range(steps):
        a = i / steps * 2 * math.pi
        if ((a * r) % 8) < 5:
            for rr, col in ((r, C["red3"]), (r - 1, C["red2"])):
                x, y = int(round(c + math.cos(a) * rr)), int(round(c + math.sin(a) * rr))
                img[y, x] = col
    L = Layer(S, S)
    L.over(C["red1"], ring_alpha(L, S / 2, S / 2, r - 0.5, 4.0, soft=1.5) * 0.22)
    return comp(L.img(16), img)


def telegraph_chevron() -> np.ndarray:
    img = E.new(16, 16)
    for i in range(6):
        for t in range(3):
            hard(img, [(3 + i + t, 2 + i), (3 + i + t, 13 - i)], C["red3"] if t == 1 else C["red2"])
    hard(img, [(9, 7), (9, 8), (10, 7), (10, 8), (11, 7), (11, 8)], C["red3"])
    out = with_glow(img, C["red1"], 1, 0.45)
    out[..., 3] = (out[..., 3].astype(float) * 0.9).astype(np.uint8)
    return out


def telegraph_fill() -> np.ndarray:
    img = E.new(8, 8)
    img[:, :] = C["red2"][:3] + (72,)
    return img


def sector_edge() -> np.ndarray:
    img = E.new(8, 8)
    img[2, :] = C["red1"][:3] + (110,)
    img[3, :] = C["red3"][:3] + (240,)
    img[4, :] = C["red3"][:3] + (240,)
    img[5, :] = C["red1"][:3] + (110,)
    return img


def synergy_link() -> np.ndarray:
    L = Layer(8, 8)
    d = L.dist(4, 4)
    L.over(C["gold3"], np.clip(1 - d / 4.0, 0, 1) ** 1.2 * 0.8)
    L.over(C["cyan3"], np.clip(1 - d / 2.4, 0, 1) ** 1.1)
    L.over(C["cyan4"], np.clip(1 - d / 1.2, 0, 1))
    return L.img(16)


# ======================================================================================
# Registry
# ======================================================================================
# name: (builder, fps, loop, pivot)
ANIMS: Dict[str, Tuple[Callable[[], List[np.ndarray]], float, bool, Tuple[float, float]]] = {
    "spark_hit": (spark_hit, 20, False, CENTER),
    "arc_storm_strike": (arc_storm_strike, 16, False, (0.5, (96 - 91) / 96)),
    "explosion": (explosion, 14, False, CENTER),
    "frost_burst": (frost_burst, 14, False, CENTER),
    "gravity_well": (gravity_well, 10, True, CENTER),
    "barrier_ring": (barrier_ring, 8, True, CENTER),
    "heal": (heal, 10, False, CENTER),
    "burn": (burn, 10, True, CENTER),
    "stun": (stun, 8, True, CENTER),
    "death_poof": (death_poof, 14, False, (0.5, 0.25)),
    "coin": (coin, 8, True, CENTER),
    "xp_orb": (xp_orb, 8, True, CENTER),
    "shell": (shell, 10, True, CENTER),
    "feather": (feather, 8, True, CENTER),
    "powder_blast": (powder_blast, 14, False, CENTER),
    "priest_heal_ring": (priest_heal_ring, 12, False, CENTER),
    "level_up": (level_up, 12, False, (0.5, (48 - 41) / 48)),
    "winter_ring": (winter_ring, 12, False, CENTER),
    "shatter": (shatter, 14, False, CENTER),
    "bleed": (bleed, 6, True, CENTER),
    "elite_aura": (elite_aura, 4, True, CENTER),
    "boss_aura": (boss_aura, 4, True, CENTER),
    "dust": (dust, 12, False, (0.5, 0.25)),
    "impact": (impact, 16, False, CENTER),
    "target_reticle": (target_reticle, 4, True, CENTER),
}
SPRITES: Dict[str, Tuple[Callable[[], np.ndarray], Tuple[float, float]]] = {
    "chill": (chill, CENTER),
    "frozen": (frozen, (0.5, 0.1)),
    "ballista_bolt": (ballista_bolt, CENTER),
    "arrow": (arrow, CENTER),
    "mark": (mark, CENTER),
    "armour_break": (armour_break, CENTER),
    "shadow": (shadow, CENTER),
    "lightning_tex": (lightning_tex, CENTER),
    "range_ring": (range_ring, CENTER),
    "telegraph_circle": (telegraph_circle, CENTER),
    "telegraph_chevron": (telegraph_chevron, CENTER),
    "telegraph_fill": (telegraph_fill, CENTER),
    "synergy_link": (synergy_link, CENTER),
    "sector_edge": (sector_edge, CENTER),
}


def build(reg: "E.Registry") -> None:
    for name, (fn, fps, loop, pivot) in ANIMS.items():
        reg.anim(ATLAS, f"fx/{name}", fn(), fps=fps, loop=loop, pivot=pivot)
    for name, (fn, pivot) in SPRITES.items():
        reg.sprite(ATLAS, f"fx/{name}", fn(), pivot=pivot)


# ======================================================================================
# Iteration previews
# ======================================================================================
def preview(names: Optional[Sequence[str]] = None, bg: str = "gravewood"):
    os.makedirs(ITER_DIR, exist_ok=True)
    try:
        import gen_env as V
        ground = V.gravewood_ground() if bg == "gravewood" else V.moonfall_ground()
    except Exception:
        ground = None
    for name, (fn, fps, loop, pivot) in ANIMS.items():
        if names and name not in names:
            continue
        frames = fn()
        shown = []
        for fr in frames:
            h, w = fr.shape[:2]
            if ground is not None:
                base = np.tile(ground, (h // 128 + 1, w // 128 + 1, 1))[:h, :w].copy()
                E.paste(base, fr, 0, 0)
                shown.append(base)
            else:
                shown.append(fr)
        sc = 6 if max(frames[0].shape[:2]) <= 24 else (4 if max(frames[0].shape[:2]) <= 48 else 2)
        E.preview_images(shown, os.path.join(ITER_DIR, f"fx_{name}.png"), scale=sc)
    sprites = []
    for name, (fn, pivot) in SPRITES.items():
        if names and name not in names:
            continue
        sprites.append(fn())
    if sprites:
        E.preview_images([s for s in sprites if max(s.shape[:2]) <= 32], os.path.join(ITER_DIR, "fx_sprites_small.png"), scale=8)
        E.preview_images([s for s in sprites if max(s.shape[:2]) > 32], os.path.join(ITER_DIR, "fx_sprites_big.png"), scale=3)


if __name__ == "__main__":
    import time
    t = time.time()
    preview(sys.argv[1:] or None)
    print(f"done in {time.time() - t:.1f}s")
