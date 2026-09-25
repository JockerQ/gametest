"""
synth.py - small deterministic DSP toolkit for the Evil Cats audio generators.

Only numpy/scipy. Everything works on float64 arrays at FS = 44100 Hz.
Mono signals are shape (n,), stereo signals are shape (n, 2).
Randomness always comes from an explicit numpy Generator passed in by the caller,
so every render is reproducible.
"""
import numpy as np
from scipy import signal, ndimage

FS = 44100
TAU = 2.0 * np.pi


# ----------------------------------------------------------------------------- basics
def midi_hz(m):
    return 440.0 * 2.0 ** ((np.asarray(m, dtype=float) - 69.0) / 12.0)


_NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_midi(name):
    """'C#4' -> 61, 'Bb3' -> 58 (C4 = 60)."""
    name = name.strip()
    base = _NOTE[name[0].upper()]
    i, acc = 1, 0
    while i < len(name) and name[i] in "#b":
        acc += 1 if name[i] == "#" else -1
        i += 1
    return 12 * (int(name[i:]) + 1) + base + acc


def undb(d):
    return 10.0 ** (np.asarray(d, dtype=float) / 20.0)


def todb(x):
    return 20.0 * np.log10(np.maximum(np.abs(x), 1e-12))


def ns(sec):
    return int(round(sec * FS))


def tvec(n):
    return np.arange(n) / FS


def rng_for(*keys):
    """Deterministic generator from integer / string keys (no Python hash randomisation)."""
    h = 1469598103934665603
    for k in keys:
        for ch in str(k).encode():
            h = ((h ^ ch) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
        h = ((h ^ 0xFF) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return np.random.default_rng(h)


# ----------------------------------------------------------------------------- envelopes
def env_exp(n, tau):
    return np.exp(-np.arange(n) / (max(tau, 1e-5) * FS))


def adsr(n, a=0.005, d=0.1, s=1.0, rel_at=None, r=0.1, a_shape="cos"):
    """Attack (raised cosine or linear), exponential decay to sustain, exponential release
    starting at rel_at seconds (reaches about -40 dB after r seconds)."""
    t = tvec(n)
    e = np.empty(n)
    a = max(a, 1e-4)
    m = t < a
    if a_shape == "cos":
        e[m] = 0.5 - 0.5 * np.cos(np.pi * t[m] / a)
    else:
        e[m] = t[m] / a
    m2 = ~m
    e[m2] = s + (1.0 - s) * np.exp(-(t[m2] - a) / max(d, 1e-4))
    if rel_at is not None:
        k = min(n - 1, max(0, ns(rel_at)))
        lvl = e[k]
        tt = t[k:] - t[k]
        e[k:] = lvl * np.exp(-tt / max(r / 4.6, 1e-4))
    return e


def fade(x, fin=0.0, fout=0.0):
    """Cosine fade in / out (seconds). Works on mono or stereo, returns a copy."""
    y = np.array(x, dtype=float, copy=True)
    n = y.shape[0]
    if fin > 0:
        k = min(n, max(1, ns(fin)))
        w = 0.5 - 0.5 * np.cos(np.pi * np.arange(k) / k)
        y[:k] *= w if y.ndim == 1 else w[:, None]
    if fout > 0:
        k = min(n, max(1, ns(fout)))
        w = 0.5 + 0.5 * np.cos(np.pi * (np.arange(k) + 1) / k)
        y[n - k:] *= w if y.ndim == 1 else w[:, None]
    return y


def seg_env(points, n):
    """Piecewise-linear envelope from [(t_sec, value), ...]."""
    ts = np.array([p[0] for p in points], dtype=float)
    vs = np.array([p[1] for p in points], dtype=float)
    return np.interp(tvec(n), ts, vs)


# ----------------------------------------------------------------------------- oscillators
def phase(freq, n, phase0=0.0):
    """Unwrapped phase in cycles for a constant or per-sample frequency."""
    if np.ndim(freq) == 0:
        return phase0 + np.arange(n) * (float(freq) / FS)
    f = np.asarray(freq, dtype=float)
    ph = np.empty(n)
    ph[0] = 0.0
    np.cumsum(f[:-1] / FS, out=ph[1:])
    return ph + phase0


def sine(freq, n, phase0=0.0):
    return np.sin(TAU * phase(freq, n, phase0))


def _blep(t, dt):
    out = np.zeros_like(t)
    m = t < dt
    if m.any():
        x = t[m] / dt[m]
        out[m] = x + x - x * x - 1.0
    m = t > 1.0 - dt
    if m.any():
        x = (t[m] - 1.0) / dt[m]
        out[m] = x * x + x + x + 1.0
    return out


def saw(freq, n, phase0=0.0):
    """PolyBLEP band-limited sawtooth, range about [-1, 1]."""
    ph = phase(freq, n, phase0)
    t = ph - np.floor(ph)
    dt = np.abs(np.broadcast_to(np.asarray(freq, dtype=float), (n,))) / FS
    dt = np.minimum(dt, 0.5)
    return 2.0 * t - 1.0 - _blep(t, dt)


def pulse(freq, n, width=0.5, phase0=0.0):
    """Band-limited pulse (difference of two BLEP saws), zero mean, peak-to-peak 2."""
    return saw(freq, n, phase0) - saw(freq, n, phase0 + width)


def tri(freq, n, phase0=0.0):
    ph = phase(freq, n, phase0)
    t = ph - np.floor(ph)
    return 1.0 - 4.0 * np.abs(t - 0.5)


# ----------------------------------------------------------------------------- noise
def white(n, rng):
    return rng.standard_normal(n)


def colored(n, rng, slope_db_oct=-3.0, lo=20.0, hi=None):
    """FFT-shaped noise (circular -> seamless when looped). slope -3 = pink, -6 = brown."""
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1.0 / FS)
    ff = np.maximum(f, lo)
    X *= (ff / 1000.0) ** (slope_db_oct / 6.0206)
    X[f < lo * 0.5] = 0.0
    if hi is not None:
        X[f > hi] *= np.exp(-((f[f > hi] - hi) / (0.15 * hi)) ** 2)
    y = np.fft.irfft(X, n)
    return y / (np.std(y) + 1e-12)


def pink(n, rng):
    return colored(n, rng, -3.0)


def brown(n, rng):
    return colored(n, rng, -6.0)


def crackle(n, rng, density, decay=0.0008, lo=1500.0, hi=9000.0, amp_jitter=0.8):
    """Sparse random clicks (Poisson, density per second) through a bandpass."""
    x = np.zeros(n)
    k = rng.poisson(max(density, 0.0) * n / FS)
    if k > 0:
        pos = rng.integers(0, n, k)
        amp = (1.0 - amp_jitter) + amp_jitter * rng.random(k)
        sgn = np.where(rng.random(k) < 0.5, -1.0, 1.0)
        np.add.at(x, pos, amp * sgn)
    ker = env_exp(ns(decay * 6) + 1, decay)
    x = signal.fftconvolve(x, ker)[:n]
    return bp(x, lo, hi, 2)


# ----------------------------------------------------------------------------- filters
def bq_coefs(kind, f0, q=0.7071, gain_db=0.0):
    f0 = float(np.clip(f0, 5.0, 0.48 * FS))
    w0 = TAU * f0 / FS
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2.0 * q)
    A = 10.0 ** (gain_db / 40.0)
    if kind == "lp":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "bp":  # constant 0 dB peak gain
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "notch":
        b = [1.0, -2 * cw, 1.0]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == "lowshelf":
        sa = np.sqrt(A)
        b = [A * ((A + 1) - (A - 1) * cw + 2 * sa * alpha), 2 * A * ((A - 1) - (A + 1) * cw),
             A * ((A + 1) - (A - 1) * cw - 2 * sa * alpha)]
        a = [(A + 1) + (A - 1) * cw + 2 * sa * alpha, -2 * ((A - 1) + (A + 1) * cw),
             (A + 1) + (A - 1) * cw - 2 * sa * alpha]
    elif kind == "highshelf":
        sa = np.sqrt(A)
        b = [A * ((A + 1) + (A - 1) * cw + 2 * sa * alpha), -2 * A * ((A - 1) + (A + 1) * cw),
             A * ((A + 1) + (A - 1) * cw - 2 * sa * alpha)]
        a = [(A + 1) - (A - 1) * cw + 2 * sa * alpha, 2 * ((A - 1) - (A + 1) * cw),
             (A + 1) - (A - 1) * cw - 2 * sa * alpha]
    else:
        raise ValueError(kind)
    b = np.asarray(b, dtype=float)
    a = np.asarray(a, dtype=float)
    return b / a[0], a / a[0]


def bq(x, kind, f0, q=0.7071, gain_db=0.0):
    b, a = bq_coefs(kind, f0, q, gain_db)
    return signal.lfilter(b, a, x, axis=0)


def _sos(kind, fc, order):
    if kind == "band":
        lo, hi = fc
        hi = min(hi, 0.48 * FS)
        lo = max(lo, 5.0)
        return signal.butter(order, [lo, hi], "bandpass", fs=FS, output="sos")
    return signal.butter(order, float(np.clip(fc, 5.0, 0.48 * FS)), kind, fs=FS, output="sos")


def lp(x, fc, order=2):
    return signal.sosfilt(_sos("lowpass", fc, order), x, axis=0)


def hp(x, fc, order=2):
    return signal.sosfilt(_sos("highpass", fc, order), x, axis=0)


def bp(x, lo, hi, order=2):
    return signal.sosfilt(_sos("band", (lo, hi), order), x, axis=0)


def onepole(x, fc):
    a = np.exp(-TAU * fc / FS)
    return signal.lfilter([1.0 - a], [1.0, -a], x, axis=0)


def tv_filter(x, kind, fc, q=0.7071, block=64):
    """Time-varying biquad (coefficients updated every `block` samples)."""
    n = len(x)
    fcv = np.broadcast_to(np.asarray(fc, dtype=float), (n,))
    qv = np.broadcast_to(np.asarray(q, dtype=float), (n,))
    y = np.empty(n)
    zi = np.zeros(2)
    for i in range(0, n, block):
        j = min(n, i + block)
        b, a = bq_coefs(kind, fcv[i], qv[i])
        y[i:j], zi = signal.lfilter(b, a, x[i:j], zi=zi)
    return y


def circular(func, x, pad_sec=1.0):
    """Apply a causal filter to a looping signal so the result is seamless: pre-roll with
    the end of the loop, then drop the pre-roll."""
    n = x.shape[0]
    p = min(n, ns(pad_sec))
    xx = np.concatenate([x[n - p:], x], axis=0)
    return func(xx)[p:]


# ----------------------------------------------------------------------------- formants
# Classic vocal formant table (frequency Hz, level dB, bandwidth Hz).
FORMANTS = {
    ("bass", "a"): ([600, 1040, 2250, 2450, 2750], [0, -7, -9, -9, -20], [60, 70, 110, 120, 130]),
    ("bass", "o"): ([400, 750, 2400, 2600, 2900], [0, -11, -21, -20, -40], [40, 80, 100, 120, 120]),
    ("bass", "u"): ([350, 600, 2400, 2675, 2950], [0, -20, -32, -28, -36], [40, 80, 100, 120, 120]),
    ("bass", "e"): ([400, 1620, 2400, 2800, 3100], [0, -12, -9, -12, -18], [40, 80, 100, 120, 120]),
    ("tenor", "a"): ([650, 1080, 2650, 2900, 3250], [0, -6, -7, -8, -22], [80, 90, 120, 130, 140]),
    ("tenor", "o"): ([400, 800, 2600, 2800, 3000], [0, -10, -12, -12, -26], [40, 80, 100, 120, 120]),
    ("tenor", "u"): ([350, 600, 2700, 2900, 3300], [0, -20, -17, -14, -26], [40, 60, 100, 120, 120]),
    ("alto", "a"): ([800, 1150, 2800, 3500, 4950], [0, -4, -20, -36, -60], [80, 90, 120, 130, 140]),
    ("alto", "o"): ([450, 800, 2830, 3500, 4950], [0, -9, -16, -28, -55], [70, 80, 100, 130, 135]),
    ("alto", "u"): ([325, 700, 2530, 3500, 4950], [0, -12, -30, -40, -64], [50, 60, 170, 180, 200]),
}


def formant(x, vowel="a", voice="bass", bw_scale=1.4, shift=1.0):
    fr, lv, bw = FORMANTS[(voice, vowel)]
    y = np.zeros_like(x)
    for f, l, b in zip(fr, lv, bw):
        f = f * shift
        qq = f / (b * bw_scale)
        y += undb(l) * bq(x, "bp", f, qq)
    return y


# ----------------------------------------------------------------------------- physical-ish models
def ks_string(f0, n, t60, exc, stretch=0.5):
    """Karplus-Strong string, vectorised one period at a time.
    Loop: y[n] = x[n] + g*(h0 y[n-N] + h1 y[n-N-1] + h2 y[n-N-2]) where h = averaging filter
    convolved with linear fractional delay. Tuned so period = N + stretch + frac."""
    P = FS / float(f0)
    N = int(np.floor(P - stretch))
    frac = P - stretch - N
    g = 10.0 ** (-3.0 / (max(t60, 0.01) * f0))
    S = stretch
    h0 = (1 - frac) * (1 - S)
    h1 = (1 - frac) * S + frac * (1 - S)
    h2 = frac * S
    c0, c1, c2 = g * h0, g * h1, g * h2
    off = N + 2
    y = np.zeros(off + n)
    x = np.zeros(off + n)
    m = min(len(exc), n)
    x[off:off + m] = exc[:m]
    tot = off + n
    for b in range(off, tot, N):
        e = min(b + N, tot)
        y[b:e] = x[b:e] + c0 * y[b - N:e - N] + c1 * y[b - N - 1:e - N - 1] + c2 * y[b - N - 2:e - N - 2]
    return y[off:]


def modal(freqs, amps, taus, n, phases=None):
    """Sum of exponentially decaying sinusoids."""
    t = tvec(n)
    y = np.zeros(n)
    for i, (f, a, tau) in enumerate(zip(freqs, amps, taus)):
        if f <= 0 or f >= 0.47 * FS or a == 0:
            continue
        ph = 0.0 if phases is None else phases[i]
        y += a * np.exp(-t / tau) * np.sin(TAU * f * t + ph)
    return y


# ----------------------------------------------------------------------------- space
def pan(x, p):
    """Constant-power pan of a mono signal, p in [-1, 1]."""
    ang = (np.clip(p, -1, 1) + 1.0) * np.pi / 4.0
    return np.stack([x * np.cos(ang), x * np.sin(ang)], axis=1) * np.sqrt(2.0)


def make_ir(t60=2.0, length=None, predelay=0.02, seed=7, lo_mul=1.25, hi_mul=0.45,
            er_gain=0.35, width=1.0):
    """Synthetic stereo room/hall impulse response: band-split noise with per-band decay,
    a soft onset, a few early reflections and a pre-delay. Unit energy per channel."""
    length = length or min(t60 * 1.15, 4.5)
    n = ns(length)
    rng = np.random.default_rng(seed)
    t = tvec(n)
    bands = [(20, 250, lo_mul), (250, 900, 1.0), (900, 2800, 0.8), (2800, 7000, 0.62), (7000, 18000, hi_mul)]
    chans = []
    for ch in range(2):
        nz = rng.standard_normal(n)
        acc = np.zeros(n)
        for lo_f, hi_f, mul in bands:
            acc += bp(nz, lo_f, hi_f, 2) * np.exp(-6.9078 * t / (t60 * mul))
        acc *= np.minimum(1.0, t / 0.03) ** 1.5  # diffuse build-up
        # early reflections
        for k in range(10):
            tt = rng.uniform(0.004, 0.07)
            idx = ns(tt)
            if idx < n:
                acc[idx] += er_gain * rng.choice([-1, 1]) * (1.0 - tt / 0.09) * np.std(acc[:ns(0.1)]) * 6
        chans.append(acc)
    ir = np.stack(chans, axis=1)
    if width < 1.0:
        mid = ir.mean(axis=1, keepdims=True)
        ir = mid + (ir - mid) * width
    ir = np.concatenate([np.zeros((ns(predelay), 2)), ir], axis=0)
    ir /= np.sqrt(np.sum(ir ** 2, axis=0, keepdims=True))
    return ir


def convolve(x, ir, circular_len=None):
    """Stereo (n,2) x stereo IR -> per-channel convolution. With circular_len the result is
    the circular convolution of that length (seamless loops)."""
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    if circular_len is not None:
        n = circular_len
        X = np.fft.rfft(x, n=n, axis=0)
        H = np.fft.rfft(ir, n=n, axis=0)
        return np.fft.irfft(X * H, n=n, axis=0)
    out = np.stack([signal.fftconvolve(x[:, c], ir[:, c]) for c in range(2)], axis=1)
    return out[: x.shape[0]]


# ----------------------------------------------------------------------------- dynamics
def limiter(x, ceiling_db=-1.5, radius_ms=6.0, wrap=False):
    """Look-ahead brickwall limiter: gain = moving average (radius R) of a moving minimum
    (radius R) of the required gain. Guarantees |y| <= ceiling (up to float error)."""
    c = undb(ceiling_db)
    pk = np.max(np.abs(x), axis=1) if x.ndim == 2 else np.abs(x)
    greq = np.minimum(1.0, c / np.maximum(pk, 1e-12))
    if greq.min() >= 1.0:
        return x.copy(), 0.0
    R = max(1, ns(radius_ms / 1000.0))
    mode = "wrap" if wrap else "nearest"
    m = ndimage.minimum_filter1d(greq, size=2 * R + 1, mode=mode)
    g = ndimage.uniform_filter1d(m, size=2 * R + 1, mode=mode)
    g = np.minimum(g, greq + 1e-9)
    y = x * (g[:, None] if x.ndim == 2 else g)
    return y, float(todb(g.min()))


def softclip(x, drive=1.0):
    return np.tanh(drive * x) / np.tanh(drive)


# ----------------------------------------------------------------------------- loudness (ITU-R BS.1770-4)
def _k_coefs():
    # stage 1: high shelf (+4 dB above ~1.5 kHz), stage 2: RLB high-pass (~38 Hz)
    G, Q, fc = 4.0, 1.0 / np.sqrt(2.0), 1500.0
    A = 10 ** (G / 40.0)
    w0 = TAU * fc / FS
    alpha = np.sin(w0) / (2.0 * Q)
    cw = np.cos(w0)
    b0 = A * ((A + 1) + (A - 1) * cw + 2 * np.sqrt(A) * alpha)
    b1 = -2 * A * ((A - 1) + (A + 1) * cw)
    b2 = A * ((A + 1) + (A - 1) * cw - 2 * np.sqrt(A) * alpha)
    a0 = (A + 1) - (A - 1) * cw + 2 * np.sqrt(A) * alpha
    a1 = 2 * ((A - 1) - (A + 1) * cw)
    a2 = (A + 1) - (A - 1) * cw - 2 * np.sqrt(A) * alpha
    s1 = (np.array([b0, b1, b2]) / a0, np.array([1.0, a1 / a0, a2 / a0]))
    fc2, Q2 = 38.0, 0.5
    w0 = TAU * fc2 / FS
    alpha = np.sin(w0) / (2.0 * Q2)
    cw = np.cos(w0)
    b = np.array([(1 + cw) / 2, -(1 + cw), (1 + cw) / 2])
    a = np.array([1 + alpha, -2 * cw, 1 - alpha])
    s2 = (b / a[0], a / a[0])
    return s1, s2


_K1, _K2 = _k_coefs()


def k_weight(x):
    y = signal.lfilter(_K1[0], _K1[1], x, axis=0)
    return signal.lfilter(_K2[0], _K2[1], y, axis=0)


def _block_ms(x, block_s=0.4, hop_s=0.1):
    y = k_weight(x)
    if y.ndim == 1:
        y = y[:, None]
    n = y.shape[0]
    B, H = ns(block_s), ns(hop_s)
    if n < B:
        y = np.concatenate([y, np.zeros((B - n, y.shape[1]))], axis=0)
        n = B
    cs = np.concatenate([np.zeros((1, y.shape[1])), np.cumsum(y ** 2, axis=0)], axis=0)
    starts = np.arange(0, n - B + 1, H)
    ms = (cs[starts + B] - cs[starts]) / B
    return ms.sum(axis=1)


def lufs_integrated(x):
    z = _block_ms(x)
    lk = -0.691 + 10 * np.log10(np.maximum(z, 1e-20))
    z1 = z[lk > -70.0]
    if z1.size == 0:
        return -99.0
    rel = -0.691 + 10 * np.log10(z1.mean()) - 10.0
    z2 = z1[(-0.691 + 10 * np.log10(z1)) > rel]
    if z2.size == 0:
        return -99.0
    return float(-0.691 + 10 * np.log10(z2.mean()))


def lufs_momentary_max(x):
    z = _block_ms(x, 0.4, 0.01)
    return float(-0.691 + 10 * np.log10(max(z.max(), 1e-20)))


# ----------------------------------------------------------------------------- analysis
def spectral_centroid(x):
    m = x.mean(axis=1) if x.ndim == 2 else x
    if len(m) < 256:
        m = np.concatenate([m, np.zeros(256 - len(m))])
    f, P = signal.welch(m, FS, nperseg=min(4096, len(m)))
    mag = np.sqrt(P)
    return float(np.sum(f * mag) / max(np.sum(mag), 1e-20))


def rms_db(x):
    return float(todb(np.sqrt(np.mean(np.asarray(x, dtype=float) ** 2))))


def peak_db(x):
    return float(todb(np.max(np.abs(x))))
