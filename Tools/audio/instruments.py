"""
instruments.py - synthesized instruments for Evil Cats (used by music.py and sfx.py).

Every instrument has the signature  inst(pitch, dur, vel, rng, **params) -> np.ndarray
  pitch : MIDI note number (or tuple of numbers for chord instruments like the choir)
  dur   : note length in seconds (the sounding tail is added by the instrument)
  vel   : 0..1 velocity
  rng   : numpy Generator (all randomness goes through it)
Mono instruments return shape (n,), stereo ones (n, 2).
"""
import numpy as np
from synth import (FS, TAU, midi_hz, ns, tvec, adsr, fade, saw, pulse, sine,
                   white, colored, bq, lp, hp, bp, onepole, tv_filter, formant, ks_string, modal,
                   softclip, crackle)


def _norm(x, peak=1.0):
    m = np.max(np.abs(x)) if x.size else 0.0
    return x * (peak / m) if m > 0 else x


# ============================================================================ plucked strings
def _pluck_exc(f0, rng, bright, pos):
    """One period of band-limited noise with a pluck-position comb (finger/plectrum shape)."""
    P = max(4, int(FS / f0))
    e = rng.uniform(-1.0, 1.0, P + 64)
    fc = min(9000.0, f0 * (2.0 + 14.0 * bright))
    e = onepole(onepole(e, fc), fc * 1.5)[64:]
    k = max(1, int(pos * P))
    e = e - np.concatenate([np.zeros(k), e[:-k]])
    e -= e.mean()
    return _norm(e)


def pizz(m, dur, vel, rng, bright=0.5, voices=2, t60=None, ring=False, gate=1.0, body="violin"):
    """Pizzicato string section: 1-3 slightly detuned Karplus-Strong strings with a body EQ.
    Staccato by default: the strings are damped `dur*gate` seconds after the pluck."""
    f0 = float(midi_hz(m))
    if t60 is None:
        t60 = float(np.clip(0.95 * (262.0 / f0) ** 0.35, 0.35, 1.8))
    held = dur * gate
    tail = t60 * 0.9 if ring else 0.14
    n = ns(min(held + tail, t60 * 1.1 + 0.05) + 0.01)
    n = max(n, ns(0.08))
    y = np.zeros(n)
    b = bright * (0.55 + 0.6 * vel)
    for v in range(voices):
        det = 2.0 ** (rng.uniform(-3.5, 3.5) / 1200.0) if voices > 1 else 1.0
        off = 0 if v == 0 else ns(rng.uniform(0.004, 0.016))
        exc = _pluck_exc(f0 * det, rng, b, rng.uniform(0.12, 0.22))
        s = ks_string(f0 * det, n - off, t60 * rng.uniform(0.9, 1.1), exc)
        y[off:] += s * (1.0 if v == 0 else rng.uniform(0.55, 0.8))
    if not ring:
        t = tvec(n)
        damp = np.where(t < held, 1.0, np.exp(-(t - held) / 0.035))
        y *= damp
    if body == "violin":
        y = bq(y, "peak", 290.0, 1.4, 3.5)
        y = bq(y, "peak", 2700.0, 1.0, 2.5)
        y = hp(y, 120.0, 2)
        y = lp(y, 9000.0, 2)
    elif body == "cello":
        y = bq(y, "peak", 180.0, 1.2, 3.0)
        y = bq(y, "peak", 1500.0, 1.0, 2.0)
        y = hp(y, 60.0, 2)
        y = lp(y, 7000.0, 2)
    y = fade(y, 0.0005, 0.01)
    return _norm(y) * vel


def harp(m, dur, vel, rng, bright=0.45, t60=None, ring=True):
    f0 = float(midi_hz(m))
    if t60 is None:
        t60 = float(np.clip(3.4 * (131.0 / f0) ** 0.5, 0.8, 4.5))
    L = min(t60 * 0.75, max(dur, 0.6) + 1.6)
    n = ns(L)
    exc = _pluck_exc(f0, rng, bright * (0.6 + 0.5 * vel), rng.uniform(0.25, 0.33))
    y = ks_string(f0, n, t60, exc)
    # second, very slightly detuned string component for a bit of shimmer
    y += 0.25 * ks_string(f0 * 2 ** (1.5 / 1200), n, t60 * 0.8, exc * 0.6)
    if not ring:
        t = tvec(n)
        y *= np.where(t < dur, 1.0, np.exp(-(t - dur) / 0.08))
    y = bq(y, "peak", 220.0, 1.0, 2.0)
    y = hp(y, 55.0, 2)
    y = lp(y, 8000.0, 1)
    y = fade(y, 0.0005, min(0.3, L * 0.3))
    return _norm(y) * vel


def pizz_bass(m, dur, vel, rng, bright=0.45, t60=1.3, gate=1.0, ring=False):
    """Double-bass pizzicato. Extra low-mid growl + gentle saturation so it reads on phones."""
    f0 = float(midi_hz(m))
    held = dur * gate
    tail = t60 * 0.8 if ring else 0.12
    n = ns(min(held + tail, t60 * 1.2) + 0.01)
    n = max(n, ns(0.1))
    exc = _pluck_exc(f0, rng, bright * (0.5 + 0.6 * vel), rng.uniform(0.18, 0.26))
    y = ks_string(f0, n, t60, exc)
    t = tvec(n)
    y = y + 0.2 * np.sin(TAU * f0 * t) * np.exp(-t / 0.3) * np.minimum(1.0, t / 0.004)
    if not ring:
        y *= np.where(t < held, 1.0, np.exp(-(t - held) / 0.04))
    y = softclip(_norm(y) * 1.6, 1.0)
    y = bq(y, "peak", 110.0, 1.0, 2.0)
    y = bq(y, "peak", 650.0, 1.1, 3.0)
    y = hp(y, 32.0, 2)
    y = lp(y, 4500.0, 2)
    y = fade(y, 0.0005, 0.01)
    return _norm(y) * vel


def pluck_bass(m, dur, vel, rng, gate=0.8):
    """Tight synth-plucked bass for the boss ostinato (saw through a snappy low-pass sweep)."""
    f0 = float(midi_hz(m))
    held = dur * gate
    n = ns(held + 0.06)
    t = tvec(n)
    src = saw(f0 * 2 ** (rng.uniform(-3, 3) / 1200), n) + 0.6 * pulse(f0 * 0.5, n, 0.5) * 0.5
    fc = 180.0 + f0 * 2.0 + (1400.0 + 1800.0 * vel) * np.exp(-t / 0.05)
    y = tv_filter(src, "lp", fc, 1.1, 64)
    y = softclip(y * 1.4, 1.0)
    env = adsr(n, 0.002, 0.12, 0.65, rel_at=held, r=0.05)
    y = y * env
    y = hp(y, 35.0, 2)
    return _norm(fade(y, 0.0, 0.012)) * vel


# ============================================================================ winds / brass
def clarinet(m, dur, vel, rng, bright=0.5, legato=False, vib=0.0, bend=None, release=0.07):
    """Low clarinet (the Peter-and-the-Wolf cat): odd-harmonic pulse, velocity brightness,
    breath noise. bend=(start_sec, cents) glides pitch at the end of the note."""
    f0 = float(midi_hz(m))
    n = ns(dur + release)
    t = tvec(n)
    cents = rng.uniform(-3.0, 3.0) + vib * np.sin(TAU * 5.2 * t + rng.uniform(0, TAU)) * np.minimum(1, t / 0.4)
    if bend is not None:
        bs, bc = bend
        cents = cents + np.where(t > bs, bc * np.clip((t - bs) / max(dur - bs, 0.05), 0, 1) ** 1.5, 0.0)
    f = f0 * 2.0 ** (cents / 1200.0)
    src = pulse(f, n, 0.46) + 0.12 * saw(f, n)
    fc = float(np.clip(f0 * (2.2 + 5.0 * vel * bright), 600.0, 4800.0))
    y = lp(src, fc, 2)
    y = bq(y, "peak", 1450.0, 1.3, 3.0)
    y = hp(y, 90.0, 1)
    breath = bp(white(n, rng), 1500.0, 5000.0, 2) * 0.035 * (0.6 + vel)
    y = y + breath
    env = adsr(n, 0.035 if legato else 0.014, 0.18, 0.82, rel_at=dur, r=release)
    y = fade(y * env, 0.0, 0.015)
    return _norm(y) * vel


def brass(m, dur, vel, rng, bright=0.6, voices=3, attack=0.05, release=0.18, scoop=35.0, vib=10.0):
    """Horn/brass section: detuned saws through an envelope-driven low-pass + brassy peak."""
    f0 = float(midi_hz(m))
    n = ns(dur + release)
    t = tvec(n)
    env = adsr(n, attack, 0.3, 0.78, rel_at=dur, r=release)
    pitch_c = -scoop * np.exp(-t / 0.035) + vib * np.sin(TAU * 5.4 * t) * np.clip((t - 0.25) / 0.4, 0, 1)
    src = np.zeros(n)
    for v in range(voices):
        c = pitch_c + (0.0 if v == 0 else rng.uniform(-7, 7))
        src += saw(f0 * 2.0 ** (c / 1200.0), n, rng.random())
    src /= voices
    fc = np.minimum(9000.0, 250.0 + f0 * (1.0 + 7.5 * bright * vel * env ** 1.6))
    y = tv_filter(src, "lp", fc, 0.9, 64)
    y = bq(y, "peak", 1150.0, 1.1, 3.5)
    y = softclip(y * 1.8, 1.0)
    y = hp(y, 60.0, 2)
    y = fade(y * env, 0.0, 0.03)
    return _norm(y) * vel


# ============================================================================ choir pad
def choir(notes, dur, vel, rng, vowel="u", voice=None, attack=0.6, release=1.0, voices=3,
          detune=10.0, vib_cents=9.0, breath=0.04, morph=None, width=0.8, bright=0.5):
    """Low choir-like pad: per note `voices` detuned BLEP saws per channel with vibrato and slow
    drift, glottal tilt, parallel formant filter bank, slow attack. Stereo output.
    vowel can be a pair (v1, v2) with morph = seconds to glide from v1 to v2."""
    if np.ndim(notes) == 0:
        notes = (int(notes),)
    n = ns(dur + release)
    t = tvec(n)
    if voice is None:
        mean = float(np.mean(notes))
        voice = "bass" if mean < 57 else ("tenor" if mean < 66 else "alto")
    vows = vowel if isinstance(vowel, (tuple, list)) else (vowel,)
    out = np.zeros((n, 2))
    for ch in range(2):
        src = np.zeros(n)
        for m in notes:
            f0 = float(midi_hz(m))
            for v in range(voices):
                cents = rng.uniform(-detune, detune)
                vr = rng.uniform(4.4, 5.8)
                vib = vib_cents * np.sin(TAU * vr * t + rng.uniform(0, TAU))
                drift = 4.0 * np.sin(TAU * rng.uniform(0.07, 0.2) * t + rng.uniform(0, TAU))
                f = f0 * 2.0 ** ((cents + vib + drift) / 1200.0)
                src += saw(f, n, rng.random())
        src /= np.sqrt(len(notes) * voices)
        src = onepole(src, 900.0 + 900.0 * bright)
        src += breath * bp(white(n, rng), 800.0, 6000.0, 2)
        if len(vows) == 1:
            y = formant(src, vows[0], voice) + 0.06 * src
        else:
            y1 = formant(src, vows[0], voice)
            y2 = formant(src, vows[1], voice)
            k = np.clip(t / max(morph or dur, 0.05), 0, 1)
            k = 0.5 - 0.5 * np.cos(np.pi * k)
            y = y1 * (1 - k) + y2 * k + 0.06 * src
        out[:, ch] = y
    mid = out.mean(axis=1, keepdims=True)
    out = mid + (out - mid) * width
    env = adsr(n, attack, 0.5, 0.9, rel_at=dur, r=release)
    out *= env[:, None]
    out = fade(lp(out, 5500.0, 2), 0.0, min(0.08, release * 0.3))
    return _norm(out) * vel


# ============================================================================ bells & keys
def celesta(m, dur, vel, rng, tau=None, bright=0.5):
    """FM celesta / music-box: ratio-1 FM with a fast-decaying index + bar overtone."""
    f0 = float(midi_hz(m))
    if tau is None:
        tau = float(np.clip(0.9 * (523.0 / f0) ** 0.6, 0.25, 1.6))
    L = min(tau * 5.0, 3.0)
    n = ns(L)
    t = tvec(n)
    idx = (0.8 + 2.5 * bright * vel) * np.exp(-t / 0.025) + 0.25
    y = np.sin(TAU * f0 * t + idx * np.sin(TAU * f0 * t))
    y += 0.22 * np.exp(-t / 0.06) * np.sin(TAU * 4.02 * f0 * t)
    y += 0.08 * np.exp(-t / 0.02) * np.sin(TAU * 9.1 * f0 * t)
    y *= np.exp(-t / tau) * np.minimum(1.0, t / 0.0008)
    y = fade(y, 0, 0.05)
    return _norm(y) * vel


def glock(m, dur, vel, rng, tau=None):
    """Glockenspiel / sparkle: free bar modes 1, 2.756, 5.404, 8.933."""
    f0 = float(midi_hz(m))
    if tau is None:
        tau = float(np.clip(1.1 * (1047.0 / f0) ** 0.5, 0.3, 1.8))
    n = ns(min(tau * 4.0, 3.0))
    y = modal([f0, f0 * 2.756, f0 * 5.404, f0 * 8.933], [1.0, 0.32, 0.12, 0.05],
              [tau, tau * 0.35, tau * 0.12, tau * 0.05], n, rng.uniform(0, 0.3, 4))
    t = tvec(n)
    y += 0.15 * bp(white(n, rng), 3000, 12000, 2) * np.exp(-t / 0.002)
    y *= np.minimum(1.0, t / 0.0005)
    y = fade(y, 0, 0.05)
    return _norm(y) * vel


def tubular(m, dur, vel, rng, tau=2.2, ratio=3.5, index=3.5):
    """DX-style tubular/chapel bell: inharmonic FM with decaying index."""
    f0 = float(midi_hz(m))
    n = ns(min(tau * 3.0, 6.0))
    t = tvec(n)
    I = index * (0.5 + 0.5 * vel) * np.exp(-t / (tau * 0.35)) + 0.4
    y = np.sin(TAU * f0 * t + I * np.sin(TAU * f0 * ratio * t))
    y += 0.3 * np.sin(TAU * f0 * 2.0 * 1.0015 * t) * np.exp(-t / (tau * 0.5))
    y *= np.exp(-t / tau) * np.minimum(1.0, t / 0.001)
    y = fade(y, 0, 0.1)
    return _norm(y) * vel


def church_bell(m, dur, vel, rng, tau=3.5, strike=0.25):
    """Big bronze bell (m = strike/nominal note). Hum, prime, minor-third tierce, quint,
    nominal and upper partials; each partial is a slightly beating pair."""
    f = float(midi_hz(m))
    ratios = [0.5, 1.0, 1.183, 1.506, 2.0, 2.514, 2.662, 3.011, 4.166, 5.433, 6.79]
    amps = [0.35, 0.45, 0.42, 0.2, 0.65, 0.34, 0.3, 0.26, 0.18, 0.12, 0.07]
    taus = [1.6, 0.8, 0.7, 0.35, 0.45, 0.24, 0.24, 0.18, 0.12, 0.08, 0.05]
    n = ns(min(tau * 2.2, 8.0))
    t = tvec(n)
    y = np.zeros(n)
    for r, a, k in zip(ratios, amps, taus):
        fr = f * 0.5 * r  # nominal (2.0) -> the named note
        if fr > 0.45 * FS:
            continue
        beat = rng.uniform(0.4, 1.6)
        env = np.exp(-t / (tau * k))
        y += a * env * (np.sin(TAU * fr * t + rng.uniform(0, TAU)) +
                        0.6 * np.sin(TAU * (fr + beat) * t + rng.uniform(0, TAU)))
    clank = bp(white(n, rng), 1200, 6000, 2) * np.exp(-t / 0.012) * strike
    y = y + clank
    y *= np.minimum(1.0, t / 0.0015)
    y = fade(y, 0, 0.4)
    return _norm(y) * vel


# ============================================================================ percussion
def kick(p, dur, vel, rng, f_hi=120.0, f_lo=52.0, tau_f=0.03, tau_a=0.19, click=0.3, knock=0.45):
    n = ns(0.55)
    t = tvec(n)
    f = f_lo + (f_hi - f_lo) * np.exp(-t / tau_f)
    body = sine(f, n) * np.exp(-t / tau_a)
    kn = np.sin(TAU * 190.0 * t) * np.exp(-t / 0.03) * knock
    cl = lp(white(n, rng), 3500.0, 2) * np.exp(-t / 0.003) * click
    y = softclip(body * 1.2 + kn + cl, 1.3)
    y *= np.minimum(1.0, t / 0.0008)
    return _norm(fade(y, 0, 0.05)) * vel


def woodblock(p, dur, vel, rng, f=None):
    f = float(midi_hz(p)) if f is None else f
    n = ns(0.12)
    t = tvec(n)
    y = modal([f, f * 1.83, f * 2.71], [1.0, 0.3, 0.12], [0.035, 0.018, 0.01], n, [0, 0.5, 1.0])
    y += 0.25 * bp(white(n, rng), 2000, 7000, 2) * np.exp(-t / 0.0015)
    y *= np.minimum(1.0, t / 0.0004)
    return _norm(fade(y, 0, 0.01)) * vel


def rim(p, dur, vel, rng):
    n = ns(0.1)
    t = tvec(n)
    y = modal([1650.0, 2950.0, 520.0], [0.8, 0.5, 0.4], [0.018, 0.01, 0.03], n)
    y += 0.5 * bp(white(n, rng), 1500, 8000, 2) * np.exp(-t / 0.003)
    y *= np.minimum(1.0, t / 0.0004)
    return _norm(fade(y, 0, 0.01)) * vel


def hat(p, dur, vel, rng, open_=False, brush=True):
    n = ns(0.5 if open_ else 0.18)
    t = tvec(n)
    nz = white(n, rng)
    hi = hp(bp(nz, 5500, 13000, 2), 5000, 2)
    tau = 0.16 if open_ else 0.028 + 0.02 * vel
    a = 0.004 if brush else 0.0005
    env = np.minimum(1.0, t / a) * np.exp(-t / tau)
    y = hi * env
    if brush:
        y += 0.5 * bp(nz, 2500, 6000, 2) * np.minimum(1.0, t / 0.01) * np.exp(-t / (tau * 1.4))
    return _norm(fade(y, 0, 0.02)) * vel


def shaker(p, dur, vel, rng):
    n = ns(0.12)
    t = tvec(n)
    y = bp(white(n, rng), 3500, 10000, 2)
    env = (t / 0.012) * np.exp(1 - t / 0.012)
    y *= env
    return _norm(fade(y, 0, 0.01)) * vel


_MEMBRANE = [1.0, 1.594, 2.136, 2.296, 2.653, 2.918, 3.156]


def frame_drum(p, dur, vel, rng, f0=None, slap=0.3, tau=0.32, drop=0.06):
    """Frame drum / bodhran: membrane modes with a small pitch drop + skin slap noise."""
    f0 = 120.0 if f0 is None else f0
    n = ns(min(tau * 3.0, 1.2))
    t = tvec(n)
    glide = 1.0 + drop * np.exp(-t / 0.03)
    y = np.zeros(n)
    amps = [1.0, 0.5, 0.35, 0.25, 0.18, 0.12, 0.08]
    for k, (r, a) in enumerate(zip(_MEMBRANE, amps)):
        y += a * sine(f0 * r * glide, n, rng.random()) * np.exp(-t / (tau / (1 + 0.6 * k)))
    y += slap * bp(white(n, rng), 700, 3500, 2) * np.exp(-t / 0.01)
    y *= np.minimum(1.0, t / 0.0006)
    y = softclip(_norm(y) * 1.2, 1.0)
    return _norm(fade(y, 0, 0.03)) * vel


def tom(p, dur, vel, rng, f0=None, tau=0.45, drop=0.22):
    f0 = float(midi_hz(p)) if f0 is None else f0
    n = ns(min(tau * 2.6, 1.3))
    t = tvec(n)
    glide = 1.0 + drop * np.exp(-t / 0.05)
    y = sine(f0 * glide, n) * np.exp(-t / tau)
    y += 0.35 * sine(f0 * 1.594 * glide, n, 0.3) * np.exp(-t / (tau * 0.4))
    y += 0.2 * sine(f0 * 2.136 * glide, n, 0.6) * np.exp(-t / (tau * 0.3))
    y += 0.45 * bp(white(n, rng), 300, 2500, 2) * np.exp(-t / 0.012)
    y *= np.minimum(1.0, t / 0.0006)
    y = softclip(_norm(y) * 1.5, 1.0)
    return _norm(fade(y, 0, 0.04)) * vel


def taiko(p, dur, vel, rng, f0=58.0, tau=0.7):
    n = ns(1.6)
    t = tvec(n)
    glide = 1.0 + 0.35 * np.exp(-t / 0.045)
    y = sine(f0 * glide, n) * np.exp(-t / tau)
    y += 0.5 * sine(f0 * 1.594 * glide, n, 0.2) * np.exp(-t / (tau * 0.35))
    y += 0.3 * sine(f0 * 2.296 * glide, n, 0.7) * np.exp(-t / (tau * 0.25))
    y += 0.5 * lp(white(n, rng), 1500.0, 2) * np.exp(-t / 0.02)
    y += 0.15 * bp(white(n, rng), 1500, 5000, 2) * np.exp(-t / 0.006)
    y *= np.minimum(1.0, t / 0.001)
    y = softclip(_norm(y) * 1.6, 1.0)
    return _norm(fade(y, 0, 0.1)) * vel


def snare(p, dur, vel, rng, tone=190.0, wires=0.8):
    n = ns(0.35)
    t = tvec(n)
    y = np.sin(TAU * tone * t) * np.exp(-t / 0.06) + 0.5 * np.sin(TAU * tone * 1.7 * t) * np.exp(-t / 0.04)
    y += wires * hp(bp(white(n, rng), 1800, 9000, 2), 1200, 2) * np.exp(-t / (0.08 + 0.06 * vel))
    y *= np.minimum(1.0, t / 0.0005)
    return _norm(fade(y, 0, 0.03)) * vel


def timpani(m, dur, vel, rng, tau=1.4):
    f0 = float(midi_hz(m))
    n = ns(min(tau * 2.5, 4.0))
    t = tvec(n)
    y = modal([f0, f0 * 1.504, f0 * 1.742, f0 * 2.0, f0 * 2.245, f0 * 2.494],
              [1.0, 0.55, 0.3, 0.3, 0.15, 0.12], [tau, tau * 0.7, tau * 0.45, tau * 0.5, tau * 0.35, tau * 0.3],
              n, rng.uniform(0, TAU, 6))
    y += 0.8 * lp(white(n, rng), 900.0, 2) * np.exp(-t / 0.015)
    y *= np.minimum(1.0, t / 0.002)
    return _norm(fade(y, 0, 0.2)) * vel


def cymbal(p, dur, vel, rng, tau=1.4, swell=False, length=None):
    """Suspended cymbal. swell=True gives a reversed crescendo of length `dur` seconds."""
    L = length or (dur if swell else min(tau * 2.5, 4.0))
    n = ns(L)
    t = tvec(n)
    fr = np.exp(rng.uniform(np.log(2500), np.log(11000), 48))
    y = np.zeros(n)
    for f in fr:
        y += np.sin(TAU * f * t + rng.uniform(0, TAU))
    y = y / 7.0 + 0.9 * hp(white(n, rng), 4000.0, 2)
    y = lp(y, 12000.0, 2)
    if swell:
        env = (t / L) ** 2.5
        y *= env
        y = fade(y, 0.0, 0.004)
    else:
        y *= np.exp(-t / tau) * np.minimum(1.0, t / 0.002)
        y = fade(y, 0, 0.2)
    return _norm(y) * vel


# ============================================================================ ambience
def thunder(p, dur, vel, rng, length=4.0, crack=0.6):
    n = ns(length)
    t = tvec(n)
    rum = lp(colored(n, rng, -6.0), 200.0, 2)
    bumps = np.zeros(n)
    for _ in range(6):
        c = rng.uniform(0.05, 0.55) * length
        w = rng.uniform(0.15, 0.6)
        bumps += rng.uniform(0.4, 1.0) * np.exp(-((t - c) / w) ** 2)
    env = (0.4 + bumps) * np.exp(-t / (length * 0.35)) * np.minimum(1.0, t / 0.08)
    y = rum * env
    if crack > 0:
        cr = hp(white(n, rng), 700.0, 2) * np.exp(-t / 0.09) * np.minimum(1, t / 0.002)
        cr += crackle(n, rng, 400.0, 0.0006, 1000, 7000) * np.exp(-t / 0.3) * 2.0
        y = y + crack * cr * (np.std(y) / (np.std(cr) + 1e-9)) * 2.0
    return _norm(fade(y, 0.002, length * 0.2)) * vel


def wind_bed(n, rng, loop=True, center=550.0, depth=0.5, cycles=(3, 5, 7)):
    """Soft moving wind (seamless when loop=True: noise is circular and every LFO completes an
    integer number of cycles over n samples)."""
    t = np.arange(n) / n
    lfo = sum(np.sin(TAU * c * t + k) for k, c in enumerate(cycles)) / len(cycles)
    nz = colored(n, rng, -4.0)
    lo = bp(nz, 150.0, 900.0, 2)
    hi_ = bp(nz, 900.0, 3000.0, 2)
    mix = (0.5 + 0.5 * lfo)
    y = lo * (1.0 - 0.5 * mix) + hi_ * 0.6 * mix
    amp = 0.6 + depth * 0.4 * lfo
    return y * amp


# registry used by music.py
INSTRUMENTS = {
    "pizz": pizz, "harp": harp, "pizz_bass": pizz_bass, "pluck_bass": pluck_bass,
    "clarinet": clarinet, "brass": brass, "choir": choir,
    "celesta": celesta, "glock": glock, "tubular": tubular, "church_bell": church_bell,
    "kick": kick, "woodblock": woodblock, "rim": rim, "hat": hat, "shaker": shaker,
    "frame_drum": frame_drum, "tom": tom, "taiko": taiko, "snare": snare, "timpani": timpani,
    "cymbal": cymbal, "thunder": thunder,
}
