"""
gen_citadel.py - the Nine-Lives Citadel (atlas "citadel") for EVIL CATS.

The fortress is modelled as a small voxel scene (1 voxel = 1 art pixel) and rendered with
the game's fixed oblique top-down projection (screen_y = ground_y - height). Because every
variant (base, reinforced, ruined) is rendered from the same scene description:
  * occlusion is always correct (walls hide the courtyard, the spire hides what is behind),
  * all variants share exactly the same size, pivot and anchors,
  * the reinforcement overlays are simply "pixels that changed" versus the base render,
  * cracks are traced over the rendered stone surfaces of the base.
Shading is deliberately stepped (palette ramps, 1 px outlines, light from the top-left).

Sprites written (atlas "citadel"):
  citadel/base            96x120, pivot = centre of the 70 px footprint circle, + anchors
  citadel/stormheart/<i>  16x16 anim (4f, 6 fps, loop), pivot = crystal centre
  citadel/cracks1, citadel/cracks2, citadel/reinforce1..3, citadel/ruin   (same as base)
  citadel/shadow          80x24 soft ground shadow; its pivot is the citadel pivot, so it can be
                          drawn at the citadel position and lands under the south base
  citadel/slot_glow       20x10 highlight under a station turret (pivot centre)

Run directly for iteration previews:  python3 Tools/art/gen_citadel.py  -> /tmp/claude-0/world_iter/
"""
from __future__ import annotations

import math
import os
import sys
from typing import Dict, List, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import eclib as E  # noqa: E402
from eclib import PAL  # noqa: E402

ATLAS = "citadel"
ITER_DIR = "/tmp/claude-0/world_iter"

# --------------------------------------------------------------------------------------
# Frame + projection
# --------------------------------------------------------------------------------------
W, H = 96, 120
PX, PY = 48, 76                      # pivot (pixel-boundary coords, y down) = footprint centre
PIVOT = (PX / W, (H - PY) / H)
KMAX = 34                            # voxel layers (height in px)
NJ = H + KMAX + 2                    # ground rows held by the voxel grid

# Ground coordinates of voxel centres (px from the pivot, +gy = south / screen-down)
_GX = np.repeat((np.arange(W) - PX + 0.5)[None, :], NJ, 0)
_GY = np.repeat((np.arange(NJ) - PY + 0.5)[:, None], W, 1)
_R = np.hypot(_GX, _GY)
_TH = np.arctan2(_GY, _GX)

# Layout (ground px from the pivot; heights in px)
R_OUT, R_IN = 35.0, 28.0             # footprint radius 35 px = 2.2 world units
R_MID = (R_OUT + R_IN) / 2
WALL_H = 9                           # visible outer wall face on the south side
MERLON_H = 2
GATE_X0, GATE_X1, GATE_Y0, GATE_Y1 = -14, 14, 20, 39   # gatehouse block (south)
GATE_H = 12
GATE_PLAT = (0.0, 30.0, 9.0)          # station platform on the gatehouse top (cx, cy, r)
BASTION = (33.0, 0.0, 12.0)           # east bastion (cx, cy, r)
BASTION_H = 12
SPIRE = (0.0, -32.0, 4.5)             # north crown spire (cx, cy, shaft radius)
SPIRE_H = 30                          # platform top height
SPIRE_GAL_R = 9.0                     # gallery (station platform) radius
DAIS = (0.0, -8.0)                    # hero dais centre
DAIS_R = 9.0
DAIS_H = 3                            # above the 1 px courtyard floor
HEART_POS = (-19.0, -15.0)            # Stormheart pedestal (ground), clear of the hero's silhouette
HEART_Z = 21                          # crystal centre height (floats above a slim pedestal)

# Materials
(EMPTY, WALL, MERLON, FLOOR, DAIS_M, DAIS_RIM, PLAT, PLAT_RIM, SPIRE_M, SLATE, GATEH,
 BANNER, STEPS, PEDESTAL, CRADLE, IRON, RUBBLE, BASTION_M, WINDOW, SILVER, SPIKE,
 RUNE, PAWREL) = range(23)

# Objects (for normals / texture coordinates)
O_NONE, O_RING, O_GATE, O_BAST, O_SPIRE, O_DAIS, O_PED, O_FLOOR, O_MISC, O_STEPS = range(10)
O_BANNER0 = 20                        # banners: O_BANNER0 + index into Scene.banners

TOP, SOUTH = 0, 1
NO_OUTLINE = [MERLON, SPIKE, RUNE, IRON, BANNER, SILVER, PAWREL, WINDOW, SLATE]

# Ramps (dark -> light)
STONE = [PAL["stone0"], PAL["stone1"], PAL["stone2"], PAL["stone3"], PAL["stone4"]]
FLOOR_R = [PAL["stone0"], PAL["stone1"], E.hexc("#383447"), PAL["stone2"], E.hexc("#4f4a63")]
VIOLET = [PAL["violet0"], PAL["violet1"], PAL["violet2"], PAL["violet3"], PAL["violet4"]]
SILV = [PAL["silver0"], PAL["silver0"], PAL["silver1"], PAL["silver2"], PAL["silver3"]]
IRON_R = [PAL["iron0"], PAL["iron1"], PAL["iron2"], PAL["iron3"], PAL["iron4"]]
CYAN = [PAL["cyan0"], PAL["cyan1"], PAL["cyan2"], PAL["cyan3"], PAL["cyan4"]]
OUT = PAL["outline"]

# Light: from the top-left of the screen = north-west and above (toward-light vector)
_L = np.array([-0.354, -0.354, 0.866])
_L = _L / np.linalg.norm(_L)

PAW5 = [".#.#.", "#...#", ".###.", ".###."]          # upright paw print (toes up)
PAW3 = ["#.#", "###"]                                  # tiny paw for the gatehouse corners
PAW7 = ["..#.#..", ".##.##.", "#.....#", "#.###.#", ".#####.", ".#####.", "..###.."]


def _hash(*arrs, salt: int = 0) -> np.ndarray:
    """Deterministic per-cell noise in [0, 1)."""
    acc = np.full(np.broadcast(*arrs).shape, np.uint64(salt * 2654435761 + 97531), dtype=np.uint64)
    for n, a in enumerate(arrs):
        a = np.asarray(a).astype(np.int64).astype(np.uint64)
        acc = acc ^ (a * np.uint64((0x9E3779B1 + 0x85EBCA77 * (n + 1)) & 0xFFFFFFFF))
        acc = (acc * np.uint64(0xC2B2AE3D)) & np.uint64(0xFFFFFFFFFFFF)
        acc = acc ^ (acc >> np.uint64(17))
    return (acc & np.uint64(0xFFFF)).astype(np.float64) / 65536.0


# --------------------------------------------------------------------------------------
# Voxel scene
# --------------------------------------------------------------------------------------
class Scene:
    def __init__(self):
        self.m = np.zeros((KMAX, NJ, W), np.uint8)     # material
        self.o = np.zeros((KMAX, NJ, W), np.uint8)     # object id
        self.banners: List[dict] = []
        self.heart = True                              # draw the static Stormheart
        self.ruin = False

    def put(self, mask, k0, k1, mat, obj):
        k0, k1 = max(0, int(k0)), min(KMAX, int(k1))
        if k1 > k0:
            self.m[k0:k1, mask] = mat
            self.o[k0:k1, mask] = obj

    def put_empty(self, mask, k0, k1, mat, obj):
        """Like put(), but never overwrites existing voxels."""
        for k in range(max(0, int(k0)), min(KMAX, int(k1))):
            mk = mask & (self.m[k] == 0)
            self.m[k, mk] = mat
            self.o[k, mk] = obj

    def put_cols(self, mask, heights, k0, mat, obj):
        """Columns of varying height: fill layers k0..heights-1 where mask."""
        for k in range(max(0, k0), KMAX):
            mk = mask & (heights > k)
            if not mk.any():
                break
            self.m[k, mk] = mat
            self.o[k, mk] = obj


def disc(cx, cy, r):
    return (_GX - cx) ** 2 + (_GY - cy) ** 2 <= r * r


def ring(cx, cy, r0, r1):
    d = np.hypot(_GX - cx, _GY - cy)
    return (d <= r1) & (d >= r0)


def box(x0, x1, y0, y1):
    return (_GX > x0) & (_GX < x1) & (_GY > y0) & (_GY < y1)


def ang_diff(a, b):
    return (a - b + math.pi) % (2 * math.pi) - math.pi


def pattern_mask(cx: float, cy: float, rows: List[str]) -> np.ndarray:
    """Ground-plane mask from an ASCII pattern ('#' = set), centred on (cx, cy)."""
    m = np.zeros(_GX.shape, bool)
    h, w = len(rows), len(rows[0])
    x0 = math.floor(cx - w / 2 + 0.5)
    y0 = math.floor(cy - h / 2 + 0.5)
    for r in range(h):
        for c in range(w):
            if rows[r][c] == "#":
                gx, gy = x0 + c + 0.5, y0 + r + 0.5
                m |= (np.abs(_GX - gx) < 0.5) & (np.abs(_GY - gy) < 0.5)
    return m


def merlon_spots() -> List[Tuple[float, float]]:
    """Centres of the paw crenels on the ring (upright paw prints), skipping the turrets."""
    out = []
    n = 14
    for i in range(n):
        a = -math.pi / 2 + (i + 0.5) * 2 * math.pi / n
        deg = math.degrees(a) % 360
        if abs(deg - 270) < 16 or abs(deg - 90) < 24 or deg < 24 or deg > 336:
            continue
        out.append((R_MID * math.cos(a), R_MID * math.sin(a)))
    return out


# kind, where (angle for "arc", gx for "flat"), width, top layer, bottom layer
BANNER_SPOTS = [
    ("arc", math.radians(90 + 43), 7, WALL_H, 1),
    ("arc", math.radians(90 - 43), 7, WALL_H, 1),
    ("arc", math.radians(90 + 76), 7, WALL_H, 2),
    ("bast", math.radians(52), 7, BASTION_H - 1, 3),
]


def build_scene(variant: str = "base") -> Scene:
    """variant: base | r1 | r2 | r3 | ruin"""
    sc = Scene()
    ruin = variant == "ruin"
    sc.ruin = ruin
    level = {"base": 0, "r1": 1, "r2": 2, "r3": 3, "ruin": 0}[variant]
    rnd = E.rng(4099)

    # --- courtyard floor + ring wall ---------------------------------------------------
    sc.put(_R < R_IN + 0.5, 0, 1, FLOOR, O_FLOOR)
    wall = (_R <= R_OUT) & (_R >= R_IN)
    if not ruin:
        sc.put(wall, 0, WALL_H, WALL, O_RING)
    else:
        a = _TH
        hgt = (5.0 + 2.0 * np.sin(a * 3 + 0.7) + 1.6 * np.sin(a * 7 + 2.1) + 1.0 * np.sin(a * 13 + 0.3))
        hgt += (_hash(np.floor((a + 4) * 9), salt=5) - 0.5) * 3.0
        for breach in (math.radians(128), math.radians(38), math.radians(205), math.radians(305)):
            dd = np.abs(ang_diff(a, breach))
            hgt = np.where(dd < 0.17, 1.0 + 2.0 * dd / 0.17, hgt)
        hgt = np.clip(np.round(hgt), 1, WALL_H).astype(int)
        sc.put_cols(wall, hgt, 0, WALL, O_RING)

    # --- paw crenels (upright paw prints standing on the wall walk) -------------------------
    spots = merlon_spots()
    for n, (cx, cy) in enumerate(spots):
        if ruin and n not in (1, 6):
            continue
        mm = pattern_mask(cx, cy, PAW5) & (_R <= R_OUT + 0.3)
        sc.put(mm, WALL_H, WALL_H + MERLON_H, MERLON, O_RING)

    # --- east bastion ------------------------------------------------------------------------
    bx, by, br = BASTION
    bmask = disc(bx, by, br)
    if not ruin:
        sc.put(bmask, 0, BASTION_H, BASTION_M, O_BAST)
        sc.put(disc(bx, by, br - 0.8), BASTION_H, BASTION_H + 1, PLAT, O_BAST)
        sc.put(ring(bx, by, br - 2.0, br - 0.8), BASTION_H, BASTION_H + 1, PLAT_RIM, O_BAST)
        # arrow slit (cyan-lit) on the south-west face
        slit = (np.abs(ang_diff(np.arctan2(_GY - by, _GX - bx), math.radians(118))) * br < 0.6) & ring(bx, by, br - 1, br)
        sc.put(slit, 5, 9, WINDOW, O_BAST)
    else:
        th = np.arctan2(_GY - by, _GX - bx)
        hb = np.round(8 + 2.2 * np.sin(th * 3 + 1.0) + 1.3 * np.sin(th * 5)).astype(int)
        hb = np.where(disc(bx, by, br - 3), 4, hb)
        sc.put_cols(bmask, hb, 0, BASTION_M, O_BAST)

    # --- north crown spire ---------------------------------------------------------------------
    sx, sy, sr = SPIRE
    if not ruin:
        sc.put(disc(sx, sy, sr), 0, SPIRE_H - 6, SPIRE_M, O_SPIRE)
        for k, r in ((SPIRE_H - 6, sr + 1.0), (SPIRE_H - 5, sr + 2.2), (SPIRE_H - 4, sr + 3.4)):
            sc.put(disc(sx, sy, r), k, k + 1, SPIRE_M, O_SPIRE)
        sc.put(disc(sx, sy, SPIRE_GAL_R), SPIRE_H - 3, SPIRE_H, PLAT, O_SPIRE)
        sc.put(ring(sx, sy, SPIRE_GAL_R - 1.2, SPIRE_GAL_R), SPIRE_H - 1, SPIRE_H, PLAT_RIM, O_SPIRE)
        sc.put(ring(sx, sy, SPIRE_GAL_R - 0.9, SPIRE_GAL_R), SPIRE_H - 3, SPIRE_H - 1, SILVER, O_SPIRE)
        # violet slate skirt (stepped cone) + silver ring
        for k, r in ((14, sr + 2.6), (15, sr + 1.9), (16, sr + 1.2)):
            sc.put(disc(sx, sy, r), k, k + 1, SLATE, O_SPIRE)
        sc.put(ring(sx, sy, sr - 0.6, sr + 0.6), 13, 14, SILVER, O_SPIRE)
        # cyan window slit facing the courtyard
        win = (np.abs(_GX - sx) < 1.0) & (_GY > sy + sr - 1.2) & (_GY < sy + sr + 0.1)
        sc.put(win, 19, 22, WINDOW, O_SPIRE)
    else:
        th = np.arctan2(_GY - sy, _GX - sx)
        hs = np.round(13 + 2.5 * np.sin(th * 2 + 0.4) + 1.5 * np.sin(th * 5 + 1.3)).astype(int)
        sc.put_cols(disc(sx, sy, sr), hs, 0, SPIRE_M, O_SPIRE)

    # --- gatehouse (south) -----------------------------------------------------------------------
    gmask = box(GATE_X0, GATE_X1, GATE_Y0, GATE_Y1)
    if not ruin:
        sc.put(gmask, 0, GATE_H, GATEH, O_GATE)
        cx, cy, cr = GATE_PLAT
        sc.put(disc(cx, cy, cr), GATE_H, GATE_H + 1, PLAT, O_GATE)
        sc.put(ring(cx, cy, cr - 1.2, cr), GATE_H, GATE_H + 1, PLAT_RIM, O_GATE)
        # small paw crenels on the four corners
        for ccx, ccy in ((-11.5, GATE_Y1 - 2), (11.5, GATE_Y1 - 2), (-11.5, GATE_Y0 + 3), (11.5, GATE_Y0 + 3)):
            sc.put(pattern_mask(ccx, ccy, PAW3), GATE_H, GATE_H + 2, MERLON, O_GATE)
    else:
        hg = np.full(_GX.shape, GATE_H - 1)
        hg = np.where(_GX < -3, np.round(GATE_H - 5 + 2 * np.sin(_GX * 0.9)).astype(int), hg)
        hg = np.where(_GX > 5, np.round(GATE_H - 2 - 0.7 * (_GX - 5)).astype(int), hg)
        sc.put_cols(gmask, hg, 0, GATEH, O_GATE)

    # --- dais + Stormheart pedestal ---------------------------------------------------------------
    dx, dy = DAIS
    sc.put(disc(dx, dy, DAIS_R), 1, 1 + DAIS_H, DAIS_M, O_DAIS)
    sc.put(ring(dx, dy, DAIS_R - 1.2, DAIS_R), DAIS_H, 1 + DAIS_H, DAIS_RIM, O_DAIS)
    hx, hy = HEART_POS
    sc.put(disc(hx, hy, 2.9), 1, 3, PEDESTAL, O_PED)
    if not ruin:
        sc.put(disc(hx, hy, 1.7), 3, 11, PEDESTAL, O_PED)
        sc.put(disc(hx, hy, 2.6), 11, 12, CRADLE, O_PED)
        for ddx, ddy in ((-2.2, -0.8), (2.2, -0.8), (0.0, 1.9)):
            sc.put(disc(hx + ddx, hy + ddy, 0.7), 12, 14, CRADLE, O_PED)
    else:
        sc.heart = False

    # --- banners (thin cloth slabs hanging on south-facing faces) --------------------------------
    for (kind, where, wdt, kt, kb) in BANNER_SPOTS:
        if kind == "arc":
            u = ang_diff(_TH, where) * (R_OUT + 0.5)
            mask = (np.abs(u) < wdt / 2) & (_R > R_OUT) & (_R <= R_OUT + 1.1)
        else:
            thb = np.arctan2(_GY - by, _GX - bx)
            rb = np.hypot(_GX - bx, _GY - by)
            u = ang_diff(thb, where) * (br + 0.5)
            mask = (np.abs(u) < wdt / 2) & (rb > br) & (rb <= br + 1.1)
        if ruin:
            kb = kb + 3
        sc.banners.append({"kind": kind, "where": where, "w": wdt, "kt": kt, "kb": kb})
        sc.put(mask, kb, kt + 1, BANNER, O_BANNER0 + len(sc.banners) - 1)

    # --- reinforcements -------------------------------------------------------------------------
    if level >= 1:
        band = (_R > R_OUT) & (_R <= R_OUT + 1.0)
        band &= ~box(GATE_X0 - 0.5, GATE_X1 + 0.5, 0, 60) & ~disc(bx, by, br + 1.2)
        for k in (2, 6):
            sc.put_empty(band, k, k + 1, IRON, O_RING)
        gband = (_GY > GATE_Y1) & (_GY < GATE_Y1 + 1) & (np.abs(_GX) < GATE_X1)
        sc.put_empty(gband & ~(np.abs(_GX) < 8.5), 2, 3, IRON, O_GATE)
        sc.put_empty(gband, GATE_H - 1, GATE_H, IRON, O_GATE)
    if level >= 2:
        sc.m[sc.m == MERLON] = IRON
        bb = ring(bx, by, br, br + 1.0) & (_GY > by - 3) & ~wall
        for k in (2, 7):
            sc.put_empty(bb, k, k + 1, IRON, O_BAST)
        for side in (-1, 1):
            brace = (np.abs(_GX - side * (GATE_X1 - 1.0)) < 1.0) & (_GY > GATE_Y1) & (_GY < GATE_Y1 + 1)
            sc.put(brace, 0, GATE_H, IRON, O_GATE)
        sb = ring(sx, sy, sr, sr + 1.0)
        for k in (8, 11, 20):
            sc.put_empty(sb, k, k + 1, IRON, O_SPIRE)
    if level >= 3:
        for (cx, cy) in spots:
            tip = pattern_mask(cx, cy + 0.5, ["#"])
            sc.put(tip, WALL_H + MERLON_H, WALL_H + MERLON_H + 2, SPIKE, O_RING)
        runes = (_R > R_OUT) & (_R <= R_OUT + 1.0) & (_GY > 4)
        runes &= np.abs(((np.round(_TH * R_OUT) + 3) % 9) - 4) < 0.6
        runes &= ~box(GATE_X0 - 0.5, GATE_X1 + 0.5, 0, 60) & ~disc(bx, by, br + 1.2)
        sc.put_empty(runes, 4, 5, RUNE, O_RING)
        sc.put(ring(sx, sy, SPIRE_GAL_R - 0.2, SPIRE_GAL_R + 1.0), SPIRE_H - 3, SPIRE_H - 1, IRON, O_SPIRE)
        for side in (-1, 1):
            spk = pattern_mask(side * 6.5, GATE_Y1 - 1, ["#"])
            sc.put(spk, GATE_H, GATE_H + 2, SPIKE, O_GATE)
        for a_deg in (-60, -20, 20, 60, 100, 140, 180, 220):
            ax_, ay_ = bx + (br - 0.8) * math.cos(math.radians(a_deg)), by + (br - 0.8) * math.sin(math.radians(a_deg))
            sc.put(pattern_mask(ax_, ay_, ["#"]), BASTION_H, BASTION_H + 2, SPIKE, O_BAST)

    # --- ruin rubble ---------------------------------------------------------------------------------
    if ruin:
        for _ in range(80):
            ang = rnd.uniform(0, 2 * math.pi)
            rr = rnd.uniform(R_OUT + 0.5, R_OUT + 5) if rnd.random() < 0.55 else rnd.uniform(R_IN - 7, R_IN - 0.5)
            cx, cy = rr * math.cos(ang), rr * math.sin(ang)
            if abs(cy) > 42 or abs(cx) > 44 or math.hypot(cx - DAIS[0], cy - DAIS[1]) < DAIS_R + 1:
                continue
            rad = rnd.choice((0.7, 1.0, 1.3, 1.6))
            sc.put_empty(disc(cx, cy, rad), 0, rnd.choice((1, 1, 2, 2, 3)), RUBBLE, O_MISC)
        for cx, cy, r, hh in ((7, -19, 2.4, 3), (11, -15, 1.6, 2), (-5, -21, 1.5, 2), (15, -22, 1.2, 2),
                              (-20, 4, 1.8, 2), (-9, 14, 1.4, 2)):
            sc.put_empty(disc(cx, cy, r), 0, hh, RUBBLE, O_MISC)
    return sc


# --------------------------------------------------------------------------------------
# Renderer
# --------------------------------------------------------------------------------------
def render_ids(sc: Scene):
    """Per screen pixel: hit, ground row J, layer K, face (TOP/SOUTH)."""
    s = np.arange(H)[:, None]
    cols = np.broadcast_to(np.arange(W)[None, :], (H, W))
    hit = np.zeros((H, W), bool)
    J = np.zeros((H, W), np.int32)
    K = np.zeros((H, W), np.int32)
    F = np.zeros((H, W), np.int8)
    for k in range(KMAX - 1, -1, -1):
        for face, dj in ((TOP, 1), (SOUTH, 0)):
            jj = np.broadcast_to(s + k + dj, (H, W))
            ok = jj < NJ
            solid = (sc.m[k, np.clip(jj, 0, NJ - 1), cols] > 0) & ok
            new = solid & ~hit
            if new.any():
                J[new] = jj[new]
                K[new] = k
                F[new] = face
                hit |= new
    return hit, J, K, F


def _occ(sc: Scene, i, j, k):
    ok = (i >= 0) & (i < W) & (j >= 0) & (j < NJ) & (k >= 0) & (k < KMAX)
    out = np.zeros(np.shape(i), bool)
    out[ok] = sc.m[k[ok], j[ok], i[ok]] > 0
    return out


def render(sc: Scene) -> Tuple[np.ndarray, dict]:
    hit, J, K, F = render_ids(sc)
    img = E.new(W, H)
    ys, xs = np.nonzero(hit)
    j, k, f = J[ys, xs], K[ys, xs], F[ys, xs]
    i = xs
    mat = sc.m[k, j, i]
    obj = sc.o[k, j, i]
    gx = i - PX + 0.5
    gy = j - PY + 0.5
    z = np.where(f == TOP, k + 1.0, k + 0.5)

    # ---- normals (horizontal part for south faces) --------------------------------------------
    nx = np.zeros(len(i))
    centres = {O_BAST: BASTION[:2], O_SPIRE: SPIRE[:2], O_PED: HEART_POS, O_DAIS: DAIS, O_RING: (0.0, 0.0)}
    for oid, (cx, cy) in centres.items():
        sel = obj == oid
        if sel.any():
            dx, dy = gx[sel] - cx, gy[sel] - cy
            d = np.hypot(dx, dy) + 1e-6
            sgn = np.where(d < R_MID, -1.0, 1.0) if oid == O_RING else 1.0
            nx[sel] = sgn * dx / d
    for bi, b in enumerate(sc.banners):
        sel = obj == O_BANNER0 + bi
        if sel.any():
            cx, cy = (0.0, 0.0) if b["kind"] == "arc" else BASTION[:2]
            nx[sel] = (gx[sel] - cx) / (np.hypot(gx[sel] - cx, gy[sel] - cy) + 1e-6)

    # ---- cast shadows (march toward the light) ---------------------------------------------------
    px0 = gx + np.where(f == SOUTH, nx * 0.51, 0)
    py0 = gy + np.where(f == SOUTH, 0.51, 0)
    pz0 = np.where(f == TOP, z + 0.01, z)
    shadow = np.zeros(len(i), bool)
    for t in np.arange(0.9, 40, 0.7):
        qx = np.floor(px0 + _L[0] * t + PX).astype(int)
        qy = np.floor(py0 + _L[1] * t + PY).astype(int)
        qz = np.floor(pz0 + _L[2] * t).astype(int)
        shadow |= _occ(sc, qx, qy, qz)

    # ---- ambient occlusion -------------------------------------------------------------------------
    ao = np.zeros(len(i))
    top = f == TOP
    for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        ao += np.where(top, _occ(sc, i + di, j + dj, k + 1), 0)
    side = ~top
    for di, dk in ((-1, 0), (1, 0), (0, 1), (-1, 1), (1, 1)):
        ao += np.where(side, _occ(sc, i + di, j + 1, k + dk) * 1.5, 0)

    # ---- rims ------------------------------------------------------------------------------------------
    same = lambda di, dj, dk: _occ(sc, i + di, j + dj, k + dk)  # noqa: E731
    rim_lit = top & (~same(-1, 0, 0) | ~same(0, -1, 0)) & ~same(0, 0, 1)
    rim_dark = top & (~same(1, 0, 0) | ~same(0, 1, 0)) & ~rim_lit
    cap = side & ~same(0, 0, 1)

    at = dict(i=i, j=j, k=k, f=f, mat=mat, obj=obj, gx=gx, gy=gy, z=z, nx=nx,
              shadow=shadow, ao=ao, rim_lit=rim_lit, rim_dark=rim_dark, cap=cap, sc=sc)
    img[ys, xs] = shade(at)
    info = dict(hit=hit, J=J, K=K, F=F, ys=ys, xs=xs, at=at)
    img = outline_pass(img, info)
    return img, info


def _pick(ramp, idx):
    idx = np.clip(np.asarray(idx), 0, len(ramp) - 1).astype(int)
    return np.array(ramp, np.uint8)[idx]


def shade(a: dict) -> np.ndarray:
    n = len(a["i"])
    out = np.zeros((n, 4), np.uint8)
    mat, f, k, obj = a["mat"], a["f"], a["k"], a["obj"]
    gx, gy = a["gx"], a["gy"]
    top = f == TOP
    side = ~top
    sc: Scene = a["sc"]
    noise = _hash(a["i"], a["j"], a["k"], a["f"], salt=11)

    # generic stepped lighting offset
    lit = np.zeros(n, int)
    lit += np.where(top & a["rim_lit"], 1, 0)
    lit -= np.where(a["shadow"], 1, 0)
    lit -= np.where(top & (a["ao"] >= 4), 1, 0)
    lit += np.where(side & (a["nx"] < -0.45), 1, 0)
    lit -= np.where(side & (a["nx"] > 0.55), 1, 0)
    lit -= np.where(side & (a["ao"] >= 3), 1, 0)
    lit += np.where(side & a["cap"], 1, 0)

    def put(sel, ramp, base):
        if np.any(sel):
            b = base[sel] if isinstance(base, np.ndarray) else np.full(int(np.sum(sel)), base)
            out[sel] = _pick(ramp, b)

    # ---- texture coordinate along faces ------------------------------------------------------
    u = np.zeros(n)
    for oid, (cx, cy, rr) in ((O_RING, (0, 0, R_OUT)), (O_BAST, BASTION), (O_SPIRE, SPIRE), (O_PED, (*HEART_POS, 2.2))):
        sel = obj == oid
        u[sel] = np.arctan2(gy[sel] - cy, gx[sel] - cx) * rr
    selg = obj == O_GATE
    u[selg] = gx[selg]

    # ---- stone ---------------------------------------------------------------------------------------
    stone_like = np.isin(mat, [WALL, BASTION_M, GATEH, SPIRE_M, STEPS, PEDESTAL, RUBBLE, MERLON])
    tone = np.where(top, 3, 2) + lit
    walk = (mat == WALL) & top                              # wall walk: calmer, one step darker
    tone -= np.where(walk & ~a["rim_lit"], 1, 0)
    tone += np.where((mat == MERLON) & top, 1, 0)
    course = np.floor_divide(k + 1, 3)
    mortar_row = side & ((k + 1) % 3 == 0) & ~a["cap"]
    joint = side & ~mortar_row & (np.floor(u + 3.5 * (course % 2)) % 7 == 0)
    tone -= np.where(stone_like & (mortar_row | joint) & (mat != MERLON) & (mat != RUBBLE), 1, 0)
    tone -= np.where(stone_like & ~walk & (noise < 0.06), 1, 0)
    tone += np.where(stone_like & top & ~walk & (noise > 0.96), 1, 0)
    tone -= np.where(side & (k == 0) & stone_like, 1, 0)
    tone -= np.where((mat == RUBBLE) & (noise < 0.4), 1, 0)
    put(stone_like, STONE, tone)

    # ---- gate + paw emblems painted on the gatehouse front face ----------------------------------
    gate_front = side & (obj == O_GATE) & (mat == GATEH) & (a["j"] == PY + GATE_Y1 - 1)
    if gate_front.any():
        idx = np.nonzero(gate_front)[0]
        cols = gate_colors(gx[idx], k[idx], sc.ruin)
        m = cols[:, 3] > 0
        out[idx[m]] = cols[m]

    # ---- courtyard floor -----------------------------------------------------------------------
    fl = mat == FLOOR
    if fl.any():
        r = np.hypot(gx, gy)
        th = np.arctan2(gy, gx)
        bounds = np.array([12.5, 20.0])
        ringi = np.digitize(r, bounds)
        nseg = np.array([8, 14, 20])[ringi]
        pos = (th + math.pi) / (2 * math.pi) * nseg + ringi * 0.37
        seg = np.floor(pos)
        edge_r = np.min(np.abs(r[:, None] - bounds[None, :]), axis=1) < 0.5
        edge_t = (pos % 1.0) * (r * 2 * math.pi / nseg) < 1.0
        ftone = 3 + lit - np.where(edge_r | edge_t, 1, 0)
        stn = _hash(seg, ringi, salt=3)
        ftone -= np.where((stn < 0.3) & (noise < 0.35), 1, 0)
        put(fl, FLOOR_R, ftone)
        if sc.heart:
            # Stormheart light pool: solid tint near the pedestal, ordered dither further out
            dh = np.hypot(gx - HEART_POS[0], (gy - HEART_POS[1]) * 1.2)
            checker = (a["i"] + a["j"]) % 2 == 0
            c1, c2 = np.array(E.hexc("#3a4a60"), np.uint8), np.array(E.hexc("#44607a"), np.uint8)
            inner = fl & top & (dh < 4.6)
            outer = fl & top & (dh >= 4.6) & (dh < 7.2) & checker
            out[outer] = c1
            out[inner] = np.where(((dh[inner] < 3.2) | checker[inner])[:, None], c2, c1)

    # ---- dais ------------------------------------------------------------------------------------------
    dm = mat == DAIS_M
    if dm.any():
        r = np.hypot(gx - DAIS[0], gy - DAIS[1])
        th = np.arctan2(gy - DAIS[1], gx - DAIS[0])
        put(dm, STONE, np.where(top, 3, 2) + lit)
        on_ring = dm & top & (np.abs(r - 5.0) < 0.55)
        dash = np.floor((th + math.pi) * 6 / math.pi) % 2 == 0
        out[on_ring & dash] = PAL["cyan1"]
        out[on_ring & ~dash] = PAL["stone2"]
    put(mat == DAIS_RIM, SILV, np.where(top, 3, 1) + lit)

    # ---- platforms (station tops) + rims ---------------------------------------------------------
    pl = mat == PLAT
    if pl.any():
        ptone = np.where(top, 3, 2) + lit
        # darker groove ring just inside the silver rim -> reads as a socket
        for oid, (cx, cy, rr) in ((O_BAST, (BASTION[0], BASTION[1], BASTION[2] - 2.0)),
                                  (O_SPIRE, (SPIRE[0], SPIRE[1], SPIRE_GAL_R - 1.2)),
                                  (O_GATE, (GATE_PLAT[0], GATE_PLAT[1], GATE_PLAT[2] - 1.2))):
            sel = pl & top & (obj == oid)
            d = np.hypot(gx - cx, gy - cy)
            ptone -= np.where(sel & (d > rr - 1.1), 1, 0)
            # engraved paw print in the middle of the socket (seen when the slot is empty)
            lx = np.floor(gx - cx + 3.5).astype(int)
            ly = np.floor(gy - cy + 3.5).astype(int)
            inside = sel & (lx >= 0) & (lx < 7) & (ly >= 0) & (ly < 7)
            for q in np.nonzero(inside)[0]:
                if PAW7[ly[q]][lx[q]] == "#":
                    ptone[q] -= 1
        put(pl, STONE, ptone)
    put(mat == PLAT_RIM, SILV, np.where(top, 2, 1) + lit)

    # ---- trims, cradle, iron, spikes, runes, windows ------------------------------------------
    put(mat == SLATE, VIOLET, np.where(top, 2, 1) + lit + np.where(top & (noise > 0.8), 1, 0))
    put(mat == SILVER, SILV, np.where(top, 3, 2) + lit)
    put(mat == CRADLE, SILV, np.where(top, 2, 1) + lit)
    ir = mat == IRON
    if ir.any():
        rivet = side & (np.floor(u + 0.5) % 3 == 0)
        itone = np.where(top, 3, 1) + np.clip(lit, -1, 1)
        put(ir, IRON_R, np.where(rivet, 4, itone))
    put(mat == SPIKE, SILV, np.where(top, 4, 3) + lit)
    out[mat == RUNE] = PAL["cyan2"]
    wn = mat == WINDOW
    if wn.any():
        out[wn] = PAL["cyan2"]
        out[wn & (k == np.max(k[wn]))] = PAL["cyan3"] if not sc.ruin else PAL["stone1"]

    # ---- banners -------------------------------------------------------------------------------------
    bn = np.nonzero(mat == BANNER)[0]
    for bi, b in enumerate(sc.banners):
        sel = bn[obj[bn] == O_BANNER0 + bi]
        if len(sel) == 0:
            continue
        if b["kind"] == "arc":
            lu = ang_diff(np.arctan2(gy[sel], gx[sel]), b["where"]) * (R_OUT + 0.5)
        else:
            lu = ang_diff(np.arctan2(gy[sel] - BASTION[1], gx[sel] - BASTION[0]), b["where"]) * (BASTION[2] + 0.5)
        out[sel] = banner_colors(lu, k[sel], b, sc.ruin)
    return out


GATE_ROWS = [  # left half of the cat-head gate, z = 11 (top) .. z = 0; mirrored at build time
    "........",
    "..s.....",
    "..ss....",
    "..sds...",
    "..sdds..",
    ".sddddss",
    ".sdddddd",
    ".sdEeddd",
    ".sdeedd.",
    ".sddddd.",
    ".sdddddi",
    ".sdddddi",
]
PAW_EMBLEM = [".#.#.", "#...#", ".###.", ".###."]


def gate_colors(gx: np.ndarray, k: np.ndarray, ruin: bool) -> np.ndarray:
    """Cat-head gate (16 px) + silver paw emblems on the gatehouse front face."""
    rows = [r + r[::-1] for r in GATE_ROWS]              # 16 wide, symmetric
    # nose: two silver pixels in the middle of row z=4
    rows = [list(r) for r in rows]
    rows[11 - 4][7] = rows[11 - 4][8] = "n"
    rows = ["".join(r) for r in rows]
    lit = not ruin
    leg = {
        "s": PAL["silver1"] if lit else PAL["silver0"],
        "d": PAL["violet0"],
        "e": PAL["cyan2"] if lit else PAL["stone1"],
        "E": PAL["cyan4"] if lit else PAL["stone2"],
        "n": PAL["silver0"],
        "i": PAL["outline"],
    }
    out = np.zeros((len(gx), 4), np.uint8)
    col = np.floor(gx + 8).astype(int)
    row = 11 - k
    for q in range(len(gx)):
        c, r = col[q], row[q]
        if 0 <= c < 16 and 0 <= r < 12:
            ch = rows[r][c]
            if ch in leg:
                out[q] = leg[ch]
        # paw emblems on the two pilasters
        for cx0 in (-13, 8):
            pc, pr = int(math.floor(gx[q])) - cx0, 8 - k[q]
            if 0 <= pc < 5 and 0 <= pr < 4 and PAW_EMBLEM[pr][pc] == "#":
                out[q] = PAL["silver2"] if lit else PAL["silver0"]
    # the bottom-row door seam shadow
    return out


def banner_colors(lu: np.ndarray, k: np.ndarray, b: dict, ruin: bool) -> np.ndarray:
    wdt, kt, kb = b["w"], b["kt"], b["kb"]
    n = len(lu)
    col = np.clip(np.floor(lu + wdt / 2).astype(int), 0, wdt - 1)
    row = kt - k                                  # 0 at the top
    height = kt - kb + 1
    out = np.zeros((n, 4), np.uint8)
    out[:] = PAL["violet2"]
    out[col == 0] = PAL["violet3"]
    out[col == wdt - 1] = PAL["violet1"]
    out[row == height - 2] = PAL["violet1"]
    out[row == 0] = PAL["silver1"]                # hanging rod
    out[(row == 0) & (col == wdt - 1)] = PAL["silver0"]
    tail = (row == height - 1)
    out[tail & (np.abs(col - (wdt - 1) / 2) < 1.6)] = 0                  # swallow-tail notch
    out[tail & ~(np.abs(col - (wdt - 1) / 2) < 1.6)] = PAL["violet1"]
    pw = PAW5
    ox, oy = (wdt - 5) // 2, 2
    for q in range(n):
        r, c = row[q] - oy, col[q] - ox
        if 0 <= r < 4 and 0 <= c < 5 and pw[r][c] == "#":
            out[q] = (PAL["silver2"] if r < 2 else PAL["silver1"]) if not ruin else PAL["silver0"]
    if ruin:   # torn: ragged lower half
        rag = (row >= height // 2) & (_hash(col, row, salt=9) < 0.45)
        out[rag] = 0
    return out


def outline_pass(img: np.ndarray, info: dict) -> np.ndarray:
    """Silhouette outline + dark lines where a nearer major form overlaps a farther one."""
    hit = info["hit"]
    at = info["at"]
    ys, xs = info["ys"], info["xs"]
    out = img.copy()
    P = np.zeros((H, W, 3))
    P[ys, xs, 0], P[ys, xs, 1], P[ys, xs, 2] = at["gx"], at["gy"], at["z"]
    matmap = np.zeros((H, W), np.uint8)
    matmap[ys, xs] = at["mat"]
    depth = np.full((H, W), -1e9)
    depth[ys, xs] = at["gy"] + at["z"]
    edge = np.zeros((H, W), bool)
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        q = np.roll(np.roll(P, dy, 0), dx, 1)
        qd = np.roll(np.roll(depth, dy, 0), dx, 1)
        qh = np.roll(np.roll(hit, dy, 0), dx, 1)
        qm = np.roll(np.roll(matmap, dy, 0), dx, 1)
        dist = np.sqrt(np.sum((P - q) ** 2, axis=2))
        edge |= hit & qh & (dist > 2.6) & (depth < qd - 1.5) & ~np.isin(qm, NO_OUTLINE)
    out[edge] = OUT
    grown = hit.copy()
    grown[1:, :] |= hit[:-1, :]
    grown[:-1, :] |= hit[1:, :]
    grown[:, 1:] |= hit[:, :-1]
    grown[:, :-1] |= hit[:, 1:]
    out[grown & ~hit] = OUT
    return out


# --------------------------------------------------------------------------------------
# Stormheart crystal
# --------------------------------------------------------------------------------------
CRYSTAL_ROWS = [
    "...o...",
    "..oWo..",
    "..o43o.",
    ".oW432o",
    ".o4432o",
    "o44322o",
    "o43322o",
    "o43221o",
    ".o3221o",
    ".o3211o",
    "..o21o.",
    "..o1o..",
    "...o...",
]
CORE_OFF = (4, 1)                    # where the core sits inside the 16x16 anim frame


def crystal_core(phase: int = 0, dim: bool = False) -> np.ndarray:
    if dim:
        ramp = [PAL["stone0"], PAL["stone1"], E.hexc("#3d5566"), E.hexc("#56707e"), E.hexc("#7d95a0")]
        leg = {"o": PAL["outline"], "1": ramp[1], "2": ramp[2], "3": ramp[3], "4": ramp[3], "W": ramp[4]}
    else:
        b = [0, 1, 1, 0][phase % 4]                  # frames 1-2 are one step brighter
        leg = {"o": PAL["cyan0"], "1": CYAN[1 + b], "2": CYAN[2 + b], "3": CYAN[3 + b],
               "4": CYAN[3 + b], "W": CYAN[4]}
    return E.ascii_art(CRYSTAL_ROWS, leg)


def stormheart_frames() -> List[np.ndarray]:
    frames = []
    strength = [0.36, 0.5, 0.64, 0.5]
    for p in range(4):
        fr = E.new(16, 16)
        core = crystal_core(p)
        src = E.new(16, 16)
        E.paste(src, core, *CORE_OFF)
        halo = E.glow(src, PAL["cyan2"], radius=3, strength=strength[p])
        halo[src[:, :, 3] > 0] = 0
        E.paste(fr, halo, 0, 0)
        E.paste(fr, core, *CORE_OFF)
        for m in range(2):                            # two orbiting motes
            ang = (p / 4.0 + m * 0.5 + 0.125) * 2 * math.pi
            mx = int(round(7.5 + 6.3 * math.cos(ang)))
            my = int(round(7.0 + 2.4 * math.sin(ang)))
            if fr[my, mx, 3] < 200:
                fr[my, mx] = PAL["cyan3"]
        frames.append(fr)
    return frames


def heart_anchor_px() -> Tuple[float, float]:
    """Stormheart anchor in sprite pixel coords (boundary coords, y down)."""
    return PX + HEART_POS[0], PY + HEART_POS[1] - HEART_Z


def paste_heart(img: np.ndarray) -> None:
    """Static crystal core at the Stormheart anchor (pixel-identical to anim frame 0's core)."""
    ax, ay = heart_anchor_px()
    E.paste(img, crystal_core(0), int(round(ax - 8 + CORE_OFF[0])), int(round(ay - 8 + CORE_OFF[1])))


def paste_fallen_heart(img: np.ndarray) -> None:
    """Ruin: the dimmed crystal lies tipped over beside its pedestal."""
    core = crystal_core(0, dim=True)
    rot = np.rot90(core, 1).copy()                    # lying on its side
    gxc, gyc = -17.0, -5.0                           # ground spot beside the toppled pedestal
    E.paste(img, rot, int(PX + gxc - rot.shape[1] / 2), int(PY + gyc - 2 - rot.shape[0] / 2))


# --------------------------------------------------------------------------------------
# Overlays
# --------------------------------------------------------------------------------------
def diff_overlay(base: np.ndarray, other: np.ndarray) -> np.ndarray:
    d = np.any(base != other, axis=2)
    out = E.new(W, H)
    out[d] = other[d]
    return out


def crack_overlay(base: np.ndarray, info: dict, level: int) -> np.ndarray:
    """Dark jagged cracks with a lit lip, chipped rims, broken crenels, soot and rubble.
    Level 2 is a strict superset of level 1 (identical pixels + more)."""
    at = info["at"]
    hit = info["hit"]
    matmap = np.zeros((H, W), np.uint8)
    matmap[info["ys"], info["xs"]] = at["mat"]
    facemap = np.full((H, W), -1, np.int8)
    facemap[info["ys"], info["xs"]] = at["f"]
    stone = np.isin(matmap, [WALL, BASTION_M, GATEH, SPIRE_M, PLAT]) & hit
    # never draw over the pasted Stormheart crystal (it is not part of the voxel render)
    heart = E.new(W, H)
    paste_heart(heart)
    hm = heart[:, :, 3] > 0
    hm = hm | np.roll(hm, 1, 0) | np.roll(hm, -1, 0) | np.roll(hm, 1, 1) | np.roll(hm, -1, 1)
    # keep the cat gate (eyes + arch) readable at every damage level
    gate_rows = PY + GATE_Y1 - 1
    hm[gate_rows - GATE_H:gate_rows + 1, PX - 9:PX + 9] = True
    stone &= ~hm
    wallface = stone & (facemap == SOUTH) & np.isin(matmap, [WALL, BASTION_M, GATEH, SPIRE_M])
    walltop = np.isin(matmap, [WALL, GATEH, PLAT, BASTION_M]) & (facemap == TOP) & ~hm
    ov = E.new(W, H)

    def spread_points(mask, n, seed, min_d=9):
        ys, xs = np.nonzero(mask)
        rr = E.rng(seed)
        order = list(range(len(xs)))
        rr.shuffle(order)
        pts = []
        for q in order:
            x, y = int(xs[q]), int(ys[q])
            if all(abs(x - a) + abs(y - b) >= min_d for a, b in pts):
                pts.append((x, y))
            if len(pts) >= n:
                break
        return pts

    def crack(x, y, length, rr, vertical, depth=0):
        dx = rr.choice((-1, 1))
        pts = []
        for _ in range(length):
            if not (0 <= x < W and 0 <= y < H) or not stone[y, x]:
                break
            pts.append((x, y))
            if vertical:
                if rr.random() < 0.72:
                    y += 1
                else:
                    x += dx
            else:
                if rr.random() < 0.6:
                    x += dx
                else:
                    y += rr.choice((-1, 1))
            if rr.random() < 0.15:
                dx = -dx
            if depth == 0 and len(pts) > 3 and rr.random() < 0.12:
                crack(x, y, 3, rr, not vertical, 1)
        for (cx, cy) in pts:
            ov[cy, cx] = OUT
        for (cx, cy) in pts:            # lit lip to the lower right
            for (lx, ly) in ((cx + 1, cy), (cx, cy + 1)):
                if 0 <= lx < W and 0 <= ly < H and stone[ly, lx] and ov[ly, lx, 3] == 0 and rr.random() < 0.5:
                    ov[ly, lx] = PAL["stone4"] if facemap[ly, lx] == TOP else PAL["stone3"]

    def chip(x, y):
        """A bite out of a wall rim: dark notch with a lit lower edge."""
        for (ddx, ddy, c) in ((0, 0, OUT), (1, 0, PAL["stone0"]), (0, 1, PAL["stone1"]), (1, 1, PAL["stone3"]), (-1, 0, PAL["stone1"])):
            xx, yy = x + ddx, y + ddy
            if 0 <= xx < W and 0 <= yy < H and hit[yy, xx] and not hm[yy, xx]:
                ov[yy, xx] = c

    def rubble_at(x):
        col = np.nonzero(hit[:, x])[0]
        if len(col) == 0:
            return
        yy = int(col.max()) + 2
        if yy >= H - 1:
            return
        for (ddx, ddy, c) in ((0, 0, PAL["stone3"]), (1, 0, PAL["stone2"]), (0, 1, PAL["stone2"]), (1, 1, PAL["stone1"])):
            ov[min(H - 1, yy + ddy), x + ddx] = c
        for (ddx, ddy) in ((-1, 0), (-1, 1), (2, 0), (2, 1), (0, 2), (1, 2), (0, -1), (1, -1)):
            xx, y2 = x + ddx, yy + ddy
            if 0 <= xx < W and 0 <= y2 < H and not hit[y2, xx] and ov[y2, xx, 3] == 0:
                ov[y2, xx] = OUT

    # rim pixels (top faces whose north neighbour is empty or much lower) for chips
    rim = walltop & ~np.roll(hit, 1, axis=0)
    groups = [(spread_points(wallface, 8, 31, 10), spread_points(walltop, 4, 32, 12), spread_points(rim, 3, 33, 14),
               [24, 71])]
    if level >= 2:
        groups.append((spread_points(wallface, 18, 41, 7)[8:], spread_points(walltop, 10, 42, 8)[4:],
                       spread_points(rim, 8, 43, 9)[3:], [31, 62, 86, 12, 44]))
    n = 0
    for gi, (faces, tops, rims, foot) in enumerate(groups):
        for (x, y) in faces:
            n += 1
            crack(x, y, E.rng(1000 + n).randint(6, 10) + 3 * gi, E.rng(2000 + n), True)
        for (x, y) in tops:
            n += 1
            crack(x, y, E.rng(1000 + n).randint(5, 8), E.rng(2000 + n), False)
        for (x, y) in rims:
            chip(x, y)
        for x in foot:
            rubble_at(x)
    if level >= 2:
        # broken paw crenels (dark tops) and soot scorch on the south faces
        mer = np.argwhere(matmap == MERLON)
        rr = E.rng(55)
        for _ in range(9):
            if not len(mer):
                break
            y, x = mer[rr.randrange(len(mer))]
            for (ddx, ddy) in ((0, 0), (1, 0), (0, 1)):
                if 0 <= x + ddx < W and 0 <= y + ddy < H and hit[y + ddy, x + ddx] and not hm[y + ddy, x + ddx]:
                    ov[y + ddy, x + ddx] = PAL["stone1"]
        for (x0, y0) in spread_points(wallface, 4, 77, 18):
            r = 4.0
            for yy in range(int(y0 - r), int(y0 + r) + 1):
                for xx in range(int(x0 - r), int(x0 + r) + 1):
                    if 0 <= xx < W and 0 <= yy < H and (wallface[yy, xx] or walltop[yy, xx]) and ov[yy, xx, 3] == 0:
                        d = math.hypot(xx - x0, (yy - y0) * 1.3)
                        if d < r and ((xx + yy) % 2 == 0 or d < r * 0.5):
                            ov[yy, xx] = PAL["stone0"] if d < r * 0.5 else PAL["stone1"]
    return ov


# --------------------------------------------------------------------------------------
# Misc sprites
# --------------------------------------------------------------------------------------
SHADOW_W, SHADOW_H = 80, 24
SHADOW_CENTRE = (3.0, 29.0)           # ground offset of the shadow centre from the citadel pivot


def shadow_sprite() -> Tuple[np.ndarray, Tuple[float, float]]:
    img = E.new(SHADOW_W, SHADOW_H)
    yy, xx = np.mgrid[0:SHADOW_H, 0:SHADOW_W]
    nx = (xx + 0.5 - SHADOW_W / 2) / (SHADOW_W / 2)
    ny = (yy + 0.5 - SHADOW_H / 2) / (SHADOW_H / 2)
    d = np.sqrt(nx * nx + ny * ny)
    a = np.where(d < 1, np.clip(1.0 - d, 0, 1) ** 0.6 * 150, 0)
    img[:, :, 0], img[:, :, 1], img[:, :, 2] = PAL["outline"][:3]
    img[:, :, 3] = (np.round(a / 15) * 15).astype(np.uint8)
    cx, cy = SHADOW_CENTRE
    return img, ((SHADOW_W / 2 - cx) / SHADOW_W, (SHADOW_H / 2 + cy) / SHADOW_H)


def slot_glow() -> np.ndarray:
    img = E.new(20, 10)
    yy, xx = np.mgrid[0:10, 0:20]
    nx = (xx + 0.5 - 10) / 10
    ny = (yy + 0.5 - 5) / 5
    d = np.sqrt(nx * nx + ny * ny)
    ringv = np.clip(1 - np.abs(d - 0.8) / 0.22, 0, 1)
    fill = np.clip(1 - d, 0, 1) * 0.4
    a = np.where(d <= 1.0, np.maximum(ringv, fill), 0)
    col = np.array(PAL["cyan3"][:3], float)
    white = np.array(PAL["cyan4"][:3], float)
    mix = ringv[..., None]
    img[:, :, :3] = (col * (1 - mix) + white * mix).astype(np.uint8)
    img[:, :, 3] = np.round(a * 225).astype(np.uint8)
    return img


# --------------------------------------------------------------------------------------
# Anchors
# --------------------------------------------------------------------------------------
def anchors() -> Dict[str, Tuple[float, float]]:
    """Pixel offsets from the pivot, +y up (screen_y = ground_y - height)."""
    gpx, gpy, _ = GATE_PLAT
    bx, by, _ = BASTION
    sx, sy, _ = SPIRE
    return {
        "hero": (DAIS[0], -(DAIS[1] - (1 + DAIS_H))),
        "stormheart": (HEART_POS[0], -(HEART_POS[1] - HEART_Z)),
        "crown": (sx, -(sy - SPIRE_H)),
        "middle": (bx, -(by - (BASTION_H + 1))),
        "base": (gpx, -(gpy - (GATE_H + 1))),
        "gate": (0.0, -((GATE_Y1 - 0.5) - 5.5)),
        "barrier_center": (0.0, 10.0),
    }


# --------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------
def make_all() -> Dict[str, object]:
    base_sc = build_scene("base")
    base, info = render(base_sc)
    paste_heart(base)
    res = {"base": base, "info": info}
    for lv in (1, 2, 3):
        img, _ = render(build_scene(f"r{lv}"))
        paste_heart(img)
        res[f"reinforce{lv}"] = diff_overlay(base, img)
        res[f"reinforced_full{lv}"] = img
    ruin, _ = render(build_scene("ruin"))
    paste_fallen_heart(ruin)
    res["ruin"] = ruin
    res["cracks1"] = crack_overlay(base, info, 1)
    res["cracks2"] = crack_overlay(base, info, 2)
    return res


def build(reg: "E.Registry") -> None:
    res = make_all()
    reg.sprite(ATLAS, "citadel/base", res["base"], pivot=PIVOT, anchors=anchors())
    for nm in ("cracks1", "cracks2", "reinforce1", "reinforce2", "reinforce3", "ruin"):
        reg.sprite(ATLAS, f"citadel/{nm}", res[nm], pivot=PIVOT)
    reg.anim(ATLAS, "citadel/stormheart", stormheart_frames(), fps=6, loop=True, pivot=(0.5, 0.5))
    sh, spv = shadow_sprite()
    reg.sprite(ATLAS, "citadel/shadow", sh, pivot=spv)
    reg.sprite(ATLAS, "citadel/slot_glow", slot_glow(), pivot=(0.5, 0.5))


# --------------------------------------------------------------------------------------
# Iteration previews (not used by the build)
# --------------------------------------------------------------------------------------
def mock_hero() -> np.ndarray:
    """40x40 placeholder silhouette (feet at y=36) used only to judge the dais anchor."""
    img = E.new(40, 40)
    E.ellipse(img, 19.5, 26, 7, 10, PAL["fur1"])
    E.ellipse(img, 19.5, 12, 8, 7, PAL["fur2"])
    E.polygon(img, [(12, 8), (14, 1), (17, 6)], PAL["fur2"])
    E.polygon(img, [(22, 6), (25, 1), (27, 8)], PAL["fur2"])
    E.rect(img, 11, 18, 4, 16, PAL["violet2"])
    E.line(img, 30, 34, 30, 6, PAL["silver1"])
    E.circle(img, 30, 4, 2, PAL["cyan2"])
    img[11, 16:18] = PAL["cyan3"]
    img[11, 21:23] = PAL["cyan3"]
    return E.outline(img)


def mock_station() -> np.ndarray:
    img = E.new(32, 32)
    E.ellipse(img, 15.5, 26, 12, 4.5, PAL["stone2"])
    E.ellipse(img, 15.5, 25, 11, 3.5, PAL["stone3"])
    E.ellipse(img, 13, 16, 5, 6, PAL["tabby1"])
    E.rect(img, 18, 8, 4, 14, PAL["wood2"])
    return E.outline(img)


def compose_with_mocks(base: np.ndarray, pad: int = 32) -> np.ndarray:
    big = E.new(W + 2 * pad, H + 2 * pad)
    E.paste(big, base, pad, pad)
    an = anchors()

    def put(img, pivot, key):
        ax, ay = an[key]
        x = pad + PX + ax - pivot[0] * img.shape[1]
        y = pad + PY - ay - (1 - pivot[1]) * img.shape[0]
        E.paste(big, img, int(round(x)), int(round(y)))
    st = mock_station()
    for key in ("crown", "middle"):
        put(st, (0.5, 0.12), key)
    put(stormheart_frames()[2], (0.5, 0.5), "stormheart")
    put(mock_hero(), (0.5, 0.1), "hero")
    put(st, (0.5, 0.12), "base")
    return big


def preview():
    os.makedirs(ITER_DIR, exist_ok=True)
    res = make_all()
    base = res["base"]
    over = base.copy()
    E.paste(over, res["cracks2"], 0, 0)
    E.preview_images([base, res["reinforced_full3"], over, res["ruin"]],
                     os.path.join(ITER_DIR, "citadel_variants.png"), scale=4)
    E.to_pil(base).save(os.path.join(ITER_DIR, "citadel_base_1x.png"))
    E.preview_images([compose_with_mocks(base)], os.path.join(ITER_DIR, "citadel_mock.png"), scale=4)
    E.preview_images(stormheart_frames() + [slot_glow(), shadow_sprite()[0]],
                     os.path.join(ITER_DIR, "citadel_small.png"), scale=6)
    E.preview_images([res["reinforce1"], res["reinforce2"], res["reinforce3"], res["cracks1"], res["cracks2"]],
                     os.path.join(ITER_DIR, "citadel_overlays.png"), scale=3)


if __name__ == "__main__":
    import time
    t = time.time()
    preview()
    print(f"done in {time.time() - t:.1f}s")
