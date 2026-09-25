"""
gen_env.py - battlefield environments for EVIL CATS (atlases "env_gravewood", "env_moonfall").

Biome 1, Gravewood Outskirts: moonlit haunted woodland (dark blue-green grass, dirt paths,
dead trees, broken walls, graves, pale-blue lanterns). Biome 2, Moonfall Ruins: cracked
flagstone courtyards under a violet sky (cat statues, broken pillars, rubble, violet crystals,
braziers, storm-lit puddles, torn banners).

The terrain is deliberately QUIET (low contrast, desaturated gw_*/mf_* colours) so that the
bright, outlined enemies always read above it. Props carry a little more contrast.

Sprites (per biome <b> = gravewood | moonfall):
  env/<b>/ground        128x128 seamless tile (all features wrap around the edges)
  env/<b>/path/<i>      16x16 soft-edged path stamps (i = 0..3), stamped every ~0.4 units
  env/<b>/prop/<name>   props, pivot (0.5, 0.1) at the base
  env/<b>/vignette      64x64 dark corner overlay

Hard-surface props (walls, graves, rocks, pillars, plinths, rubble, stumps...) are modelled as
tiny voxel sculptures and rendered with the same oblique top-down projection as the citadel
(screen_y = ground_y - height), so everything on the battlefield shares one camera. Organic
props (trees, bushes, grass, crystals, flames, cloth) are drawn procedurally in 2D.

Run directly for previews:  python3 Tools/art/gen_env.py  -> /tmp/claude-0/world_iter/
"""
from __future__ import annotations

import math
import os
import sys
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import eclib as E  # noqa: E402
from eclib import PAL  # noqa: E402

ITER_DIR = "/tmp/claude-0/world_iter"
OUT = PAL["outline"]
PROP_PIVOT = (0.5, 0.1)
TILE = 128

BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0 + 1 / 32


def bayer(h: int, w: int) -> np.ndarray:
    return np.tile(BAYER4, (h // 4 + 1, w // 4 + 1))[:h, :w]


def mix(c1, c2, t: float):
    return tuple(int(round(c1[i] * (1 - t) + c2[i] * t)) for i in range(3)) + (255,)


def tile_noise(size: int, cells: int, rnd) -> np.ndarray:
    """Periodic (seamlessly tiling) smooth value noise in [0, 1]."""
    g = np.array([[rnd.random() for _ in range(cells)] for _ in range(cells)])
    p = np.arange(size) * cells / size
    i0 = np.floor(p).astype(int)
    t = p - i0
    t = t * t * (3 - 2 * t)
    i1 = (i0 + 1) % cells
    a = g[i0[:, None], i0[None, :]]
    b = g[i0[:, None], i1[None, :]]
    c = g[i1[:, None], i0[None, :]]
    d = g[i1[:, None], i1[None, :]]
    tx, ty = t[None, :], t[:, None]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def fbm(size: int, rnd, octaves=((4, 0.5), (8, 0.27), (16, 0.15), (32, 0.08))) -> np.ndarray:
    v = sum(w * tile_noise(size, c, rnd) for c, w in octaves)
    v = v - v.min()
    return v / max(1e-6, v.max())


def wrap_px(img: np.ndarray, x: int, y: int, c) -> None:
    h, w = img.shape[:2]
    img[y % h, x % w] = c


# ======================================================================================
# Ground tiles
# ======================================================================================
GW = {k: PAL[k] for k in ("gw_grass0", "gw_grass1", "gw_grass2", "gw_grass3", "gw_moon",
                           "gw_path0", "gw_path1", "gw_path2")}
GW_MOONGRASS = mix(PAL["gw_grass3"], PAL["gw_moon"], 0.45)
GW_LEAF = E.hexc("#2b2a2a")
GW_LEAF2 = E.hexc("#353130")


# grass tufts: L = light tip, M = mid blade, D = dark root/shadow
TUFTS = [
    ["L.L", ".D."],
    [".L.", "LML", ".D."],
    ["L..", ".L.", ".D."],
    ["..L", ".L.", ".D."],
    ["L.L.", ".LM.", "..D."],
    [".L", "LM", "D."],
]


def gravewood_ground(seed: int = 101) -> np.ndarray:
    rnd = E.rng(seed)
    S = TILE
    img = E.new(S, S)
    v = fbm(S, rnd, ((4, 0.18), (8, 0.36), (16, 0.28), (32, 0.18)))
    moon = fbm(S, rnd, ((2, 0.5), (4, 0.35), (8, 0.15)))
    bay = bayer(S, S)
    # soft 3-tone mottling: mostly grass1, lighter moonlit clearings, darker hollows
    lvl = 0.35 + v * 1.6 + (moon - 0.5) * 0.5 + (bay - 0.5) * 0.5
    tone = np.clip(np.floor(lvl), 0, 2).astype(int)
    ramp = np.array([GW["gw_grass0"], GW["gw_grass1"], GW["gw_grass2"]], np.uint8)
    img[:] = ramp[tone]

    # grass tufts, denser in the lighter areas
    placed = 0
    while placed < 430:
        x, y = rnd.randrange(S), rnd.randrange(S)
        if rnd.random() > 0.25 + 0.75 * v[y, x]:
            continue
        placed += 1
        t = tone[y, x]
        light = GW["gw_grass3"] if t >= 1 else GW["gw_grass2"]
        if t == 2 and moon[y, x] > 0.6 and rnd.random() < 0.22:
            light = GW_MOONGRASS
        midc = GW["gw_grass2"] if t >= 1 else GW["gw_grass1"]
        dark = GW["gw_grass0"]
        tf = TUFTS[rnd.randrange(len(TUFTS))]
        for yy, row in enumerate(tf):
            for xx, ch in enumerate(row):
                if ch == "L":
                    wrap_px(img, x + xx, y + yy, light)
                elif ch == "M":
                    wrap_px(img, x + xx, y + yy, midc)
                elif ch == "D":
                    wrap_px(img, x + xx, y + yy, dark)
    # dirt specks in the hollows, small pebbles, a few dead leaves
    for _ in range(90):
        x, y = rnd.randrange(S), rnd.randrange(S)
        if tone[y, x] == 0:
            wrap_px(img, x, y, GW["gw_path0"])
    for _ in range(12):
        x, y = rnd.randrange(S), rnd.randrange(S)
        wrap_px(img, x, y, mix(GW["gw_grass3"], PAL["stone3"], 0.35))
        wrap_px(img, x + 1, y, GW["gw_grass3"])
        wrap_px(img, x, y + 1, GW["gw_grass0"])
        wrap_px(img, x + 1, y + 1, GW["gw_grass0"])
    for _ in range(10):
        x, y = rnd.randrange(S), rnd.randrange(S)
        wrap_px(img, x, y, GW_LEAF2)
        wrap_px(img, x + 1, y, GW_LEAF)
    return img


MF = {k: PAL[k] for k in ("mf_stone0", "mf_stone1", "mf_stone2", "mf_stone3", "mf_sky", "mf_storm",
                           "mf_path0", "mf_path1", "mf_path2")}
MF_MOSS = E.hexc("#28302f")
MF_MOSS2 = E.hexc("#2f3934")


def moonfall_ground(seed: int = 202) -> np.ndarray:
    """Weathered courtyard of 32 px flagstones (some split in halves/quarters). The 32 px grid
    divides the tile, so it tiles seamlessly; all weathering wraps around the edges."""
    rnd = E.rng(seed)
    S = TILE
    img = E.new(S, S, MF["mf_stone0"])
    sid = np.full((S, S), -1, int)
    stones = []
    for gy in range(0, S, 32):
        for gx in range(0, S, 32):
            r = rnd.random()
            if r < 0.5:
                parts = [(0, 0, 32, 32)]
            elif r < 0.7:
                parts = [(0, 0, 32, 16), (0, 16, 32, 16)]
            elif r < 0.88:
                parts = [(0, 0, 16, 32), (16, 0, 16, 32)]
            else:
                parts = [(0, 0, 16, 16), (16, 0, 16, 16), (0, 16, 16, 16), (16, 16, 16, 16)]
            for (px_, py_, w_, h_) in parts:
                stones.append((gx + px_, gy + py_, w_, h_))
    ramp = np.array([MF["mf_stone0"], MF["mf_stone1"], MF["mf_stone2"], MF["mf_stone3"]], np.uint8)
    noise = fbm(S, rnd, ((8, 0.5), (16, 0.3), (32, 0.2)))
    dust = fbm(S, rnd, ((4, 0.5), (8, 0.35), (16, 0.15)))
    bay = bayer(S, S)
    yy, xx = np.mgrid[0:S, 0:S]
    missing = set(rnd.sample(range(len(stones)), 2))
    for n, (x0, y0, w_, h_) in enumerate(stones):
        lx, ly = xx - x0, yy - y0
        inside = (lx >= 1) & (lx < w_) & (ly >= 1) & (ly < h_)
        corner = ((lx < 2) | (lx >= w_ - 1)) & ((ly < 2) | (ly >= h_ - 1))
        inside &= ~(corner & (rnd.random() < 0.7))
        sid[inside] = n
        if n in missing:
            img[inside] = MF["mf_path0"]
            continue
        base = rnd.choice((1, 2, 2))
        spk = np.array([[rnd.random() for _ in range(S)] for _ in range(1)])  # keep rng stream stable
        t = base + np.where((noise > 0.72) & (bay < (noise - 0.72) * 2.5), 1 - 2 * (base == 2), 0)
        tone = np.clip(t, 1, 2).astype(int)
        img[inside] = ramp[tone[inside]]
        # a soft bevel: lit top edge, shaded right/bottom edges (only one step)
        top_edge = inside & (ly == 1) & (lx < w_ - 1)
        img[top_edge] = ramp[np.minimum(3, tone[top_edge] + 1)]
        bot_edge = inside & ((ly == h_ - 1) | (lx == w_ - 1))
        img[bot_edge] = ramp[np.maximum(1, tone[bot_edge] - 1)]
        for _ in range(w_ * h_ // 55):
            sx_, sy_ = x0 + rnd.randrange(2, w_ - 1), y0 + rnd.randrange(2, h_ - 1)
            wrap_px(img, sx_, sy_, ramp[max(1, base - 1)] if rnd.random() < 0.7 else ramp[min(3, base + 1)])
    # rubble + weeds in the missing stones
    for n in missing:
        x0, y0, w_, h_ = stones[n]
        for _ in range(w_ * h_ // 40):
            x, y = x0 + rnd.randrange(2, w_ - 1), y0 + rnd.randrange(2, h_ - 1)
            if rnd.random() < 0.5:
                wrap_px(img, x, y, MF["mf_stone2"])
                wrap_px(img, x, y + 1, MF["mf_stone0"])
            else:
                wrap_px(img, x, y, MF_MOSS2)
                wrap_px(img, x + 1, y + 1, MF_MOSS)
    # long jagged cracks: keep a main heading, jitter sideways (no loops)
    for _ in range(9):
        x, y = rnd.randrange(S), rnd.randrange(S)
        head = rnd.uniform(0, 2 * math.pi)
        fx, fy = float(x), float(y)
        for _ in range(rnd.randint(8, 18)):
            ix, iy = int(round(fx)), int(round(fy))
            if sid[iy % S, ix % S] >= 0:
                wrap_px(img, ix, iy, MF["mf_stone0"])
                if rnd.random() < 0.45 and sid[(iy + 1) % S, (ix + 1) % S] >= 0:
                    wrap_px(img, ix + 1, iy + 1, MF["mf_stone2"])
            head += rnd.uniform(-0.6, 0.6)
            fx += math.cos(head)
            fy += math.sin(head)
    # moss creeping along some joints
    joint = sid < 0
    moss = joint & (noise > 0.58) & (bay < 0.7)
    img[moss] = np.where((bay[moss] < 0.35)[:, None], np.array(MF_MOSS2, np.uint8), np.array(MF_MOSS, np.uint8))
    # dust drifts soften the grid (ordered dither, low contrast)
    drift = (dust > 0.68) & (bay < (dust - 0.68) * 1.6)
    img[drift & joint] = MF["mf_stone1"]
    img[drift & ~joint & (bay < 0.25)] = MF["mf_path0"]
    # sparse specks
    for _ in range(50):
        x, y = rnd.randrange(S), rnd.randrange(S)
        if sid[y, x] >= 0:
            wrap_px(img, x, y, MF["mf_stone1"] if rnd.random() < 0.6 else MF["mf_stone3"])
    return img


# ======================================================================================
# Path stamps
# ======================================================================================
def path_stamp(biome: str, i: int) -> np.ndarray:
    """16x16 soft-edged dirt (gravewood) / gravel-dust (moonfall) stamp. The core is opaque and
    evenly textured so overlapping stamps merge without seams; the fringe alpha is quantised to
    a few steps with an ordered dither so the edge stays pixel-crisp but soft."""
    rnd = E.rng(3000 + i * 17 + (0 if biome == "gravewood" else 500))
    S = 16
    img = E.new(S, S)
    yy, xx = np.mgrid[0:S, 0:S]
    cx, cy = 7.5 + rnd.uniform(-0.4, 0.4), 7.5 + rnd.uniform(-0.4, 0.4)
    ang = np.arctan2(yy - cy, xx - cx)
    rad = np.full(ang.shape, 6.0)
    for hmn in (2, 3, 5):
        rad = rad + rnd.uniform(0.25, 0.65) * np.sin(ang * hmn + rnd.uniform(0, 6.28))
    d = np.hypot(xx - cx, yy - cy)
    edge = d - rad
    a = np.clip(0.55 - edge / (2.4 if biome == "gravewood" else 2.0), 0, 1)
    a = np.clip(np.floor(a * 4 + (bayer(S, S) - 0.5) * 0.9) / 4, 0, 1)
    n = np.array([[rnd.random() for _ in range(S)] for _ in range(S)])
    if biome == "gravewood":
        c0, c1, c2 = PAL["gw_path0"], PAL["gw_path1"], PAL["gw_path2"]
        img[:, :, :3] = np.array(c1[:3], np.uint8)
        img[n < 0.14, :3] = np.array(c0[:3], np.uint8)
        img[n > 0.94, :3] = np.array(c2[:3], np.uint8)
        # a couple of pebbles (light top, dark underside)
        for _ in range(2):
            px_, py_ = rnd.randrange(4, 12), rnd.randrange(4, 11)
            img[py_, px_, :3] = np.array(c2[:3], np.uint8)
            img[py_ + 1, px_, :3] = np.array(c0[:3], np.uint8)
    else:
        # pale moon-dust over the flagstones: lighter than the stone so routes read clearly
        c0, c1, c2 = PAL["mf_path1"], PAL["mf_path2"], mix(PAL["mf_path2"], PAL["mf_storm"], 0.18)
        img[:, :, :3] = np.array(c1[:3], np.uint8)
        img[n < 0.2, :3] = np.array(c0[:3], np.uint8)
        # gravel: small light stones with a dark lower edge
        for _ in range(8):
            px_, py_ = rnd.randrange(3, 13), rnd.randrange(3, 12)
            img[py_, px_, :3] = np.array(c2[:3], np.uint8)
            if rnd.random() < 0.5:
                img[py_, px_ + 1, :3] = np.array(c2[:3], np.uint8)
            img[py_ + 1, px_, :3] = np.array(PAL["mf_path0"][:3], np.uint8)
    img[:, :, 3] = (a * 255).astype(np.uint8)
    return img


# ======================================================================================
# Vignette
# ======================================================================================
def vignette(color) -> np.ndarray:
    S = 64
    img = E.new(S, S)
    yy, xx = np.mgrid[0:S, 0:S]
    nx = (xx + 0.5 - S / 2) / (S / 2)
    ny = (yy + 0.5 - S / 2) / (S / 2)
    r = np.sqrt(nx * nx + ny * ny) / math.sqrt(2)
    a = np.clip((r - 0.45) / 0.55, 0, 1) ** 1.6 * 215
    img[:, :, :3] = np.array(color[:3], np.uint8)
    img[:, :, 3] = a.astype(np.uint8)
    return img


# ======================================================================================
# Tiny voxel renderer for hard-surface props (same camera as the citadel)
# ======================================================================================
_LIGHT = np.array([-0.62, 0.12, 0.78])       # screen top-left, slightly toward the viewer
_LIGHT = _LIGHT / np.linalg.norm(_LIGHT)


def _blur3(a: np.ndarray) -> np.ndarray:
    """3x3x3 box blur with zero padding."""
    p = np.pad(a, 1)
    out = np.zeros_like(a)
    for dz in range(3):
        for dy in range(3):
            for dx in range(3):
                out += p[dz:dz + a.shape[0], dy:dy + a.shape[1], dx:dx + a.shape[2]]
    return out / 27.0


class Vox:
    """Voxel sculpture: m[z, y, x] material index (0 = empty) into a list of ramps;
    t[z, y, x] integer tone offset (texture: mortar, moss, cracks...)."""

    def __init__(self, w: int, d: int, h: int):
        self.w, self.d, self.h = w, d, h
        self.m = np.zeros((h, d, w), np.uint8)
        self.t = np.zeros((h, d, w), np.int8)
        z, y, x = np.mgrid[0:h, 0:d, 0:w]
        self.X, self.Y, self.Z = x + 0.5, y + 0.5, z + 0.5

    def fill(self, mask, mat: int, tone: int = 0) -> None:
        self.m[mask] = mat
        self.t[mask] = tone

    def box(self, x0, x1, y0, y1, z0, z1):
        return (self.X > x0) & (self.X < x1) & (self.Y > y0) & (self.Y < y1) & (self.Z > z0) & (self.Z < z1)

    def ellipsoid(self, cx, cy, cz, rx, ry, rz):
        return ((self.X - cx) / rx) ** 2 + ((self.Y - cy) / ry) ** 2 + ((self.Z - cz) / rz) ** 2 <= 1.0

    def cyl(self, cx, cy, r, z0, z1):
        return ((self.X - cx) ** 2 + (self.Y - cy) ** 2 <= r * r) & (self.Z > z0) & (self.Z < z1)

    def render(self, ramps: Sequence[Sequence], ambient: float = 0.34, shadows: bool = True,
               edge_lines: bool = True, emissive: Sequence[int] = ()) -> np.ndarray:
        W, H = self.w, self.d + self.h
        occ = self.m > 0
        rows = np.arange(H)[:, None]
        cols = np.broadcast_to(np.arange(W)[None, :], (H, W))
        hit = np.zeros((H, W), bool)
        J = np.zeros((H, W), int)
        K = np.zeros((H, W), int)
        F = np.zeros((H, W), int)
        for k in range(self.h - 1, -1, -1):
            for face, dj in ((0, 1), (1, 0)):
                jj = np.broadcast_to(rows + k + dj - self.h, (H, W))
                ok = (jj >= 0) & (jj < self.d)
                sol = np.zeros((H, W), bool)
                sol[ok] = occ[k, jj[ok], cols[ok]]
                new = sol & ~hit
                J[new], K[new], F[new] = jj[new], k, face
                hit |= new
        ys, xs = np.nonzero(hit)
        j, k, f = J[ys, xs], K[ys, xs], F[ys, xs]
        # normals from the blurred occupancy, nudged toward the face normal
        b = _blur3(occ.astype(float))
        gz, gy, gx = np.gradient(b)
        n = -np.stack([gx[k, j, xs], gy[k, j, xs], gz[k, j, xs]], axis=1)
        n[:, 2] += np.where(f == 0, 0.35, 0.0)
        n[:, 1] += np.where(f == 1, 0.35, 0.0)
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-6
        lam = np.clip((n @ _LIGHT + 0.45) / 1.45, 0, 1)      # wrap lighting
        if shadows:
            p0 = np.stack([xs + 0.5, j + 0.5 + (f == 1) * 0.51, k + 0.5 + (f == 0) * 0.51], axis=1)
            sh = np.zeros(len(xs), bool)
            for tt in np.arange(0.8, 24, 0.6):
                q = np.floor(p0 + tt * _LIGHT[None, :]).astype(int)
                ok = (q[:, 0] >= 0) & (q[:, 0] < self.w) & (q[:, 1] >= 0) & (q[:, 1] < self.d) & (q[:, 2] >= 0) & (q[:, 2] < self.h)
                sh[ok] |= occ[q[ok, 2], q[ok, 1], q[ok, 0]]
            lam = np.where(sh, lam * 0.6, lam)
        lam = ambient + (1 - ambient) * lam
        mat = self.m[k, j, xs]
        tone = self.t[k, j, xs]
        dth = BAYER4[ys % 4, xs % 4] - 0.5
        img = E.new(W, H)
        for mi, ramp in enumerate(ramps, start=1):
            sel = mat == mi
            if not sel.any():
                continue
            nr = len(ramp)
            idx = np.floor(lam[sel] * (nr - 1) + 0.5 + dth[sel] * 0.12).astype(int) + tone[sel]
            if mi in emissive:
                idx = (nr - 1) + tone[sel]
            idx = np.clip(idx, 0, nr - 1)
            img[ys[sel], xs[sel]] = np.array(ramp, np.uint8)[idx]
        if edge_lines:
            P = np.zeros((H, W, 3))
            P[ys, xs] = np.stack([xs + 0.5, j + 0.5, k + 0.5 + (f == 0) * 0.5], axis=1)
            depth = np.full((H, W), -1e9)
            depth[ys, xs] = j + k
            edge = np.zeros((H, W), bool)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = np.roll(np.roll(P, dy, 0), dx, 1)
                qd = np.roll(np.roll(depth, dy, 0), dx, 1)
                qh = np.roll(np.roll(hit, dy, 0), dx, 1)
                dist = np.sqrt(np.sum((P - q) ** 2, axis=2))
                edge |= hit & qh & (dist > 2.9) & (depth < qd - 2)
            img[edge] = OUT
        return img


def outline_img(img: np.ndarray) -> np.ndarray:
    """1 px outline around the opaque region, grown into a 1 px transparent margin."""
    h, w = img.shape[:2]
    big = E.new(w + 2, h + 2)
    big[1:-1, 1:-1] = img
    return E.outline(big)


def place_prop(img: np.ndarray, ref_x: float, ref_y: float, size: Tuple[int, int],
               shadow: Optional[np.ndarray] = None) -> np.ndarray:
    """Put a rendered prop into its final canvas so the ground reference point (ref_x, ref_y)
    (boundary coords in img) lands exactly on the (0.5, 0.1) pivot."""
    Wf, Hf = size
    out = E.new(Wf, Hf)
    ox = int(round(Wf * PROP_PIVOT[0] - ref_x))
    oy = int(round(Hf * (1 - PROP_PIVOT[1]) - ref_y))
    if shadow is not None:
        E.paste(out, shadow, ox, oy)
    E.paste(out, img, ox, oy)
    return out


def contact_shadow(w: int, h: int, cx: float, cy: float, rx: float, ry: float, alpha: int = 80) -> np.ndarray:
    """Hard-edged translucent ellipse (grounds a prop on any terrain)."""
    sh = E.new(w, h)
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((xx + 0.5 - cx) / rx) ** 2 + ((yy + 0.5 - cy) / ry) ** 2 <= 1.0
    sh[m] = (8, 6, 12, alpha)
    return sh


# ---- prop palettes ---------------------------------------------------------------------
GW_STONE = [E.hexc("#15191c"), E.hexc("#1f2629"), E.hexc("#2b3437"), E.hexc("#3a4548"), E.hexc("#4d5a5b"), E.hexc("#627274")]
GW_MOSS = [E.hexc("#141d18"), E.hexc("#1b2a21"), E.hexc("#24382a"), E.hexc("#2f4834"), E.hexc("#3b5a40")]
GW_DIRT = [E.hexc("#141216"), E.hexc("#1e1a20"), E.hexc("#28232b"), E.hexc("#332c36"), E.hexc("#3d3541")]
GW_WOOD = [E.hexc("#151216"), E.hexc("#1f1a1f"), E.hexc("#2a2329"), E.hexc("#372e34"), E.hexc("#463b41"), E.hexc("#564a4e")]
MF_STONE = [E.hexc("#17151f"), E.hexc("#221f2e"), E.hexc("#2f2b3f"), E.hexc("#3e3953"), E.hexc("#514b69"), E.hexc("#686184")]
MF_IRON = [PAL["iron0"], PAL["iron1"], PAL["iron2"], PAL["iron3"]]


def brick_tone(v: Vox, course: int = 3, brick: int = 5, seed: int = 0) -> np.ndarray:
    """Mortar pattern as a tone offset (-1 on mortar lines) for walls built along x."""
    zc = np.floor(v.Z).astype(int)
    xc = np.floor(v.X).astype(int)
    row = zc // course
    mortar = (zc % course == course - 1) | (((xc + (row % 2) * (brick // 2 + 1)) % brick) == 0)
    return np.where(mortar, -1, 0).astype(np.int8)


# ---- gravewood stone props ---------------------------------------------------------------
def wall_broken(variant: str) -> np.ndarray:
    rnd = E.rng({"a": 11, "b": 12, "c": 13}[variant])
    W_, D_, H_ = 30, 7, 14
    v = Vox(W_, D_, H_)
    length = {"a": 26, "b": 22, "c": 24}[variant]
    x0 = (W_ - length) / 2
    # broken top profile (height per column)
    prof = []
    base_h = {"a": 11, "b": 8, "c": 12}[variant]
    for x in range(W_):
        t = (x - x0) / max(1, length)
        hgt = base_h
        if variant == "a":
            hgt = base_h - max(0, (t - 0.55) * 18) + rnd.choice((0, 0, -1))
        elif variant == "b":
            hgt = base_h - abs(t - 0.4) * 6 + rnd.choice((0, -1, -1, -2))
        else:
            hgt = base_h - (0 if t < 0.35 else 5) - max(0, (t - 0.8) * 20) + rnd.choice((0, 0, -1))
        prof.append(max(2, int(round(hgt))))
    prof = np.array(prof)[None, None, :]
    body = (v.X > x0) & (v.X < x0 + length) & (v.Y > 2) & (v.Y < 5) & (v.Z < prof)
    v.fill(body, 1)
    v.t[body] = brick_tone(v)[body]
    # moss on some top voxels
    topz = prof[0, 0] - 1
    for x in range(W_):
        if x0 < x + 0.5 < x0 + length and rnd.random() < 0.45:
            v.m[topz[x], 2:5, x] = 2
    # fallen bricks
    for _ in range({"a": 3, "b": 4, "c": 2}[variant]):
        bx = rnd.uniform(x0 - 2, x0 + length + 1)
        by = rnd.choice((5.6, 6.2, 1.2))
        v.fill(v.box(bx, bx + rnd.choice((2, 3)), by - 0.9, by + 0.9, 0, rnd.choice((1, 2))), 1)
    img = v.render([GW_STONE, GW_MOSS])
    img = outline_img(img)
    sh = contact_shadow(img.shape[1], img.shape[0], img.shape[1] / 2 + 1, H_ + 4.6 + 1, length / 2 + 2, 3.2)
    return place_prop(img, img.shape[1] / 2, H_ + 3.5 + 1, (32, 22), sh)


def grave(variant: str) -> np.ndarray:
    W_, D_, H_ = 12, 7, 12
    v = Vox(W_, D_, H_)
    cx = 6.0
    # dirt mound in front
    v.fill(v.ellipsoid(cx, 4.6, 0.0, 4.2, 2.2, 1.6), 3)
    if variant == "a":        # rounded headstone
        slab = v.box(cx - 3.5, cx + 3.5, 1.2, 3.0, 0, 11) & (((v.X - cx) / 3.5) ** 2 + ((v.Z - 8.0) / 3.0) ** 2 <= 1.0) | v.box(cx - 3.5, cx + 3.5, 1.2, 3.0, 0, 8.2)
        v.fill(slab, 1)
        for (px_, pz_) in ((-1, 7), (1, 7), (-2, 6), (2, 6), (-1, 5), (0, 5), (1, 5), (0, 4)):
            v.t[(np.abs(v.X - (cx + px_)) < 0.5) & (np.abs(v.Z - (pz_ + 0.5)) < 0.5) & (v.Y > 2.0) & (v.Y < 3.0)] = -2
    elif variant == "b":      # stone cross
        v.fill(v.box(cx - 1, cx + 1, 1.2, 3.0, 0, 11), 1)
        v.fill(v.box(cx - 3, cx + 3, 1.2, 3.0, 6.5, 8.5), 1)
        v.fill(v.box(cx - 2, cx + 2, 0.8, 3.4, 0, 1.5), 1)
    elif variant == "c":      # cat-eared headstone
        v.fill(v.box(cx - 3.5, cx + 3.5, 1.2, 3.0, 0, 8.5), 1)
        for side in (-1, 1):
            ex = cx + side * 2.4                       # ear triangle: 3 px wide base, 1 px tip
            ear = v.box(ex - 1.5, ex + 1.5, 1.2, 3.0, 8.4, 9.5) | v.box(ex - 1.0 + side * 0.5, ex + 1.0 + side * 0.5, 1.2, 3.0, 9.4, 10.5)
            ear |= v.box(ex - 0.5 + side * 1.0, ex + 0.5 + side * 1.0, 1.2, 3.0, 10.4, 11.5)
            v.fill(ear, 1)
        # two carved eye dots
        for side in (-1, 1):
            v.t[(np.abs(v.X - (cx + side * 1.5)) < 0.6) & (np.abs(v.Z - 6.5) < 0.6) & (v.Y > 2.0) & (v.Y < 3.0)] = -2
    else:                     # broken, tilted slab
        tilt = (v.Z - 0) * 0.28
        slab = (v.X - tilt > cx - 3.8) & (v.X - tilt < cx + 2.8) & (v.Y > 1.4) & (v.Y < 3.2) & (v.Z < 7.5 - np.maximum(0, (v.X - cx) * 0.9))
        v.fill(slab, 1)
        v.fill(v.box(cx + 2.5, cx + 4.5, 4.4, 6.0, 0, 1.2), 1)
    # weathering speckle
    rnd = E.rng(ord(variant))
    st = v.m == 1
    speck = st & (np.array([[[rnd.random() for _ in range(W_)] for _ in range(D_)] for _ in range(H_)]) < 0.08)
    v.t[speck] -= 1
    img = outline_img(v.render([GW_STONE, GW_MOSS, GW_DIRT]))
    sh = contact_shadow(img.shape[1], img.shape[0], cx + 1 + 0.8, H_ + 3.6 + 1, 5.0, 2.4)
    return place_prop(img, cx + 1, H_ + 3.0 + 1, (14, 18), sh)


def rock(variant: str) -> np.ndarray:
    rnd = E.rng({"a": 31, "b": 32}[variant])
    W_, D_, H_ = (15, 10, 8) if variant == "a" else (11, 8, 6)
    v = Vox(W_, D_, H_)
    cx, cy = W_ / 2, D_ / 2
    rx, ry, rz = (6.2, 3.8, 5.5) if variant == "a" else (4.4, 3.0, 4.0)
    # lumpy ellipsoid: perturb with a few bumps
    blob = v.ellipsoid(cx, cy, 0, rx, ry, rz)
    for _ in range(4):
        bx, by = cx + rnd.uniform(-rx * 0.6, rx * 0.6), cy + rnd.uniform(-ry * 0.5, ry * 0.5)
        blob |= v.ellipsoid(bx, by, 0, rx * 0.55, ry * 0.6, rz * rnd.uniform(0.7, 1.05))
    blob &= v.Z < rz
    v.fill(blob, 1)
    # facet-ish tone variation + moss cap on the upper surfaces
    fac = np.floor((v.X * 0.7 + v.Z * 0.9 + v.Y * 0.3)) % 3 == 0
    v.t[blob & fac] = -1
    top = blob & ~np.roll(blob, -1, axis=0)
    rr = np.array([[[rnd.random() for _ in range(W_)] for _ in range(D_)] for _ in range(H_)])
    mossy = top & (v.Z > rz * 0.62) & (rr < 0.55) & (v.X < cx + rx * 0.4)
    v.m[mossy] = 2
    img = outline_img(v.render([GW_STONE, GW_MOSS]))
    sh = contact_shadow(img.shape[1], img.shape[0], cx + 1 + 1, H_ + cy + 1.5 + 1, rx + 1, ry * 0.7 + 1)
    size = (16, 14) if variant == "a" else (12, 10)
    return place_prop(img, cx + 1, H_ + cy + 1 + 1, size, sh)


def stump() -> np.ndarray:
    W_, D_, H_ = 15, 12, 7
    v = Vox(W_, D_, H_)
    cx, cy = 7.5, 6.0
    v.fill(v.cyl(cx, cy, 4.3, 0, 6.0), 1)
    rnd = E.rng(44)
    for ang in (0.3, 2.0, 3.4, 4.9):
        for t in np.arange(0, 3.2, 0.5):
            rx_, ry_ = cx + math.cos(ang) * (4 + t), cy + math.sin(ang) * (3 + t) * 0.8
            v.fill(v.cyl(rx_, ry_, 1.3 - t * 0.2, 0, 2.2 - t * 0.5), 1)
    # rings on the top face, bark grooves on the sides
    r = np.hypot(v.X - cx, v.Y - cy)
    top = (v.m == 1) & (v.Z > 5.0)
    v.m[top] = 2
    v.t[top & (np.floor(r * 1.2) % 2 == 0)] = -1
    groove = (v.m == 1) & (np.floor(np.arctan2(v.Y - cy, v.X - cx) * 3.5) % 2 == 0)
    v.t[groove] = -1
    ring_pal = [E.hexc("#28232a"), E.hexc("#362e35"), E.hexc("#463c43"), E.hexc("#564b50"), E.hexc("#665a5c")]
    img = outline_img(v.render([GW_WOOD, ring_pal]))
    sh = contact_shadow(img.shape[1], img.shape[0], cx + 2, H_ + cy + 1.8, 6.5, 3.4)
    return place_prop(img, cx + 1, H_ + cy + 1, (16, 16), sh)


# ---- 2D organic props -------------------------------------------------------------------
BARK = [E.hexc("#141117"), E.hexc("#1d1820"), E.hexc("#272029"), E.hexc("#332a35"), E.hexc("#403543")]
BARK_MOON = E.hexc("#4a5a6c")
LEAF = [E.hexc("#15201d"), E.hexc("#1c2c27"), E.hexc("#253a32"), E.hexc("#2f4a3f"), E.hexc("#3d5f55")]
LEAF_MOON = E.hexc("#4c6f73")


class Stroke:
    """Accumulates thick strokes into a mask plus a per-pixel thickness map."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.mask = np.zeros((h, w), bool)
        self.rad = np.zeros((h, w))

    def dot(self, x, y, r):
        if r < 0.75:
            xi, yi = int(math.floor(x)), int(math.floor(y))
            if 0 <= xi < self.w and 0 <= yi < self.h:
                self.mask[yi, xi] = True
                self.rad[yi, xi] = max(self.rad[yi, xi], r)
            return
        x0, x1 = int(math.floor(x - r)), int(math.ceil(x + r))
        y0, y1 = int(math.floor(y - r)), int(math.ceil(y + r))
        for yy in range(max(0, y0), min(self.h, y1 + 1)):
            for xx in range(max(0, x0), min(self.w, x1 + 1)):
                if (xx + 0.5 - x) ** 2 + (yy + 0.5 - y) ** 2 <= r * r:
                    self.mask[yy, xx] = True
                    self.rad[yy, xx] = max(self.rad[yy, xx], r)


def limb(st: Stroke, rnd, x, y, ang, length, width, depth, gnarl=0.22, bend=0.0, fork=(2, 3)):
    """Grow one limb, then fork into 2-3 thinner limbs (recursive)."""
    n = max(2, int(round(length)))
    for i in range(n):
        x += math.cos(ang)
        y -= math.sin(ang)
        ang += rnd.gauss(0, gnarl) * 0.6 + bend
        st.dot(x, y, max(0.5, width * (1 - 0.45 * i / n)) / 2)
        if depth > 0 and 2 < i < n - 2 and rnd.random() < 0.08:       # small side twig
            limb(st, rnd, x, y, ang + rnd.choice((-1, 1)) * rnd.uniform(0.7, 1.2), rnd.uniform(2, 4), 1.0, 0, gnarl)
    if depth <= 0:
        return
    k = rnd.randint(*fork)
    spread = [(-0.55, 0.5), (-0.7, 0.05, 0.65)][k - 2]
    for a_off in spread:
        limb(st, rnd, x, y, ang + a_off + rnd.uniform(-0.15, 0.15), length * rnd.uniform(0.55, 0.72),
             max(1.0, width * 0.62), depth - 1, gnarl, -bend * 0.5, fork=(2, 2))


def shade_organic(st: Stroke, ramp, rim, seed: int = 0) -> np.ndarray:
    """Side-lit shading for strokes: moonlit left rim on thick parts, darker right edge,
    vertical bark streaks, thin twigs in a mid tone."""
    mask = st.mask
    h, w = mask.shape
    img = E.new(w, h)
    left_empty = mask & ~np.roll(mask, 1, axis=1)
    right_empty = mask & ~np.roll(mask, -1, axis=1)
    thick = st.rad >= 1.1
    idx = np.full((h, w), 2)
    idx[right_empty & thick] = 1
    idx[~thick] = 3
    rnd = E.rng(seed)
    ph = np.array([rnd.randrange(4) for _ in range(w)])
    streak = thick & ~left_empty & ~right_empty & (((np.arange(w)[None, :] * 3 + ph[None, :] + np.arange(h)[:, None] // 4) % 4) == 0)
    idx[streak] = 1
    img[mask] = np.array(ramp, np.uint8)[idx[mask]]
    img[left_empty & thick] = rim
    img[:, 0] = img[:, -1] = 0
    img[0, :] = img[-1, :] = 0
    return E.outline(img)


def dead_tree(variant: str) -> np.ndarray:
    W_, H_ = 32, 48
    rnd = E.rng({"a": 511, "b": 522, "c": 533}[variant])
    st = Stroke(W_, H_)
    bx, by = 16.0, 43.5
    if variant == "a":     # tall, wide crown of twisted limbs
        limb(st, rnd, bx, by, math.pi / 2 + 0.05, 17, 6.0, 0, gnarl=0.12)
        tx, ty = bx + 0.6, by - 17
        for a_off, ln, wd in ((0.85, 10, 3.4), (-0.8, 11, 3.4), (0.1, 9, 2.6)):
            limb(st, rnd, tx, ty, math.pi / 2 + a_off, ln, wd, 2, gnarl=0.25)
    elif variant == "b":   # leaning, gnarled, broken top
        limb(st, rnd, bx - 1, by, math.pi / 2 - 0.25, 15, 6.4, 0, gnarl=0.1, bend=0.012)
        tx, ty = bx + 2.6, by - 14.5
        limb(st, rnd, tx, ty, math.pi / 2 + 1.0, 10, 3.2, 2, gnarl=0.28)
        limb(st, rnd, tx + 0.5, ty + 2, math.pi / 2 - 0.9, 9, 3.0, 2, gnarl=0.28)
        limb(st, rnd, tx, ty, math.pi / 2 - 0.1, 5, 3.6, 0, gnarl=0.1)
    else:                  # forked twin trunk
        limb(st, rnd, bx, by, math.pi / 2, 8, 6.4, 0, gnarl=0.05)
        limb(st, rnd, bx - 1, by - 8, math.pi / 2 + 0.38, 16, 3.8, 2, gnarl=0.2, bend=-0.01)
        limb(st, rnd, bx + 1, by - 8, math.pi / 2 - 0.34, 15, 3.6, 2, gnarl=0.2, bend=0.01)
    for a_r, ln, wd in ((math.pi + 0.28, 5, 3.6), (-0.3, 5, 3.4), (math.pi + 0.95, 3, 2.4), (-0.95, 3, 2.2)):
        limb(st, rnd, bx, by - 1.2, a_r, ln, wd, 0, gnarl=0.05)
    img = shade_organic(st, BARK, BARK_MOON, seed=ord(variant))
    if variant == "b":           # dark knot-hole
        img[33:35, 15:17] = BARK[0]
        img[33, 15] = OUT
    if variant == "c":           # hanging moss strands
        ys, xs = np.nonzero(st.mask[:28, :] & (st.rad[:28, :] >= 1.0))
        rr = E.rng(9)
        for q in rr.sample(range(len(xs)), min(8, len(xs))):
            x0, y0 = xs[q], ys[q]
            ln = rr.randint(3, 6)
            for dy in range(1, ln):
                if y0 + dy < H_ and img[y0 + dy, x0, 3] == 0:
                    img[y0 + dy, x0] = E.hexc("#44524c") if dy < ln - 1 else E.hexc("#2f3a36")
    out = E.new(W_, H_)
    E.paste(out, contact_shadow(W_, H_, bx + 1.5, by + 0.2, 7.5, 2.2), 0, 0)
    E.paste(out, img, 0, 0)
    return out


def bush(variant: str) -> np.ndarray:
    W_, H_ = (18, 14) if variant == "a" else (14, 12)
    rnd = E.rng({"a": 61, "b": 62}[variant])
    img = E.new(W_, H_)
    clumps = []
    n = 7 if variant == "a" else 5
    for i in range(n):
        cx = W_ / 2 + rnd.uniform(-W_ * 0.27, W_ * 0.27)
        cy = H_ * 0.6 + rnd.uniform(-H_ * 0.22, H_ * 0.12)
        clumps.append((cy, cx, rnd.uniform(2.3, 3.4)))
    clumps.sort()
    yy, xx = np.mgrid[0:H_, 0:W_]
    bay = bayer(H_, W_)
    for cy, cx, r in clumps:          # back to front
        d = np.hypot(xx + 0.5 - cx, (yy + 0.5 - cy) * 1.15)
        m = d <= r
        lit = ((xx + 0.5 - cx) * -0.55 + (yy + 0.5 - cy) * -0.85) / r
        idx = np.clip(np.floor(1.5 + lit * 1.5 + (bay - 0.5) * 0.9), 0, 4).astype(int)
        img[m] = np.array(LEAF, np.uint8)[idx[m]]
        img[m & (d > r - 0.9) & (lit < -0.2)] = LEAF[0]
    # thorny twigs
    for _ in range(3):
        x0, y0 = rnd.uniform(3, W_ - 3), rnd.uniform(3, H_ * 0.45)
        ang = rnd.uniform(0.6, 2.5)
        for t in range(1, 4):
            xi, yi = int(x0 + math.cos(ang) * t), int(y0 - math.sin(ang) * t)
            if 1 <= xi < W_ - 1 and 1 <= yi < H_ - 1 and img[yi, xi, 3] == 0:
                img[yi, xi] = BARK[3]
    img[:, 0] = img[:, -1] = 0
    img[0, :] = img[-1, :] = 0
    a = img[:, :, 3] > 0
    toprim = a & ~np.roll(a, 1, axis=0) & (np.arange(W_)[None, :] < W_ * 0.7)
    img[toprim & (bayer(H_, W_) < 0.7)] = LEAF_MOON
    img = E.outline(img)
    out = E.new(W_, H_)
    E.paste(out, contact_shadow(W_, H_, W_ / 2 + 1, H_ * 0.9 - 0.5, W_ * 0.42, 1.8), 0, 0)
    E.paste(out, img, 0, 0)
    return out


def ascii_prop(rows: Sequence[str], legend: Dict[str, Tuple[int, int, int, int]], size: Tuple[int, int],
               shadow: Optional[Tuple[float, float]] = None, outline=True, outline_color=OUT) -> np.ndarray:
    """ASCII art placed so its bottom-centre base sits on the prop pivot."""
    art = E.ascii_art(rows, legend)
    if outline:
        art = E.recolor(outline_img(art), {OUT: outline_color}) if outline_color != OUT else outline_img(art)
    Wf, Hf = size
    out = E.new(Wf, Hf)
    ah, aw = art.shape[:2]
    ox = (Wf - aw) // 2
    base_row = Hf * (1 - PROP_PIVOT[1])
    oy = int(round(base_row - ah + 1 + (1 if outline else 0)))
    if shadow is not None:
        E.paste(out, contact_shadow(Wf, Hf, Wf / 2 + 1, base_row, shadow[0], shadow[1]), 0, 0)
    E.paste(out, art, ox, oy)
    return out


MUSH_LEG = {"c": E.hexc("#6c8aa0"), "C": E.hexc("#9cc0d4"), "h": E.hexc("#d8f0fa"), "k": E.hexc("#44607a"),
            "s": E.hexc("#8a8a90"), "S": E.hexc("#b4b2b6"), "d": E.hexc("#5a5860")}


def mushroom(variant: str) -> np.ndarray:
    if variant == "a":
        rows = [
            "..kCCk....",
            ".kChCCk...",
            "kccccck...",
            "..dSs.kCk.",
            "..dSs.cCc.",
            "..dSs..Sd.",
        ]
    else:
        rows = [
            ".kCk...",
            "kChCk..",
            "kccck..",
            ".dSkCk.",
            ".dSccc.",
            ".dS.S..",
        ]
    return ascii_prop(rows, MUSH_LEG, (12, 10) if variant == "a" else (10, 9), shadow=(4.5, 1.2))


def grass_tuft(variant: str, biome: str = "gravewood") -> np.ndarray:
    if biome == "gravewood":
        leg = {"a": PAL["gw_grass1"], "b": PAL["gw_grass2"], "c": PAL["gw_grass3"], "m": GW_MOONGRASS}
    else:
        leg = {"a": E.hexc("#2c2934"), "b": E.hexc("#3b3744"), "c": E.hexc("#4d4757"), "m": E.hexc("#5f5a6a")}
    designs = {
        "a": ["m...c..", ".c..b.m", ".b.cb.b", "ab.bba.", ".abbaa."],
        "b": ["..m.....", "c..c..m.", "b.cb.cb.", "b.bb.bb.", ".abbab..", "..aaa..."],
        "c": [".m.c.", ".b.b.", "cb.bc", "abbba"],
    }
    rows = designs[variant]
    out_c = PAL["gw_grass0"] if biome == "gravewood" else PAL["mf_stone0"]
    art = E.ascii_art(rows, leg)
    art = outline_img(art)
    art = E.recolor(art, {OUT: out_c})
    Wf, Hf = (art.shape[1], art.shape[0] + 1)
    out = E.new(Wf, Hf)
    E.paste(out, art, 0, Hf - art.shape[0] - int(round(Hf * PROP_PIVOT[1])) + 1)
    return out


LANTERN_LEG = {"w": GW_WOOD[2], "W": GW_WOOD[4], "v": GW_WOOD[1], "i": PAL["iron1"], "I": PAL["iron3"],
               "f": E.hexc("#6fa6d6"), "F": E.hexc("#bfe6ff"), "h": E.hexc("#f0fbff"), "g": E.hexc("#3d5f80")}


def lantern_post() -> np.ndarray:
    rows = [
        "...IiiiiiiI",
        ".......Wi..",
        "......iIi..",
        ".....iIiIi.",
        ".....IfFfi.",
        ".....ihFfi.",
        ".....ifFfi.",
        ".....IiiIi.",
        "......Wi...",
        "......Wv...",
        "......Wv...",
        "......Wv...",
        "......Wv...",
        "......Wv...",
        "......Wv...",
        "......Wv...",
        "......Wv...",
        "......Wv...",
        "......Wv...",
        "......Wv...",
        ".....WWvv..",
        "....vWwwvv.",
    ]
    rows[0] = "......IiiI."
    rows[1] = "......Wi..."
    art = outline_img(E.ascii_art([r.ljust(11, ".") for r in rows], LANTERN_LEG))
    # pale-blue glow around the lantern glass (soft alpha, it is a light)
    glass = E.new(*E.size(art))
    for (yy, xx) in zip(*np.nonzero(np.all(art[:, :, :3] == np.array(LANTERN_LEG["F"][:3]), axis=2))):
        glass[yy, xx] = LANTERN_LEG["F"]
    halo = E.glow(glass, E.hexc("#7fb8e8"), radius=4, strength=0.32)
    halo[glass[:, :, 3] > 0] = 0
    Wf, Hf = 16, 28
    out = E.new(Wf, Hf)
    ox = Wf // 2 - 7
    oy = int(round(Hf * 0.9)) - art.shape[0] + 2
    E.paste(out, contact_shadow(Wf, Hf, Wf / 2 + 1, Hf * 0.9, 3.5, 1.2), 0, 0)
    E.paste(out, halo, ox, oy)
    E.paste(out, art, ox, oy)
    return out


# ---- moonfall props -----------------------------------------------------------------------
CRYSTAL = [E.hexc("#1f1030"), E.hexc("#35195a"), E.hexc("#4f2a82"), E.hexc("#7148aa"), E.hexc("#9d7fd0"), E.hexc("#d4c4f2")]
VFLAME = [E.hexc("#3d1f6e"), E.hexc("#5f35a8"), E.hexc("#8a62cc"), E.hexc("#b9a0e6"), E.hexc("#e0d4f5")]


def _weather(v: Vox, rnd, p=0.1):
    st = v.m > 0
    rr = np.array([[[rnd.random() for _ in range(v.w)] for _ in range(v.d)] for _ in range(v.h)])
    v.t[st & (rr < p)] -= 1


def _cat_figure(broken: bool) -> np.ndarray:
    """2D sitting-cat sculpture (front 3/4 view), shaded as carved stone, 16x22."""
    Wc, Hc = 16, 22
    img = E.new(Wc, Hc)
    yy, xx = np.mgrid[0:Hc, 0:Wc]
    X, Y = xx + 0.5, yy + 0.5
    head = ((X - 8) / 5.3) ** 2 + ((Y - 7.2) / 4.4) ** 2 <= 1
    ears = np.zeros_like(head)
    for side in (-1, 1):
        ex = 8 + side * 3.3
        for (yy0, half) in ((1.5, 0.5), (2.5, 1.0), (3.5, 1.5), (4.5, 2.0)):
            ears |= (np.abs(Y - yy0) < 0.5) & (np.abs(X - (ex + side * 0.4 * (4.5 - yy0) / 3)) < half)
    body = ((X - 8) / 5.8) ** 2 + ((Y - 16.5) / 6.4) ** 2 <= 1
    body &= Y < 21.0
    neck = (np.abs(X - 8) < 3.6) & (Y > 9) & (Y < 12)
    tail = np.zeros_like(head)
    for t in np.linspace(0, 1, 30):
        a = -0.3 + t * 2.2
        tx, ty = 8 + 6.4 * math.cos(a), 19.2 + 1.6 * math.sin(a)
        tail |= (X - tx) ** 2 + (Y - ty) ** 2 <= 1.05
    tail &= Y < 21.0
    shape_body = body | neck | tail
    shape_head = head | ears
    if broken:
        shape_head[:] = False
        jag = 10.5 + 1.2 * np.sin(X * 2.1) + np.where(X > 9, 1.5, 0)
        shape_body &= Y > jag
    ramp = MF_STONE[1:]
    E.shade_mask(img, shape_body, ramp, light=(-0.7, -0.6), dither=False)
    if shape_head.any():
        E.shade_mask(img, shape_head, ramp, light=(-0.7, -0.6), dither=False)
        img[ears & ~head & (X > 8)] = MF_STONE[2]
        img[(ears & ~head) & (X < 8) & (np.abs(X - 4.7) < 0.6)] = MF_STONE[4]
        # carved almond eyes, nose, whisker pads
        img[7, 4:6] = MF_STONE[0]          # almond eye slits
        img[7, 10:12] = MF_STONE[0]
        img[6, 5] = img[6, 10] = MF_STONE[1]
        img[9, 7:9] = MF_STONE[1]          # nose
        # chin shadow separates head from chest
        img[11, 5:11] = MF_STONE[1]
    # chest ruff + separation of the front legs + paw toes
    if not broken:
        img[13, 7:9] = MF_STONE[4]
        img[14, 6:10] = MF_STONE[3]
    img[16:20, 8] = MF_STONE[1]
    img[20, 5] = img[20, 7] = img[20, 9] = img[20, 11] = MF_STONE[1]
    # tail edge highlight
    tm = tail & ~body
    img[tm & (np.roll(~tail, 1, axis=0))] = MF_STONE[3]
    img[:, 0] = img[:, -1] = 0
    img[0, :] = 0
    return E.outline(img)


def cat_statue(variant: str) -> np.ndarray:
    W_, D_, H_ = 22, 11, 8
    v = Vox(W_, D_, H_)
    rnd = E.rng({"a": 71, "b": 72}[variant])
    cx, cy = 11.0, 5.5
    v.fill(v.box(cx - 8, cx + 8, cy - 4.5, cy + 4.5, 0, 1.5), 1)
    v.fill(v.box(cx - 7, cx + 7, cy - 3.8, cy + 3.8, 0, 6.5), 1)
    v.fill(v.box(cx - 7.8, cx + 7.8, cy - 4.4, cy + 4.4, 6.0, 8), 1)
    v.t[v.box(cx - 7, cx + 7, cy - 3.8, cy + 3.8, 2.5, 3.5)] = -1          # carved band
    # a paw relief on the plinth front
    for (px_, pz_) in ((-1, 5), (1, 5), (-2, 4), (2, 4), (-1, 3), (0, 3), (1, 3), (0, 2)):
        v.t[(np.abs(v.X - (cx + px_)) < 0.5) & (np.abs(v.Z - (pz_ + 0.5)) < 0.5) & (v.Y > cy + 3)] = 1
    _weather(v, rnd, 0.08)
    plinth = outline_img(v.render([MF_STONE]))
    fig = _cat_figure(variant == "b")
    Wf, Hf = (24, 40) if variant == "a" else (28, 40)
    canvas = E.new(Wf + 4, Hf + 4)
    # plinth top face spans rows 1..10 of the render; the cat sits on its back half
    px0 = (Wf - plinth.shape[1]) // 2 + 2
    py0 = Hf + 4 - plinth.shape[0] - int(round(Hf * 0.1)) + 1
    E.paste(canvas, plinth, px0, py0)
    E.paste(canvas, fig, px0 + int(cx + 1 - fig.shape[1] / 2), py0 + 8 - fig.shape[0] + 3)
    if variant == "b":     # the fallen head lies beside the plinth
        hv = _cat_figure(False)[0:13, :]
        head = hv[:, ::-1].copy()                      # mirrored so it faces the plinth
        small = E.new(head.shape[1], head.shape[0])
        E.paste(small, head, 0, 0)
        E.paste(canvas, small, px0 + plinth.shape[1] - 7, py0 + plinth.shape[0] - small.shape[0] + 1)
    out = E.new(Wf, Hf)
    E.paste(out, contact_shadow(Wf, Hf, Wf / 2 + 1.5, Hf * 0.9, 9.5, 2.4), 0, 0)
    E.paste(out, canvas, -2, -2)
    return out


def pillar(variant: str) -> np.ndarray:
    rnd = E.rng({"a": 81, "b": 82, "c": 83}[variant])
    if variant == "c":           # fallen column drum + stub
        W_, D_, H_ = 24, 11, 9
        v = Vox(W_, D_, H_)
        cyl = ((v.Y - 5.5) ** 2 + (v.Z - 4.0) ** 2 <= 3.9 ** 2) & (v.X > 3) & (v.X < 20)
        v.fill(cyl, 1)
        ang = np.arctan2(v.Z - 4.0, v.Y - 5.5)
        v.t[cyl & (np.floor(ang * 3.2) % 2 == 0)] = -1                  # fluting
        v.t[cyl & (v.X > 19)] = 1                                        # cut face
        v.fill(v.box(19.5, 23.5, 2.5, 8.5, 0, 2.2), 1)                   # broken base block
        _weather(v, rnd, 0.08)
        img = outline_img(v.render([MF_STONE]))
        sh = contact_shadow(img.shape[1], img.shape[0], 13, H_ + 6.5 + 1, 10, 2.2)
        return place_prop(img, 12.5, H_ + 5.5 + 1 + 1, (26, 20), sh)
    W_, D_ = 14, 11
    H_ = 31 if variant == "a" else 20
    v = Vox(W_, D_, H_)
    cx, cy = 7.0, 5.5
    v.fill(v.box(cx - 5.5, cx + 5.5, cy - 5, cy + 5, 0, 2.5), 1)            # square base
    top = H_ - 2 if variant == "a" else H_
    shaft = v.cyl(cx, cy, 3.9, 2, top)
    if variant == "b":           # jagged break
        jag = 15 + 2.5 * np.sin(v.X * 1.7) + 1.5 * np.cos(v.Y * 2.3)
        shaft &= v.Z < jag
    v.fill(shaft, 1)
    ang = np.arctan2(v.Y - cy, v.X - cx)
    v.t[shaft & (np.floor(ang * 3.2) % 2 == 0)] = -1                      # fluting
    if variant == "a":
        v.fill(v.box(cx - 5, cx + 5, cy - 4.6, cy + 4.6, H_ - 2.2, H_), 1)   # capital
        v.fill(v.cyl(cx, cy, 4.6, H_ - 3.2, H_ - 2.0), 1)
    _weather(v, rnd, 0.08)
    img = outline_img(v.render([MF_STONE]))
    if variant == "b":           # a fallen chunk at the foot
        ch = Vox(7, 6, 5)
        ch.fill(ch.ellipsoid(3.5, 3, 1.8, 3.0, 2.2, 2.4), 1)
        chi = outline_img(ch.render([MF_STONE]))
        big = E.new(img.shape[1] + 4, img.shape[0])
        E.paste(big, img, 0, 0)
        E.paste(big, chi, img.shape[1] - 6, img.shape[0] - chi.shape[0])
        img = big
    sh = contact_shadow(img.shape[1], img.shape[0], cx + 2, H_ + cy + 1.6, 6.5, 2.2)
    return place_prop(img, cx + 1, H_ + cy + 1, (16 if variant == "a" else 20, 42 if variant == "a" else 32), sh)


def rubble(variant: str) -> np.ndarray:
    rnd = E.rng({"a": 91, "b": 92, "c": 93}[variant])
    W_, D_, H_ = {"a": (16, 10, 6), "b": (12, 8, 5), "c": (20, 12, 7)}[variant]
    v = Vox(W_, D_, H_)
    n = {"a": 7, "b": 5, "c": 10}[variant]
    for i in range(n):
        bw, bd = rnd.choice((2, 3, 3, 4)), rnd.choice((2, 2, 3))
        bh = rnd.choice((1, 2, 2, 3)) if i < n // 2 else rnd.choice((1, 2))
        x0 = rnd.uniform(1.5, W_ - bw - 1.5)
        y0 = rnd.uniform(1.5, D_ - bd - 1.5)
        z0 = 0
        # stack on whatever is below
        col = v.m[:, int(y0 + bd / 2), int(x0 + bw / 2)]
        nz = np.nonzero(col)[0]
        if len(nz) and rnd.random() < 0.6:
            z0 = nz.max() + 1
        if z0 + bh > H_:
            continue
        blk = v.box(x0, x0 + bw, y0, y0 + bd, z0, z0 + bh)
        v.fill(blk, 1, rnd.choice((0, 0, -1, 1)))
    _weather(v, rnd, 0.06)
    img = outline_img(v.render([MF_STONE]))
    sh = contact_shadow(img.shape[1], img.shape[0], W_ / 2 + 2, H_ + D_ / 2 + 2, W_ / 2, D_ / 3)
    return place_prop(img, W_ / 2 + 1, H_ + D_ / 2 + 2, (W_ + 2, H_ + D_ + 2), sh)


def crystal(variant: str) -> np.ndarray:
    """Cluster of violet crystal shards (flat-shaded facets) with a faint glow."""
    if variant == "a":
        rows = [
            "....o.......",
            "...o5o......",
            "...o54o.....",
            "..o543o..o..",
            "..o543o.o5o.",
            ".o5433o.o43o",
            ".o5432oo543o",
            "o.o432oo432o",
            "o5o432o.o32o",
            "o54o32o.o32o",
            "o43o21oo321o",
            "o32o21o.o21o",
            ".oooooooooo.",
        ]
    else:
        rows = [
            "...o.....",
            "..o5o....",
            "..o54o...",
            ".o543o.o.",
            ".o543oo5o",
            "o.o32oo4o",
            "o5o32oo3o",
            "o43o2oo2o",
            ".ooooooo.",
        ]
    leg = {"o": OUT, "1": CRYSTAL[1], "2": CRYSTAL[2], "3": CRYSTAL[3], "4": CRYSTAL[4], "5": CRYSTAL[5]}
    art = E.ascii_art(rows, leg)
    core = E.new(art.shape[1] + 6, art.shape[0] + 6)
    E.paste(core, art, 3, 3)
    glowsrc = core.copy()
    glowsrc[np.all(core[:, :, :3] == np.array(OUT[:3]), axis=2)] = 0
    halo = E.glow(glowsrc, CRYSTAL[3], radius=3, strength=0.22)
    halo[core[:, :, 3] > 0] = 0
    Wf, Hf = core.shape[1], core.shape[0]
    out = E.new(Wf, Hf)
    base_row = Hf * 0.9
    oy = int(round(base_row - (3 + art.shape[0]) + 1))
    E.paste(out, contact_shadow(Wf, Hf, Wf / 2 + 1, base_row, art.shape[1] / 2, 1.3), 0, 0)
    E.paste(out, halo, 0, oy)
    E.paste(out, core, 0, oy)
    return out


def brazier() -> np.ndarray:
    W_, D_, H_ = 14, 10, 11
    v = Vox(W_, D_, H_)
    cx, cy = 7.0, 5.0
    for a in (0.5, 2.6, 4.7):                                   # three iron legs
        lx, ly = cx + 3.3 * math.cos(a), cy + 2.8 * math.sin(a)
        v.fill(v.cyl(lx, ly, 0.8, 0, 6.5), 2)
    bowl = v.cyl(cx, cy, 5.0, 6, 10) & ~v.cyl(cx, cy, 3.6, 7.2, 11)
    v.fill(bowl, 1)
    v.t[bowl & (v.Z > 9)] = 1
    coals = v.cyl(cx, cy, 3.7, 6.5, 8.2)
    v.fill(coals, 3)
    img = outline_img(v.render([MF_STONE, MF_IRON, [VFLAME[0], VFLAME[1], VFLAME[2]]], emissive=(3,)))
    # violet flame (2D) above the bowl
    flame_rows = [
        "...w...",
        "..wvw..",
        "..vpv.w",
        ".wvpv.v",
        "wvpPpvv",
        "vpPhPpv",
        ".vpPpv.",
    ]
    fl = E.ascii_art(flame_rows, {"w": VFLAME[1], "v": VFLAME[2], "p": VFLAME[3], "P": VFLAME[4], "h": (255, 255, 255, 255)})
    canvas = E.new(img.shape[1] + 6, img.shape[0] + 10)
    E.paste(canvas, img, 3, 10)
    fx0 = 3 + int(cx + 1 - 3.5)
    fy0 = 10 + int(H_ - 10 + cy + 1 - 5)
    flame_layer = E.new(*E.size(canvas))
    E.paste(flame_layer, fl, fx0, fy0)
    halo = E.glow(flame_layer, VFLAME[1], radius=3, strength=0.22)
    halo[flame_layer[:, :, 3] > 0] = 0
    halo[canvas[:, :, 3] > 0] = 0
    out = E.new(*E.size(canvas))
    E.paste(out, halo, 0, 0)
    E.paste(out, canvas, 0, 0)
    E.paste(out, flame_layer, 0, 0)
    ref_y = 10 + H_ + cy + 1
    sh = contact_shadow(*E.size(out), 3 + cx + 2, ref_y + 0.5, 5.5, 1.8)
    return place_prop(out, 3 + cx + 1, ref_y, (18, 28), sh)


def puddle() -> np.ndarray:
    W_, H_ = 26, 14
    rnd = E.rng(97)
    img = E.new(W_, H_)
    yy, xx = np.mgrid[0:H_, 0:W_]
    cx, cy = W_ / 2, H_ * 0.52
    ang = np.arctan2(yy + 0.5 - cy, (xx + 0.5 - cx) * 0.5)
    rad = 1.0 + 0.12 * np.sin(ang * 3 + 1.0) + 0.08 * np.sin(ang * 5 + 2.0)
    d = np.hypot((xx + 0.5 - cx) / 11.5, (yy + 0.5 - cy) / 5.2) / rad
    water = d <= 1.0
    rim = water & (d > 0.84)
    img[water] = MF["mf_sky"]
    img[water & (d < 0.62)] = E.hexc("#231a3b")
    img[rim] = MF["mf_stone0"]
    # reflections: horizontal streaks of the lit sky + two storm glints
    for (x0, y0, ln, c) in ((7, 5, 5, MF["mf_stone3"]), (13, 7, 4, MF["mf_stone3"]), (10, 8, 3, E.hexc("#4a4270")),
                            (16, 5, 2, E.hexc("#4a4270"))):
        for x in range(x0, x0 + ln):
            if water[y0, x] and not rim[y0, x]:
                img[y0, x] = c
    img[5, 8] = MF["mf_storm"]
    img[7, 14] = E.hexc("#6c7fd0")
    out = E.new(W_, H_ + 2)
    E.paste(out, img, 0, 0)
    return out


def banner_torn() -> np.ndarray:
    rows = [
        "IIIIIIIIIII..",
        "Ibbbbbbbbb...",
        "IbBBbbbbbd...",
        "IbBbbsbsbd...",
        "IbBbsbbbsd...",
        "IbBbbsssbd...",
        "IbBbbsssbd...",
        "IbBbbbbbbd...",
        "Ibbb.bbbbd...",
        "IbBb.bbbbd...",
        "IbBbbbb.bd...",
        "IbBbbbbbbd...",
        "Ibbbbbbbd....",
        "IbBbb.bbd....",
        "Ib.bb..bd....",
        "Ib..b...d....",
        "I...b........",
        "p............",
        "p............",
        "p............",
        "p............",
        "p............",
        "p............",
        "p............",
        "p............",
        "pP...........",
        "PPp..........",
    ]
    leg = {"I": PAL["iron2"], "p": PAL["wood1"], "P": PAL["wood2"], "b": E.hexc("#3d2a57"), "B": E.hexc("#4c3570"),
           "d": E.hexc("#2c1f40"), "s": E.hexc("#8c8aa0")}
    art = outline_img(E.ascii_art([r.ljust(13, ".") for r in rows], leg))
    Wf, Hf = 28, 32
    out = E.new(Wf, Hf)
    pole_x = 1                                         # pole column inside the outlined art
    ox = Wf // 2 - pole_x - 1                          # pole occupies the pixel just right of the pivot
    E.paste(out, contact_shadow(Wf, Hf, Wf / 2 + 1.5, Hf * 0.9, 3.5, 1.2), 0, 0)
    E.paste(out, art, ox, int(round(Hf * 0.9)) - art.shape[0] + 2)
    return out


# ======================================================================================
# Build
# ======================================================================================
def fit_prop(img: np.ndarray, max_drop: float = 2.5) -> np.ndarray:
    """Trim a prop canvas to its content, keeping the pivot at (0.5, 0.1). The horizontal
    pivot stays exactly on the same pixel boundary; the base point may slide down by up to
    `max_drop` px onto the prop's front edge / contact shadow so the canvas stays compact."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = E.trim_box(img)
    px, py = w * PROP_PIVOT[0], h * (1 - PROP_PIVOT[1])
    half = int(math.ceil(max(px - x0, x1 - px)))
    Wn = max(2, 2 * half)
    ox = int(round(Wn * PROP_PIVOT[0] - px))
    for Hn in range(max(2, y1 - y0), 4 * h):
        # the pivot may slide down (onto the prop's front/shadow edge) by up to max_drop px
        lo = max(-y0, int(math.ceil(Hn * (1 - PROP_PIVOT[1]) - py - max_drop)))
        hi = min(Hn - y1, int(math.floor(Hn * (1 - PROP_PIVOT[1]) - py)))
        if lo <= hi:
            oy = hi
            break
    out = E.new(Wn, Hn)
    E.paste(out, img, ox, oy)
    return out


def props(biome: str) -> Dict[str, np.ndarray]:
    """All props of a biome, keyed by prop name (canvases trimmed around the base pivot)."""
    return {k: fit_prop(v) for k, v in _props_raw(biome).items()}


def _props_raw(biome: str) -> Dict[str, np.ndarray]:
    if biome == "gravewood":
        out = {}
        for v in "abc":
            out[f"tree_dead_{v}"] = dead_tree(v)
        for v in "abc":
            out[f"wall_broken_{v}"] = wall_broken(v)
        for v in "abcd":
            out[f"grave_{v}"] = grave(v)
        out["bush_a"], out["bush_b"] = bush("a"), bush("b")
        out["mushroom_a"], out["mushroom_b"] = mushroom("a"), mushroom("b")
        out["lantern_post"] = lantern_post()
        out["stump"] = stump()
        out["rock_a"], out["rock_b"] = rock("a"), rock("b")
        for v in "abc":
            out[f"grass_{v}"] = grass_tuft(v, "gravewood")
        return out
    out = {"cat_statue_a": cat_statue("a"), "cat_statue_b": cat_statue("b")}
    for v in "abc":
        out[f"pillar_{v}"] = pillar(v)
    for v in "abc":
        out[f"rubble_{v}"] = rubble(v)
    out["crystal_a"], out["crystal_b"] = crystal("a"), crystal("b")
    out["brazier"] = brazier()
    out["puddle"] = puddle()
    out["banner_torn"] = banner_torn()
    out["grass_a"], out["grass_b"] = grass_tuft("a", "moonfall"), grass_tuft("b", "moonfall")
    return out


def build(reg: "E.Registry") -> None:
    for biome, ground, vcol in (("gravewood", gravewood_ground(), PAL["gw_grass0"]),
                                ("moonfall", moonfall_ground(), E.hexc("#120d1c"))):
        at = f"env_{biome}"
        reg.sprite(at, f"env/{biome}/ground", ground, pivot=(0.5, 0.5))
        for i in range(4):
            reg.sprite(at, f"env/{biome}/path/{i}", path_stamp(biome, i), pivot=(0.5, 0.5))
        for name, img in props(biome).items():
            reg.sprite(at, f"env/{biome}/prop/{name}", img, pivot=PROP_PIVOT)
        reg.sprite(at, f"env/{biome}/vignette", vignette(vcol), pivot=(0.5, 0.5))


def preview():
    os.makedirs(ITER_DIR, exist_ok=True)
    pr = [wall_broken(v) for v in "abc"] + [grave(v) for v in "abcd"] + [rock("a"), rock("b"), stump()]
    E.preview_images(pr, os.path.join(ITER_DIR, "props_gw_stone.png"), scale=6)
    pr = [dead_tree(v) for v in "abc"] + [bush("a"), bush("b"), mushroom("a"), mushroom("b"),
                                          grass_tuft("a"), grass_tuft("b"), grass_tuft("c"), lantern_post()]
    E.preview_images(pr, os.path.join(ITER_DIR, "props_gw_org.png"), scale=6)
    pr = [cat_statue("a"), cat_statue("b"), pillar("a"), pillar("b"), pillar("c"), rubble("a"), rubble("b"),
          rubble("c"), crystal("a"), crystal("b"), brazier(), puddle(), banner_torn(),
          grass_tuft("a", "moonfall"), grass_tuft("b", "moonfall")]
    E.preview_images(pr, os.path.join(ITER_DIR, "props_mf.png"), scale=5)
    for biome, g in (("gravewood", gravewood_ground()), ("moonfall", moonfall_ground())):
        t3 = np.tile(g, (3, 3, 1))
        E.preview_images([t3], os.path.join(ITER_DIR, f"ground3x3_{biome}.png"), scale=2)
        E.preview_images([path_stamp(biome, i) for i in range(4)], os.path.join(ITER_DIR, f"paths_{biome}.png"), scale=8)


if __name__ == "__main__":
    import time
    t = time.time()
    preview()
    print(f"done in {time.time() - t:.1f}s")
