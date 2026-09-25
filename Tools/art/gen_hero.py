"""
gen_hero.py - Arc Light Cat (atlas "hero") + his portrait/avatar (atlas "portraits").

Arc Light Cat is built from layered, hand-placed pixel parts (tail, body, mantle, feet,
staff, arms, head, crown, crystal).  Every animation frame is composed from the same parts
with small per-part offsets / variants, so all frames stay on-model.  Skins are ramp swaps
applied per part through the legend (mantle body, trim, crown, clasp, fork), so the eyes,
forehead bolt and crystal always stay cyan.

Run directly for iteration previews:
    python3 Tools/art/gen_hero.py            -> /tmp/claude-0/hero_iter/*.png
"""
from __future__ import annotations

import math
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eclib as E  # noqa: E402
from eclib import PAL  # noqa: E402

Color = Tuple[int, int, int, int]
FW = FH = 40                 # frame size
PIVOT = (0.5, 0.1)           # feet (pixel row 36 from the top)
OL = PAL["outline"]
SEED = 4111

# --------------------------------------------------------------------------------------
# Legend.  Fixed characters (fur, silver markings, cyan) never change between skins.
# Skinned characters: mantle body v w x y z, trim T U, crown e f g h, clasp K M,
# staff fork D F G H.
# --------------------------------------------------------------------------------------
BASE_LEGEND: Dict[str, Color] = {
    '#': PAL['outline'],
    '1': PAL['fur0'], '2': PAL['fur1'], '3': PAL['fur2'], '4': PAL['fur3'],
    'a': PAL['silver0'], 'b': PAL['silver1'], 'c': PAL['silver2'], 'd': PAL['silver3'],
    'i': PAL['cyan0'], 'j': PAL['cyan1'], 'k': PAL['cyan2'], 'l': PAL['cyan3'], 'm': PAL['cyan4'],
    'W': PAL['white'],
    'p': PAL['pink0'], 'q': PAL['pink1'], 'Q': PAL['pink2'],
    'n': PAL['violet1'], 'N': PAL['violet2'], 'P': PAL['violet3'],   # inner ear (never skinned)
    'o': PAL['wood0'], 'r': PAL['wood1'], 's': PAL['wood2'], 't': PAL['wood3'],
    # --- skinned ---
    'v': PAL['violet0'], 'w': PAL['violet1'], 'x': PAL['violet2'], 'y': PAL['violet3'], 'z': PAL['violet4'],
    'T': PAL['violet3'], 'U': PAL['violet4'],
    'e': PAL['silver0'], 'f': PAL['silver1'], 'g': PAL['silver2'], 'h': PAL['silver3'],
    'K': PAL['silver1'], 'M': PAL['silver3'],
    'D': PAL['silver0'], 'F': PAL['silver1'], 'G': PAL['silver2'], 'H': PAL['silver3'],
}


def _skin(**over) -> Dict[str, Color]:
    d = dict(BASE_LEGEND)
    for k, v in over.items():
        d[k] = PAL[v] if isinstance(v, str) else v
    return d


SKINS: Dict[str, Dict[str, Color]] = {
    "arc_light_cat": _skin(),
    # ember-orange mantle, gold crown
    "arc_light_cat_ember": _skin(v='red0', w='fire0', x='orange1', y='orange2', z='orange3',
                                 T='fire2', U='fire3',
                                 e='gold1', f='gold2', g='gold3', h='gold4', K='gold2', M='gold4'),
    # ice-blue mantle, white crown
    "arc_light_cat_frost": _skin(v='frost0', w='frost0', x='frost1', y='frost2', z='frost3',
                                 T='frost3', U='frost4',
                                 e='snow0', f='snow1', g='snow2', h='snow3', K='snow1', M='snow3'),
    # black mantle with gold trim, gold crown (and a gilded fork)
    "arc_light_cat_gilded": _skin(v='crow0', w='crow1', x='crow2', y='crow3', z='crow3',
                                  T='gold2', U='gold3',
                                  e='gold1', f='gold2', g='gold3', h='gold4', K='gold2', M='gold4',
                                  D='gold1', F='gold2', G='gold3', H='gold4'),
}

# --------------------------------------------------------------------------------------
# Head = ears (rows 0-5) + face (rows 6-16).  16 px wide; the face centre line is col 8.5
# (3/4 view facing right).  Forehead bolt: (9,6) (8,7) (9,8) (8,9).
# --------------------------------------------------------------------------------------
EARS = {
    "normal": [
        ".4............3.",
        ".44..........32.",
        ".4P3........3N2.",
        ".4PN3......33N2.",
        "44PN43....333n22",
        "44PN4333333333n2",
    ],
    "twitch": [   # far ear flicks outward
        ".4.............3",
        ".44..........332",
        ".4P3........3N2.",
        ".4PN3......33N2.",
        "44PN43....333n22",
        "44PN4333333333n2",
    ],
    "back": [     # pinned back (flinch)
        "................",
        "................",
        "4..............2",
        "44P3........3N22",
        "44PN43....333n22",
        "44PN4333333333n2",
    ],
    "droop": [    # drooping sideways (defeat)
        "................",
        "................",
        "................",
        "44.............2",
        "4PP43.....3332n2",
        "44PN4333333333n2",
    ],
}

_FACE_TOP = [
    "444433333l333322",   # 6
    "44433333k3333322",   # 7
]
_FACE_BOTTOM = [
    "a4333333pp33332a",   # 12
    ".a33333bccbb332a",   # 13
    "..33333bcacb32..",   # 14
    "...222333b3222..",   # 15
    ".....22222222...",   # 16
]
FACES = {
    "normal": _FACE_TOP + [
        "4cb333333l333b22",
        "43cc3333k333cc22",
        "433Wlk3333Wlk322",
        "433kkj3333klj322",
    ] + _FACE_BOTTOM,
    "blink": _FACE_TOP + [
        "4cb333333l333b22",
        "43cc3333k333cc22",
        "4333333333333322",
        "433jkj3333jkj322",
    ] + _FACE_BOTTOM,
    "glow": _FACE_TOP + [
        "4cb333333l333b22",
        "43cc3333k333cc22",
        "433WWm3333WWm322",
        "433mlk3333mll322",
    ] + _FACE_BOTTOM,
    "squint": _FACE_TOP + [
        "4cb333333l333b22",
        "43ck3333k333kc22",
        "4333k333333k3322",
        "433k33333333k322",
        "a4333333pp33332a",
        ".a33333bccbb332a",
        "..33333b1a1b32..",
        "...222333b3222..",
        ".....22222222...",
    ],
    "smug": _FACE_TOP + [
        "4cb333333l333b22",
        "43cc3333k333cc22",
        "4332223333222322",
        "433Wlk3333Wlk322",
        "a4333333pp33332a",
        ".a3333bcccccb32a",
        "..3333a1W11a32..",
        "...2223bbb3222..",
        ".....22222222...",
    ],
    "closed": _FACE_TOP + [
        "43b333333l33b322",
        "4c3c3333k33c3c22",
        "4333333333333322",
        "433jjj3333jjj322",
        "a4333333pp33332a",
        ".a33333bccbb332a",
        "..33333bc1cb32..",
        "...222333b3222..",
        ".....22222222...",
    ],
}

CROWN = [
    "...g...",
    "h..g..f",
    "hg.g.fe",
    "hggggfe",
    "gffffee",
]

CRYSTAL = [
    ".ml.",
    "mllk",
    "lkkj",
    "lkkj",
    "kkjj",
    ".jj.",
]
CRYSTAL_STATES = {
    "normal": {},
    "bright": {'j': 'k', 'k': 'l', 'l': 'm', 'm': 'W'},
    "flare": {'j': 'l', 'k': 'm', 'l': 'W', 'm': 'W'},
    "dim1": {'m': 'l', 'l': 'k', 'k': 'j', 'j': 'i'},
    "dim2": {'m': 'k', 'l': 'j', 'k': 'j', 'j': 'i'},
    "dim3": {'m': 'j', 'l': 'j', 'k': 'i', 'j': 'i'},
}

FORK = [
    "G...F",
    "G...F",
    "HG.FD",
    ".GFD.",
    "..F..",
]

TORSO = [
    # x=14..26, y=20..30 (only seen through the mantle opening)
    ".....33333...",
    "....4333332..",
    "...443333322.",
    "...443333322.",
    "...443333322.",
    "...433333222.",
    "...433333222.",
    "..4433333222.",
    "..4433333222.",
    "..443322332..",
    "..44332.332..",
]
LEGS = [
    # x=14..26, y=31..35
    "..4432..332..",
    "..4432..332..",
    "..4432..332..",
    "..4432..332..",
    "..4432..332..",
]
FEET = [
    # x=14..26, y=33..35
    "..443...443..",
    ".44332.44322.",
    ".32322.32322.",
]

PAWS = {
    "grip": [      # wraps a vertical staff; staff column = col 2
        ".44.",
        "4443",
        "3322",
    ],
    "open": [      # raised paw, pink toe beans towards the viewer
        "4.43",
        "4Q3q",
        "3qp2",
        ".32.",
    ],
    "fist": [
        "443",
        "432",
        ".2.",
    ],
}


def A(rows: Sequence[str], L) -> np.ndarray:
    return E.ascii_art(rows, L)


# --------------------------------------------------------------------------------------
# Procedural helpers
# --------------------------------------------------------------------------------------
def _catmull(pts: Sequence[Tuple[float, float]], steps: int = 10) -> List[Tuple[float, float]]:
    out = []
    p = [pts[0]] + list(pts) + [pts[-1]]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(tuple(pts[-1]))
    return out


def tube(pts: Sequence[Tuple[float, float]], r0: float, r1: float, ramp: Sequence[Color],
         W: int = FW, H: int = FH) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
    """Shaded tube along a spline: light top-left edge, dark bottom-right edge."""
    path = _catmull(pts, 10) if len(pts) > 2 else [
        (pts[0][0] + (pts[1][0] - pts[0][0]) * t / 20, pts[0][1] + (pts[1][1] - pts[0][1]) * t / 20) for t in range(21)]
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
    return img, path


FUR_RAMP = [PAL['fur1'], PAL['fur2'], PAL['fur3']]


def tail_layer(sway: float = 0.0, curl: float = 0.0, puff: float = 0.0, limp: float = 0.0):
    """Curved tail rising on the left behind the mantle.  limp (0..1) lowers it to the ground."""
    s = sway
    up = [(13, 33.5), (8.5, 33.5), (5.5, 31.5), (4 + s * 0.3, 28), (4 + s * 0.6, 24),
          (5 + s, 20.5 - curl), (7 + s, 19 - curl), (8 + s, 20.5 - curl)]
    down = [(13, 34), (9, 34.3), (6, 34.2), (3.5, 33.6), (2.5, 32.2), (2.8, 30.8), (3.6, 30.2), (4.3, 30.8)]
    pts = [(a[0] + (b[0] - a[0]) * limp, a[1] + (b[1] - a[1]) * limp) for a, b in zip(up, down)]
    return tube(pts, 1.15 + puff, 0.75 + puff, FUR_RAMP)


def _interp(ctrl: Sequence[Tuple[float, ...]], y: float) -> Tuple[float, ...]:
    if y <= ctrl[0][0]:
        return tuple(ctrl[0][1:])
    for (y0, *v0), (y1, *v1) in zip(ctrl, ctrl[1:]):
        if y0 <= y <= y1:
            t = (y - y0) / max(1e-6, (y1 - y0))
            return tuple(a + (b - a) * t for a, b in zip(v0, v1))
    return tuple(ctrl[-1][1:])


def cloak_layer(L, dxt: float = 0.0, dyt: int = 0, flare_l: float = 0.0, flare_r: float = 0.0,
                wave: float = 0.0, wave_amp: float = 0.0, lift_l: float = 0.0, lift_r: float = 0.0,
                open_w: float = 0.0, shadow: Optional[Tuple[int, int]] = None) -> np.ndarray:
    """Dark violet mantle: bell shape from the shoulders to the ground with a trimmed front
    opening.  dxt/dyt: shift of the shoulders (hem stays planted); flare_*: widen the hem;
    lift_*: raise the hem at that side (billow / flourish; the swung-out part shows the
    darker lining); wave: hem flutter."""
    img = E.new(FW, FH)
    top = 20 + dyt
    k25, k30 = 0.6, 0.25

    def outer_ctrl(fl, fr):
        return [(20 + dyt, 14.0 + dxt, 26.0 + dxt), (21 + dyt, 13.0 + dxt, 27.0 + dxt),
                (22 + dyt, 12.4 + dxt, 27.6 + dxt),
                (25 + dyt * k25, 11.6 + dxt * k25 - fl * 0.15, 28.0 + dxt * k25 + fr * 0.15),
                (30 + dyt * k30, 10.2 + dxt * k30 - fl * 0.5, 29.0 + dxt * k30 + fr * 0.5),
                (35, 9.0 - fl, 30.0 + fr)]
    outer = outer_ctrl(flare_l, flare_r)
    neutral = outer_ctrl(min(flare_l, 1.0), min(flare_r, 1.0))
    ax = 20.0 + dxt
    opening = [(22 + dyt, ax, ax), (24 + dyt, ax - 0.8, ax + 1.4),
               (27 + dyt * k25, 18.2 + dxt * k25 - open_w * 0.4, 22.4 + dxt * k25 + open_w * 0.4),
               (31 + dyt * k30, 17.2 + dxt * k30 - open_w * 0.7, 23.4 + dxt * k30 + open_w * 0.7),
               (35, 16.2 - open_w, 24.4 + open_w)]
    apex_y = 22 + dyt
    for yy in range(top, 36):
        xl, xr = _interp(outer, yy)
        nl, nr = _interp(neutral, yy)
        ol, orr = _interp(opening, yy)
        for x in range(int(math.floor(xl)), int(math.ceil(xr)) + 1):
            if x < xl - 0.5 or x > xr + 0.5 or not (0 <= x < FW):
                continue
            if yy >= apex_y and ol - 0.5 < x < orr + 0.5 and not (yy == apex_y and abs(x - ax - 0.5) <= 1.0):
                continue
            left_panel = x < (ol + orr) / 2
            u = (x - xl) / max(1.0, xr - xl)
            ul = max(0.0, (nl - x) / max(1.0, nl - xl)) if x < nl else 0.0     # 0..1 into the left swing
            ur = max(0.0, (x - nr) / max(1.0, xr - nr)) if x > nr else 0.0
            hem = 35 - lift_l * (ul if flare_l > 1.0 else max(0.0, 0.5 - u) * 2) \
                - lift_r * (ur if flare_r > 1.0 else max(0.0, u - 0.5) * 2)
            hem += wave_amp * math.sin(u * 8.0 + wave)
            if yy > hem + 0.5:
                continue
            d_out_l, d_out_r = x - xl, xr - x
            d_open = (ol - x) if left_panel else (x - orr)
            lining = (x < nl - 0.5 and yy > top + 3) or (x > nr + 0.5 and yy > top + 3)
            if yy >= hem - 0.5:
                c = L['T'] if u < 0.75 else L['x']
            elif yy == top:
                c = L['y'] if x < ax else L['x']
            elif yy >= apex_y and 0 <= d_open < 1.0:
                c = L['U'] if (left_panel and yy < apex_y + 4) else L['T']
            elif lining:
                if d_out_l < 1.0 or d_out_r < 1.0:
                    c = L['T']
                else:
                    c = L['v'] if (abs(x - nl) < 1.2 or abs(x - nr) < 1.2) else L['w']
            elif left_panel:
                if d_out_l < 1.0:
                    c = L['y']
                elif d_out_l < 2.0 and yy < 30:
                    c = L['y'] if (yy + x) % 2 == 0 and yy > top + 3 else L['x']
                else:
                    fu = (x - xl) / max(1.0, ol - xl)
                    c = L['w'] if abs(fu - 0.55) < 0.12 and yy > top + 4 else L['x']
            else:
                if d_out_r < 1.0:
                    c = L['v']
                elif d_out_r < 2.5:
                    c = L['w']
                else:
                    fu = (x - orr) / max(1.0, xr - orr)
                    c = L['w'] if abs(fu - 0.45) < 0.12 and yy > top + 5 else L['x']
            if shadow is not None and yy <= top + 1 and shadow[0] <= x <= shadow[1]:
                c = L['w'] if c != L['v'] else c
            img[yy, x] = c
    cx, cy = int(round(ax)), apex_y
    if 0 <= cy < FH:
        img[cy, cx] = L['M']
        img[cy, cx + 1] = L['K']
        if cy + 1 < FH:
            img[cy + 1, cx] = L['K']
    return img


def cape_wing(L, tip: Tuple[float, float], side: int = -1, dxt: float = 0.0, dyt: float = 0.0) -> np.ndarray:
    """The mantle's side flung outward (flourish): a wing from the shoulder to `tip` and back
    down to the hem.  Upper edge = lit rim, a band of outer surface, then the darker lining."""
    img = E.new(FW, FH)
    if side < 0:
        A_ = (12.5 + dxt, 21.0 + dyt)
        D_ = (9.0, 35.5)
    else:
        A_ = (27.5 + dxt, 21.0 + dyt)
        D_ = (31.0, 35.5)
    B_ = tip
    C_ = (tip[0] - side * 1.5, tip[1] + 3.0)
    pts = [A_, B_, C_, D_, (A_[0] - side * 1.0, 35.5)]
    mask_img = E.new(FW, FH)
    E.polygon(mask_img, pts, (255, 255, 255, 255))
    m = mask_img[:, :, 3] > 0
    ax, ay = A_
    bx, by = B_
    ex, ey = bx - ax, by - ay
    ln = math.hypot(ex, ey) or 1
    ys, xs = np.nonzero(m)
    for x, y in zip(xs, ys):
        # distance below the upper edge A->B (perpendicular)
        d = abs((x - ax) * ey - (y - ay) * ex) / ln
        hem_d = abs((x - C_[0]) * (D_[1] - C_[1]) - (y - C_[1]) * (D_[0] - C_[0])) / (math.hypot(D_[0] - C_[0], D_[1] - C_[1]) or 1)
        if d < 1.0:
            c = L['T']
        elif d < 2.6:
            c = L['x']
        elif hem_d < 1.0:
            c = L['T']
        else:
            c = L['v'] if (x - ax) * side < 1.5 else L['w']
        img[y, x] = c
    return img


def staff_layer(L, x: int, bottom: int, top: int, lean: int = 0) -> np.ndarray:
    """Wooden shaft from (x, bottom) to (x+lean, top) with a silver ferrule."""
    img = E.new(FW, FH)
    n = bottom - top
    for i, y in enumerate(range(bottom, top - 1, -1)):
        xx = x + int(round(lean * i / max(1, n)))
        if 0 <= y < FH and 0 <= xx < FW:
            img[y, xx] = PAL['wood3'] if (y % 4 == 1) else PAL['wood2']
    if 0 <= bottom < FH:
        img[bottom, x] = L['F']
    return img


def part_ring(a: np.ndarray) -> np.ndarray:
    g = a.copy()
    g[1:, :] |= a[:-1, :]
    g[:-1, :] |= a[1:, :]
    g[:, 1:] |= a[:, :-1]
    g[:, :-1] |= a[:, 1:]
    return g & ~a


def compose(layers, W: int = FW, H: int = FH) -> np.ndarray:
    """layers: (img, x, y, line_colour|None). A part's 1px ring is drawn only over already
    opaque pixels (internal separation lines); the silhouette is outlined afterwards."""
    canvas = E.new(W, H)
    for img, x, y, lc in layers:
        if img is None:
            continue
        full = E.new(W, H)
        E.paste(full, img, x, y)
        a = full[:, :, 3] > 0
        if lc is not None:
            ring = part_ring(a) & (canvas[:, :, 3] > 0)
            canvas[ring] = lc
        canvas[a] = full[a]
    return canvas


def recolor_chars(rows: Sequence[str], mapping: Dict[str, str]) -> List[str]:
    return ["".join(mapping.get(ch, ch) for ch in r) for r in rows]


# --------------------------------------------------------------------------------------
# FX helpers (drawn after the outline pass: crisp bright pixels, soft alpha only for glow)
# --------------------------------------------------------------------------------------
def put(img, x, y, c):
    x, y = int(round(x)), int(round(y))
    if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
        img[y, x] = c


def soft_glow_under(fr: np.ndarray, src: np.ndarray, color: Color, radius: int, strength: float) -> np.ndarray:
    halo = E.glow(src, color, radius=radius, strength=strength)
    halo[src[:, :, 3] > 0] = 0            # keep halo only (sprite pasted back on top)
    out = halo
    m = fr[:, :, 3] > 0
    out[m] = fr[m]
    return out


def zigzag(img, x0, y0, x1, y1, rnd, cols=(PAL['cyan3'], PAL['cyan2']), jitter=1):
    """A little lightning crack between two points (1px, jittered)."""
    n = max(2, int(max(abs(x1 - x0), abs(y1 - y0))))
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        if 0 < i < n:
            x += rnd.choice((-jitter, 0, jitter)) if abs(y1 - y0) >= abs(x1 - x0) else 0
            y += rnd.choice((-jitter, 0, jitter)) if abs(x1 - x0) > abs(y1 - y0) else 0
        put(img, x, y, cols[0] if i % 2 == 0 else cols[1])


def tail_arcs(img, path, rnd, count: int):
    n = len(path)
    for _ in range(count):
        i = rnd.randint(int(n * 0.25), n - 3)
        (x, y), (x2, y2) = path[i], path[min(n - 1, i + 2)]
        dx, dy = x2 - x, y2 - y
        ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / ln, dx / ln
        side = rnd.choice((-1, 1))
        pts = [(x + nx * 1.8 * side, y + ny * 1.8 * side),
               (x + dx / ln, y + dy / ln),
               (x - nx * 1.6 * side + 2 * dx / ln, y - ny * 1.6 * side + 2 * dy / ln)]
        cols = [PAL['cyan2'], PAL['cyan3'], PAL['cyan1']]
        for (px_, py_), c in zip(pts, cols):
            put(img, px_, py_, c)


def starburst(img, cx, cy, r, inner: int = 3):
    """Crystal flare: long horizontal streak + shorter vertical/diagonal rays, white -> cyan."""
    ramp = [PAL['white'], PAL['cyan4'], PAL['cyan3'], PAL['cyan3'], PAL['cyan2'], PAL['cyan2'], PAL['cyan1']]
    cx, cy = int(round(cx)), int(round(cy))
    for s in (1, -1):
        for i in range(r + 2):
            put(img, cx + s * (inner + i), cy, ramp[min(len(ramp) - 1, i)])
        for i in range(r):
            put(img, cx, cy + s * (inner + 1 + i), ramp[min(len(ramp) - 1, i + 1)])
        for t in (1, -1):
            for i in range(max(1, r - 2)):
                put(img, cx + s * (inner - 1 + i), cy + t * (inner - 1 + i), ramp[min(len(ramp) - 1, i + 2)])


def sparkle(img, x, y, big=False):
    put(img, x, y, PAL['white'])
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        put(img, x + dx, y + dy, PAL['cyan3'])
    if big:
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            put(img, x + dx, y + dy, PAL['cyan2'])


def aura(img, rnd, density: float):
    """Crackling electric aura: glowing silhouette edge + a few short arcs jumping off it."""
    a = img[:, :, 3] > 0
    ring = part_ring(a)
    edge = np.zeros_like(a)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        sh = np.zeros_like(a)
        ys0, ys1 = max(0, dy), FH + min(0, dy)
        xs0, xs1 = max(0, dx), FW + min(0, dx)
        sh[ys0:ys1, xs0:xs1] = ring[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
        edge |= sh
    edge &= a & np.all(img[:, :, :3] == np.array(OL[:3], np.uint8), axis=-1)
    ys, xs = np.nonzero(edge)
    for x, y in zip(xs, ys):
        if rnd.random() < density * 0.6:
            img[y, x] = PAL['cyan0'] if rnd.random() < 0.7 else PAL['cyan1']
    # arcs: pick silhouette points and shoot a 3-4 px jagged spark outward
    ys, xs = np.nonzero(ring)
    pts = list(zip(xs, ys))
    rnd.shuffle(pts)
    cx, cy = FW / 2, FH / 2
    n_arcs = int(2 + density * 6)
    used = []
    for x, y in pts:
        if len(used) >= n_arcs:
            break
        if any(abs(x - u) + abs(y - v) < 7 for u, v in used):
            continue
        used.append((x, y))
        dx, dy = x - cx, y - cy
        ln = math.hypot(dx, dy) or 1
        dx, dy = dx / ln, dy / ln
        px_, py_ = float(x), float(y)
        cols = [PAL['cyan3'], PAL['white'], PAL['cyan2'], PAL['cyan1']]
        for i in range(rnd.randint(2, 4)):
            put(img, px_, py_, cols[min(i, 3)])
            px_ += dx + rnd.choice((-0.8, 0, 0.8)) * abs(dy)
            py_ += dy + rnd.choice((-0.8, 0, 0.8)) * abs(dx)


def puff(img, cx, cy, r, alpha=200):
    c = PAL['silver2'][:3] + (alpha,)
    c2 = PAL['silver3'][:3] + (alpha,)
    for dx, dy, rr in ((0, 0, r), (-r, 1, r - 1), (r, 1, r - 1)):
        for yy in range(int(cy + dy - rr), int(cy + dy + rr) + 1):
            for xx in range(int(cx + dx - rr), int(cx + dx + rr) + 1):
                if (xx - cx - dx) ** 2 + (yy - cy - dy) ** 2 <= rr * rr + 0.3:
                    if 0 <= xx < FW and 0 <= yy < FH and img[yy, xx, 3] == 0:
                        img[yy, xx] = c2 if yy < cy + dy else c


# --------------------------------------------------------------------------------------
# Frame renderer
# --------------------------------------------------------------------------------------
def render(pose: dict, L: Dict[str, Color], seed: int = 0) -> np.ndarray:
    """Compose one 40x40 frame from a pose description (see the clip builders below)."""
    rnd = E.rng(SEED + seed)
    bx, by = pose.get("body", (0, 0))          # torso / shoulders / arms
    hx, hy = pose.get("head", (0, 0))          # extra on top of body
    kneel = pose.get("kneel", 0)               # lowers torso & shoulders; legs/feet hidden
    by_eff = by + pose.get("breath", 0) + kneel
    cl = dict(pose.get("cloak", {}))
    st = dict(x=30, raise_=0, lean=0)
    st.update(pose.get("staff", {}))
    sx, sr, slean = st["x"] + bx, st["raise_"], st["lean"]
    s_bottom = 35 + sr
    fork_y = 13 + sr
    s_top = fork_y + 5
    tail_img, tail_path = tail_layer(pose.get("sway", 0.0), pose.get("curl", 0.0), pose.get("tail_puff", 0.0),
                                     pose.get("limp", 0.0))
    HX, HY = 11 + bx + hx, 5 + by_eff + hy
    head = A(EARS[pose.get("ears", "normal")] + FACES[pose.get("face", "normal")], L)
    crown_dx, crown_dy = pose.get("crown", (0, 0))

    # staff paw (top-left) - absolute y, x follows the (leaning) shaft
    grip = pose.get("grip")
    gpos = None
    if grip is not None:
        gy = grip
        frac = (s_bottom - gy) / max(1, s_bottom - s_top)
        gpos = (sx + int(round(slean * frac)) - 2, gy)

    layers = [(cape_wing(L, tip, side, dxt=bx, dyt=by_eff), 0, 0, None) for side, tip in pose.get("wings", [])]
    layers += [(tail_img, 0, 0, OL), (A(TORSO, L), 14 + bx, 20 + by_eff, OL)]
    if not kneel:
        layers.append((A(LEGS, L), 14, 31, OL))
    front = []
    for key in ("arm_near", "arm_far"):
        arm = pose.get(key)
        if not arm:
            continue
        sh = (arm["shoulder"][0] + bx, arm["shoulder"][1] + by_eff)
        if arm.get("to_grip") and gpos is not None:
            wr = (gpos[0] + 0.5, gpos[1] + 1.0)
        else:
            wr = (arm["wrist"][0] + bx, arm["wrist"][1] + by_eff)
        pts = [sh, (arm["elbow"][0] + bx, arm["elbow"][1] + by_eff), wr] if arm.get("elbow") else [sh, wr]
        img, _ = tube(pts, arm.get("r", 1.25), arm.get("r", 1.25) - 0.25, FUR_RAMP)
        (front if arm.get("front") else layers).append((img, 0, 0, OL))
        if arm.get("paw"):
            pw = A(PAWS[arm["paw"]], L)
            ph, pwid = pw.shape[:2]
            front.append((pw, int(round(wr[0] - pwid / 2 + arm.get("paw_dx", 0))),
                          int(round(wr[1] - ph + 1 + arm.get("paw_dy", 0))), OL))
    layers.append((cloak_layer(L, dxt=bx + cl.get("dxt", 0), dyt=by_eff, flare_l=cl.get("flare_l", 0),
                               flare_r=cl.get("flare_r", 0), wave=cl.get("wave", 0), wave_amp=cl.get("wave_amp", 0),
                               lift_l=cl.get("lift_l", 0), lift_r=cl.get("lift_r", 0), open_w=cl.get("open_w", 0),
                               shadow=(HX + 3, HX + 13)), 0, 0, OL))
    if not kneel:
        layers.append((A(FEET, L), 14, 33, OL))
    layers.append((staff_layer(L, sx, s_bottom, s_top, slean), 0, 0, OL))
    layers.append((A(FORK, L), sx - 2 + slean, fork_y, OL))
    layers.extend(front)
    if gpos is not None:
        layers.append((A(PAWS["grip"], L), gpos[0], gpos[1], OL))
    layers.append((head, HX, HY, OL))
    layers.append((A(CROWN, L), HX + 5 + crown_dx, HY + crown_dy, OL))
    fr = compose(layers)
    fr = E.outline(fr)

    # crystal: outlined on its own so it floats above the fork
    cstate = pose.get("crystal_state", "normal")
    cdx, cdy = pose.get("crystal", (0, 0))
    cimg = E.new(FW, FH)
    ccx, ccy = sx - 2 + slean + cdx, 4 + sr + cdy
    E.paste(cimg, A(recolor_chars(CRYSTAL, CRYSTAL_STATES[cstate]), L), ccx, ccy)
    cimg = E.outline(cimg)
    m = cimg[:, :, 3] > 0
    fr[m] = cimg[m]

    tail_arcs(fr, tail_path, rnd, pose.get("arcs", 1))
    for fx in pose.get("fx", []):
        kind = fx[0]
        if kind == "burst":
            starburst(fr, ccx + 1 + fx[1][0], ccy + 2 + fx[1][1], fx[2], fx[3] if len(fx) > 3 else 3)
        elif kind == "sparkle":
            sparkle(fr, fx[1], fx[2], fx[3] if len(fx) > 3 else False)
        elif kind == "zig":
            zigzag(fr, *fx[1], rnd)
        elif kind == "aura":
            aura(fr, rnd, fx[1])
        elif kind == "puff":
            puff(fr, fx[1], fx[2], fx[3])
    glow_r = {"normal": 2, "bright": 3, "flare": 4}.get(cstate, 1)
    glow_s = {"normal": 0.35, "bright": 0.5, "flare": 0.75}.get(cstate, 0.15)
    return soft_glow_under(fr, cimg, PAL['cyan2'], glow_r, glow_s)


# --------------------------------------------------------------------------------------
# Clips
# --------------------------------------------------------------------------------------
STAFF_ARM = dict(shoulder=(22, 24), front=True, to_grip=True)


def _idle() -> List[dict]:
    poses = []
    breath = [0, 0, -1, -1, -1, -1, 0, 0]
    bob = [0, -1, -1, -1, 0, 0, 1, 0]
    for i in range(8):
        p = dict(breath=breath[i], sway=0.9 * math.sin(2 * math.pi * i / 8), crystal=(0, bob[i]),
                 grip=24 + breath[i], arm_far=STAFF_ARM, arcs=1 + (i % 3 == 0) + (i == 4))
        if i == 4:
            p["ears"] = "twitch"
        if i == 7:
            p["face"] = "blink"
        poses.append(p)
    return poses


def _attack() -> List[dict]:
    arm = dict(shoulder=(22, 24), front=True, to_grip=True)
    arm_up = dict(arm, shoulder=(22, 23))
    thrust = dict(raise_=-2, lean=1, x=31)
    return [
        # 0 anticipation: lean back, staff tips back, crystal gathers light
        dict(body=(-1, 1), staff=dict(lean=-1), grip=25, arm_far=arm, crystal=(-1, 1), sway=-0.8, arcs=1,
             ears="back", fx=[("sparkle", 29, 6)]),
        # 1 thrust: staff driven up and forward, crystal brightens, mantle kicks back
        dict(body=(1, -1), staff=thrust, grip=22, arm_far=arm_up, crystal_state="bright", sway=0.6, arcs=2,
             cloak=dict(flare_l=2, lift_l=2, wave=0.5, wave_amp=0.4)),
        # 2 flare (white-cyan)
        dict(body=(1, -1), face="glow", staff=thrust, grip=22, arm_far=arm_up, crystal_state="flare", sway=0.9,
             arcs=2, cloak=dict(flare_l=2.5, lift_l=2.5, wave=1.5, wave_amp=0.6), fx=[("burst", (0, 0), 5, 3)]),
        # 3 follow-through, flare fading into sparks
        dict(body=(1, 0), staff=thrust, grip=22, arm_far=arm_up, crystal_state="bright", sway=0.6, arcs=2,
             cloak=dict(flare_l=1.5, lift_l=1.5, wave=2.5, wave_amp=0.5),
             fx=[("burst", (0, 0), 2, 4), ("sparkle", 37, 2), ("sparkle", 26, 9)]),
        # 4 recover
        dict(staff=dict(raise_=-1), grip=23, arm_far=arm, crystal=(0, -1), sway=0.2, arcs=1,
             cloak=dict(flare_l=0.5, lift_l=0.5, wave=3.5, wave_amp=0.3), fx=[("sparkle", 35, 6)]),
    ]


def _cast() -> List[dict]:
    far = dict(shoulder=(25, 23), front=True, to_grip=True)
    near_up = dict(shoulder=(14, 23), elbow=(10, 20), wrist=(8, 15), front=True, paw="open", paw_dy=-1)
    near_mid = dict(shoulder=(14, 23), elbow=(11, 22), wrist=(10, 19), front=True, paw="open", paw_dy=-1)
    P = [dict(staff=dict(raise_=-1), grip=22, arm_far=far, arm_near=near_mid, crystal_state="bright", sway=-1.0,
              arcs=1, cloak=dict(flare_l=0.8, flare_r=0.5), fx=[("sparkle", 9, 13)])]
    for i in range(5):
        fx = [("aura", 0.45 + 0.1 * i)]
        if i >= 1:
            fx.append(("zig", (9, 10, 28, 4)))
        fx.append(("sparkle", 7 + (i % 2), 10 - (i % 3), i % 2 == 0))
        P.append(dict(breath=-1, staff=dict(raise_=-3), grip=19, arm_far=far, arm_near=near_up, face="glow",
                      crystal_state="bright", crystal=(0, -1 if i % 2 else 0), sway=-1.4 + 0.4 * math.sin(i * 1.7),
                      arcs=2 + i % 2,
                      wings=[(-1, (6 - (i % 2), 26 - (i % 2))), (1, (33 + (i % 2), 27 - (i % 2)))],
                      cloak=dict(wave=i * 1.4, wave_amp=0.8), fx=fx))
    P.append(dict(breath=-1, staff=dict(raise_=-3), grip=19, arm_far=far, arm_near=near_up, face="glow",
                  crystal_state="flare", sway=-1.2, arcs=3,
                  wings=[(-1, (4, 24)), (1, (35, 25))], cloak=dict(wave=7, wave_amp=1.0),
                  fx=[("aura", 1.0), ("burst", (0, 0), 4, 3), ("sparkle", 7, 9, True)]))
    P.append(dict(staff=dict(raise_=-2), grip=21, arm_far=far, arm_near=near_mid, crystal_state="bright",
                  sway=-0.6, arcs=2, cloak=dict(flare_l=1.0, flare_r=0.8, wave=8, wave_amp=0.4),
                  fx=[("aura", 0.2), ("sparkle", 10, 14)]))
    return P


def _hit() -> List[dict]:
    arm = dict(shoulder=(22, 24), front=True, to_grip=True)
    return [
        dict(body=(-2, 0), head=(-1, 0), ears="back", face="squint", staff=dict(lean=-1), grip=24, arm_far=arm,
             crystal=(-1, 1), crystal_state="bright", sway=-1.2, tail_puff=0.35, arcs=3),
        dict(body=(-1, 0), head=(-1, 0), ears="back", face="squint", staff=dict(lean=-1), grip=24, arm_far=arm,
             crystal=(-1, 0), sway=-0.8, tail_puff=0.2, arcs=2),
        dict(face="blink", grip=24, arm_far=arm, sway=-0.3, arcs=1),
    ]


def _victory() -> List[dict]:
    far = dict(shoulder=(25, 23), front=True, to_grip=True)
    P = []
    hop = [0, -1, -1, 0, 0, 0]
    wing_tips = [(6, 27), (4, 25), (3, 23), (3.5, 24), (4.5, 26), (5.5, 27)]   # cape flourish
    sparks = [(35, 3), (26, 6), (37, 9), (34, 1), (25, 3), (38, 5)]
    for i in range(6):
        lower = 1 if i in (3, 4) else 0
        P.append(dict(body=(0, hop[i]), face="smug", staff=dict(raise_=-3 + lower), grip=19 + hop[i] + lower,
                      arm_far=far, crystal_state="bright", crystal=(0, -1 if i in (1, 2) else 0),
                      sway=0.9 * math.sin(2 * math.pi * i / 6) + 0.4, curl=0.5, arcs=1 + i % 2,
                      wings=[(-1, wing_tips[i])], cloak=dict(wave=i * 1.05, wave_amp=0.5, flare_r=0.3),
                      fx=[("sparkle", sparks[i][0], sparks[i][1], i % 3 == 0)]))
    return P


def _defeat() -> List[dict]:
    arm_lo = dict(shoulder=(22, 24), front=True, to_grip=True)
    return [
        dict(body=(-1, 0), ears="back", face="squint", staff=dict(lean=-1), grip=24, arm_far=arm_lo,
             crystal_state="dim1", crystal=(0, 1), sway=-0.8, arcs=2),
        dict(kneel=1, head=(0, 1), ears="back", face="closed", staff=dict(lean=-1), grip=26, arm_far=arm_lo,
             crystal_state="dim1", crystal=(0, 2), sway=-0.4, limp=0.3, arcs=1, cloak=dict(flare_l=0.5, flare_r=0.3)),
        dict(kneel=3, head=(0, 1), ears="droop", face="closed", staff=dict(lean=-1), grip=28, arm_far=arm_lo,
             crystal_state="dim2", crystal=(0, 3), limp=0.6, arcs=1, crown=(1, 0),
             cloak=dict(flare_l=1.2, flare_r=0.8)),
        dict(kneel=4, head=(0, 2), ears="droop", face="closed", staff=dict(lean=-2), grip=29, arm_far=arm_lo,
             crystal_state="dim3", crystal=(-1, 3), limp=0.9, arcs=0, crown=(1, 1),
             cloak=dict(flare_l=1.6, flare_r=1.0), fx=[("puff", 5, 34, 2), ("puff", 34, 34, 2)]),
        dict(kneel=4, head=(0, 1), ears="droop", face="closed", staff=dict(lean=-2), grip=29, arm_far=arm_lo,
             crystal_state="dim3", crystal=(-1, 3), limp=1.0, arcs=0, crown=(1, 1),
             cloak=dict(flare_l=1.8, flare_r=1.1), fx=[("puff", 3, 33, 1), ("puff", 36, 33, 1)]),
        dict(kneel=4, head=(0, 2), ears="droop", face="closed", staff=dict(lean=-2), grip=29, arm_far=arm_lo,
             crystal_state="dim3", crystal=(-1, 3), limp=1.0, arcs=0, crown=(1, 1),
             cloak=dict(flare_l=1.8, flare_r=1.1)),
    ]


CLIPS = {  # name: (builder, fps, loop)
    "idle": (_idle, 8, True),
    "attack": (_attack, 14, False),
    "cast": (_cast, 12, False),
    "hit": (_hit, 12, False),
    "victory": (_victory, 8, True),
    "defeat": (_defeat, 8, False),
}


def build_clips() -> Dict[str, Tuple[List[dict], float, bool]]:
    return {k: (fn(), fps, loop) for k, (fn, fps, loop) in CLIPS.items()}


def render_clip(name: str, skin: str) -> List[np.ndarray]:
    fn, fps, loop = CLIPS[name]
    return [render(p, SKINS[skin], seed=i + 31 * len(name)) for i, p in enumerate(fn())]


# --------------------------------------------------------------------------------------
# Portrait (64x64 bust) and avatar (32x32 head)
# --------------------------------------------------------------------------------------
def _poly_mask(pts, W, H) -> np.ndarray:
    im = E.new(W, H)
    E.polygon(im, pts, (255, 255, 255, 255))
    return im[:, :, 3] > 0


def _ell_mask(cx, cy, rx, ry, W, H) -> np.ndarray:
    im = E.new(W, H)
    E.ellipse(im, cx, cy, rx, ry, (255, 255, 255, 255))
    return im[:, :, 3] > 0


def _band_shade(img, mask, ramp, cx, cy, rx, ry, light=(-0.62, -0.78), bias=0.0, cuts=(0.55, 0.12, -0.38)):
    """Banded (non-dithered) sphere shading lit from the top-left.  ramp dark->light, 4 steps."""
    ys, xs = np.nonzero(mask)
    lx, ly = light
    for x, y in zip(xs, ys):
        nx, ny = (x - cx) / rx, (y - cy) / ry
        d = min(1.0, math.hypot(nx, ny))
        nz = math.sqrt(max(0.0, 1 - d * d))
        lam = -(nx * lx + ny * ly) * 0.8 + nz * 0.45 + bias
        if lam > cuts[0]:
            c = ramp[3]
        elif lam > cuts[1]:
            c = ramp[2]
        elif lam > cuts[2]:
            c = ramp[1]
        else:
            c = ramp[0]
        img[y, x] = c


def _rim(img, mask, color, dirs=((-1, 0), (0, -1)), W=None, H=None):
    """Recolour mask pixels whose neighbour in any of `dirs` is outside the mask (rim light)."""
    H, W = mask.shape
    ys, xs = np.nonzero(mask)
    for x, y in zip(xs, ys):
        for dx, dy in dirs:
            xx, yy = x + dx, y + dy
            if not (0 <= xx < W and 0 <= yy < H) or not mask[yy, xx]:
                img[y, x] = color
                break


# Portrait head: hand-refined 2x of the sprite head (32 x 34), same markings, more detail.
PHEAD = [
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
  "44444PN444333333333lk33333332222",
  "444444444333333333lm333333332222",
  "44444444333333333lm3333333322222",
  "4444444333333333lm33333333322222",
  "4cdc443333333333lmmmlk3333b22222",
  "4bcdcc3333333333333lm3333ccb2222",
  "43bbcdc33333333333lm3333cdcb2222",
  "433##bcc333333333lm3333ccb##2222",
  "43331W##b3333333k333333b##Wl2222",
  "4333kWWll##33333333333##lWlk2222",
  "4333kkllllk1333333333#klllkk3222",
  "43333jkkkkkj33333333jkkkkkj32222",
  "a4333.jjjjj3333pQqp33jjjjj.3322a",
  "aa3333333333333bqpb33333333322aa",
  ".aa33333333bcccc1ccccb333322aa..",
  "..a3333333bcddcc1ccccb33322a2...",
  "...3333333bccc11b11cbb33332222..",
  "....3333333abbcbbWbba33322222...",
  ".....22233333abbbbba33322222....",
  "......22222333aaaa3322222.......",
  "........222222222222222.........",
  "..........222222222222..........",
]

PCROWN = [
    "......hg......",
    "......hg......",
    "h.....hgg....f",
    "hh...hggg...fe",
    "hgh..hgggg.fge",
    "hggh.hgggg.fge",
    "hgggghggggfgge",
    "hggggggggggfee",
    "hhggggMgggffee",
    "gffffffffffeee",
]
PFORK = [
    "G.....F",
    "G.....F",
    "HG...FD",
    ".HG.FD.",
    "..GFD..",
    "...F...",
    "...D...",
]
PGEM = [
    "..ml..",
    ".mWlk.",
    "mmllkj",
    "mllkkj",
    "lllkkj",
    "lkkkjj",
    ".kkjj.",
    "..jj..",
]

# Avatar head: 24 px wide (1.5x of the sprite head).
AHEAD = [
  "..4..................3..",
  "..44................33..",
  "..4P4..............3N2..",
  ".44PN4............33Nn2.",
  ".4PPNN4..........333Nn2.",
  ".4PPNN44........3333nn2.",
  "44PPNNN44333333333333Nn2",
  "444PNN443333333333333n22",
  "4444P44333333333lk333322",
  "44444433333333lm33333222",
  "4444433333333lm333333222",
  "4cc433333333lmmlk333b222",
  "4bdcc333333333lm333ccb22",
  "43bbcc3333333lm333cdcb22",
  "43#Wl##33333k3333##Wl#22",
  "43kWlll#33333333#lWllk22",
  "43kkllkj33333333kllkkj22",
  "433jkkj3333333333jkkj322",
  "a4333333333qQqp3333322aa",
  "aa333333333bqpb3333322a.",
  ".aa333333bccc1cccb3332a.",
  "...33333bcc11b11cb33222.",
  "....33333abbbbWba3222...",
  ".....2233abbbba33222....",
  "......2222222222222.....",
  "........222222222.......",
]
ACROWN = [
  "....hg....",
  "h...hg...f",
  "hh..hgg.fe",
  "hgh.hgg.fe",
  "hgghhgggfe",
  "hggggggfee",
  "gfffffffee",
]


def portrait_arc(L: Dict[str, Color]) -> np.ndarray:
    """64x64 bust: head + crown, high-collared violet mantle with silver clasp, and the forked
    staff with its floating cyan crystal on the right."""
    W = H = 64
    img = E.new(W, H)
    mantle = _poly_mask([(0, 64), (1, 57), (6, 51), (10, 49), (7, 33), (14, 38), (18, 43), (46, 43), (50, 38),
                         (57, 32), (54, 49), (58, 51), (63, 57), (63, 64)], W, H)
    ys, xs = np.nonzero(mantle)
    for x, y in zip(xs, ys):
        if x < 20:
            c = L['y'] if x < 12 else L['x']
        elif x < 44:
            c = L['x']
        else:
            c = L['w'] if x < 56 else L['v']
        img[y, x] = c
    lining = _poly_mask([(9, 36), (16, 40), (20, 44), (14, 47)], W, H) | _poly_mask([(55, 35), (48, 40), (44, 44), (50, 47)], W, H)
    img[lining & mantle] = L['v']
    for (x0, y0, x1, y1, c) in ((13, 63, 16, 52, 'w'), (6, 63, 8, 56, 'x'), (51, 63, 49, 52, 'v'), (57, 63, 56, 57, 'w'),
                                (10, 63, 12, 55, 'y')):
        E.line(img, x0, y0, x1, y1, L[c])
    _rim(img, mantle, L['T'], dirs=((0, -1), (-1, 0)))
    chest = _poly_mask([(24, 64), (27, 47), (32, 44), (37, 47), (40, 64)], W, H)
    _band_shade(img, chest, [PAL['fur0'], PAL['fur1'], PAL['fur2'], PAL['fur3']], 29, 50, 9, 12)
    for y in range(44, 64):
        row = [x for x in range(18, 46) if chest[y, x]]
        if row:
            img[y, row[0] - 1] = L['U']
            img[y, row[0] - 2] = L['T']
            img[y, row[-1] + 1] = L['T']
    for (x, y, c) in ((32, 44, 'M'), (31, 45, 'M'), (32, 45, 'K'), (33, 45, 'K'), (30, 46, 'K'), (31, 46, 'y'),
                      (32, 46, 'x'), (33, 46, 'K'), (34, 46, 'D'), (31, 47, 'K'), (32, 47, 'K'), (33, 47, 'D'),
                      (32, 48, 'D')):
        img[y, x] = L[c]
    img = compose([(img, 0, 0, None), (A(PHEAD, L), 15, 9, OL), (A(PCROWN, L), 25, 8, OL)], W, H)
    img = E.outline(img)
    st = E.new(W, H)
    for y in range(29, 64):
        st[y, 58] = PAL['wood3'] if y % 4 == 1 else PAL['wood2']
    E.paste(st, A(PFORK, L), 55, 22)
    st = E.outline(st)
    m = (st[:, :, 3] > 0) & (img[:, :, 3] == 0)
    img[m] = st[m]
    g = E.new(W, H)
    E.paste(g, A(PGEM, L), 55, 9)
    g = E.outline(g)
    m = g[:, :, 3] > 0
    img[m] = g[m]
    img = soft_glow_under(img, g, PAL['cyan2'], 3, 0.45)
    sparkle(img, 53, 7)
    return img


def avatar_arc(L: Dict[str, Color]) -> np.ndarray:
    """32x32 head with crown and a sliver of mantle collar."""
    W = H = 32
    col = E.new(W, H)
    m = _poly_mask([(1, 32), (3, 27), (7, 25), (25, 25), (29, 27), (31, 32)], W, H)
    ys, xs = np.nonzero(m)
    for x, y in zip(xs, ys):
        col[y, x] = L['y'] if x < 10 else (L['x'] if x < 22 else L['w'])
    _rim(col, m, L['T'], dirs=((0, -1),))
    for (x, y, c) in ((16, 29, 'M'), (17, 29, 'K'), (16, 30, 'K'), (15, 30, 'K'), (17, 30, 'D')):
        col[y, x] = L[c]
    img = compose([(col, 0, 0, None), (A(AHEAD, L), 4, 3, OL), (A(ACROWN, L), 11, 2, OL)], W, H)
    return E.outline(img)


# --------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------
def _check_frame(img: np.ndarray, name: str) -> None:
    if img.shape != (FH, FW, 4):
        raise ValueError(f"{name}: frame must be {FW}x{FH}")


def build(reg: "E.Registry") -> None:
    for skin in SKINS:
        for clip, (fn, fps, loop) in CLIPS.items():
            frames = render_clip(clip, skin)
            for f in frames:
                _check_frame(f, f"hero/{skin}/{clip}")
            reg.anim("hero", f"hero/{skin}/{clip}", frames, fps, loop, pivot=PIVOT)
    L = SKINS["arc_light_cat"]
    reg.sprite("portraits", "portrait/arc_light_cat", portrait_arc(L), pivot=(0.5, 0.5))
    reg.sprite("portraits", "avatar/arc_light_cat", avatar_arc(L), pivot=(0.5, 0.5))


def _iter_preview():
    out = "/tmp/claude-0/hero_iter"
    os.makedirs(out, exist_ok=True)
    for name in CLIPS:
        E.preview_images(render_clip(name, "arc_light_cat"), os.path.join(out, f"clip_{name}.png"), scale=5)
    L = SKINS["arc_light_cat"]
    E.preview_images([portrait_arc(L), avatar_arc(L)], os.path.join(out, "portrait.png"), scale=6)
    frames = [render_clip("idle", s)[0] for s in SKINS]
    E.preview_images(frames, os.path.join(out, "skins.png"), scale=6)


if __name__ == "__main__":
    _iter_preview()
