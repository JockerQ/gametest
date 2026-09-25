"""
gen_marketing.py - launcher icons and store art for EVIL CATS  (docs/ASSET_SPEC.md 3.11)

Runs after the atlases are written (build_all.py calls export()):

  * EvilCats/Assets/_EvilCats/Art/Icons/launcher_{512,192,144,96,72,48}.png
      the emblem on a dark violet background with a cyan rim glow. Every size is an
      integer nearest-neighbour scale of a pixel-art master drawn for that size
      (64px master -> 512/192, 48px -> 144/96/48, 36px -> 72). 512 (Play Store) is a
      full-bleed square; the legacy launcher sizes get a pixel rounded-square silhouette.
  * .../Icons/adaptive_fg_432.png  emblem centred inside the 288px safe zone, transparent
    .../Icons/adaptive_bg_432.png  dark violet with a subtle paw-lattice pattern
      (both drawn on a 108px master scaled x4, so their pixels line up)
  * store/feature_graphic_1024x500.png
      composed from the game's real atlases (env, citadel, hero, enemies, bosses, fx)
      scaled x3 with nearest-neighbour, plus the title rendered in Pixelify Sans Bold.
      Missing atlases are skipped with a note, so this can run while art is in progress.
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

import eclib as E
from eclib import PAL

O = PAL["outline"]


# --------------------------------------------------------------------------------------
# atlas access (reads what build_all wrote; x,y are top-left origin)
# --------------------------------------------------------------------------------------
class Atlases:
    def __init__(self, art_dir: str = E.ART_OUT, verbose: bool = True):
        self.dir = art_dir
        self.verbose = verbose
        self._cache: Dict[str, Optional[Tuple[np.ndarray, dict]]] = {}
        self.missing: List[str] = []

    def _note(self, msg: str) -> None:
        if self.verbose:
            print(f"[marketing] note: {msg}")

    def load(self, atlas: str) -> Optional[Tuple[np.ndarray, dict]]:
        if atlas not in self._cache:
            png = os.path.join(self.dir, f"{atlas}.png")
            js = os.path.join(self.dir, f"{atlas}_atlas.json")
            if not (os.path.exists(png) and os.path.exists(js)):
                self._note(f"atlas '{atlas}' not built yet - skipping its elements")
                self.missing.append(atlas)
                self._cache[atlas] = None
            else:
                with open(js, encoding="utf-8") as fh:
                    meta = json.load(fh)
                sheet = np.array(Image.open(png).convert("RGBA"), dtype=np.uint8)
                self._cache[atlas] = (sheet, meta)
        return self._cache[atlas]

    def names(self, atlas: str) -> List[str]:
        a = self.load(atlas)
        return sorted(a[1]["sprites"]) if a else []

    def sprite(self, atlas: str, name: str) -> Optional[np.ndarray]:
        a = self.load(atlas)
        if not a:
            return None
        sheet, meta = a
        d = meta["sprites"].get(name)
        if d is None:
            self._note(f"sprite '{name}' not in atlas '{atlas}' - skipped")
            return None
        return sheet[d["y"]:d["y"] + d["h"], d["x"]:d["x"] + d["w"]].copy()

    def meta(self, atlas: str, name: str) -> Optional[dict]:
        a = self.load(atlas)
        return a[1]["sprites"].get(name) if a else None

    def frame(self, atlas: str, anim: str, i: int = 0) -> Optional[np.ndarray]:
        a = self.load(atlas)
        if not a:
            return None
        an = a[1].get("anims", {}).get(anim)
        if an:
            frames = an["frames"]
            return self.sprite(atlas, frames[i % len(frames)])
        return self.sprite(atlas, f"{anim}/{i}")

    def find(self, atlas: str, pattern: str) -> Optional[str]:
        rx = re.compile(pattern)
        for n in self.names(atlas):
            if rx.search(n):
                return n
        return None


def paste_at_pivot(dst: np.ndarray, img: Optional[np.ndarray], x: float, y: float,
                   pivot=(0.5, 0.1), flip: bool = False) -> None:
    """Place a sprite so its pivot (normalised, from the bottom-left) lands on (x, y)."""
    if img is None:
        return
    if flip:
        img = img[:, ::-1]
    h, w = img.shape[:2]
    px = int(round(x - pivot[0] * w))
    py = int(round(y - (1.0 - pivot[1]) * h))
    alpha_paste(dst, img, px, py)


def alpha_paste(dst: np.ndarray, src: np.ndarray, x: int, y: int) -> None:
    """Vectorised alpha composite (eclib.paste is per-pixel; this is for big canvases)."""
    H, W = dst.shape[:2]
    h, w = src.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32) / 255.0
    d = dst[y0:y1, x0:x1].astype(np.float32) / 255.0
    sa = s[..., 3:4]
    da = d[..., 3:4]
    oa = sa + da * (1 - sa)
    rgb = np.where(oa > 0, (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6), 0)
    dst[y0:y1, x0:x1, :3] = np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)
    dst[y0:y1, x0:x1, 3] = np.clip(oa[..., 0] * 255 + 0.5, 0, 255).astype(np.uint8)


def scale(img: np.ndarray, k: int) -> np.ndarray:
    return np.repeat(np.repeat(img, k, axis=0), k, axis=1)


def _dilate(m: np.ndarray) -> np.ndarray:
    g = m.copy()
    g[1:, :] |= m[:-1, :]
    g[:-1, :] |= m[1:, :]
    g[:, 1:] |= m[:, :-1]
    g[:, :-1] |= m[:, 1:]
    return g


BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0 + 1 / 32


def _bayer(h: int, w: int) -> np.ndarray:
    return np.tile(BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w]


def _emblem(size: int) -> np.ndarray:
    import gen_ui
    return gen_ui.emblem(size)


# --------------------------------------------------------------------------------------
# launcher + adaptive icons
# --------------------------------------------------------------------------------------
PAW_TILE = [          # 12x12 repeat: one small paw print per tile, offset rows
    "............",
    "............",
    "...p.p......",
    "..p...p.....",
    "....pp......",
    "...pppp.....",
    "............",
    "............",
    "............",
    "............",
    "............",
    "............",
]


def background(size: int, pattern: bool = True, glow: bool = True) -> np.ndarray:
    """Dark violet field: stepped radial light in the middle, darker corners, faint paws."""
    img = E.new(size, size, PAL["violet0"])
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(xx + 0.5 - size / 2, yy + 0.5 - size / 2) / (size / 2)
    th = _bayer(size, size)
    if glow:
        img[(d + (th - 0.5) * 0.18) < 0.62] = PAL["violet1"]
    img[(d + (th - 0.5) * 0.18) > 1.18] = E.hexc("#1a0c28")
    if pattern:
        faint = E.hexc("#2d1644")
        faint_in = E.hexc("#4a2873")
        cell = 12
        for ty in range(-1, size // cell + 2):
            for tx in range(-1, size // cell + 2):
                ox = tx * cell + (6 if ty % 2 else 0)
                oy = ty * cell
                for j, row in enumerate(PAW_TILE):
                    for i, ch in enumerate(row):
                        if ch != "p":
                            continue
                        x, y = ox + i, oy + j
                        if 0 <= x < size and 0 <= y < size:
                            img[y, x] = faint_in if img[y, x, 0] == PAL["violet1"][0] else faint
    return img


def rim_glow(canvas: np.ndarray, mask: np.ndarray, rings=None) -> None:
    """Pixel-art glow: solid cyan bands hugging the silhouette, the last one dithered."""
    rings = rings or [(PAL["cyan2"], 1.0), (PAL["cyan1"], 1.0), (PAL["cyan0"], 0.5)]
    grown = mask.copy()
    th = _bayer(*mask.shape)
    for col, density in rings:
        nxt = _dilate(grown)
        band = nxt & ~grown
        if density < 1.0:
            band &= th < density
        canvas[band] = col
        grown = nxt


def launcher_master(size: int, emblem_size: int) -> np.ndarray:
    img = background(size)
    em = _emblem(emblem_size)
    off = (size - emblem_size) // 2
    placed = np.zeros((size, size), bool)
    placed[off:off + emblem_size, off:off + emblem_size] = em[:, :, 3] > 0
    rim_glow(img, placed)
    E.paste(img, em, off, off)
    return img


def rounded_legacy(img: np.ndarray, radius: float) -> np.ndarray:
    """Pixel rounded square with a 1px outline; outside the shape is transparent."""
    n = img.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    cx = np.clip(xx + 0.5, radius, n - radius)
    cy = np.clip(yy + 0.5, radius, n - radius)
    inside = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) <= radius
    out = img.copy()
    out[~inside] = (0, 0, 0, 0)
    er = inside.copy()
    er[1:, :] &= inside[:-1, :]
    er[:-1, :] &= inside[1:, :]
    er[:, 1:] &= inside[:, :-1]
    er[:, :-1] &= inside[:, 1:]
    out[inside & ~er] = O
    return out


LAUNCHERS = [  # (output size, master size, emblem size inside the master)
    (512, 64, 52), (192, 64, 52), (144, 48, 40), (96, 48, 40), (72, 36, 32), (48, 48, 40),
]


def export_launcher_icons(out_dir: str = E.ICON_OUT) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []
    masters: Dict[Tuple[int, int], np.ndarray] = {}
    for out, m, es in LAUNCHERS:
        key = (m, es)
        if key not in masters:
            masters[key] = launcher_master(m, es)
        master = masters[key]
        if out != 512:
            master = rounded_legacy(master, radius=m * 0.14)
        k = out // m
        assert k * m == out, (out, m)
        path = os.path.join(out_dir, f"launcher_{out}.png")
        E.to_pil(scale(master, k)).save(path, optimize=True)
        written.append(path)

    # adaptive icon: 108px masters x4 (432px). Visible area = inner 72dp (288px),
    # guaranteed-safe circle = 66dp (264px); the round seal is 236px wide.
    bg = background(108)
    E.to_pil(scale(bg, 4)).save(os.path.join(out_dir, "adaptive_bg_432.png"), optimize=True)
    fg = E.new(108, 108)
    em = _emblem(64)
    off = (108 - 64) // 2
    mask = np.zeros((108, 108), bool)
    mask[off:off + 64, off:off + 64] = em[:, :, 3] > 0
    rim_glow(fg, mask, [(PAL["cyan2"], 1.0), (PAL["cyan1"], 0.5)])
    E.paste(fg, em, off, off)
    E.to_pil(scale(fg, 4)).save(os.path.join(out_dir, "adaptive_fg_432.png"), optimize=True)
    written += [os.path.join(out_dir, "adaptive_bg_432.png"), os.path.join(out_dir, "adaptive_fg_432.png")]
    return written


# --------------------------------------------------------------------------------------
# store feature graphic
# --------------------------------------------------------------------------------------
FG_W, FG_H, FG_K = 1024, 500, 3          # composed at 1/3 scale, then x3 nearest
AW, AH = (FG_W + FG_K - 1) // FG_K, (FG_H + FG_K - 1) // FG_K     # 342 x 167 art px


TITLE_UNIT = 1000.0 / 65.0     # Pixelify Sans' design grid: 1 unit = 65/1000 em (cap = 10 units)


def _title_mask(text: str, units: int = 3) -> np.ndarray:
    """Pixelify Sans Bold on its own design grid (so strokes land on whole pixels), with
    one logo-lettering tweak: this font's C is an O with a one-unit slit, which closes up
    once outlined, so the C gets a proper open aperture."""
    from PIL import ImageDraw
    font = E.font(TITLE_UNIT * units, bold=True)
    x0, y0, x1, y1 = font.getbbox(text)
    w, h = x1 - x0 + 4, y1 - y0 + 4
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).text((2 - x0, 2 - y0), text, fill=255, font=font)
    m = np.array(im) > 127
    for i, ch in enumerate(text):
        if ch not in "Cc":
            continue
        # find this glyph's own ink by drawing it alone at the same pen position
        gi = Image.new("L", (w, h), 0)
        ImageDraw.Draw(gi).text((2 - x0 + font.getlength(text[:i]), 2 - y0), ch, fill=255, font=font)
        gm = np.array(gi) > 127
        cols_ink = np.nonzero(gm.any(axis=0))[0]
        if not len(cols_ink):
            continue
        c1 = cols_ink.max()
        cs = slice(c1 - 2 * units + 1, c1 + 1)            # the right-hand stroke
        rows = np.nonzero(gm[:, c1])[0]                     # extent of the outer edge only
        top, bot = rows.min(), rows.max()
        m[top + 2 * units:bot - 2 * units + 1, cs] &= ~gm[top + 2 * units:bot - 2 * units + 1, cs]
    return m


def _title_layer(lines=("EVIL", "CATS"), units: int = 3, gap: int = 4) -> np.ndarray:
    """Stacked title in art pixels: stepped cyan fill with a white top edge, 1px dark
    outline and a straight-down violet drop shadow (kept out of the letter apertures)."""
    masks = [_title_mask(t, units) for t in lines]
    w = max(m.shape[1] for m in masks) + 4
    h = sum(m.shape[0] for m in masks) + gap * (len(masks) - 1) + 6
    m = np.zeros((h, w), bool)
    y = 1
    for mk in masks:
        m[y:y + mk.shape[0], 1:1 + mk.shape[1]] = mk
        y += mk.shape[0] + gap
    out = E.new(w, h)
    ring = _dilate(m) & ~m
    sh = np.zeros_like(m)
    sh[3:, :] = m[:-3, :]
    shadow = (sh | (_dilate(sh) & np.roll(sh, -1, axis=0))) & ~m & ~ring
    out[shadow] = PAL["violet1"]
    for mk_top, mk in zip(np.cumsum([1] + [mk.shape[0] + gap for mk in masks[:-1]]), masks):
        rows = np.nonzero(mk.any(axis=1))[0]
        t0, t1 = mk_top + rows.min(), mk_top + rows.max()
        for yy in range(t0, t1 + 1):
            rel = (yy - t0) / max(1, t1 - t0)
            c = PAL["cyan4"] if rel < 0.3 else (PAL["cyan3"] if rel < 0.62 else PAL["cyan2"])
            out[yy][m[yy]] = c
    top_edge = m & ~np.vstack([np.zeros((1, w), bool), m[:-1]])
    out[top_edge] = PAL["white"]
    out[ring] = O
    return out


def _ground(canvas: np.ndarray, at: Atlases) -> None:
    tile = at.sprite("env_gravewood", "env/gravewood/ground")
    if tile is None:
        # quiet fallback so the graphic never ships blank
        canvas[:] = PAL["gw_grass1"]
        th = _bayer(*canvas.shape[:2])
        canvas[th < 0.12] = PAL["gw_grass2"]
        return
    th_, tw_ = tile.shape[:2]
    for y in range(0, canvas.shape[0], th_):
        for x in range(0, canvas.shape[1], tw_):
            alpha_paste(canvas, tile, x, y)


def _path(canvas: np.ndarray, at: Atlases, pts: List[Tuple[float, float]], rng) -> None:
    stamps = [at.sprite("env_gravewood", f"env/gravewood/path/{i}") for i in range(4)]
    stamps = [s for s in stamps if s is not None]
    if not stamps:
        return
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = int(math.hypot(x1 - x0, y1 - y0) / 6) + 1
        for i in range(n):
            t = i / n
            s = stamps[rng.randrange(len(stamps))]
            alpha_paste(canvas, s, int(x0 + (x1 - x0) * t) - 8, int(y0 + (y1 - y0) * t) - 8)


def _darken(canvas: np.ndarray, amount: np.ndarray) -> None:
    c = canvas[:, :, :3].astype(np.float32)
    tgt = np.array(PAL["black"][:3], np.float32)
    canvas[:, :, :3] = np.clip(c + (tgt - c) * amount[..., None], 0, 255).astype(np.uint8)


def compose_feature(at: Atlases) -> np.ndarray:
    rng = E.rng(0xEC51)
    cv = E.new(AW, AH, PAL["black"])
    _ground(cv, at)

    # citadel on the right third, paths leading in from both sides
    cx, cy = 262, 100               # footprint centre (pivot) in art px
    _path(cv, at, [(-10, 150), (70, 132), (150, 118), (cx - 30, cy + 8)], rng)
    _path(cv, at, [(AW + 10, 40), (300, 70), (cx + 30, cy - 4)], rng)
    _path(cv, at, [(cx + 6, AH + 10), (cx + 2, cy + 30)], rng)

    props = [("tree_dead_a", 334, 58), ("tree_dead_b", 200, 30), ("tree_dead_c", 18, 118),
             ("grave_a", 128, 100), ("grave_c", 318, 162), ("grave_b", 214, 64),
             ("lantern_post", 196, 150), ("rock_a", 60, 162), ("wall_broken_a", 112, 172),
             ("bush_a", 330, 118), ("mushroom_a", 84, 132), ("grass_a", 232, 160),
             ("grass_b", 300, 30), ("grass_c", 36, 96), ("stump", 158, 42)]
    for name, x, y in sorted(props, key=lambda p: p[2]):
        paste_at_pivot(cv, at.sprite("env_gravewood", f"env/gravewood/prop/{name}"), x, y)

    shadow = at.sprite("citadel", "citadel/shadow")
    paste_at_pivot(cv, shadow, cx, cy + 12, pivot=(0.5, 0.5))
    base = at.sprite("citadel", "citadel/base")
    bmeta = at.meta("citadel", "citadel/base") or {}
    piv = tuple(bmeta.get("pivot", (0.5, 0.5)))
    anchors = bmeta.get("anchors", {})
    if base is not None:
        paste_at_pivot(cv, base, cx, cy, pivot=piv)
        sh = at.frame("citadel", "citadel/stormheart", 1)
        if sh is not None and "stormheart" in anchors:
            ax, ay = anchors["stormheart"]
            paste_at_pivot(cv, sh, cx + ax, cy - ay, pivot=(0.5, 0.5))
    hero = at.frame("hero", "hero/arc_light_cat/cast", 4)
    hx, hy = (cx + anchors["hero"][0], cy - anchors["hero"][1]) if "hero" in anchors else (cx, cy - 12)
    hmeta = at.meta("hero", "hero/arc_light_cat/cast/4") or {}
    paste_at_pivot(cv, hero, hx, hy, pivot=tuple(hmeta.get("pivot", (0.5, 0.1))))

    # the Golden Collar Order closing in (sprites face right; flip those coming from the right)
    foes = [
        ("enemies", "enemy/rat_raider/walk", 1, 172, 134, False),
        ("enemies", "enemy/hound_runner/walk", 2, 140, 150, False),
        ("enemies", "enemy/shield_guard/walk", 0, 200, 124, False),
        ("enemies", "enemy/powder_rat/walk", 3, 112, 130, False),
        ("enemies", "enemy/rat_raider_elite/walk", 2, 88, 158, False),
        ("enemies", "enemy/crow_archer/walk", 1, 324, 90, True),
        ("enemies", "enemy/iron_golem/walk", 0, 318, 150, True),
        ("enemies", "enemy/bell_priest/walk", 2, 314, 64, True),
        ("enemies", "enemy/hound_runner_elite/walk", 0, 300, 134, True),
    ]
    for atlas, anim, fi, x, y, flip in sorted(foes, key=lambda f: f[4]):
        img = at.frame(atlas, anim, fi)
        mm = at.meta(atlas, f"{anim}/{fi}") or {}
        paste_at_pivot(cv, img, x, y, pivot=tuple(mm.get("pivot", (0.5, 0.1))), flip=flip)
    for i, (x, y) in enumerate(((304, 16), (318, 10), (292, 24), (328, 24), (312, 30))):
        paste_at_pivot(cv, at.frame("enemies", "enemy/bat/fly", i), x, y, pivot=(0.5, 0.5), flip=True)
    boss = at.frame("bosses", "boss/king_goldenfang/command", 1)
    bm = at.meta("bosses", "boss/king_goldenfang/command/1") or {}
    paste_at_pivot(cv, boss, 46, 166, pivot=tuple(bm.get("pivot", (0.5, 0.1))))

    # Arc Light Cat's lightning: a sky strike on the shield guard, sparks on two foes
    strike = at.frame("fx", "fx/arc_storm_strike", 2)
    if strike is not None:
        paste_at_pivot(cv, strike, 200, 126, pivot=(0.5, 0.0))
    for fi, (x, y) in ((1, (172, 126)), (2, (324, 82)), (3, (140, 142))):
        paste_at_pivot(cv, at.frame("fx", "fx/spark_hit", fi), x, y, pivot=(0.5, 0.5))

    # quiet the left third behind the title and vignette the edges
    yy, xx = np.mgrid[0:AH, 0:AW]
    th = _bayer(AH, AW)
    left = np.clip((190 - xx) / 190.0, 0, 1) * np.clip((86 - yy) / 86.0 + 0.2, 0, 1)
    edge = np.clip((np.hypot((xx - AW / 2) / (AW / 2), (yy - AH / 2) / (AH / 2)) - 0.78) * 1.6, 0, 1)
    amt = np.clip(0.62 * left + 0.55 * edge, 0, 0.8)
    _darken(cv, np.floor((amt + (th - 0.5) * 0.08) * 6) / 6)    # stepped, pixel-art style

    # title + emblem, all on the same x3 pixel grid
    title = _title_layer()
    emb = at.sprite("ui", "logo/emblem")
    if emb is None:
        emb = _emblem(64)
    alpha_paste(cv, emb, 8, 8)
    alpha_paste(cv, title, 78, 7)
    return cv


def export_feature_graphic(out_dir: str = E.STORE_OUT) -> str:
    at = Atlases()
    art = compose_feature(at)
    big = scale(art, FG_K)[:FG_H, :FG_W].copy()
    big[:, :, 3] = 255
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "feature_graphic_1024x500.png")
    E.to_pil(big).convert("RGB").save(path, optimize=True)
    if at.missing:
        print(f"[marketing] feature graphic made without: {', '.join(sorted(set(at.missing)))} "
              f"(re-run export() once those atlases exist)")
    return path


def export() -> None:
    files = export_launcher_icons()
    files.append(export_feature_graphic())
    for f in files:
        print(f"[marketing] wrote {os.path.relpath(f, E.ROOT)}")


if __name__ == "__main__":
    export()
