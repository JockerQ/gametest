"""
gen_bosses.py - the three bosses of the Golden Collar Order for EVIL CATS.

Atlases written:
  * bosses (flash=True): boss/<id>/<clip>/<i>
  * portraits:           portrait/<boss_id> (64x64 busts)
  * icons:               icon/enemy/<boss_id> (16x16)

Same method as gen_enemies.py: hand-placed pixel parts (ASCII art on the eclib palette)
composed per frame with per-part offsets, a 1 px outline around the silhouette, FX drawn
after the outline. Bosses are bigger, so a few parts (weapons, wings, capes) are drawn
procedurally with pixel-perfect primitives and shaded from the top-left.

Run directly for quick iteration previews:
    python3 Tools/art/gen_bosses.py [boss_id ...] [portraits] [icons]
"""
from __future__ import annotations

import math
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import eclib as E  # noqa: E402
from eclib import PAL  # noqa: E402
import gen_enemies as GE  # noqa: E402  (shared rig helpers)
from gen_enemies import (OUTLINE, Canvas, art, blit, cloud, spark, soft_glow, glow_disc, dust_kick,  # noqa: E402
                         brighten, tint, squash, DUST, _sheet)

ITER_DIR = GE.ITER_DIR
DARK = {PAL["iron4"]: PAL["iron3"], PAL["iron3"]: PAL["iron2"], PAL["iron2"]: PAL["iron1"], PAL["iron1"]: PAL["iron0"]}


def ground_row(h: int, pivot_y: float) -> int:
    return int(round(h * (1 - pivot_y))) - 1


def darker(img: np.ndarray, mapping=DARK) -> np.ndarray:
    return E.recolor(img, mapping)


def thick_line(img, x0, y0, x1, y1, c, width: int = 2) -> None:
    E.line(img, x0, y0, x1, y1, c)
    if width >= 2:
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) > abs(dy):
            E.line(img, x0, y0 + 1, x1, y1 + 1, c)
        else:
            E.line(img, x0 + 1, y0, x1 + 1, y1, c)
    if width >= 3:
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) > abs(dy):
            E.line(img, x0, y0 - 1, x1, y1 - 1, c)
        else:
            E.line(img, x0 - 1, y0, x1 - 1, y1, c)


def shaded_disc(img, cx, cy, r, ramp, light=(-0.7, -0.75)) -> None:
    """Hard-pixel disc lit from the top-left (ramp dark -> light)."""
    n = len(ramp)
    for yy in range(int(math.floor(cy - r - 1)), int(math.ceil(cy + r + 1)) + 1):
        for xx in range(int(math.floor(cx - r - 1)), int(math.ceil(cx + r + 1)) + 1):
            dx, dy = xx + 0.5 - cx, yy + 0.5 - cy
            d = math.hypot(dx, dy)
            if d > r:
                continue
            lam = -(dx * light[0] + dy * light[1]) / max(r, 0.01)
            v = 0.5 + lam * 0.55 + (1 - d / r) * 0.15
            idx = max(0, min(n - 1, int(v * n)))
            E.px(img, xx, yy, ramp[idx])


def smear_arc(img, cx, cy, r, a0, a1, colors=(PAL["white"], PAL["silver2"], PAL["silver1"]), width=3) -> None:
    """Motion smear: a crescent of light pixels along an arc (FX)."""
    steps = int(abs(a1 - a0) * r * 1.6) + 2
    for i in range(steps):
        t = i / (steps - 1)
        a = a0 + (a1 - a0) * t
        for k in range(width):
            rr = r - k
            x, y = cx + math.cos(a) * rr, cy + math.sin(a) * rr
            col = colors[min(len(colors) - 1, k + (0 if t > 0.35 else 1))]
            if t < 0.15 and k > 0:
                continue
            E.px(img, int(round(x)), int(round(y)), col)


def speed_lines(img, x0, x1, ys, color=PAL["silver2"], alt=PAL["silver1"]) -> None:
    for i, y in enumerate(ys):
        a, b = x0 + (i % 2) * 2, x1 - (i % 3)
        for x in range(a, b):
            E.px(img, x, y, color if x > (a + b) // 2 else alt)


def aura(img: np.ndarray, color, radius: int = 2, strength: float = 0.5) -> np.ndarray:
    """Soft coloured halo around the whole silhouette (telegraph FX)."""
    return E.glow(img, color, radius=radius, strength=strength)


def boss_death_puffs(img: np.ndarray, blobs, sparks_at=(), sparks=(PAL["gold4"], PAL["gold3"])) -> None:
    blit(img, cloud(img.shape[1], img.shape[0], blobs), 0, 0)
    for (x, y, big) in sparks_at:
        spark(img, x, y, big, sparks)


def dist_in(mask: np.ndarray, cap: int = 12) -> np.ndarray:
    """Chamfer-ish distance (in px) from each masked pixel to the mask edge (4-neighbour erosion)."""
    d = np.zeros(mask.shape, np.float32)
    cur = mask.copy()
    for i in range(1, cap + 1):
        d[cur] = i
        er = cur.copy()
        er[1:, :] &= cur[:-1, :]
        er[:-1, :] &= cur[1:, :]
        er[:, 1:] &= cur[:, :-1]
        er[:, :-1] &= cur[:, 1:]
        cur = er
        if not cur.any():
            break
    return d


def shade_region(img: np.ndarray, mask: np.ndarray, ramp: Sequence, light=(-0.55, -0.75), cap: int = 6,
                 slope: float = 2.2, bias: float = 0.0, thresholds: Optional[Sequence[float]] = None,
                 dither: bool = True) -> None:
    """Fill `mask` with `ramp` (dark -> light) shaded as a rounded form lit from `light`
    (normals from a distance-field height map, quantised to hard bands, optional ordered
    dither on band edges)."""
    if not mask.any():
        return
    d = dist_in(mask, cap)
    h = np.sqrt(np.clip(d, 0, cap) / cap)
    gy, gx = np.gradient(h)
    nx, ny, nz = -gx * slope, -gy * slope, np.ones_like(h)
    nl = np.sqrt(nx * nx + ny * ny + nz * nz)
    lx, ly, lz = light[0], light[1], 0.62
    ll = math.sqrt(lx * lx + ly * ly + lz * lz)
    lam = (nx * lx + ny * ly + nz * lz) / (nl * ll) + bias
    n = len(ramp)
    th = thresholds or [0.30 + 0.62 * (i + 1) / n for i in range(n - 1)]
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0 - 0.5
    ys, xs = np.nonzero(mask)
    for x, y in zip(xs, ys):
        v = lam[y, x] + (bayer[y % 4, x % 4] * 0.06 if dither else 0)
        idx = sum(1 for t in th if v >= t)
        img[y, x] = ramp[idx]


def poly_mask(pts, w: int, h: int) -> np.ndarray:
    tmp = E.new(w, h)
    E.polygon(tmp, pts, (255, 255, 255, 255))
    return tmp[:, :, 3] > 0


def ell_mask(cx, cy, rx, ry, w: int, h: int) -> np.ndarray:
    tmp = E.new(w, h)
    E.ellipse(tmp, cx, cy, rx, ry, (255, 255, 255, 255))
    return tmp[:, :, 3] > 0


def stamp(img: np.ndarray, rows: str, x: int, y: int, legend: Dict) -> None:
    """Paste hand-placed ASCII detail at (x, y) (opaque pixels only)."""
    blit(img, art(rows, legend), x, y)


# ======================================================================================
# SIR BARKHELM, the Iron Hound (48x48): armoured hound knight, hounskull visor helm,
# gold collar (gorget), heavy heater shield, iron bone-mace.
# ======================================================================================
BK_W, BK_H, BK_PIV = 48, 48, 0.08
BK_G = ground_row(BK_H, BK_PIV)  # 43
BK_LEG = {"A": PAL["brown0"], "B": PAL["brown1"], "C": PAL["brown2"], "D": PAL["brown3"]}


def _bk(s):
    return art(s, BK_LEG)


BK_HELM_SRC = """
......lm....lm.....
.....lmk...lmkj....
.....lkj..jlkj.....
....jkllllllllkj...
...jklmmmllllllkj..
...jkllmmllllllkkj.
..ijkllllllllllkkkj.
..ijkkkkkkkkkkkkkkkj
..ijk%%Fy%%%%%%kkkkkj
..ijkkkkkkkkkkkklmmmlj
..ijkllkkkk%k%k%klllkj
...ijkkkkkkkkkkkkkkkj.
...iijjkkkkkkkkjjjjj..
.....iijjjjjjjjii.....
"""
BK_HELM = _bk(BK_HELM_SRC)
BK_HELM_RED = _bk(BK_HELM_SRC.replace("%%Fy%%", "%99009"))   # windup: blazing red eyes
BK_HELM_DIM = _bk(BK_HELM_SRC.replace("%%Fy%%", "%%%%%%"))   # defeat / hit squint
BK_PLUME = [_bk("""
.........09.
......09988.
...099888...
.0998877....
09887766....
98776.......
8776........
76..........
"""), _bk("""
.........09.
.......0998.
....09988...
.09988877...
098877766...
98776.......
877.........
76..........
"""), _bk("""
.........09.
......09988.
...099888...
..998877....
.9887766....
98776.......
8776........
.76.........
""")]
BK_GORGET = _bk("""
..2344444432..
.234555554432.
.1233333333221
..11222222211.
""")
BK_TORSO = _bk("""
....jkllllkj....
..jklmmllllkkj..
.jkllm7888lkkkj.
jkllll7888llkkkj
jklll378883lkkkj
jkllk7888887kkkj
jklkk7888887kkji
jkkkk7788877kkji
jkkkk7788777kjji
.jkkk6777776kji.
.i23332222333ji.
.i23444444432ii.
..jkkkkkkkkkkj..
""")
BK_PAUL = _bk("""
...jkllkj..
.jkllmmllkj
jkllmmmllkkj
jklllllllkkj
i2333333332i
.i1222222i.
""")
BK_SHIELD = _bk("""
23333333333332
34444444444443
34788888888743
34788888888743
34788888888743
33443444434433
35555555555553
32223323322233
34788838888743
34788888888743
.3478888888743.
.3478888888743.
..34788888743..
..34777777743..
...347777743...
....3477743....
.....34443.....
......343......
.......3.......
""")
BK_SHIELD_FLAT = _bk("""
...23333333333332..
.234888888888884432
23488888888888888432
.2347777777777777432
...2333333333333332.
""")
BK_LEGS = {
    "stand": _bk("""
.jkllkj.
.jkllkj.
.jklkkj.
.ilmmli.
.jkllkj.
.jkllkj.
.jkkkkj.
.jkkkkj.
ijkllkkj
jkllllkkj
iiiiiiiii
"""),
    "bend": _bk("""
.jkllkj.
.jkllkj.
..jklkkj.
..ilmmlij
..jkllkj.
.jkllkj..
.jkkkkj..
ijkllkkj.
jkllllkkj
iiiiiiiii
"""),
    "kneel": _bk("""
......jkkj.
......jkkj.
......jklj.
......ilmi.
......jkkj.
.ijjjjjkkj.
ijkkkkkklkj
iiiiiiiiiii
"""),
    "kneel_up": _bk("""
jkllkkj.....
.jkllllkkj..
..jkllmmlkj.
.......jkkj.
.......jkkj.
.......jkkj.
......ijklkj
......jkllkkj
......iiiiiii
"""),
    "reach": _bk("""
.jkllkj...
..jkllkj..
...jklkkj.
...ilmmli.
....jkllkj
....jkllkj
....jkkkkj
....ijkllkkj
....jkllllkkj
....iiiiiiiii
"""),
    "push": _bk("""
....jkllkj
...jkllkj.
..jklkkj..
..ilmmli..
.jkllkj...
.jkllkj...
jkkkkj....
jkkkkj....
jkllkkj...
kllllkkj..
iiiiiiii..
"""),
}
BK_TAIL = [_bk("""
.DD...
.CDD..
..BCD.
...BCC
....BC
.....B
"""), _bk("""
DD....
CDD...
.BCD..
..BCC.
...BCC
....BB
""")]
BK_ARM = PAL["iron2"], PAL["iron3"]


def bone_mace(c: Canvas, hx: int, hy: int, ang: float, length: int = 9, dark: bool = False) -> Tuple[float, float]:
    """Iron bone-club held at (hx, hy) pointing along `ang` (radians, y down)."""
    ramp = [PAL["iron1"], PAL["iron2"], PAL["iron3"], PAL["iron4"]] if not dark else \
        [PAL["iron0"], PAL["iron1"], PAL["iron2"], PAL["iron3"]]
    ex, ey = hx + math.cos(ang) * length, hy + math.sin(ang) * length
    thick_line(c.img, hx, hy, int(round(ex)), int(round(ey)), ramp[1], 2)
    # grip wrap (gold)
    E.px(c.img, hx, hy, PAL["gold2"])
    E.px(c.img, hx + 1, hy, PAL["gold1"])
    # the bone knob: two lobes perpendicular to the handle + a centre
    px_, py_ = -math.sin(ang), math.cos(ang)
    kx, ky = ex + math.cos(ang) * 1.5, ey + math.sin(ang) * 1.5
    shaded_disc(c.img, kx, ky, 2.2, ramp)
    for s in (-1, 1):
        shaded_disc(c.img, kx + px_ * 2.4 * s + math.cos(ang) * 1.6, ky + py_ * 2.4 * s + math.sin(ang) * 1.6, 2.0, ramp)
    return kx, ky


def draw_barkhelm(pose: dict) -> np.ndarray:
    c = Canvas(BK_W, BK_H)
    g = BK_G
    bx, by = pose.get("bx", 0), pose.get("by", 0)
    hx, hy = bx + pose.get("hx", 0), by + pose.get("hy", 0)
    # --- back layer: tail, far leg, far arm + mace, far pauldron
    c.put(BK_TAIL[pose.get("tail", 0)], 9 + bx, 23 + by)
    legs = pose.get("legs", ("stand", "stand"))
    leg_x = pose.get("leg_x", (16, 23))
    for i, (name, x) in enumerate(zip(legs, leg_x)):
        part = BK_LEGS[name]
        if i == 0:
            part = darker(part)
        y = g - part.shape[0] + 1
        if name == "kneel":
            y = g - part.shape[0] + 1
        c.put(part, x + (pose.get("lx", 0) if i == 1 else 0), y)
        if i == 0 and pose.get("mace_layer", "back") == "back":
            _bk_mace(c, pose, bx, by)
    c.put(darker(BK_PAUL), 12 + bx, 16 + by)
    # --- body
    c.put(BK_TORSO, 15 + bx, 18 + by)
    if not pose.get("no_collar"):
        c.put(BK_GORGET, 17 + hx, 15 + hy)
    c.put(BK_PLUME[pose.get("plume", 0)], 8 + hx, 1 + hy)
    helm = {"normal": BK_HELM, "red": BK_HELM_RED, "dim": BK_HELM_DIM}[pose.get("eyes", "normal")]
    c.put(helm, 15 + hx, 3 + hy)
    if pose.get("mace_layer") == "front":
        _bk_mace(c, pose, bx, by, sep=True)
    c.put(BK_PAUL, 21 + bx, 15 + by, sep=OUTLINE)
    sx, sy = pose.get("sx", 0), pose.get("sy", 0)
    if pose.get("shield_flat"):
        c.put(BK_SHIELD_FLAT, 27, BK_G - 4, sep=OUTLINE)
    else:
        c.put(BK_SHIELD, 26 + bx + sx, 18 + by + sy, sep=OUTLINE)
    if pose.get("mace_layer") == "top":
        _bk_mace(c, pose, bx, by, sep=True)
    # --- FX
    img = c.finish()
    if pose.get("red_glow"):
        k = pose["red_glow"]
        img = aura(img, PAL["red3"], 2, 0.45 + 0.17 * k)
        soft_glow(img, 22.5 + hx, 11.5 + hy, 5.5 + k, PAL["red3"], 1.0)
        for (x, y, col) in ((20, 11, PAL["red3"]), (21, 11, PAL["red4"]), (22, 11, PAL["white"]), (23, 11, PAL["red4"])):
            E.px(img, x + hx, y + hy, col)
    for (x, y, r) in pose.get("snort", []):
        blit(img, cloud(BK_W, BK_H, [(x + hx, y + hy, r)], [PAL["red1"], PAL["red2"], PAL["red3"], PAL["red4"]]), 0, 0)
    for (x, y, r) in pose.get("dust", []):
        dust_kick(img, x, y, r)
    if pose.get("speed"):
        speed_lines(img, 1, 14 + bx, pose["speed"])
    if pose.get("smear"):
        cx, cy, r, a0, a1 = pose["smear"]
        smear_arc(img, cx, cy, r, a0, a1)
    for (x, y, big) in pose.get("sparks", []):
        spark(img, x, y, big, (PAL["white"], PAL["gold3"]))
    if pose.get("glint"):
        x, y = pose["glint"]
        spark(img, x, y, True, (PAL["white"], PAL["gold4"]))
    if pose.get("collar_at"):
        x, y, rot = pose["collar_at"]
        _loose_collar(img, x, y, rot)
    return img


def _bk_mace(c: Canvas, pose: dict, bx: int, by: int, sep: bool = False) -> None:
    mx, my, ang = pose.get("mace", (15, 30, 2.0))
    arm_from = pose.get("arm_from", (19, 22))
    tmp = Canvas(BK_W, BK_H)
    # far arm: shoulder -> hand
    ax0, ay0 = arm_from[0] + bx, arm_from[1] + by
    thick_line(tmp.img, ax0, ay0, mx + bx, my + by, PAL["iron2"] if not sep else PAL["iron3"], 3)
    shaded_disc(tmp.img, mx + bx + 0.5, my + by + 0.5, 1.8, [PAL["iron1"], PAL["iron2"], PAL["iron3"], PAL["iron4"]])
    bone_mace(tmp, mx + bx, my + by, ang, pose.get("mace_len", 9), dark=not sep)
    c.put(tmp.img, 0, 0, sep=OUTLINE if sep else None)


def _loose_collar(img, x, y, rot: int) -> None:
    """The gold collar flying off / lying on the ground (rot 0 = flat ellipse, 1 = tilted, 2 = on edge)."""
    shapes = {
        0: ["..2344432..", ".23.....32.", "234.....432", ".233333332.", "...12221..."],
        1: ["...2344.", "..3...43", ".3....42", "43...33.", "4..332..", ".332...."],
        2: ["..34.", ".3.43", "34..3", "3..43", "3.43.", ".32.."],
        3: [".2344444432.", "23........32", ".2333333332."],
    }
    rows = shapes[rot]
    part = art("\n".join(rows))
    part = E.outline(np.pad(part, ((1, 1), (1, 1), (0, 0))), OUTLINE)
    blit(img, part, x - part.shape[1] // 2, y - part.shape[0] // 2)
    E.px(img, x + 1, y - part.shape[0] // 2 + 1, PAL["gold4"])


BARKHELM_CLIPS = {
    # clip: (poses, fps, loop)
    "walk": ([dict(legs=("reach", "push"), leg_x=(15, 21), plume=0, tail=0, by=0),
              dict(legs=("stand", "bend"), by=-1, plume=1, tail=1, sy=-1),
              dict(legs=("push", "reach"), leg_x=(17, 21), plume=2, tail=0, by=0),
              dict(legs=("bend", "stand"), by=-1, plume=1, tail=1, sy=-1)], 8, True),
    "attack": ([dict(mace=(16, 12, -2.3), arm_from=(19, 20), mace_layer="back", bx=-1, hy=-1, plume=2),
                dict(mace=(26, 8, -0.9), arm_from=(20, 19), mace_layer="top", plume=1,
                     smear=(24, 20, 16, -2.6, -0.6)),
                dict(mace=(33, 24, 0.9), arm_from=(21, 19), mace_layer="top", bx=2, by=1, hx=1, plume=0,
                     sparks=[(44, 39, True), (41, 42, False), (46, 35, False)], dust=[(42.5, 42.5, 2.2)],
                     smear=(26, 22, 16, -0.9, 0.7)),
                dict(mace=(16, 30, 2.0), plume=1)], 10, False),
    "shield": ([dict(sy=-2, sx=1, by=0, plume=1),
                dict(sy=-4, sx=2, by=1, hy=1, legs=("bend", "stand"), plume=2),
                dict(sy=-5, sx=3, by=2, hy=2, legs=("bend", "bend"), plume=0, glint=(30, 15)),
                dict(sy=-5, sx=3, by=2, hy=2, legs=("bend", "bend"), plume=0, glint=(41, 17))], 10, False),
    "windup": ([dict(by=3, hy=3, bx=-1, legs=("bend", "bend"), sx=1, eyes="red", red_glow=1, plume=2,
                     dust=[(14.5, 42.5, 2.0)], tail=1, snort=[(37.5, 13.5, 1.3)]),
                dict(by=3, hy=3, bx=0, legs=("bend", "bend"), sx=1, eyes="red", red_glow=2, plume=0,
                     dust=[(12.5, 41.5, 2.6), (17.5, 42.8, 1.6)], tail=0, snort=[(39.5, 12.5, 1.8)]),
                dict(by=3, hy=3, bx=-1, legs=("bend", "bend"), sx=1, eyes="red", red_glow=3, plume=2,
                     dust=[(10.5, 40.5, 3.0), (16.5, 42.5, 2.0)], tail=1, snort=[(37.5, 13.5, 1.3), (41.5, 11.5, 1.5)]),
                dict(by=3, hy=3, bx=0, legs=("bend", "bend"), sx=1, eyes="red", red_glow=2, plume=0,
                     dust=[(13.5, 41.5, 2.2)], tail=0, snort=[(42.5, 10.5, 1.2)])], 10, True),
    "charge": ([dict(bx=4, by=2, hy=3, legs=("push", "reach"), leg_x=(17, 23), sx=2, eyes="red", red_glow=1, plume=2,
                     speed=(20, 26, 33), dust=[(15.5, 42.5, 2.0)], tail=1),
                dict(bx=5, by=1, hy=2, legs=("bend", "stand"), leg_x=(19, 26), sx=2, eyes="red", red_glow=1, plume=2,
                     speed=(18, 24, 30, 36), tail=1),
                dict(bx=4, by=2, hy=3, legs=("reach", "push"), leg_x=(17, 22), sx=2, eyes="red", red_glow=1, plume=2,
                     speed=(21, 28, 35), dust=[(20.5, 42.5, 2.0)], tail=1),
                dict(bx=5, by=1, hy=2, legs=("stand", "bend"), leg_x=(19, 26), sx=2, eyes="red", red_glow=1, plume=2,
                     speed=(19, 25, 32, 38), tail=1)], 12, True),
    "hit": ([dict(bx=-2, hx=-3, hy=-1, eyes="dim", sx=-1, plume=1, sparks=[(38, 20, True)]),
             dict(bx=-1, hx=-1, eyes="normal", plume=2)], 12, False),
    "defeat": ([dict(bx=-2, hx=-3, hy=-1, eyes="dim", plume=1),
                dict(by=3, hy=3, legs=("bend", "kneel_up"), leg_x=(16, 20), eyes="dim", sy=7, sx=3, plume=2,
                     mace=(14, 36, 2.6)),
                dict(by=6, hy=8, hx=1, legs=("kneel", "kneel_up"), leg_x=(11, 20), eyes="dim", shield_flat=True,
                     plume=0, mace=(12, 38, 2.9), dust=[(40.5, 42.5, 1.6), (29.5, 42.8, 1.3)]),
                dict(by=6, hy=8, hx=1, legs=("kneel", "kneel_up"), leg_x=(11, 20), eyes="dim", shield_flat=True,
                     plume=0, mace=(12, 38, 2.9), no_collar=True, collar_at=(27, 5, 1), sparks=[(31, 8, False)]),
                dict(by=6, hy=9, hx=1, legs=("kneel", "kneel_up"), leg_x=(11, 20), eyes="dim", shield_flat=True,
                     plume=0, mace=(12, 38, 2.9), no_collar=True, collar_at=(38, 34, 2),
                     sparks=[(35, 32, False), (42, 33, True)]),
                dict(by=6, hy=9, hx=1, legs=("kneel", "kneel_up"), leg_x=(11, 20), eyes="dim", shield_flat=True,
                     plume=0, mace=(12, 38, 2.9), no_collar=True, collar_at=(37, 37, 3), glint=(41, 36))], 8, False),
}


# ======================================================================================
# MOTHER CARRION, the Bell Crow (64x56): huge crow matriarch in tattered violet-black
# robes, hovering on great wings, a great bronze bell gripped in one talon.
# ======================================================================================
MC_W, MC_H = 64, 56
MC_G = 50                         # talon / bell bottom row (the pivot line)
MC_PIV = (MC_H - MC_G - 1) / MC_H  # 5/56 from the bottom
MC_LEG = {"A": PAL["crow0"], "B": PAL["crow1"], "C": PAL["crow2"], "D": PAL["crow3"], "E": PAL["stone3"],
          "P": PAL["crow0"], "Q": PAL["violet0"], "R": PAL["violet1"], "S": PAL["violet2"], "T": PAL["violet3"],
          "G": PAL["bone1"], "H": PAL["bone2"], "I": PAL["bone3"], "J": PAL["bone4"],
          "a": PAL["brown1"], "b": PAL["gold0"], "c": PAL["gold1"], "d": PAL["orange3"], "h": PAL["gold4"]}


def _mc(s):
    return art(s, MC_LEG)


_MC_HEAD_SRC = """
........3.4.3......
.......24345........
......PQRSSTS.......
....PQRRSSSSTS......
...PQRRSSSSSSSR.....
..PQRRSSAAAAASR.....
.PQRRSSAAB9BAAAR....
PQQRRSAAB90BAAAGHI..
PQQRRSAAABBAAAGHIIIJ
PQQRRSAAAAAAAGHHIIIIJ
.PQQRRSAAAAGGHHHHH.JI
.PPQQRRSAAGGG......H
..PPQQRRRAA..........
...PPQQQRR..........
"""
MC_HEAD = _mc(_MC_HEAD_SRC)
MC_HEAD_HURT = _mc(_MC_HEAD_SRC.replace("AAB9BAAA", "AABBBAAA").replace("AAB90BAAA", "AA%%%BAAA"))
MC_HEAD_SHRIEK = _mc("""
........3.4.3......
.......24345........
......PQRSSTS.......
....PQRRSSSSTS......
...PQRRSSSSSSSR.....
..PQRRSSAAAAASR.....
.PQRRSSAAB9BAAAR.....
PQQRRSAAB90BAAAGHIIJ.
PQQRRSAAABBAAAGHIIIIJ
PQQRRSAAAAAAA6699..JI
.PQQRRSAAAA66GHH....
.PPQQRRSAAGHHHHIJ...
..PPQQRRRAGGGHH.....
...PPQQQRR..........
""")
MC_ROBE = [_mc("""
.......TSSR...........
.....TS3444432........
....TS23.4.32Q........
...TSSRDCECDQQ........
..TSSRRCDEDCQQQ.......
..TSRRRRCDCRQQQP......
.TSSRRRRCECRQQQP......
.TSSRRRRRDRRQQQPP.....
TSSRRRRRRCRRQQQQPP....
TSSRRRRRRRRQQQQQQP....
TSRRRRRRRRRQQQQQQP....
TSRRRRRRRRRQQQQQQP....
TSRRRRRRRRRRQQQQQP....
TSSRRRRRRRRRQQQQQP....
TSSRRRRRRRRRRQQQQP....
.TSRRRRRRRRRRQQQQPP...
.TSRRRRRRRRRRRQQQPP...
.TSSRRRRRRRRRRQQQQP...
.TSSRRRRRRRRRRRQQQP...
..TSRRRRRRRRRRRQQQP...
..TS.RRRR.RRRRR.QQP...
..T..RRR...RRR...QP...
.....RR.....RR....P...
......R......R........
"""), _mc("""
.......TSSR...........
.....TS3444432........
....TS23.4.32Q........
...TSSRDCECDQQ........
..TSSRRCDEDCQQQ.......
..TSRRRRCDCRQQQP......
.TSSRRRRCECRQQQP......
.TSSRRRRRDRRQQQPP.....
TSSRRRRRRCRRQQQQPP....
TSSRRRRRRRRQQQQQQP....
TSRRRRRRRRRQQQQQQP....
TSRRRRRRRRRQQQQQQP....
TSRRRRRRRRRRQQQQQP....
TSSRRRRRRRRRQQQQQP....
TSSRRRRRRRRRRQQQQP....
.TSRRRRRRRRRRQQQQPP...
.TSRRRRRRRRRRRQQQPP...
.TSSRRRRRRRRRRQQQQP...
.TSSRRRRRRRRRRRQQQP...
.TSSRRRRRRRRRRRQQQP...
..T.SRRRR.RRRRR.QQ.P..
.....RRR...RRR...Q....
....RR.....RR.....Q...
...R.......R..........
""")]
MC_BELL = {
    "up": _mc("""
.....cdd.....
....c...d....
....c...d....
...abcdddhh..
..abcddhhhdd.
..abccddhhdd.
..abccdddddd.
.aabccddddddc
.aabcc3333ddc
.aabccddddddd
aabbccddddddcd
aa2333333333dd
.aaabbbbbcccc.
......a3a.....
"""),
    "tilt_r": _mc("""
......cdd......
.....c...d.....
.....c...d.....
....abcdddhh...
...abcddhhhdd..
...abccddhhddd.
..aabccddddddd.
..aabcc3333dddc
..aabccdddddddc
.aabbccddddddcd
.aa23333333333d
..aaabbbbbccccc
.......a3a.....
"""),
    "tilt_l": _mc("""
.....cdd......
....c...d.....
....c...d.....
...abcdddhh...
..abcddhhhdd..
.abccddhhdd...
.abccddddddc..
aabcc3333ddc..
aabccddddddd..
abbccdddddcdd.
a23333333333d.
aaabbbbbcccc..
.....a3a......
"""),
    "fallen": _mc("""
......aabbc....
....aabccddd...
..aabccdddhdh..
.a2bccddddhhh..
a23bccdddddhd.c
a23bbccdddddddd
.a3bbccddddddc.
..aabbccdddc...
....aabbbcc....
"""),
}
MC_TALON = _mc("""
.kl..
jkll.
k.lk.
W..W.
""")
MC_TALON_GRIP = _mc("""
.kkl.
jklllk
k..lk
W...W
""")
MC_RAMP_NEAR = [PAL["crow0"], PAL["crow2"], PAL["crow3"], PAL["stone3"], PAL["stone4"]]
MC_RAMP_FAR = [PAL["crow0"], PAL["crow1"], PAL["crow2"], PAL["crow3"], PAL["stone3"]]


def bird_wing(img, shoulder, ang_deg, span, side, ramp, seed=1, n=11, tatter=0.35, spread=1.0, w0=2.4) -> None:
    """Procedural feathered wing: a bone from the shoulder at elevation `ang_deg`
    (0 = level, + = raised), tattered primaries/secondaries hanging from its trailing edge."""
    a = math.radians(ang_deg)
    sx, sy = shoulder
    d = (side * math.cos(a), -math.sin(a))
    p = (side * math.sin(a), math.cos(a))
    rnd = E.rng(seed)
    bone_len = span * 0.62
    feathers = []
    for i in range(n):
        t = 0.1 + 0.9 * i / (n - 1)
        bx, by = sx + d[0] * bone_len * t, sy + d[1] * bone_len * t
        k = -0.35 + 1.3 * (t ** 1.4) * spread
        fx, fy = p[0] + d[0] * k, p[1] + d[1] * k
        fl = math.hypot(fx, fy)
        fx, fy = fx / fl, fy / fl
        L = span * (0.32 + 0.33 * t ** 1.2)
        if rnd.random() < tatter:
            L *= rnd.uniform(0.62, 0.85)
        feathers.append((bx, by, fx, fy, L, i))
    for (bx, by, fx, fy, L, i) in feathers:
        tx, ty = bx + fx * L, by + fy * L
        qx, qy = -fy, fx
        poly = [(bx + qx * w0, by + qy * w0), (tx + qx * 0.6, ty + qy * 0.6), (tx - qx * 0.6, ty - qy * 0.6),
                (bx - qx * w0, by - qy * w0)]
        E.polygon(img, poly, ramp[1] if i % 2 else ramp[2])
        E.line(img, bx + fx * 2, by + fy * 2, bx + fx * L * 0.75, by + fy * L * 0.75, ramp[3] if i % 2 == 0 else ramp[2])
    ex, ey = sx + d[0] * bone_len, sy + d[1] * bone_len
    for w in range(5):
        ox, oy = p[0] * w, p[1] * w
        col = ramp[4] if w == 0 else ramp[3] if w < 2 else ramp[2] if w < 4 else ramp[1]
        E.line(img, sx + ox, sy + oy, ex + ox * 0.5, ey + oy * 0.5, col)


def _feather_fx(img, x, y, kind=0) -> None:
    """Small loose feather (FX): kind 0 = level, 1 = tilted."""
    pts = [(0, 0, PAL["crow3"]), (1, 0, PAL["crow2"]), (2, 0, PAL["crow2"]), (3, 0, PAL["crow1"]), (-1, 0, PAL["stone3"])] \
        if kind == 0 else [(0, 0, PAL["crow3"]), (1, 1, PAL["crow2"]), (2, 2, PAL["crow1"]), (-1, -1, PAL["stone3"])]
    for (dx, dy, c) in pts:
        E.px(img, x + dx, y + dy, c)


def draw_carrion(pose: dict) -> np.ndarray:
    c = Canvas(MC_W, MC_H)
    bx, by = pose.get("bx", 0), pose.get("by", 0)
    wl, wr = pose.get("wings", (15, 15))
    ground = pose.get("ground", False)
    # wings behind the body
    if wl is not None:
        bird_wing(c.img, (26 + bx, 22 + by), wl, pose.get("span_l", 30), -1, MC_RAMP_FAR, seed=4,
                  spread=pose.get("spread_l", 1.0))
    if wr is not None:
        bird_wing(c.img, (37 + bx, 22 + by), wr, pose.get("span_r", 31), 1, MC_RAMP_NEAR, seed=3,
                  spread=pose.get("spread_r", 1.0))
    # dangling back leg + talon
    if not ground:
        thick_line(c.img, 28 + bx, 40 + by, 29 + bx, MC_G - 3, PAL["iron1"], 2)
        c.put(MC_TALON, 27 + bx, MC_G - 3)
    c.put(MC_ROBE[pose.get("robe", 0)], 20 + bx, 17 + by)
    head = {"normal": MC_HEAD, "hurt": MC_HEAD_HURT, "shriek": MC_HEAD_SHRIEK}[pose.get("head", "normal")]
    c.put(head, 25 + bx + pose.get("hx", 0), 5 + by + pose.get("hy", 0))
    # bell gripped by the front talon
    bell = pose.get("bell", "up")
    if bell == "fallen":
        c.put(MC_BELL["fallen"], pose.get("bell_x", 43), MC_G - 8, sep=OUTLINE)
    elif bell is not None:
        blx, bly = 36 + bx + pose.get("bell_dx", 0), 37 + by + pose.get("bell_dy", 0)
        thick_line(c.img, 35 + bx, 38 + by, blx + 6, bly - 1, PAL["iron2"], 2)
        c.put(MC_BELL[bell], blx, bly, sep=OUTLINE)
        c.put(MC_TALON_GRIP, blx + 4, bly - 3, sep=OUTLINE)
    # FX under
    if pose.get("red_mark"):
        pass
    img = c.finish()
    for ring in pose.get("rings", []):
        rx, ry, rr, strength = ring
        GE._ring(img, rx + bx, ry + by, rr, rr * 0.8, (PAL["gold4"], PAL["gold3"]), dither=strength < 1)
    if pose.get("glint"):
        gx, gy, big = pose["glint"]
        soft_glow(img, gx + 0.5, gy + 0.5, 5 + (3 if big else 0), PAL["red3"], 0.9)
        spark(img, gx, gy, True, (PAL["white"], PAL["red3"]))
        if big:
            for (ox, oy) in ((3, 0), (-3, 0), (0, 3), (0, -3)):
                E.px(img, gx + ox, gy + oy, PAL["red4"])
    for (fx, fy, k) in pose.get("feathers", []):
        _feather_fx(img, fx + bx, fy + by, k)
    for (x, y, big) in pose.get("sparks", []):
        spark(img, x, y, big, (PAL["white"], PAL["gold3"]))
    for (x, y, r) in pose.get("dust", []):
        dust_kick(img, x, y, r)
    if pose.get("eyeglow"):
        soft_glow(img, 35.5 + bx + pose.get("hx", 0), 11.5 + by + pose.get("hy", 0), 4, PAL["red3"], 0.8)
    return img


CARRION_CLIPS = {
    "fly": ([dict(wings=(60, 60), by=1, robe=0),
             dict(wings=(20, 20), by=0, robe=1),
             dict(wings=(-28, -28), by=-1, robe=0, bell_dy=1),
             dict(wings=(5, 5), by=0, robe=1)], 8, True),
    "summon": ([dict(wings=(35, 35), bell="up", bell_dy=-2, robe=0),
                dict(wings=(20, 20), bell="tilt_r", bell_dx=1, robe=1, eyeglow=True,
                     rings=[(43, 44, 9, 1)]),
                dict(wings=(10, 10), bell="tilt_l", bell_dx=-1, robe=0, eyeglow=True,
                     rings=[(42, 44, 12, 1), (42, 44, 7, 0.5)]),
                dict(wings=(45, 45), bell="up", robe=1, rings=[(42, 44, 15, 0.5)],
                     sparks=[(22, 30, False), (58, 33, True), (48, 24, False)])], 10, False),
    "mark": ([dict(wings=(30, 5), span_r=31, robe=0, hx=1),
              dict(wings=(35, -5), span_r=33, spread_r=0.5, robe=1, hx=2, head="shriek"),
              dict(wings=(35, -5), span_r=33, spread_r=0.5, robe=0, hx=2, head="shriek", glint=(61, 26, True)),
              dict(wings=(35, -5), span_r=33, spread_r=0.5, robe=1, hx=2, glint=(61, 26, False))], 10, False),
    "barrage": ([dict(wings=(-35, -35), span_l=24, span_r=25, by=2, robe=0),
                 dict(wings=(75, 75), span_l=32, span_r=33, spread_l=1.25, spread_r=1.25, by=-1, robe=1, head="shriek"),
                 dict(wings=(70, 70), span_l=32, span_r=33, spread_l=1.25, spread_r=1.25, by=-1, robe=0, head="shriek",
                      feathers=[(4, 12, 1), (58, 8, 1), (2, 28, 0), (60, 30, 0), (10, 4, 1), (52, 3, 0)]),
                 dict(wings=(25, 25), robe=1, feathers=[(1, 10, 1), (61, 6, 0), (0, 32, 0)])], 10, False),
    "hit": ([dict(wings=(40, 40), bx=-2, by=-1, head="hurt", robe=1, feathers=[(18, 20, 1), (44, 16, 0), (30, 12, 1)]),
             dict(wings=(25, 25), bx=-1, robe=0, feathers=[(16, 24, 0), (47, 18, 1)])], 12, False),
    "defeat": ([dict(wings=(45, 45), bx=-2, by=-1, head="hurt", robe=1, feathers=[(18, 20, 1), (44, 14, 0)]),
                dict(wings=(-20, -10), span_l=24, span_r=24, by=3, head="hurt", robe=0, bell_dy=1,
                     feathers=[(14, 12, 1), (50, 10, 0), (30, 6, 1)]),
                dict(wings=(-45, -40), span_l=22, span_r=22, by=6, head="hurt", robe=1, ground=True, bell="fallen",
                     bell_x=44, dust=[(20.5, 50.5, 2.2), (44.5, 50.5, 2.4)], feathers=[(10, 18, 0), (54, 16, 1)]),
                dict(wings=(-50, -45), span_l=21, span_r=21, by=7, head="hurt", robe=0, ground=True, bell="fallen",
                     bell_x=45, sparks=[(46, 41, True), (56, 44, False), (41, 45, False)],
                     rings=[(51, 46, 8, 0.5)], feathers=[(8, 24, 1), (57, 22, 0)]),
                dict(wings=(-55, -50), span_l=20, span_r=20, by=8, head="hurt", robe=1, ground=True, bell="fallen",
                     bell_x=45, feathers=[(12, 30, 0), (55, 28, 1), (33, 18, 0)]),
                dict(wings=(-55, -50), span_l=20, span_r=20, by=8, head="hurt", robe=0, ground=True, bell="fallen",
                     bell_x=45, feathers=[(14, 38, 0), (52, 36, 1)])], 8, False),
}


# ======================================================================================
# KING GOLDENFANG (64x64): regal golden-furred wolfhound king - crown, golden fangs,
# red royal cape with ermine, steel breastplate with the Order's grand gold chain, sceptre.
# ======================================================================================
KG_W, KG_H, KG_PIV = 64, 64, 0.08
KG_G = ground_row(KG_H, KG_PIV)  # 58
KG_LEG = {"A": PAL["brown1"], "B": PAL["gold0"], "C": PAL["gold1"], "D": PAL["gold2"], "E": PAL["bone3"],
          "N": PAL["brown0"], "K": PAL["black"], "O": PAL["snow2"], "U": PAL["snow1"], "V": PAL["snow3"]}


def _kg(s):
    return art(s, KG_LEG)


_KG_HEAD_SRC = """
........D.D.D.............
......ADEDEDEC............
.....ACDEEEEDDC...........
....NACDEEEDDDDC..........
...NNACDDDDDDDDDDC........
..NNACCDDDDDDDDDDDC.......
.NNACC%%%%DDDDDDDDDC......
.NACCD%59x%DDDDDDDDDEDC...
.ACCCDD%%%DDDCDEEEEEEEEDKK
ACCCCDDDDDDDCDDDDDDDDDDDKK
ACCCCCDDDDDDCCCCCCCCCCCC%.
.ACCCCDDDDDC%%%%%%%%%%%%..
.ACCCCCDDDC54C45CCCC5C....
..ABCCCCCCC4BCCCCCCBB.....
..AABCCCBCCBCCBCB.........
...AABCB.BCC.BC...........
....AB....BC..B...........
"""
KG_HEAD = _kg(_KG_HEAD_SRC)
KG_HEAD_GLOW = _kg(_KG_HEAD_SRC.replace("%59x%", "%55y%"))
KG_HEAD_HURT = _kg(_KG_HEAD_SRC.replace("%59x%", "%%%%%"))
KG_HEAD_ROAR = _kg("""
..........D.D...............
.....ADEDDEDEC..............
....ACDEEEEEDDC.............
...NACDEEEDDDDDC..........KK
..NNACDDDDDDDDDDC.......DDKK
.NNACCDDDDDDDDDDDC....DEEDC.
.NACC%%%%DDDDDDDDDC.DEEEDC..
.NACD%55y%DDDDDDDCDEEEDC5...
.ACCDD%%%DDDDDDCDDDDDC%5....
ACCCCDDDDDDDCDDDDDC%66%.....
ACCCCCDDDDDDCCCC%%6666%.....
.ACCCCDDDDDC%6666666%.......
.ACCCCCDDD%66600%%5%........
..ABCCCCCCC%%45CCC5C........
..AABCCCBCCBCCBCB...........
...AABCB.BCC.BC.............
....AB....BC..B.............
""")
KG_CROWN = _kg("""
.5..0..5..
.4..4..4..
.43444434.
2349349432
.23333332.
""")
KG_RUFF = _kg("""
.....DDEDD.DD.....
...CDDEEDDDDDDC...
..CDDDDDDDDDDDDC..
.CCDDDCDDDCDDDCC..
BCCDCCDCCDCCDCCB..
.BC.BC.BCC.BC.BC..
""")
KG_ERMINE = _kg("""
..VVOVOOVOVOOVOVO..
.VOKOVVOKOVOVKOVOO.
VVOOVOKOOVOOVOOKOOU
.UOUOOUOOUOUOOUOU..
""")
KG_TORSO = _kg("""
....jkllllllkj.....
..jklmmmlllllkj....
.jkllm54333345kj...
jklllm4......4kkj..
jkllllm3....3kkkkj.
jklllkkm3..3kkkkkj.
jkllkkkkk44kkkkkkj.
jklkkkkk4554kkkkji.
jkkkkkkk5995kkkkji.
jkkkkkkkk55kkkkkji.
.jkkkkkkkkkkkkkji..
.i23333333333332i..
.i34444454444443i..
.lkmklkl4lklkkjkji.
.kmklklk4klkkjkjii.
lmklklkl4lklkkjkjii
kmklklkl4klkkjkjjii
lmklklkl4lklkkjkjjii
kmklklkl4klkkjkjiiii
lmklklkl4lklkkjkjjii
kmklklkl4klkkjkjiiii
lmklklkl4lklkkjkjjii
.3444444434444443332
.2333333323333333221
""")
KG_LEGS = {
    "stand": _kg("""
.jkllj.....jkllj.
.jkllj.....jkllj.
.jkllj.....jkllj.
.jkllj.....jkllj.
.jklkj.....jklkj.
.ilmmi.....ilmmi.
.jkllj.....jkllj.
.jkkkj.....jkkkj.
.34443.....34443.
.jkkkj.....jkkkj.
jkkkkkj...jkkkkkj
jkllkkkj..jkllkkkj
iiiiiiii..iiiiiiii
"""),
    "step_a": _kg("""
..jkllj...jkllj..
..jkllj...jkllj..
..jkllj...jkllj..
..jkllj....jkllj.
.jklkj......jklkj
.ilmmi......ilmmi
.jkllj.......jkllj
jkkkj........jkkkj
34443........34443
jkkkj........jkkkj
kkkkkj......jkkkkkj
kllkkkj.....jkllkkkj
iiiiiii.....iiiiiiii
"""),
    "step_b": _kg("""
.jkllj.....jkllj.
.jkllj.....jkllj.
.jkllj.....jkllj.
.jkllj....jkllj..
.jklkj....jklkj..
.ilmmi...ilmmi...
.jkllj...jkllj...
.jkkkj..jkkkj....
.34443..34443....
.jkkkj..jkkkj....
jkkkkkj.kkkkkj...
jkllkkkjkllkkkj..
iiiiiiiiiiiiiii..
"""),
    "kneel": _kg("""
.jkllj...........
.jkllkkkkkkj.....
.ilmmkkkkkkkkj...
.jkllllllllkkkj..
..iiiiiiiiiiiii..
"""),
}
KG_TAIL = [_kg("""
..DDE....
.DDEEDD..
CDDDDDDC.
CCDDDCCC.
.BCCCCBB.
..BBCBB..
...AB....
"""), _kg("""
.DDE.....
DDEEDD...
CDDDDDC..
CCDDDCCC.
.BCCCCBB.
..BBCBB..
...AB....
""")]
KG_SCEPTRE_HEAD = _kg("""
...3444...
..34..54..
.34.99.43.
.4.9909.4.
.4.9999.4.
.34.99.43.
..34..43..
...3443...
....44....
""")
KG_CROWN_TUMBLE = _kg("""
....5.....
...44..0..
..434.44..
.2344434..
2349344...
.2333332..
..2322....
""")
KG_CROWN_FALLEN = _kg("""
.5....0....5.
.4....4....4.
.43444444434.
23493334934322
.233333333332.
""")
KG_HAND = _kg("""
.DDC
DEDDC
CDDC.
""")


def kg_cape(img, sway: int = 0, lift: int = 0, ground: int = KG_G) -> None:
    """Royal cape: drapes from the shoulders to the ground, flaring out behind (left).
    Lit on the left, folds as darker vertical strokes, dark hem."""
    top_l, top_r = (17, 19), (37, 19)
    bot_l, bot_r = (3 + sway, ground - lift), (42 + sway // 2, ground - lift)
    poly = [top_l, top_r, (40 + sway // 2, 36), bot_r, (bot_r[0] - 6, bot_r[1] + 1), (22 + sway, ground - lift - 1),
            (12 + sway, bot_l[1] + 1), bot_l, (9 + sway // 2, 34)]
    mask_img = E.new(img.shape[1], img.shape[0])
    E.polygon(mask_img, poly, (255, 255, 255, 255))
    m = mask_img[:, :, 3] > 0
    ys, xs = np.nonzero(m)
    for x, y in zip(xs, ys):
        t = (y - 19) / max(1, (ground - 19))
        left = 17 + (bot_l[0] - 17) * t  # approximate left edge at this row
        rel = (x - left) / max(1.0, 25 + 14 * t)
        if rel < 0.08:
            c = PAL["red3"]
        elif rel < 0.45:
            c = PAL["red2"]
        elif rel < 0.8:
            c = PAL["red1"]
        else:
            c = PAL["red0"]
        img[y, x] = c
    # folds
    for fx in (0.3, 0.55, 0.78):
        for y in range(24, ground - lift):
            t = (y - 19) / max(1, (ground - 19))
            left = 17 + (bot_l[0] - 17) * t
            x = int(round(left + fx * (25 + 14 * t)))
            if 0 <= x < img.shape[1] and m[y, x]:
                img[y, x] = PAL["red1"] if fx < 0.7 else PAL["red0"]
                if fx < 0.7 and x - 1 >= 0 and m[y, x - 1]:
                    img[y, x - 1] = PAL["red3"] if fx < 0.4 else PAL["red2"]
    # ermine hem lining peeking at the bottom
    for x in range(0, img.shape[1]):
        col = [y for y in range(img.shape[0]) if m[y, x]]
        if col and col[-1] > ground - lift - 3:
            y = col[-1]
            img[y, x] = PAL["snow2"] if (x // 2) % 3 else PAL["black"]


def _arc(img, cx, cy, r, a0, a1, color, dither=False) -> None:
    n = int(abs(a1 - a0) * r * 2) + 2
    seen = set()
    for i in range(n):
        a = a0 + (a1 - a0) * i / (n - 1)
        x, y = int(round(cx + math.cos(a) * r)), int(round(cy + math.sin(a) * r * 1.1))
        if (x, y) in seen:
            continue
        seen.add((x, y))
        if dither and (x + y) % 2:
            continue
        E.px(img, x, y, color)


def draw_goldenfang(pose: dict) -> np.ndarray:
    c = Canvas(KG_W, KG_H)
    g = KG_G
    bx, by = pose.get("bx", 0), pose.get("by", 0)
    hx, hy = bx + pose.get("hx", 0), by + pose.get("hy", 0)
    # aura behind everything (windup / command)
    if pose.get("gold_aura"):
        k = pose["gold_aura"]
        soft_glow(c.fx_under, 30 + bx, 32 + by, 20 + k * 4, PAL["gold3"], 0.18 + 0.1 * k)
    c.put(KG_TAIL[pose.get("tail", 0)], 3 + bx, 42 + by)
    cape = E.new(KG_W, KG_H)
    kg_cape(cape, pose.get("sway", 0), pose.get("cape_lift", 0), g if not pose.get("kneel") else g)
    c.put(E.shift(cape, bx, by if pose.get("kneel") else 0), 0, 0)
    legs = KG_LEGS[pose.get("legs", "stand")]
    c.put(legs, 22 + bx + (0 if pose.get("legs", "stand") != "step_a" else -1), g - legs.shape[0] + 1)
    c.put(KG_TORSO, 18 + bx, 21 + by)
    c.put(KG_ERMINE, 16 + bx, 18 + by)
    c.put(KG_RUFF, 18 + hx, 15 + hy)
    head = {"normal": KG_HEAD, "glow": KG_HEAD_GLOW, "hurt": KG_HEAD_HURT, "roar": KG_HEAD_ROAR}[pose.get("head", "normal")]
    c.put(head, 19 + hx, 4 + hy)
    if not pose.get("no_crown"):
        c.put(KG_CROWN, 24 + hx + pose.get("cx", 0), 1 + hy + pose.get("cy", 0), sep=OUTLINE)
    # sceptre + near arm
    sc = pose.get("sceptre", (47, 32, 0))  # hand x, y, raise (0 = at side, 1 = high)
    hxp, hyp, mode = sc
    shoulder = (35 + bx, 24 + by)
    arm = E.new(KG_W, KG_H)
    elbow = pose.get("elbow", (shoulder[0] + 4, shoulder[1] + 7))
    thick_line(arm, shoulder[0], shoulder[1], elbow[0], elbow[1], PAL["red2"], 3)
    thick_line(arm, shoulder[0] - 1, shoulder[1], elbow[0] - 1, elbow[1], PAL["red3"], 1)
    thick_line(arm, elbow[0], elbow[1], hxp, hyp, PAL["red1"], 3)
    thick_line(arm, elbow[0], elbow[1] - 1, hxp, hyp - 1, PAL["red2"], 1)
    cx_, cy_ = hxp + (elbow[0] - hxp) * 0.3, hyp + (elbow[1] - hyp) * 0.3
    shaded_disc(arm, cx_, cy_, 1.8, [PAL["gold1"], PAL["gold2"], PAL["gold3"], PAL["gold4"]])
    # sceptre rod
    rod_top = pose.get("rod_top", (hxp + 1, hyp - 18))
    rod_bot = pose.get("rod_bot", (hxp + 1, hyp + 22))
    rod = E.new(KG_W, KG_H)
    thick_line(rod, rod_top[0], rod_top[1], rod_bot[0], rod_bot[1], PAL["gold2"], 2)
    E.line(rod, rod_top[0], rod_top[1], rod_bot[0], rod_bot[1], PAL["gold3"])
    c.put(rod, 0, 0, sep=OUTLINE)
    sh = KG_SCEPTRE_HEAD
    c.put(sh, rod_top[0] - 4, rod_top[1] - 8, sep=OUTLINE)
    c.put(arm, 0, 0, sep=OUTLINE)
    c.put(KG_HAND, hxp - 1, hyp - 1, sep=OUTLINE)
    img = c.finish()
    gem = (rod_top[0] + 0.5, rod_top[1] - 4.5)
    if pose.get("gem_glow"):
        k = pose["gem_glow"]
        soft_glow(img, gem[0], gem[1], 4 + 3 * k, PAL["gold3"] if k < 3 else PAL["gold4"], 0.6 + 0.12 * k)
        spark(img, int(gem[0]), int(gem[1]), True, (PAL["white"], PAL["gold4"]))
    if pose.get("rays"):
        for i in range(8):
            a = i / 8 * math.tau + pose["rays"] * 0.2
            for r in range(8, 8 + pose.get("ray_len", 4)):
                E.px(img, gem[0] + math.cos(a) * r, gem[1] + math.sin(a) * r, PAL["gold4"] if r % 2 else PAL["gold3"])
    if pose.get("eyes_glow"):
        soft_glow(img, 27.5 + hx, 11.5 + hy, 4.0, PAL["gold4"], 0.9)
    for ring in pose.get("rings", []):
        rx, ry, rr, strength = ring
        _arc(img, rx + bx, ry + by, rr, -1.1, 1.1, PAL["gold4"] if strength >= 1 else PAL["gold3"], dither=strength < 1)
        _arc(img, rx + bx, ry + by, rr - 1, -0.9, 0.9, PAL["gold3"] if strength >= 1 else PAL["gold2"], dither=True)
    for (x, y, big) in pose.get("sparks", []):
        spark(img, x, y, big, (PAL["white"], PAL["gold3"]))
    for (x, y, r) in pose.get("dust", []):
        dust_kick(img, x, y, r)
    if pose.get("crown_at"):
        x, y, rot = pose["crown_at"]
        cr = {0: KG_CROWN, 1: KG_CROWN_TUMBLE, 2: E.flip_x(KG_CROWN_TUMBLE), 3: KG_CROWN_FALLEN}[rot]
        cr = E.outline(np.pad(cr, ((1, 1), (1, 1), (0, 0))), OUTLINE)
        blit(img, cr, x - cr.shape[1] // 2, y - cr.shape[0] // 2)
    if pose.get("burst"):
        x, y, r = pose["burst"]
        soft_glow(img, x, y, r, PAL["gold4"], 1.0)
        for i in range(6):
            a = i / 6 * math.tau
            E.line(img, x + math.cos(a) * 2, y + math.sin(a) * 2, x + math.cos(a) * (r - 1), y + math.sin(a) * (r - 1), PAL["gold4"])
        spark(img, int(x), int(y), True, (PAL["white"], PAL["white"]))
    return img


GOLDENFANG_CLIPS = {
    "idle": ([dict(sway=0, tail=0),
              dict(sway=1, by=0, hy=1, tail=1, gem_glow=1),
              dict(sway=1, tail=1),
              dict(sway=0, hy=1, tail=0)], 6, True),
    "walk": ([dict(legs="step_a", sway=-2, tail=0, by=0),
              dict(legs="stand", sway=-1, by=-1, tail=1),
              dict(legs="step_b", sway=-2, tail=0),
              dict(legs="stand", sway=-1, by=-1, tail=1)], 8, True),
    "command": ([dict(sceptre=(45, 26, 0), elbow=(41, 25), rod_top=(46, 9), rod_bot=(46, 46)),
                 dict(sceptre=(44, 14, 1), elbow=(40, 19), rod_top=(45, 2 + 8), rod_bot=(45, 34), gem_glow=2, head="glow",
                      hy=-1, sway=1),
                 dict(sceptre=(44, 14, 1), elbow=(40, 19), rod_top=(45, 10), rod_bot=(45, 34), gem_glow=3, rays=1, ray_len=5,
                      head="glow", hy=-1, sway=1),
                 dict(sceptre=(45, 26, 0), elbow=(41, 25), rod_top=(46, 9), rod_bot=(46, 46), gem_glow=1)], 8, False),
    "windup": ([dict(sceptre=(46, 26, 0), elbow=(41, 26), rod_top=(51, 11), rod_bot=(42, 44), gold_aura=1, gem_glow=1,
                     head="glow", eyes_glow=True, by=1),
                dict(sceptre=(46, 26, 0), elbow=(41, 26), rod_top=(51, 11), rod_bot=(42, 44), gold_aura=2, gem_glow=2,
                     head="glow", eyes_glow=True, by=1, rays=0, ray_len=3),
                dict(sceptre=(46, 26, 0), elbow=(41, 26), rod_top=(51, 11), rod_bot=(42, 44), gold_aura=3, gem_glow=3,
                     head="glow", eyes_glow=True, by=1, rays=1, ray_len=4),
                dict(sceptre=(46, 26, 0), elbow=(41, 26), rod_top=(51, 11), rod_bot=(42, 44), gold_aura=2, gem_glow=2,
                     head="glow", eyes_glow=True, by=1, rays=0, ray_len=3)], 10, True),
    "volley": ([dict(sceptre=(48, 24, 0), elbow=(42, 24), rod_top=(55, 13), rod_bot=(42, 38), gem_glow=3, head="glow",
                     burst=(55.5, 8.5, 7), bx=1),
                dict(sceptre=(49, 24, 0), elbow=(43, 24), rod_top=(56, 13), rod_bot=(43, 38), gem_glow=2, head="glow",
                     sparks=[(60, 5, True), (61, 12, False), (57, 2, False)], bx=1),
                dict(sceptre=(46, 26, 0), elbow=(41, 26), rod_top=(51, 11), rod_bot=(42, 44), gem_glow=1, bx=-1),
                dict(sceptre=(47, 32, 0))], 10, False),
    "roar": ([dict(head="normal", hy=1, bx=-1, sway=0),
              dict(head="roar", hy=-2, hx=1, sway=2, eyes_glow=True, rings=[(44, 12, 6, 1)], cape_lift=1,
                   sceptre=(46, 36, 0), elbow=(40, 31), rod_top=(55, 28), rod_bot=(40, 55)),
              dict(head="roar", hy=-2, hx=1, sway=3, eyes_glow=True, rings=[(44, 12, 10, 1), (44, 12, 6, 0.5)],
                   cape_lift=1, sparks=[(59, 3, True), (61, 19, False)],
                   sceptre=(46, 36, 0), elbow=(40, 31), rod_top=(55, 28), rod_bot=(40, 55)),
              dict(head="roar", hy=-1, hx=1, sway=2, eyes_glow=True, rings=[(44, 12, 14, 0.5), (44, 12, 9, 0.5)],
                   sceptre=(46, 36, 0), elbow=(40, 31), rod_top=(55, 28), rod_bot=(40, 55))], 8, False),
    "hit": ([dict(bx=-2, hx=-3, hy=-1, head="hurt", sway=2, cx=-1, sparks=[(44, 16, True)]),
             dict(bx=-1, hx=-1, sway=1)], 12, False),
    "defeat": ([dict(bx=-2, hx=-3, hy=-1, head="hurt", sway=2, cx=-2, cy=0),
                dict(bx=-1, by=4, hx=-1, hy=5, head="hurt", legs="stand", cx=-3, cy=1, sway=1,
                     sceptre=(46, 36, 0), rod_top=(52, 20), rod_bot=(40, 55)),
                dict(by=9, hy=11, head="hurt", legs="kneel", kneel=True, no_crown=True, crown_at=(38, 6, 1),
                     sceptre=(46, 44, 0), elbow=(40, 38), rod_top=(58, 50), rod_bot=(30, 57), dust=[(46.5, 57.5, 2.0)]),
                dict(by=9, hy=11, head="hurt", legs="kneel", kneel=True, no_crown=True, crown_at=(50, 52, 2),
                     sceptre=(46, 44, 0), elbow=(40, 38), rod_top=(58, 50), rod_bot=(30, 57), sparks=[(53, 49, True)]),
                dict(by=10, hy=13, head="hurt", legs="kneel", kneel=True, no_crown=True, crown_at=(54, 55, 3),
                     sceptre=(46, 44, 0), elbow=(40, 38), rod_top=(58, 50), rod_bot=(30, 57)),
                dict(by=10, hy=13, head="hurt", legs="kneel", kneel=True, no_crown=True, crown_at=(54, 55, 3),
                     sceptre=(46, 44, 0), elbow=(40, 38), rod_top=(58, 50), rod_bot=(30, 57), sparks=[(57, 53, False)])],
               8, False),
}


# ======================================================================================
# PORTRAITS (64x64 busts, transparent background, shoulders cut at the bottom edge -
# the same framing as the hero portrait). Big forms are shaded with flat bands from a
# distance-field normal map; faces are hand-placed pixels.
# ======================================================================================
PW = PH = 64
W, H, O = PW, PH, OUTLINE
FUR = [PAL["gold0"], PAL["gold1"], PAL["gold2"], PAL["gold3"]]
FUR_D = [PAL["brown1"], PAL["gold0"], PAL["gold1"], PAL["gold2"]]
RED = [PAL["red0"], PAL["red1"], PAL["red2"], PAL["red3"]]
IRON = [PAL["iron1"], PAL["iron2"], PAL["iron3"], PAL["iron4"]]
GOLD = [PAL["gold1"], PAL["gold2"], PAL["gold3"], PAL["gold4"]]


def layer(mask, ramp, **kw) -> np.ndarray:
    im = E.new(PW, PH)
    shade_region(im, mask, ramp, dither=False, **kw)
    return im


def king_portrait():
    c = Canvas(W, H)
    cape = poly_mask([(0, 64), (1, 52), (8, 46), (22, 43), (44, 43), (57, 46), (64, 53), (64, 64)], W, H)
    cl = layer(cape, RED, cap=8, slope=1.5)
    for (x0, y0, x1, y1) in ((6, 63, 9, 52), (13, 63, 15, 50), (56, 63, 54, 51), (60, 63, 59, 54)):
        E.line(cl, x0, y0, x1, y1, PAL["red1"])
        E.line(cl, x0 - 1, y0, x1 - 1, y1, PAL["red3"])
    c.put(cl, 0, 0)
    plate = poly_mask([(19, 64), (20, 54), (27, 50), (40, 50), (47, 54), (48, 64)], W, H)
    c.put(layer(plate, IRON, cap=5), 0, 0, sep=O)
    erm = poly_mask([(8, 48), (14, 43), (24, 44), (33, 45), (44, 43), (55, 46), (50, 51), (40, 51), (33, 52), (24, 51), (16, 52)], W, H)
    im = E.new(W, H)
    ys, xs = np.nonzero(erm)
    for x, y in zip(xs, ys):
        im[y, x] = PAL["snow3"] if y < 46 else (PAL["snow2"] if y < 49 else PAL["snow1"])
    for (x, y) in ((13, 47), (19, 49), (25, 47), (31, 49), (37, 48), (43, 47), (49, 48)):
        im[y, x] = PAL["black"]; im[y + 1, x] = PAL["black"]
    c.put(im, 0, 0, sep=O)
    for x in range(24, 44, 2):
        y = 53 + int(round(3 * math.sin((x - 24) / 19 * math.pi)))
        E.px(c.img, x, y, PAL["gold3"]); E.px(c.img, x + 1, y, PAL["gold1"])
    med = art("""
.2332.
234432
349943
349943
234432
.2332.
""")
    c.put(med, 31, 56, sep=O)
    ruff = poly_mask([(12, 46), (11, 40), (14, 41), (13, 35), (17, 37), (18, 31), (22, 34), (26, 30), (30, 34), (35, 31), (38, 35),
                        (43, 32), (45, 36), (50, 34), (50, 40), (53, 42), (47, 45), (40, 47), (30, 47), (20, 48)], W, H)
    c.put(layer(ruff, FUR, cap=4, slope=2.0), 0, 0, sep=O)
    skull = ell_mask(28, 26, 13, 12, W, H)
    muzzle = poly_mask([(36, 18), (46, 20), (54, 22), (58, 25), (58, 31), (50, 34), (40, 36), (34, 34)], W, H)
    c.put(layer(skull | muzzle, FUR, cap=7, slope=2.4, bias=0.02), 0, 0, sep=O)
    beard = poly_mask([(33, 34), (40, 36), (50, 34), (52, 38), (49, 39), (50, 43), (46, 41), (44, 46), (41, 42), (38, 45), (36, 40), (32, 42)], W, H)
    c.put(layer(beard, FUR_D, cap=3, slope=2.0), 0, 0, sep=O)
    ear = poly_mask([(16, 17), (23, 15), (25, 20), (21, 27), (14, 26), (12, 21)], W, H)
    c.put(layer(ear, [PAL["brown0"], PAL["brown1"], PAL["gold0"], PAL["gold1"]], cap=3), 0, 0, sep=O)
    # eye: heavy slanted brow, gold iris, red pupil, glint
    face = """
.%%%.........
.%%%%%%......
..CC%%%%%....
..%W5559%....
..%55x9%.....
...%%%%......
"""
    c.put(art(face, KG_LEG), 31, 17)
    c.put(art("""
.xx.
xxWx
xxxx
.xx.
""", KG_LEG), 55, 24, sep=O)
    # sly grin: mouth line rising to the cheek, gold fangs over the lip
    mouth = art("""
.%%...............
..%%%.............
....%%%%%%%%%%%%..
.......5.....45...
.......4......5...
""", KG_LEG)
    c.put(mouth, 38, 28)
    crown = art("""
...5......0......5..
...4.....404.....4..
..434...34543...434.
.3444333444443334443
.2344444444444444432
.23499433499943349432
..2333333333333333332
...22222222222222222.
""", KG_LEG)
    c.put(crown, 13, 8, sep=O)
    return c.finish()


CROW = [PAL["crow0"], PAL["crow1"], PAL["crow2"], PAL["crow3"], PAL["stone3"]]
HOOD = [PAL["crow0"], PAL["violet0"], PAL["violet1"], PAL["violet2"], PAL["violet3"]]
BONE = [PAL["bone0"], PAL["bone1"], PAL["bone2"], PAL["bone3"], PAL["bone4"]]
BRONZE = [PAL["brown1"], PAL["gold0"], PAL["gold1"], PAL["orange3"], PAL["gold4"]]


def feathers_mask(base_y, x0, x1, n, length, seed):
    rnd = E.rng(seed)
    m = np.zeros((H, W), bool)
    for i in range(n):
        x = x0 + (x1 - x0) * i / (n - 1)
        L = length * rnd.uniform(0.7, 1.1)
        ang = math.radians(100 + (i - n / 2) * 9)
        tipx, tipy = x + math.cos(ang) * L * 0.4, base_y + L
        m |= poly_mask([(x - 3, base_y), (x + 3, base_y), (tipx + 1, tipy), (tipx - 1, tipy)], W, H)
    return m

def carrion_portrait():
    c = Canvas(W, H)
    # feathered shoulders (wings folded around the bust)
    sh = poly_mask([(0, 64), (0, 46), (6, 40), (14, 38), (22, 42), (42, 42), (52, 38), (60, 40), (64, 46), (64, 64)], W, H)
    sh_l = layer(sh, CROW, cap=6, slope=1.6)
    # feather scallops
    for row in range(44, 64, 4):
        for x in range((row // 4) % 2 * 3, 64, 6):
            for k in range(4):
                E.px(sh_l, x + k, row + (1 if k in (0, 3) else 0), PAL["crow3"] if x < 30 else PAL["crow2"])
    c.put(sh_l * (sh[:, :, None]), 0, 0)
    # hood
    hood = poly_mask([(10, 50), (8, 36), (11, 22), (18, 11), (27, 6), (36, 7), (44, 13), (48, 22), (49, 32), (46, 44), (40, 50),
                        (34, 47), (28, 51), (22, 47), (16, 52)], W, H)
    c.put(layer(hood, HOOD, cap=7, slope=1.8), 0, 0, sep=O)
    # face shadow inside the hood opening
    face = poly_mask([(22, 20), (30, 15), (40, 17), (46, 24), (46, 36), (40, 42), (30, 42), (24, 36), (21, 28)], W, H)
    fl = E.new(W, H)
    ys, xs = np.nonzero(face)
    for x, y in zip(xs, ys):
        fl[y, x] = PAL["crow1"] if (x - 22) + (y - 15) < 12 else PAL["crow0"]
    c.put(fl, 0, 0, sep=O)
    # crow head inside the hood: rounded crown of feathers catching a little light
    head_in = ell_mask(33, 27, 9, 10, W, H) & face
    hl = E.new(W, H)
    shade_region(hl, head_in, [PAL["crow0"], PAL["crow1"], PAL["crow2"], PAL["crow3"]], cap=4, slope=2.0, dither=False)
    c.put(hl, 0, 0)
    E.line(c.img, 28, 21, 38, 19, PAL["stone3"])
    # eye (glowing red)
    eye = art("""
.%%%%%.
%%69999%
%6990W9%
%69999%.
.%%%%%..
""")
    c.put(eye, 31, 22)
    # beak
    beak = poly_mask([(38, 26), (48, 24), (56, 25), (61, 27), (63, 31), (62, 36), (60, 39), (59, 35), (56, 32), (48, 33), (39, 35)], W, H)
    bl = layer(beak, BONE, cap=3, slope=2.0, bias=0.08)
    E.line(bl, 44, 31, 58, 31, PAL["bone1"])  # beak seam
    E.px(bl, 46, 28, PAL["outline"]); E.px(bl, 47, 28, PAL["bone0"])  # nostril
    for y in range(24, 37):  # gold ring on the beak
        for x in (43, 44):
            if beak[y, x]:
                bl[y, x] = PAL["gold3"] if x == 43 else PAL["gold2"]
    c.put(bl, 0, 0, sep=O)
    # gold circlet on the hood
    circ = art("""
..5....0....5..
..4...444...4..
.434.34943.434.
2344444444444432
.23333333333332.
""")
    c.put(circ, 17, 7, sep=O)
    # gold chain collar
    for i, x in enumerate(range(18, 44, 2)):
        y = 46 + int(round(3 * math.sin((x - 18) / 25 * math.pi)))
        E.px(c.img, x, y, PAL["gold3"]); E.px(c.img, x + 1, y, PAL["gold1"])
        E.px(c.img, x, y + 1, PAL["gold1"])
    # bell peeking bottom-right
    bell = poly_mask([(47, 64), (49, 56), (52, 51), (56, 49), (60, 50), (63, 53), (64, 64)], W, H)
    c.put(layer(bell, BRONZE, cap=4, slope=2.0), 0, 0, sep=O)
    for x in range(48, 64):
        if bell[60, x]:
            c.img[60, x] = PAL["gold2"]
    img = c.finish()
    soft_glow(img, 35.5, 24.5, 5, PAL["red3"], 0.55)
    return img


IRON5 = [PAL["iron0"], PAL["iron1"], PAL["iron2"], PAL["iron3"], PAL["iron4"]]
RED5 = [PAL["red0"], PAL["red1"], PAL["red2"], PAL["red3"], PAL["red4"]]


def barkhelm_portrait():
    c = Canvas(W, H)
    # plume behind (flowing back-left)
    plume = poly_mask([(24, 8), (18, 4), (10, 5), (4, 10), (2, 18), (4, 27), (8, 32), (10, 26), (13, 30), (14, 22), (18, 24), (19, 16), (25, 14)], W, H)
    pl = layer(plume, RED5, cap=4, slope=2.0)
    for (x0, y0, x1, y1) in ((6, 12, 20, 7), (5, 19, 17, 11), (7, 26, 16, 17)):
        E.line(pl, x0, y0, x1, y1, PAL["red1"])
    c.put(pl * plume[:, :, None], 0, 0)
    # shoulders: pauldrons + tabard
    tab = poly_mask([(18, 64), (20, 50), (44, 50), (46, 64)], W, H)
    tl = layer(tab, RED, cap=6, slope=1.5)
    for y in (55, 56, 57):
        for x in range(19, 46):
            if tab[y, x]:
                tl[y, x] = PAL["gold3"] if y == 55 else (PAL["gold4"] if y == 56 else PAL["gold1"])
    for (x, y) in ((25, 56), (31, 56), (37, 56)):
        tl[y, x] = PAL["gold1"]
    tl[58, 32] = PAL["gold3"]; tl[59, 32] = PAL["gold2"]; tl[58, 31] = PAL["gold2"]; tl[58, 33] = PAL["gold2"]
    c.put(tl, 0, 0)
    pl_l = ell_mask(10, 56, 13, 11, W, H)
    pl_r = ell_mask(54, 57, 12, 10, W, H)
    for m in (pl_l, pl_r):
        lay = layer(m, IRON, cap=5, slope=2.0)
        c.put(lay, 0, 0, sep=O)
    # gold rims on pauldrons
    for (cx, cy, rx, ry) in ((10, 56, 13, 11), (54, 57, 12, 10)):
        for i in range(60):
            a = math.pi + i / 59 * math.pi
            x, y = int(round(cx + math.cos(a) * (rx - 2))), int(round(cy + math.sin(a) * (ry - 2)))
            if 0 <= x < W and 0 <= y < H:
                c.img[y, x] = PAL["gold2"] if a < math.pi * 1.5 else PAL["gold1"]
    # gorget (gold collar)
    gor = poly_mask([(15, 45), (19, 41), (31, 43), (44, 41), (49, 45), (45, 49), (32, 50), (19, 49)], W, H)
    gl = layer(gor, [PAL["gold0"], PAL["gold1"], PAL["gold2"], PAL["gold3"]], cap=3, slope=2.0)
    for x in range(19, 47, 4):
        y = 45 + (0 if abs(x - 32) > 8 else 1)
        if gor[y, x]:
            gl[y, x] = PAL["gold4"]
            gl[y + 1, x] = PAL["gold1"]
    c.put(gl, 0, 0, sep=O)
    tag = art("""
.232.
23942
.343.
""")
    c.put(tag, 30, 49, sep=O)
    # helm dome
    dome = ell_mask(28, 24, 15, 15, W, H)
    c.put(layer(dome, IRON5, cap=8, slope=2.2), 0, 0, sep=O)
    # iron dog ears
    for pts in ([(16, 14), (19, 2), (25, 11)], [(29, 9), (34, 1), (38, 11)]):
        m = poly_mask(pts, W, H)
        c.put(layer(m, IRON, cap=2, slope=2.0), 0, 0, sep=O)
    # visor snout (hounskull)
    snout = poly_mask([(33, 20), (42, 20), (52, 22), (60, 26), (61, 30), (58, 34), (48, 37), (38, 39), (34, 37), (32, 31), (32, 25)], W, H)
    sl = layer(snout, IRON5, cap=5, slope=2.4, bias=0.03)
    for i, (x, y) in enumerate(((44, 31), (47, 30), (50, 29), (53, 29), (46, 34), (49, 33), (52, 32))):
        sl[y, x] = PAL["outline"]
    E.line(sl, 34, 36, 56, 32, PAL["iron1"])  # visor seam
    c.put(sl, 0, 0, sep=O)
    # specular streak on the dome
    for (x, y) in ((19, 14), (20, 13), (21, 12), (22, 12), (18, 16), (18, 17)):
        c.img[y, x] = PAL["iron4"]
    c.img[12, 23] = PAL["white"]
    # eye slit with glowing amber eyes
    slit = art("""
%%%%%%%%%%%%%%%%%
%%%%Fyy%%%%%%Fy%%
.%%%%%%%%%%%%%%%.
""")
    c.put(slit, 23, 22)
    # gold trim along the helm rim + hinge rivet
    for x in range(14, 32):
        y = 34 + int(round((x - 14) * 0.15))
        if dome[y, x]:
            c.img[y, x] = PAL["gold2"]
    for (x, y, col) in ((19, 29, PAL["gold4"]), (20, 29, PAL["gold2"]), (19, 30, PAL["gold2"]), (20, 30, PAL["gold1"])):
        c.img[y, x] = col
    img = c.finish()
    soft_glow(img, 29.5, 23.5, 6, PAL["fire2"], 0.45)
    soft_glow(img, 37.5, 23.5, 4, PAL["fire2"], 0.35)
    return img


# ======================================================================================
# Registry / preview
# ======================================================================================
BOSSES = {
    "sir_barkhelm": (draw_barkhelm, BARKHELM_CLIPS, BK_PIV),
    "mother_carrion": (draw_carrion, CARRION_CLIPS, MC_PIV),
    "king_goldenfang": (draw_goldenfang, GOLDENFANG_CLIPS, KG_PIV),
}


def boss_frames(bid: str, clip: str) -> List[np.ndarray]:
    draw, clips, _ = BOSSES[bid]
    poses, _, _ = clips[clip]
    return [draw(p) for p in poses]


def preview_boss(bid: str, scale: int = 5) -> str:
    _, clips, _ = BOSSES[bid]
    rows = [boss_frames(bid, c) for c in clips]
    path = os.path.join(ITER_DIR, f"boss_{bid}.png")
    _sheet(rows, path, scale)
    return path


# ======================================================================================
# 16x16 boss icons (hand-placed; the in-game heads are too wide to crop cleanly)
# ======================================================================================
ICON_BARKHELM = """
................
.0..............
98..lm....lm....
87..lkj..lkj....
87.jkllllllkj...
.8jklmmlllllkj..
..jkllllllllkkj.
.ijkk%Fy%%%kkkkj
.ijkkkkkkkklmmlj
.ijkkkkk%k%kllkj
..ijkkkkkkkkkkj.
..234444444432..
.23455555554432.
.12233333333221.
..111222222111..
................
"""
ICON_CARRION = """
................
......3.4.3.....
.....2434343....
....PQRSSTSS....
...PQRRSSSSSR...
..PQRSAAAAAASR..
..PQRSAB9BAAAR..
.PQRSAB90BAAGHI.
.PQQRSAABBAGHIIJ
.PQQRSAAAAGHHIIJ
..PQRRSAAAGGH.JI
..PPQQRRSAAG...H
...PPQQRRR......
....3444443.....
.....33333......
................
"""
ICON_KING = """
.....5..0..5....
.....4.404.4....
....343454343...
...2349934994...
...ACDEEEEDDC...
..NACDEEDDDDDC..
.NNCD%%%DDDDDDC.
.NCD%5x9DDDDDEDK
.ACCDDDDDDDDDDKK
.ACCCDDDDCCCCC%.
..ACCDDC%%%%%%..
..ACCCC45CC45...
...ABCCBBCCB....
....ABCB.BC.....
.....AB.........
................
"""


def boss_icons() -> Dict[str, np.ndarray]:
    out = {}
    for bid, src, lg in (("sir_barkhelm", ICON_BARKHELM, BK_LEG), ("mother_carrion", ICON_CARRION, MC_LEG),
                         ("king_goldenfang", ICON_KING, KG_LEG)):
        img = art(src, lg)
        img = E.outline(img, OUTLINE)
        out[bid] = img
    # small glows so the eyes read at icon size
    soft_glow(out["sir_barkhelm"], 7.5, 7.5, 2.5, PAL["fire2"], 0.5)
    soft_glow(out["mother_carrion"], 8.5, 7.5, 2.5, PAL["red3"], 0.5)
    return out


PORTRAITS = {
    "sir_barkhelm": barkhelm_portrait,
    "mother_carrion": carrion_portrait,
    "king_goldenfang": king_portrait,
}


def build(reg: E.Registry) -> None:
    reg.atlas("bosses", flash=True)
    for bid, (draw, clips, piv) in BOSSES.items():
        for clip, (poses, fps, loop) in clips.items():
            frames = [draw(p) for p in poses]
            reg.anim("bosses", f"boss/{bid}/{clip}", frames, fps, loop, pivot=(0.5, piv))
    for bid, fn in PORTRAITS.items():
        reg.sprite("portraits", f"portrait/{bid}", fn(), pivot=(0.5, 0.5))
    for bid, img in boss_icons().items():
        reg.sprite("icons", f"icon/enemy/{bid}", img, pivot=(0.5, 0.5))


if __name__ == "__main__":
    want = sys.argv[1:]
    if "icons" in want:
        path = os.path.join(ITER_DIR, "boss_icons.png")
        _sheet([list(boss_icons().values()) + list(GE.enemy_icons().values())], path, 8)
        print(path)
    if "portraits" in want:
        path = os.path.join(ITER_DIR, "boss_portraits.png")
        _sheet([[fn() for fn in PORTRAITS.values()]], path, 6)
        print(path)
    for bid in BOSSES:
        if not want or bid in want:
            print(preview_boss(bid))
