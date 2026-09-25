"""
gen_stations.py - station modules (atlas "stations"), operator portraits/avatars
(atlas "portraits") and module icons (atlas "icons").

Every station = a small cat operator + their weapon on the same round stone platform.
Tiers change the actual weapon visuals: t2 adds parts + silver trim, t3 adds more parts,
gilded trim and a bigger glow.  The platform rim also carries the tier (plain / silver band
+ rune / gold band + glowing gem).

Run directly for iteration previews:
    python3 Tools/art/gen_stations.py        -> /tmp/claude-0/hero_iter/st_*.png
"""
from __future__ import annotations

import math
import os
import sys
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eclib as E  # noqa: E402
from eclib import PAL, RAMPS  # noqa: E402

Color = Tuple[int, int, int, int]
FW = FH = 32
PIVOT = (0.5, 0.12)
OL = PAL["outline"]
SEED = 7331

MODULES = ["arc_coil", "ember_maw", "frost_whisker", "bone_ballista", "ward_lantern", "gravity_paw"]
FAMILY = {"arc_coil": "cyan", "ember_maw": "fire", "frost_whisker": "frost", "bone_ballista": "bone",
          "ward_lantern": "ward", "gravity_paw": "grav"}

# --------------------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------------------
BASE_LEGEND: Dict[str, Color] = {
    '#': PAL['outline'], 'W': PAL['white'],
    # stone
    's': PAL['stone0'], 't': PAL['stone1'], 'u': PAL['stone2'], 'v': PAL['stone3'], 'w': PAL['stone4'],
    # iron
    'I': PAL['iron0'], 'J': PAL['iron1'], 'K': PAL['iron2'], 'L': PAL['iron3'], 'M': PAL['iron4'],
    # copper / orange
    'o': PAL['orange0'], 'p': PAL['orange1'], 'q': PAL['orange2'], 'r': PAL['orange3'], 'x': PAL['orange4'],
    # silver
    'a': PAL['silver0'], 'b': PAL['silver1'], 'c': PAL['silver2'], 'd': PAL['silver3'],
    # gold
    'g': PAL['gold1'], 'h': PAL['gold2'], 'i': PAL['gold3'], 'j': PAL['gold4'], 'G': PAL['gold0'],
    # cyan
    'k': PAL['cyan1'], 'l': PAL['cyan2'], 'm': PAL['cyan3'], 'n': PAL['cyan4'], 'y': PAL['cyan0'],
    # wood
    '0': PAL['wood0'], '1': PAL['wood1'], '2': PAL['wood2'], '3': PAL['wood3'],
    # fire
    'Q': PAL['fire0'], 'R': PAL['fire1'], 'S': PAL['fire2'], 'T': PAL['fire3'], 'U': PAL['fire4'],
    # frost
    'e': PAL['frost0'], 'f': PAL['frost1'], 'F': PAL['frost2'], 'H': PAL['frost3'], 'z': PAL['frost4'],
    # bone
    '4': PAL['bone0'], '5': PAL['bone1'], '6': PAL['bone2'], '7': PAL['bone3'], '8': PAL['bone4'],
    # ward
    'A': PAL['ward0'], 'B': PAL['ward1'], 'C': PAL['ward2'], 'D': PAL['ward3'], 'V': PAL['ward4'],
    # gravity
    'N': PAL['grav0'], 'O': PAL['grav1'], 'P': PAL['grav2'], 'X': PAL['grav3'], 'Y': PAL['grav4'],
    # leather
    '9': PAL['leather1'], 'Z': PAL['leather2'],
}


def A(rows: Sequence[str], legend: Optional[Dict[str, Color]] = None, **extra) -> np.ndarray:
    L = dict(BASE_LEGEND)
    if legend:
        L.update(legend)
    for k, v in extra.items():
        L[k] = PAL[v] if isinstance(v, str) else v
    return E.ascii_art(rows, L)


def part_ring(a: np.ndarray) -> np.ndarray:
    g = a.copy()
    g[1:, :] |= a[:-1, :]
    g[:-1, :] |= a[1:, :]
    g[:, 1:] |= a[:, :-1]
    g[:, :-1] |= a[:, 1:]
    return g & ~a


def compose(layers, W: int = FW, H: int = FH) -> np.ndarray:
    """layers: (img, x, y, line_colour|None).  Internal separation lines are drawn only where a
    part overlaps something already opaque; the silhouette is outlined afterwards."""
    canvas = E.new(W, H)
    for img, x, y, lc in layers:
        if img is None:
            continue
        full = E.new(W, H)
        E.paste(full, img, int(x), int(y))
        a = full[:, :, 3] > 0
        if lc is not None:
            ring = part_ring(a) & (canvas[:, :, 3] > 0)
            canvas[ring] = lc
        canvas[a] = full[a]
    return canvas


def put(img, x, y, c):
    x, y = int(round(x)), int(round(y))
    if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
        img[y, x] = c


def put_empty(img, x, y, c):
    x, y = int(round(x)), int(round(y))
    if 0 <= x < img.shape[1] and 0 <= y < img.shape[0] and img[y, x, 3] == 0:
        img[y, x] = c


def glow_under(fr: np.ndarray, src: np.ndarray, color: Color, radius: int, strength: float) -> np.ndarray:
    """Soft halo around src's opaque pixels, placed under the frame (FX only)."""
    halo = E.glow(src, color, radius=radius, strength=strength)
    halo[src[:, :, 3] > 0] = 0
    m = fr[:, :, 3] > 0
    halo[m] = fr[m]
    return halo


def mask_img(img: np.ndarray) -> np.ndarray:
    return img[:, :, 3] > 0


def only(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = img.copy()
    out[~mask] = 0
    return out




def tube(pts: Sequence[Tuple[float, float]], r0: float, r1: float, ramp: Sequence[Color],
         W: int = FW, H: int = FH) -> np.ndarray:
    """Shaded tube along a polyline (3-tone: light top-left edge, dark bottom-right edge)."""
    path = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) * 3))
        for i in range(n):
            t = i / n
            path.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    path.append(tuple(pts[-1]))
    mask = np.zeros((H, W), bool)
    n = len(path)
    for i, (x, y) in enumerate(path):
        r = r0 + (r1 - r0) * (i / max(1, n - 1))
        for yy in range(max(0, int(y - r - 2)), min(H, int(y + r + 3))):
            for xx in range(max(0, int(x - r - 2)), min(W, int(x + r + 3))):
                if (xx - x) ** 2 + (yy - y) ** 2 <= (r + 0.15) ** 2:
                    mask[yy, xx] = True
    img = E.new(W, H)
    img[mask] = ramp[1]
    ys, xs = np.nonzero(mask)
    for x, y in zip(xs, ys):
        up = y - 1 < 0 or not mask[y - 1, x]
        lf = x - 1 < 0 or not mask[y, x - 1]
        dn = y + 1 >= H or not mask[y + 1, x]
        rt = x + 1 >= W or not mask[y, x + 1]
        if up or lf:
            img[y, x] = ramp[2]
        elif dn or rt:
            img[y, x] = ramp[0]
    return img


def sphere(img, cx, cy, rx, ry, ramp4: Sequence[Color], cuts=(0.62, 0.2, -0.35)):
    """Banded sphere lit from the top-left (ramp dark -> light, 4 colours)."""
    for y in range(int(cy - ry - 1), int(cy + ry + 2)):
        for x in range(int(cx - rx - 1), int(cx + rx + 2)):
            nx = (x + 0.5 - (cx + 0.5)) / (rx + 0.25)
            ny = (y + 0.5 - (cy + 0.5)) / (ry + 0.25)
            d2 = nx * nx + ny * ny
            if d2 > 1.0 or not (0 <= x < img.shape[1] and 0 <= y < img.shape[0]):
                continue
            nz = math.sqrt(max(0.0, 1 - d2))
            lam = -(nx * -0.6 + ny * -0.75) * 0.75 + nz * 0.5
            k = 3 if lam > cuts[0] else (2 if lam > cuts[1] else (1 if lam > cuts[2] else 0))
            img[y, x] = ramp4[k]


def shear_rows(img: np.ndarray, k: float, pivot_y: float) -> np.ndarray:
    """Shift each row by round(k * (y - pivot_y)) (small swings of hanging parts)."""
    out = E.new(img.shape[1], img.shape[0])
    for y in range(img.shape[0]):
        dx = int(round(k * (y - pivot_y)))
        if dx == 0:
            out[y] = img[y]
        elif dx > 0:
            out[y, dx:] = img[y, :-dx]
        else:
            out[y, :dx] = img[y, -dx:]
    return out


def fx_ring(img, cx, cy, rx, ry, color: Color, alpha: int = 255, gap: int = 0):
    """1px elliptical ring (FX; may be translucent). gap>0 leaves dashes."""
    steps = int(2 * math.pi * max(rx, ry) * 2) + 8
    seen = set()
    for i in range(steps):
        a = 2 * math.pi * i / steps
        x = int(round(cx + math.cos(a) * rx))
        y = int(round(cy + math.sin(a) * ry))
        if (x, y) in seen:
            continue
        seen.add((x, y))
        if gap and (len(seen) // gap) % 2:
            continue
        if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
            c = color[:3] + (alpha,)
            if img[y, x, 3] == 0 or alpha == 255:
                img[y, x] = c


def smoke(img, cx, cy, r, shade=0):
    cols = [PAL['stone3'], PAL['stone4'], PAL['silver0']]
    c = cols[min(2, shade)]
    for y in range(int(cy - r - 1), int(cy + r + 2)):
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r + 0.3 and 0 <= x < FW and 0 <= y < FH and img[y, x, 3] == 0:
                img[y, x] = c[:3] + (210,)
    for y in range(int(cy - r - 1), int(cy + 1)):
        for x in range(int(cx - r - 1), int(cx + 1)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= (r - 0.8) ** 2 and 0 <= x < FW and 0 <= y < FH and img[y, x, 3] == 210:
                img[y, x] = PAL['silver1'][:3] + (220,)

# --------------------------------------------------------------------------------------
# Platform (shared by all stations)
# --------------------------------------------------------------------------------------
PCX, PCY, PRX, PRY, PDEPTH = 15.5, 22.0, 13.5, 4.5, 3


def platform(tier: int, family: str) -> np.ndarray:
    img = E.new(FW, FH)
    ramp = RAMPS[family]
    top = np.zeros((FH, FW), bool)
    face = np.zeros((FH, FW), bool)
    for y in range(FH):
        for x in range(FW):
            nx = (x + 0.5 - (PCX + 0.5)) / (PRX + 0.25)
            ny = (y + 0.5 - (PCY + 0.5)) / (PRY + 0.25)
            if nx * nx + ny * ny <= 1.0:
                top[y, x] = True
            for d in range(1, PDEPTH + 1):
                ny2 = (y - d + 0.5 - (PCY + 0.5)) / (PRY + 0.25)
                if nx * nx + ny2 * ny2 <= 1.0 and y - d >= PCY:
                    face[y, x] = True
    face &= ~top
    # top surface: lit toward the back-left, rim highlight on the back edge
    ys, xs = np.nonzero(top)
    for x, y in zip(xs, ys):
        nx = (x - PCX) / PRX
        ny = (y - PCY) / PRY
        lam = -nx * 0.55 - ny * 0.5
        c = PAL['stone3'] if lam > 0.25 else (PAL['stone2'] if lam > -0.45 else PAL['stone1'])
        img[y, x] = c
    # flagstone joints on the top (a ring + radial lines)
    for y, x in zip(ys, xs):
        nx = (x - PCX) / PRX
        ny = (y - PCY) / PRY
        r = math.hypot(nx, ny)
        if 0.55 < r < 0.66:
            img[y, x] = PAL['stone1'] if img[y, x][0] != PAL['stone1'][0] else PAL['stone0']
    back_rim = top & ~np.roll(top, 1, axis=0)
    img[back_rim] = PAL['stone4']
    # front face: masonry blocks
    ys, xs = np.nonzero(face)
    for x, y in zip(xs, ys):
        u = (x - (PCX - PRX)) / (2 * PRX)
        c = PAL['stone2'] if u < 0.3 else (PAL['stone1'] if u < 0.78 else PAL['stone0'])
        img[y, x] = c
    for x in range(FW):
        col = [y for y in range(FH) if face[y, x]]
        if not col:
            continue
        if (x + (1 if col[0] % 2 else 0)) % 6 == 0:
            for y in col:
                img[y, x] = PAL['stone0']
    # bevel between top and face
    edge = top & np.roll(face, -1, axis=0)
    img[edge] = PAL['stone4'] if tier == 1 else (PAL['silver1'] if tier == 2 else PAL['gold2'])
    if tier >= 2:
        band_hi = PAL['silver2'] if tier == 2 else PAL['gold3']
        ys2, xs2 = np.nonzero(edge)
        for x, y in zip(xs2, ys2):
            if x < PCX - 4:
                img[y, x] = band_hi
        # tier emblem on the front face centre: rune (t2) / glowing gem (t3)
        cx = int(PCX)
        fy = int(PCY + PRY) + 1
        if tier == 2:
            for (dx, dy) in ((0, 0), (-1, 1), (1, 1), (0, 2)):
                put(img, cx + dx, fy + dy, ramp[2])
        else:
            for (dx, dy, k) in ((0, 0, 3), (-1, 1, 2), (0, 1, 4), (1, 1, 2), (0, 2, 1)):
                put(img, cx + dx, fy + dy, ramp[k])
            for (dx, dy) in ((-2, 1), (2, 1)):
                put(img, cx + dx, fy + dy, PAL['gold2'])
            # gold trim along the bottom of the face
            for x in range(FW):
                col = [y for y in range(FH) if face[y, x]]
                if col and (x % 2 == 0):
                    img[col[-1], x] = PAL['gold1']
    return img


def platform_glow(tier: int, family: str) -> Optional[Tuple[np.ndarray, Color]]:
    if tier < 3:
        return None
    g = E.new(FW, FH)
    cx, fy = int(PCX), int(PCY + PRY) + 2
    put(g, cx, fy, RAMPS[family][3])
    return g, RAMPS[family][2]


# --------------------------------------------------------------------------------------
# Tiny operator cats (station scale).  Template roles:
#   L light fur, M mid fur, D dark fur, X darkest, I inner ear, E eye, P pupil/eye-dark,
#   N nose, Y muzzle/chest (light patch), B belly/paws light
# --------------------------------------------------------------------------------------
CATS = {
    # fur ramp (X, D, M, L), eye (E, P), inner ear, nose, light patch Y/B
    "silver_tabby": dict(fur=('tabby0', 'tabby0', 'tabby1', 'tabby2'), eye=('#8fd16a', '#2d4a1c'),
                         ear='pink1', nose='pink1', light='tabby3', stripes='tabby0'),
    "orange_cat": dict(fur=('orange0', 'orange1', 'orange2', 'orange3'), eye=('#ffd24a', '#6b4210'),
                       ear='pink1', nose='pink0', light='orange4', soot=True),
    "white_cat": dict(fur=('snow0', 'snow0', 'snow1', 'snow2'), eye=('#7fcaee', '#1d4d7a'),
                      ear='pink2', nose='pink1', light='snow3', fluffy=True),
    "skeletal_cat": dict(fur=('bone0', 'bone1', 'bone2', 'bone3'), eye=('#140c1c', '#56b89c'),
                         ear='bone1', nose='outline', light='bone4', skull=True),
    "hooded_cat": dict(fur=('fur0', 'fur0', 'fur1', 'fur2'), eye=('#ffd24a', '#fff4c2'),
                       ear='fur1', nose='fur0', light='fur2', hood=True),
    "purple_eyed_cat": dict(fur=('rat0', 'rat0', 'rat1', 'rat2'), eye=('#b07cff', '#e2ccff'),
                            ear='grav1', nose='pink0', light='rat3'),
    "calico_cat": dict(fur=('snow0', 'snow0', 'snow1', 'snow2'), eye=('#8fd16a', '#2d4a1c'),
                       ear='pink1', nose='pink1', light='snow3', calico=True),
}
OPERATOR = {"arc_coil": "silver_tabby", "ember_maw": "orange_cat", "frost_whisker": "white_cat",
            "bone_ballista": "skeletal_cat", "ward_lantern": "hooded_cat", "gravity_paw": "purple_eyed_cat"}


def _c(v) -> Color:
    if isinstance(v, tuple):
        return v
    if v.startswith('#'):
        return E.hexc(v)
    return PAL[v]


def cat_legend(cat: str) -> Dict[str, Color]:
    spec = CATS[cat]
    X, D, M, Lc = (_c(v) for v in spec['fur'])
    return {'X': X, 'D': D, 'M': M, 'L': Lc, 'E': _c(spec['eye'][0]), 'P': _c(spec['eye'][1]),
            'I': _c(spec['ear']), 'N': _c(spec['nose']), 'Y': _c(spec['light']), 'B': _c(spec['light'])}


# --------------------------------------------------------------------------------------
# Weapons
# --------------------------------------------------------------------------------------
def coil_parts(tier: int):
    """Returns the arc coil image (without sparks) and the terminal centre."""
    img = E.new(FW, FH)
    h = {1: 11, 2: 13, 3: 14}[tier]
    base_y = 22
    x0 = 17
    w = 5
    top_y = base_y - h
    # plinth
    plinth = {1: ["JKKKKKJ", "IJJJJJI"], 2: ["bKKKKKb", "IJJJJJI"], 3: ["hiiiiih", "GgggggG"]}[tier]
    # coil windings
    for y in range(top_y, base_y):
        for x in range(x0, x0 + w):
            u = x - x0
            band = (y - top_y) % 2 == 0
            if tier >= 2 and (y - top_y) % 4 == 3:
                c = PAL['silver2'] if u < 2 else PAL['silver0'] if tier == 2 else (PAL['gold3'] if u < 2 else PAL['gold1'])
            elif band:
                c = PAL['orange3'] if u == 0 else (PAL['orange2'] if u < 3 else PAL['orange1'])
            else:
                c = PAL['orange1'] if u < 3 else PAL['orange0']
            img[y, x] = c
    E.paste(img, A(plinth), x0 - 1, base_y)
    # terminal
    if tier == 1:
        term = [".bc.", "bdcb", "abba", ".aa."]
        E.paste(img, A(term), x0 + 1 - 1 + 0, top_y - 4)
        tc = (x0 + 2, top_y - 2)
    elif tier == 2:
        term = [".bcb.", "bdccb", "abbba", ".aaa."]
        E.paste(img, A(term), x0, top_y - 4)
        # side prongs
        for sx, sgn in ((x0 - 3, -1), (x0 + w + 2, 1)):
            for yy in range(base_y - 6, base_y):
                put(img, sx, yy, PAL['silver1'] if yy > base_y - 6 else PAL['silver2'])
            put(img, sx, base_y - 7, PAL['silver3'])
            put(img, sx - sgn, base_y - 1, PAL['iron2'])
        tc = (x0 + 2, top_y - 2)
    else:
        orb = ["..mn..", ".mnnm.", "lmmmml", "llmmlk", ".kllk.", "..kk.."]
        E.paste(img, A(orb), x0 - 0, top_y - 6)
        ring = ["hiiiih"]
        E.paste(img, A(ring), x0 - 0, top_y)
        for sx, sgn in ((x0 - 3, -1), (x0 + w + 2, 1)):
            for yy in range(base_y - 8, base_y):
                put(img, sx, yy, PAL['gold2'] if yy % 3 else PAL['gold3'])
            put(img, sx, base_y - 9, PAL['cyan3'])
            put(img, sx - sgn, base_y - 1, PAL['gold1'])
        tc = (x0 + 2.5, top_y - 3)
    return img, tc


def spark_zig(img, x0, y0, x1, y1, rnd, cols=None):
    cols = cols or (PAL['cyan3'], PAL['cyan2'], PAL['white'])
    n = max(2, int(max(abs(x1 - x0), abs(y1 - y0))))
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        if 0 < i < n:
            if abs(y1 - y0) >= abs(x1 - x0):
                x += rnd.choice((-1, 0, 1))
            else:
                y += rnd.choice((-1, 0, 1))
        put(img, x, y, cols[i % len(cols)])


def burst(img, cx, cy, r, ramp=None, diag=True):
    ramp = ramp or [PAL['white'], PAL['cyan4'], PAL['cyan3'], PAL['cyan2'], PAL['cyan1']]
    cx, cy = int(round(cx)), int(round(cy))
    for s in (1, -1):
        for i in range(1, r + 1):
            put(img, cx + s * i, cy, ramp[min(len(ramp) - 1, i - 1)])
            put(img, cx, cy + s * i, ramp[min(len(ramp) - 1, i - 1)])
        if diag:
            for t in (1, -1):
                for i in range(1, max(1, r - 1)):
                    put(img, cx + s * i, cy + t * i, ramp[min(len(ramp) - 1, i)])
    put(img, cx, cy, ramp[0])


def station_arc_coil(tier: int, clip: str, f: int) -> np.ndarray:
    rnd = E.rng(SEED + tier * 101 + f * 7 + (0 if clip == "idle" else 50))
    plat = platform(tier, "cyan")
    coil, (tx, ty) = coil_parts(tier)
    op = tiny_operator("silver_tabby", "blink" if clip == "idle" and f == 3 else ("reach" if clip == "fire" and f == 0 else ("look" if clip == "fire" and f in (1, 2) else "idle")))
    fr = compose([(plat, 0, 0, None), (coil, 0, 0, OL), (op, 0, 11, OL)])
    fr = E.outline(fr)
    # sparks / discharge
    fx = E.new(FW, FH)
    if clip == "idle":
        n = [1, 2, 1, 2][f] + (tier - 1)
        for _ in range(n):
            a = rnd.uniform(0, 2 * math.pi)
            r0, r1 = 2.5, 4.5 + tier * 0.5
            spark_zig(fx, tx + math.cos(a) * r0, ty + math.sin(a) * r0 * 0.8,
                      tx + math.cos(a) * r1, ty + math.sin(a) * r1 * 0.8, rnd)
    else:
        if f == 0:
            for _ in range(2 + tier):
                a = rnd.uniform(0, 2 * math.pi)
                spark_zig(fx, tx + math.cos(a) * 2.5, ty + math.sin(a) * 2, tx + math.cos(a) * 5, ty + math.sin(a) * 4, rnd)
        elif f == 1:
            burst(fx, tx, ty, 5 + tier)
            spark_zig(fx, tx, ty - 2, tx + 6, 0, rnd)
        elif f == 2:
            burst(fx, tx, ty, 3 + tier)
            for _ in range(3 + tier):
                a = rnd.uniform(0, 2 * math.pi)
                spark_zig(fx, tx + math.cos(a) * 3, ty + math.sin(a) * 2.5, tx + math.cos(a) * 7, ty + math.sin(a) * 6, rnd)
        elif f == 3:
            for _ in range(2):
                a = rnd.uniform(0, 2 * math.pi)
                spark_zig(fx, tx + math.cos(a) * 2.5, ty + math.sin(a) * 2, tx + math.cos(a) * 5, ty + math.sin(a) * 4, rnd,
                          cols=(PAL['cyan2'], PAL['cyan1']))
    m = mask_img(fx)
    fr[m] = fx[m]
    # glow around the terminal
    src = E.new(FW, FH)
    put(src, tx, ty, PAL['cyan3'])
    strength = 0.35 + 0.15 * tier
    if clip == "fire" and f in (1, 2):
        strength = 0.9
    fr = glow_under(fr, src, PAL['cyan2'], 3 + (1 if clip == "fire" and f == 1 else 0), strength)
    return fr


# --------------------------------------------------------------------------------------
# Tiny operator cats (station scale), facing right in 3/4 view.
# Template roles: L light fur, M mid, D dark, I inner ear, E eye, P eye detail, N nose,
# Y light patch (muzzle/chest), B paws.  Per-cat overlays add markings and accessories.
# --------------------------------------------------------------------------------------
OP_HEAD = [
    ".L......D.",
    "LIL....DID",
    "LLLMMMMMDD",
    "LMMMMMMMMD",
    "LMEPMMEPMD",
    "LMMMYNYMMD",
    ".MMYYYYYD.",
    "..DMMMMD..",
]
OP_BODY = [
    "..LMMMMD..",
    ".LMYYYMMD.",
    ".LMYYYMMD.",
    ".LMMMMMDD.",
    ".BB.MD.BB.",
]
SKULL_HEAD = [
    ".7......6.",
    "757....656",
    "7888888876",
    "7888888876",
    "78##88##76",
    "78#D88D#76",
    ".7888#8876",
    "..8W8W876.",
]
SKULL_BODY = [
    "...6776...",
    "..7#7#76..",
    "..7#7#76..",
    "...5665...",
    ".77.66.76.",
]
HOOD = [   # overlay for the hooded cat: hood cloth with ear bumps, face in shadow
    ".B......A.",
    "BCB....ABA",
    "BCCBBBBBAA",
    "CBB111111A",
    "CB1......A",
    "CB1......A",
    ".B1......A",
    "..........",
]
HOOD_BODY = [
    "..CBBBBA..",
    ".CBBBBBBA.",
    ".CBBhBBBA.",
    ".CBBBBBAA.",
    ".BB.BA.BB.",
]

CAT_OVERLAYS = {
    "silver_tabby": [
        "..........",
        ".9......9.",
        "9hyX.Xhy99",
        ".hnMXMhn..",
        "..........",
        "X........X",
        "..........",
        "..........",
    ],
    "orange_cat": [
        "..........",
        "..........",
        "..........",
        ".......k..",
        "..........",
        "..k.......",
        "......k...",
        "..........",
    ],
    "white_cat": [
        "..........",
        "..........",
        "..........",
        "..........",
        "..........",
        "L........D",
        "L........D",
        ".L......D.",
    ],
    "purple_eyed_cat": [
        "..........",
        "..........",
        ".....X....",
        "..........",
        "..........",
        "..........",
        "..........",
        "..........",
    ],
}


def _overlay(rows: List[str], over: Optional[List[str]]) -> List[str]:
    if not over:
        return rows
    out = []
    for r, o in zip(rows, over):
        out.append("".join(oc if oc != '.' else rc for rc, oc in zip(r, o)))
    return out


def tiny_operator(cat: str, pose: str = "idle") -> np.ndarray:
    """~10x13 standing operator. pose: idle | blink | reach (arm out) | cheer (arm up) | look."""
    spec = CATS[cat]
    L = {**BASE_LEGEND, **cat_legend(cat), 'k': (52, 44, 46, 255)}
    if spec.get("skull"):
        head_rows, body_rows = list(SKULL_HEAD), list(SKULL_BODY)
    elif spec.get("hood"):
        head_rows = _overlay(list(OP_HEAD), HOOD)
        body_rows = list(HOOD_BODY)
    else:
        head_rows = _overlay(list(OP_HEAD), CAT_OVERLAYS.get(cat))
        body_rows = list(OP_BODY)
    if pose == "blink":
        head_rows = [r.replace('E', 'D').replace('P', 'D') if i in (4, 5) and not spec.get("skull") else r
                     for i, r in enumerate(head_rows)]
    head = E.ascii_art(head_rows, L)
    body = E.ascii_art(body_rows, L)
    img = E.new(13, 15)
    layers = [(body, 1, 9, OL), (head, 1, 1 if pose != "look" else 0, OL)]
    arm_col = L['M'] if not spec.get("hood") else L['B']
    paw_col = L['B'] if not spec.get("hood") else L['M']
    if spec.get("skull"):
        arm_col, paw_col = L['6'], L['8']
    if pose in ("reach", "cheer"):
        arm = E.new(13, 15)
        if pose == "reach":
            for (x, y) in ((9, 10), (10, 10), (10, 9)):
                arm[y, x] = arm_col
            arm[9, 11] = paw_col
            arm[8, 11] = paw_col
        else:
            for (x, y) in ((9, 9), (10, 8), (10, 7)):
                arm[y, x] = arm_col
            arm[6, 11] = paw_col
            arm[6, 10] = paw_col
        layers.append((arm, 0, 0, OL))
    return compose(layers, 13, 15)


def finish(layers, fx: Optional[np.ndarray] = None, glows: Sequence[Tuple[np.ndarray, Color, int, float]] = ()) -> np.ndarray:
    fr = compose(layers)
    fr = E.outline(fr)
    if fx is not None:
        m = mask_img(fx)
        fr[m] = fx[m]
    for src, col, rad, st in glows:
        fr = glow_under(fr, src, col, rad, st)
    return fr


def dot_src(points, W: int = FW, H: int = FH) -> np.ndarray:
    g = E.new(W, H)
    for x, y in points:
        put(g, x, y, PAL['white'])
    return g


# --------------------------------------------------------------------------------------
# EMBER MAW - iron furnace cannon, the muzzle is a cat face with a glowing mouth
# --------------------------------------------------------------------------------------
MAW_HEAD = {
    1: [
        "..J.........J..",
        ".JKJ.......JKJ.",
        ".JLKJ.....JKLJ.",
        ".JLLKJJJJJKLKJ.",
        "JLLKKKKKKKKKKKJ",
        "LLKSSKKKKKSSKKJ",
        "LLKKRSKKKSRKKKJ",
        "LKKKKKKKKKKKKKJ",
        "LKKRRRRRRRRRKKJ",
        "LKRWTTTTTTTWRKJ",
        "LKRTUUUUUUUTRKJ",
        "JKKRTUUUUUTRKKJ",
        ".JKKRWSSSWRKKJ.",
        "..JKKKKKKKKKJ..",
        "...JJJJJJJJJ...",
    ],
    2: [
        "..h.........h..",
        ".hKh.......hKh.",
        ".JLKJ.....JKLJ.",
        ".JLLKJJJJJKLKJ.",
        "JLLKKKKKKKKKKKJ",
        "LLKSSKKKKKSSKKJ",
        "LMKKRSKKKSRKKKJ",
        "hhhhhhhhhhhhhhg",
        "LKKRRRRRRRRRKKJ",
        "LKRWTTTTTTTWRKJ",
        "LMRTUUUUUUUTRMJ",
        "JKKRTUUUUUTRKKJ",
        ".JKKRWSSSWRKKJ.",
        "..JhhhhhhhhgJ..",
        "...JJJJJJJJJ...",
    ],
    3: [
        "..j.........i..",
        ".jih.......ihg.",
        ".hiih.....hiihg",
        ".hiiihhhhhiiihg",
        "hiiiiiiiiiiiihg",
        "iiiUUiiiiiUUihg",
        "iiiiTUiiiUTiihg",
        "iihhhhhhhhhhhhg",
        "iihRRRRRRRRRhhg",
        "ihRWTTTTTTTWRhg",
        "ihRTUUUUUUUTRhg",
        "hhhRTUUUUUTRhhg",
        ".hhhRWSSSWRhhg.",
        "..hhhhhhhhhhg..",
        "...gggggggggg..",
    ],
}


def station_ember_maw(tier: int, clip: str, f: int) -> np.ndarray:
    """The furnace IS the cannon: an iron cat head whose open mouth is the glowing muzzle."""
    rnd = E.rng(SEED + 211 + tier * 101 + f * 7 + (0 if clip == "idle" else 50))
    plat = platform(tier, "fire")
    recoil = {1: 2, 2: 1}.get(f, 0) if clip == "fire" else 0
    hx, hy = 14 - recoil, 6 - (1 if recoil == 2 else 0)
    head = A(MAW_HEAD[tier])
    hot = (clip == "fire" and f in (0, 1)) or (clip == "idle" and f in (1, 2))
    if hot:
        head = E.recolor(head, {PAL['fire1']: PAL['fire2'], PAL['fire2']: PAL['fire3'], PAL['fire3']: PAL['fire4']})
    elif clip == "fire" and f == 3:
        head = E.recolor(head, {PAL['fire4']: PAL['fire3'], PAL['fire3']: PAL['fire2']})
    # squat iron base / carriage
    base = E.new(FW, FH)
    bc = {1: PAL['iron1'], 2: PAL['iron1'], 3: PAL['gold1']}[tier]
    for x in range(15, 27):
        put(base, x, 20, PAL['iron2'] if x < 21 else PAL['iron1'])
        put(base, x, 21, bc if x % 3 else PAL['iron0'])
    for (x, y) in ((15, 22), (16, 22), (25, 22), (26, 22)):
        put(base, x, y, PAL['iron1'])
    layers = [(plat, 0, 0, None), (base, 0, 0, OL)]
    # chimney (t2+) behind the head
    if tier >= 2:
        ch = A(["LKJ", "JKI", "JKI", "JKI"]) if tier == 2 else A(["iih", "hig", "hig", "hig", "hig"])
        layers.append((ch, 15 - recoil, 1 if tier == 3 else 2, OL))
        if tier == 3:
            layers.append((A(["hg", "hg", "hg"]), 24 - recoil, 3, OL))
    layers.append((head, hx, hy, OL))
    op = tiny_operator("orange_cat", "reach" if clip == "fire" and f == 0 else ("blink" if clip == "idle" and f == 3 else "idle"))
    layers.append((op, 0, 11, OL))
    fx = E.new(FW, FH)
    glows = []
    mouth = (hx + 7, hy + 9)
    if clip == "fire" and f in (1, 2, 3):
        r = {1: 5.0, 2: 3.8, 3: 2.2}[f]
        cols = [PAL['fire4'], PAL['fire3'], PAL['fire2'], PAL['fire1']]
        cx, cy = mouth[0] + 1, mouth[1] + r * 0.55
        for y in range(FH):
            for x in range(FW):
                d = math.hypot((x - cx) / 1.25, (y - cy) / 0.9)
                if d <= r:
                    k = 0 if d < r * 0.35 else (1 if d < r * 0.6 else (2 if d < r * 0.85 else 3))
                    if f == 3:
                        k = min(3, k + 2)
                    if f == 1 or fx[y, x, 3] == 0:
                        fx[y, x] = cols[k]
        for _ in range(3 + 2 * (f == 1)):
            a = rnd.uniform(0.2, math.pi - 0.2)
            d = r + rnd.uniform(0.5, 2.5)
            put_empty(fx, cx + math.cos(a) * d * 1.3, cy + math.sin(a) * d * 0.7, PAL['fire3'])
        if f >= 2:
            smoke(fx, mouth[0] + 6, mouth[1] - 3, 1.6, 1)
            smoke(fx, mouth[0] - 5, mouth[1] - 2, 1.2, 0)
        glows.append((dot_src([(cx, cy)]), PAL['fire2'], 4, 0.65))
    if tier >= 2:
        ph = f if clip == "idle" else f + 1
        smoke(fx, 16 - recoil + (ph % 2), 0 + (ph % 2) if tier == 3 else 1 - (ph % 2) + 1, 1.2 + 0.4 * (ph % 2), 0)
        if tier == 3:
            put_empty(fx, 25 - recoil, 1 - (ph % 2) + 1, PAL['fire3'])
            put_empty(fx, 26 - recoil + ph % 2, 0 + (ph % 2), PAL['fire2'])
    glows.append((dot_src([mouth]), PAL['fire2'], 2 + (tier > 1), 0.3 + 0.1 * tier + (0.15 if hot else 0)))
    return finish(layers, fx, glows)


# --------------------------------------------------------------------------------------
# FROST WHISKER - hanging ice bell in a frosted frame
# --------------------------------------------------------------------------------------
BELL = {
    1: [
        "...fF...",
        "..fHHF..",
        ".fHzHFe.",
        ".fHHFFe.",
        ".fHHFFe.",
        "fFHHFFee",
        "effffeee",
        "...ee...",
    ],
    2: [
        "....FH....",
        "...fHzF...",
        "..fHzHHF..",
        "..fHHHFFe.",
        "..fHzHFFe.",
        ".fHHzFFFe.",
        ".fHHHFFFee",
        "fFHHHFFeee",
        "effffffeee",
        "....ee....",
    ],
    3: [
        "....zH....",
        "...Hzzf...",
        "..fzzzHF..",
        "..fHzHHFe.",
        "..fzzzHFe.",
        ".fHzHzFFe.",
        ".fHHzHFFe.",
        "fHzHHHFFee",
        "ezzzzzzzze",
        "....HH....",
    ],
}


def station_frost_whisker(tier: int, clip: str, f: int) -> np.ndarray:
    rnd = E.rng(SEED + 311 + tier * 101 + f * 7 + (0 if clip == "idle" else 50))
    plat = platform(tier, "frost")
    wood = {1: (PAL['wood1'], PAL['wood2'], PAL['wood3']), 2: (PAL['iron1'], PAL['iron2'], PAL['silver1']),
            3: (PAL['gold0'], PAL['gold1'], PAL['gold3'])}[tier]
    frame = E.new(FW, FH)
    lx, rxp, top = 12, 28, 5
    for x in (lx, rxp):
        for y in range(top, 23):
            put(frame, x, y, wood[1])
            put(frame, x + 1, y, wood[0])
        put(frame, x, top, wood[2])
    for x in range(lx - 1, rxp + 3):
        put(frame, x, top, wood[2] if x < 20 else wood[1])
        put(frame, x, top + 1, wood[1] if x < 20 else wood[0])
    # snow cap + icicles
    for x in range(lx - 1, rxp + 3):
        put(frame, x, top - 1, PAL['snow2'] if x % 3 else PAL['snow3'])
    icicles = [(lx + 2, 2), (lx + 5, 1), (rxp - 2, 2), (rxp - 5, 1)] if tier >= 2 else [(lx + 3, 1), (rxp - 3, 1)]
    for x, ln in icicles:
        for k in range(ln):
            put(frame, x, top + 2 + k, PAL['frost3'] if k == 0 else PAL['frost2'])
    if tier == 3:
        for x in (lx, rxp):
            put(frame, x, top - 2, PAL['frost4'])
            put(frame, x, top - 3, PAL['frost3'])
    # bell (swings in fire)
    bell = A(BELL[tier])
    bw, bh = bell.shape[1], bell.shape[0]
    swing = 0.0
    if clip == "idle":
        swing = [0.0, 0.12, 0.0, -0.12][f]
    else:
        swing = [-0.35, 0.45, 0.25, -0.15, 0.0][f]
    bimg = E.new(FW, FH)
    bx = 20 - bw // 2 + 1
    by = top + 3
    E.paste(bimg, bell, bx, by)
    # hanger
    put(bimg, 20, top + 2, PAL['iron2'])
    bimg = shear_rows(bimg, -swing, top + 2)
    layers = [(plat, 0, 0, None), (frame, 0, 0, OL), (bimg, 0, 0, OL)]
    # rope from the beam to the operator paw
    rope = E.new(FW, FH)
    pulling = clip == "fire" and f in (0, 1)
    E.line(rope, lx - 1, top + 2, 10, 17 if pulling else 15, PAL['wood3'])
    layers.append((rope, 0, 0, None))
    op = tiny_operator("white_cat", "reach" if pulling else ("blink" if clip == "idle" and f == 1 else "idle"))
    layers.append((op, 0, 11, OL))
    fx = E.new(FW, FH)
    mouth = (20 + int(round(swing * (bh + 1))), by + bh)
    if clip == "fire" and f in (1, 2, 3):
        r = {1: 3, 2: 5, 3: 7}[f]
        fx_ring(fx, mouth[0], mouth[1] - 1, r, r * 0.6, PAL['frost3'], 255 if f < 3 else 170, gap=0 if f == 1 else 2)
        for _ in range(4 + tier * 2):
            a = rnd.uniform(0, 2 * math.pi)
            d = rnd.uniform(1, r + 1)
            put_empty(fx, mouth[0] + math.cos(a) * d, mouth[1] - 1 + math.sin(a) * d * 0.6,
                      PAL['frost4'] if rnd.random() < 0.5 else PAL['snow2'])
    else:
        # twinkles
        for k in range(tier):
            x = rnd.randint(12, 29)
            y = rnd.randint(3, 16)
            put_empty(fx, x, y, PAL['frost4'])
    glows = [(dot_src([(20, by + bh // 2)]), PAL['frost3'], 2 + tier // 2, 0.2 + 0.12 * tier)]
    return finish(layers, fx, glows)


# --------------------------------------------------------------------------------------
# BONE BALLISTA - bone crossbow on a post
# --------------------------------------------------------------------------------------
def _bow(img, bxp, cy, span, flex, trim, knob):
    for k in range(-span, span + 1):
        bend = int(round((k * k) / (span * 1.35)))
        cx = bxp - bend + (flex if abs(k) > span - 3 else 0)
        put(img, cx, cy + k, PAL['bone3'] if k < 0 else PAL['bone2'])
        put(img, cx + 1, cy + k, PAL['bone1'] if k < span - 1 else PAL['bone0'])
    tip = bxp - int(round(span / 1.35)) + flex
    for ty in (cy - span, cy + span):
        put(img, tip - 1, ty, knob)
        put(img, tip, ty, knob)
        put(img, tip - 1, ty + (1 if ty > cy else -1), knob)
    # centre binding
    put(img, bxp, cy - 1, trim)
    put(img, bxp, cy + 1, trim)
    put(img, bxp + 1, cy - 1, trim)
    put(img, bxp + 1, cy + 1, trim)
    return (tip, cy - span), (tip, cy + span)


def station_bone_ballista(tier: int, clip: str, f: int) -> np.ndarray:
    rnd = E.rng(SEED + 411 + tier * 101 + f * 7 + (0 if clip == "idle" else 50))
    plat = platform(tier, "bone")
    kick = {1: 1, 2: 1}.get(f, 0) if clip == "fire" else 0
    ox = -kick
    trim = {1: PAL['bone1'], 2: PAL['iron3'], 3: PAL['gold2']}[tier]
    knob = {1: PAL['bone4'], 2: PAL['bone4'], 3: PAL['gold3']}[tier]
    cy = 12
    stand = E.new(FW, FH)
    # vertebra post + tripod feet
    for y in range(cy + 1, 23):
        put(stand, 18, y, PAL['bone3'] if y % 2 else PAL['bone2'])
        put(stand, 19, y, PAL['bone2'] if y % 2 else PAL['bone1'])
    for (x, y) in ((16, 22), (17, 21), (20, 21), (21, 22), (15, 22), (22, 22)):
        put(stand, x, y, PAL['bone2'])
    if tier >= 2:
        for y in (15, 19):
            put(stand, 18, y, trim)
            put(stand, 19, y, trim)
    # stock (spine) pointing right
    stock = E.new(FW, FH)
    for x in range(10, 27):
        put(stock, x + ox, cy, PAL['bone3'] if x % 2 else PAL['bone2'])
        put(stock, x + ox, cy + 1, PAL['bone1'] if x % 2 else PAL['bone0'])
    for x in range(11, 26, 2):
        put(stock, x + ox, cy - 1, PAL['bone2'])
    # bow(s)
    bow = E.new(FW, FH)
    span = {1: 7, 2: 8, 3: 9}[tier]
    flex = 1 if (clip == "fire" and f == 1) else 0
    tip_t, tip_b = _bow(bow, 23 + ox, cy, span, flex, trim, knob)
    if tier >= 2:
        _bow(bow, 20 + ox, cy, span - 3, flex, trim, knob)
    snapped = clip == "fire" and f in (1, 2)
    drawn = (13 if not (clip == "fire" and f == 0) else 12) + ox
    nock_x = tip_t[0] + 1 if snapped else drawn
    string = E.new(FW, FH)
    E.line(string, tip_t[0], tip_t[1] + 1, nock_x, cy, PAL['bone4'])
    E.line(string, tip_b[0], tip_b[1] - 1, nock_x, cy, PAL['bone4'])
    layers = [(plat, 0, 0, None), (stand, 0, 0, OL), (string, 0, 0, None), (stock, 0, 0, OL), (bow, 0, 0, OL)]
    has_bolt = not (clip == "fire" and f in (1, 2))
    if has_bolt:
        bolt = E.new(FW, FH)
        start = drawn if not (clip == "fire" and f == 3) else drawn + 5
        for x in range(start, 28 + ox):
            put(bolt, x, cy - 1, PAL['bone3'] if x % 2 else PAL['bone2'])
        tipc = PAL['bone4'] if tier < 3 else PAL['gold3']
        for (dx, dy) in ((0, 0), (1, 0), (0, -1), (0, 1)):
            put(bolt, 28 + ox + dx, cy - 1 + dy, tipc)
        put(bolt, 30 + ox, cy - 1, tipc)
        put(bolt, start, cy - 2, PAL['bone1'])
        put(bolt, start + 1, cy - 2, PAL['bone2'])
        layers.append((bolt, 0, 0, OL))
    if tier == 3:
        # small cat skull emblem on the stock front
        layers.append((A(["5.5", "777", "#7#", ".7."]), 24 + ox, cy + 2, OL))
    op_pose = "reach" if clip == "fire" and f == 0 else ("look" if clip == "idle" and f == 2 else "idle")
    op = tiny_operator("skeletal_cat", op_pose)
    layers.append((op, 0, 11, OL))
    fx = E.new(FW, FH)
    if clip == "fire" and f in (1, 2):
        for x in range(25 if f == 1 else 28, 32):
            put_empty(fx, x, cy - 1, PAL['bone4'] if x % 2 else PAL['white'])
        if f == 1:
            for x in range(21, 31, 2):
                put_empty(fx, x, cy - 3, PAL['bone3'])
                put_empty(fx, x + 1, cy + 2, PAL['bone3'])
    elif clip == "idle" and f == 1:
        put_empty(fx, 30 + ox, cy - 3, PAL['bone4'])
        put_empty(fx, 31 + ox, cy - 2, PAL['bone3'])
    glows = []
    if tier == 3:
        glows.append((dot_src([(29 + ox, cy - 1)]), PAL['gold3'], 2, 0.3))
    return finish(layers, fx, glows)


# --------------------------------------------------------------------------------------
# WARD LANTERN - tall lantern on a pole, warm gold-teal light
# --------------------------------------------------------------------------------------
LANTERN = {
    1: [
        "...J...",
        "..JKJ..",
        ".JLKKJ.",
        "JKKKKKJ",
        "KDViVDK",
        "KDijiDK",
        "KDijiDK",
        "KDViVDK",
        "JKKKKKJ",
        "..JKJ..",
    ],
    2: [
        "...h...",
        "..hih..",
        ".JLKKJ.",
        "hhhhhhg",
        "KDViVDK",
        "KViji VK".replace(" ", "V"),
        "KDijiDK",
        "KDijiDK",
        "KDViVDK",
        "hhhhhhg",
        ".JKKKJ.",
        "...K...",
    ],
    3: [
        "...j...",
        "..jih..",
        ".hiiih.",
        "hiiiiig",
        "iDVjVDg",
        "iVjWjVg",
        "iDjWjDg",
        "iDjWjDg",
        "iVjjjVg",
        "hiiiiig",
        ".hiiig.",
        "..hig..",
        "...g...",
    ],
}


def station_ward_lantern(tier: int, clip: str, f: int) -> np.ndarray:
    rnd = E.rng(SEED + 511 + tier * 101 + f * 7 + (0 if clip == "idle" else 50))
    plat = platform(tier, "ward")
    pole_cols = {1: (PAL['wood1'], PAL['wood2'], PAL['wood3']), 2: (PAL['iron1'], PAL['iron2'], PAL['iron3']),
                 3: (PAL['gold0'], PAL['gold1'], PAL['gold3'])}[tier]
    pole = E.new(FW, FH)
    px_, top = 16, 2
    for y in range(top, 23):
        put(pole, px_, y, pole_cols[2] if y % 5 else pole_cols[1])
        put(pole, px_ + 1, y, pole_cols[0])
    for x in range(px_, px_ + 9):
        put(pole, x, top, pole_cols[2])
        put(pole, x, top + 1, pole_cols[0] if x > px_ + 1 else pole_cols[1])
    put(pole, px_ + 8, top + 2, pole_cols[1])
    # brace + feet
    put(pole, px_ + 2, top + 2, pole_cols[1])
    put(pole, px_ + 3, top + 3, pole_cols[1])
    for (x, y) in ((px_ - 1, 22), (px_ - 2, 22), (px_ + 2, 22), (px_ + 3, 22)):
        put(pole, x, y, pole_cols[1])
    if tier >= 2:
        put(pole, px_, top - 1, pole_cols[2])
        put(pole, px_ + 1, top - 1, pole_cols[1])
    if tier == 3:
        put(pole, px_, top - 2, PAL['ward3'])
    lant = A(LANTERN[tier])
    sway = [0, 0, 1, 0][f] if clip == "idle" else [0, -1, 0, 0, 0][f]
    lx = px_ + 8 - lant.shape[1] // 2 + sway
    ly = top + 3
    flare = clip == "fire" and f in (1, 2)
    if flare:
        lant = E.recolor(lant, {PAL['ward3']: PAL['ward4'], PAL['ward4']: PAL['white'], PAL['gold3']: PAL['gold4'],
                                PAL['gold4']: PAL['white']})
    elif clip == "idle" and f % 2:
        lant = E.recolor(lant, {PAL['gold3']: PAL['gold4']})
    layers = [(plat, 0, 0, None), (pole, 0, 0, OL), (lant, lx, ly, OL)]
    op = tiny_operator("hooded_cat", "cheer" if clip == "fire" and f in (0, 1) else "idle")
    layers.append((op, 0, 11, OL))
    fx = E.new(FW, FH)
    cx, cy = lx + lant.shape[1] // 2, ly + lant.shape[0] // 2
    if clip == "fire" and f in (1, 2, 3):
        r = {1: 6, 2: 9, 3: 12}[f]
        fx_ring(fx, cx, cy, r, r * 0.8, PAL['ward3'], 255 if f == 1 else (200 if f == 2 else 120), gap=0 if f < 3 else 2)
        if f == 1:
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                for i in range(5, 8):
                    put_empty(fx, cx + dx * i, cy + dy * i, PAL['ward4'])
    if tier == 3:
        for k in range(3):
            a = ((f / 4.0) if clip == "idle" else (f / 5.0)) * 2 * math.pi + k * 2 * math.pi / 3
            put_empty(fx, cx + math.cos(a) * 7, cy + math.sin(a) * 5, PAL['ward3'])
            put_empty(fx, cx + math.cos(a) * 7, cy + math.sin(a) * 5 - 1, PAL['ward4'])
    strength = 0.35 + 0.12 * tier + (0.35 if flare else 0.0) + (0.06 if clip == "idle" and f % 2 else 0)
    glows = [(dot_src([(cx, cy)]), PAL['ward4'], 3 + (1 if flare or tier == 3 else 0), min(0.95, strength)),
             (dot_src([(cx, cy)]), PAL['ward2'], 4 + (1 if flare else 0), 0.25)]
    return finish(layers, fx, glows)


# --------------------------------------------------------------------------------------
# GRAVITY PAW - floating rune orb in a paw-shaped cradle
# --------------------------------------------------------------------------------------
PAW_CRADLE = {
    1: [
        "w.......t",
        "vw.....ut",
        ".vw...ut.",
        ".vvwuuvt.",
        "..vvvvt..",
        "..vXvXt..",
        "..XvvvX..",
        "..vXXXt..",
        "..vXXXt..",
        ".uvvvvtt.",
    ],
    2: [
        "c.......b",
        "cb.....ab",
        ".cb...ab.",
        ".cvwuuab.",
        "..vvvvt..",
        "..vXvXt..",
        "..XvvvX..",
        "..vXYXt..",
        "..vXXXt..",
        ".bbcbbba.",
    ],
    3: [
        "j.......h",
        "ji.....hg",
        ".ji...hg.",
        ".jiiiihg.",
        "..hiiig..",
        "..hYvYg..",
        "..YvvvY..",
        "..hYYYg..",
        "..hYYYg..",
        ".hijiigg.",
    ],
}


def station_gravity_paw(tier: int, clip: str, f: int) -> np.ndarray:
    rnd = E.rng(SEED + 611 + tier * 101 + f * 7 + (0 if clip == "idle" else 50))
    plat = platform(tier, "grav")
    cradle = A(PAW_CRADLE[tier])
    cxp = 20
    layers = [(plat, 0, 0, None), (cradle, cxp - 4, 13, OL)]
    orb = E.new(FW, FH)
    bob = [0, -1, -1, 0][f] if clip == "idle" else [1, -1, -1, 0, 0][f]
    r = {1: 3.0, 2: 3.5, 3: 4.2}[tier]
    if clip == "fire" and f == 0:
        r -= 0.8
    if clip == "fire" and f == 1:
        r += 0.8
    oy = 9 + bob
    sphere(orb, cxp, oy, r, r, [PAL['grav0'], PAL['grav1'], PAL['grav2'], PAL['grav3']])
    # runes on the orb
    for (dx, dy) in ((0, 0), (-1, 1), (1, 1)) if tier == 1 else ((0, -1), (0, 0), (-1, 1), (1, 1), (0, 2)):
        put(orb, cxp + dx, oy + dy, PAL['grav4'])
    put(orb, cxp - 1, oy - int(r) + 1, PAL['white'])
    layers.append((orb, 0, 0, OL))
    op = tiny_operator("purple_eyed_cat", "cheer" if clip == "fire" and f in (0, 1) else ("blink" if clip == "idle" and f == 2 else "idle"))
    layers.append((op, 0, 11, OL))
    fx = E.new(FW, FH)
    if tier >= 2:
        fx_ring(fx, cxp, oy, r + 2.5, (r + 2.5) * 0.35, PAL['grav3'], 200, gap=2)
    if tier == 3:
        for k in range(2):
            a = (f / (4.0 if clip == "idle" else 5.0) + k / 2.0) * 2 * math.pi
            put(fx, cxp + math.cos(a) * 7, oy + math.sin(a) * 2.5, PAL['stone4'])
            put(fx, cxp + math.cos(a) * 7 + 1, oy + math.sin(a) * 2.5, PAL['stone3'])
    if clip == "fire" and f in (1, 2, 3):
        rr = {1: 6, 2: 9, 3: 12}[f]
        fx_ring(fx, cxp, oy, rr, rr * 0.75, PAL['grav3'], 255 if f == 1 else (190 if f == 2 else 110), gap=0 if f == 1 else 2)
        if f == 1:
            fx_ring(fx, cxp, oy, rr - 2, (rr - 2) * 0.75, PAL['grav4'], 220)
    strength = 0.3 + 0.12 * tier + (0.4 if clip == "fire" and f == 1 else 0)
    glows = [(dot_src([(cxp, oy)]), PAL['grav2'], 3, min(0.95, strength))]
    return finish(layers, fx, glows)


STATIONS: Dict[str, Callable[[int, str, int], np.ndarray]] = {
    "arc_coil": station_arc_coil,
    "ember_maw": station_ember_maw,
    "frost_whisker": station_frost_whisker,
    "bone_ballista": station_bone_ballista,
    "ward_lantern": station_ward_lantern,
    "gravity_paw": station_gravity_paw,
}




# --------------------------------------------------------------------------------------
# Operator heads for avatars (24 px) and portraits (32 px): one generic template,
# recoloured per cat, plus per-cat overlays (markings / accessories).
# Roles: fur 1 2 3 4 (dark..light) | inner ear P N n | eye F E G (light..dark), # pupil,
#        W highlight | nose q Q p | light patch a b c d (dark..light)
# --------------------------------------------------------------------------------------
GEN_AHEAD = [
    "..4..................3..",
    "..44................33..",
    "..4P4..............3N2..",
    ".44PN4............33Nn2.",
    ".4PPNN4..........333Nn2.",
    ".4PPNN44........3333nn2.",
    "44PPNNN44333333333333Nn2",
    "444PNN443333333333333n22",
    "444444433333333333333322",
    "444443333333333333333222",
    "444433333333333333333222",
    "444333333333333333333222",
    "443333333333333333333222",
    "433111133333333311113322",
    "431WF#F133333331WF#F1322",
    "431FE#E133333331FE#E1322",
    "4332GEG2333333332GEG2322",
    "433322233333333332223322",
    "a4333333333qQqp3333322aa",
    "aa333333333bqpb3333322a.",
    ".aa333333bccc1cccb3332a.",
    "...33333bcc11b11cb33222.",
    "....33333abbbbbba3222...",
    ".....2233abbbba33222....",
    "......2222222222222.....",
    "........222222222.......",
]
GEN_PHEAD = [
    "...4........................3...",
    "...44......................33...",
    "..4P44....................33N2..",
    "..4PP44..................33NN2..",
    "..4PPN44................333NNn2.",
    "..4PPNN44..............3333NNn2.",
    ".44PPNNN44............33333Nnn2.",
    ".44PPNNNN44..........333333Nnn22",
    "444PPNNNN443........3333333Nnn22",
    "444PPNNNN4433......33333333nnn22",
    "4444PNNNN44333333333333333nnn222",
    "4444PPNN4443333333333333333nn222",
    "44444PN444333333333333333332222 ".replace(" ", "2"),
    "44444444433333333333333333332222",
    "44444444333333333333333333322222",
    "44444443333333333333333333322222",
    "44444433333333333333333333322222",
    "44444333333333333333333333322222",
    "44443333333333333333333333322222",
    "44433111111333333333111113322222",
    "44331WWF#FF1333333331WF#FF132222",
    "43331WFE#EF1333333331FE#EF132222",
    "43331FEE#EE1333333331EE#EE132222",
    "433332GE#EG2333333332GE#EG232222",
    "a43333GGGG333pQqp3333GGG3333322a",
    "aa3333333333333bqpb33333333322aa",
    ".aa33333333bcccc1ccccb333322aa..",
    "..a3333333bcddcc1ccccb33322a2...",
    "...3333333bccc11b11cbb33332222..",
    "....3333333abbcbbbbba33322222...",
    ".....22233333abbbbba33322222....",
    "......22222333aaaa3322222.......",
    "........222222222222222.........",
    "..........222222222222..........",
]


def _cat_map(fur, ear, eye, nose, light) -> Dict[str, Color]:
    return {'1': fur[0], '2': fur[1], '3': fur[2], '4': fur[3], 'P': ear[0], 'N': ear[1], 'n': ear[2],
            'F': eye[0], 'E': eye[1], 'G': eye[2], '#': PAL['outline'], 'W': PAL['white'],
            'q': nose[0], 'Q': nose[1], 'p': nose[2], 'a': light[0], 'b': light[1], 'c': light[2], 'd': light[3]}


_GREEN = (E.hexc('#b8f07a'), E.hexc('#6fbf3a'), E.hexc('#3a7a1e'))
CAT_HEAD_COLORS: Dict[str, Dict[str, Color]] = {
    "silver_tabby": _cat_map([PAL['tabby0'], PAL['tabby0'], PAL['tabby1'], PAL['tabby2']],
                             [PAL['pink1'], PAL['pink0'], PAL['tabby0']], _GREEN,
                             [PAL['pink1'], PAL['pink2'], PAL['pink0']],
                             [PAL['tabby2'], PAL['tabby3'], PAL['snow1'], PAL['snow2']]),
    "orange_cat": _cat_map([PAL['orange0'], PAL['orange1'], PAL['orange2'], PAL['orange3']],
                           [PAL['pink1'], PAL['pink0'], PAL['orange1']], (PAL['gold4'], PAL['gold3'], PAL['gold1']),
                           [PAL['pink1'], PAL['pink2'], PAL['pink0']],
                           [PAL['orange3'], PAL['orange4'], PAL['bone3'], PAL['bone4']]),
    "white_cat": _cat_map([PAL['snow0'], PAL['snow0'], PAL['snow1'], PAL['snow2']],
                          [PAL['pink2'], PAL['pink1'], PAL['snow0']], (PAL['frost3'], PAL['frost2'], PAL['frost1']),
                          [PAL['pink1'], PAL['pink2'], PAL['pink0']],
                          [PAL['snow1'], PAL['snow2'], PAL['snow3'], PAL['snow3']]),
    "purple_eyed_cat": _cat_map([PAL['rat0'], PAL['rat0'], PAL['rat1'], PAL['rat2']],
                                [PAL['grav2'], PAL['grav1'], PAL['rat0']], (PAL['grav4'], PAL['grav3'], PAL['grav2']),
                                [PAL['pink0'], PAL['pink1'], PAL['pink0']],
                                [PAL['rat2'], PAL['rat3'], PAL['silver1'], PAL['silver2']]),
    "calico_cat": _cat_map([PAL['snow0'], PAL['snow0'], PAL['snow1'], PAL['snow2']],
                           [PAL['pink1'], PAL['pink0'], PAL['snow0']], _GREEN,
                           [PAL['pink1'], PAL['pink2'], PAL['pink0']],
                           [PAL['snow1'], PAL['snow2'], PAL['snow3'], PAL['snow3']]),
    "hooded_cat": _cat_map([PAL['fur0'], PAL['fur0'], PAL['fur1'], PAL['fur2']],
                           [PAL['fur1'], PAL['fur0'], PAL['fur0']], (PAL['gold4'], PAL['gold3'], PAL['gold2']),
                           [PAL['fur0'], PAL['fur1'], PAL['fur0']],
                           [PAL['fur1'], PAL['fur2'], PAL['fur3'], PAL['silver0']]),
    "skeletal_cat": {'4': PAL['bone0'], '5': PAL['bone1'], '6': PAL['bone2'], '7': PAL['bone3'], '8': PAL['bone4'],
                     'D': PAL['ward3'], 'C': PAL['ward2'], '#': PAL['outline']},
}
ACCENT = {  # extra overlay colours (chars never used by the template roles)
    'h': PAL['gold2'], 'g': PAL['gold1'], 'y': PAL['cyan0'], 'z': PAL['cyan3'], '9': PAL['leather1'],
    'k': E.hexc('#3a3336'), 'K': E.hexc('#4d4448'), 'o': PAL['orange2'], 'O': PAL['orange1'], 'u': PAL['fur1'], 'U': PAL['fur2'],
    'X': PAL['grav3'], 'Y': PAL['grav4'], 'V': PAL['grav2'],
    'B': PAL['ward1'], 'C': PAL['ward2'], 'A': PAL['ward0'], 'j': PAL['gold3'],
    'L': PAL['snow2'], 'l': PAL['snow3'], 'm': PAL['snow1'],
}


def _ov(rows: List[str], over: Sequence[str], start: int = 0) -> List[str]:
    rows = list(rows)
    for i, o in enumerate(over):
        r = rows[start + i]
        rows[start + i] = "".join(oc if oc not in ". " else rc for rc, oc in zip(r, o.ljust(len(r), '.')))
    return rows


def _skull_rows(template: List[str], big: bool) -> List[str]:
    """Bone version of the head template: cute rounded skull, dark sockets, nose hole, teeth."""
    m = {'1': '5', '2': '6', '3': '7', '4': '8', 'P': '5', 'N': '4', 'n': '4', 'a': '6', 'b': '7', 'c': '8', 'd': '8',
         'q': '#', 'Q': '#', 'p': '#', 'F': '7', 'E': '7', 'G': '7', 'W': '7', '#': '7'}
    rows = ["".join(m.get(ch, ch) for ch in r) for r in template]
    if big:
        sock = ["..####..", ".######.", "########", "####D###", ".##DC##.", "..####.."]
        for dx in (4, 20):
            for j, s in enumerate(sock):
                r = rows[18 + j]
                rows[18 + j] = "".join(s[i - dx] if 0 <= i - dx < len(s) and s[i - dx] != '.' else r[i] for i in range(len(r)))
        rows = _ov(rows, ["...............#.#..............", "...............###..............",
                          "................#..............."], 24)
        rows = _ov(rows, ["...........5555555555...........", "..........8#8#8#8#8#8..........",
                          "...........5#5#5#5#5............"], 27)
    else:
        sock = [".##.", "####", "##D#", ".#D."]
        for dx in (3, 16):
            for j, s in enumerate(sock):
                r = rows[13 + j]
                rows[13 + j] = "".join(s[i - dx] if 0 <= i - dx < len(s) and s[i - dx] != '.' else r[i] for i in range(len(r)))
        rows = _ov(rows, ["...........#.#..........", "............#..........."], 18)
        rows = _ov(rows, [".........8#8#8#8........", "..........5#5#5........."], 21)
    return rows


def op_head(cat: str, big: bool) -> np.ndarray:
    """Operator head: big=True -> 32x34 portrait head, else 24x26 avatar head."""
    tpl = list(GEN_PHEAD if big else GEN_AHEAD)
    L = dict(BASE_LEGEND)
    L.update(ACCENT)
    if cat == "skeletal_cat":
        rows = _skull_rows(tpl, big)
        L.update(CAT_HEAD_COLORS[cat])
        return E.ascii_art(rows, L)
    L.update(CAT_HEAD_COLORS[cat])
    L.update({k: v for k, v in ACCENT.items() if k in "hgyz9kKoOuUXYVBCAjLlm"})
    rows = tpl
    if cat == "silver_tabby":
        if big:
            rows = _ov(rows, ["..............1.1.1.............", "..............1.1.1.............",
                              "...............1.1..............",
                              "......hhhhh.........hhhh........", ".....hyyyyyh.......hyyyyh.......",
                              "99999hyzyyyh9999999hyzyyh9999999", ".....hyyyyyh.......hyyyyh.......",
                              "......ghhhg.........ghhg........"], 9)
            rows = _ov(rows, ["..111......................111..", "................................",
                              "...11......................11..."], 25)
        else:
            rows = _ov(rows, ["..........1.1.1.........", "..........1.1.1.........",
                              ".99hhh99999999hhh999....", "9.hyyyh......hyyyh.9....",
                              "..hyzyh......hyzyh......", "...hhh........hhh......."], 7)
            rows = _ov(rows, ["11..................11..", "........................", "1......................1"], 17)
    elif cat == "orange_cat":
        if big:
            rows = _ov(rows, ["...................kkK..........", "..................kkkkK.........",
                              "...................kkk..........", "................................",
                              "................................", "...............kk..............."], 11)
            rows = _ov(rows, ["..kk............................", ".kkkK...........................",
                              "..kkk.......................k...", "............................kk..",
                              ".................W.............."], 25)
        else:
            rows = _ov(rows, ["................kk......", "...............kkk......"], 9)
            rows = _ov(rows, ["..k.....................", ".kkk....................",
                              "..kk..............k.....", "..................kk....",
                              "...........W............"], 17)
    elif cat == "purple_eyed_cat":
        if big:
            rows = _ov(rows, ["...............Y................", "..............YXY...............",
                              ".............YXWXY..............", "..............YXY...............",
                              "...............Y................"], 11)
            rows = _ov(rows, [".....WWYXYY1.........WYXYY1.....", ".....WYXXXY1.........YXXXY1.....",
                              ".....YXXXXX1.........XXXXX1.....", "......VXXXV..........VXXV......."], 20)
        else:
            rows = _ov(rows, ["...........Y............", "..........YXY...........", "...........Y............"], 8)
            rows = _ov(rows, ["...WYXY.........WYXY....", "...YXXX.........YXXX....", "....VXV..........VXV...."], 14)
    elif cat == "calico_cat":
        if big:
            rows = _ov(rows, ["...o........................u...", "...oo......................uu...",
                              "..oPoo....................uuNu..", "..oPPoo..................uuNNu..",
                              "..oPPNoo................uuuNNnu.", "..oPPNNoo..............uuuuNNnu.",
                              ".ooPPNNNoo............uuuuuNnnu.", ".ooPPNNNNoo..........uuuuuuNnnuu",
                              "oooPPNNNNooo........uuuuuuuNnnuu", "oooPPNNNNoooo......uuuuuuuunnnuu",
                              "ooooPNNNNoooooo..........uuunnnuu", "ooooPPNNoooooo.............nnuuu",
                              "ooooooooooooo..............uuuuu", "oooooooooooo.................uuu",
                              "ooooooooooo...................uu", "oooooooooo......................",
                              "Ooooooooo.......................", "OOooooo.........................",
                              "OOoooo..........................", "OOooo..........................."], 0)
        else:
            rows = _ov(rows, ["..o.....................", "..oo................uu..", "..oPo..............uNu..",
                              ".ooPNo............uuNnu.", ".oPPNNo..........uuuNnu.", ".oPPNNoo........uuuunnu.",
                              "ooPPNNNoo.........uuuNnu", "oooPNNoo.............nuu", "ooooooo...............uu",
                              "oooooo.................u", "ooooo...................", "Oooo....................",
                              "OO......................"], 0)
    elif cat == "hooded_cat":
        if big:
            hood = [
                "...B........................A...",
                "...BB......................AA...",
                "..BCBB....................AABA..",
                "..BCCBB..................AABBA..",
                "..BCCBBB................AAABBA..",
                "..BCCBBBB..............AAAABBA..",
                ".BBCCBBBBB............AAAAABBA..",
                ".BCCCBBBBBBBBBBBBBBBBBAAAAABBAA.",
                "BBCCBBBBBBBBBBBBBBBBBBBBBBBBBAAA",
                "BCCCBBBBBBBBBBBBBBBBBBBBBBBBBBAA",
                "BCCBBBBBBBBBBBBBBBBBBBBBBBBBBBAA",
                "BCCBBBBBBBBBBBBBBBBBBBBBBBBBBBAA",
                "BCBBBBBBBBBBBBBBBBBBBBBBBBBBBBBA",
                "BCBB11111111111111111111111BBBAA",
                "CBB1111111111111111111111111BBAA",
                "CBB1111111111111111111111111BBAA",
                "CB111........................BAA",
                "CB11.........................BAA",
                "CB1..........................BA.",
                "CB1..........................BA.",
                "CB1.WWFFF1..........1WFFF1...BA.",
                "CB1.WFEEE1..........1FEEE1...BA.",
                "CB1.FEEEE1..........1EEEE1...BA.",
                "CB1..GEEG............GEEG....BA.",
                "CB1...GG..............GG.....BA.",
                "CB............................BA",
                "CB............................BA",
                "CB............................BA",
                "C..............................A",
                "C..............................A",
            ]
            rows = _ov(rows, hood, 0)
        else:
            rows = _ov(rows, [
                "..B..................A..", "..BB................AA..", "..BCB..............ABA..",
                ".BBCBB............AABBA.", ".BCCBBB..........AAABBA.", ".BCCBBBB........AAAABBA.",
                "BBCCBBBBBBBBBBBBBBBAABBA", "BCCCBBBBBBBBBBBBBBBBBBAA", "BCCBBBBBBBBBBBBBBBBBBBAA",
                "BCB11111111111111111BBAA", "BCB1111111111111111111BA", "CB11111111111111111111BA",
                "CB1111111111111111111BAA", "CB1.................1BA.", "CB1WFFF1.......1WFFF1BA.",
                "CB1FEEE1.......1FEEE1BA.", "CB1.GGG.........GGG..BA.", "CB......................",
                "CB.....................A", "CB.....................A"], 0)
    elif cat == "white_cat":
        pass
    return E.ascii_art(rows, L)


def fluff_tufts(img: np.ndarray, x0: int, y0: int, big: bool) -> None:
    """White cat: fluffy cheek and crown tufts beyond the head outline (drawn before outlining)."""
    c1, c2 = PAL['snow2'], PAL['snow1']
    if big:
        pts = [(-1, 22, c1), (-2, 23, c1), (-1, 24, c1), (-2, 26, c2), (-1, 27, c2), (-1, 28, c2), (0, 29, c2),
               (32, 22, c2), (33, 23, c2), (32, 24, c2), (33, 26, c2), (32, 27, c2), (31, 29, c2),
               (13, 10, c1), (14, 9, c1), (15, 10, c1), (16, 9, c1), (17, 10, c1)]
    else:
        pts = [(-1, 17, c1), (-2, 18, c1), (-1, 19, c1), (-1, 21, c2), (24, 17, c2), (25, 18, c2), (24, 19, c2),
               (10, 6, c1), (11, 5, c1), (12, 6, c1)]
    for dx, dy, c in pts:
        put(img, x0 + dx, y0 + dy, c)


# --------------------------------------------------------------------------------------
# Avatars (32x32) and portraits (64x64)
# --------------------------------------------------------------------------------------
def _poly(pts, W, H) -> np.ndarray:
    im = E.new(W, H)
    E.polygon(im, pts, (255, 255, 255, 255))
    return im[:, :, 3] > 0


def _fill(img, mask, fn):
    ys, xs = np.nonzero(mask)
    for x, y in zip(xs, ys):
        c = fn(x, y)
        if c is not None:
            img[y, x] = c


def _top_rim(img, mask, color):
    H, W = mask.shape
    ys, xs = np.nonzero(mask)
    for x, y in zip(xs, ys):
        if y == 0 or not mask[y - 1, x]:
            img[y, x] = color


AVATAR_COLLAR = {
    "silver_tabby": (PAL['leather1'], PAL['leather2'], PAL['orange3']),
    "orange_cat": (PAL['fire1'], PAL['fire2'], PAL['fire3']),
    "white_cat": (PAL['frost1'], PAL['frost2'], PAL['frost4']),
    "skeletal_cat": (PAL['crow1'], PAL['crow2'], PAL['bone3']),
    "hooded_cat": (PAL['ward1'], PAL['ward2'], PAL['gold3']),
    "purple_eyed_cat": (PAL['grav1'], PAL['grav2'], PAL['grav4']),
    "calico_cat": (PAL['violet2'], PAL['violet3'], PAL['silver3']),
}


def avatar(cat: str) -> np.ndarray:
    W = H = 32
    img = E.new(W, H)
    dark, mid, acc = AVATAR_COLLAR[cat]
    m = _poly([(2, 32), (4, 27), (8, 25), (24, 25), (28, 27), (30, 32)], W, H)
    _fill(img, m, lambda x, y: mid if x < 16 else dark)
    _top_rim(img, m, acc if cat in ("hooded_cat", "skeletal_cat") else mid)
    put(img, 16, 28, acc)
    put(img, 15, 29, acc)
    put(img, 16, 29, acc)
    head = op_head(cat, big=False)
    layers = [(img, 0, 0, None), (head, 4, 3, OL)]
    fr = compose(layers, W, H)
    if cat == "white_cat":
        fluff_tufts(fr, 4, 3, big=False)
    return E.outline(fr)


def _prop(cat: str) -> Tuple[np.ndarray, Optional[Tuple[int, int, Color]]]:
    """Small weapon prop for the portrait's top-right corner, plus an optional glow point."""
    W = H = 64
    p = E.new(W, H)
    glow = None
    if cat == "silver_tabby":            # mini copper coil with a spark
        for y in range(10, 22):
            for x in range(53, 58):
                u = x - 53
                c = (PAL['orange3'] if u == 0 else PAL['orange2'] if u < 3 else PAL['orange1']) if y % 2 == 0 else \
                    (PAL['orange1'] if u < 3 else PAL['orange0'])
                p[y, x] = c
        E.paste(p, A([".bc.", "bdcb", "abba", ".aa."]), 53, 6)
        E.paste(p, A(["JKKKKKJ", "IJJJJJI"]), 52, 22)
        glow = (55, 7, PAL['cyan2'])
    elif cat == "orange_cat":            # a live coal / ember flame on a shovel
        E.paste(p, A(["....U....", "...UT....", "..TUTS...", ".STUUTS..", ".RTTTTSR.", "..RSSSR.."]), 51, 6)
        for i in range(8):
            put(p, 55 - i // 2, 12 + i, PAL['wood2'] if i % 2 else PAL['wood3'])
        E.paste(p, A(["LLLLLLL", ".KKKKK."]), 52, 12)
        glow = (55, 9, PAL['fire2'])
    elif cat == "white_cat":             # small ice bell
        E.paste(p, A(["...K...", "...fF..", "..fHHF.", ".fHzHFe", ".fHHFFe", "fFHHFFe", "effffee", "...e..."]), 51, 6)
        glow = (55, 10, PAL['frost3'])
    elif cat == "skeletal_cat":          # bone bolt (diagonal)
        for i in range(12):
            put(p, 50 + i, 20 - i, PAL['bone3'] if i % 2 else PAL['bone2'])
            put(p, 51 + i, 20 - i, PAL['bone1'])
        E.paste(p, A(["..88", ".888", "8888", ".8.."]), 60, 5)
        E.paste(p, A(["6.6", "66.", "6.."]), 48, 19)
    elif cat == "hooded_cat":            # little lantern
        E.paste(p, A(["...h...", "..hih..", ".JLKKJ.", "hhhhhhg", "KDViVDK", "KDijiDK", "KDijiDK", "KDViVDK", "hhhhhhg",
                      ".JKKKJ."]), 52, 5)
        glow = (55, 11, PAL['ward3'])
    elif cat == "purple_eyed_cat":       # floating rune orb
        sphere(p, 56, 11, 4.2, 4.2, [PAL['grav0'], PAL['grav1'], PAL['grav2'], PAL['grav3']])
        for (dx, dy) in ((0, -1), (0, 0), (-1, 1), (1, 1), (0, 2)):
            put(p, 56 + dx, 11 + dy, PAL['grav4'])
        put(p, 55, 8, PAL['white'])
        glow = (56, 11, PAL['grav2'])
    return p, glow


def portrait(cat: str) -> np.ndarray:
    W = H = 64
    img = E.new(W, H)
    hc = CAT_HEAD_COLORS[cat]
    fur = [hc.get('1', PAL['bone1']), hc.get('2', PAL['bone2']), hc.get('3', PAL['bone3']), hc.get('4', PAL['bone4'])]
    shoulders = _poly([(3, 64), (6, 54), (12, 47), (21, 43), (43, 43), (52, 47), (58, 54), (61, 64)], W, H)
    neck = _poly([(23, 38), (41, 38), (43, 48), (21, 48)], W, H)
    img[neck] = fur[1]

    def fur_fill(x, y):
        return fur[3] if x < 14 else (fur[2] if x < 40 else fur[1])
    if cat == "silver_tabby":
        _fill(img, shoulders, fur_fill)
        # tabby stripes on the shoulders
        for (x0, y0) in ((9, 52), (12, 49), (52, 50), (55, 53)):
            E.line(img, x0, y0, x0 + 2, y0 + 4, PAL['tabby0'])
        vest = _poly([(12, 64), (15, 49), (24, 44), (29, 52), (29, 64)], W, H) | \
            _poly([(35, 64), (35, 52), (40, 44), (49, 49), (52, 64)], W, H)
        _fill(img, vest, lambda x, y: PAL['leather2'] if x < 22 else PAL['leather1'])
        _top_rim(img, vest, PAL['leather2'])
        chest = _poly([(29, 64), (29, 52), (32, 47), (35, 52), (35, 64)], W, H)
        _fill(img, chest, lambda x, y: PAL['tabby3'] if x < 33 else PAL['tabby2'])
        for y in (54, 58, 62):
            put(img, 27, y, PAL['orange3'])
            put(img, 37, y, PAL['orange2'])
        # wrench in the vest pocket
        E.paste(img, A(["L.L", "LLL", ".K.", ".K.", ".K."]), 43, 53)
    elif cat == "orange_cat":
        _fill(img, shoulders, fur_fill)
        apron = _poly([(20, 64), (21, 50), (43, 50), (44, 64)], W, H)
        _fill(img, apron, lambda x, y: PAL['leather2'] if x < 28 else PAL['leather1'])
        _top_rim(img, apron, PAL['leather2'])
        for x in (22, 42):
            for y in range(44, 51):
                put(img, x, y, PAL['leather0'])
        for (x, y) in ((22, 52), (42, 52), (26, 58), (38, 61)):
            put(img, x, y, PAL['iron3'])
        for (x, y) in ((30, 56), (31, 56), (31, 57), (35, 60), (36, 60)):
            put(img, x, y, E.hexc('#2a2224'))
        scarf = _poly([(22, 42), (42, 42), (40, 47), (33, 49), (24, 47)], W, H)
        _fill(img, scarf, lambda x, y: PAL['fire2'] if x < 30 else PAL['fire1'])
        E.paste(img, A(["SSR", ".SR", ".RR", "..R"]), 37, 46)
    elif cat == "white_cat":
        _fill(img, shoulders, fur_fill)
        ruff = _poly([(18, 43), (46, 43), (44, 54), (40, 51), (37, 56), (32, 52), (27, 56), (24, 51), (20, 54)], W, H)
        _fill(img, ruff, lambda x, y: PAL['snow3'] if x < 30 else PAL['snow2'])
        scarf = _poly([(19, 40), (45, 40), (45, 45), (19, 45)], W, H)
        _fill(img, scarf, lambda x, y: PAL['frost2'] if (x // 3) % 2 == 0 else PAL['frost1'])
        _top_rim(img, scarf, PAL['frost3'])
        tail = _poly([(40, 44), (45, 44), (47, 57), (42, 57)], W, H)
        _fill(img, tail, lambda x, y: PAL['frost1'] if (y // 3) % 2 else PAL['frost2'])
        for (dx, dy) in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            put(img, 24 + dx, 42 + dy, PAL['frost4'])
    elif cat == "skeletal_cat":
        cloak = shoulders
        _fill(img, cloak, lambda x, y: PAL['crow3'] if x < 14 else (PAL['crow2'] if x < 40 else PAL['crow1']))
        _top_rim(img, cloak, PAL['crow3'])
        ribs = _poly([(25, 64), (26, 47), (38, 47), (39, 64)], W, H)
        img[ribs] = PAL['crow0']
        for y in range(48, 64, 3):
            for x in range(27, 38):
                if x != 32:
                    put(img, x, y, PAL['bone3'] if x < 32 else PAL['bone2'])
        for y in range(47, 64):
            put(img, 32, y, PAL['bone4'] if y % 2 else PAL['bone2'])
        E.paste(img, A(["8.8", "787", ".6."]), 31, 44)
    elif cat == "hooded_cat":
        cloak = shoulders | _poly([(14, 34), (18, 46), (10, 50)], W, H) | _poly([(50, 34), (46, 46), (54, 50)], W, H)
        _fill(img, cloak, lambda x, y: PAL['ward2'] if x < 14 else (PAL['ward1'] if x < 42 else PAL['ward0']))
        _top_rim(img, cloak, PAL['ward2'])
        for (x0, y0, x1, y1) in ((20, 63, 23, 50), (44, 63, 42, 50)):
            E.line(img, x0, y0, x1, y1, PAL['ward0'])
        E.paste(img, A([".hj.", "hDVg", "gCDg", ".gg."]), 30, 45)
    elif cat == "purple_eyed_cat":
        _fill(img, shoulders, fur_fill)
        shawl = _poly([(4, 64), (7, 54), (13, 47), (22, 43), (32, 50), (42, 43), (51, 47), (57, 54), (60, 64)], W, H)
        _fill(img, shawl, lambda x, y: PAL['grav2'] if x < 16 else (PAL['grav1'] if x < 44 else PAL['grav0']))
        _top_rim(img, shawl, PAL['grav3'])
        for (x, y) in ((10, 57), (14, 53), (18, 56), (47, 55), (51, 58), (44, 60), (22, 61), (40, 61)):
            put(img, x, y, PAL['grav4'])
        E.paste(img, A([".Y.", "YXY", ".Y."]), 31, 49)
    head = op_head(cat, big=True)
    layers = [(img, 0, 0, None), (head, 16, 6, OL)]
    fr = compose(layers, W, H)
    if cat == "white_cat":
        fluff_tufts(fr, 16, 6, big=True)
    fr = E.outline(fr)
    prop, glow = _prop(cat)
    prop = E.outline(prop)
    m = mask_img(prop) & ~mask_img(fr)
    fr[m] = prop[m]
    if glow is not None:
        fr = glow_under(fr, dot_src([(glow[0], glow[1])], W, H), glow[2], 4, 0.45)
    if cat == "silver_tabby":
        rnd = E.rng(SEED + 9)
        spark_zig(fr, 55, 5, 60, 1, rnd)
        spark_zig(fr, 54, 5, 50, 2, rnd)
    return fr


# --------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------
CLIP_SPEC = {"idle": (4, 6, True), "fire": (5, 14, False)}


def build_stations(reg: "E.Registry") -> None:
    for mid in MODULES:
        fn = STATIONS[mid]
        for tier in (1, 2, 3):
            for clip, (n, fps, loop) in CLIP_SPEC.items():
                frames = [fn(tier, clip, f) for f in range(n)]
                for fimg in frames:
                    assert fimg.shape == (FH, FW, 4), (mid, tier, clip)
                reg.anim("stations", f"station/{mid}/t{tier}/{clip}", frames, fps, loop, pivot=PIVOT)


def build(reg: "E.Registry") -> None:
    build_stations(reg)


def _iter_preview():
    out = "/tmp/claude-0/hero_iter"
    os.makedirs(out, exist_ok=True)
    for mid, fn in STATIONS.items():
        frames = []
        for tier in (1, 2, 3):
            frames += [fn(tier, "idle", f) for f in range(4)]
            frames += [fn(tier, "fire", f) for f in range(5)]
        E.preview_images(frames, os.path.join(out, f"st_{mid}.png"), scale=5)
        E.preview_images(frames, os.path.join(out, f"st_{mid}_1x.png"), scale=2)


if __name__ == "__main__":
    _iter_preview()
