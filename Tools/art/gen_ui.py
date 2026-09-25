"""
gen_ui.py - EVIL CATS interface kit -> atlas "ui"  (docs/ASSET_SPEC.md section 3.8)

Everything is drawn by code. 9-slice frames are built from ring *profiles*: every pixel
gets a colour from (depth from the outer edge, facing), where facing is lit for
top/left edges, shadowed for bottom/right edges and "mid" where the two meet. Because the
colour only depends on depth and facing, the edge strips are identical along their
stretch axis and the centre is one flat colour, so Unity can slice and stretch them
without seams. Corner-only details (paw rivets, glints) stay inside the border; the
`check_nine_slice` assertion enforces that for every sprite with a border.

Tintable pieces (ui/card, ui/bar_fill, ui/circle, ui/ring, ui/white) are neutral
greyscale/white so the game can multiply them by any colour.

Also here: the logo emblem (Arc Light Cat's crowned head on a violet/silver seal),
drawn from a parametric design so gen_marketing can render it at launcher sizes.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

import eclib as E
from eclib import PAL

ATLAS = "ui"
O = PAL["outline"]
OS = PAL["outline_soft"]
CLEAR = (0, 0, 0, 0)
Color = Tuple[int, int, int, int]


# --------------------------------------------------------------------------------------
# small colour helpers
# --------------------------------------------------------------------------------------
def grey(v: int, a: int = 255) -> Color:
    return (v, v, v, a)


def mix(a: Color, b: Color, t: float) -> Color:
    """A single in-between tone (used to pick a palette-adjacent shade, not gradients)."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)) + (255,)  # type: ignore


# --------------------------------------------------------------------------------------
# 9-slice frame machinery
# --------------------------------------------------------------------------------------
def shape_mask(w: int, h: int, insets: Sequence[int] = (), open_sides: str = "",
               bottom_insets: Optional[Sequence[int]] = None) -> np.ndarray:
    """w*h rectangle with stepped corners. insets[i] = pixels cut from both ends of row i
    (counted from the top, and mirrored from the bottom unless bottom_insets is given).
    Sides listed in open_sides ('t','b','l','r') run on past the image edge (no corner cut
    and no outline there), e.g. a tab that joins the panel below it."""
    m = np.ones((h, w), bool)
    bi = insets if bottom_insets is None else bottom_insets
    for i, cut in enumerate(insets):
        if cut > 0 and "t" not in open_sides:
            if "l" not in open_sides:
                m[i, :cut] = False
            if "r" not in open_sides:
                m[i, w - cut:] = False
    for i, cut in enumerate(bi):
        if cut > 0 and "b" not in open_sides:
            if "l" not in open_sides:
                m[h - 1 - i, :cut] = False
            if "r" not in open_sides:
                m[h - 1 - i, w - cut:] = False
    return m


def _shifted(a: np.ndarray, dy: int, dx: int, fill_edge: Optional[str], open_sides: str) -> np.ndarray:
    """Neighbour lookup: out[y,x] = a[y+dy, x+dx]; beyond the image edge is `False`/-1
    unless that side is open (then the edge value is repeated)."""
    h, w = a.shape
    out = np.full_like(a, False if a.dtype == bool else -1)
    ys0, ys1 = max(0, -dy), min(h, h - dy)
    xs0, xs1 = max(0, -dx), min(w, w - dx)
    out[ys0:ys1, xs0:xs1] = a[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
    if dy == -1 and "t" in open_sides:
        out[0, :] = a[0, :]
    if dy == 1 and "b" in open_sides:
        out[-1, :] = a[-1, :]
    if dx == -1 and "l" in open_sides:
        out[:, 0] = a[:, 0]
    if dx == 1 and "r" in open_sides:
        out[:, -1] = a[:, -1]
    return out


def depth_map(mask: np.ndarray, open_sides: str = "") -> np.ndarray:
    """City-block distance (in rings) from the outside; -1 outside the mask."""
    depth = np.full(mask.shape, -1, int)
    cur = mask.copy()
    k = 0
    while cur.any():
        er = cur.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            er &= _shifted(cur, dy, dx, None, open_sides)
        ring = cur & ~er
        depth[ring] = k
        cur = er
        k += 1
    return depth


def facing_map(depth: np.ndarray, open_sides: str = "") -> np.ndarray:
    """+1 lit (edge faces up/left), -1 shadow (faces down/right), 0 where both meet."""
    lit = np.zeros(depth.shape, int)
    sh = np.zeros(depth.shape, int)
    for dy, dx, sign in ((-1, 0, 1), (0, -1, 1), (1, 0, -1), (0, 1, -1)):
        nb = _shifted(depth, dy, dx, None, open_sides)
        shallower = nb < depth
        if sign > 0:
            lit += shallower
        else:
            sh += shallower
    return np.sign(lit - sh)


def paint_rings(mask: np.ndarray, rings: Sequence, fill: Optional[Color], open_sides: str = "") -> np.ndarray:
    """rings[d] is a colour, None (transparent) or a (lit, mid, shadow) triple."""
    h, w = mask.shape
    depth = depth_map(mask, open_sides)
    face = facing_map(depth, open_sides)
    img = E.new(w, h)
    for y in range(h):
        for x in range(w):
            d = depth[y, x]
            if d < 0:
                continue
            if d < len(rings):
                r = rings[d]
                if r is None:
                    continue
                if isinstance(r[0], (int, np.integer)):
                    col = r
                else:
                    col = r[0] if face[y, x] > 0 else (r[1] if face[y, x] == 0 else r[2])
            else:
                col = fill
            if col is not None:
                img[y, x] = col
    return img


def frame(w, h, rings, fill, insets=(), open_sides="", bottom_insets=None) -> np.ndarray:
    return paint_rings(shape_mask(w, h, insets, open_sides, bottom_insets), rings, fill, open_sides)


def check_nine_slice(name: str, img: np.ndarray, border: Tuple[int, int, int, int]) -> None:
    """Edges must be uniform along their stretch axis and the centre must be flat,
    otherwise Unity's sliced stretch would smear detail."""
    l, b, r, t = border
    h, w = img.shape[:2]
    cx0, cx1 = l, w - r
    cy0, cy1 = t, h - b
    # an axis without borders is not sliced (Unity just scales it), so only check the
    # stretch axes that actually have borders
    if cx1 > cx0 and (l or r):  # top and bottom strips: every column identical
        for ys in (slice(0, t), slice(cy0, cy1), slice(h - b, h)):
            strip = img[ys, cx0:cx1]
            if strip.size and not (strip == strip[:, :1]).all():
                raise AssertionError(f"9-slice: {name} varies along x in rows {ys}")
    if cy1 > cy0 and (t or b):  # left and right strips: every row identical
        for xs in (slice(0, l), slice(cx0, cx1), slice(w - r, w)):
            strip = img[cy0:cy1, xs]
            if strip.size and not (strip == strip[:1, :]).all():
                raise AssertionError(f"9-slice: {name} varies along y in columns {xs}")


def nine_slice(img: np.ndarray, border: Tuple[int, int, int, int], W: int, H: int) -> np.ndarray:
    """Stretch like Unity's Image.Type.Sliced (nearest sampling). For previews/mocks."""
    l, b, r, t = border
    h, w = img.shape[:2]

    def axis_map(n_src, a, c, n_dst):
        mid_src = n_src - a - c
        idx = []
        for i in range(n_dst):
            if i < a:
                idx.append(i)
            elif i >= n_dst - c:
                idx.append(n_src - (n_dst - i))
            else:
                if mid_src <= 0:
                    idx.append(min(n_src - 1, a))
                else:
                    k = (i - a) * mid_src // max(1, n_dst - a - c)
                    idx.append(a + k)
        return np.array(idx)

    xs = axis_map(w, l, r, W)
    ys = axis_map(h, t, b, H)
    return img[ys][:, xs].copy()


def recolor_px(img: np.ndarray, pts: Sequence[Tuple[int, int]], c: Color) -> None:
    for x, y in pts:
        if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
            img[y, x] = c


def stamp_corners(img: np.ndarray, orn: np.ndarray, dx: int = 0, dy: int = 0, mirror: bool = True) -> None:
    """Paste a top-left corner ornament into all four corners (mirrored to fit)."""
    h, w = img.shape[:2]
    oh, ow = orn.shape[:2]
    E.paste(img, orn, dx, dy)
    E.paste(img, E.flip_x(orn) if mirror else orn, w - ow - dx, dy)
    E.paste(img, E.flip_y(orn) if mirror else orn, dx, h - oh - dy)
    E.paste(img, E.flip_y(E.flip_x(orn)) if mirror else orn, w - ow - dx, h - oh - dy)


def ascii_img(rows: Sequence[str], legend: Dict[str, Color]) -> np.ndarray:
    return E.ascii_art(rows, legend)


# --------------------------------------------------------------------------------------
# palettes for the kit
# --------------------------------------------------------------------------------------
SILVER_TRIM = (PAL["silver2"], PAL["silver1"], PAL["silver0"])
VSTONE = (PAL["violet2"], PAL["violet1"], mix(PAL["violet0"], PAL["violet1"], 0.5))   # violet stone band
RECESS = (mix(O, PAL["violet0"], 0.35), PAL["violet0"], PAL["violet1"])  # inverted: lit side dark
PANEL_FILL = PAL["violet0"]


def _auto_outline(fill_rows: Sequence[str], legend: Dict[str, Color], pad: int = 1) -> np.ndarray:
    """ASCII fill + automatic 1px outline (4-neighbour)."""
    w = max(len(r) for r in fill_rows)
    rows = ["." * (w + 2 * pad)] * pad + ["." * pad + r.ljust(w, ".") + "." * pad for r in fill_rows] + \
           ["." * (w + 2 * pad)] * pad
    return E.outline(E.ascii_art(rows, legend), O)


def paw_rivet() -> np.ndarray:
    """7x7 silver paw print (three toes over a pad) used on frame corners."""
    return _auto_outline([
        "T.T.T",
        ".....",
        ".HPP.",
        "PPPPP",
        ".PPd.",
    ], {"T": PAL["silver2"], "P": PAL["silver1"], "H": PAL["silver3"], "d": PAL["silver0"]})


# --------------------------------------------------------------------------------------
# frames
# --------------------------------------------------------------------------------------
def make_panel() -> np.ndarray:
    rings = [O, SILVER_TRIM, O, VSTONE, RECESS]
    img = frame(24, 24, rings, PANEL_FILL, insets=(2, 1))
    stamp_corners(img, paw_rivet(), 0, 0, mirror=False)
    return img


def make_panel_inset() -> np.ndarray:
    # a well cut into a panel: dark rim, shadow on the top/left inner edge, faint light
    # catching the bottom/right lip; a thin dim silver line keeps it on-style.
    rings = [
        O,
        (mix(O, PAL["violet0"], 0.2), mix(O, PAL["violet0"], 0.5), PAL["silver0"]),
        (mix(O, PAL["violet0"], 0.5), mix(O, PAL["violet0"], 0.7), mix(O, PAL["violet0"], 0.7)),
    ]
    return frame(24, 24, rings, mix(O, PAL["violet0"], 0.7), insets=(1,))


BUTTON_STYLES = {
    #            rim (lit, mid, shadow)                              face hi / face / face lo       lip
    "violet": ((PAL["silver2"], PAL["silver1"], PAL["silver0"]), PAL["violet3"], PAL["violet2"], PAL["violet1"], PAL["violet0"]),
    "gold": ((PAL["gold4"], PAL["gold3"], PAL["gold1"]), PAL["gold3"], PAL["gold2"], PAL["gold1"], PAL["gold0"]),
    "red": ((PAL["red4"], PAL["red3"], PAL["red1"]), PAL["red3"], PAL["red2"], PAL["red1"], PAL["red0"]),
    "disabled": ((PAL["stone4"], PAL["stone3"], PAL["stone1"]), PAL["stone3"], PAL["stone2"], PAL["stone1"], PAL["stone0"]),
}

BUTTON_INSETS = (2, 1)
LIP = 3


def make_button(style: str, pressed: bool = False, w: int = 24, h: int = 24) -> np.ndarray:
    """Raised button: face + a LIP-px darker base below it. Pressed: the face drops onto
    the base (same silhouette, so layouts don't jump) and a dark band shows at the top."""
    rim, fhi, face, flo, lip = BUTTON_STYLES[style]
    face_rings = [None, rim, (fhi, face, flo)]
    if not pressed:
        img = frame(w, h, [O], lip, insets=BUTTON_INSETS)
        E.paste(img, frame(w, h - LIP, face_rings, face, insets=BUTTON_INSETS), 0, 0)
        return img
    img = frame(w, h, [O], mix(O, lip, 0.5), insets=BUTTON_INSETS)
    pressed_rings = [None, (rim[1], rim[1], rim[2]), (face, face, flo)]
    f = frame(w, h - LIP + 1, pressed_rings, face, insets=BUTTON_INSETS)
    f = E.recolor(f, {face: mix(face, flo, 0.35)})
    E.paste(img, f, 0, LIP - 1)
    E.paste(img, frame(w, h, [O], None, insets=BUTTON_INSETS), 0, 0)  # keep the silhouette outline
    return img


def make_card() -> np.ndarray:
    """Neutral (greyscale) card: multiply by any family colour in code."""
    rings = [
        O,
        (grey(250), grey(226), grey(168)),
        (grey(208), grey(196), grey(146)),
        grey(36),
    ]
    img = frame(32, 32, rings, grey(64), insets=(3, 1, 1))
    br = ascii_img([
        "LLLL",
        "L...",
        "L...",
        "L...",
    ], {"L": grey(140)})
    stamp_corners(img, br, 5, 5, mirror=True)
    return img


def make_slot_frame() -> np.ndarray:
    rings = [O, SILVER_TRIM, O, VSTONE, RECESS]
    img = frame(40, 40, rings, mix(O, PAL["violet0"], 0.6), insets=(3, 1, 1))
    stamp_corners(img, paw_rivet(), 0, 0, mirror=False)
    return img


def make_bar_bg() -> np.ndarray:
    rings = [O, (mix(O, PAL["stone0"], 0.3), PAL["stone0"], PAL["stone1"])]
    return frame(12, 8, rings, PAL["stone0"], insets=(1,))


def make_bar_fill() -> np.ndarray:
    # transparent where the background's outline + channel edge sit; white body with a
    # shine row on top and a darker row at the bottom so a tint keeps some volume.
    rings = [None, None, (grey(255), grey(232), grey(150))]
    return frame(12, 8, rings, grey(206), insets=(1,))


def _bar_strip(w: int, h: int, top: Sequence[Color], bottom: Sequence[Color], fill: Color,
               side_lit: Color, side_shadow: Color) -> np.ndarray:
    """Full-width HUD strip: explicit row stacks at the top and bottom (outermost first)."""
    img = E.new(w, h, fill)
    for y in range(len(top), h - len(bottom)):
        img[y, 0] = O
        img[y, 1] = side_lit
        img[y, w - 2] = side_shadow
        img[y, w - 1] = O
    for i, c in enumerate(top):
        img[i, :] = c
    for i, c in enumerate(bottom):
        img[h - 1 - i, :] = c
    return img


def make_topbar() -> np.ndarray:
    # plain top (it sits against the screen top); silver-trimmed bottom edge with paw rivets
    img = _bar_strip(24, 24, top=[O, PAL["stone2"]],
                     bottom=[O, PAL["silver0"], PAL["silver2"], O, mix(PAL["stone0"], PAL["stone1"], 0.5)],
                     fill=PAL["stone1"], side_lit=PAL["stone2"], side_shadow=PAL["stone0"])
    paw = paw_rivet()
    E.paste(img, paw, 0, 24 - 7)
    E.paste(img, paw, 24 - 7, 24 - 7)
    return img


def make_dock() -> np.ndarray:
    # mirror of the top bar: silver-trimmed top edge with paw rivets, plain bottom
    img = _bar_strip(24, 24, top=[O, PAL["silver2"], PAL["silver0"], O, PAL["stone2"]],
                     bottom=[O, PAL["stone0"]],
                     fill=PAL["stone1"], side_lit=PAL["stone2"], side_shadow=PAL["stone0"])
    paw = paw_rivet()
    E.paste(img, paw, 0, 0)
    E.paste(img, paw, 24 - 7, 0)
    return img


def make_tab(active: bool) -> np.ndarray:
    if active:
        rings = [O, (PAL["silver2"], PAL["silver1"], PAL["silver0"]), (PAL["violet3"], PAL["violet2"], PAL["violet2"])]
        return frame(24, 16, rings, PAL["violet2"], insets=(3, 1, 1), open_sides="b")
    rings = [O, (PAL["stone3"], PAL["stone2"], PAL["stone1"]), (PAL["violet1"], PAL["violet1"], PAL["violet0"])]
    return frame(24, 16, rings, PAL["violet1"], insets=(3, 1, 1), bottom_insets=())


def make_tooltip() -> np.ndarray:
    rings = [O, (PAL["silver2"], PAL["silver1"], PAL["silver0"]), O]
    return frame(16, 16, rings, mix(O, PAL["violet0"], 0.45), insets=(1,))


def make_badge() -> np.ndarray:
    return ascii_img([
        "..oooo..",
        ".o3322o.",
        "o342222o",
        "o322221o",
        "o222211o",
        "o222111o",
        ".o2111o.",
        "..oooo..",
    ], {"o": O, "1": PAL["red1"], "2": PAL["red2"], "3": PAL["red3"], "4": PAL["red4"]})


def make_toggle(on: bool) -> np.ndarray:
    w, h = 24, 12
    if on:
        track = [O, (PAL["cyan0"], PAL["cyan1"], PAL["cyan1"])]
        tfill = PAL["cyan1"]
    else:
        track = [O, (mix(O, PAL["stone0"], 0.4), PAL["stone0"], PAL["stone1"])]
        tfill = PAL["stone0"]
    img = frame(w, h, track, tfill, insets=(3, 1, 1))
    knob_rows = [
        "..oooooo..",
        ".oHHSSSSo.",
        "oHHSSSSSSo",
        "oHSSSSSSMo",
        "oSSSSSSSMo",
        "oSSSSSSSMo",
        "oSSSSSSMMo",
        "oSSSSSMMMo",
        ".oSMMMMMo.",
        "..oooooo..",
    ]
    if on:
        knob = ascii_img(knob_rows, {"o": O, "H": PAL["silver3"], "S": PAL["silver2"], "M": PAL["silver1"]})
        E.paste(img, knob, w - 11, 1)
    else:
        knob = ascii_img(knob_rows, {"o": O, "H": PAL["silver2"], "S": PAL["silver1"], "M": PAL["silver0"]})
        E.paste(img, knob, 1, 1)
    return img


def make_slider_bg() -> np.ndarray:
    rings = [O, (mix(O, PAL["stone0"], 0.3), PAL["stone0"], PAL["stone1"])]
    return frame(12, 6, rings, PAL["stone0"], insets=(1,))


def make_slider_fill() -> np.ndarray:
    img = E.new(12, 6)
    rows = [None, PAL["cyan3"], PAL["cyan2"], PAL["cyan2"], PAL["cyan1"], None]
    for y, c in enumerate(rows):
        if c is None:
            continue
        img[y, 1:11] = c
    # rounded ends: keep the outline-corner pixels of the track visible
    img[1, 1] = CLEAR
    img[1, 10] = CLEAR
    img[4, 1] = CLEAR
    img[4, 10] = CLEAR
    return img


def make_slider_handle() -> np.ndarray:
    return ascii_img([
        "..oooooo..",
        ".oHHSSSSo.",
        "oHSSSSSSMo",
        "oSSooooSMo",
        "oSocCCcoMo",
        "oSoCWCcoMo",
        "oSocCccoMo",
        "oSSooooSMo",
        "oSSSSSSSMo",
        "oSSSSSSMMo",
        ".oMMMMMMo.",
        "..oooooo..",
    ], {"o": O, "H": PAL["silver3"], "S": PAL["silver2"], "M": PAL["silver0"],
        "c": PAL["cyan1"], "C": PAL["cyan2"], "W": PAL["cyan4"]})


def make_circle() -> np.ndarray:
    img = E.new(32, 32)
    for y in range(32):
        for x in range(32):
            if (x + 0.5 - 16) ** 2 + (y + 0.5 - 16) ** 2 <= 16.0 ** 2 - 0.5:
                img[y, x] = (255, 255, 255, 255)
    return img


def make_ring() -> np.ndarray:
    img = E.new(32, 32)
    for y in range(32):
        for x in range(32):
            dx, dy = x + 0.5 - 16, y + 0.5 - 16
            d = math.hypot(dx, dy)
            if d > 15.97:
                continue
            if d > 15.0:
                img[y, x] = O
            elif d > 13.0:
                lit = (-dx - dy) / max(d, 1e-6)
                img[y, x] = grey(255) if lit > -0.35 else grey(214)
            elif d > 12.0:
                img[y, x] = O
    return img


def make_vignette() -> np.ndarray:
    img = E.new(64, 64)
    for y in range(64):
        for x in range(64):
            nx = (x + 0.5 - 32) / 32
            ny = (y + 0.5 - 32) / 32
            d = math.hypot(nx, ny) / math.sqrt(2)  # 0 centre .. 1 corner
            t = max(0.0, (d - 0.45) / 0.55)
            a = int(round(210 * (t ** 1.6)))
            img[y, x] = (PAL["black"][0], PAL["black"][1], PAL["black"][2], a)
    return img


def make_divider() -> np.ndarray:
    return ascii_img([
        "..oo........oo..",
        "ooHSoooooooooSHoo"[:16],
        "oHSSSSSSSSSSSSSo"[:16],
        "..oo........oo..",
    ], {"o": O, "H": PAL["silver3"], "S": PAL["silver1"]})


def make_white() -> np.ndarray:
    return E.new(4, 4, (255, 255, 255, 255))


# --------------------------------------------------------------------------------------
# Emblem: Arc Light Cat's crowned head on a silver-rimmed violet seal
# Design space is 64x64 "units"; render(size) samples pixel centres at any size.
# --------------------------------------------------------------------------------------
def _poly_mask(S: int, pts, k: float) -> np.ndarray:
    img = E.new(S, S)
    E.polygon(img, [(x * k, y * k) for x, y in pts], (255, 255, 255, 255))
    return img[:, :, 3] > 0


def _ellipse_mask(S: int, cx, cy, rx, ry, k: float) -> np.ndarray:
    yy, xx = np.mgrid[0:S, 0:S]
    return ((xx + 0.5 - cx * k) / (rx * k)) ** 2 + ((yy + 0.5 - cy * k) / (ry * k)) ** 2 <= 1.0


def _mirror_pts(pts):
    return [(64 - x, y) for x, y in pts]


def _dilate(m: np.ndarray, diag: bool = False) -> np.ndarray:
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


def _edges(m: np.ndarray):
    """(top-left rim, bottom-right rim) pixels of a mask."""
    up = np.zeros_like(m); up[1:] = m[:-1]
    dn = np.zeros_like(m); dn[:-1] = m[1:]
    lf = np.zeros_like(m); lf[:, 1:] = m[:, :-1]
    rt = np.zeros_like(m); rt[:, :-1] = m[:, 1:]
    tl = m & (~up | ~lf)
    br = m & (~dn | ~rt)
    return tl & ~br, br & ~tl


EMBLEM_CENTER = (32.0, 34.5)
EMBLEM_R = 29.5

# design coordinates (64x64 units, y down); right-hand parts are mirrored at x=32
FACE = (32.0, 40.5, 16.2, 12.2)                     # ellipse cx, cy, rx, ry
EAR_L = [(15.2, 37.0), (11.6, 11.0), (30.6, 28.0)]
EAR_IN_L = [(18.2, 31.5), (15.2, 17.5), (25.6, 28.2)]
TUFT_L = [(17.5, 38.0), (6.8, 47.0), (14.0, 47.2), (10.8, 52.2), (22.5, 50.5)]
JAW = [(24.0, 50.0), (32.0, 56.0), (40.0, 50.0)]
CROWN = [(25.6, 27.6), (25.6, 18.0), (28.9, 22.2), (32.0, 13.6), (35.1, 22.2), (38.4, 18.0), (38.4, 27.6)]
EYE_L = [(19.0, 37.0), (29.4, 40.8), (28.4, 44.2), (20.8, 43.4)]
MUZZLE_L = (29.2, 49.0, 3.8, 3.0)
MANTLE_L = [(6.0, 44.0), (19.0, 52.0), (32.0, 59.0), (32.0, 66.0), (8.0, 60.0)]
CLASP = (32.0, 58.6)

# hand-placed pixel stamps for details that must stay crisp at every size
BOLT_BIG = [          # forehead lightning, sizes >= 48
    "...hc",
    "..hc.",
    ".hc..",
    "hcccc",
    "..cc.",
    ".cc..",
    ".c...",
    "c....",
]
BOLT_MID = [          # sizes 36..47
    "..hc",
    ".hc.",
    "hccc",
    ".cc.",
    ".c..",
    "c...",
]
BOLT_SMALL = [        # sizes < 36
    ".h",
    "hc",
    ".c",
    "c.",
]
NOSE_BIG = ["nnnn", ".nn."]
NOSE_SMALL = ["nn"]


def _clean(m: np.ndarray, min_nb: int = 2) -> np.ndarray:
    """Drop lonely pixels / 1px spurs left by polygon sampling at small sizes."""
    m = m.copy()
    for _ in range(2):
        nb = np.zeros(m.shape, int)
        nb[1:, :] += m[:-1, :]
        nb[:-1, :] += m[1:, :]
        nb[:, 1:] += m[:, :-1]
        nb[:, :-1] += m[:, 1:]
        m &= ~(m & (nb < min_nb))
    return m


def _stamp(img, rows, x0, y0, legend):
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch in legend and 0 <= y0 + j < img.shape[0] and 0 <= x0 + i < img.shape[1]:
                img[y0 + j, x0 + i] = legend[ch]


# Hand-drawn head for the 32px emblem (procedural shapes get mushy at this size).
EMBLEM_LEGEND = {
    "o": PAL["outline"], "W": PAL["silver3"], "S": PAL["silver2"], "s": PAL["silver1"], "d": PAL["silver0"],
    "v": PAL["violet1"], "V": PAL["violet2"], "L": PAL["violet3"], "M": PAL["violet4"], "e": PAL["violet0"],
    "k": PAL["fur0"], "f": PAL["fur1"], "F": PAL["fur2"], "H": PAL["fur3"],
    "c": PAL["cyan1"], "C": PAL["cyan2"], "Y": PAL["cyan3"], "Z": PAL["cyan4"], "w": PAL["white"],
}
EMBLEM32_HEAD = [
    "................................",
    "................................",
    "................................",
    ".......o.......oo.......o.......",
    "......oHo...o.oWSo.o...ofo......",
    "......oHFo..oWoWSoSo..oFfo......",
    "......oHeFo.oWWSSSso.oFefo......",
    "......oHeeFoossYCsdooFeefo......",
    "......oHFeeFooooooooFeeFfo......",
    "......oHFFeFFFFFZYFFFeFFfo......",
    "......oHFFFFFFFZYFFFFFFFfo......",
    "......oHFFFFFFFYYYFFFFFFfo......",
    ".....oHFFFFFFFFFYFFFFFFFFfo.....",
    ".....oHFFooFFFFYFFFFFooFFfo.....",
    ".....oHFoZYoFFFFFFFFoYZoFfo.....",
    ".....oHFoCCkYoFFFFoYkCCoFfo.....",
    ".....oHFFocCkCoFFoCkCcoFFfo.....",
    ".....oHFFFoooooFFoooooFFFfo.....",
    "....oHHFFFFFFSSkkSSFFFFFFffo....",
    "....oHFFFFFFsSssssSsFFFFFFfo....",
    "....ooHFFFFFFsssswsFFFFFFfoo....",
    "....ooofFFFFFFFFFFFFFFFFfooo....",
    "....oMoffFFFFFFFFFFFFFFffoMo....",
    ".....oMooffFFFFFFFFFFffooMo.....",
    ".....ovVVooffffffffffooVVvo.....",
    "......ovVVVooooSSooooVVVvo......",
    ".......oovvVVVoYSoVVVvvoo.......",
    ".........oovvvvoovvvvoo.........",
    "...........oooooooooo...........",
    "................................",
    "................................",
    "................................",
]


def seal_layer(S: int, center=None, radius=None, glow_y: float = 22.0):
    """Silver-rimmed violet seal: returns (image, field mask). Coordinates in 64-units."""
    k = S / 64.0
    img = E.new(S, S)
    yy, xx = np.mgrid[0:S, 0:S]
    c = center or EMBLEM_CENTER
    cx, cy = c[0] * k, c[1] * k
    dx, dy = xx + 0.5 - cx, yy + 0.5 - cy
    r = np.hypot(dx, dy)
    R = (radius or EMBLEM_R) * k
    band = 2 if S >= 40 else 1
    disc = _clean(r <= R, 2)
    img[disc] = O
    silver = disc & _clean(r <= R - 1, 2) & (r > R - 1 - band)
    lit = (-dx - dy) / np.maximum(r, 1e-6) / math.sqrt(2)
    for cond, col in ((lit > 0.5, PAL["silver3"]), ((lit <= 0.5) & (lit > -0.3), PAL["silver2"]),
                      ((lit <= -0.3) & (lit > -0.8), PAL["silver1"]), (lit <= -0.8, PAL["silver0"])):
        img[silver & cond] = col
    inner_line = 1 if S >= 40 else 0
    field = _clean(r <= R - 1 - band - inner_line, 2)
    gd = np.hypot(xx + 0.5 - 32.0 * k, yy + 0.5 - glow_y * k) / k
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0
    th = np.tile(bayer, (S // 4 + 1, S // 4 + 1))[:S, :S]
    v = gd / 30.0 + (th - 0.5) * (0.12 if S >= 40 else 0.0)
    img[field & (v >= 0.80)] = PAL["violet1"]
    img[field & (v < 0.80) & (v >= 0.50)] = PAL["violet2"]
    img[field & (v < 0.50)] = PAL["violet3"]
    return img, field


def emblem(S: int = 64, seal: bool = True) -> np.ndarray:
    k = S / 64.0
    yy, xx = np.mgrid[0:S, 0:S]
    if seal:
        img, field = seal_layer(S)
    else:
        img, field = E.new(S, S), np.ones((S, S), bool)
    if S == 32:
        E.paste(img, E.ascii_art(EMBLEM32_HEAD, EMBLEM_LEGEND), 0, 0)
        return img

    # --- high mantle collar behind the head, clipped to the seal field
    mant = _poly_mask(S, MANTLE_L, k) | _poly_mask(S, _mirror_pts(MANTLE_L), k)
    mant = _clean(mant & field)
    img[_dilate(mant) & ~mant & field] = O
    img[mant] = PAL["violet2"]
    tlm, brm = _edges(mant)
    img[brm] = PAL["violet1"]
    img[tlm] = PAL["violet4"]

    # --- head silhouette (face + ears + cheek tufts + jaw) and crown
    head = _ellipse_mask(S, *FACE, k)
    head |= _poly_mask(S, EAR_L, k) | _poly_mask(S, _mirror_pts(EAR_L), k)
    head |= _poly_mask(S, TUFT_L, k) | _poly_mask(S, _mirror_pts(TUFT_L), k)
    head |= _poly_mask(S, JAW, k)
    head = _clean(head)
    crown = _clean(_poly_mask(S, CROWN, k))
    grp = head | crown
    img[_dilate(grp) & ~grp] = O
    img[head] = PAL["fur2"]
    tl, br = _edges(head)
    img[br] = PAL["fur1"]
    img[tl] = PAL["fur3"]
    img[head & ~tl & (yy + 0.5 > 51.5 * k)] = PAL["fur1"]

    # inner ears: dark, so the ears read solid
    ei = _clean(_poly_mask(S, EAR_IN_L, k) | _poly_mask(S, _mirror_pts(EAR_IN_L), k), 1)
    img[ei] = PAL["violet0"]
    t2, _ = _edges(ei)
    img[t2] = PAL["violet1"]

    # silver muzzle: two cheek puffs
    muz = _ellipse_mask(S, *MUZZLE_L, k) | _ellipse_mask(S, 64 - MUZZLE_L[0], *MUZZLE_L[1:], k)
    muz &= head
    img[muz] = PAL["silver1"]
    t3, _ = _edges(muz)
    img[t3] = PAL["silver2"]

    # eyes: glowing cyan, slit pupil, glint
    for pts, side in ((EYE_L, -1), (_mirror_pts(EYE_L), 1)):
        em = _clean(_poly_mask(S, pts, k), 1)
        ys, xs = np.nonzero(em)
        if not len(xs):
            continue
        img[_dilate(em) & head & ~em] = O
        img[em] = PAL["cyan2"]
        te, be = _edges(em)
        img[be] = PAL["cyan1"]
        img[te] = PAL["cyan3"]
        if S >= 28:
            mx = int(math.floor(xs.mean() + 0.5 * side))
            img[em & (xx == mx) & (yy > ys.min())] = PAL["fur0"]
        gy0 = ys.min()
        gxs = xs[ys == gy0]
        img[gy0, gxs.min() if side < 0 else gxs.max()] = PAL["cyan4"]

    # nose (+ smirk and one fang on bigger sizes)
    nl = {"n": PAL["fur0"]}
    if S >= 48:
        mx0 = int(round(32 * k))          # first pixel right of the centre line
        ny0 = int(round(46.4 * k))
        _stamp(img, NOSE_BIG, mx0 - 2, ny0, nl)
        for i in (1, 2):                  # little "w" mouth under the nose
            img[ny0 + 2, mx0 - 1 - i] = PAL["fur0"]
            img[ny0 + 2, mx0 + i] = PAL["fur0"]
        img[ny0 + 3, mx0 + 2] = PAL["white"]   # one smug fang
    else:
        nx0, ny0 = int(round(32 * k)) - 1, int(round(47.2 * k))
        _stamp(img, NOSE_SMALL, nx0, ny0, nl)

    # forehead lightning mark
    bl = {"h": PAL["cyan4"], "c": PAL["cyan2"] if S < 36 else PAL["cyan3"]}
    stamp = BOLT_BIG if S >= 48 else (BOLT_MID if S >= 36 else BOLT_SMALL)
    bw, bh = len(stamp[0]), len(stamp)
    bx0 = int(round(32.6 * k - bw / 2))
    by0 = int(round(35.0 * k - bh / 2))
    _stamp(img, stamp, bx0, by0, bl)

    # crown: angular silver with a cyan gem
    img[crown] = PAL["silver2"]
    tc, bc = _edges(crown)
    img[bc] = PAL["silver0"]
    img[tc] = PAL["silver3"]
    band_m = crown & (yy + 0.5 >= 23.4 * k) & ~tc & ~bc
    img[band_m] = PAL["silver1"]
    gy, gx = int(24.6 * k), int(round(32 * k)) - (1 if S >= 48 else 0)
    if S >= 48:
        _stamp(img, ["cc", "cc"], gx, gy - 1, {"c": PAL["cyan2"]})
        img[gy - 1, gx] = PAL["cyan4"]
    else:
        img[gy, int(32 * k) - (1 if S % 2 == 0 else 0)] = PAL["cyan3"]

    # silver clasp with a cyan stone at the collar
    if seal:
        ccx, ccy = int(round(CLASP[0] * k)), int(round(CLASP[1] * k))
        if S >= 48:
            _stamp(img, ["..o..", ".oSo.", "oScSo", ".oSo.", "..o.."], ccx - 3, ccy - 2,
                   {"o": O, "S": PAL["silver2"], "c": PAL["cyan3"]})
        else:
            _stamp(img, [".o.", "oco", ".o."], ccx - 2, ccy - 1, {"o": O, "c": PAL["silver2"]})
    return img


def build(reg: E.Registry) -> None:
    def add(name, img, border=(0, 0, 0, 0), pivot=(0.5, 0.5)):
        if any(border):
            check_nine_slice(name, img, border)
        reg.sprite(ATLAS, name, img, pivot=pivot, border=border)

    b8 = (8, 8, 8, 8)
    add("ui/panel", make_panel(), b8)
    add("ui/panel_inset", make_panel_inset(), b8)
    add("ui/button", make_button("violet"), b8)
    add("ui/button_pressed", make_button("violet", pressed=True), b8)
    add("ui/button_gold", make_button("gold"), b8)
    add("ui/button_gold_pressed", make_button("gold", pressed=True), b8)
    add("ui/button_red", make_button("red"), b8)
    add("ui/button_red_pressed", make_button("red", pressed=True), b8)
    add("ui/button_disabled", make_button("disabled"), b8)
    add("ui/card", make_card(), (12, 12, 12, 12))
    add("ui/slot_frame", make_slot_frame(), (12, 12, 12, 12))
    add("ui/bar_bg", make_bar_bg(), (3, 3, 3, 3))
    add("ui/bar_fill", make_bar_fill(), (3, 3, 3, 3))
    add("ui/topbar", make_topbar(), b8)
    add("ui/dock", make_dock(), b8)
    add("ui/tab", make_tab(False), (6, 6, 6, 6))
    add("ui/tab_active", make_tab(True), (6, 6, 6, 6))
    add("ui/tooltip", make_tooltip(), (5, 5, 5, 5))
    add("ui/badge", make_badge())
    add("ui/toggle_on", make_toggle(True))
    add("ui/toggle_off", make_toggle(False))
    add("ui/slider_bg", make_slider_bg(), (3, 3, 3, 3))
    add("ui/slider_fill", make_slider_fill(), (3, 3, 3, 3))
    add("ui/slider_handle", make_slider_handle())
    add("ui/circle", make_circle())
    add("ui/ring", make_ring())
    try:
        import gen_icons
        add("ui/lock", gen_icons.lock_overlay())
    except Exception as ex:  # pragma: no cover - gen_icons is part of the same kit
        raise
    add("ui/vignette", make_vignette())
    add("ui/divider", make_divider(), (4, 0, 4, 0))
    add("ui/white", make_white())
    add("logo/emblem", emblem(64))
    add("logo/emblem_small", emblem(32))
