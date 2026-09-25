"""
gen_enemies.py - the Golden Collar Order (regular enemies) for EVIL CATS.

Atlases written:
  * enemies (flash=True): enemy/<id>/<clip>/<i> and enemy/<id>_elite/<clip>/<i>
  * icons:                icon/enemy/<id> (16x16; bats use the id "bat_swarm")

Every enemy is a small rig of hand-placed pixel parts (ASCII art using the eclib palette)
that are composed per frame with per-part offsets, so every frame stays on-model. The
whole silhouette gets a 1 px PAL['outline'] outline; FX (sparks, glows, halos) are drawn
after the outline. Elite variants add gold armour trim + a small gold crest/plume and are
slightly brighter (the game also scales them 1.25x).

Run directly for quick iteration previews:
    python3 Tools/art/gen_enemies.py [enemy_id ...]   -> /tmp/claude-0/enemy_iter/
"""
from __future__ import annotations

import math
import os
import sys
import textwrap
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import eclib as E  # noqa: E402
from eclib import PAL  # noqa: E402

ITER_DIR = "/tmp/claude-0/enemy_iter"
OUTLINE = PAL["outline"]

# --------------------------------------------------------------------------------------
# Shared legend for ASCII parts. Per-creature legends extend it (fur ramps etc).
#   '.' / ' ' transparent, '#' outline, 'x' black, 'W' white
#   gold 1-5 (gold0..gold4)  red 6-0 (red0..red4)  iron i-m (iron0..iron4)
#   fire e f F y (fire1..fire4)  pink p q n  wood w v u  leather L M N
# --------------------------------------------------------------------------------------
LEG: Dict[str, Tuple[int, int, int, int]] = {
    "#": PAL["outline"], "x": PAL["black"], "W": PAL["white"], "%": PAL["outline_soft"],
    "1": PAL["gold0"], "2": PAL["gold1"], "3": PAL["gold2"], "4": PAL["gold3"], "5": PAL["gold4"],
    "6": PAL["red0"], "7": PAL["red1"], "8": PAL["red2"], "9": PAL["red3"], "0": PAL["red4"],
    "i": PAL["iron0"], "j": PAL["iron1"], "k": PAL["iron2"], "l": PAL["iron3"], "m": PAL["iron4"],
    "e": PAL["fire1"], "f": PAL["fire2"], "F": PAL["fire3"], "y": PAL["fire4"],
    "p": PAL["pink0"], "q": PAL["pink1"], "n": PAL["pink2"],
    "w": PAL["wood1"], "v": PAL["wood2"], "u": PAL["wood3"],
    "L": PAL["leather0"], "M": PAL["leather1"], "N": PAL["leather2"],
}

RAT_LEG = {"A": PAL["rat0"], "B": PAL["rat1"], "C": PAL["rat2"], "D": PAL["rat3"], "E": E.hexc("#bcaebb")}


def art(s: str, legend: Optional[Dict] = None) -> np.ndarray:
    """ASCII rows -> RGBA part. Blank lines at the ends are dropped; '.' is transparent."""
    lines = textwrap.dedent(s).split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    lg = dict(LEG)
    if legend:
        lg.update(legend)
    w = max(len(r) for r in lines)
    return E.ascii_art([r.ljust(w, ".") for r in lines], lg)


# --------------------------------------------------------------------------------------
# Fast compositing helpers
# --------------------------------------------------------------------------------------
def blit(dst: np.ndarray, src: np.ndarray, x: int, y: int) -> None:
    """Composite src onto dst at (x, y). Opaque pixels copy; translucent ones blend."""
    x, y = int(x), int(y)
    sh, sw = src.shape[:2]
    dh, dw = dst.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dw, x + sw), min(dh, y + sh)
    if x0 >= x1 or y0 >= y1:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    d = dst[y0:y1, x0:x1]
    a = s[:, :, 3]
    op = a == 255
    d[op] = s[op]
    tr = (a > 0) & (a < 255)
    if tr.any():
        ys, xs = np.nonzero(tr)
        for yy, xx in zip(ys, xs):
            E._blend_px(dst, x0 + xx, y0 + yy, tuple(int(v) for v in s[yy, xx]))


def dilate(m: np.ndarray, diag: bool = False) -> np.ndarray:
    g = m.copy()
    g[1:, :] |= m[:-1, :]
    g[:-1, :] |= m[1:, :]
    g[:, 1:] |= m[:, :-1]
    g[:, :-1] |= m[:, 1:]
    if diag:
        g[1:, 1:] |= m[:-1, :-1]
        g[1:, :-1] |= m[:-1, 1:]
        g[:-1, 1:] |= m[1:, :-1]
        g[:-1, :-1] |= m[1:, 1:]
    return g


class Canvas:
    """Frame under construction. put() parts back-to-front, then finish()."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.img = E.new(w, h)
        self.fx = E.new(w, h)       # drawn after the outline (glows, sparks)
        self.fx_under = E.new(w, h)  # drawn after the outline but *behind* the body

    def put(self, part: np.ndarray, x: int, y: int, sep=None, flip: bool = False, sep_sides: str = "lrtb") -> None:
        """Paste a part. `sep` = colour of a 1px separation line drawn around the part
        wherever it overlaps pixels that are already on the canvas (keeps limbs legible)."""
        if flip:
            part = E.flip_x(part)
        if sep is not None:
            m = part[:, :, 3] > 0
            ph, pw = m.shape
            big = np.zeros((ph + 2, pw + 2), bool)
            big[1:-1, 1:-1] = m
            g = np.zeros_like(big)
            if "t" in sep_sides:
                g[:-1, :] |= big[1:, :]
            if "b" in sep_sides:
                g[1:, :] |= big[:-1, :]
            if "l" in sep_sides:
                g[:, :-1] |= big[:, 1:]
            if "r" in sep_sides:
                g[:, 1:] |= big[:, :-1]
            ring = g & ~big
            ys, xs = np.nonzero(ring)
            for yy, xx in zip(ys, xs):
                tx, ty = x + xx - 1, y + yy - 1
                if 0 <= tx < self.w and 0 <= ty < self.h and self.img[ty, tx, 3] > 0:
                    self.img[ty, tx] = sep
        blit(self.img, part, x, y)

    def px(self, x, y, c, fx: bool = False):
        E.px(self.fx if fx else self.img, x, y, c)

    def finish(self, outline: bool = True) -> np.ndarray:
        body = E.outline(self.img, OUTLINE) if outline else self.img.copy()
        out = self.fx_under.copy()
        blit(out, body, 0, 0)
        blit(out, self.fx, 0, 0)
        return out


def ground_row(h: int, pivot_y: float = 0.1) -> int:
    """Last row of foot pixels (before the outline) so the feet stand on the pivot."""
    return int(round(h * (1 - pivot_y))) - 1


# --------------------------------------------------------------------------------------
# Colour utilities
# --------------------------------------------------------------------------------------
def brighten(img: np.ndarray, k: float = 1.1, add: int = 8, keep=(OUTLINE,)) -> np.ndarray:
    """Slightly brighter copy (elite look), leaving the outline colour untouched."""
    out = img.copy()
    m = img[:, :, 3] > 0
    for c in keep:
        m &= ~np.all(img == np.array(c, np.uint8), axis=-1)
    rgb = out[:, :, :3].astype(np.float32)
    rgb = np.clip(rgb * k + add, 0, 255)
    out[:, :, :3] = np.where(m[:, :, None], rgb.astype(np.uint8), out[:, :, :3])
    return out


def tint(img: np.ndarray, color, amount: float) -> np.ndarray:
    out = img.copy()
    m = img[:, :, 3] > 0
    rgb = out[:, :, :3].astype(np.float32)
    rgb = rgb * (1 - amount) + np.array(color[:3], np.float32) * amount
    out[:, :, :3] = np.where(m[:, :, None], np.clip(rgb, 0, 255).astype(np.uint8), out[:, :, :3])
    return out


def recolor_chars(img: np.ndarray, mapping: Dict) -> np.ndarray:
    return E.recolor(img, mapping)


# --------------------------------------------------------------------------------------
# Death puff (shared by all enemies): the body crumples into a bumpy cloud of dust, a few
# sparks fly out and the little gold collar is left glinting on the ground. No gore.
# --------------------------------------------------------------------------------------
DUST = [PAL["stone3"], PAL["stone4"], PAL["silver1"], PAL["silver2"], PAL["silver3"]]
SPARKS = (PAL["gold4"], PAL["gold3"])


def _shade_circle_px(dx: float, dy: float, r: float, ramp) -> Tuple[int, int, int, int]:
    nd = (dx * 0.72 + dy * 0.85) / max(r, 0.01)  # >0 towards bottom-right (away from light)
    d = math.hypot(dx, dy) / max(r, 0.01)
    v = 0.56 - nd * 0.62 + (1 - d) * 0.1
    th = (0.06, 0.26, 0.56, 0.86)[-(len(ramp) - 1):] if len(ramp) > 1 else ()
    return ramp[sum(1 for t in th if v > t)]


def cloud(w: int, h: int, blobs: Sequence[Tuple[float, float, float]], ramp=DUST, outline: bool = True) -> np.ndarray:
    """Bumpy cartoon cloud: circles drawn back-to-front, each shaded from the top-left,
    so every bump keeps its own lit rim. Hard pixels + dark outline."""
    img = E.new(w, h)
    for (cx, cy, r) in sorted(blobs, key=lambda b: -(b[0] * 0.3 + b[1])):  # back (low) first
        r = max(0.9, r)
        for yy in range(int(math.floor(cy - r - 1)), int(math.ceil(cy + r + 1)) + 1):
            for xx in range(int(math.floor(cx - r - 1)), int(math.ceil(cx + r + 1)) + 1):
                if not (0 <= xx < w and 0 <= yy < h):
                    continue
                dx, dy = xx + 0.5 - cx, yy + 0.5 - cy
                if dx * dx + dy * dy > r * r:
                    continue
                img[yy, xx] = _shade_circle_px(dx, dy, r, ramp)
    if outline:
        img = E.outline(img, OUTLINE)
    return img


def spark(img, x, y, big: bool = False, colors=SPARKS):
    E.px(img, x, y, colors[0])
    if big:
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            E.px(img, x + ox, y + oy, colors[1])


def squash(img: np.ndarray, fy: float, fx: float = 1.0, base: Optional[int] = None) -> np.ndarray:
    """Nearest-neighbour squash towards the ground row (keeps hard pixels)."""
    h, w = img.shape[:2]
    base = ground_row(h) + 1 if base is None else base
    x0, y0, x1, y1 = E.trim_box(img)
    cxm = (x0 + x1) / 2.0
    out = E.new(w, h)
    for yy in range(h):
        sy = base - (base - yy - 0.5) / fy
        iy = int(math.floor(sy))
        if not (0 <= iy < h):
            continue
        for xx in range(w):
            sx = cxm + (xx + 0.5 - cxm) / fx
            ix = int(math.floor(sx))
            if 0 <= ix < w:
                out[yy, xx] = img[iy, ix]
    return out


def collar_ring(img: np.ndarray, cx: int, gy: int, glint: bool = True) -> None:
    """The little gold collar left on the ground (3x2 ring)."""
    E.px(img, cx - 1, gy - 1, PAL["outline"])
    for x, c in ((cx - 1, PAL["gold2"]), (cx, PAL["gold1"]), (cx + 1, PAL["gold2"])):
        E.px(img, x, gy, c)
    E.px(img, cx - 1, gy - 1, PAL["gold3"])
    E.px(img, cx, gy - 1, PAL["outline"])
    E.px(img, cx + 1, gy - 1, PAL["gold3"])
    for x in (cx - 2, cx + 2):
        E.px(img, x, gy, PAL["outline"])
        E.px(img, x, gy - 1, PAL["outline"])
    for x in range(cx - 1, cx + 2):
        E.px(img, x, gy + 1, PAL["outline"])
        E.px(img, x, gy - 2, PAL["outline"])
    if glint:
        E.px(img, cx + 1, gy - 1, PAL["gold4"])


def death_frames(hurt: np.ndarray, seed: int, scale: float = 1.0, sparks=SPARKS, ramp=DUST,
                 collar: bool = True, flying: bool = False) -> List[np.ndarray]:
    """5 frames: flinch + dust at feet -> crumple into puff -> full puff -> puffs rise and
    break up, sparks fly -> last wisps, gold collar glinting on the ground."""
    h, w = hurt.shape[:2]
    g = ground_row(h)
    x0, y0, x1, y1 = E.trim_box(hurt)
    bw, bh = x1 - x0, y1 - y0
    cx = (x0 + x1) / 2.0
    cy = y0 + bh * (0.5 if flying else 0.58)
    R = max(2.5, min(bw, bh) * 0.36 * scale)
    sx = max(1.0, min(1.8, (bw / max(bh, 1)) ** 0.8))  # spread wide creatures sideways
    rnd = E.rng(seed)
    frames = []
    base = cy + R * 0.6 if flying else g

    # 0: flinch, dust kicks up at the feet (or a small burst around a flyer)
    f = E.new(w, h)
    blit(f, hurt, 0, 0)
    if flying:
        for i in range(3):
            a = i / 3.0 * math.tau + 0.4
            spark(f, cx + math.cos(a) * R * 1.2 * sx, cy + math.sin(a) * R * 0.9, i == 0, sparks)
    else:
        blit(f, cloud(w, h, [(cx - R * 0.7 * sx, g - 0.2, R * 0.38), (cx + R * 0.55 * sx, g + 0.1, R * 0.32)], ramp), 0, 0)
    frames.append(f)

    # 1: crumple (squashed body) swallowed by a rising puff
    f = E.new(w, h)
    blit(f, squash(hurt, 0.72, 1.08, None if not flying else int(cy + R)), 0, 0)
    bl = [(cx - R * 0.55 * sx, base - R * 0.35, R * 0.62), (cx + R * 0.5 * sx, base - R * 0.3, R * 0.58),
          (cx - R * 0.05, base - R * 0.85, R * 0.66)]
    if sx > 1.3:
        bl += [(cx - R * 1.1 * sx, base - R * 0.2, R * 0.45), (cx + R * 1.0 * sx, base - R * 0.25, R * 0.45)]
    blit(f, cloud(w, h, bl, ramp), 0, 0)
    for i in range(2):
        a = rnd.uniform(3.6, 5.8)
        spark(f, cx + math.cos(a) * R * 1.3 * sx, cy + math.sin(a) * R * 1.1, False, sparks)
    frames.append(f)

    # 2: full puff
    blobs = []
    for i in range(5):
        a = i / 5.0 * math.tau + rnd.uniform(-0.25, 0.25) + 0.3
        d = R * rnd.uniform(0.5, 0.7)
        blobs.append((cx + math.cos(a) * d * sx, cy + math.sin(a) * d * 0.75, R * rnd.uniform(0.5, 0.62)))
    blobs.append((cx - R * 0.15, cy - R * 0.2, R * 0.7))
    f = cloud(w, h, blobs, ramp)
    for i in range(4):
        a = i / 4.0 * math.tau + 0.5 + rnd.uniform(-0.3, 0.3)
        spark(f, cx + math.cos(a) * R * 1.45 * sx, cy + math.sin(a) * R * 1.25, i % 2 == 0, sparks)
    frames.append(f)

    # 3: breaks up into smaller rising puffs, collar drops
    bl = []
    for i, (bx, by, br) in enumerate(blobs[:5]):
        if i % 2 == 0 or i == 3:
            bl.append((bx + (bx - cx) * 0.45, by - R * 0.45 + (by - cy) * 0.3, br * 0.6))
    f = cloud(w, h, bl, ramp)
    if collar:
        collar_ring(f, int(round(cx)), g)
    for i in range(4):
        a = i / 4.0 * math.tau + 1.1
        E.px(f, cx + math.cos(a) * R * 1.7 * sx, cy - 1 + math.sin(a) * R * 1.45, sparks[1])
    frames.append(f)

    # 4: last dithered wisps; collar glints
    f = E.new(w, h)
    wisp = cloud(w, h, [(bx + (bx - cx) * 0.6, by - R * 0.9 + (by - cy) * 0.4, br * 0.6) for (bx, by, br) in bl],
                 ramp[1:], outline=False)
    m = E.dither_mask(wisp[:, :, 3] > 0, 0.55, "checker")
    f[m] = wisp[m]
    if collar:
        collar_ring(f, int(round(cx)), g, glint=True)
        E.px(f, int(round(cx)) + 2, g - 3, PAL["gold4"])
    frames.append(f)
    return frames


# --------------------------------------------------------------------------------------
# Enemy definition + clip building
# --------------------------------------------------------------------------------------
class EnemyDef:
    def __init__(self, eid: str, w: int, h: int, draw: Callable[[dict, bool], np.ndarray],
                 clips: Dict[str, Tuple[List[dict], float, bool]], hurt: dict, seed: int,
                 death_scale: float = 1.0, death_sparks=SPARKS, flying: bool = False):
        self.id, self.w, self.h, self.draw = eid, w, h, draw
        self.clips, self.hurt, self.seed, self.death_scale = clips, hurt, seed, death_scale
        self.death_sparks, self.flying = death_sparks, flying

    def frames(self, clip: str, elite: bool) -> List[np.ndarray]:
        if clip == "death":
            hurt = self.render(self.hurt, elite)
            fr = death_frames(hurt, self.seed + (7 if elite else 0), scale=self.death_scale,
                              sparks=self.death_sparks, flying=self.flying)
            return fr
        poses, _, _ = self.clips[clip]
        return [self.render(p, elite) for p in poses]

    def render(self, pose: dict, elite: bool) -> np.ndarray:
        img = self.draw(pose, elite)
        assert img.shape[:2] == (self.h, self.w), (self.id, img.shape)
        if elite:
            img = brighten(img)
        return img


def P(**kw) -> dict:
    return kw


# --------------------------------------------------------------------------------------
# RAT anatomy (rat_raider + powder_rat share head, legs and tail)
# --------------------------------------------------------------------------------------
def _ra(s: str, extra: Optional[Dict] = None) -> np.ndarray:
    lg = dict(RAT_LEG)
    if extra:
        lg.update(extra)
    return art(s, lg)


RAT_UPPER = _ra("""
....................
..........EC........
.........DnqB.......
.........CnqBCDD....
.......DDCBDDDDDDC..
......DDCDCDDD9ADDC.
.....CDDCBBCDDDDDDDn
.....BCC23445CC%%W..
....BC788834BBB.....
....BC7888874.......
...BC788888.........
...BC778877.........
...BB777766.........
....B6.6.6..........
""")
# elite: gold hem trim, gold shoulder stud, gold crest on the head
RAT_UPPER_ELITE = _ra("""
..........5.........
.........E45........
.........D43........
.........CnqB.......
.......DDCBDDDDDDC..
......DDCDCDDD9ADDC.
.....CDDCBBCDDDDDDDn
.....BCC23445CC%%W..
....BC784434BBB.....
....BC7843874.......
...BC788888.........
...BC778877.........
...B3444443.........
....3.3.3...........
""")

RAT_TAILS = [_ra("""
..q.
.q..
.q..
q...
q...
.q..
..q.
..qp
"""), _ra("""
.q..
.q..
q...
q...
.q..
.q..
..q.
..qp
"""), _ra("""
q...
.q..
..q.
..q.
.q..
.q..
..q.
..qp
""")]

RAT_LEGS = {
    "stand": _ra("""
BB.
BB.
.BB
.BB
qqq
"""),
    "fwd": _ra("""
BB..
.BB.
..BB
..BB
..qqq
"""),
    "back": _ra("""
.BB
BB.
BB.
B..
qq.
"""),
    "lift": _ra("""
BB.
.BB
.BBq
..qq
"""),
    "crouch": _ra("""
BBB.
.BBB
qqqq
"""),
}


def _dark_leg(p):
    return E.recolor(p, {PAL["rat1"]: PAL["rat0"], PAL["pink1"]: PAL["pink0"]})


def _light_leg(p):
    return E.recolor(p, {PAL["rat1"]: PAL["rat2"]})


RAT_LEGS_B = {k: _dark_leg(v) for k, v in RAT_LEGS.items()}
RAT_LEGS_F = {k: _light_leg(v) for k, v in RAT_LEGS.items()}

RAT_ARMS = {
    # shoulder pixel at part (0,0) -> placed at (9, 8)
    "hold": _ra("""
CB.....
.BD3...
..D2klmW
...3....
"""),
    "back": _ra("""
.....W.
....m..
C..l...
BD3k...
.D2....
"""),
    "thrust": _ra("""
C.........
.BD.3.....
..DD2kllmW
....3.....
"""),
    "slash": _ra("""
C.........
.BDD3.....
...D2kllmW
....3...5.
"""),
}

HURT_EYE = {PAL["red3"]: PAL["outline_soft"]}


def _rat_legs(c: Canvas, legs, g: int, hip_b: int, hip_f: int, bx: int = 0) -> Tuple[np.ndarray, int, int]:
    """Draw the back leg now; return (front part, x, y) to draw after the body."""
    def place(name, hip):
        part = RAT_LEGS[name]
        x = hip + (-1 if name == "back" else 0)
        y = g - part.shape[0] + 1 + (-1 if name == "lift" else 0)
        return x, y
    nb, nf = legs
    xb, yb = place(nb, hip_b + bx)
    c.put(RAT_LEGS_B[nb], xb, yb)
    xf, yf = place(nf, hip_f + bx)
    return RAT_LEGS_F[nf], xf, yf


def draw_rat_raider(pose: dict, elite: bool) -> np.ndarray:
    c = Canvas(20, 20)
    g = ground_row(20)
    bx, by = pose.get("bx", 0), pose.get("by", 0)
    c.put(RAT_TAILS[pose.get("tail", 0)], 1 + bx, 5 + by)
    front, fx_, fy_ = _rat_legs(c, pose.get("legs", ("stand", "stand")), g, 4, 8, pose.get("lx", 0))
    up = RAT_UPPER_ELITE if elite else RAT_UPPER
    if pose.get("hurt"):
        up = E.recolor(up, HURT_EYE)
    c.put(up, bx, by)
    c.put(front, fx_, fy_, sep=PAL["rat0"])
    arm = RAT_ARMS[pose.get("arm", "hold")]
    ax, ay = pose.get("ax", 0), pose.get("ay", 0)
    arm_y = {"back": 5}.get(pose.get("arm", "hold"), 8)
    c.put(arm, 9 + bx + ax, arm_y + by + ay, sep=OUTLINE)
    img = c.finish()
    if pose.get("glint"):
        gx, gy = pose["glint"]
        spark(img, gx, gy, True, (PAL["white"], PAL["gold3"]))
    return img


RAT_RAIDER = EnemyDef(
    "rat_raider", 20, 20, draw_rat_raider,
    {
        "walk": ([P(legs=("back", "fwd"), tail=0),
                  P(legs=("lift", "stand"), by=-1, tail=1),
                  P(legs=("fwd", "back"), tail=2),
                  P(legs=("stand", "lift"), by=-1, tail=1)], 8, True),
        "attack": ([P(legs=("stand", "stand"), bx=-1, arm="back", tail=0),
                    P(legs=("back", "fwd"), bx=1, arm="thrust", tail=1),
                    P(legs=("back", "fwd"), bx=1, arm="slash", tail=2, glint=(17, 9)),
                    P(legs=("stand", "stand"), arm="hold", tail=1)], 10, False),
    },
    hurt=P(legs=("stand", "stand"), bx=-1, hurt=True, arm="hold", tail=2),
    seed=101,
)


# --------------------------------------------------------------------------------------
# Shared limb helper: two-segment limb (hip -> joint -> paw), upper segment 2 px thick.
# --------------------------------------------------------------------------------------
def limb(img: np.ndarray, pts, col_hi, col_lo, paw=None, w1: int = 2, w2: int = 1, paw_w: int = 2) -> None:
    (x0, y0), (x1, y1), (x2, y2) = pts

    def seg(a, b, col, width):
        E.line(img, a[0], a[1], b[0], b[1], col)
        if width >= 2:
            E.line(img, a[0] + 1, a[1], b[0] + 1, b[1], col)
    seg((x0, y0), (x1, y1), col_hi, w1)
    seg((x1, y1), (x2, y2), col_lo, w2)
    if paw is not None:
        for i in range(paw_w):
            E.px(img, x2 + i, y2, paw)


def dust_kick(img: np.ndarray, x: float, y: float, r: float = 1.4) -> None:
    """Tiny dust puff behind a planted foot (drawn after the outline)."""
    blit(img, cloud(img.shape[1], img.shape[0], [(x, y, r), (x - r * 0.9, y + 0.4, r * 0.7)]), 0, 0)


# --------------------------------------------------------------------------------------
# HOUND RUNNER (24x20): lean sighthound, low stretched gallop, ears pinned back
# --------------------------------------------------------------------------------------
HOUND_LEG = {"A": PAL["brown0"], "B": PAL["brown1"], "C": PAL["brown2"], "D": PAL["brown3"],
             "E": PAL["bone2"], "H": PAL["bone3"]}


def _ha(s):
    return art(s, HOUND_LEG)


HOUND_BODY = _ha("""
....DDDD8888DDD.....
...CDDD788888DDDC...
..BCCC7788888CCDDC..
..BBC.6777776BCDDE..
...BB..34443.BBCEE..
....B.........BCE...
""")
HOUND_BODY_ELITE = _ha("""
....DD44444444D.....
...CDD3788883DDDC...
..BCCC7788888CCDDC..
..BBC.6777776BCDDE..
...BB.3454543BBCEE..
....B..3.3.3..BCE...
""")
HOUND_HEADS = {
    "run": _ha("""
..AB........
.ABBDDDD....
BBCDDDD9DD...
BCCDDDDDDDDDx
.B5CCCDDD%%%.
.B4BBBBB.....
.34..........
"""),
    "bite": _ha("""
..AB.........
.ABBDDDD.....
BBCDDDD9DDDDx
BCCDDDD%WW%..
.B5CCCDDDDD..
.B4BBBBBB%...
.34..........
"""),
    "snap": _ha("""
..AB........
.ABBDDDD....
BBCDDDD9DD...
BCCDDDDDDDDDx
.B5CCCDDWW%%.
.B4BBBBBB....
.34..........
"""),
}
HOUND_CREST = _ha("""
.5.
454
.3.
""")
HOUND_TAILS = [_ha("""
DC......
.BCC....
....BCC.
"""), _ha("""
........
DBCC....
....BCC.
"""), _ha("""
........
........
DBCCBCC.
""")]

# joint sets: nf/ff = near/far front, nh/fh = near/far hind: [hip, joint, paw]
HOUND_LEGS = {
    "ext": dict(nf=[(15, 12), (18, 15), (20, 16)], ff=[(14, 12), (16, 15), (18, 17)],
                nh=[(5, 12), (3, 14), (1, 16)], fh=[(6, 12), (4, 15), (3, 17)]),
    "land": dict(nf=[(15, 12), (15, 15), (14, 17)], ff=[(14, 12), (13, 15), (12, 17)],
                 nh=[(5, 12), (7, 14), (9, 15)], fh=[(6, 12), (7, 15), (8, 16)]),
    "gather": dict(nf=[(15, 12), (14, 14), (11, 15)], ff=[(14, 12), (12, 14), (10, 16)],
                   nh=[(5, 12), (8, 14), (10, 16)], fh=[(6, 12), (9, 14), (11, 17)]),
    "push": dict(nf=[(15, 12), (17, 14), (18, 15)], ff=[(14, 12), (16, 14), (17, 16)],
                 nh=[(5, 12), (4, 15), (2, 17)], fh=[(6, 12), (5, 15), (4, 17)]),
    "stand": dict(nf=[(15, 12), (16, 14), (16, 17)], ff=[(14, 12), (14, 15), (14, 17)],
                  nh=[(5, 12), (6, 14), (5, 17)], fh=[(6, 12), (7, 15), (7, 17)]),
    "crouch": dict(nf=[(15, 12), (17, 15), (17, 17)], ff=[(14, 12), (15, 15), (15, 17)],
                   nh=[(5, 12), (7, 15), (5, 17)], fh=[(6, 12), (8, 15), (7, 17)]),
}


def draw_hound_runner(pose: dict, elite: bool) -> np.ndarray:
    c = Canvas(24, 20)
    dx, dy = pose.get("bx", 0), pose.get("by", 0)
    L = HOUND_LEGS[pose.get("legs", "stand")]
    sh = lambda pts, ox, oy: [(pts[0][0] + ox, pts[0][1] + oy)] + list(pts[1:])  # hips follow the body
    c.put(HOUND_TAILS[pose.get("tail", 0)], dx, 7 + dy)
    limb(c.img, sh(L["fh"], dx, dy), PAL["brown1"], PAL["brown0"], PAL["bone1"])
    limb(c.img, sh(L["ff"], dx, dy), PAL["brown1"], PAL["brown0"], PAL["bone1"])
    c.put(HOUND_BODY_ELITE if elite else HOUND_BODY, dx, 8 + dy)
    limb(c.img, sh(L["nh"], dx, dy), PAL["brown2"], PAL["brown2"], PAL["bone3"])
    limb(c.img, sh(L["nf"], dx, dy), PAL["brown2"], PAL["brown3"], PAL["bone3"])
    head = HOUND_HEADS[pose.get("head", "run")]
    if pose.get("hurt"):
        head = E.recolor(head, HURT_EYE)
    hx, hy = 12 + dx + pose.get("hx", 0), 4 + dy + pose.get("hy", 0)
    c.put(head, hx, hy)
    if elite:
        c.put(HOUND_CREST, hx + 2, hy - 2)
    img = c.finish()
    for (kx, ky) in pose.get("dust", []):
        dust_kick(img, kx, ky, 1.0)
    if pose.get("glint"):
        gx, gy = pose["glint"]
        spark(img, gx, gy, True, (PAL["white"], PAL["gold3"]))
    return img


HOUND_RUNNER = EnemyDef(
    "hound_runner", 24, 20, draw_hound_runner,
    {
        "walk": ([P(legs="ext", tail=0, dust=[(2.5, 16.5)]),
                  P(legs="land", by=1, tail=1),
                  P(legs="gather", tail=2),
                  P(legs="push", by=-1, tail=1, dust=[(3.5, 16.8)])], 8, True),
        "attack": ([P(legs="crouch", bx=-1, by=1, head="run", hy=1, tail=2),
                    P(legs="ext", bx=1, head="bite", tail=0, dust=[(3.5, 16.5)]),
                    P(legs="ext", bx=2, head="snap", tail=0, glint=(21, 10)),
                    P(legs="stand", head="run", tail=1)], 10, False),
    },
    hurt=P(legs="crouch", bx=-1, hurt=True, head="run", tail=2),
    seed=202,
)


# --------------------------------------------------------------------------------------
# SHIELD GUARD (24x28): stocky bulldog behind a gold-rimmed tower shield
# --------------------------------------------------------------------------------------
BULL_LEG = {"A": PAL["bone0"], "B": PAL["bone1"], "C": PAL["bone2"], "D": PAL["bone3"],
            "M": PAL["brown1"], "N": PAL["brown2"]}


def _ba(s):
    return art(s, BULL_LEG)


SG_HEAD = _ba("""
.....ijkkkj....
....ijklllmj...
...ijjkkkkjj...
.NM.DDDDDDD.MN.
.MCD%%DDD%%DCM.
..CD9xDDD9xDC..
..CDDDDxDDDDC..
.BCDDDxxxDDDCB.
BCCDWNNNNNWDCCB
BCCCWMMMMMWCCCB
.BCCCMMMMMCCCB.
..ABBBBBBBBBA..
""")
SG_HEAD_ELITE = _ba("""
.......5.......
......545......
.....i434i.....
....ijklllmj...
...3444444443..
.NM.DDDDDDD.MN.
.MCD%%DDD%%DCM.
..CD9xDDD9xDC..
..CDDDDxDDDDC..
.BCDDDxxxDDDCB.
BCCDWNNNNNWDCCB
BCCCWMMMMMWCCCB
.BCCCMMMMMCCCB.
..ABBBBBBBBBA..
""")
SG_BODY = _ba("""
...iikkki...
..ijkllkki..
.A2345432i..
.Bjk7887kji.
ABjk7887kji.
ABjk7887kji.
AAij7667ji..
.Aij6776ji..
..ij6..6j...
""")
SG_BODY_ELITE = _ba("""
...i3443i...
..i4kllk3i..
.A2345432i..
.B3k7887kji.
AB3k7887kji.
ABjk7887kji.
AAij7667ji..
.Ai34554ji..
..i3...3j...
""")
SG_SHIELD = art("""
.23333332.
2344444432
3478888763
3478888763
3478444763
3474888463
3474888463
3478444763
3478848763
3478888763
3478888763
3478888763
3477777663
3476666663
2333333332
.22222222.
""")
SG_SHIELD_ELITE = art("""
.24444442.
2455555542
3478888763
3478448763
3474554763
3445885443
3445885443
3474554763
3478448763
3478848763
3478888763
3548888653
3477777663
3546666653
2444444442
.23333332.
""")
SG_LEG = {
    "stand": art("""
.jkk
.jkk
.kkl
ijkkl
"""),
    "lift": art("""
.jkk
.jkk
ijkkl
"""),
}


def draw_shield_guard(pose: dict, elite: bool) -> np.ndarray:
    c = Canvas(24, 28)
    g = ground_row(28)
    bx, by = pose.get("bx", 0), pose.get("by", 0)
    lb, lf = pose.get("legs", ("stand", "stand"))
    for name, x in ((lb, 5), (lf, 10)):
        part = SG_LEG[name]
        c.put(part, x + pose.get("lx", 0), g - part.shape[0] + 1 - (1 if name == "lift" else 0))
    c.put(SG_BODY_ELITE if elite else SG_BODY, 3 + bx, 11 + by)
    head = SG_HEAD_ELITE if elite else SG_HEAD
    if pose.get("hurt"):
        head = E.recolor(head, HURT_EYE)
    hy = 1 + by + pose.get("hy", 0) - (2 if elite else 0)
    c.put(head, 5 + bx + pose.get("hx", 0), hy)
    sx, sy = pose.get("sx", 0), pose.get("sy", 0)
    c.put(SG_SHIELD_ELITE if elite else SG_SHIELD, 11 + bx + sx, 11 + by + sy, sep=OUTLINE)
    img = c.finish()
    if pose.get("impact"):
        ix, iy = pose["impact"]
        for (ox, oy) in ((0, 0), (1, -3), (1, 3)):
            spark(img, ix + ox, iy + oy, oy == 0, (PAL["white"], PAL["gold3"]))
    return img


SHIELD_GUARD = EnemyDef(
    "shield_guard", 24, 28, draw_shield_guard,
    {
        "walk": ([P(legs=("stand", "lift")),
                  P(legs=("stand", "stand"), by=1, sy=0),
                  P(legs=("lift", "stand")),
                  P(legs=("stand", "stand"), by=1, sy=0)], 8, True),
        "attack": ([P(bx=-1, sx=-1, legs=("stand", "stand"), hy=1),
                    P(bx=1, sx=1, legs=("stand", "lift")),
                    P(bx=1, sx=2, legs=("stand", "stand"), impact=(23, 17)),
                    P(bx=0, sx=0, legs=("stand", "stand"))], 10, False),
    },
    hurt=P(bx=-1, sx=-1, hurt=True, legs=("stand", "stand")),
    seed=303,
)


# --------------------------------------------------------------------------------------
# CROW ARCHER (22x24): upright crow soldier with a bow (walks, does not fly)
# --------------------------------------------------------------------------------------
CROW_LEG = {"A": PAL["crow0"], "B": PAL["crow1"], "C": PAL["crow2"], "D": PAL["stone3"], "E": PAL["stone4"],
            "S": PAL["silver1"], "T": PAL["silver2"]}


def _ca(s):
    return art(s, CROW_LEG)


CROW_HEADS = {
    "idle": _ca("""
...CDEE.....
..CDDDEEE...
.CDDDDD9xD..
BCDDDDDDD4455
BCCDDDDD33332
.BCCCDD2222..
..BBCC.......
"""),
    "peck": _ca("""
...CDEE......
..CDDDEEE....
.CDDDDD9xD...
BCDDDDDDD44555
BCCDDDDD%....
.BCCCDD333332
..BBCC.2222..
"""),
}
CROW_CREST = art("""
.5.5
4.44
.34.
""")
CROW_BODY = _ca("""
....BCCD....
...BC2345...
..BCC78888..
.BCD788888..
.BCC788887..
BCCC777776..
BCCC677776..
BBCC66666B..
.BBCCBBBB...
..BBBBBB....
""")
CROW_BODY_ELITE = _ca("""
....BCCD....
...BC2345...
..BC344443..
.BCD788883..
.BCC788887..
BCCC777776..
BCCC677776..
BBCC34543B..
.BBC3BBB3...
..BBBBBB....
""")
CROW_TAILS = [_ca("""
DC.....
CCB....
BCCB...
.BBCB..
..BBB..
"""), _ca("""
.......
DCB....
CCCB...
.BBCB..
..BBB..
""")]
CROW_QUIVER = art("""
W.W.
SWS.
.LL.
LMNL
LMNL
LMN.
.LM.
""", {"S": PAL["silver1"]})
CROW_BOW = art("""
vu...
.vu..
..vu.
...v.
...u.
...3.
...4.
...3.
...u.
...v.
..vu.
.vu..
vu...
""")
CROW_BOW_ELITE = art("""
45...
.34..
..vu.
...v.
...u.
...3.
...4.
...3.
...u.
...v.
..vu.
.34..
45...
""")
CROW_WING = _ca("""
BCD..
.BCDD
..BD3
""")
CROW_WING_DRAW = _ca("""
BCDD.
.BCD3
""")
CROW_LEGS = {
    "stand": art("""
l.
l.
l.
kll
"""),
    "fwd": art("""
l..
.l.
.l.
.kll
"""),
    "back": art("""
.l
.l
l.
kl.
"""),
    "lift": art("""
l..
.l.
kll
"""),
}
CROW_LEGS_B = {k: E.recolor(v, {PAL["iron3"]: PAL["iron2"], PAL["iron2"]: PAL["iron1"]}) for k, v in CROW_LEGS.items()}


def _arrow(c: Canvas, x: int, y: int, length: int = 9) -> None:
    """Horizontal arrow, nock at x, head pointing right."""
    E.px(c.img, x, y - 1, PAL["red3"])
    E.px(c.img, x, y + 1, PAL["red3"])
    E.px(c.img, x + 1, y - 1, PAL["white"])
    E.px(c.img, x + 1, y + 1, PAL["white"])
    for i in range(length - 2):
        E.px(c.img, x + i, y, PAL["wood3"])
    E.px(c.img, x + length - 2, y, PAL["iron4"])
    E.px(c.img, x + length - 1, y, PAL["white"])
    E.px(c.img, x + length - 2, y - 1, PAL["iron3"])
    E.px(c.img, x + length - 2, y + 1, PAL["iron3"])


def draw_crow_archer(pose: dict, elite: bool) -> np.ndarray:
    c = Canvas(22, 24)
    g = ground_row(24)
    bx, by = pose.get("bx", 0), pose.get("by", 0)
    c.put(CROW_QUIVER, 2 + bx, 5 + by)
    c.put(CROW_TAILS[pose.get("tail", 0)], 1 + bx, 14 + by)
    lb, lf = pose.get("legs", ("stand", "stand"))
    for name, hip, parts in ((lb, 7, CROW_LEGS_B), (lf, 10, CROW_LEGS)):
        part = parts[name]
        x = hip + {"back": -1}.get(name, 0)
        y = g - part.shape[0] + 1 - (1 if name == "lift" else 0)
        c.put(part, x, y)
    c.put(CROW_BODY_ELITE if elite else CROW_BODY, 3 + bx, 8 + by)
    head = CROW_HEADS[pose.get("head", "idle")]
    if pose.get("hurt"):
        head = E.recolor(head, HURT_EYE)
    hx, hy = 6 + bx + pose.get("hx", 0), 1 + by + pose.get("hy", 0)
    c.put(head, hx, hy)
    if elite:
        c.put(CROW_CREST, hx + 2, hy - 2)
    # bow: bx2/by2 = bow offset, draw = how far the string is pulled back (0 = straight)
    bow = CROW_BOW_ELITE if elite else CROW_BOW
    wx, wy = 15 + bx + pose.get("wx", 0), 8 + by + pose.get("wy", 0)
    c.put(bow, wx, wy, sep=OUTLINE)
    draw = pose.get("draw", 0)
    top, bot, mid = (wx, wy), (wx, wy + 12), (wx - draw, wy + 6)
    if pose.get("arrow"):
        _arrow(c, mid[0], mid[1], 8)
    c.put(CROW_WING_DRAW if draw else CROW_WING, (mid[0] - 3 if draw else 12 + bx), (mid[1] - 1 if draw else 11 + by), sep=OUTLINE)
    img = c.finish()
    # bowstring: thin light line drawn after the outline
    sc = PAL["silver2"]
    if pose.get("twang"):
        pts = [(wx, wy + i + 1) for i in range(11)]
        for i, (x, y) in enumerate(pts):
            E.px(img, x + (1 if i in (3, 4, 5) else 0), y, sc)
        for (x, y) in ((wx + 6, wy + 5), (wx + 5, wy + 7), (wx + 7, wy + 6)):
            E.px(img, x, y, PAL["white"])
    else:
        E.line(img, top[0], top[1] + 1, mid[0], mid[1], sc)
        E.line(img, mid[0], mid[1], bot[0], bot[1] - 1, sc)
    if pose.get("glint"):
        gx, gy = pose["glint"]
        spark(img, gx, gy, True, (PAL["white"], PAL["gold3"]))
    return img


CROW_ARCHER = EnemyDef(
    "crow_archer", 22, 24, draw_crow_archer,
    {
        "walk": ([P(legs=("back", "fwd"), tail=0),
                  P(legs=("lift", "stand"), by=-1, tail=1, wy=-1),
                  P(legs=("fwd", "back"), tail=0),
                  P(legs=("stand", "lift"), by=-1, tail=1, wy=-1)], 8, True),
        "attack": ([P(bx=-1, hx=-1, head="idle", tail=1),
                    P(bx=1, hx=2, hy=1, head="peck", legs=("back", "fwd"), tail=0),
                    P(bx=1, hx=2, hy=1, head="idle", legs=("back", "fwd"), tail=0, glint=(20, 5)),
                    P(head="idle", tail=1)], 10, False),
        "shoot": ([P(wx=-2, wy=-1, arrow=True, draw=0, tail=1),
                   P(wx=-1, wy=-1, arrow=True, draw=2, bx=-1, tail=1),
                   P(wx=-1, wy=-1, arrow=True, draw=4, bx=-1, tail=0, legs=("back", "stand")),
                   P(wx=-1, wy=-1, twang=True, tail=0)], 10, False),
    },
    hurt=P(bx=-1, hurt=True, tail=1),
    seed=404,
)


# --------------------------------------------------------------------------------------
# BAT (14x12): tiny crimson-winged bat with a gold collar tag (spawns in swarms of 5)
# --------------------------------------------------------------------------------------
BAT_BODY = {
    "idle": _ra("""
B..B.
BCDCB
BC5C5
BCCCB
.B3W.
..B..
"""),
    "bite": _ra("""
B..B.
BCDCB
BC5C5
BCW%W
.B3..
..B..
"""),
}
BAT_BODY_ELITE = {k: v for k, v in BAT_BODY.items()}
BAT_BODY_ELITE["idle"] = _ra("""
..5..
B.4.B
BCDCB
BC5C5
BCCCB
.343.
..4..
""")
BAT_BODY_ELITE["bite"] = _ra("""
..5..
B.4.B
BCDCB
BC5C5
BCW%W
.343.
..4..
""")
BAT_WINGS = {
    "up": art("""
....9
...98
..988
.9878
98778
87.7.
"""),
    "mid": art("""
99999.
788889
77.878
7...7.
"""),
    "down": art("""
9.....
89....
789...
7789..
.7788.
.7.78.
"""),
    "fold": art("""
99....
7889..
.7879.
.7.78.
"""),
}
BAT_WING_GOLD = {PAL["red3"]: PAL["gold3"]}


def draw_bat(pose: dict, elite: bool) -> np.ndarray:
    c = Canvas(14, 12)
    st = pose.get("wings", "mid")
    by = pose.get("by", 0)
    bx = pose.get("bx", 0)
    w = BAT_WINGS[st]
    if elite:
        w = E.recolor(w, BAT_WING_GOLD)
    body_y = 4 + by
    wy = {"up": body_y - 4, "mid": body_y + 1, "down": body_y + 1, "fold": body_y + 1}[st]
    c.put(w, 9 + bx, wy)
    c.put(E.flip_x(w), 5 - w.shape[1] + bx, wy)
    body = (BAT_BODY_ELITE if elite else BAT_BODY)[pose.get("face", "idle")]
    if pose.get("hurt"):
        body = E.recolor(body, {PAL["gold4"]: PAL["outline_soft"]})
    c.put(body, 4 + bx, body_y - (1 if elite else 0))
    img = c.finish()
    if pose.get("glint"):
        gx, gy = pose["glint"]
        spark(img, gx, gy, False, (PAL["white"], PAL["gold3"]))
    return img


BAT = EnemyDef(
    "bat", 14, 12, draw_bat,
    {
        "fly": ([P(wings="up", by=1), P(wings="mid"), P(wings="down", by=-1), P(wings="fold")], 12, True),
        "attack": ([P(wings="up", by=1, bx=-1),
                    P(wings="fold", bx=1, by=1, face="bite"),
                    P(wings="down", bx=1, by=1, face="bite", glint=(9, 9)),
                    P(wings="mid")], 10, False),
    },
    hurt=P(wings="fold", hurt=True),
    seed=505,
    death_scale=1.3,
    flying=True,
)


# --------------------------------------------------------------------------------------
# BELL PRIEST (22x28): goat priest in pale robes with a golden hand-bell (support/healer)
# --------------------------------------------------------------------------------------
PRIEST_LEG = {"A": PAL["bone0"], "B": PAL["bone1"], "C": PAL["bone2"], "D": PAL["bone3"], "H": PAL["bone4"],
              "K": PAL["brown0"], "M": PAL["brown1"], "N": PAL["brown2"], "O": PAL["brown3"],
              "s": PAL["snow1"], "t": PAL["snow2"], "T": PAL["snow3"]}


def _pa(s):
    return art(s, PRIEST_LEG)


_PR_HEAD_SRC = """
.....DHD.....
....DH4HD....
...CD353DC...
...C33333C...
..M.OOOOO.M..
.MMNTTOTTNMM.
.MMN5xO5xNMM.
.MMNOOxOONMM.
.MM.TTxTT.MM.
.M..NTTTN..M.
.....NNN.....
"""
PR_HEAD = _pa(_PR_HEAD_SRC)
PR_HEAD_HURT = _pa(_PR_HEAD_SRC.replace("N5xO5xN", "N%%O%%N"))
# elite: gilded mitre with a red gem
_PR_HEAD_ELITE_SRC = """
.....454.....
....45954....
...3458543...
...2344432...
..M.OOOOO.M..
.MMNTTOTTNMM.
.MMN5xO5xNMM.
.MMNOOxOONMM.
.MM.TTxTT.MM.
.M..NTTTN..M.
.....NNN.....
"""
PR_HEAD_ELITE = _pa(_PR_HEAD_ELITE_SRC)
PR_HEAD_ELITE_HURT = _pa(_PR_HEAD_ELITE_SRC.replace("N5xO5xN", "N%%O%%N"))
PR_ROBE = [_pa("""
....23445....
...CD8888D...
..CDD8778DC..
.BCDD8778DDC.
.BCDDD87DDDC.
.BCDDD87DDDDC
BBCDDD87DDDDC
BBCDDD87DDDDC
BBCDDD87DDDDC
BBCDDD87DDDDC
BBCCDD5.5DDCC
BBCCCDDDDDCCC
BABCCCCCCCCCB
.AABBBBBBBBA.
"""), _pa("""
....23445....
...CD8888D...
..CDD8778DC..
.BCDD8778DDC.
.BCDDD87DDDC.
.BCDDD87DDDDC
BBCDDD87DDDDC
BBCDDD87DDDDC
BBCDDD87DDDDC
BBCDDD87DDDDC
BBCCDD5.5DDDC
.BCCCDDDDDDCC
.BBCCCCCCCCCC
..AABBBBBBBBA
""")]
PR_TRIM = {PAL["bone1"]: PAL["gold2"], PAL["bone0"]: PAL["gold1"]}
PR_HOOVES = art("""
jk...jk
""")
PR_ARM = {
    "hold": _pa("""
DDC..
.CDDC
..BCO
"""),
    "raise": _pa("""
....O
...DC
..DC.
.DC..
DC...
"""),
    "swing": _pa("""
DDC...
.CDDDO
"""),
}
PR_BELL = {
    "up": art("""
..u..
..v..
.343.
34453
34443
23332
..5..
"""),
    "tilt_r": art("""
.u....
..v...
..343.
.34453
.34443
..2333
....5.
"""),
    "tilt_l": art("""
....u.
...v..
.343..
34453.
34443.
2333..
.5....
"""),
    "down": art("""
..5..
23332
34443
34453
.343.
..v..
..u..
"""),
}


def _ring(img, cx, cy, rx, ry, colors, dither=False):
    """1px ellipse ring (FX), light on the top-left arc."""
    n = int(max(rx, ry) * 8)
    pts = set()
    for i in range(n):
        a = i / n * math.tau
        x, y = int(round(cx + math.cos(a) * rx)), int(round(cy + math.sin(a) * ry))
        pts.add((x, y, a))
    for (x, y, a) in pts:
        if dither and (x + y) % 2:
            continue
        lit = math.cos(a) * -0.7 + math.sin(a) * -0.7
        E.px(img, x, y, colors[0] if lit > 0.2 else colors[1])


def draw_bell_priest(pose: dict, elite: bool) -> np.ndarray:
    c = Canvas(22, 28)
    g = ground_row(28)
    bx, by = pose.get("bx", 0), pose.get("by", 0)
    halo = pose.get("halo", 0)
    if halo:
        hc = (PAL["gold4"], PAL["gold3"])
        _ring(c.fx_under, 11 + bx, 6 + by, 7 + (1 if halo == 3 else 0), 6 + (1 if halo == 3 else 0), hc, dither=halo in (1, 4))
        if halo in (2, 3):
            _ring(c.fx_under, 11 + bx, 6 + by, 9 + halo - 2, 8 + halo - 2, (PAL["gold3"], PAL["gold2"]), dither=True)
    hv = PR_HOOVES
    c.put(hv, 7 + pose.get("hoof", 0), g)
    robe = PR_ROBE[pose.get("robe", 0)]
    if elite:
        robe = E.recolor(robe, PR_TRIM) if False else robe
    c.put(robe, 4 + bx, 11 + by)
    if elite:
        # gold hem + cuffs trim
        for x in range(5 + bx, 17 + bx):
            if c.img[11 + by + 12, x, 3] > 0:
                c.img[11 + by + 12, x] = PAL["gold2"] if (x % 2) else PAL["gold3"]
    if pose.get("hurt"):
        head = PR_HEAD_ELITE_HURT if elite else PR_HEAD_HURT
    else:
        head = PR_HEAD_ELITE if elite else PR_HEAD
    c.put(head, 5 + bx + pose.get("hx", 0), 1 + by + pose.get("hy", 0))
    arm = pose.get("arm", "hold")
    ax, ay = {"hold": (12, 13), "raise": (12, 8), "swing": (12, 14)}[arm]
    c.put(PR_ARM[arm], ax + bx, ay + by, sep=OUTLINE)
    bell = pose.get("bell", "up")
    blx, bly = pose.get("bell_at", {"hold": (16, 10), "raise": (15, 2), "swing": (17, 13)}[arm])
    c.put(PR_BELL[bell], blx + bx, bly + by, sep=OUTLINE)
    img = c.finish()
    for (x, y) in pose.get("sparkles", []):
        spark(img, x + bx, y + by, True, (PAL["white"], PAL["gold3"]))
    if pose.get("dings"):
        # little ringing arcs beside the bell
        cx, cy = blx + bx + 2, bly + by + 3
        for (ox, oy) in ((4, -1), (5, 0), (4, 1), (-2, -1), (-3, 0), (-2, 1)):
            E.px(img, cx + ox, cy + oy, PAL["gold4"])
    if pose.get("impact"):
        ix, iy = pose["impact"]
        spark(img, ix, iy, True, (PAL["white"], PAL["gold3"]))
    return img


BELL_PRIEST = EnemyDef(
    "bell_priest", 22, 28, draw_bell_priest,
    {
        "walk": ([P(robe=0, hoof=0),
                  P(robe=1, by=-1, hoof=1),
                  P(robe=0, hoof=0, bell_at=(16, 11)),
                  P(robe=1, by=-1, hoof=-1)], 8, True),
        "attack": ([P(arm="raise", bell="tilt_l", bx=-1),
                    P(arm="swing", bell="down", bx=1),
                    P(arm="swing", bell="down", bx=1, impact=(20, 21)),
                    P(arm="hold", bell="up")], 10, False),
        "cast": ([P(arm="raise", bell="up", halo=1, sparkles=[(3, 8)]),
                  P(arm="raise", bell="tilt_r", halo=2, dings=True, sparkles=[(2, 5), (20, 15)]),
                  P(arm="raise", bell="tilt_l", halo=3, dings=True, sparkles=[(1, 12), (19, 18), (4, 2)]),
                  P(arm="raise", bell="up", halo=4, sparkles=[(2, 14)])], 10, False),
    },
    hurt=P(bx=-1, hurt=True),
    seed=606,
)


# --------------------------------------------------------------------------------------
# POWDER RAT (20x20): sapper rat hauling a banded powder keg with a lit fuse
# --------------------------------------------------------------------------------------
PW_BODY = _ra("""
..........EC......
.........DnqB.....
.........CnqBCDD..
........DDBDDDDDDC
.......CDkmD9ADDDC
.......BCDDDDDDDDn
......BCC34CC%%W..
.....BCCLMN3BB....
....BCCCLMDD......
....BCCCCBB.......
....BBCCCB........
.....B6.6.........
""")
PW_BODY_ELITE = _ra("""
..........EC......
.........DnqB.....
.........CnqBCDD..
........DDBDDDDDDC
.......CD45D9ADDDC
.......BCDDDDDDDDn
......BCC34CC%%W..
.....BCCL4N3BB....
....BCCCL4DD......
....BCCCCBB.......
....BBCCCB........
.....B3.3.........
""")
PW_BODY_WIDE = PW_BODY.copy()  # eyes-wide variant for fuse/charge (white eye)
PW_BODY_WIDE[4, 12] = PAL["white"]
PW_BODY_WIDE_E = PW_BODY_ELITE.copy()
PW_BODY_WIDE_E[4, 12] = PAL["white"]
PW_KEG = art("""
...iiiii...
..iuvuvuvi.
..ijkllkji.
.wvuvuvuvw.
.w8988887w.
.wvuvuvuvw.
..jkllkkj..
...wwwww...
""")
PW_KEG_ELITE = art("""
...22222...
..2uvuvuv2.
..2344432..
.wvuvuvuvw.
.w8988887w.
.wvuvuvuvw.
..2344432..
...wwwww...
""")
PW_ARMS = {
    "hold": _ra("""
CB..
.BDD
"""),
    "brace": _ra("""
..DD
.BD.
CB..
"""),
    "pump": _ra("""
CB...
.BD..
..DD.
"""),
    "shove": _ra("""
CB....
.BDDDD
"""),
}
FUSE_TIP = (7, 0)  # relative to the keg origin


def _spark_star(img, x, y, kind: int) -> None:
    """Lit-fuse sparks. kind 0 = ember, 1 = plus, 2 = cross, 3 = big burst."""
    W, Y, F, R = PAL["white"], PAL["fire4"], PAL["fire3"], PAL["red3"]
    if kind == 0:
        E.px(img, x, y, PAL["fire2"])
        E.px(img, x + 1, y - 1, PAL["fire3"])
        return
    if kind == 1:
        E.px(img, x, y, W)
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            E.px(img, x + ox, y + oy, Y)
        for ox, oy in ((2, 0), (-2, 0), (0, -2)):
            E.px(img, x + ox, y + oy, F)
        E.px(img, x + 2, y - 2, R)
        return
    if kind == 2:
        E.px(img, x, y, W)
        for ox, oy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
            E.px(img, x + ox, y + oy, Y)
        for ox, oy in ((2, -2), (-2, -2), (2, 1)):
            E.px(img, x + ox, y + oy, F)
        E.px(img, x - 2, y + 1, R)
        return
    # big burst
    E.px(img, x, y, W)
    for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        E.px(img, x + ox, y + oy, W if (ox, oy) == (0, -1) else Y)
    for ox, oy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
        E.px(img, x + ox, y + oy, F)
    for ox, oy in ((3, 0), (-3, 0), (0, -3), (2, -2), (-2, -2)):
        E.px(img, x + ox, y + oy, R)


def soft_glow(img: np.ndarray, cx: float, cy: float, r: float, color, strength: float = 0.5) -> None:
    """Soft translucent glow (FX only): brightens pixels and adds alpha into empty space."""
    h, w = img.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    d = np.hypot(xs + 0.5 - cx, ys + 0.5 - cy) / r
    a = (np.clip(1 - d, 0, 1) ** 1.6) * strength
    src_a = img[:, :, 3].astype(np.float32) / 255.0
    col = np.array(color[:3], np.float32)
    rgb = img[:, :, :3].astype(np.float32)
    # over opaque pixels: lighten toward the glow colour
    lit = rgb * (1 - a[:, :, None] * 0.6) + col * a[:, :, None] * 0.6
    empty = src_a == 0
    out_rgb = np.where(empty[:, :, None], col, lit)
    out_a = np.where(empty, a, src_a)
    keep = (a > 0.02)
    img[:, :, :3] = np.where(keep[:, :, None], np.clip(out_rgb, 0, 255), img[:, :, :3]).astype(np.uint8)
    img[:, :, 3] = np.where(keep, np.clip(out_a * 255, 0, 255), img[:, :, 3]).astype(np.uint8)


def draw_powder_rat(pose: dict, elite: bool) -> np.ndarray:
    c = Canvas(20, 20)
    g = ground_row(20)
    bx, by = pose.get("bx", 0), pose.get("by", 0)
    kx, ky = bx + pose.get("kx", 0), by + pose.get("ky", 0)
    c.put(RAT_TAILS[pose.get("tail", 0)], 1 + bx, 8 + by)
    front, fx_, fy_ = _rat_legs(c, pose.get("legs", ("stand", "stand")), g, 5, 10, pose.get("lx", 0))
    if pose.get("wide"):
        body = PW_BODY_WIDE_E if elite else PW_BODY_WIDE
    else:
        body = PW_BODY_ELITE if elite else PW_BODY
    if pose.get("hurt"):
        body = E.recolor(body, HURT_EYE)
    c.put(body, 1 + bx, 4 + by)
    c.put(front, fx_, fy_, sep=PAL["rat0"])
    kox, koy = 0 + kx, 4 + ky
    c.put(PW_KEG_ELITE if elite else PW_KEG, kox, koy, sep=OUTLINE)
    # fuse cord from the lid, curling up
    cord = pose.get("cord", [(6, 0), (6, -1), (7, -2)])
    for (x, y) in cord:
        E.px(c.img, kox + x, koy + y, PAL["leather1"])
    arm = pose.get("arm", "hold")
    ax, ay = {"hold": (10, 12), "brace": (9, 9), "pump": (10, 11), "shove": (10, 12)}[arm]
    c.put(PW_ARMS[arm], ax + bx, ay + by, sep=OUTLINE)
    img = c.finish()
    tx, ty = kox + cord[-1][0] + 1, koy + cord[-1][1] - 1
    if pose.get("spark", 0) > 0:
        soft_glow(img, tx + 0.5, ty + 0.5, 4.5 + pose["spark"] * 0.6, PAL["fire2"], 0.85)
    _spark_star(img, tx, ty, pose.get("spark", 0))
    for (ox, oy, col) in pose.get("embers", []):
        E.px(img, tx + ox, ty + oy, {"y": PAL["fire4"], "f": PAL["fire3"], "r": PAL["red3"], "s": PAL["stone4"]}[col])
    if pose.get("smoke"):
        sx, sy = pose["smoke"]
        blit(img, cloud(20, 20, [(tx + sx, ty + sy, 1.2)], DUST[:3]), 0, 0)
    for (kx2, ky2) in pose.get("dust", []):
        dust_kick(img, kx2, ky2, 1.1)
    return img


_EMB = [[(-2, 2, "f"), (2, 3, "r")], [(-3, 1, "r"), (3, 1, "f")], [(-2, 3, "y"), (2, -1, "r")], [(3, 3, "f"), (-3, 0, "f")]]

POWDER_RAT = EnemyDef(
    "powder_rat", 20, 20, draw_powder_rat,
    {
        "walk": ([P(legs=("back", "fwd"), tail=0, spark=0),
                  P(legs=("lift", "stand"), by=-1, tail=1, spark=0, ky=0, embers=[(1, -1, "s")]),
                  P(legs=("fwd", "back"), tail=2, spark=0),
                  P(legs=("stand", "lift"), by=-1, tail=1, spark=0, embers=[(-1, -2, "s")])], 8, True),
        "attack": ([P(legs=("crouch", "crouch"), bx=-1, by=1, arm="brace", spark=1, tail=2),
                    P(legs=("back", "fwd"), bx=1, arm="shove", spark=2, tail=0, kx=1),
                    P(legs=("back", "fwd"), bx=2, arm="shove", spark=3, tail=0, kx=2, embers=_EMB[0]),
                    P(legs=("stand", "stand"), arm="hold", spark=1, tail=1)], 10, False),
        "fuse": ([P(legs=("crouch", "crouch"), by=1, arm="brace", wide=True, spark=1, embers=_EMB[0], tail=2, smoke=(-3, -1)),
                  P(legs=("crouch", "crouch"), by=1, arm="brace", wide=True, spark=2, embers=_EMB[1], tail=2, kx=1, smoke=(-4, -2)),
                  P(legs=("crouch", "crouch"), by=1, arm="brace", wide=True, spark=3, embers=_EMB[2], tail=2),
                  P(legs=("crouch", "crouch"), by=1, arm="brace", wide=True, spark=2, embers=_EMB[3], tail=2, kx=-1, smoke=(-3, -1))], 12, True),
        "charge": ([P(legs=("back", "fwd"), bx=1, arm="pump", wide=True, spark=1, tail=0, ky=-1,
                      embers=[(-3, 2, "f"), (-5, 3, "r")], dust=[(3.5, 16.5)]),
                    P(legs=("lift", "back"), bx=1, by=-1, arm="hold", wide=True, spark=2, tail=0,
                      embers=[(-3, 1, "y"), (-6, 2, "f")]),
                    P(legs=("fwd", "back"), bx=1, arm="pump", wide=True, spark=3, tail=0, ky=-1,
                      embers=[(-4, 2, "r"), (-2, 3, "f")], dust=[(5.5, 16.5)]),
                    P(legs=("back", "lift"), bx=1, by=-1, arm="hold", wide=True, spark=2, tail=0,
                      embers=[(-3, 0, "f"), (-5, 2, "y")])], 14, True),
    },
    hurt=P(legs=("stand", "stand"), bx=-1, hurt=True, spark=0, tail=2),
    seed=707,
    death_sparks=(PAL["fire4"], PAL["fire2"]),
)


# --------------------------------------------------------------------------------------
# IRON GOLEM (36x40): hulking iron automaton, furnace chest shaped like a gold collar
# --------------------------------------------------------------------------------------
GOLEM_LEG = {"Q": PAL["orange0"], "R": PAL["orange1"], "S": PAL["stone3"], "T": PAL["stone4"], "U": PAL["stone1"]}


def _ga(s):
    return art(s, GOLEM_LEG)


GO_DARK = {PAL["iron4"]: PAL["iron3"], PAL["iron3"]: PAL["iron2"], PAL["iron2"]: PAL["iron1"]}
GO_TORSO = _ga("""
..jkkkkkkkkkkkkkkkkj..
.jkllllkkkkkkkkkkkkkj.
jkllllkkk2334332kkkkji
jklllkkk23eeeee32kkkji
jkllkkk23effFffe32kkji
jkllkkk3efFyyyFfe3kkji
jklkkkk3efFyyyFfe3kkji
jklkkkk3efFyyyFfe3kjji
jkkkkkk23effFffe32kjji
jkkkkkkk23eeeee32kkjji
.jkkkkkkk2345432kkkjji.
.jkmkkkkkkk454kkkkmjji.
.jkkkkkkkkkk5kkkkkjji..
..jkkllkkkkkkkkkkjji...
..jkllkkkkkkkkkkkjji...
..ijkkkkkkkkkkkkjjii...
...ijjjjjjjjjjjjjii....
...iRRiiiRRiiiRRii.....
""")
GO_TORSO_ELITE = _ga("""
..j33333333333333333..
.jkllllkkkkkkkkkkkkkj.
jkllllkkk2334332kkkkji
jklllkkk23eeeee32kkkji
jkllkkk23effFffe32kkji
jkllkkk3efFyyyFfe3kkji
jklkkkk3efFyyyFfe3kkji
jklkkkk3efFyyyFfe3kjji
jkkkkkk23effFffe32kjji
jkkkkkkk23eeeee32kkjji
.jkkkkkkk2345432kkkjji.
.jk4kkkkkkk454kkkk4jji.
.jkkkkkkkkkk5kkkkkjji..
..jkkllkkkkkkkkkkjji...
..jkllkkkkkkkkkkkjji...
..ijkkkkkkkkkkkkjjii...
...i23222322232222i....
...i3443i3443i3443i....
""")
# furnace flicker: alternate core patterns (drawn over the chest, rows 3..9 of the torso)
GO_FIRE = [_ga("""
.eeeee.
effFffe
efFyyyFfe
efFyyyFfe
efFyyyFfe
effFffe
.eeeee.
"""), _ga("""
.efeee.
eFfffFe
effyyFfFe
eFyyyyyFe
efFyyFfFe
eFffFfe
.eeefe.
""")]
GO_PAUL = _ga("""
...jkkkj...
.jkllmmlkj.
jkllmmmllkj
jklmlllllkj
jkllllllkkj
jkkkkkkkkkj
ikmkkkkkmki
.iiiiiiiii.
""")
GO_PAUL_ELITE = _ga("""
...34443...
.34llmml43.
3kllmmmllk3
jklmlllllkj
jkllllllkkj
jkkkkkkkkkj
i4k3kkk3k4i
.333444333.
""")
GO_HEAD = _ga("""
..jkkkj..
.jkllmkj.
jklllkkkj
jkFyyyFkj
jkkkkkkji
.jjkkkjj.
""")
GO_HEAD_ELITE = _ga("""
....5....
...545...
..j343j..
.jkllmkj.
jklllkkkj
jkFyyyFkj
jkkkkkkji
.jjkkkjj.
""")
GO_CHIMNEY = _ga("""
iUUUi
jkllj
.klj.
.klj.
.kkj.
.kkj.
.kkj.
""")
GO_ARM = _ga("""
.jkkkj..
.jkllkj.
.jkllkj.
.jkllkj.
.jkkkkj.
.ijkkji.
.jkllkj.
.jkllkj.
.jkkkkj.
.jkkkkj.
jkllllkj
kllmmllkj
klmmmllkj
kllllllkj
jkkkkkkji
.ijjjjji.
""")
GO_ARM_UP = _ga("""
.jkkkkkj.
jklmmllkj
klmmmllkj
kllllllkj
jkkkkkkji
.jkllkji.
.jkllkj..
.jkllkj..
.jkkkkj..
.jkkkkj..
""")
GO_ARM_SLAM = _ga("""
.jkkj......
.jkllkj....
..jkllkkj..
....jkllkkj
....jklmmlkj
....klmmmllkj
....kllllllkj
....jkkkkkkji
.....ijjjjji.
""")
GO_LEG = {
    "plant": _ga("""
jkkkkj.
jkllkj.
jkllkj.
jkkkkj.
ijkkkji
jkllllkj
iiiiiiii
"""),
    "lift": _ga("""
jkkkkj.
jkllkj.
ijkkkji
jkllllkj
iiiiiiii
"""),
}


def draw_iron_golem(pose: dict, elite: bool) -> np.ndarray:
    c = Canvas(36, 40)
    g = ground_row(40)
    bx, by = pose.get("bx", 0), pose.get("by", 0)
    c.put(GO_CHIMNEY, 7 + bx, 2 + by)
    arms = pose.get("arms", "hang")
    fa, ba = pose.get("fa", (0, 0)), pose.get("ba", (0, 0))
    paul = GO_PAUL_ELITE if elite else GO_PAUL
    # back arm + pauldron
    if arms == "hang":
        c.put(E.recolor(GO_ARM, GO_DARK), 1 + bx + ba[0], 14 + by + ba[1])
    elif arms == "up":
        c.put(E.recolor(GO_ARM_UP, GO_DARK), 9 + bx, 1 + by)
    elif arms == "slam":
        c.put(E.recolor(GO_ARM_SLAM, GO_DARK), 13 + bx, 26 + by)
    c.put(E.recolor(paul, GO_DARK), 2 + bx, 9 + by)
    # legs
    lb, lf = pose.get("legs", ("plant", "plant"))
    for name, x, dk in ((lb, 11, True), (lf, 19, False)):
        part = GO_LEG[name]
        if dk:
            part = E.recolor(part, GO_DARK)
        c.put(part, x, g - part.shape[0] + 1 - (2 if name == "lift" else 0))
    torso = GO_TORSO_ELITE if elite else GO_TORSO
    c.put(torso, 7 + bx, 11 + by)
    fire = GO_FIRE[pose.get("fire", 0)]
    c.put(fire, 7 + bx + 7, 11 + by + 3)
    head = GO_HEAD_ELITE if elite else GO_HEAD
    if pose.get("hurt"):
        head = E.recolor(head, {PAL["fire4"]: PAL["iron1"], PAL["fire3"]: PAL["iron2"]})
    c.put(head, 14 + bx + pose.get("hx", 0), 6 + by + pose.get("hy", 0) - (2 if elite else 0))
    # front arm + pauldron
    if arms == "hang":
        c.put(GO_ARM, 26 + bx + fa[0], 14 + by + fa[1], sep=OUTLINE)
    elif arms == "up":
        c.put(GO_ARM_UP, 20 + bx, 1 + by, sep=OUTLINE)
    elif arms == "slam":
        c.put(GO_ARM_SLAM, 22 + bx, 27 + by, sep=OUTLINE)
    c.put(paul, 24 + bx, 9 + by, sep=OUTLINE)
    img = c.finish()
    # furnace glow (soft FX)
    glow_disc(img, 17.5 + bx, 17.5 + by, 7.5, PAL["fire2"], 0.28, under_only=True)
    if pose.get("smoke") is not None:
        k = pose["smoke"]
        pts = [(8.5, 0.8, 1.3), (7.5, -0.6, 1.6), (9.5, -1.2, 1.9), (8.0, -1.0, 1.1)][k]
        blit(img, cloud(36, 40, [(pts[0] + bx, pts[1] + 1 + by, pts[2])], DUST[:4]), 0, 0)
    for (kx, ky) in pose.get("dust", []):
        dust_kick(img, kx, ky, 1.8)
    if pose.get("impact"):
        for (ix, iy) in pose["impact"]:
            blit(img, cloud(36, 40, [(ix, iy, 2.4), (ix + 2.5, iy + 0.5, 1.8), (ix - 2.2, iy + 0.6, 1.6)]), 0, 0)
            spark(img, ix + 3, iy - 4, True, (PAL["white"], PAL["fire3"]))
            spark(img, ix - 3, iy - 3, False, (PAL["fire4"], PAL["fire3"]))
    return img


def glow_disc(img: np.ndarray, cx: float, cy: float, r: float, color, strength: float = 0.35,
              under_only: bool = False) -> None:
    """Soft additive-looking glow (FX only). With under_only, only brightens opaque pixels'
    surroundings (never paints into empty space)."""
    h, w = img.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    d = np.hypot(xs + 0.5 - cx, ys + 0.5 - cy) / r
    a = np.clip(1 - d, 0, 1) ** 1.5 * strength
    if under_only:
        a = a * (img[:, :, 3] > 0)
    a3 = a[:, :, None]
    rgb = img[:, :, :3].astype(np.float32)
    col = np.array(color[:3], np.float32)
    rgb = rgb * (1 - a3) + col * a3 + (col * a3 * 0.3)
    img[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)


IRON_GOLEM = EnemyDef(
    "iron_golem", 36, 40, draw_iron_golem,
    {
        "walk": ([P(legs=("plant", "lift"), fa=(-1, 0), ba=(1, 0), fire=0, smoke=0),
                  P(legs=("plant", "plant"), by=1, fire=1, smoke=1, dust=[(25.5, 35.5)]),
                  P(legs=("lift", "plant"), fa=(1, 0), ba=(-1, 0), fire=0, smoke=2),
                  P(legs=("plant", "plant"), by=1, fire=1, smoke=3, dust=[(12.5, 35.5)])], 8, True),
        "attack": ([P(arms="up", bx=-1, by=-1, fire=1, smoke=0),
                    P(arms="up", bx=0, by=-1, fire=0, hy=-1, smoke=1),
                    P(arms="slam", bx=1, by=2, fire=1, impact=[(30, 34)], smoke=2),
                    P(arms="hang", fire=0, smoke=3)], 10, False),
    },
    hurt=P(bx=-1, hurt=True, fire=1),
    seed=808,
    death_scale=1.0,
)

ENEMIES: List[EnemyDef] = [RAT_RAIDER, HOUND_RUNNER, SHIELD_GUARD, CROW_ARCHER, BAT, BELL_PRIEST, POWDER_RAT, IRON_GOLEM]


# --------------------------------------------------------------------------------------
# 16x16 enemy icons: busts cropped from real frames (so they match the in-game look);
# cut edges are closed with the outline colour. Bats get a hand-drawn 3-bat cluster.
# --------------------------------------------------------------------------------------
def icon_crop(frame: np.ndarray, x: int, y: int, size: int = 16) -> np.ndarray:
    out = E.new(size, size)
    blit(out, frame, -x, -y)
    op = out[:, :, 3] > 0
    border = np.zeros_like(op)
    border[0, :] = border[-1, :] = True
    border[:, 0] = border[:, -1] = True
    out[op & border] = OUTLINE
    return out


MINI_BAT = art("""
9..B.B..9
89.BDB.98
.887C788.
..7.5.7..
""", RAT_LEG)
MINI_BAT_UP = art("""
.9.....9.
.89B.B98.
..8BDB8..
...7C7...
....5....
""", RAT_LEG)


def bat_swarm_icon() -> np.ndarray:
    c = Canvas(16, 16)
    c.put(MINI_BAT_UP, 0, 1)
    c.put(MINI_BAT, 7, 3)
    c.put(MINI_BAT, 3, 9)
    img = c.finish()
    return img


ICON_SPECS = {
    # id: (enemy def, clip, frame, crop x, crop y)
    "rat_raider": ("rat_raider", "walk", 0, 3, 1),
    "hound_runner": ("hound_runner", "walk", 2, 8, 2),
    "shield_guard": ("shield_guard", "walk", 1, 4, 0),
    "crow_archer": ("crow_archer", "walk", 0, 3, 0),
    "bell_priest": ("bell_priest", "walk", 0, 3, 0),
    "powder_rat": ("powder_rat", "fuse", 2, 1, 0),
    "iron_golem": ("iron_golem", "walk", 1, 10, 4),
}


def enemy_icons() -> Dict[str, np.ndarray]:
    by_id = {d.id: d for d in ENEMIES}
    out = {}
    for iid, (eid, clip, fi, x, y) in ICON_SPECS.items():
        fr = by_id[eid].frames(clip, False)[fi]
        out[iid] = icon_crop(fr, x, y)
    out["bat_swarm"] = bat_swarm_icon()
    return out


# --------------------------------------------------------------------------------------
# Preview / build
# --------------------------------------------------------------------------------------
def clip_names(d: EnemyDef) -> List[str]:
    return list(d.clips.keys()) + ["death"]


def preview_enemy(d: EnemyDef, scale: int = 6) -> str:
    rows = []
    for elite in (False, True):
        for clip in clip_names(d):
            rows.append(d.frames(clip, elite))
    path = os.path.join(ITER_DIR, f"{d.id}.png")
    _sheet(rows, path, scale)
    return path


def _sheet(rows_of_frames, path, scale=6, bg=(26, 38, 38, 255), gap=4):
    from PIL import Image
    ims = []
    for frames in rows_of_frames:
        w = sum(f.shape[1] for f in frames) * scale + gap * (len(frames) + 1)
        h = max(f.shape[0] for f in frames) * scale + gap * 2
        im = Image.new("RGBA", (w, h), bg)
        x = gap
        for f in frames:
            big = E.to_pil(E.scale_nearest(f, scale))
            im.alpha_composite(big, (x, gap))
            x += big.size[0] + gap
        ims.append(im)
    for k in (1, 2):
        allf = [f for fr in rows_of_frames for f in fr]
        w = sum(f.shape[1] for f in allf) * k + 3 * (len(allf) + 1)
        h = max(f.shape[0] for f in allf) * k + 6
        for bgc in ((26, 38, 38, 255), (53, 48, 61, 255)):
            im = Image.new("RGBA", (w, h), bgc)
            x = 3
            for f in allf:
                big = E.to_pil(E.scale_nearest(f, k))
                im.alpha_composite(big, (x, 3))
                x += big.size[0] + 3
            ims.append(im)
    W = max(i.size[0] for i in ims)
    H = sum(i.size[1] for i in ims) + 2 * len(ims)
    out = Image.new("RGBA", (W, H), (10, 10, 12, 255))
    y = 0
    for i in ims:
        out.alpha_composite(i, (0, y))
        y += i.size[1] + 2
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.save(path)


def build(reg: E.Registry) -> None:
    reg.atlas("enemies", flash=True)
    for d in ENEMIES:
        for elite in (False, True):
            eid = d.id + ("_elite" if elite else "")
            for clip in clip_names(d):
                if clip == "death":
                    fps, loop = 12, False
                else:
                    _, fps, loop = d.clips[clip]
                reg.anim("enemies", f"enemy/{eid}/{clip}", d.frames(clip, elite), fps, loop, pivot=(0.5, 0.1))
    for iid, img in enemy_icons().items():
        reg.sprite("icons", f"icon/enemy/{iid}", img, pivot=(0.5, 0.5))


if __name__ == "__main__":
    want = sys.argv[1:]
    if "icons" in want:
        ic = enemy_icons()
        _sheet([list(ic.values())], os.path.join(ITER_DIR, "enemy_icons.png"), 8)
        print(os.path.join(ITER_DIR, "enemy_icons.png"))
    for d in ENEMIES:
        if not want or d.id in want:
            print(preview_enemy(d))
