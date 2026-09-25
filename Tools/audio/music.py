"""
music.py - a tiny score/arrangement engine plus the Evil Cats soundtrack.

Scores are written as text, one token per note:  PITCH/DUR[flags]
  PITCH  C4, F#3, Bb5, r (rest) or [D4,F4,A4] (chord)
  DUR    w h q e s (whole .. sixteenth), t (triplet 8th), dotted with '.', '3e' = three 8ths
  flags  >  accent        ~  legato (full gate)      !  very short      _  tie into next same pitch
  |      bar line (the parser asserts every bar adds up to the time signature)
Chord progressions:  "Dm | Dm | Gm A7 | ..."  (several chords in one bar share it evenly).

Loops are rendered "folded": any sound that runs past the loop end (note tails, reverb) is
wrapped around to the start, reverb is a circular convolution and every master process uses
wrap-around padding, so the file is exactly periodic and loops without a seam.
"""
from dataclasses import dataclass, field
import numpy as np

from synth import (FS, ns, undb, note_midi, rng_for, pan, make_ir, convolve, limiter, hp,
                   circular, lufs_integrated, fade, bq, _NOTE)
import instruments as I

# ============================================================================ score parsing
DUR = {"w": 4.0, "h": 2.0, "q": 1.0, "e": 0.5, "s": 0.25, "t": 1.0 / 3.0, "x": 1.0 / 6.0}


def pdur(s):
    if s.endswith("."):
        return 1.5 * pdur(s[:-1])
    if s[0].isdigit():
        if s[-1] in DUR:
            return int(s[:-1]) * DUR[s[-1]]
        return float(s)
    return DUR[s]


@dataclass
class Ev:
    beat: float
    dur: float
    pitch: object
    vel: float = 0.8
    kw: dict = field(default_factory=dict)


def seq(text, bar=0, vel=0.8, transpose=0, bpb=4, **kw):
    """Parse a score line starting at `bar`. Returns a list of Ev (beats are absolute)."""
    t = bar * bpb
    bar_start = t
    out = []
    tie_open = False
    for tok in text.split():
        if tok == "|":
            if abs(t - bar_start - bpb) > 1e-6:
                raise ValueError("bar has %.3f beats (expected %d) near bar %d in: %s"
                                 % (t - bar_start, bpb, int(round(bar_start / bpb)), text[:60]))
            bar_start = t
            continue
        flags = ""
        while tok[-1] in ">~!_":
            flags += tok[-1]
            tok = tok[:-1]
        p, d = tok.split("/")
        d = pdur(d)
        if p != "r":
            if p.startswith("["):
                pitch = tuple(note_midi(q) + transpose for q in p[1:-1].split(","))
            else:
                pitch = note_midi(p) + transpose
            if tie_open and out and out[-1].pitch == pitch and abs(out[-1].beat + out[-1].dur - t) < 1e-6:
                out[-1].dur += d
            else:
                e_kw = dict(kw)
                if "~" in flags:
                    e_kw["gate"] = 1.0
                if "!" in flags:
                    e_kw["gate"] = 0.35
                out.append(Ev(t, d, pitch, min(1.0, vel + 0.15 * flags.count(">")), e_kw))
            tie_open = "_" in flags
        else:
            tie_open = False
        t += d
    if abs(t - bar_start) > 1e-6 and abs(t - bar_start - bpb) > 1e-6:
        raise ValueError("last bar incomplete (%.3f beats): %s" % (t - bar_start, text[:60]))
    return out


# ============================================================================ harmony helpers
QUAL = {
    "": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10], "m7": [0, 3, 7, 10], "maj7": [0, 4, 7, 11],
    "mmaj7": [0, 3, 7, 11], "dim": [0, 3, 6], "dim7": [0, 3, 6, 9], "m7b5": [0, 3, 6, 10],
    "sus4": [0, 5, 7], "7sus4": [0, 5, 7, 10], "7b9": [0, 4, 7, 10, 13], "6": [0, 4, 7, 9],
    "m6": [0, 3, 7, 9], "aug": [0, 4, 8], "5": [0, 7], "add9": [0, 4, 7, 14], "madd9": [0, 3, 7, 14],
    "sus2": [0, 2, 7], "m9": [0, 3, 7, 10, 14], "7b13": [0, 4, 7, 10, 8],
}


def pc(name):
    return (_NOTE[name[0].upper()] + name.count("#") - name[1:].count("b")) % 12


def chord_parse(sym):
    bass = None
    if "/" in sym:
        sym, b = sym.split("/")
        bass = pc(b)
    i = 2 if len(sym) > 1 and sym[1] in "#b" else 1
    root = pc(sym[:i])
    ivs = QUAL[sym[i:]]
    pcs = []
    for iv in ivs:
        p = (root + iv) % 12
        if p not in pcs:
            pcs.append(p)
    return root, pcs, (root if bass is None else bass)


def prog(text, bar=0, bpb=4):
    """'Dm | Gm A7 | ...' -> [(beat, dur, sym)]"""
    out = []
    for k, cell in enumerate(text.split("|")):
        syms = cell.split()
        if not syms:
            continue
        d = bpb / len(syms)
        for j, s in enumerate(syms):
            out.append(((bar + k) * bpb + j * d, d, s))
    return out


def voicing(sym, lo, hi, prev=None, size=None):
    root, pcs, _ = chord_parse(sym)
    size = min(len(pcs), 4) if size is None else size
    pcs = list(pcs)
    while len(pcs) > size:  # drop the fifth first, then from the top
        fifth = (root + 7) % 12
        pcs.remove(fifth if fifth in pcs and fifth != root else pcs[-1])
    tones = [m for m in range(lo, hi + 1) if m % 12 in pcs]
    cands = [tuple(tones[i:i + size]) for i in range(len(tones) - size + 1)
             if len({x % 12 for x in tones[i:i + size]}) == size]
    if not cands:
        raise ValueError("no voicing for %s in %d..%d" % (sym, lo, hi))
    if prev:
        pv = sorted(prev)
        def cost(c):
            return sum(abs(a - b) for a, b in zip(sorted(c), pv[:len(c)])) + 0.01 * abs(np.mean(c) - (lo + hi) / 2)
    else:
        def cost(c):
            return abs(np.mean(c) - (lo + hi) / 2)
    return min(cands, key=cost)


def bass_pitch(sym, lo):
    _, _, b = chord_parse(sym)
    m = lo
    while m % 12 != b:
        m += 1
    return m


def chord_tones(sym, lo, hi):
    _, pcs, _ = chord_parse(sym)
    return [m for m in range(lo, hi + 1) if m % 12 in pcs]


# ============================================================================ generators
def gen_pad(ch, lo, hi, vel=0.7, size=None, **kw):
    out, prev = [], None
    for beat, dur, sym in ch:
        v = voicing(sym, lo, hi, prev, size)
        out.append(Ev(beat, dur, v, vel, dict(kw)))
        prev = v
    return out


def gen_arp(ch, pattern, step, lo, hi, vel=0.6, accent=0.12, dur=None, **kw):
    out = []
    for beat, cdur, sym in ch:
        tones = chord_tones(sym, lo, hi)
        k = 0
        t = 0.0
        while t < cdur - 1e-6:
            idx = pattern[k % len(pattern)]
            if idx is not None:
                p = tones[min(idx, len(tones) - 1)]
                v = vel + (accent if abs((beat + t) % 1.0) < 1e-6 else 0.0)
                out.append(Ev(beat + t, dur or step, p, v, dict(kw)))
            t += step
            k += 1
    return out


def gen_offbeat(ch, lo, hi, vel=0.4, positions=(0.5, 1.5, 2.5, 3.5), dur=0.5, size=3, **kw):
    out, prev = [], None
    for beat, cdur, sym in ch:
        v = voicing(sym, lo, hi, prev, size)
        prev = v
        for p in positions:
            if p < cdur - 1e-6:
                out.append(Ev(beat + p, dur, v, vel, dict(kw)))
    return out


def gen_bass(ch, pattern, lo, vel=0.8, step=0.5, **kw):
    """pattern tokens per step: R root, 5 fifth, 8 octave, 3 third, b3/b7..., '.' rest."""
    out = []
    for beat, cdur, sym in ch:
        root = bass_pitch(sym, lo)
        _, pcs, _ = chord_parse(sym)
        rpc = chord_parse(sym)[0]
        third = next((iv for iv in (3, 4) if (rpc + iv) % 12 in pcs), 4)
        t, k = 0.0, 0
        while t < cdur - 1e-6:
            tok = pattern[k % len(pattern)]
            if tok != ".":
                off = {"R": 0, "5": 7, "8": 12, "3": third, "-": -12, "4": 5, "7": 10}[tok]
                out.append(Ev(beat + t, step, root + off, vel + (0.1 if abs(t % 1.0) < 1e-6 else 0), dict(kw)))
            t += step
            k += 1
    return out


def drums(pattern, bars, pitch=60, vel=0.8, bpb=4, **kw):
    """pattern: one char per step (len 16 -> 16ths). X accent, x normal, o soft, g ghost."""
    vm = {"X": 1.0, "x": 0.78, "o": 0.5, "g": 0.3}
    out = []
    step = bpb / len(pattern)
    for b in bars:
        for i, c in enumerate(pattern):
            if c in vm:
                out.append(Ev(b * bpb + i * step, step, pitch, vel * vm[c], dict(kw)))
    return out


def ramp(evs, v0, v1):
    """Linear velocity ramp across a list of events (crescendo)."""
    if not evs:
        return evs
    b0, b1 = evs[0].beat, evs[-1].beat
    for e in evs:
        k = 0.0 if b1 == b0 else (e.beat - b0) / (b1 - b0)
        e.vel = e.vel * (v0 + (v1 - v0) * k)
    return evs


def shift(evs, semis):
    for e in evs:
        e.pitch = tuple(p + semis for p in e.pitch) if isinstance(e.pitch, tuple) else e.pitch + semis
    return evs


# ============================================================================ song model
@dataclass
class Track:
    name: str
    inst: str
    group: str
    pan: float = 0.0
    send: float = 0.2
    gain_db: float = 0.0
    human_ms: float = 5.0
    vel_jit: float = 0.06
    phrase: bool = False  # metric accents + 2-bar phrase arch (leads)
    params: dict = field(default_factory=dict)
    events: list = field(default_factory=list)

    def add(self, evs):
        self.events.extend(evs)
        return self


@dataclass
class Song:
    id: str
    bpm: float
    bars: int
    loop: bool = True
    tail: float = 0.0
    bpb: int = 4
    lufs: float = -17.0
    groups: dict = field(default_factory=dict)
    reverb: dict = field(default_factory=dict)
    reverb_return_db: float = 0.0
    tracks: list = field(default_factory=list)
    raws: list = field(default_factory=list)  # (group, send, fn(N, loop) -> stereo)
    fade_out: float = 0.0
    volume: float = 0.8           # manifest volume (battle loops sit a little lower under the SFX)
    low_shelf_db: float = -4.0
    presence_db: float = 1.0

    def track(self, name, inst, group, **kw):
        params = {k: kw.pop(k) for k in list(kw) if k not in Track.__dataclass_fields__}
        tr = Track(name, inst, group, params=params, **kw)
        self.tracks.append(tr)
        return tr

    @property
    def spb(self):
        return 60.0 / self.bpm

    @property
    def loop_len(self):
        return int(round(self.bars * self.bpb * self.spb * FS))


def _add(buf, sig, start, wrap):
    N = buf.shape[0]
    n = sig.shape[0]
    if not wrap:
        if start < 0:
            sig = sig[-start:]
            n = sig.shape[0]
            start = 0
        end = min(N, start + n)
        if end > start:
            buf[start:end] += sig[: end - start]
        return
    start %= N
    pos = 0
    while pos < n:
        s = (start + pos) % N
        m = min(n - pos, N - s)
        buf[s:s + m] += sig[pos:pos + m]
        pos += m


_CACHE = {}
CHORD_INSTS = {"choir"}


def _note_audio(song_id, tr, ev, vq, variant):
    params = dict(tr.params)
    params.update({k: v for k, v in ev.kw.items() if k != "pan"})
    key = (tr.inst, ev.pitch, round(ev.dur, 4), vq, repr(sorted(params.items())), variant)
    a = _CACHE.get(key)
    if a is None:
        rng = rng_for(song_id, tr.name, repr(key))
        fn = I.INSTRUMENTS[tr.inst]
        if isinstance(ev.pitch, tuple) and tr.inst not in CHORD_INSTS:
            parts = [fn(p, ev.dur, vq, rng, **params) for p in ev.pitch]
            L = max(len(p) for p in parts)
            a = np.zeros((L,) + parts[0].shape[1:])
            for p in parts:
                a[:len(p)] += p
            a /= np.sqrt(len(parts))
        else:
            a = fn(ev.pitch, ev.dur, vq, rng, **params)
        if len(_CACHE) > 6000:
            _CACHE.clear()
        _CACHE[key] = a
    return a


def render_song(S, verbose=True, keep_groups=False):
    spb = S.spb
    n_loop = S.loop_len
    N = n_loop if S.loop else n_loop + ns(S.tail)
    dry = np.zeros((N, 2))
    send = np.zeros((N, 2))
    order = []
    for tr in S.tracks:
        if tr.group not in order:
            order.append(tr.group)
    for g, _, _ in S.raws:
        if g not in order:
            order.append(g)
    report = []
    kept = {}
    for g in order:
        gd = np.zeros((N, 2))
        gs = np.zeros((N, 2))
        for tr in [t for t in S.tracks if t.group == g]:
            for i, ev in enumerate(tr.events):
                r = rng_for(S.id, tr.name, i)
                jit = float(np.clip(r.normal(0.0, tr.human_ms / 1000.0), -2.5 * tr.human_ms / 1000.0,
                                    2.5 * tr.human_ms / 1000.0))
                vel = ev.vel * (1.0 + r.normal(0.0, tr.vel_jit))
                if tr.phrase or tr.group in ("lead", "lead2"):
                    pos = ev.beat % S.bpb
                    acc = 1.08 if pos < 1e-6 else (1.03 if abs(pos - 2) < 1e-6 else
                                                   (1.0 if abs(pos % 1.0) < 1e-6 else 0.93))
                    arch = 0.94 + 0.1 * np.sin(np.pi * ((ev.beat / (2 * S.bpb)) % 1.0))
                    vel *= acc * arch
                vel = float(np.clip(vel, 0.05, 1.0))
                vq = round(min(1.0, round(vel * 10.0) / 10.0 + 1e-9), 2) or 0.1
                variant = int(r.integers(0, 4))
                ev_sec = Ev(ev.beat, ev.dur * spb, ev.pitch, ev.vel, ev.kw)
                a = _note_audio(S.id, tr, ev_sec, vq, variant) * (vel / vq)
                if a.ndim == 1:
                    a = pan(a, tr.pan + ev.kw.get("pan", 0.0))
                a = a * undb(tr.gain_db)
                st = int(round((ev.beat * spb + jit) * FS))
                _add(gd, a, st, S.loop)
                if tr.send > 0:
                    _add(gs, a * tr.send, st, S.loop)
        for rg, rsend, fn in S.raws:
            if rg == g:
                a = fn(N, S.loop)
                gd += a
                gs += a * rsend
        L = lufs_integrated(gd)
        tgt = S.groups.get(g, -10.0) - 20.0
        gain = undb(tgt - L) if L > -90 else 1.0
        dry += gd * gain
        send += gs * gain
        report.append((g, L, tgt - L))
        if keep_groups:
            kept[g] = gd * gain
    ir = make_ir(**S.reverb)
    wet = convolve(send, ir, circular_len=N if S.loop else None)
    wet = hp(wet, 180.0, 2) if not S.loop else circular(lambda x: hp(x, 180.0, 2), wet)
    mix = dry + wet * undb(S.reverb_return_db)
    # master: rumble filter, loudness normalisation, look-ahead limiter (wrap-around for loops)
    def f(x):
        x = hp(x, 28.0, 2)
        x = bq(x, "lowshelf", 95.0, 0.7, S.low_shelf_db)
        return bq(x, "peak", 3200.0, 0.8, S.presence_db)
    mix = circular(f, mix, 1.0) if S.loop else f(mix)
    gr = 0.0
    for _ in range(3):
        Lm = lufs_integrated(mix)
        mix = mix * undb(S.lufs - Lm)
        mix, gr = limiter(mix, -1.6, 6.0, wrap=S.loop)
    if not S.loop:
        mix = fade(mix, 0.0, S.fade_out or 0.4)
    if S.loop:  # remove any residual DC exactly (keeps periodicity)
        mix = mix - mix.mean(axis=0, keepdims=True)
    info = dict(groups=report, limiter_db=gr, lufs=lufs_integrated(mix), n_loop=n_loop, N=N, kept=kept)
    if verbose:
        rep = ", ".join("%s %+.1fdB" % (g, gn) for g, _, gn in report)
        print("  [%s] group gains: %s | limiter %.2f dB" % (S.id, rep, gr))
    return mix, info


# ============================================================================ THE SONGS
# ---------------------------------------------------------------------------- menu
def song_menu():
    """'The Villain's Parlour' - D minor, 98 BPM, 28 bars. A clock ticks, pizzicato tiptoes,
    the low clarinet (the cat) sings in B, celesta and harp add the magic."""
    S = Song("menu", bpm=98, bars=28, loop=True, lufs=-17.0,
             reverb=dict(t60=2.1, predelay=0.022, seed=11),
             groups=dict(lead=0, lead2=-3, accomp=-8, bass=-4, pad=-9, drums=-7, sparkle=-11))
    S.volume = 0.8
    I0, A, B, A2 = 0, 4, 12, 20
    PA = "Dm | Dm | Gm | A7 | Dm | Bb | Em7b5 | A7"
    PB = "Bbmaj7 | Bbmaj7 | Gm7 | Gm7 | Ebmaj7 | Ebmaj7 | A7sus4 | A7b9"
    chA, chB, chA2 = prog(PA, A), prog(PB, B), prog(PA, A2)

    MEL_A = ("A4/e r/e D5/e r/e E5/s F5/s E5/e D5/e r/e | C#5/e r/e D5/e r/e A4/q r/q | "
             "Bb4/e r/e D5/e r/e Eb5/s F5/s Eb5/e D5/e r/e | C#5/e r/e E5/e r/e A4/q r/q | "
             "A4/e r/e D5/e r/e E5/s F5/s G5/e A5/e r/e | Bb5/e r/e A5/e r/e G5/s A5/s G5/e F5/e r/e | "
             "E5/e r/e G5/e r/e Bb5/s A5/s G5/e E5/e r/e | F5/e E5/e D5/e C#5/e E5/q r/q |")
    MEL_A2_END = "F5/e E5/e D5/e C#5/e A4/q r/q |"
    MEL_B = ("D6/q. C6/e Bb5/q A5/q | F5/h. r/q | Bb5/q. A5/e G5/q F5/q | D5/h. r/q | "
             "G5/q. F5/e Eb5/q D5/q | Bb4/h C5/q D5/q | E5/q. D5/e E5/q A5/q | G5/q F5/q E5/q C#5/q |")
    CLAR_A2 = ("D4/h. F4/q | E4/h F4/h | D4/h Bb3/h | C#4/h E4/h | F4/h. A4/q | G4/h F4/h | "
               "E4/h D4/q Bb3/q | A3/h C#4/h |")
    BASS_A = ("D2/q A1/q D2/q C#2/q | D2/q A1/q D2/q F2/q | G1/q D2/q G2/q Bb1/q | A1/q E2/q A2/q C#2/q | "
              "D2/q A1/q D2/q C2/q | Bb1/q F2/q Bb2/q F2/q | E2/q Bb1/q E2/q G2/q | A1/q E2/q A1/q C#2/q |")
    BASS_B = ("Bb1/h F2/h | Bb1/h D2/h | G1/h D2/h | G1/h Bb1/h | Eb2/h Bb1/h | Eb2/h G2/h | "
              "A1/h E2/h | A1/h C#2/h |")

    lead = S.track("pizz_lead", "pizz", "lead", pan=-0.12, send=0.22, bright=0.6, gate=0.8)
    lead.add(seq(MEL_A, A, 0.8))
    lead.add(seq(MEL_A.rsplit("|", 2)[0] + "| " + MEL_A2_END, A2, 0.85))

    cel = S.track("cel_lead", "celesta", "lead", pan=0.18, send=0.35)
    cel.add(seq(MEL_B, B, 0.85))
    cel.add(shift(seq(MEL_A.rsplit("|", 2)[0] + "| " + MEL_A2_END, A2, 0.42), 12))

    clar = S.track("clar", "clarinet", "lead2", pan=-0.22, send=0.22, legato=True, bright=0.45)
    clar.add(shift(seq(MEL_B, B, 0.7), -12))
    clar.add(seq(CLAR_A2, A2, 0.62))

    harp = S.track("harp", "harp", "accomp", pan=0.3, send=0.3)
    harp.add(seq("D3/e F3/e A3/e C4/e D4/e F4/e A4/e C5/e | D3/e F3/e A3/e B3/e D4/e F4/e A4/e B4/e |", I0 + 2, 0.55))
    harp.add(gen_arp(chB, [0, 1, 2, 3, 4, 3, 2, 1], 0.5, 50, 74, 0.5))

    acc = S.track("pizz_acc", "pizz", "accomp", pan=0.25, send=0.18, gate=0.45, bright=0.4, voices=1)
    acc.add(gen_offbeat(chA, 55, 69, 0.38, positions=(1.5, 3.5)))
    acc.add(gen_offbeat(chA2, 55, 69, 0.42, positions=(0.5, 1.5, 2.5, 3.5)))

    bass = S.track("bass", "pizz_bass", "bass", pan=0.0, send=0.06, gate=0.55)
    bass.add(seq("D2/e r/e r/q A1/e r/e r/q | " * 4, I0, 0.75))
    bass.add(seq(BASS_A, A, 0.8))
    bass.add(seq(BASS_B, B, 0.75, gate=0.9))
    bass.add(seq(BASS_A, A2, 0.82))

    ch = S.track("choir", "choir", "pad", send=0.35, attack=0.9, release=1.3)
    for k, v in enumerate([(50, 53, 57, 62), (50, 53, 57, 61), (50, 53, 57, 60), (50, 53, 57, 59)]):
        ch.add([Ev((I0 + k) * 4, 4, v, 0.7, dict(vowel="u"))])
    ch.add(gen_pad(chA, 50, 65, 0.5, vowel="o"))
    ch.add(gen_pad(chB, 50, 69, 0.75, vowel="a", attack=0.6))
    ch.add(gen_pad(chA2, 50, 65, 0.58, vowel="u"))

    kick = S.track("kick", "kick", "drums", send=0.05, human_ms=2, gain_db=-3)
    hat = S.track("hat", "hat", "drums", pan=0.3, send=0.1, human_ms=3, gain_db=-7)
    frame = S.track("frame", "frame_drum", "drums", pan=-0.1, send=0.15, human_ms=2, gain_db=-3)
    wbh = S.track("wb_hi", "woodblock", "drums", pan=-0.35, send=0.2, human_ms=2, gain_db=-5)
    wbl = S.track("wb_lo", "woodblock", "drums", pan=-0.3, send=0.2, human_ms=2, gain_db=-5)
    shk = S.track("shaker", "shaker", "drums", pan=0.35, send=0.1, human_ms=3, gain_db=-10)
    # the parlour clock
    wbh.add(drums("x.......x.......", range(I0, I0 + 4), 84, 0.6))
    wbl.add(drums("....x.......x...", range(I0, I0 + 4), 79, 0.6))
    kick.add(drums("x...............", [2, 3], vel=0.6))
    # A
    kick.add(drums("x.......x.......", range(A, A + 8), vel=0.8))
    hat.add(drums("o.x.o.x.o.x.o.x.", range(A, A + 8)))
    frame.add(drums("....x.......x...", range(A, A + 7), vel=0.7, slap=0.5))
    frame.add(drums("....x.......xxxx", [A + 7], vel=0.7, slap=0.5))
    wbh.add(drums("..............x.", range(A, A + 8), 84, 0.7))
    # B
    kick.add(drums("x...............", range(B, B + 8), vel=0.7))
    frame.add(drums("x.........x.....", range(B, B + 7), vel=0.6, slap=0.2, f0=95.0))
    frame.add(drums("x.......x.x.xxxx", [B + 7], vel=0.65, slap=0.3))
    shk.add(drums("o.x.o.x.o.x.o.x.", range(B, B + 8)))
    # A2
    kick.add(drums("x.......x.....x.", range(A2, A2 + 8), vel=0.8))
    hat.add(drums("o.x.o.x.o.x.o.x.", range(A2, A2 + 8)))
    frame.add(drums("....x.......x...", range(A2, A2 + 7), vel=0.72, slap=0.5))
    frame.add(drums("....x.......x.xx", [A2 + 7], vel=0.72, slap=0.5))
    wbh.add(drums("..x.......x.....", range(A2, A2 + 8), 84, 0.6))
    wbl.add(drums(".............x..", range(A2, A2 + 8), 79, 0.6))
    shk.add(drums("gogogogogogogogo", range(A2, A2 + 8)))

    sp = S.track("sparkle", "celesta", "sparkle", pan=0.35, send=0.5)
    sp.add(seq("r/w | r/q. A5/s D6/s F6/e r/e r/q | r/w | r/h D6/s F6/s A6/s B6/s A6/q |", I0, 0.6))
    gl = S.track("glock", "glock", "sparkle", pan=0.4, send=0.5)
    gl.add(seq("r/h. F6/s A6/s Bb6/s D7/s |", A + 7, 0.5))
    gl.add(seq("r/h. A6/s C#7/s E7/s G7/s |", B + 7, 0.5))
    gl.add(seq("r/h. D6/s F6/s A6/s D7/s |", A2 + 7, 0.45))
    return S


# ---------------------------------------------------------------------------- shared helpers
def wind_raw(seed, level=1.0, fin=0.0, fout=0.0, center=550.0):
    def fn(N, loop):
        a = I.wind_bed(N, rng_for("wind", seed, 0), loop, center)
        b = I.wind_bed(N, rng_for("wind", seed, 1), loop, center)
        y = np.stack([a, b], axis=1) * level
        if not loop and (fin or fout):
            y = fade(y, fin, fout)
        return y
    return fn


def std_kit(S, send_scale=1.0):
    """Common percussion tracks (group 'drums')."""
    k = dict(
        kick=S.track("kick", "kick", "drums", send=0.05 * send_scale, human_ms=2, gain_db=-3),
        hat=S.track("hat", "hat", "drums", pan=0.3, send=0.1 * send_scale, human_ms=3, gain_db=-8),
        frame=S.track("frame", "frame_drum", "drums", pan=-0.1, send=0.15 * send_scale, human_ms=2, gain_db=-3),
        wbh=S.track("wb_hi", "woodblock", "drums", pan=-0.35, send=0.2 * send_scale, human_ms=2, gain_db=-6),
        wbl=S.track("wb_lo", "woodblock", "drums", pan=-0.3, send=0.2 * send_scale, human_ms=2, gain_db=-6),
        shk=S.track("shaker", "shaker", "drums", pan=0.35, send=0.1 * send_scale, human_ms=3, gain_db=-11),
    )
    return k


# ---------------------------------------------------------------------------- gravewood
def song_gravewood():
    """'Gravewood Skirmish' - A minor, 120 BPM, 44 bars. Bouncy dotted pizzicato theme over a
    clip-clop woodblock groove; clarinet counter-lines; lyrical B; creeping Phrygian breakdown
    that builds back into the theme."""
    S = Song("gravewood", bpm=120, bars=44, loop=True, lufs=-17.0,
             reverb=dict(t60=1.8, predelay=0.018, seed=21),
             groups=dict(lead=0, lead2=-3, accomp=-8, bass=-4, pad=-9, drums=-5, sparkle=-11))
    S.volume = 0.7
    I0, A, A2, B, C, A3 = 0, 4, 12, 20, 28, 36
    PA = "Am | F | Dm | E | Am | F | Bb | E7"
    PB = "F | G | C | Am | Dm | Bb | E | E7"
    PC = "Am | Bb | Am | Bb | Am | Bb | E | E7"
    chI = prog("Am | Am | Am | E7", I0)
    chA, chA2, chB, chC, chA3 = prog(PA, A), prog(PA, A2), prog(PB, B), prog(PC, C), prog(PA, A3)
    MEL = ("A4/e. B4/s C5/e A4/e E5/q D5/e C5/e | B4/e C5/e A4/q r/e F4/e A4/e C5/e | "
           "D5/e. E5/s F5/e D5/e A5/q G5/e F5/e | E5/e F5/e E5/e D5/e C5/e B4/e G#4/q | "
           "A4/e. B4/s C5/e A4/e E5/q D5/e C5/e | F5/e. E5/s D5/e C5/e A5/q G5/e F5/e | "
           "D5/e. C5/s Bb4/e D5/e F5/q E5/e D5/e | E5/e r/e B4/e r/e G#4/e r/e E4/e r/e |")
    CTR = "E4/h C4/h | C4/h A3/h | D4/h F4/h | E4/h. G#3/q | A3/h C4/h | A3/h C4/h | D4/h F4/h | E4/w |"
    MEL_B = ("A4/q. G4/e F4/q C5/q | B4/h. D5/q | C5/q. B4/e G4/q E4/q | A4/w | "
             "F4/q. E4/e D4/q A4/q | Bb4/h. D5/q | G#4/q. A4/e B4/q D5/q | E5/h B4/h |")
    GL_C = "A5/e. B5/s C6/e A5/e E6/q r/q | r/w | C6/e. D6/s E6/e C6/e A6/q r/q | r/w |"
    CL_C = "r/w | D4/e r/e F4/e r/e E4/e D4/e Bb3/q | r/w | F4/e r/e D4/e r/e Bb3/e A3/e G3/q |"

    lead = S.track("pizz_lead", "pizz", "lead", pan=-0.1, send=0.2, bright=0.65, gate=0.75)
    lead.add(seq(MEL, A, 0.82))
    lead.add(seq(MEL, A2, 0.8))
    lead.add(seq(MEL, A3, 0.88))
    harpl = S.track("harp_lead", "harp", "lead", pan=0.2, send=0.25, ring=False)
    harpl.add(seq(MEL, A3, 0.55, transpose=-12))
    cel = S.track("cel", "celesta", "lead", pan=0.25, send=0.35)
    cel.add(seq(MEL, A2, 0.45, transpose=12))
    cel.add(seq(MEL_B, B, 0.3, transpose=12))
    cel.add(seq(MEL, A3, 0.5, transpose=12))

    clar = S.track("clar", "clarinet", "lead2", pan=-0.25, send=0.22, bright=0.5)
    clar.add(seq(CTR, A2, 0.6, legato=True))
    clar.add(seq(MEL_B, B, 0.8, legato=True, vib=6.0))
    clar.add(seq(CL_C, C, 0.72))
    clar.add(seq(CTR, A3, 0.62, legato=True))

    acc = S.track("pizz_acc", "pizz", "accomp", pan=0.28, send=0.15, gate=0.4, bright=0.45, voices=1)
    acc.add(gen_offbeat(chI + chA, 57, 72, 0.4))
    acc.add(gen_offbeat(chA3, 57, 72, 0.45))
    harp = S.track("harp", "harp", "accomp", pan=0.32, send=0.3)
    harp.add(gen_arp(chA2, [0, 2, 1, 2], 0.5, 57, 76, 0.45))
    harp.add(gen_arp(chB, [0, 1, 2, 3, 4, 3, 2, 1], 0.5, 52, 76, 0.5))
    harp.add(seq("E3/s G#3/s B3/s E4/s G#4/s B4/s E5/s G#5/s B5/q r/q |", C + 6, 0.55))
    harp.add(gen_arp(chA3, [0, 2, 1, 2], 0.5, 57, 76, 0.42))
    spic = S.track("pizz_16", "pizz", "accomp", pan=-0.3, send=0.15, gate=0.5, bright=0.5, voices=2)
    spic.add(ramp(gen_arp(chC[4:], [0, 0, 1, 2], 0.25, 57, 76, 0.5), 0.5, 1.0))

    bass = S.track("bass", "pizz_bass", "bass", send=0.05, gate=0.6)
    groove = ["R", ".", ".", "R", "R", ".", "5", "8"]
    bass.add(gen_bass(chI + chA + chA2, groove, 33, 0.8))
    bass.add(gen_bass(chB, ["R", ".", ".", ".", "5", ".", "R", "."], 33, 0.78, gate=0.9))
    bass.add(gen_bass(chC[:4], ["R", ".", "R", ".", "R", "R", ".", "5"], 33, 0.78))
    bass.add(ramp(gen_bass(chC[4:], ["R"] * 8, 33, 0.75), 0.7, 1.0))
    bass.add(gen_bass(chA3, groove, 33, 0.85))

    ch = S.track("choir", "choir", "pad", send=0.35, attack=0.7, release=1.1)
    ch.add(gen_pad(chI, 52, 67, 0.45, vowel="u"))
    ch.add(gen_pad(chA, 52, 67, 0.5, vowel="o"))
    ch.add(gen_pad(chA2, 52, 69, 0.6, vowel="a"))
    ch.add(gen_pad(chB, 52, 69, 0.7, vowel="a"))
    ch.add(gen_pad(chC[:4], 50, 65, 0.45, vowel="u"))
    ch.add(ramp(gen_pad(chC[4:], 52, 69, 0.6, vowel=("u", "a")), 0.6, 1.0))
    ch.add(gen_pad(chA3, 52, 69, 0.65, vowel="a"))

    k = std_kit(S)
    groove_bars = list(range(I0, I0 + 4)) + list(range(A, A + 8)) + list(range(A2, A2 + 8))
    k["kick"].add(drums("x.....x.x.......", groove_bars, vel=0.8))
    k["hat"].add(drums("o.x.o.x.o.x.o.x.", groove_bars))
    k["wbh"].add(drums("..x.......x.....", groove_bars, 84, 0.7))
    k["wbl"].add(drums(".....x.......x..", groove_bars, 79, 0.7))
    for b in groove_bars:
        fill = b in (I0 + 3, A + 7, A2 + 7)
        k["frame"].add(drums("....X.......xxxx" if fill else "....X.......X...", [b], vel=0.75, slap=0.5))
    k["shk"].add(drums("gogogogogogogogo", range(A2, A2 + 8)))
    # B: lighter
    k["kick"].add(drums("x.......x.......", range(B, B + 8), vel=0.7))
    k["hat"].add(drums("o...x...o...x...", range(B, B + 8)))
    k["frame"].add(drums("....x.......x...", range(B, B + 7), vel=0.6, slap=0.35))
    k["frame"].add(drums("....x...x.x.xxxx", [B + 7], vel=0.65, slap=0.45))
    # C: creeping clock, then build
    k["kick"].add(drums("x...............", range(C, C + 4), vel=0.7))
    k["wbh"].add(drums("x.......x.......", range(C, C + 4), 84, 0.55))
    k["wbl"].add(drums("....x.......x...", range(C, C + 4), 79, 0.55))
    tom = S.track("tom", "tom", "drums", pan=0.05, send=0.15, human_ms=2, gain_db=-2)
    tom.add(ramp(drums("x.......x.......", [C + 4], 45, 0.7) + drums("x...x...x...x...", [C + 5], 45, 0.7)
                 + drums("x.x.x.x.x.x.x.x.", [C + 6], 45, 0.7) + drums("xxxxxxxxxxxxxxxx", [C + 7], 45, 0.7),
                 0.55, 1.0))
    k["kick"].add(drums("x...............", range(C + 4, C + 8), vel=0.8))
    cym = S.track("cym", "cymbal", "drums", pan=0.2, send=0.3, gain_db=-8)
    cym.add([Ev((C + 7) * 4, 4, 0, 0.8, dict(swell=True))])
    # A3: full
    k["kick"].add(drums("x.....x.x.....x.", range(A3, A3 + 8), vel=0.85))
    k["hat"].add(drums("o.x.o.x.o.x.o.x.", range(A3, A3 + 8)))
    k["shk"].add(drums("gogogogogogogogo", range(A3, A3 + 8)))
    k["wbh"].add(drums("..x.......x.....", range(A3, A3 + 8), 84, 0.7))
    k["wbl"].add(drums(".....x.......x..", range(A3, A3 + 8), 79, 0.7))
    for b in range(A3, A3 + 8):
        k["frame"].add(drums("....X.......xxxx" if b == A3 + 7 else "....X.......X...", [b], vel=0.8, slap=0.5))

    gl = S.track("glock", "glock", "sparkle", pan=0.4, send=0.45)
    gl.add(seq(GL_C, C, 0.6))
    gl.add(seq("r/h. E6/s A6/s C7/s E7/s |", A + 7, 0.45))
    gl.add(seq("r/h. F6/s A6/s C7/s F7/s |", A2 + 7, 0.45))
    gl.add(seq("r/h. E6/s G#6/s B6/s E7/s |", A3 + 7, 0.45))
    return S


# ---------------------------------------------------------------------------- moonfall
def song_moonfall():
    """'Moonfall Siege' - C minor, 126 BPM, 44 bars. Tolling bells, a low chant (choir doubled
    by the clarinet), restless 16th-note pizzicato 'rain', distant thunder and wind."""
    S = Song("moonfall", bpm=126, bars=44, loop=True, lufs=-17.0,
             reverb=dict(t60=2.6, predelay=0.028, seed=31),
             groups=dict(lead=0, lead2=-3, accomp=-8, bass=-4, pad=-8, drums=-5, bells=-6,
                         wind=-19, thunder=-9, sparkle=-12))
    S.volume = 0.7
    I0, A, A2, B, C, A3 = 0, 4, 12, 20, 28, 36
    PA = "Cm | Cm | Ab | Bb | Fm | Db | Gsus4 G | G7b9"
    PB = "Eb | Bb/D | Cm | Ab | Fm | Bb | G | G7"
    PC = "Cm | Db | Cm | Db | Bbm | Cm | Db | G7"
    chI = prog("Cm | Cm | Db/C | Cm", I0)
    chA, chA2, chB, chC, chA3 = prog(PA, A), prog(PA, A2), prog(PB, B), prog(PC, C), prog(PA, A3)
    CHANT = ("C4/q. D4/e Eb4/q D4/q | C4/h G3/h | Ab3/q. Bb3/e C4/q Eb4/q | D4/h. r/q | "
             "F4/q. G4/e Ab4/q G4/q | F4/q Eb4/q Db4/q C4/q | C4/h B3/h | B3/q D4/q F4/q Ab4/q |")
    CTR = "G3/w | Eb4/h G4/h | C4/w | D4/h F4/h | Ab3/w | F3/h Ab3/h | G3/w | F4/h D4/h |"
    MEL_B = ("G5/q. F5/e Eb5/q Bb4/q | F5/h D5/h | Eb5/q. D5/e C5/q G4/q | Ab4/h C5/h | "
             "F5/q. Eb5/e D5/q C5/q | D5/h F5/h | G5/q. F5/e Eb5/q D5/q | B4/h D5/q F5/q |")
    CALL = "G3/w | Ab3/w | G3/w | Ab3/h F3/h | Bb3/w | C4/w | Db4/w | D4/h B3/h |"

    chant = S.track("chant", "choir", "lead", send=0.3, attack=0.07, release=0.45, voices=3,
                    vowel="a", voice="bass", detune=6.0, width=0.5)
    chant.add(seq(CHANT, A, 0.85))
    chant.add(seq(CALL, C, 0.9))
    chant.add(seq(CHANT, A3, 0.9))
    clar_l = S.track("clar_lead", "clarinet", "lead", pan=-0.15, send=0.25, bright=0.5)
    clar_l.add(seq(CHANT, A, 0.75, legato=True))
    clar_l.add(seq(CHANT, A3, 0.78, legato=True))
    cel = S.track("cel", "celesta", "lead", pan=0.2, send=0.4)
    cel.add(seq(CHANT, A2, 0.8, transpose=12))
    cel.add(seq(CHANT, A3, 0.4, transpose=24))
    harpl = S.track("harp_lead", "harp", "lead", pan=0.15, send=0.3, bright=0.55)
    harpl.add(seq(MEL_B, B, 0.85))
    tub = S.track("tub", "tubular", "lead", pan=0.25, send=0.45, tau=1.8)
    tub.add(seq(CHANT, A2, 0.35, transpose=12))

    clar = S.track("clar", "clarinet", "lead2", pan=-0.25, send=0.25, bright=0.45)
    clar.add(seq(CTR, A2, 0.62, legato=True))
    clar.add(seq(MEL_B, B, 0.62, transpose=-12, legato=True, vib=5.0))

    rain = S.track("pizz_rain", "pizz", "accomp", pan=0.25, send=0.25, gate=0.5, bright=0.45, voices=1)
    pat = [0, 1, 2, 3, 2, 1, 2, 1]
    rain.add(gen_arp(chI, pat, 0.25, 67, 84, 0.3, accent=0.15))
    rain.add(gen_arp(chA + chA2, pat, 0.25, 67, 84, 0.36, accent=0.15))
    rain.add(gen_arp(chB, [0, 1, 2, 1], 0.25, 67, 84, 0.3, accent=0.12))
    rain.add(ramp(gen_arp(chC, [0, 0, 1, 1, 2, 2, 1, 1], 0.25, 60, 79, 0.45, accent=0.15), 0.6, 1.0))
    rain.add(gen_arp(chA3, pat, 0.25, 67, 84, 0.4, accent=0.15))
    harp = S.track("harp", "harp", "accomp", pan=-0.3, send=0.3)
    harp.add(gen_arp(chA2, [0, 1, 2, 3], 1.0, 48, 67, 0.45))

    bass = S.track("bass", "pizz_bass", "bass", send=0.05, gate=0.55, t60=1.1)
    bass.add(gen_bass(chI, ["R", ".", ".", ".", "R", ".", "R", "."], 36, 0.75))
    bass.add(gen_bass(chA + chA2, ["R", "R", "R", "R", "R", "R", "5", "R"], 36, 0.72))
    bass.add(gen_bass(chB, ["R", ".", "R", ".", "5", ".", "R", "."], 36, 0.74, gate=0.8))
    bass.add(ramp(gen_bass(chC, ["R", "R", "R", "R", "R", "R", "R", "R"], 36, 0.72), 0.75, 1.0))
    bass.add(gen_bass(chA3, ["R", "R", "R", "R", "R", "R", "5", "R"], 36, 0.8))

    pad = S.track("choir_pad", "choir", "pad", send=0.4, attack=1.0, release=1.4)
    pad.add(gen_pad(chI, 48, 63, 0.55, vowel="u"))
    pad.add(gen_pad(chA, 48, 63, 0.45, vowel="u"))
    pad.add(gen_pad(chA2, 50, 67, 0.6, vowel="o"))
    pad.add(gen_pad(chB, 50, 67, 0.7, vowel="a"))
    pad.add(ramp(gen_pad(chC, 48, 65, 0.6, vowel=("u", "a")), 0.6, 1.0))
    pad.add(gen_pad(chA3, 48, 65, 0.55, vowel="o"))

    k = std_kit(S)
    low = S.track("low_drum", "frame_drum", "drums", pan=0.0, send=0.2, human_ms=2, gain_db=0)
    rimt = S.track("rim", "rim", "drums", pan=-0.25, send=0.2, human_ms=2, gain_db=-7)
    full = list(range(A, A + 8)) + list(range(A2, A2 + 8)) + list(range(A3, A3 + 8))
    low.add(drums("X.....x.........", range(I0, I0 + 4), vel=0.7, f0=78.0, slap=0.15, tau=0.5))
    low.add(drums("X..x..x...x..x..", full, vel=0.75, f0=82.0, slap=0.2, tau=0.4))
    k["kick"].add(drums("x.......x.......", full, vel=0.75))
    k["hat"].add(drums("o.x.o.x.o.x.o.x.", full, vel=0.8))
    rimt.add(drums("....x.......x...", full, vel=0.7))
    k["shk"].add(drums("gogogogogogogogo", range(A3, A3 + 8)))
    for b in (A + 7, A2 + 7, A3 + 7):
        k["frame"].add(drums("........x.x.xxxx", [b], vel=0.7, slap=0.5))
    # B: half-time
    low.add(drums("X.......x.......", range(B, B + 8), vel=0.65, f0=82.0, slap=0.2, tau=0.45))
    rimt.add(drums("........x.......", range(B, B + 8), vel=0.6))
    k["hat"].add(drums("o...x...o...x...", range(B, B + 8), vel=0.7))
    # C: storm build
    tom = S.track("tom", "tom", "drums", pan=0.05, send=0.2, human_ms=2, gain_db=-1)
    tom.add(ramp(drums("x.....x.....x...", range(C, C + 4), 43, 0.7) + drums("x..x..x.x..x..x.", [C + 4, C + 5], 43, 0.7)
                 + drums("x.x.x.x.x.x.x.x.", [C + 6], 45, 0.7) + drums("xxxxxxxxxxxxxxxx", [C + 7], 47, 0.7), 0.55, 1.0))
    k["kick"].add(drums("x.......x.......", range(C, C + 8), vel=0.75))
    cym = S.track("cym", "cymbal", "drums", pan=0.2, send=0.35, gain_db=-9)
    cym.add([Ev((C + 7) * 4, 4, 0, 0.8, dict(swell=True)), Ev((I0 + 3) * 4, 4, 0, 0.6, dict(swell=True))])

    bell = S.track("bell", "church_bell", "bells", pan=0.1, send=0.45, tau=3.2)
    for b, note in [(I0, "C4"), (I0 + 2, "C4"), (A, "C4"), (A + 4, "F4"), (A2, "C4"), (A2 + 4, "F4"),
                    (B, "Eb4"), (C, "C4"), (C + 2, "C4"), (C + 4, "Bb3"), (C + 6, "Db4"), (A3, "C4"), (A3 + 4, "F4")]:
        bell.add([Ev(b * 4, 2, note_midi(note), 0.85)])

    thun = S.track("thunder", "thunder", "thunder", send=0.3, human_ms=0)
    thun.add([Ev(I0 * 4 + 0.5, 1, 0, 0.9, dict(length=5.0, crack=0.25)),
              Ev(C * 4, 1, 0, 1.0, dict(length=5.5, crack=0.4)),
              Ev((C + 4) * 4 + 2, 1, 0, 0.8, dict(length=4.5, crack=0.2))])
    S.raws.append(("wind", 0.4, wind_raw("moonfall", 1.0)))

    gl = S.track("glock", "glock", "sparkle", pan=0.4, send=0.5)
    gl.add(seq("r/h. G6/s C7/s Eb7/s G7/s |", A2 - 1, 0.45))
    gl.add(seq("r/h. Bb6/s Eb7/s G7/s Bb7/s |", B - 1, 0.4))
    gl.add(seq("r/h. G6/s B6/s D7/s F7/s |", A3 - 1, 0.45))
    return S


# ---------------------------------------------------------------------------- boss
def song_boss():
    """'The Golden Collar Falls' - E Phrygian-dominant colour, 144 BPM, 48 bars. Taiko and toms,
    a galloping plucked bass, a brass horn theme, choir stabs and tubular bells."""
    S = Song("boss", bpm=144, bars=48, loop=True, lufs=-16.5,
             reverb=dict(t60=1.7, predelay=0.02, seed=41),
             groups=dict(lead=0, lead2=-3, accomp=-8, bass=-3, pad=-7, drums=-3, bells=-8, sparkle=-12))
    S.volume = 0.7
    I0, A, A2, B, C, A3, O = 0, 4, 12, 20, 28, 36, 44
    PA = "Em | C | D | Em | Em | C | F | B7"
    PB = "Am | Em | F | B7 | Am | C | F | B7"
    PC = "Em | F | Em | F | Em | F | G | B7"
    chI = prog("Em | Em | F/E | Em", I0)
    chA, chA2, chB, chC, chA3 = prog(PA, A), prog(PA, A2), prog(PB, B), prog(PC, C), prog(PA, A3)
    chO = prog("Em | F | Em | B7", O)
    HORN = ("E4/h. B3/q | C4/q. D4/e E4/q G4/q | F#4/h. D4/q | E4/w | "
            "E4/q. F4/e G4/q B4/q | C5/h. B4/q | A4/q. G4/e F4/q E4/q | D#4/h F#4/h |")
    CH_B = "A4/h C5/h | B4/w | A4/h F4/h | F#4/h D#4/h | E5/h C5/h | G5/h E5/h | F5/h. E5/q | D#5/h F#5/h |"
    BR_B = "A3/w | G3/w | F3/w | F#3/w | A3/w | G3/w | A3/w | B3/w |"
    FRAG = "E4/q. F4/e E4/h | r/w | G4/q. A4/e G4/h | r/w | E4/q. F4/e G4/q B4/q | C5/h A4/h | B4/h D5/h | D#5/h B4/h |"

    horn = S.track("horn", "brass", "lead", pan=-0.05, send=0.25, bright=0.9)
    horn.add(seq(HORN, A, 0.8))
    horn.add(seq(HORN, A2, 0.85))
    horn.add(seq(FRAG, C, 0.8))
    horn.add(seq(HORN, A3, 0.95))
    horn2 = S.track("horn_hi", "brass", "lead", pan=0.1, send=0.25, bright=0.6)
    horn2.add(seq(HORN, A3, 0.55, transpose=12))
    chl = S.track("choir_lead", "choir", "lead", send=0.3, attack=0.12, release=0.6, voices=2, vowel="a")
    chl.add(seq(HORN, A2, 0.6))
    chl.add(seq(CH_B, B, 0.9))
    chl.add(seq(HORN, A3, 0.65, transpose=12))

    br2 = S.track("horn_low", "brass", "lead2", pan=-0.2, send=0.2, bright=0.4)
    br2.add(seq(BR_B, B, 0.7))

    spic = S.track("pizz_spic", "pizz", "accomp", pan=0.28, send=0.15, gate=0.45, bright=0.55, voices=2)
    spic.add(gen_arp(chA + chA2, [0, 2, 1, 2], 0.5, 64, 79, 0.5))
    spic.add(gen_arp(chB, [0, 1, 2, 1], 0.5, 60, 76, 0.4))
    spic.add(ramp(gen_arp(chC[4:], [0, 0, 1, 2], 0.25, 64, 81, 0.5), 0.5, 1.0))
    spic.add(gen_arp(chA3, [0, 2, 1, 2, 3, 2, 1, 2], 0.25, 64, 83, 0.42))
    harp = S.track("harp", "harp", "accomp", pan=-0.3, send=0.3)
    harp.add(gen_arp(chB, [0, 1, 2, 3, 4, 3, 2, 1], 0.5, 52, 76, 0.5))
    harp.add(seq("E3/s G3/s B3/s E4/s G4/s B4/s E5/s G5/s B5/q r/q |", A - 1, 0.5))

    bass = S.track("bass", "pluck_bass", "bass", send=0.04, human_ms=2, gate=0.85)
    gal = ["R", ".", "R", "R"] * 3 + ["8", ".", "5", "R"]
    bass.add(gen_bass(chI + chA + chA2, gal, 35, 0.8, step=0.25))
    bass.add(gen_bass(chB, ["R", ".", ".", ".", ".", ".", "R", "R"], 35, 0.8, step=0.5, gate=0.9))
    bass.add(gen_bass(chC, gal, 35, 0.8, step=0.25))
    bass.add(gen_bass(chA3 + chO, gal, 35, 0.85, step=0.25))
    pb = S.track("bass_pizz", "pizz_bass", "bass", send=0.05, gain_db=-4, gate=0.7)
    pb.add(gen_bass(chA + chA2 + chA3, ["R", ".", ".", ".", "R", ".", ".", "."], 28, 0.8))
    pb.add(gen_bass(chB, ["R", ".", ".", ".", ".", ".", ".", "."], 28, 0.8, ring=True))

    pad = S.track("choir_pad", "choir", "pad", send=0.35, attack=0.6, release=1.0)
    pad.add(gen_pad(chI, 52, 67, 0.5, vowel="u"))
    pad.add(gen_pad(chA, 52, 67, 0.5, vowel="o"))
    pad.add(gen_pad(chB, 50, 67, 0.6, vowel="o"))
    pad.add(ramp(gen_pad(chC, 52, 69, 0.55, vowel=("u", "a")), 0.6, 1.0))
    pad.add(gen_pad(chO, 52, 67, 0.55, vowel="u"))
    stab = S.track("choir_stab", "choir", "pad", send=0.35, attack=0.025, release=0.35, vowel="a", gain_db=2)
    for c in chA2 + chA3:
        stab.add([Ev(c[0], 0.6, voicing(c[2], 55, 72), 0.85)])
    for c in chI:
        stab.add([Ev(c[0] + 3.5, 0.4, voicing(c[2], 55, 72), 0.6)])

    taiko = S.track("taiko", "taiko", "drums", send=0.2, human_ms=2, gain_db=0)
    kick = S.track("kick", "kick", "drums", send=0.04, human_ms=1.5, gain_db=-5)
    sn = S.track("snare", "snare", "drums", pan=0.05, send=0.15, human_ms=2, gain_db=-4)
    hat = S.track("hat", "hat", "drums", pan=0.3, send=0.08, human_ms=2, gain_db=-9, brush=False)
    tom = S.track("tom", "tom", "drums", pan=-0.15, send=0.15, human_ms=2, gain_db=-3)
    cym = S.track("cym", "cymbal", "drums", pan=0.2, send=0.3, gain_db=-9)
    drive = list(range(A, A + 8)) + list(range(A2, A2 + 8)) + list(range(A3, A3 + 8))
    taiko.add(drums("X.......x.......", range(I0, I0 + 4), vel=0.85))
    tom.add(drums("..........x.x.xx", [I0 + 3], 45, 0.7))
    for b in drive:
        end = (b + 1 - A) % 8 == 0
        taiko.add(drums("X.......x.....x." if not end else "X.......x.x.x.xx", [b], vel=0.85))
        tom.add(drums("......x.......x." if not end else "......x...xxxxxx", [b], 50 if b % 2 else 45, 0.7))
    kick.add(drums("x.....x...x.....", drive, vel=0.8))
    sn.add(drums("....x.......x...", drive, vel=0.75))
    hat.add(drums("x.x.x.x.x.x.x.x.", list(range(A, A + 8)) + list(range(A2, A2 + 8)), vel=0.7))
    hat.add(drums("xoxoxoxoxoxoxoxo", range(A3, A3 + 8), vel=0.7))
    # B half-time
    taiko.add(drums("X...............", range(B, B + 8), vel=0.8))
    sn.add(drums("........x.......", range(B, B + 8), vel=0.7))
    hat.add(drums("x...x...x...x...", range(B, B + 8), vel=0.6))
    tom.add(drums("..........x.xxxx", [B + 7], 47, 0.75))
    # C taiko feature + build
    taiko.add(drums("X..x..x.X..x..x.", range(C, C + 4), vel=0.85))
    taiko.add(ramp(drums("X..x..x.x.x.x.x.", range(C + 4, C + 8), vel=0.8), 0.7, 1.0))
    sn.add(ramp(drums("xxxxxxxxxxxxxxxx", [C + 7], vel=0.6), 0.4, 1.0))
    kick.add(drums("x.......x.......", range(C, C + 8), vel=0.75))
    # outro/turnaround
    taiko.add(drums("X.......x..x..x.", range(O, O + 3), vel=0.85))
    tom.add(ramp(drums("x.x.x.x.xxxxxxxx", [O + 3], 45, 0.8), 0.6, 1.0))
    kick.add(drums("x.....x...x.....", range(O, O + 4), vel=0.8))
    hat.add(drums("x.x.x.x.x.x.x.x.", range(O, O + 4), vel=0.65))
    cym.add([Ev((A - 1) * 4, 4, 0, 0.8, dict(swell=True)), Ev((A3 - 1) * 4, 4, 0, 0.9, dict(swell=True)),
             Ev((C - 1) * 4 + 2, 2, 0, 0.6, dict(swell=True))])

    bells = S.track("tubular", "tubular", "bells", pan=0.2, send=0.4, tau=2.0)
    for b in list(range(C, C + 8)):
        c = chC[b - C][2]
        bells.add([Ev(b * 4, 2, bass_pitch(c, 64), 0.8)])
    for b in (A, A2, A3):
        bells.add([Ev(b * 4, 2, note_midi("E5"), 0.8), Ev(b * 4 + 0.02, 2, note_midi("B4"), 0.6)])
    gl = S.track("glock", "celesta", "sparkle", pan=0.4, send=0.45)
    gl.add(seq("r/h. E6/s G6/s B6/s E7/s |", A2 - 1, 0.45))
    gl.add(seq("r/h. A6/s C7/s E7/s A7/s |", B - 1, 0.45))
    return S


# ---------------------------------------------------------------------------- jingles & story
def song_victory():
    """Victory jingle (~7.5 s): a villainous 'ta-da' in D major with a bVI-bVII-I swagger."""
    S = Song("victory", bpm=120, bars=3, loop=False, tail=1.6, lufs=-16.0, fade_out=0.6,
             reverb=dict(t60=2.0, predelay=0.02, seed=51),
             groups=dict(lead=0, pad=-6, accomp=-7, bass=-5, drums=-5, sparkle=-9))
    LEAD = "D4/s F#4/s A4/s D5/s F#5/q. E5/e D5/q | Bb4/e. Bb4/s C5/e. C5/s D5/h | r/w |"
    lead = S.track("brass", "brass", "lead", send=0.25, bright=0.65, attack=0.03)
    lead.add(seq(LEAD, 0, 0.85))
    pl = S.track("pizz", "pizz", "lead", pan=0.2, send=0.25, bright=0.6, gain_db=-4)
    pl.add(seq(LEAD, 0, 0.75, transpose=12))
    ch = S.track("choir", "choir", "pad", send=0.4, attack=0.08, release=1.4, vowel="a")
    ch.add([Ev(1, 3, (62, 66, 69, 74), 0.85), Ev(4, 0.75, (62, 65, 70, 74), 0.8),
            Ev(5, 0.75, (64, 67, 72, 76), 0.85), Ev(6, 3.0, (62, 66, 69, 74, 78), 0.95)])
    harp = S.track("harp", "harp", "accomp", pan=-0.3, send=0.35)
    harp.add(seq("D3/s F#3/s A3/s D4/s F#4/s A4/s D5/s F#5/s A5/s D6/s r/s r/s r/q | r/w | r/w |", 0, 0.6))
    harp.add(seq("r/h D4/s F#4/s A4/s D5/s F#5/s A5/s D6/s F#6/s | r/w |", 1, 0.55))
    bass = S.track("bass", "pizz_bass", "bass", send=0.08)
    bass.add(seq("r/q D2/h. | Bb1/q C2/q D2/h | D2/q r/q r/h |", 0, 0.85, ring=True))
    tim = S.track("timp", "timpani", "drums", send=0.25)
    tim.add([Ev(1, 1, 38, 0.9), Ev(6, 1, 38, 0.95)])
    tim.add(ramp(drums("xxxxxxxx........", [1], 33, 0.5), 0.4, 0.8))
    kick = S.track("kick", "taiko", "drums", send=0.2, gain_db=-4)
    kick.add([Ev(1, 1, 0, 0.9), Ev(4, 1, 0, 0.7), Ev(5, 1, 0, 0.75), Ev(6, 1, 0, 0.95)])
    cym = S.track("cym", "cymbal", "drums", pan=0.2, send=0.4, gain_db=-6)
    cym.add([Ev(6, 1, 0, 0.8, dict(tau=1.6)), Ev(4.0, 2, 0, 0.6, dict(swell=True))])
    sp = S.track("cel", "celesta", "sparkle", pan=0.35, send=0.5)
    sp.add(seq("r/w | r/h D6/s F#6/s A6/s D7/s F#6/s A6/s D7/s r/s | r/q D7/e r/e r/h |", 0, 0.6))
    return S


def song_defeat():
    """Defeat jingle (~6 s), wry rather than tragic: a drooping chromatic clarinet sigh, a
    shrugging pizzicato, a soft low chord and one cheeky music-box plink."""
    S = Song("defeat", bpm=100, bars=2, loop=False, tail=1.6, lufs=-18.0, fade_out=0.6,
             reverb=dict(t60=2.0, predelay=0.02, seed=61),
             groups=dict(lead=0, accomp=-6, pad=-8, bass=-5, drums=-8, sparkle=-8))
    clar = S.track("clar", "clarinet", "lead", pan=-0.1, send=0.3, bright=0.45)
    clar.add(seq("A4/q G#4/q G4/q F#4/q_ | F#4/q. r/e r/h |", 0, 0.8, legato=True))
    clar.events[-1].kw.update(dict(bend=(0.9, -70.0), vib=18.0))
    pz = S.track("pizz", "pizz", "accomp", pan=0.2, send=0.25, bright=0.5, gate=0.5)
    pz.add(seq("A5/q G#5/q G5/q F#5/q | r/w |", 0, 0.55))
    bass = S.track("bass", "pizz_bass", "bass", send=0.1, gate=0.6)
    bass.add(seq("D3/q C#3/q C3/q B2/q | D2/h r/h |", 0, 0.7))
    bass.events[-1].kw.update(dict(ring=True))
    ch = S.track("choir", "choir", "pad", send=0.4, attack=0.3, release=1.4, vowel="u")
    ch.add([Ev(4, 2.5, (50, 53, 57, 62), 0.7)])
    tim = S.track("timp", "timpani", "drums", send=0.3)
    tim.add([Ev(4, 1, 38, 0.6)])
    sp = S.track("plink", "celesta", "sparkle", pan=0.35, send=0.45)
    sp.add(seq("r/w | r/h r/e A6/s r/s D6/q |", 0, 0.7))
    return S


def song_story():
    """Opening-scene underscore (~20.7 s): wind and a low choir, the villain motif on celesta,
    the clarinet cat answers, timpani swell, and a full D-minor 'curtain up' hit with a bell."""
    S = Song("story", bpm=100, bars=8, loop=False, tail=1.5, lufs=-18.0, fade_out=0.8,
             reverb=dict(t60=2.5, predelay=0.025, seed=71),
             groups=dict(lead=0, lead2=-2, pad=-6, accomp=-7, bass=-6, drums=-6, bells=-5, wind=-16, sparkle=-10))
    P = prog("Dm | Dm | Dm | A7 | Bb | Gm | Em7b5 A7 | Dm", 0)
    cel = S.track("cel", "celesta", "lead", pan=0.15, send=0.45)
    cel.add(seq("A5/q D6/q E6/e F6/e E6/q | D6/q C#6/q A5/h |", 2, 0.8))
    clar = S.track("clar", "clarinet", "lead2", pan=-0.2, send=0.3, bright=0.45)
    clar.add(seq("D4/h. F4/q | G4/h Bb3/h | E4/h C#4/h |", 4, 0.75, legato=True))
    harp = S.track("harp", "harp", "accomp", pan=0.3, send=0.35)
    harp.add(gen_arp(P[:6], [0, 1, 2, 3, 4, 3, 2, 1], 0.5, 50, 74, 0.42))
    harp.add(seq("E3/s G3/s Bb3/s D4/s E4/s G4/s A4/s C#5/s E5/s G5/s A5/s C#6/s E6/q |", 6, 0.55))
    ch = S.track("choir", "choir", "pad", send=0.4, attack=1.6, release=1.2)
    ch.add(ramp(gen_pad(P[:8], 50, 65, 0.6, vowel="u"), 0.55, 0.95))
    ch.add([Ev(28, 4, (50, 53, 57, 62, 65), 1.0, dict(vowel="a", attack=0.05, release=1.8))])
    bass = S.track("bass", "pizz_bass", "bass", send=0.08, gate=0.8)
    bass.add(seq("D2/q r/q r/h | D2/q r/q A1/q r/q | D2/q r/q r/h | A1/q r/q E2/q r/q | "
                 "Bb1/q r/q F2/q r/q | G1/q r/q D2/q r/q | E2/h A1/h | D2/w |", 0, 0.7))
    bass.events[-1].kw.update(dict(ring=True))
    tim = S.track("timp", "timpani", "drums", send=0.3)
    tim.add([Ev(16, 1, 34, 0.5), Ev(20, 1, 31, 0.5)])
    tim.add(ramp(drums("xxxxxxxxxxxxxxxx", [6], 33, 0.8), 0.25, 1.0))
    tim.add([Ev(28, 1, 38, 1.0)])
    cym = S.track("cym", "cymbal", "drums", pan=0.2, send=0.45, gain_db=-5)
    cym.add([Ev(24, 4, 0, 0.8, dict(swell=True)), Ev(28, 1, 0, 0.55, dict(tau=1.8))])
    tutti = S.track("tutti", "pizz", "accomp", pan=0.0, send=0.3, bright=0.6, gate=0.5, voices=3)
    tutti.add([Ev(28, 1, (50, 57, 62, 65, 69), 1.0)])
    bell = S.track("bell", "church_bell", "bells", pan=0.1, send=0.5, tau=3.0)
    bell.add([Ev(28, 2, note_midi("D4"), 0.9)])
    S.raws.append(("wind", 0.4, wind_raw("story", 1.0, fin=1.5, fout=4.0, center=450.0)))
    sp = S.track("glock", "glock", "sparkle", pan=0.4, send=0.5)
    sp.add(seq("r/h. D6/s F6/s A6/s D7/s |", 1, 0.4))
    return S


SONGS = {
    "menu": song_menu,
    "gravewood": song_gravewood,
    "moonfall": song_moonfall,
    "boss": song_boss,
    "victory": song_victory,
    "defeat": song_defeat,
    "story": song_story,
}
