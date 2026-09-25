"""
sfx.py - every Evil Cats sound effect, synthesized from scratch (mono, 44.1 kHz).

Each design is a function  f(rng, v) -> mono float array  (v = variation index).
SFX_TABLE lists every id with its variation count and the manifest mix data:
  target  : intended loudness (momentary-max LUFS) at the id's manifest volume; the build
            converts it into the manifest "volume" after measuring the peak-normalised file
  pitchVar, maxVoices, cooldownMs, category : copied into audio_manifest.json
"""
import numpy as np
from synth import (FS, TAU, ns, tvec, midi_hz, note_midi, env_exp, adsr, fade, saw, pulse, sine,
                   white, colored, bq, lp, hp, bp, onepole, tv_filter, formant, modal, softclip)
import instruments as I


# ============================================================================ helpers
class Mix:
    def __init__(self, dur):
        self.y = np.zeros(ns(dur))

    def add(self, sig, at=0.0, gain=1.0):
        sig = np.asarray(sig, dtype=float)
        if sig.ndim == 2:
            sig = sig.mean(axis=1)
        s = ns(at)
        need = s + len(sig)
        if need > len(self.y):
            self.y = np.concatenate([self.y, np.zeros(need - len(self.y))])
        self.y[s:need] += gain * sig
        return self


def env_ad(n, a, tau):
    t = tvec(n)
    return np.minimum(1.0, t / max(a, 1e-5)) * np.exp(-np.maximum(0.0, t - a) / tau)


def fsweep(n, f0, f1, tau=None):
    """Frequency trajectory: exponential glide over the whole length, or with `tau` a fast
    exponential approach from f0 to f1."""
    t = tvec(n)
    if tau is None:
        return f0 * (f1 / f0) ** (t / (n / FS))
    return f1 + (f0 - f1) * np.exp(-t / tau)


def bp_sweep(x, f0, f1, q=1.0, tau=None):
    return tv_filter(x, "bp", fsweep(len(x), f0, f1, tau), q)


def lp_sweep(x, f0, f1, tau=None, q=0.7071):
    return tv_filter(x, "lp", fsweep(len(x), f0, f1, tau), q)


def jitter(n, rng, rate=200.0, amount=0.05):
    j = lp(rng.standard_normal(n), rate, 2)
    return 1.0 + amount * j / (np.std(j) + 1e-12)


def flicker(n, rng, rate=150.0, duty=0.55, smooth_hz=3000.0):
    """Random on/off gate with exponential segment lengths (electric crackle)."""
    k = int(n * rate / FS * 2) + 8
    edges = np.cumsum(rng.exponential(1.0 / rate, k)) * FS
    vals = (rng.random(k) < duty).astype(float)
    idx = np.minimum(np.searchsorted(edges, np.arange(n)), k - 1)
    return onepole(vals[idx], smooth_hz)


def crackle_rate(n, rng, rate_fn, lo=1500.0, hi=9000.0, decay=0.0006, max_rate=2000.0):
    """Non-homogeneous Poisson crackle: rate_fn(t) in events per second."""
    x = np.zeros(n)
    k = rng.poisson(max_rate * n / FS)
    pos = np.sort(rng.integers(0, n, k))
    keep = rng.random(k) < np.clip(rate_fn(pos / FS) / max_rate, 0, 1)
    pos = pos[keep]
    amp = (0.3 + 0.7 * rng.random(len(pos))) * np.where(rng.random(len(pos)) < 0.5, -1, 1)
    np.add.at(x, pos, amp)
    ker = env_exp(ns(decay * 6) + 1, decay)
    x = np.convolve(x, ker)[:n]
    return bp(x, lo, hi, 2)


def string_twang(f0, f1, n, tau, harm=12, bright=1.0, rng=None):
    """Additive plucked 'thwang' with a pitch drop f0->f1 (bow / ballista string)."""
    t = tvec(n)
    f = f1 + (f0 - f1) * np.exp(-t / 0.03)
    ph = np.cumsum(f) / FS
    y = np.zeros(n)
    for k in range(1, harm + 1):
        if f0 * k > 0.45 * FS:
            break
        y += (bright ** (k - 1)) / k * np.sin(TAU * k * ph + (0 if rng is None else rng.uniform(0, TAU))) \
            * np.exp(-t / (tau / (1 + 0.35 * (k - 1))))
    return y * np.minimum(1.0, t / 0.0005)


def glass_ping(f, n, rng, tau=0.3, amp=1.0):
    ratios = [1.0, 2.32, 4.25, 6.63]
    amps = [1.0, 0.55, 0.3, 0.15]
    taus = [tau, tau * 0.55, tau * 0.3, tau * 0.18]
    y = np.zeros(n)
    t = tvec(n)
    for r, a, k in zip(ratios, amps, taus):
        fr = f * r
        if fr > 0.45 * FS:
            continue
        beat = rng.uniform(1.0, 4.0)
        y += a * np.exp(-t / k) * (np.sin(TAU * fr * t + rng.uniform(0, TAU)) +
                                   0.5 * np.sin(TAU * (fr + beat) * t + rng.uniform(0, TAU)))
    return amp * y * np.minimum(1.0, t / 0.0003)


def thump(n, f0, f1, tau_f, tau_a, click=0.0, rng=None):
    t = tvec(n)
    y = sine(fsweep(n, f0, f1, tau_f), n) * np.exp(-t / tau_a)
    if click and rng is not None:
        y += click * lp(white(n, rng), 3000.0, 2) * np.exp(-t / 0.004)
    return y * np.minimum(1.0, t / 0.0005)


def fm_bell(f, n, tau=0.8, ratio=1.4, index=2.0, idx_tau=0.15):
    t = tvec(n)
    I_ = index * np.exp(-t / idx_tau) + 0.2
    return np.sin(TAU * f * t + I_ * np.sin(TAU * f * ratio * t)) * np.exp(-t / tau) * np.minimum(1, t / 0.0008)


def shards(n, rng, count, t_scale, f_lo, f_hi, tau_lo, tau_hi, t0=0.0):
    y = np.zeros(n)
    for _ in range(count):
        st = t0 + min(rng.exponential(t_scale), 0.9 * n / FS)
        s = ns(st)
        L = n - s
        if L <= 64:
            continue
        f = np.exp(rng.uniform(np.log(f_lo), np.log(f_hi)))
        tau = rng.uniform(tau_lo, tau_hi)
        a = rng.uniform(0.3, 1.0) * np.exp(-(st - t0) / (t_scale * 2.5 + 1e-3))
        y[s:] += glass_ping(f, L, rng, tau, a)
    return y


def fft_band(x, lo, hi, soft=0.15):
    """Circular (loop-safe) band-pass by spectral weighting."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / FS)
    w = 1.0 / (1.0 + (lo / np.maximum(f, 1e-3)) ** 4) / (1.0 + (f / hi) ** 4)
    return np.fft.irfft(X * w, len(x))


# ============================================================================ UI
def ui_click(rng, v=0):
    n = ns(0.09)
    y = modal([1750.0, 2980.0, 4650.0], [1.0, 0.45, 0.2], [0.018, 0.010, 0.006], n, [0.0, 0.7, 1.4])
    y += 0.35 * bp(white(n, rng), 3000, 9000, 2) * env_exp(n, 0.0012)
    return y * np.minimum(1.0, tvec(n) / 0.0003)


def ui_back(rng, v=0):
    m = Mix(0.16)
    n = ns(0.1)
    m.add(modal([1320.0, 2210.0], [1.0, 0.35], [0.02, 0.01], n) + 0.25 * bp(white(n, rng), 2500, 7000, 2) * env_exp(n, 0.001))
    m.add(modal([960.0, 1650.0], [1.0, 0.3], [0.025, 0.012], n) + 0.2 * bp(white(n, rng), 2000, 6000, 2) * env_exp(n, 0.001),
          0.042, 0.8)
    return m.y


def ui_denied(rng, v=0):
    m = Mix(0.3)
    for k, (at, f, L) in enumerate([(0.0, 196.0, 0.085), (0.12, 185.0, 0.11)]):
        n = ns(L + 0.03)
        src = 0.5 * pulse(f, n, 0.5) + 0.5 * pulse(f * 1.059, n, 0.3)
        src = lp(src, 1900.0, 2)
        env = adsr(n, 0.003, 0.05, 0.85, rel_at=L, r=0.03)
        body = src * env
        body += 0.3 * thump(n, 120.0, 85.0, 0.02, 0.04)
        body += 0.25 * bp(white(n, rng), 300.0, 1500.0, 2) * env_exp(n, 0.012)
        m.add(body, at, 1.0 if k == 0 else 0.95)
    return lp(m.y, 2600.0, 2)


def ui_toggle(rng, v=0):
    m = Mix(0.1)
    n = ns(0.06)
    m.add(modal([1500.0, 2620.0], [1.0, 0.4], [0.012, 0.007], n) + 0.2 * bp(white(n, rng), 3000, 8000, 2) * env_exp(n, 0.0008))
    m.add(modal([2250.0, 3900.0], [1.0, 0.35], [0.014, 0.008], n) + 0.2 * bp(white(n, rng), 3000, 9000, 2) * env_exp(n, 0.0008),
          0.03, 0.85)
    return m.y


def _coin_tone(f, n, tau=0.3):
    return modal([f, f * 2.405, f * 3.87, f * 5.3], [1.0, 0.5, 0.25, 0.12], [tau, tau * 0.5, tau * 0.27, tau * 0.16], n,
                 [0.0, 0.4, 0.9, 1.7])


def purchase(rng, v=0):
    m = Mix(0.8)
    n = ns(0.75)
    t = tvec(n)
    m.add(0.6 * bp(white(n, rng), 3000, 10000, 2) * env_exp(n, 0.01))
    m.add(0.35 * np.sin(TAU * 180 * t) * np.exp(-t / 0.04))
    m.add(_coin_tone(1975.5, n, 0.32))
    m.add(_coin_tone(2637.0, n, 0.36), 0.075, 0.9)
    return m.y


def _arp(m, notes, start, step, inst, vel=0.8, dur=0.3, gains=None, **kw):
    for i, nt in enumerate(notes):
        g = 1.0 if gains is None else gains[i]
        m.add(inst(nt, dur, vel, np.random.default_rng(1000 + i), **kw), start + i * step, g)


def _sparkle(m, rng, t0, t1, count, lo=96, hi=108, gain=0.3, scale=(0, 2, 4, 7, 9)):
    for k in range(count):
        at = t0 + (t1 - t0) * (k / max(1, count - 1)) ** 1.3 + rng.uniform(-0.01, 0.01)
        octs = [p for p in range(lo, hi + 1) if p % 12 in scale]
        p = int(rng.choice(octs))
        m.add(I.glock(p, 0.1, 1.0, rng, tau=rng.uniform(0.08, 0.2)), max(0, at), gain * (1 - 0.6 * k / count))


def reward(rng, v=0):
    m = Mix(1.4)
    _arp(m, [84, 88, 91, 96, 100], 0.0, 0.06, I.celesta, 0.9, gains=[0.7, 0.75, 0.8, 0.9, 1.0], tau=0.45)
    _sparkle(m, rng, 0.25, 1.0, 14, 96, 108, 0.25, (0, 4, 7, 9))
    n = ns(1.2)
    t = tvec(n)
    sh = hp(white(n, rng), 6000.0, 2) * (0.5 + 0.5 * np.sin(TAU * 28 * t)) ** 2 * env_ad(n, 0.12, 0.35)
    m.add(0.06 * sh, 0.1)
    return m.y


def level_up(rng, v=0):
    m = Mix(1.8)
    notes = [67, 71, 74, 79, 83, 86, 91, 95, 98]
    _arp(m, notes, 0.0, 0.05, I.harp, 0.8, dur=0.5, gains=np.linspace(0.6, 1.0, len(notes)))
    _arp(m, notes[2:], 0.1, 0.05, I.celesta, 0.7, gains=np.linspace(0.4, 0.8, len(notes) - 2), tau=0.5)
    ch = I.choir((67, 71, 74, 79), 0.55, 0.8, rng, vowel="a", attack=0.06, release=0.6, voice="alto")
    m.add(ch, 0.42, 0.45)
    for nt, g in [(91, 0.7), (95, 0.6), (98, 0.6), (103, 0.4)]:
        m.add(I.celesta(nt, 0.5, 0.9, rng, tau=0.6), 0.45, g)
    n = ns(0.5)
    wh = bp_sweep(white(n, rng), 500.0, 5000.0, 1.2) * np.linspace(0.2, 1.0, n) ** 2
    m.add(0.25 * fade(wh, 0.01, 0.05))
    _sparkle(m, rng, 0.5, 1.4, 12, 96, 110, 0.2, (0, 2, 4, 7, 9))
    return m.y


def perk_pick(rng, v=0):
    m = Mix(1.0)
    n = ns(0.24)
    wh = bp_sweep(white(n, rng), 700.0, 3800.0, 1.5) * np.linspace(0.1, 1.0, n) ** 1.5
    m.add(0.5 * fade(wh, 0.005, 0.03))
    m.add(I.tubular(81, 0.5, 0.8, rng, tau=0.45), 0.18, 0.7)
    m.add(I.celesta(88, 0.5, 0.9, rng, tau=0.45), 0.18, 0.6)
    m.add(I.glock(93, 0.3, 0.8, rng), 0.22, 0.35)
    return m.y


COIN_F = [2637.0, 2960.0, 3322.4]


def coin(rng, v=0):
    n = ns(0.16)
    f = COIN_F[v % 3]
    y = modal([f, f * 2.76, f * 5.4], [1.0, 0.3, 0.1], [0.045, 0.02, 0.008], n, [0.0, 0.5, 1.0])
    y += 0.3 * bp(white(n, rng), 4000, 12000, 2) * env_exp(n, 0.001)
    return y * np.minimum(1.0, tvec(n) / 0.0003)


def xp(rng, v=0):
    m = Mix(0.4)
    pent = [93, 97, 100, 102, 105]
    for k, at in enumerate([0.0, 0.035, 0.075, 0.12]):
        f = float(midi_hz(pent[(k * 2 + v) % len(pent)]))
        n = ns(0.2)
        t = tvec(n)
        m.add(np.sin(TAU * f * t) * np.exp(-t / 0.06) * np.minimum(1, t / 0.001), at, 1.0 - 0.18 * k)
    n = ns(0.3)
    m.add(0.08 * hp(white(n, rng), 7000.0, 2) * env_ad(n, 0.02, 0.08))
    return m.y


def unlock(rng, v=0):
    m = Mix(1.8)
    n = ns(0.5)
    t = tvec(n)
    rise = bp_sweep(white(n, rng), 300.0, 4000.0, 1.3) * (t / t[-1]) ** 2
    rise += 0.3 * sine(fsweep(n, 400.0, 1600.0), n) * (t / t[-1]) ** 3
    m.add(0.45 * fade(rise, 0.01, 0.02))
    k = ns(0.08)
    m.add(modal([900.0, 2100.0, 3400.0], [1.0, 0.5, 0.25], [0.02, 0.012, 0.006], k), 0.5, 0.9)
    m.add(modal([620.0, 1480.0], [1.0, 0.4], [0.03, 0.015], k), 0.52, 0.7)
    _arp(m, [86, 90, 93, 98], 0.53, 0.045, I.celesta, 0.9, gains=[0.7, 0.8, 0.9, 1.0], tau=0.5)
    m.add(I.choir((62, 66, 69, 74), 0.6, 0.7, rng, vowel="a", attack=0.05, release=0.7, voice="alto"), 0.53, 0.4)
    _sparkle(m, rng, 0.6, 1.5, 10, 98, 110, 0.2, (2, 6, 9))
    return m.y


def claim(rng, v=0):
    m = Mix(1.1)
    m.add(I.celesta(88, 0.3, 0.9, rng, tau=0.35), 0.0, 0.8)
    m.add(I.glock(100, 0.3, 0.8, rng), 0.0, 0.25)
    m.add(I.celesta(95, 0.3, 1.0, rng, tau=0.45), 0.09, 1.0)
    m.add(I.glock(107, 0.3, 0.8, rng), 0.09, 0.25)
    _sparkle(m, rng, 0.15, 0.7, 8, 100, 112, 0.18, (0, 4, 7, 11))
    return m.y


def swoosh(rng, v=0):
    n = ns(0.32)
    t = tvec(n)
    T = n / FS
    fc = 500.0 * (4.5 ** np.sin(np.pi * np.clip(t / (0.75 * T), 0, 1) * 0.5)) * np.where(t > 0.6 * T, 1 - 0.35 * (t - 0.6 * T) / (0.4 * T), 1)
    y = tv_filter(white(n, rng), "bp", fc, 1.3)
    env = np.sin(np.pi * np.clip(t / T, 0, 1)) ** 2 * (1.0 + 0.3 * np.exp(-((t - 0.35 * T) / (0.1 * T)) ** 2))
    return fade(y * env, 0.003, 0.02)


def countdown(rng, v=0):
    m = Mix(0.22)
    n = ns(0.09)
    m.add(modal([1200.0, 2190.0, 3300.0], [1.0, 0.4, 0.15], [0.03, 0.015, 0.008], n) +
          0.3 * bp(white(n, rng), 2500, 8000, 2) * env_exp(n, 0.0012))
    n2 = ns(0.18)
    t = tvec(n2)
    beep = (np.sin(TAU * 1760.0 * t) + 0.25 * np.sin(TAU * 3520.0 * t)) * env_ad(n2, 0.002, 0.05)
    m.add(beep, 0.004, 0.55)
    return m.y


# ============================================================================ combat: lightning
def arc_bolt(rng, v=0):
    n = ns(0.3 + 0.04 * v)
    t = tvec(n)
    f_start = [3200.0, 2700.0, 3600.0][v % 3]
    f_end = [320.0, 260.0, 380.0][v % 3]
    f = fsweep(n, f_start, f_end, tau=0.045 + 0.01 * v) * jitter(n, rng, 180.0, 0.08)
    zap = saw(f, n) + 0.5 * pulse(f * 1.5, n, 0.3)
    zap = bp(zap, 350.0, 7000.0, 2) * env_ad(n, 0.001, 0.08)
    snap = bp(white(n, rng), 1800.0, 9000.0, 2) * env_exp(n, 0.0025)
    crack = bp(white(n, rng), 1200.0, 7500.0, 2) * flicker(n, rng, 170.0, 0.5) * env_ad(n, 0.002, 0.11)
    buzz = bp(pulse(115.0 * jitter(n, rng, 60, 0.05), n, 0.12), 300, 4000, 2) * env_ad(n, 0.003, 0.06) * flicker(n, rng, 90.0, 0.6)
    y = 0.55 * snap + 0.55 * zap + 0.8 * crack + 0.6 * buzz
    y = softclip(y / (np.max(np.abs(y)) + 1e-9) * 1.6, 1.2)
    return lp(bq(y, "peak", 2800.0, 1.0, 2.0), 10000.0, 2)


def chain_jump(rng, v=0):
    n = ns(0.09)
    t = tvec(n)
    x = np.zeros(n)
    for k in range(5 + v):
        p = ns(rng.uniform(0.0, 0.035)) if k else 0
        x[p] += rng.uniform(0.5, 1.0) * rng.choice([-1, 1])
    x = np.convolve(x, env_exp(ns(0.004), 0.0006))[:n]
    cr = bp(x, 1800.0, 9000.0, 2)
    ch = np.sin(TAU * np.cumsum(fsweep(n, 5200.0 - 300 * v, 2200.0, tau=0.012)) / FS) * env_ad(n, 0.0005, 0.015)
    return cr + 0.35 * ch


def arc_storm(rng, v=0):
    m = Mix(2.6)
    n = ns(2.6)
    t = tvec(n)
    crack = hp(white(n, rng), 400.0, 2) * env_ad(n, 0.0015, 0.07)
    crack += 1.5 * crackle_rate(n, rng, lambda tt: 3000.0 * np.exp(-tt / 0.12), 800.0, 8000.0, max_rate=3000.0)
    m.add(crack, 0.0, 0.9)
    zn = ns(0.3)
    z = saw(fsweep(zn, 3000.0, 150.0, tau=0.06) * jitter(zn, rng, 150, 0.1), zn) * env_ad(zn, 0.001, 0.1)
    m.add(bp(z, 200, 6000, 2), 0.0, 0.35)
    m.add(thump(n, 60.0, 34.0, 0.08, 0.45), 0.0, 0.9)
    rum = I.thunder(0, 1, 1.0, rng, length=2.5, crack=0.0)
    m.add(rum, 0.04, 0.9)
    return softclip(m.y / np.max(np.abs(m.y)) * 1.4, 1.0)


def ward_cast(rng, v=0):
    n = ns(1.15)
    t = tvec(n)
    notes = [69, 76, 81, 85, 88]
    glide = 2.0 ** (-4.0 * np.exp(-t / 0.18) / 12.0)
    y = np.zeros(n)
    for k, m_ in enumerate(notes):
        f = float(midi_hz(m_)) * glide
        on = np.clip((t - 0.06 * k) / 0.05, 0, 1)
        trem = 1.0 + 0.3 * np.sin(TAU * (10.5 + k) * t + k)
        y += (np.sin(TAU * np.cumsum(f) / FS) + 0.2 * np.sin(2 * TAU * np.cumsum(f) / FS)) * on * trem * (1.0 - 0.1 * k)
    env = np.clip(t / 0.7, 0, 1) ** 1.5 * np.where(t > 0.75, np.exp(-(t - 0.75) / 0.14), 1.0)
    y *= env
    nz = bp_sweep(white(n, rng), 800.0, 6000.0, 1.0) * env * 0.5
    m = Mix(1.2)
    m.add(y / 4.0)
    m.add(nz, 0.0, 0.35)
    m.add(I.glock(93, 0.2, 1.0, rng), 0.72, 0.35)
    m.add(hp(white(ns(0.2), rng), 5000.0, 2) * env_exp(ns(0.2), 0.03), 0.72, 0.12)
    return m.y


def barrier_hit(rng, v=0):
    n = ns(0.55)
    t = tvec(n)
    y = glass_ping(2100.0, n, rng, 0.3)
    y += 0.4 * hp(white(n, rng), 3000.0, 2) * env_exp(n, 0.001)
    y += 0.4 * np.sin(TAU * 420.0 * t) * np.exp(-t / 0.03)
    return y


def barrier_break(rng, v=0):
    n = ns(1.2)
    t = tvec(n)
    m = Mix(1.2)
    m.add(hp(white(n, rng), 800.0, 2) * env_exp(n, 0.03), 0.0, 0.8)
    m.add(thump(n, 140.0, 90.0, 0.03, 0.1), 0.0, 0.7)
    m.add(glass_ping(2100.0, n, rng, 0.2), 0.0, 0.6)
    m.add(shards(n, rng, 36, 0.14, 2200.0, 8000.0, 0.04, 0.12), 0.0, 0.5)
    m.add(bp(white(n, rng), 2000, 9000, 2) * env_ad(n, 0.002, 0.22), 0.0, 0.35)
    return lp(m.y, 11000.0, 2)


def station_arc_coil(rng, v=0):
    n = ns(0.62)
    t = tvec(n)
    f = fsweep(n, 105.0, 150.0) * jitter(n, rng, 40.0, 0.04)
    buzz = pulse(f, n, 0.08)
    buzz = hp(buzz, 150.0, 2) + 0.6 * bp(buzz, 1000.0, 4500.0, 2)
    gate = flicker(n, rng, 60.0, 0.75, 800.0) * np.clip(t / 0.25, 0.35, 1.0)
    cr = crackle_rate(n, rng, lambda tt: 150.0 + 500.0 * tt, 2000.0, 9000.0, max_rate=500.0)
    y = buzz * gate * 0.5 + 2.0 * cr
    env = adsr(n, 0.02, 0.2, 1.0, rel_at=0.5, r=0.1)
    return y * env


def station_ember_fire(rng, v=0):
    n = ns(0.9)
    t = tvec(n)
    m = Mix(0.9)
    m.add(thump(n, 88.0, 45.0, 0.04, 0.14), 0.0, 1.0)
    m.add(lp(white(n, rng), 1100.0, 2) * env_exp(n, 0.03), 0.0, 0.8)
    wh = bp_sweep(white(n, rng), 2600.0, 480.0, 0.9) * env_ad(n, 0.02, 0.22)
    m.add(wh, 0.01, 0.9)
    m.add(crackle_rate(n, rng, lambda tt: 180.0 * np.exp(-tt / 0.3), 800.0, 5000.0, max_rate=200.0), 0.03, 2.0)
    return softclip(m.y / np.max(np.abs(m.y)) * 1.3, 1.0)


def _boom(rng, dur, f0, f1, tau_a, lp0, lp1, lp_tau, crack_rate, crack_tau, drive):
    n = ns(dur)
    t = tvec(n)
    m = Mix(dur)
    m.add(thump(n, f0, f1, 0.08, tau_a), 0.0, 1.0)
    body = lp_sweep(white(n, rng), lp0, lp1, tau=lp_tau) * env_ad(n, 0.002, tau_a * 1.1)
    m.add(body, 0.0, 0.9)
    m.add(hp(white(n, rng), 900.0, 2) * env_exp(n, 0.012), 0.0, 0.5)
    m.add(crackle_rate(n, rng, lambda tt: crack_rate * np.exp(-tt / crack_tau), 700.0, 6000.0,
                       max_rate=crack_rate), 0.02, 3.0)
    y = m.y / np.max(np.abs(m.y))
    return softclip(y * drive, 1.0)


def explosion(rng, v=0):
    return _boom(rng, 1.3, 72.0, 32.0, 0.3, 6000.0, 260.0, 0.18, 260.0, 0.35, 1.8)


def powder_explode(rng, v=0):
    y = _boom(rng, 1.8, 62.0, 28.0, 0.45, 7500.0, 200.0, 0.3, 420.0, 0.55, 2.2)
    n = len(y)
    return y + 0.25 * lp(I.thunder(0, 1, 1.0, rng, length=n / FS, crack=0.0), 300, 2)


# ============================================================================ combat: frost / glass
def frost_bell(rng, v=0):
    n = ns(1.6)
    t = tvec(n)
    f = 2093.0
    y = fm_bell(f * 2 ** (4 / 1200), n, 0.55, 1.4, 1.6, 0.1) + fm_bell(f * 2 ** (-4 / 1200), n, 0.5, 1.4, 1.6, 0.1)
    y += 0.5 * fm_bell(3136.0, n, 0.4, 1.4, 1.2, 0.08) * np.clip((t - 0.07) / 0.002, 0, 1)
    y += 0.25 * modal([f * 2.756], [1.0], [0.12], n)
    y += 0.8 * crackle_rate(n, rng, lambda tt: 600.0 * np.exp(-tt / 0.06), 4000.0, 11000.0, max_rate=600.0)
    return y


def freeze(rng, v=0):
    n = ns(0.85)
    t = tvec(n)
    rate = lambda tt: 900.0 * np.clip(tt / 0.35, 0.05, 1.0) * np.exp(-np.maximum(0, tt - 0.35) / 0.15)
    cr = crackle_rate(n, rng, rate, 2500.0, 11000.0, 0.0004, 900.0)
    hiss = hp(white(n, rng), 5000.0, 2) * env_ad(n, 0.25, 0.25) * 0.12
    tone = np.sin(TAU * np.cumsum(fsweep(n, 5200.0, 3800.0)) / FS) * env_ad(n, 0.05, 0.25) * 0.08
    return lp(2.5 * cr + hiss + tone, 11000.0, 2)


def shatter(rng, v=0):
    n = ns(0.75)
    m = Mix(0.75)
    m.add(bp(white(n, rng), 1500, 7000, 2) * env_exp(n, 0.04), 0.0, 0.8)
    m.add(crackle_rate(n, rng, lambda tt: 2000.0 * (tt < 0.06), 2000.0, 9000.0, max_rate=2000.0), 0.0, 2.0)
    m.add(shards(n, rng, 24, 0.08, 3500.0, 10000.0, 0.02, 0.08), 0.0, 0.6)
    m.add(thump(n, 200.0, 120.0, 0.02, 0.05), 0.0, 0.3)
    return lp(m.y, 11000.0, 2)


# ============================================================================ combat: ballista / arrows / hits
def ballista_fire(rng, v=0):
    n = ns(0.65)
    m = Mix(0.65)
    m.add(string_twang(128.0, 110.0, n, 0.16, 16, 0.93, rng), 0.0, 1.0)
    m.add(modal([420.0, 980.0, 1600.0], [1.0, 0.5, 0.2], [0.03, 0.02, 0.01], n) +
          0.4 * bp(white(n, rng), 1000, 5000, 2) * env_exp(n, 0.004), 0.0, 0.6)
    w = ns(0.4)
    m.add(bp_sweep(white(w, rng), 2200.0, 700.0, 1.2) * env_ad(w, 0.01, 0.12), 0.02, 0.8)
    return m.y


def ballista_hit(rng, v=0):
    n = ns(0.28)
    t = tvec(n)
    y = modal([170.0 + 12 * v, 330.0 + 18 * v, 560.0 + 25 * v], [0.7, 0.5, 0.35], [0.06, 0.04, 0.02], n, [0, 1, 2])
    y += modal([860.0 + 45 * v, 1480.0 + 70 * v, 2350.0 + 60 * v], [0.9, 0.45, 0.2], [0.028, 0.016, 0.008], n, [0.3, 1.1, 2.0])
    y += 0.35 * thump(n, 95.0, 70.0, 0.02, 0.05)
    y += 0.6 * bp(white(n, rng), 1200.0, 6000.0 - 500 * v, 2) * env_exp(n, 0.003)
    return y * np.minimum(1, t / 0.0004)


def arrow_fire(rng, v=0):
    n = ns(0.38)
    m = Mix(0.38)
    m.add(string_twang(195.0, 176.0, n, 0.07, 10, 0.9, rng), 0.0, 0.8)
    w = ns(0.3)
    m.add(bp_sweep(white(w, rng), 3500.0, 1400.0, 3.0) * env_ad(w, 0.005, 0.08), 0.01, 0.9)
    return m.y


def enemy_hit(rng, v=0):
    n = ns(0.16)
    t = tvec(n)
    f0 = [150.0, 170.0, 135.0][v % 3]
    y = 0.5 * thump(n, f0, 85.0, 0.02, 0.04)
    y += 0.9 * bp(white(n, rng), 250.0, 1300.0, 2) * env_ad(n, 0.001, 0.018)
    y += (0.5 - 0.08 * v) * bp(white(n, rng), 1300.0, 4500.0 + 600 * v, 2) * env_exp(n, 0.005)
    y += 0.55 * modal([380.0 + 45 * v, 690.0 + 60 * v], [1.0, 0.45], [0.022, 0.012], n, [0.0, 1.0])
    return y * np.minimum(1, t / 0.0004)


def enemy_death(rng, v=0):
    n = ns(0.45)
    t = tvec(n)
    m = Mix(0.45)
    poof = bp_sweep(white(n, rng), 2600.0 - 200 * v, 450.0 + 50 * v, 0.8, tau=0.08) * env_ad(n, 0.004, 0.11)
    m.add(poof, 0.0, 1.0)
    pn = ns(0.06)
    m.add(np.sin(TAU * np.cumsum(fsweep(pn, 430.0 + 30 * v, 170.0, tau=0.012)) / FS) * env_ad(pn, 0.001, 0.02), 0.0, 0.5)
    m.add(I.glock(100 + 2 * v, 0.1, 0.6, rng, tau=0.08), 0.05, 0.08)
    return m.y


def citadel_hit(rng, v=0):
    n = ns(0.5)
    m = Mix(0.5)
    m.add(thump(n, 80.0 - 4 * v, 48.0, 0.03, 0.1), 0.0, 0.55)
    m.add(modal([240.0 + 15 * v, 510.0 + 20 * v, 830.0, 1270.0], [1.0, 0.6, 0.35, 0.2], [0.05, 0.03, 0.02, 0.012], n), 0.0, 0.6)
    m.add(crackle_rate(n, rng, lambda tt: 700.0 * np.exp(-tt / 0.15), 500.0, 4000.0, 0.001, 700.0), 0.005, 3.0)
    m.add(bp(white(n, rng), 300.0, 2500.0, 2) * env_exp(n, 0.035), 0.0, 0.8)
    return m.y


def citadel_heavy_hit(rng, v=0):
    n = ns(1.7)
    t = tvec(n)
    m = Mix(1.7)
    m.add(thump(n, 62.0, 30.0, 0.1, 0.45), 0.0, 1.0)
    m.add(bp(white(n, rng), 700, 5000, 2) * env_exp(n, 0.06), 0.0, 0.6)
    m.add(lp_sweep(white(n, rng), 4000.0, 200.0, tau=0.25) * env_ad(n, 0.002, 0.35), 0.0, 0.7)
    deb = np.zeros(n)
    for _ in range(45):
        st = 0.05 + min(rng.exponential(0.35), 1.4)
        s = ns(st)
        L = min(n - s, ns(0.08))
        if L < 32:
            continue
        f = np.exp(rng.uniform(np.log(400), np.log(2500)))
        deb[s:s + L] += rng.uniform(0.2, 1.0) * np.exp(-st / 0.6) * modal([f, f * 1.7], [1, 0.4],
                                                                          [rng.uniform(0.008, 0.03), 0.008], L)
    m.add(deb, 0.0, 0.6)
    m.add(lp(colored(n, rng, -6.0), 150.0, 2) * env_ad(n, 0.05, 0.6), 0.0, 0.8)
    return softclip(m.y / np.max(np.abs(m.y)) * 1.5, 1.0)


def golem_step(rng, v=0):
    n = ns(0.75)
    m = Mix(0.75)
    m.add(thump(n, 64.0 - 3 * v, 40.0, 0.04, 0.14), 0.0, 0.6)
    r = 1.0 + 0.035 * (v - 1)
    m.add(modal([185.0 * r, 412.0 * r, 693.0 * r, 1127.0 * r, 1650.0 * r], [0.6, 0.8, 0.5, 0.35, 0.2],
                [0.3, 0.22, 0.15, 0.1, 0.07], n, rng.uniform(0, TAU, 5)), 0.004, 0.6)
    m.add(crackle_rate(n, rng, lambda tt: 300.0 * np.exp(-tt / 0.12), 300.0, 2500.0, 0.001, 300.0), 0.0, 2.0)
    m.add(lp(white(n, rng), 1200.0, 2) * env_exp(n, 0.02), 0.0, 0.6)
    return m.y


# ============================================================================ combat: magic / creatures
def ward_pulse(rng, v=0):
    n = ns(1.0)
    t = tvec(n)
    m = Mix(1.0)
    for f, at, g in [(880.0, 0.0, 1.0), (1318.5, 0.02, 0.7)]:
        c = np.sin(TAU * f * t + 0.8 * np.exp(-t / 0.05) * np.sin(TAU * f * t)) * env_ad(n, 0.008, 0.45)
        m.add(c, at, g)
    sw = (np.sin(TAU * 440.0 * t) + 0.5 * np.sin(TAU * 659.3 * t)) * env_ad(n, 0.12, 0.3)
    m.add(sw, 0.0, 0.35)
    return m.y


def gravity_pull(rng, v=0):
    n = ns(0.9)
    t = tvec(n)
    T = 0.82
    e = np.clip(t / T, 0, 1) ** 3 * (t < T)
    sub = sine(fsweep(n, 190.0, 48.0), n) * e
    nz = bp_sweep(white(n, rng), 3000.0, 300.0, 1.0) * e
    mid = lp(saw(fsweep(n, 420.0, 110.0), n), 1600.0, 2) * e
    m = Mix(0.95)
    m.add(0.45 * sub + 1.1 * nz + 0.35 * mid)
    k = ns(0.12)
    m.add(thump(k, 75.0, 50.0, 0.02, 0.05, 0.3, rng), T - 0.005, 0.8)
    return m.y


def priest_heal(rng, v=0):
    m = Mix(1.4)
    m.add(I.tubular(76, 0.5, 0.9, rng, tau=0.8, index=1.3), 0.0, 0.8)
    m.add(I.tubular(83, 0.5, 0.7, rng, tau=0.6, index=1.1), 0.05, 0.5)
    m.add(I.celesta(88, 0.3, 0.8, rng, tau=0.5), 0.0, 0.35)
    m.add(I.choir((64, 68, 71, 76), 0.5, 0.8, rng, vowel="a", attack=0.08, release=0.5, voice="alto"), 0.0, 0.5)
    for k, nt in enumerate([88, 92, 95]):
        m.add(I.glock(nt, 0.1, 0.7, rng, tau=0.15), 0.1 + 0.06 * k, 0.2)
    return lp(m.y, 9000.0, 2)


def powder_fuse(rng, v=0):
    """Seamless 1.0 s sizzle loop (all processing is circular)."""
    n = ns(1.0)
    hiss = fft_band(colored(n, rng, -1.0), 2500.0, 9000.0)
    hiss /= np.std(hiss)
    am = fft_band(rng.standard_normal(n), 8.0, 45.0)
    am = 0.65 + 0.35 * am / (np.max(np.abs(am)) + 1e-9)
    pops = np.zeros(n)
    k = 40
    pos = rng.integers(0, n, k)
    np.add.at(pops, pos, rng.uniform(0.4, 1.0, k) * rng.choice([-1, 1], k))
    ker = np.zeros(n)
    kk = ns(0.004)
    ker[:kk] = env_exp(kk, 0.0006)
    pops = np.fft.irfft(np.fft.rfft(pops) * np.fft.rfft(ker), n)
    pops = fft_band(pops, 1200.0, 8000.0)
    pops /= (np.max(np.abs(pops)) + 1e-9)
    y = 0.25 * hiss * am + 0.8 * pops
    return y - y.mean()


def bat_swarm(rng, v=0):
    n = ns(1.4)
    t = tvec(n)
    wings = np.zeros(n)
    for k in range(7):
        rate = rng.uniform(14.0, 24.0)
        ph = rng.uniform(0, TAU)
        flap = (0.5 + 0.5 * np.sin(TAU * rate * t * jitter(n, rng, 3.0, 0.05) + ph)) ** 4
        c = rng.uniform(350.0, 1500.0)
        wings += bp(white(n, rng), c * 0.6, c * 1.6, 2) * flap * rng.uniform(0.5, 1.0)
    m = Mix(1.4)
    m.add(wings, 0.0, 0.5)
    for _ in range(14):
        at = rng.uniform(0.05, 1.15)
        L = ns(0.05)
        tt = tvec(L)
        f = rng.uniform(5500.0, 8500.0) * (1 - 0.25 * tt / tt[-1]) * (1 + 0.03 * np.sin(TAU * 90 * tt))
        sq = np.sin(TAU * np.cumsum(f) / FS) * env_ad(L, 0.002, 0.012)
        m.add(sq, at, rng.uniform(0.15, 0.35))
    env = np.clip(tvec(len(m.y)) / 0.12, 0, 1) * np.clip((1.4 - tvec(len(m.y))) / 0.35, 0, 1)
    return m.y * env


def boss_roar(rng, v=0):
    n = ns(2.0)
    t = tvec(n)
    f0 = fsweep(n, 128.0, 66.0, tau=0.7) * jitter(n, rng, 25.0, 0.06)
    src = saw(f0, n) + 0.6 * saw(f0 * 0.5, n, 0.3) + 0.5 * bp(white(n, rng), 200.0, 3000.0, 2)
    src *= 1.0 + 0.45 * np.sin(TAU * 33.0 * t + 2.0 * np.sin(TAU * 7.0 * t))
    a = formant(src, "a", "bass", 1.3, 0.85)
    o = formant(src, "o", "bass", 1.3, 0.85)
    k = np.clip((t - 0.3) / 1.0, 0, 1)
    y = a * (1 - k) + o * k + 0.05 * src
    env = adsr(n, 0.12, 0.8, 0.75, rel_at=1.35, r=0.6)
    y = softclip(y / np.max(np.abs(y)) * 2.5, 1.0) * env
    y += 0.35 * np.sin(TAU * np.cumsum(f0 * 0.5) / FS) * env
    return y


# ============================================================================ stingers
def boss_warning(rng, v=0):
    """Two-hit war-horn stinger (E then F: the Phrygian half-step of doom). A bright, nasal,
    slightly overdriven horn layer sits in 1-4 kHz so it cuts through the battle mix."""
    m = Mix(2.4)
    for at, root, dur, g in [(0.0, 40, 0.26, 0.75), (0.34, 41, 1.25, 1.0)]:
        for nt in (root + 12, root + 19, root + 24):
            m.add(I.brass(nt, dur, 0.95, rng, bright=1.0, attack=0.02, release=0.35), at, 0.55 * g)
        n = ns(dur + 0.35)
        t = np.arange(n) / FS
        f = float(midi_hz(root + 12)) * 2 ** ((-30 * np.exp(-t / 0.04) + 8 * np.sin(TAU * 6 * t)) / 1200)
        horn = sum(saw(f * 2 ** (d / 1200), n, rng.random()) for d in (-9, 0, 7))
        horn = softclip(bp(horn, 700.0, 3800.0, 2) * 2.5, 2.0)
        horn = bq(horn, "peak", 1800.0, 1.2, 5.0) * adsr(n, 0.03, 0.2, 0.85, rel_at=dur, r=0.3)
        m.add(horn, at, 0.5 * g)
        m.add(I.taiko(0, 0.1, 1.0, rng, f0=55.0), at, 0.6 * g)
    m.add(I.church_bell(note_midi("F4"), 1.0, 0.8, rng, tau=2.0), 0.34, 0.3)
    return bq(m.y, "lowshelf", 120.0, 0.7, -4.0)


def bell_toll(rng, v=0):
    return I.church_bell(note_midi("D4"), 1.0, 1.0, rng, tau=3.6)


def wave_start(rng, v=0):
    m = Mix(1.7)
    m.add(I.taiko(0, 0.1, 1.0, rng, f0=56.0), 0.0, 1.0)
    m.add(I.frame_drum(0, 0.1, 1.0, rng, slap=0.6), 0.0, 0.5)
    for at, nt, dur in [(0.08, 57, 0.16), (0.3, 62, 0.85)]:
        m.add(I.brass(nt, dur, 0.9, rng, bright=0.85, attack=0.02, release=0.3), at, 0.8)
        m.add(I.brass(nt - 12, dur, 0.8, rng, bright=0.7, attack=0.02, release=0.3), at, 0.5)
    m.add(I.taiko(0, 0.1, 0.9, rng, f0=60.0), 0.3, 0.8)
    return m.y


def wave_clear(rng, v=0):
    m = Mix(1.4)
    _arp(m, [86, 90, 93, 98], 0.0, 0.07, I.celesta, 0.9, gains=[0.75, 0.8, 0.9, 1.0], tau=0.5)
    _arp(m, [98, 102, 105, 110], 0.0, 0.07, I.glock, 0.7, gains=[0.25, 0.25, 0.25, 0.3])
    m.add(I.tubular(86, 0.5, 0.6, rng, tau=0.8), 0.28, 0.3)
    _sparkle(m, rng, 0.35, 1.1, 8, 98, 110, 0.15, (2, 6, 9))
    return m.y


def victory_sting(rng, v=0):
    m = Mix(2.3)
    gl = [50, 54, 57, 62, 66, 69, 74, 78, 81, 86]
    _arp(m, gl, 0.0, 0.025, I.harp, 0.8, dur=0.5, gains=np.linspace(0.5, 0.9, len(gl)))
    for nt in (62, 66, 69, 74):
        m.add(I.brass(nt, 0.55, 0.9, rng, bright=0.8, attack=0.02, release=0.45), 0.25, 0.45)
    m.add(I.choir((62, 66, 69, 74), 0.9, 0.9, rng, vowel="a", attack=0.03, release=0.8), 0.25, 0.6)
    m.add(I.timpani(38, 0.1, 1.0, rng, tau=0.9), 0.25, 0.8)
    m.add(I.cymbal(0, 1.0, 0.7, rng, tau=0.9), 0.25, 0.15)
    _arp(m, [86, 90, 93, 98], 0.32, 0.06, I.celesta, 0.9, gains=[0.5, 0.55, 0.6, 0.7], tau=0.5)
    return m.y


def defeat_sting(rng, v=0):
    m = Mix(2.1)
    m.add(I.clarinet(57, 0.26, 0.85, rng, legato=True, bright=0.8), 0.0, 1.0)
    m.add(I.clarinet(53, 0.95, 0.85, rng, legato=True, vib=16.0, bend=(0.35, -80.0), bright=0.8), 0.32, 1.0)
    m.add(I.pizz(50, 0.4, 0.9, rng, ring=True, body="cello"), 0.32, 0.45)
    m.add(I.woodblock(60, 0.1, 0.8, rng), 0.32, 0.25)
    m.add(I.celesta(93, 0.2, 0.8, rng), 1.45, 0.3)
    return m.y


# ============================================================================ table
# id: (fn, variations, target LUFS(momentary max) at manifest volume, pitchVar, maxVoices, cooldownMs, category)
SFX_TABLE = {
    "ui_click":           (ui_click, 1, -24, 0.0, 2, 40, "ui"),
    "ui_back":            (ui_back, 1, -24, 0.0, 2, 40, "ui"),
    "ui_denied":          (ui_denied, 1, -22, 0.0, 1, 150, "ui"),
    "ui_toggle":          (ui_toggle, 1, -24, 0.0, 2, 40, "ui"),
    "purchase":           (purchase, 1, -20, 0.0, 1, 100, "ui"),
    "reward":             (reward, 1, -19, 0.0, 1, 200, "ui"),
    "level_up":           (level_up, 1, -18, 0.0, 1, 300, "ui"),
    "perk_pick":          (perk_pick, 1, -20, 0.0, 1, 100, "ui"),
    "arc_bolt":           (arc_bolt, 3, -20, 0.05, 3, 40, "combat"),
    "chain_jump":         (chain_jump, 3, -24, 0.06, 4, 30, "combat"),
    "arc_storm":          (arc_storm, 1, -15, 0.03, 2, 300, "combat"),
    "ward_cast":          (ward_cast, 1, -19, 0.03, 2, 150, "combat"),
    "barrier_hit":        (barrier_hit, 1, -21, 0.05, 3, 50, "combat"),
    "barrier_break":      (barrier_break, 1, -17, 0.04, 2, 150, "combat"),
    "station_arc_coil":   (station_arc_coil, 1, -21, 0.05, 2, 80, "combat"),
    "station_ember_fire": (station_ember_fire, 1, -19, 0.05, 2, 80, "combat"),
    "explosion":          (explosion, 1, -16, 0.06, 2, 80, "combat"),
    "frost_bell":         (frost_bell, 1, -20, 0.03, 2, 120, "combat"),
    "freeze":             (freeze, 1, -21, 0.05, 3, 60, "combat"),
    "shatter":            (shatter, 1, -19, 0.06, 3, 60, "combat"),
    "ballista_fire":      (ballista_fire, 1, -20, 0.05, 3, 60, "combat"),
    "ballista_hit":       (ballista_hit, 3, -22, 0.06, 4, 40, "combat"),
    "ward_pulse":         (ward_pulse, 1, -21, 0.03, 2, 120, "combat"),
    "gravity_pull":       (gravity_pull, 1, -19, 0.04, 2, 200, "combat"),
    "enemy_hit":          (enemy_hit, 3, -23, 0.07, 4, 30, "combat"),
    "enemy_death":        (enemy_death, 3, -21, 0.07, 4, 40, "combat"),
    "citadel_hit":        (citadel_hit, 3, -19, 0.05, 3, 80, "combat"),
    "citadel_heavy_hit":  (citadel_heavy_hit, 1, -15, 0.04, 2, 250, "combat"),
    "arrow_fire":         (arrow_fire, 1, -23, 0.07, 4, 40, "combat"),
    "priest_heal":        (priest_heal, 1, -20, 0.03, 2, 150, "combat"),
    "powder_fuse":        (powder_fuse, 1, -24, 0.04, 2, 100, "combat"),
    "powder_explode":     (powder_explode, 1, -14, 0.05, 2, 150, "combat"),
    "golem_step":         (golem_step, 3, -19, 0.05, 3, 120, "combat"),
    "bat_swarm":          (bat_swarm, 1, -21, 0.05, 2, 250, "combat"),
    "boss_warning":       (boss_warning, 1, -14, 0.0, 1, 2000, "stinger"),
    "boss_roar":          (boss_roar, 1, -15, 0.03, 1, 1000, "combat"),
    "bell_toll":          (bell_toll, 1, -17, 0.0, 1, 1000, "ambient"),
    "wave_start":         (wave_start, 1, -16, 0.0, 1, 1000, "stinger"),
    "wave_clear":         (wave_clear, 1, -17, 0.0, 1, 1000, "stinger"),
    "victory_sting":      (victory_sting, 1, -16, 0.0, 1, 2000, "stinger"),
    "defeat_sting":       (defeat_sting, 1, -17, 0.0, 1, 2000, "stinger"),
    "coin":               (coin, 3, -25, 0.0, 3, 35, "ui"),
    "xp":                 (xp, 1, -25, 0.0, 3, 35, "ui"),
    "unlock":             (unlock, 1, -18, 0.0, 1, 300, "ui"),
    "claim":              (claim, 1, -19, 0.0, 1, 150, "ui"),
    "swoosh":             (swoosh, 1, -25, 0.0, 2, 60, "ui"),
    "countdown":          (countdown, 1, -19, 0.0, 1, 250, "stinger"),
}
LOOPING = {"powder_fuse"}
# hard maximum length (s); the last 30 % becomes a smooth fade so long instrument tails stay tidy
MAXLEN = {
    "ui_click": 0.09, "ui_back": 0.16, "ui_denied": 0.3, "ui_toggle": 0.1, "purchase": 0.7, "reward": 1.3,
    "level_up": 1.7, "perk_pick": 0.9, "coin": 0.16, "xp": 0.35, "unlock": 1.6, "claim": 1.0, "swoosh": 0.32,
    "countdown": 0.2, "arc_bolt": 0.4, "chain_jump": 0.1, "arc_storm": 2.6, "ward_cast": 1.2, "barrier_hit": 0.55,
    "barrier_break": 1.2, "station_arc_coil": 0.62, "station_ember_fire": 0.9, "explosion": 1.3, "frost_bell": 1.5,
    "freeze": 0.85, "shatter": 0.75, "ballista_fire": 0.65, "ballista_hit": 0.28, "ward_pulse": 1.0,
    "gravity_pull": 0.95, "enemy_hit": 0.16, "enemy_death": 0.45, "citadel_hit": 0.5, "citadel_heavy_hit": 1.7,
    "arrow_fire": 0.38, "priest_heal": 1.3, "powder_explode": 1.8, "golem_step": 0.75, "bat_swarm": 1.4,
    "boss_warning": 2.4, "boss_roar": 2.0, "bell_toll": 4.5, "wave_start": 1.7, "wave_clear": 1.3,
    "victory_sting": 2.3, "defeat_sting": 2.0,
}
