"""
gen_icons.py - EVIL CATS interface icons -> atlas "icons" (docs/ASSET_SPEC.md section 3.9)

  * icon/<name>            16x16 UI icons
  * icon/perk/<perk_id>    24x24 perk icons: family-coloured frame + symbol

(Enemy and module icons in the same atlas are drawn by gen_enemies / gen_stations.)

How an icon is made: a 14x14 *char grid* is filled either from hand-written ASCII or by
small primitives (circle, ring, polygon, thick line). Upper-case letters are material
regions that get automatic, consistent shading (light from the top-left: pixels on a
region's top/left rim get the next lighter ramp step, bottom/right rim the next darker
one). Lower-case letters and digits are explicit colours (glints, pupils, details).
The grid is padded to 16x16 and given a 1px PAL['outline'] outline. This keeps all
icons bold, flat-lit the same way and readable at 32-40 dp.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

import eclib as E
from eclib import PAL, RAMPS, FAMILY_COLORS

ATLAS = "icons"
O = PAL["outline"]
Color = Tuple[int, int, int, int]

# --------------------------------------------------------------------------------------
# materials: region letter -> (ramp, base index)
# --------------------------------------------------------------------------------------
REGIONS: Dict[str, Tuple[str, int]] = {
    "S": ("silver", 2),   # neutral UI metal / glyphs
    "G": ("gold", 2),     # gold, rewards
    "H": ("gold", 3),     # bright yellow-gold (warning, sparkles)
    "R": ("red", 2),
    "X": ("red", 1),      # dark red
    "C": ("cyan", 2),
    "E": ("cyan", 3),     # bright cyan
    "V": ("violet", 3),
    "Z": ("violet", 2),
    "F": ("fire", 2),
    "I": ("frost", 2),
    "U": ("frost", 1),    # deeper ice blue
    "B": ("bone", 2),
    "Q": ("bone", 3),     # parchment / light bone
    "T": ("ward", 2),
    "P": ("grav", 2),
    "D": ("grav", 1),     # dark purple
    "N": ("iron", 3),
    "W": ("wood", 2),
    "K": ("fur", 2),
    "M": ("stone", 3),
    "J": ("stone", 2),    # dark grey (empty star)
    "A": ("snow", 2),     # white-ish
    "O": ("orange", 2),
    "L": ("leather", 2),
}

# explicit colours (never shaded)
EXPLICIT: Dict[str, Color] = {
    "o": PAL["outline"], "x": PAL["outline_soft"], "k": PAL["black"], "w": PAL["white"],
    "s": PAL["silver3"], "1": PAL["silver1"], "0": PAL["silver0"],
    "g": PAL["gold4"], "y": PAL["gold3"], "c": PAL["cyan4"], "b": PAL["cyan3"],
    "r": PAL["red4"], "e": PAL["red3"], "f": PAL["fire4"], "h": PAL["fire3"],
    "i": PAL["frost4"], "j": PAL["frost3"], "t": PAL["ward4"], "u": PAL["ward3"],
    "p": PAL["grav4"], "q": PAL["grav3"], "v": PAL["violet4"], "n": PAL["violet0"],
    "d": PAL["fur0"], "m": PAL["bone4"], "z": PAL["bone0"], "a": PAL["snow3"],
    "2": PAL["gold1"], "3": PAL["gold0"],
}
DARK_EXPLICIT = set("oxkdnz")  # count as material boundaries for shading


# --------------------------------------------------------------------------------------
# char grid with drawing primitives
# --------------------------------------------------------------------------------------
class Grid:
    def __init__(self, w: int = 14, h: int = 14, rows: Optional[Sequence[str]] = None):
        if rows is not None:
            h = len(rows)
            w = max(len(r) for r in rows)
            for r in rows:
                if len(r) != w:
                    raise ValueError(f"ragged icon row {r!r} (len {len(r)} != {w})")
        self.w, self.h = w, h
        self.c = np.full((h, w), ".", dtype="<U1")
        if rows is not None:
            for y, r in enumerate(rows):
                for x, ch in enumerate(r):
                    self.c[y, x] = ch

    # all coordinates are continuous: pixel (x, y) covers [x, x+1)
    def _paint(self, mask: np.ndarray, ch: str) -> "Grid":
        self.c[mask] = ch
        return self

    def mgrid(self):
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        return xx + 0.5, yy + 0.5

    def circle(self, cx, cy, r, ch):
        X, Y = self.mgrid()
        return self._paint((X - cx) ** 2 + (Y - cy) ** 2 <= r * r, ch)

    def ellipse(self, cx, cy, rx, ry, ch):
        X, Y = self.mgrid()
        return self._paint(((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2 <= 1.0, ch)

    def ring(self, cx, cy, r0, r1, ch, a0=None, a1=None):
        """annulus r0 < d <= r1, optionally only angles a0..a1 (degrees, 0 = +x, ccw up)."""
        X, Y = self.mgrid()
        d = np.hypot(X - cx, Y - cy)
        m = (d > r0) & (d <= r1)
        if a0 is not None:
            ang = (np.degrees(np.arctan2(-(Y - cy), X - cx)) + 360) % 360
            if a0 <= a1:
                m &= (ang >= a0) & (ang <= a1)
            else:
                m &= (ang >= a0) | (ang <= a1)
        return self._paint(m, ch)

    def poly(self, pts, ch):
        img = E.new(self.w, self.h)
        E.polygon(img, pts, (255, 255, 255, 255))
        return self._paint(img[:, :, 3] > 0, ch)

    def thick(self, x0, y0, x1, y1, r, ch):
        """capsule of radius r around segment (x0,y0)-(x1,y1)."""
        X, Y = self.mgrid()
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy or 1e-9
        t = np.clip(((X - x0) * dx + (Y - y0) * dy) / L2, 0, 1)
        d = np.hypot(X - (x0 + t * dx), Y - (y0 + t * dy))
        return self._paint(d <= r, ch)

    def rect(self, x, y, w, h, ch):
        self.c[max(0, y):max(0, y + h), max(0, x):max(0, x + w)] = ch
        return self

    def px(self, x, y, ch):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.c[y, x] = ch
        return self

    def stamp(self, rows: Sequence[str], x0: int = 0, y0: int = 0):
        for j, r in enumerate(rows):
            for i, ch in enumerate(r):
                if ch != "." and 0 <= y0 + j < self.h and 0 <= x0 + i < self.w:
                    self.c[y0 + j, x0 + i] = "." if ch == "_" else ch
        return self

    def flipped_x(self) -> "Grid":
        g = Grid(self.w, self.h)
        g.c = self.c[:, ::-1].copy()
        return g

    def rows(self) -> List[str]:
        return ["".join(r) for r in self.c]


# --------------------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------------------
def shade_grid(g: Grid, regions: Optional[Dict[str, Tuple[str, int]]] = None,
               explicit: Optional[Dict[str, Color]] = None) -> np.ndarray:
    regions = {**REGIONS, **(regions or {})}
    explicit = {**EXPLICIT, **(explicit or {})}
    h, w = g.h, g.w
    img = E.new(w, h)
    C = g.c

    def same(y, x, ch):
        if not (0 <= y < h and 0 <= x < w):
            return False
        n = C[y, x]
        if n == ch:
            return True
        # light explicit paint on a region does not break its shading
        return n in explicit and n not in DARK_EXPLICIT and n != "."

    for y in range(h):
        for x in range(w):
            ch = C[y, x]
            if ch == ".":
                continue
            if ch in explicit and ch not in regions:
                img[y, x] = explicit[ch]
                continue
            if ch not in regions:
                raise KeyError(f"icon char {ch!r} has no colour")
            ramp_name, base = regions[ch]
            ramp = RAMPS[ramp_name]
            tl = not same(y - 1, x, ch) or not same(y, x - 1, ch)
            br = not same(y + 1, x, ch) or not same(y, x + 1, ch)
            idx = base + (1 if tl and not br else (-1 if br and not tl else 0))
            img[y, x] = ramp[max(0, min(len(ramp) - 1, idx))]
    return img


def render(g: Grid, pad: int = 1, outline: bool = True, **kw) -> np.ndarray:
    body = shade_grid(g, kw.get("regions"), kw.get("explicit"))
    img = E.new(g.w + 2 * pad, g.h + 2 * pad)
    E.paste(img, body, pad, pad)
    if outline:
        img = E.outline(img, O)
    return img


def icon_from_rows(rows: Sequence[str], **kw) -> np.ndarray:
    return render(Grid(rows=rows), **kw)


# --------------------------------------------------------------------------------------
# UI icons (14x14 fill grids -> 16x16)
# --------------------------------------------------------------------------------------
ICONS: Dict[str, Callable[[], Grid]] = {}


def icon(name: str):
    def deco(fn):
        ICONS[name] = fn
        return fn
    return deco


def R(rows: Sequence[str]) -> Grid:
    return Grid(rows=rows)


@icon("pause")
def _pause():
    return R(["..............",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              "..SSSS..SSSS..",
              ".............."])


@icon("play")
def _play():
    return R(["..............",
              "...S..........",
              "...SSS........",
              "...SSSSS......",
              "...SSSSSSS....",
              "...SSSSSSSSS..",
              "...SSSSSSSSSSS",
              "...SSSSSSSSSSS",
              "...SSSSSSSSS..",
              "...SSSSSSS....",
              "...SSSSS......",
              "...SSS........",
              "...S..........",
              ".............."])


@icon("speed1")
def _speed1():
    return R(["..............",
              "......S.......",
              "......SS......",
              "......SSS.....",
              "..SS..SSSS....",
              "......SSSSS...",
              "SSSS..SSSSSS..",
              "SSSS..SSSSSS..",
              "......SSSSS...",
              "..SS..SSSS....",
              "......SSS.....",
              "......SS......",
              "......S.......",
              ".............."])


@icon("speed2")
def _speed2():
    return R(["..............",
              ".S......S.....",
              ".SS.....SS....",
              ".SSS....SSS...",
              ".SSSS...SSSS..",
              ".SSSSS..SSSSS.",
              ".SSSSSS.SSSSSS",
              ".SSSSSS.SSSSSS",
              ".SSSSS..SSSSS.",
              ".SSSS...SSSS..",
              ".SSS....SSS...",
              ".SS.....SS....",
              ".S......S.....",
              ".............."])


@icon("settings")
def _settings():
    return R([".....SSSS.....",
              ".SS..SSSS..SS.",
              ".SSSSSSSSSSSS.",
              "..SSSSSSSSSS..",
              "..SSSSSSSSSS..",
              "SSSSSS..SSSSSS",
              "SSSSS....SSSSS",
              "SSSSS....SSSSS",
              "SSSSSS..SSSSSS",
              "..SSSSSSSSSS..",
              "..SSSSSSSSSS..",
              ".SSSSSSSSSSSS.",
              ".SS..SSSS..SS.",
              ".....SSSS....."])


@icon("home")
def _home():
    return R(["......SS......",
              ".....SSSS.....",
              "....SSSSSS....",
              "...SSSSSSSS...",
              "..SSSSSSSSSS..",
              ".SSSSSSSSSSSS.",
              "..oooooooooo..",
              "..SSSSSSSSSS..",
              "..SSSSSSSSSS..",
              "..SSSSooSSSS..",
              "..SSSSooSSSS..",
              "..SSSSooSSSS..",
              "..SSSSooSSSS..",
              ".............."])


@icon("back")
def _back():
    return R(["..............",
              "..............",
              "....S.........",
              "...SS.........",
              "..SSSSSSSSS...",
              ".SSSSSSSSSSS..",
              "..SSSSSSSSSSS.",
              "...SS.....SSS.",
              "....S......SS.",
              "...........SS.",
              "..........SSS.",
              "...SSSSSSSSSS.",
              "...SSSSSSSSS..",
              ".............."])


@icon("close")
def _close():
    return R(["..............",
              ".SS........SS.",
              ".SSS......SSS.",
              "..SSS....SSS..",
              "...SSS..SSS...",
              "....SSSSSS....",
              ".....SSSS.....",
              ".....SSSS.....",
              "....SSSSSS....",
              "...SSS..SSS...",
              "..SSS....SSS..",
              ".SSS......SSS.",
              ".SS........SS.",
              ".............."])


def lock_grid() -> Grid:
    return R(["..............",
              "....NNNNNN....",
              "...NNNNNNNN...",
              "...NN....NN...",
              "...NN....NN...",
              "...NN....NN...",
              "..SSSSSSSSSS..",
              "..SSSSSSSSSS..",
              "..SSSSooSSSS..",
              "..SSSSooSSSS..",
              "..SSSSSoSSSS..",
              "..SSSSSSSSSS..",
              "..SSSSSSSSSS..",
              ".............."])


@icon("lock")
def _lock():
    return lock_grid()


def lock_overlay() -> np.ndarray:
    """ui/lock: the padlock icon (drawn here so both atlases share one design)."""
    return render(lock_grid())


@icon("check")
def _check():
    return R(["..............",
              "..............",
              "...........TT.",
              "..........TTT.",
              ".........TTT..",
              "........TTT...",
              ".TT....TTT....",
              ".TTT..TTT.....",
              "..TTTTTT......",
              "...TTTT.......",
              "....TT........",
              "..............",
              "..............",
              ".............."])


def star_points(cx, cy, R, r, n=5, rot=-90.0):
    pts = []
    for i in range(2 * n):
        a = math.radians(rot + i * 180.0 / n)
        rr = R if i % 2 == 0 else r
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def star_grid(ch: str) -> Grid:
    return Grid().poly(star_points(7.0, 7.9, 7.6, 3.3), ch)


@icon("star")
def _star():
    g = star_grid("G")
    g.px(6, 2, "g").px(4, 5, "g")
    return g


@icon("star_empty")
def _star_empty():
    return star_grid("M")


@icon("plus")
def _plus():
    return R(["..............",
              ".....SSSS.....",
              ".....SSSS.....",
              ".....SSSS.....",
              ".....SSSS.....",
              ".SSSSSSSSSSSS.",
              ".SSSSSSSSSSSS.",
              ".SSSSSSSSSSSS.",
              ".SSSSSSSSSSSS.",
              ".....SSSS.....",
              ".....SSSS.....",
              ".....SSSS.....",
              ".....SSSS.....",
              ".............."])


@icon("minus")
def _minus():
    g = Grid()
    return g.rect(1, 5, 12, 4, "S")


def _arrow_left_grid() -> Grid:
    return R(["..............",
              "......S.......",
              ".....SS.......",
              "....SSS.......",
              "...SSSS.......",
              "..SSSSSSSSSSS.",
              ".SSSSSSSSSSSS.",
              ".SSSSSSSSSSSS.",
              "..SSSSSSSSSSS.",
              "...SSSS.......",
              "....SSS.......",
              ".....SS.......",
              "......S.......",
              ".............."])


@icon("arrow_left")
def _arrow_left():
    return _arrow_left_grid()


@icon("arrow_right")
def _arrow_right():
    return _arrow_left_grid().flipped_x()


@icon("up_arrow")
def _up_arrow():
    return R(["..............",
              "......TT......",
              ".....TTTT.....",
              "....TTTTTT....",
              "...TTTTTTTT...",
              "..TTTTTTTTTT..",
              ".TTTTTTTTTTTT.",
              ".....TTTT.....",
              ".....TTTT.....",
              ".....TTTT.....",
              ".....TTTT.....",
              ".....TTTT.....",
              ".....TTTT.....",
              ".............."])


@icon("info")
def _info():
    g = Grid().circle(7, 7, 7.0, "U")
    g.rect(6, 2, 2, 2, "w").rect(5, 5, 3, 1, "w").rect(6, 6, 2, 4, "w").rect(5, 10, 4, 1, "w")
    return g


@icon("warning")
def _warning():
    return R(["......HH......",
              "......HH......",
              ".....HHHH.....",
              ".....HooH.....",
              "....HHooHH....",
              "....HHooHH....",
              "...HHHooHHH...",
              "...HHHooHHH...",
              "..HHHHHHHHHH..",
              "..HHHHooHHHH..",
              ".HHHHHooHHHHH.",
              ".HHHHHHHHHHHH.",
              "HHHHHHHHHHHHHH",
              ".............."])


@icon("refresh")
def _refresh():
    g = Grid()
    g.ring(7, 7.4, 3.3, 5.6, "S", 105, 35)      # arc with a gap at the upper right
    g.poly([(7.0, 0.2), (7.0, 6.4), (11.6, 3.3)], "S")  # clockwise arrow head
    return g


@icon("swap")
def _swap():
    return R(["........S.....",
              "........SS....",
              ".SSSSSSSSSS...",
              ".SSSSSSSSSSS..",
              ".SSSSSSSSSS...",
              "........SS....",
              "........S.....",
              ".....S........",
              "....SS........",
              "...SSSSSSSSSS.",
              "..SSSSSSSSSSS.",
              "...SSSSSSSSSS.",
              "....SS........",
              ".....S........"])


@icon("shield")
def _shield():
    return R([".SSSSSSSSSSSS.",
              ".SVVVVVVVVVVS.",
              ".SVVVVVVVVVVS.",
              ".SVVVVVVVVVVS.",
              ".SVVVVVVVVVVS.",
              ".SVVVVVVVVVVS.",
              ".SVVVVVVVVVVS.",
              ".SSVVVVVVVVSS.",
              "..SVVVVVVVVS..",
              "..SSVVVVVVSS..",
              "...SSVVVVSS...",
              "....SSVVSS....",
              ".....SSSS.....",
              "......SS......"]).stamp(["v", ".v", "..v"], 3, 2)


HEART_ROWS = ["..............",
              "..###....###..",
              ".#####..#####.",
              "##############",
              "##############",
              "##############",
              "##############",
              ".############.",
              "..##########..",
              "...########...",
              "....######....",
              ".....####.....",
              "......##......",
              ".............."]


@icon("heart")
def _heart():
    g = R([r.replace("#", "R") for r in HEART_ROWS])
    return g.px(2, 3, "w").px(3, 2, "r").px(2, 4, "r")


@icon("heart_plus")
def _heart_plus():
    g = R(["..............",
           ".RRR...RRR....",
           "RRRRR.RRRRR...",
           "RRRRRRRRRRR...",
           "RRRRRRRRRRR...",
           "RRRRRRRRRRR...",
           ".RRRRRRRRR....",
           "..RRRRRRR.TT..",
           "...RRRRR..TT..",
           "....RRR.TTTTTT",
           ".....R..TTTTTT",
           "..........TT..",
           "..........TT..",
           ".............."])
    return g.px(1, 2, "w").px(2, 1, "r")


@icon("regen")
def _regen():
    # heart with a heartbeat line running through it: steady life, not a one-off "+"
    g = R([r.replace("#", "R") for r in HEART_ROWS])
    g.stamp(["......a.......",
             ".....a.a......",
             "aaaaa...a.aaaa",
             ".........a...."], 0, 4)
    return g.px(2, 3, "r")


@icon("bolt")
def _bolt():
    return R([".......CCCCCC.",
              "......CCCCCC..",
              ".....CCCCCC...",
              "....CCCCCC....",
              "...CCCCCC.....",
              "..CCCCCCCCCCC.",
              "..CCCCCCCCCC..",
              "........CCC...",
              ".......CCC....",
              "......CCC.....",
              ".....CC.......",
              "....CC........",
              "...CC.........",
              "..C..........."]).stamp(["c", "c", "c", "c"], 7, 0).stamp(["...c", "..c", ".c", "c"], 3, 1)


@icon("flame")
def _flame():
    return R([".......F......",
              "......FF......",
              "......FFF.....",
              ".....FFFF.....",
              "....FFFFFF..F.",
              "...FFFFFFF.FF.",
              "...FFFFFFFFFF.",
              "..FFFFhFFFFFF.",
              "..FFFhhhFFFFF.",
              ".FFFFhhhhFFFF.",
              ".FFFhhffhhFFF.",
              ".FFFhffffhFF..",
              "..FFhffffhF...",
              "...FFFFFFFF..."])


@icon("snowflake")
def _snowflake():
    return R(["......II......",
              "....I.II.I....",
              ".....IIII.....",
              ".I....II....I.",
              "..II..II..II..",
              "...IIIIIIII...",
              "IIIIIIiiIIIIII",
              "IIIIIIiiIIIIII",
              "...IIIIIIII...",
              "..II..II..II..",
              ".I....II....I.",
              ".....IIII.....",
              "....I.II.I....",
              "......II......"])


@icon("bone")
def _bone():
    g = Grid()
    g.thick(3.6, 10.4, 10.4, 3.6, 1.35, "B")
    for cx, cy in ((11.6, 4.5), (9.5, 2.4), (4.5, 11.6), (2.4, 9.5)):
        g.circle(cx, cy, 1.9, "B")
    return g


@icon("lantern")
def _lantern():
    return R(["......NN......",
              ".....N..N.....",
              "....NNNNNN....",
              "...NNNNNNNN...",
              "...NuuuuuuN...",
              "...NuttttuN...",
              "...NutwwtuN...",
              "...NutwwtuN...",
              "...NuttttuN...",
              "...NuuuuuuN...",
              "...NNNNNNNN...",
              "....NNNNNN....",
              ".....NNNN.....",
              ".............."])


@icon("gravity")
def _gravity():
    # two-armed vortex around a dark singularity
    g = Grid()
    X, Y = g.mgrid()
    r = np.hypot(X - 7, Y - 7)
    th = np.arctan2(Y - 7, X - 7)
    for arm in (0.0, math.pi):
        ph = (th - arm - 0.62 * r) % (2 * math.pi)
        g.c[(r > 1.8) & (r < 7.0) & (ph < 1.45)] = "P"
    g.circle(7, 7, 2.4, "D")
    return g.rect(6, 6, 2, 2, "k")


@icon("sword")
def _sword():
    return R([".............S",
              "............SS",
              "...........SSS",
              "..........SSS.",
              ".........SSS..",
              "........SSS...",
              ".......SSS....",
              "......SSS.....",
              "..G..SSS......",
              "...GSSS.......",
              "....GG........",
              "...WWGG.......",
              "..WWW..G......",
              ".GWW.........."]).stamp(["s", ".s", "..s", "...s"], 9, 2)


@icon("haste")
def _haste():
    # swept wing: a bright leading edge over three long primary feathers
    return R(["..............",
              "...........AA.",
              ".........AAAA.",
              ".......AAAAAA.",
              ".....AAAAAAAA.",
              "...AAAAAAAAA..",
              ".AAAAAAAAAAA..",
              "..ooooAAAAAA..",
              ".AAAAAAoAAAA..",
              "..ooooAAoAAA..",
              "...AAAAAAoA...",
              "....oooAAAo...",
              ".....AAAAA....",
              ".............."]).stamp([".......aa", ".....aaa", "...aaa", ".aa"], 3, 2)


@icon("crit")
def _crit():
    # three claw slashes, white-hot cores with red edges
    g = Grid()
    for c, y0, y1 in ((5, 0, 5), (10, 0, 10), (15, 3, 13)):
        for y in range(y0, y1 + 1):
            for x in range(14):
                d = x + y - c
                if d in (0, 1, 2):
                    tip = y in (y0, y1)
                    g.px(x, y, "R" if (d != 1 or tip) else "w")
    return g


@icon("magnet")
def _magnet():
    return R(["..............",
              "..............",
              ".SSS......SSS.",
              ".SSS......SSS.",
              ".RRR......RRR.",
              ".RRR......RRR.",
              ".RRR......RRR.",
              ".RRR......RRR.",
              ".RRRR....RRRR.",
              "..RRRR..RRRR..",
              "..RRRRRRRRRR..",
              "...RRRRRRRR...",
              ".....RRRR.....",
              ".............."]).stamp(["b...b", ".b.b."], 5, 0)


BOLT_GLYPH = ["...cb",
              "..cb.",
              ".cb..",
              "cbbbb",
              "..bb.",
              ".bb..",
              ".b...",
              "b...."]


@icon("spark")
def _spark():
    g = Grid().circle(7, 7, 6.6, "G")
    g.ring(7, 7, 4.6, 5.4, "2")
    g.stamp(BOLT_GLYPH, 5, 3)
    # dark drop shadow on the lower right of the glyph so cyan reads on gold
    glyph = np.isin(g.c, ["c", "b"])
    sh = np.zeros_like(glyph)
    sh[1:, :] |= glyph[:-1, :]
    sh[:, 1:] |= glyph[:, :-1]
    g.c[sh & ~glyph] = "3"
    return g


@icon("moon_gold")
def _moon_gold():
    g = Grid()
    X, Y = g.mgrid()
    outer = (X - 6.6) ** 2 + (Y - 7.2) ** 2 <= 6.5 ** 2
    bite = (X - 9.6) ** 2 + (Y - 4.6) ** 2 <= 5.0 ** 2
    g.c[outer & ~bite] = "G"
    g.stamp([".g.", "gyg", ".g."], 10, 7)
    return g.px(2, 5, "g").px(3, 3, "g")


@icon("storm_shard")
def _storm_shard():
    g = Grid()
    g.poly([(7.0, 0.0), (7.0, 14.0), (3.6, 10.2), (2.6, 4.6)], "V")
    g.poly([(7.0, 0.0), (11.4, 4.6), (10.4, 10.2), (7.0, 14.0)], "C")
    return g.stamp(["c", "c", ".c"], 5, 3).px(8, 2, "c")


@icon("xp")
def _xp():
    g = Grid().circle(7, 7, 6.2, "Z")
    g.circle(6.4, 6.4, 3.4, "E")
    g.stamp(["..c..", "..c..", "ccwcc", "..c..", "..c.."], 4, 4)
    return g


@icon("trophy")
def _trophy():
    return R(["..............",
              "..GGGGGGGGGG..",
              "GGGGGGGGGGGGGG",
              "G.GGGGGGGGGG.G",
              "G.GGGGGGGGGG.G",
              "GG.GGGGGGGG.GG",
              "..GGGGGGGGGG..",
              "...GGGGGGGG...",
              "....GGGGGG....",
              "......GG......",
              "......GG......",
              "....GGGGGG....",
              "...GGGGGGGG...",
              ".............."]).stamp(["g", "g", "g"], 4, 2).stamp(["2222"], 5, 10)


@icon("calendar")
def _calendar():
    return R(["...S......S...",
              ".RRSRRRRRRSRR.",
              ".RRRRRRRRRRRR.",
              ".AAAAAAAAAAAA.",
              ".AxAAxAAxAAxA.",
              ".AAAAAAAAAAAA.",
              ".AxAAxAAxAAxA.",
              ".AAAAAAAAAAAA.",
              ".AxAAGGAxAAxA.",
              ".AAAAGGAAAAAA.",
              ".AxAAxAAxAAAA.",
              ".AAAAAAAAAAAA.",
              "..............",
              ".............."])


@icon("shop")
def _shop():
    return R(["..............",
              "..............",
              ".VVAAVVAAVVAA.",
              "VVVAAVVAAVVAAA",
              "VVVAAVVAAVVAAA",
              ".V..A..V..A...",
              ".MMMMMMMMMMMM.",
              ".MMMMMMMMMMMM.",
              ".MxxxMMMMxxMM.",
              ".MxIxMMMMxxMM.",
              ".MxxxMMMMxxMM.",
              ".MMMMMMMMxxMM.",
              "WWWWWWWWWWWWWW",
              ".............."])


@icon("profile")
def _profile():
    return R(["..............",
              "...S......S...",
              "...SS....SS...",
              "...SSSSSSSS...",
              "...SSSSSSSS...",
              "...SxSSSSxS...",
              "...SSSSSSSS...",
              "....SSSSSS....",
              ".....SSSS.....",
              "..SSSSSSSSSS..",
              ".SSSSSSSSSSSS.",
              ".SSSSSSSSSSSS.",
              ".SSSSSSSSSSSS.",
              ".............."])


@icon("scroll")
def _scroll():
    return R(["..............",
              ".BBBBBBBBBBBB.",
              ".BBBBBBBBBBBB.",
              "..QQQQQQQQQQ..",
              "..QzzzzzzzQQ..",
              "..QQQQQQQQQQ..",
              "..QzzzzzzQQQ..",
              "..QQQQQQQQQQ..",
              "..QzzzzzzzQQ..",
              "..QQQQQQQQQQ..",
              ".BBBBBBBBBBBB.",
              ".BBBBBBBBBBBB.",
              "..............",
              ".............."])


@icon("music")
def _music():
    return R(["..............",
              "......SSSSSSS.",
              "......SSSSSSS.",
              "......S.....S.",
              "......S.....S.",
              "......S.....S.",
              "......S.....S.",
              "......S.....S.",
              "...SSSS..SSSS.",
              "..SSSSS.SSSSS.",
              "..SSSSS.SSSSS.",
              "...SSS...SSS..",
              "..............",
              ".............."])


@icon("sfx")
def _sfx():
    return R(["..............",
              ".....S........",
              "....SS...S....",
              "...SSS....S...",
              "SSSSSS..S..S..",
              "SSSSSS...S.S..",
              "SSSSSS...S..S.",
              "SSSSSS...S..S.",
              "SSSSSS...S.S..",
              "SSSSSS..S..S..",
              "...SSS....S...",
              "....SS...S....",
              ".....S........",
              ".............."])


@icon("vibration")
def _vibration():
    return R(["..............",
              "....SSSSSS....",
              "....SxxxxS....",
              ".S..SxxxxS..S.",
              "S...SxxxxS...S",
              ".S..SxxxxS..S.",
              "S...SxxxxS...S",
              ".S..SxxxxS..S.",
              "S...SxxxxS...S",
              "....SxxxxS....",
              "....SSSSSS....",
              "....SSxxSS....",
              "....SSSSSS....",
              ".............."])


@icon("skull")
def _skull():
    return R(["..............",
              "....BBBBBB....",
              "..BBBBBBBBBB..",
              ".BBBBBBBBBBBB.",
              ".BBBBBBBBBBBB.",
              ".BBooBBBBooBB.",
              ".BBoooBBoooBB.",
              ".BBoooBBoooBB.",
              "..BBBBooBBBB..",
              "...BBBBBBBB...",
              "...BoBoBoBB...",
              "....BBBBBB....",
              "..............",
              ".............."]).px(3, 2, "m").px(2, 3, "m")


@icon("crown")
def _crown():
    return R(["..............",
              "..............",
              ".G....GG....G.",
              ".GG..GGGG..GG.",
              ".GGG.GGGG.GGG.",
              ".GGGGGGGGGGGG.",
              ".GGGGGGGGGGGG.",
              ".GGGGGGGGGGGG.",
              ".GGbGGGGGGeGG.",
              ".GGGGGvvGGGGG.",
              ".GGGGGGGGGGGG.",
              ".GGGGGGGGGGGG.",
              "..............",
              ".............."]).px(1, 2, "g").px(6, 2, "g").px(12, 2, "g")


@icon("map")
def _map():
    return R(["..............",
              "BBBB....BBBB..",
              "BBBBQQQQBBBBQQ",
              "BBBBQQQQBBBBQQ",
              "BzBBQQQzBBBBQQ",
              "BBzBQQzQBBBBQQ",
              "BBBzQzQQBBeBQe",
              "BBBBzQQQBBBeeQ",
              "BBBBQQQQBBBeeQ",
              "BBBBQQQQBBeBQe",
              "BBBBQQQQBBBBQQ",
              "BBBBQQQQBBBBQQ",
              "....QQQQ....QQ",
              ".............."])


@icon("target_nearest")
def _target_nearest():
    # concentric rings with a bullseye: "closest to the centre first"
    g = Grid()
    g.ring(7, 7, 5.2, 7.0, "R")
    g.ring(7, 7, 3.4, 5.2, "A")
    g.circle(7, 7, 3.4, "R")
    g.circle(7, 7, 1.6, "A")
    return g


@icon("target_strongest")
def _target_strongest():
    # flexed arm: "the toughest enemy first"
    return R(["..............",
              ".........SSS..",
              "........SSSSS.",
              "........SSSSS.",
              ".........SSSS.",
              "..........SSS.",
              "....SSS...SSS.",
              "..SSSSSS.oSSS.",
              ".SSSSSSSSSSSS.",
              ".SSSSSSSSSSSS.",
              ".SSSSSSSSSSS..",
              "..SSSSSSSSS...",
              "....SSSSS.....",
              ".............."]).stamp(["ss", "s"], 4, 7)


@icon("target_ranged")
def _target_ranged():
    # bow and arrow: "ranged attackers first"
    return R(["...WWW........",
              ".....WW.......",
              "......WW......",
              ".......W....SS",
              "..o.....W..SSS",
              "...o....W.SSS.",
              "....o...WSSS..",
              ".....o..SSS...",
              "......oSSSW...",
              "......SSo.W...",
              "..R..SS..oW...",
              "..RRSS....W...",
              "...RR....WW...",
              "..R.R..WWW...."])


@icon("gift")
def _gift():
    return R(["..GG....GG....",
              ".G..G..G..G...",
              ".G...GG...G...",
              "..GGGGGGGGG...",
              "RRRRRGGGRRRRR.",
              "RRRRRGGGRRRRR.",
              "..............",
              ".ZZZZGGGZZZZ..",
              ".ZZZZGGGZZZZ..",
              ".ZZZZGGGZZZZ..",
              ".ZZZZGGGZZZZ..",
              ".ZZZZGGGZZZZ..",
              ".ZZZZGGGZZZZ..",
              ".............."])


@icon("clock")
def _clock():
    g = Grid()
    g.circle(7, 7, 7.0, "S")
    g.circle(7, 7, 5.6, "A")
    g.rect(6, 3, 2, 5, "d").rect(6, 6, 4, 2, "d")
    return g.px(7, 1, "0").px(12, 7, "0").px(7, 12, "0").px(1, 7, "0")


@icon("flag")
def _flag():
    return R([".g............",
              ".SRRRRR.......",
              ".SRRRRRRR.RRR.",
              ".SRRRRRRRRRRR.",
              ".SRRRRRRRRRRR.",
              ".SRRRRRRRRRR..",
              ".S..RRRRRRRRR.",
              ".S.......RRR..",
              ".S............",
              ".S............",
              ".S............",
              ".S............",
              ".S............",
              "SSS..........."])


@icon("boss")
def _boss():
    return R(["X............X",
              "XX..........XX",
              ".XX........XX.",
              ".XXXBBBBBBXXX.",
              "..BBBBBBBBBB..",
              ".BBBBBBBBBBBB.",
              ".BBooBBBBooBB.",
              ".BBoeoBBoeoBB.",
              ".BBoooBBoooBB.",
              "..BBBBooBBBB..",
              "...BBBBBBBB...",
              "...BoBoBoBB...",
              "....BBBBBB....",
              ".............."])


@icon("chain")
def _chain():
    # two links; the left one passes over the right one at the bottom
    g = Grid()
    link = [".XXXXXX.",
            "XXXXXXXX",
            "XX....XX",
            "XX....XX",
            "XXXXXXXX",
            ".XXXXXX."]
    g.stamp([r.replace("X", "S") for r in link], 0, 4)
    g.stamp([r.replace("X", "N") for r in link], 6, 4)
    return g.stamp(["SS", "SS"], 6, 8)


@icon("flash_off")
def _flash_off():
    g = R(["........SSSS..",
           ".......SSSS...",
           "......SSSS....",
           ".....SSSS.....",
           "....SSSSSSSS..",
           "...SSSSSSSS...",
           ".......SSS....",
           "......SSS.....",
           ".....SSS......",
           "....SS........",
           "...SS.........",
           "..S...........",
           "..............",
           ".............."])
    return _slash(g)


def _slash(g: Grid) -> Grid:
    """red 'off' bar from the top-left to the bottom-right, cut out of the glyph below."""
    for i in range(14):
        for d in (-2, -1, 2):
            x = i + d
            if 0 <= x < 14 and d in (-2, 2):
                if g.c[i, x] != ".":
                    g.c[i, x] = "o"
        for d in (0, 1):
            if 0 <= i + d - 0 < 14:
                g.c[i, min(13, i + d)] = "R"
        if i + 1 < 14:
            g.c[i, i] = "R"
    return g


@icon("shake_off")
def _shake_off():
    g = R(["..............",
           "..............",
           ".S.SSSSSSSS.S.",
           "S..SAAAAAAS..S",
           ".S.SAAAAAAS.S.",
           "S..SAAAAAAS..S",
           ".S.SAAAAAAS.S.",
           "S..SAAAAAAS..S",
           ".S.SAAAAAAS.S.",
           "...SSSSSSSS...",
           "..............",
           "..............",
           "..............",
           ".............."])
    return _slash(g)


@icon("numbers")
def _numbers():
    return R(["..............",
              "...SS....SS...",
              "...SS....SS...",
              ".SSSSSSSSSSSS.",
              ".SSSSSSSSSSSS.",
              "...SS....SS...",
              "...SS....SS...",
              "...SS....SS...",
              ".SSSSSSSSSSSS.",
              ".SSSSSSSSSSSS.",
              "...SS....SS...",
              "...SS....SS...",
              "..............",
              ".............."])


@icon("globe")
def _globe():
    g = Grid().circle(7, 7, 7.0, "U")
    X, Y = g.mgrid()
    ell = ((X - 7) / 3.3) ** 2 + ((Y - 7) / 6.6) ** 2
    g.c[(ell <= 1) & (ell > 0.55) & (np.hypot(X - 7, Y - 7) <= 6.6)] = "j"
    return g.rect(1, 6, 12, 2, "j").rect(2, 3, 10, 1, "j").rect(2, 10, 10, 1, "j")


@icon("cloud")
def _cloud():
    g = Grid()
    g.circle(7.6, 5.6, 3.8, "A")
    g.circle(3.8, 7.8, 2.8, "A")
    g.circle(10.8, 7.6, 2.8, "A")
    g.rect(2, 7, 11, 4, "A")
    g.circle(2.9, 8.4, 2.5, "A")
    g.circle(11.3, 8.4, 2.5, "A")
    return g


@icon("ad")
def _ad():
    # megaphone: advertising
    return R(["..............",
              "..........SS..",
              "........RRSS..",
              "......RRRRSS..",
              "..SS.RRRRRSS..",
              ".SSSRRRRRRSS.b",
              ".SSSRRRRRRSS..",
              ".SSSRRRRRRSS.b",
              "..SS.RRRRRSS..",
              "...W..RRRRSS..",
              "...WW...RRSS..",
              "....W.....SS..",
              "..............",
              ".............."])


@icon("star_burst")
def _star_burst():
    g = Grid()
    g.poly(star_points(7.0, 7.0, 7.4, 3.4, n=8, rot=-90), "H")
    g.circle(7, 7, 2.3, "g")
    return g


@icon("play_ad")
def _play_ad():
    return R(["..............",
              ".SSSSSSSSSSSS.",
              ".SnnnnnnnnnnS.",
              ".SnnnGnnnnnnS.",
              ".SnnnGGnnnnnS.",
              ".SnnnGGGnnnnS.",
              ".SnnnGGGGnnnS.",
              ".SnnnGGGnnnnS.",
              ".SnnnGGnnnnnS.",
              ".SnnnGnnnnnnS.",
              ".SnnnnnnnnnnS.",
              ".SSSSSSSSSSSS.",
              "....SS..SS....",
              ".............."])


@icon("eye")
def _eye():
    return R(["..............",
              "..............",
              ".....AAAA.....",
              "...AAAAAAAA...",
              "..AAAACCAAAA..",
              ".AAAACCdCAAAA.",
              "AAAAACCdCCAAAA",
              "AAAAACCdCCAAAA",
              ".AAAACCdCAAAA.",
              "..AAAACCAAAA..",
              "...AAAAAAAA...",
              ".....AAAA.....",
              "..............",
              ".............."]).px(6, 4, "c")


def build_ui_icons() -> Dict[str, np.ndarray]:
    return {name: render(fn()) for name, fn in ICONS.items()}


# --------------------------------------------------------------------------------------
# Perk icons: 24x24 = family-coloured frame + 14x14 symbol (outlined to 16x16) at (4, 4)
# --------------------------------------------------------------------------------------
PERKS: Dict[str, Callable[[], Grid]] = {}
PERK_FAMILY_ORDER = ["arc", "ember", "frost", "bone", "ward", "gravity"]
PERK_IDS = {
    "arc": ["arc_forked_bolt", "arc_static_mark", "arc_thunderclap", "arc_conductive_chill", "arc_overcharged_crown"],
    "ember": ["ember_lingering_embers", "ember_cinder_spread", "ember_molten_shell", "ember_furnace_heart", "ember_wildfire_pact"],
    "frost": ["frost_deep_chill", "frost_brittle_armour", "frost_shatter", "frost_winter_ring", "frost_frozen_oath"],
    "bone": ["bone_barbed_bolts", "bone_double_nock", "bone_armour_break", "bone_executioner", "bone_heavy_quarrels"],
    "ward": ["ward_reinforced_barrier", "ward_mending_purr", "ward_last_thread", "ward_reflective_fur", "ward_guardian_pact"],
    "gravity": ["gravity_wider_orbit", "gravity_crushing_centre", "gravity_event_horizon", "gravity_falling_star", "gravity_unstable_singularity"],
}
EPIC = {ids[4] for ids in PERK_IDS.values()}   # the trade-off perk of each family


def perk(pid: str):
    def deco(fn):
        PERKS[pid] = fn
        return fn
    return deco


def _mixc(a: Color, b: Color, t: float) -> Color:
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)) + (255,)  # type: ignore


def perk_frame(family: str, epic: bool = False) -> np.ndarray:
    import gen_ui  # shared ring-profile frame builder
    ramp = RAMPS[FAMILY_COLORS[family]]
    n = len(ramp)
    hi, mid, lo, deep = ramp[min(3, n - 1)], ramp[2], ramp[1], ramp[0]
    bg_out = _mixc(deep, O, 0.55)
    bg_in = _mixc(deep, O, 0.25)
    if epic:
        rings = [O, (ramp[n - 1], hi, mid), (hi, mid, lo), O, (mid, lo, lo), O]
    else:
        rings = [O, (hi, mid, lo), (mid, mid, deep), O]
    img = gen_ui.frame(24, 24, rings, bg_out, insets=(2, 1))
    # soft stepped glow behind the symbol
    yy, xx = np.mgrid[0:24, 0:24]
    inner = (np.hypot(xx + 0.5 - 12, yy + 0.5 - 12) <= 7.2)
    body = np.all(img == np.array(bg_out, np.uint8), axis=-1)
    img[inner & body] = bg_in
    if epic:
        stud = E.outline(E.ascii_art(["...",
                                      ".H.",
                                      "HMH",
                                      ".L.",
                                      "..."], {"H": ramp[n - 1], "M": hi, "L": lo}), O)
        for (x, y) in ((0, 0), (19, 0), (0, 19), (19, 19)):
            E.paste(img, stud, x, y)
        crest = E.outline(E.ascii_art([".....",
                                       "..H..",
                                       ".HMH.",
                                       "....."], {"H": ramp[n - 1], "M": hi}), O)
        E.paste(img, crest, 9, -1)
    return img


def perk_icon(pid: str) -> np.ndarray:
    family = next(f for f, ids in PERK_IDS.items() if pid in ids)
    img = perk_frame(family, pid in EPIC)
    sym = render(PERKS[pid]())
    E.paste(img, sym, 4, 4)
    return img


# ---- ARC ------------------------------------------------------------------------------
@perk("arc_forked_bolt")
def _p_forked():
    # main bolt with a thinner branch splitting off to the right
    return R([".........EEEE.",
              "........EEEE..",
              ".......EEEE...",
              "......EEEE....",
              ".....EEEEEEEE.",
              "....EEEEEEEE..",
              ".......EEEE...",
              "......EEE.EE..",
              ".....EEE...EE.",
              "....EEE.....E.",
              "...EEE........",
              "..EEE.........",
              ".EE...........",
              ".E............"]).stamp(["...c", "..c", ".c", "c"], 5, 1)


@perk("arc_static_mark")
def _p_static():
    g = Grid().ring(7, 7, 4.3, 6.1, "C")
    g.rect(6, 0, 2, 4, "C").rect(6, 10, 2, 4, "C").rect(0, 6, 4, 2, "C").rect(10, 6, 4, 2, "C")
    g.rect(5, 5, 4, 4, ".")
    return g.stamp([".cc.", "cwwc", "cwwc", ".cc."], 5, 5)


@perk("arc_thunderclap")
def _p_thunderclap():
    g = Grid()
    g.poly(star_points(8.6, 8.8, 5.4, 2.3, n=8, rot=-90), "E")
    g.circle(8.6, 8.8, 2.2, "w")
    return g.stamp(["EEEE....",
                    ".EEEE...",
                    "..EEEEEE",
                    "....EEEE",
                    "......EE"], 0, 0).stamp(["cc", ".cc", "..c"], 0, 0)


@perk("arc_conductive_chill")
def _p_conductive():
    g = R(["....EEEE......",
           "...EEEE.......",
           "..EEEE........",
           ".EEEEEEE......",
           "...EEEE.......",
           "..EEE.........",
           ".EEE..........",
           ".EE...........",
           ".E............",
           "..............",
           "..............",
           "..............",
           "..............",
           ".............."]).stamp(["c", "c", "c"], 4, 0)
    return g.stamp(["....I....",
                    "..I.I.I..",
                    "...III...",
                    ".I.III.I.",
                    "IIIIiIIII",
                    ".I.III.I.",
                    "...III...",
                    "..I.I.I..",
                    "....I...."], 5, 5)


@perk("arc_overcharged_crown")
def _p_overcharged():
    return R([".E....E.....E.",
              "..E..E.E...E..",
              "...E.....E....",
              ".S....SS....S.",
              ".SS..SSSS..SS.",
              ".SSSSSSSSSSSS.",
              ".SSSSSbSSSSSS.",
              ".SSSSSSSSSSSS.",
              "..............",
              "......RR.RR...",
              ".....RRRoRRR..",
              "......RRoRR...",
              ".......RoR....",
              "........R....."])


# ---- EMBER ----------------------------------------------------------------------------
@perk("ember_lingering_embers")
def _p_lingering():
    return R([".WWWWWWWWWWWW.",
              "..IFFFFFFFFI..",
              "..IFhhhhhhFI..",
              "...IFhffhFI...",
              "....IFhhFI....",
              ".....IFFI.....",
              "......hh......",
              ".....I..I.....",
              "....I....I....",
              "...I..hh..I...",
              "..I..hffh..I..",
              "..IFFhhhhFFI..",
              ".WWWWWWWWWWWW.",
              ".............."])


@perk("ember_cinder_spread")
def _p_cinder():
    g = Grid()
    g.ring(7, 8.6, 4.4, 6.0, "F", 30, 150)          # burning arc jumping between targets
    g.stamp(["...h..", "..hFh.", ".hFFFh"], 5, 0)
    g.circle(2.6, 11.0, 2.6, "X").circle(11.4, 11.0, 2.6, "X")
    return g.stamp(["h.h", "hhh"], 1, 7).stamp([".F.", "FhF"], 10, 7)


@perk("ember_molten_shell")
def _p_molten():
    g = Grid()
    for a in range(0, 360, 45):
        g.ring(7, 7, 5.4, 6.9, "F", a + 8, a + 37)
    g.circle(7, 7, 3.6, "N")
    return g.stamp([".hh.", "hffh", ".hh."], 5, 5).px(5, 4, "n" if False else "0")


@perk("ember_furnace_heart")
def _p_furnace():
    return R(["..............",
              "..NNN....NNN..",
              ".NNNNN..NNNNN.",
              "NNhhhNNNNhhhNN",
              "NhffhhNNhhffhN",
              "NoooooooooooON".replace("O", "o"),
              "NhhffhhhhffhhN",
              ".NoooooooooooN"[:13] + ".",
              "..NhhhffhhhN..",
              "...NNhhhhNN...",
              "....NNhhNN....",
              ".....NNNN.....",
              "......NN......",
              ".............."])


@perk("ember_wildfire_pact")
def _p_wildfire():
    return R(["......F.......",
              "......FF......",
              ".....FFF..F...",
              ".....FFFF.FF..",
              "....FFFFFFFF..",
              "...FFFFhFFFF..",
              "...FFFhhhFFFF.",
              "..FFFhhfhhFFF.",
              "..FFFhfffhFF..",
              "...FFhhhhFF...",
              "..............",
              ".......S...RR.",
              ".SSSSSSSS..RR.",
              ".......S...RR."])


# ---- FROST ----------------------------------------------------------------------------
@perk("frost_deep_chill")
def _p_deep_chill():
    g = Grid().stamp(["....I....",
                      "..I.I.I..",
                      "...III...",
                      ".I..I..I.",
                      "IIIIiIIII",
                      ".I..I..I.",
                      "...III...",
                      "..I.I.I..",
                      "....I...."], 0, 0)
    return g.stamp(["..AA..",
                    "..AA..",
                    "..AA..",
                    "..AA..",
                    "AAAAAA",
                    ".AAAA.",
                    "..AA.."], 8, 6)


@perk("frost_brittle_armour")
def _p_brittle():
    return R([".IIIIIIIIIIII.",
              ".IIIIIoIIIIII.",
              ".IiIIIoIIIIII.",
              ".IiIIooIIIIII.",
              ".IIIIoIIIIIII.",
              ".IIIIooIIIIII.",
              ".IIIIIoooIIII.",
              ".IIIIIIIoIIII.",
              "..IIIIIIoIII..",
              "..IIIIIooIII..",
              "...IIIIoIII...",
              "....IIIoII....",
              ".....IIII.....",
              "......II......"])


@perk("frost_shatter")
def _p_shatter():
    g = Grid()
    for k in range(6):
        a = math.radians(-90 + k * 60)
        ca, sa = math.cos(a), math.sin(a)
        px_, py_ = -sa, ca
        tip = (7 + 6.9 * ca, 7 + 6.9 * sa)
        b0 = (7 + 2.6 * ca + 1.5 * px_, 7 + 2.6 * sa + 1.5 * py_)
        b1 = (7 + 2.6 * ca - 1.5 * px_, 7 + 2.6 * sa - 1.5 * py_)
        g.poly([tip, b0, b1], "I" if k % 2 == 0 else "U")
    return g.stamp([".i.", "iwi", ".i."], 6, 6)


@perk("frost_winter_ring")
def _p_winter_ring():
    g = Grid().ring(7, 7, 4.2, 6.0, "I")
    for x, y in ((0, 0), (12, 0), (0, 12), (12, 12)):
        g.stamp(["i.", ".i"] if (x == y) else [".i", "i."], x, y)
    g.stamp(["..i..", ".iIi.", "iIIIi", ".iIi.", "..i.."], 5, 5)
    return g


@perk("frost_frozen_oath")
def _p_frozen_oath():
    g = Grid()
    g.poly([(7.0, 0.0), (10.8, 3.4), (10.8, 10.6), (7.0, 14.0), (3.2, 10.6), (3.2, 3.4)], "I")
    g.poly([(7.0, 0.0), (7.0, 14.0), (3.2, 10.6), (3.2, 3.4)], "U")
    g.stamp(["i", "i", "i"], 5, 2)
    return g.stamp(["SS.NN.SS.NN.SS",
                    "S.SN.NS.SN.NS."[:14]], 0, 6).stamp(["SS.NN.SS.NN.SS"], 0, 8).rect(0, 7, 14, 1, "o")


# ---- BONE -----------------------------------------------------------------------------
def _bolt_grid(g: Grid, x0, y0, x1, y1, shaft="B", head="Q", barbs=False, fletch="Z", thick=0.75):
    g.thick(x0, y0, x1, y1, thick, shaft)
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    px_, py_ = -uy, ux
    hb = (x1 - ux * 3.2, y1 - uy * 3.2)
    g.poly([(x1 + ux * 1.0, y1 + uy * 1.0), (hb[0] + px_ * 2.3, hb[1] + py_ * 2.3), (hb[0] - px_ * 2.3, hb[1] - py_ * 2.3)], head)
    if barbs:
        for t in (0.35, 0.58):
            bx, by = x0 + dx * t, y0 + dy * t
            g.poly([(bx + ux * 0.6, by + uy * 0.6), (bx - ux * 1.6 + px_ * 1.9, by - uy * 1.6 + py_ * 1.9),
                    (bx - ux * 1.0, by - uy * 1.0)], head)
    if fletch:
        for sgn in (1, -1):
            g.poly([(x0 + ux * 2.6, y0 + uy * 2.6), (x0 + px_ * 1.9 * sgn, y0 + py_ * 1.9 * sgn),
                    (x0 - ux * 0.6 + px_ * 1.6 * sgn, y0 - uy * 0.6 + py_ * 1.6 * sgn), (x0 + ux * 0.6, y0 + uy * 0.6)], fletch)
    return g


@perk("bone_barbed_bolts")
def _p_barbed():
    return _bolt_grid(Grid(), 2.0, 12.0, 11.2, 2.8, barbs=True, thick=1.0)


@perk("bone_double_nock")
def _p_double():
    g = Grid()
    _bolt_grid(g, 1.4, 9.4, 8.4, 2.4, thick=0.95)
    _bolt_grid(g, 5.6, 13.0, 12.6, 6.0, thick=0.95)
    return g


@perk("bone_armour_break")
def _p_armour_break():
    g = R(["..............",
           "..............",
           ".NNNNNNNNN....",
           ".NNNNoNNNN....",
           ".NNNNoNNNN....",
           ".NNNooNNNN....",
           ".NNNNoNNNN....",
           "..NNNNooNN....",
           "..NNNNNoN.....",
           "...NNNNNN.....",
           "....NNNN......",
           ".....NN.......",
           "..............",
           ".............."])
    return _bolt_grid(g, 1.0, 13.0, 12.6, 1.4, thick=0.7, fletch="Z")


@perk("bone_executioner")
def _p_executioner():
    g = Grid()
    g.thick(2.0, 12.4, 11.0, 3.4, 0.7, "W")                    # axe haft behind the skull
    g.poly([(9.0, 0.6), (13.6, 2.2), (13.6, 6.8), (11.8, 5.4), (9.8, 5.0)], "S")   # blade
    g.stamp(["..BBBBBB..",
             ".BBBBBBBB.",
             "BBBBBBBBBB",
             "BBooBBooBB",
             "BBooBBooBB",
             ".BBBooBBB.",
             "..BBBBBB..",
             "..BoBoBB.."], 1, 5)
    return g.px(3, 6, "m")


@perk("bone_heavy_quarrels")
def _p_heavy():
    g = Grid()
    g.thick(2.6, 11.4, 9.4, 4.6, 1.7, "B")
    g.poly([(13.9, 0.1), (13.2, 6.6), (7.4, 0.8)], "N")                      # broad iron head
    g.poly([(2.8, 7.4), (6.6, 11.2), (3.4, 14.0), (0.0, 10.6)], "Z")        # fletching
    return g.stamp(["m", ".m", "..m"], 5, 7)


# ---- WARD -----------------------------------------------------------------------------
SHIELD_SMALL = ["TTTTTTTTT",
                "TTTTTTTTT",
                "TTTTTTTTT",
                "TTTTTTTTT",
                "TTTTTTTTT",
                ".TTTTTTT.",
                "..TTTTT..",
                "...TTT...",
                "....T...."]


@perk("ward_reinforced_barrier")
def _p_reinforced():
    g = Grid().stamp([r.replace("T", "N") for r in SHIELD_SMALL], 0, 0)
    g.rect(3, 3, 11, 11, ".")
    g.stamp(["TTTTTTTTTTT",
             "TuTTTTTTTTT",
             "TuTTTTTTTTT",
             "TTTTTTTTTTT",
             "TTTTTTTTTTT",
             "TTTTTTTTTTT",
             ".TTTTTTTTT.",
             "..TTTTTTT..",
             "...TTTTT...",
             "....TTT...."], 3, 3)
    return g.rect(2, 2, 12, 1, "o").rect(2, 2, 1, 11, "o")


@perk("ward_mending_purr")
def _p_purr():
    g = Grid().stamp(["..RRR.RRR..",
                      ".RRRRRRRRR.",
                      ".RRRRRRRRR.",
                      "..RRRRRRR..",
                      "...RRRRR...",
                      "....RRR....",
                      ".....R....."], 1, 3)
    g.px(3, 4, "r").px(3, 5, "w")
    g.ring(7, 6.5, 5.6, 7.0, "T", 120, 240)          # purr waves either side
    g.ring(7, 6.5, 5.6, 7.0, "T", 300, 60)
    return g


@perk("ward_last_thread")
def _p_last_thread():
    g = Grid().stamp(SHIELD_SMALL, 0, 3)
    g.thick(4.0, 12.0, 13.0, 1.0, 0.55, "S")            # needle
    g.px(12, 1, "o")                                       # eye of the needle
    return g.stamp(["...ttt", "..t...", ".t....", "t....."], 0, 0).px(3, 7, "t").px(5, 9, "t")


@perk("ward_reflective_fur")
def _p_reflective():
    g = Grid().stamp(SHIELD_SMALL, 0, 2)
    g.thick(13.2, 0.4, 9.6, 6.6, 0.75, "S")          # incoming
    g.thick(9.6, 6.6, 11.8, 10.4, 0.75, "S")         # bounced away
    g.poly([(13.9, 13.9), (9.4, 11.2), (13.4, 9.0)], "S")
    return g.stamp([".w.", "www", ".w."], 8, 5).stamp(["u", "u"], 2, 4)


@perk("ward_guardian_pact")
def _p_guardian():
    g = Grid().stamp([r.replace("T", "T") for r in ["TTTTTTTTTTTT",
                                                    "TTTTTTTTTTTT",
                                                    "TTTTTTTTTTTT",
                                                    "TTTTTTTTTTTT",
                                                    "TTTTTTTTTTTT",
                                                    "TTTTTTTTTTTT",
                                                    ".TTTTTTTTTT.",
                                                    "..TTTTTTTT..",
                                                    "...TTTTTT...",
                                                    "....TTTT...."]], 1, 1)
    return g.stamp(["...NN...",
                    "..N..N..",
                    ".NNNNNN.",
                    ".NuuuuN.",
                    ".NutwuN.",
                    ".NuttuN.",
                    ".NuuuuN.",
                    ".NNNNNN.",
                    "..NNNN.."], 3, 4)


# ---- GRAVITY --------------------------------------------------------------------------
@perk("gravity_wider_orbit")
def _p_wider():
    # wide circular orbit with a small moon riding it, around a dark core
    g = Grid().ring(7, 7, 5.0, 6.6, "P")
    g.circle(7, 7, 2.6, "D")
    g.circle(11.3, 2.9, 2.0, "q")
    return g.px(6, 6, "p").px(10, 2, "p")


@perk("gravity_crushing_centre")
def _p_crushing():
    g = Grid()
    g.poly(star_points(7.0, 7.0, 4.2, 1.5, n=4, rot=-90), "p")
    g.stamp(["..P..", ".PPP.", "PPPPP"], 0, 0)
    return (g.stamp(["......PP......", ".....PPPP.....", "......PP......"], 0, 0)
             .stamp(["......PP......", ".....PPPP.....", "......PP......"], 0, 11)
             .stamp([".P.", "PPP", "PPP", ".P."], 0, 5).stamp([".P.", "PPP", "PPP", ".P."], 11, 5)
             .rect(0, 0, 5, 3, "."))


@perk("gravity_event_horizon")
def _p_horizon():
    g = Grid()
    g.ring(8.5, 7, 3.4, 5.4, "q")
    g.circle(8.5, 7, 3.4, "k")
    return g.stamp(["PPP", "", "PPPP", "", "PPP"][:1], 0, 3).rect(0, 3, 3, 1, "P").rect(0, 6, 3, 2, "P").rect(0, 10, 3, 1, "P")


@perk("gravity_falling_star")
def _p_falling():
    g = Grid()
    g.thick(1.0, 1.0, 7.0, 7.0, 0.8, "P")
    g.thick(0.5, 5.0, 5.0, 9.5, 0.5, "D")
    g.thick(5.0, 0.5, 9.5, 5.0, 0.5, "D")
    g.poly(star_points(9.6, 9.6, 4.4, 1.9), "q")
    return g.px(9, 9, "p").px(9, 8, "p")


@perk("gravity_unstable_singularity")
def _p_unstable():
    g = Grid().circle(7, 7, 5.6, "D")
    g.stamp(["....p.",
             "....p.",
             "...pp.",
             "..p...",
             ".pp.pp",
             "p....."], 3, 3)
    g.px(0, 1, "q").px(13, 3, "q").px(12, 12, "q").px(1, 11, "q")
    return g.px(4, 4, "q")


# --------------------------------------------------------------------------------------
def build(reg: E.Registry) -> None:
    for name, img in build_ui_icons().items():
        assert img.shape[:2] == (16, 16), (name, img.shape)
        reg.sprite(ATLAS, f"icon/{name}", img)
    for fam in PERK_FAMILY_ORDER:
        for pid in PERK_IDS[fam]:
            img = perk_icon(pid)
            assert img.shape[:2] == (24, 24), (pid, img.shape)
            reg.sprite(ATLAS, f"icon/perk/{pid}", img)
