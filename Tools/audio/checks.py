"""
checks.py - numeric QA for rendered/decoded audio + small spectrogram/waveform previews.
"""
import numpy as np
from scipy import signal
from synth import FS, todb, spectral_centroid, lufs_integrated, lufs_momentary_max


def metrics(x):
    x = np.asarray(x, dtype=float)
    mono = x.mean(axis=1) if x.ndim == 2 else x
    pk = float(np.max(np.abs(x))) if x.size else 0.0
    rms = float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
    dc = np.abs(x.mean(axis=0)).max() if x.ndim == 2 else abs(x.mean())
    thr = 10 ** (-60 / 20)  # leading silence = time until the signal first exceeds -60 dBFS
    idx = np.argmax(np.abs(mono) > thr) if np.any(np.abs(mono) > thr) else len(mono)
    return dict(
        dur=len(x) / FS, peak_db=float(todb(pk)), rms_db=float(todb(rms)), centroid=spectral_centroid(x),
        dc_db=float(todb(dc)), nan=bool(np.isnan(x).any() or np.isinf(x).any()),
        lead_ms=1000.0 * idx / FS, lufs=lufs_integrated(x), mom_max=lufs_momentary_max(x),
    )


def seam(x):
    """Loop seam check: jump from last to first sample relative to the file's typical
    sample-to-sample steps (ratio <= ~1 means the seam is as smooth as normal audio)."""
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        x = x[:, None]
    d = np.abs(np.diff(x, axis=0))
    jump = np.abs(x[0] - x[-1]).max()
    p99 = np.percentile(d, 99)
    med = np.median(d)
    # energy continuity: RMS of 50 ms before vs after the seam
    w = int(0.05 * FS)
    r_end = np.sqrt(np.mean(x[-w:] ** 2))
    r_start = np.sqrt(np.mean(x[:w] ** 2))
    return dict(jump=float(jump), p99=float(p99), median=float(med), ratio=float(jump / max(p99, 1e-12)),
                rms_step_db=float(todb(r_start) - todb(r_end)))


# ----------------------------------------------------------------------------- PNG preview
def _cmap(v):
    """v in [0,1] -> RGB (dark purple -> magenta -> orange -> pale yellow)."""
    stops = np.array([[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66],
                      [245, 125, 21], [250, 193, 39], [252, 255, 164]], dtype=float)
    pos = np.clip(v, 0, 1) * (len(stops) - 1)
    i = np.minimum(pos.astype(int), len(stops) - 2)
    f = (pos - i)[..., None]
    return (stops[i] * (1 - f) + stops[i + 1] * f).astype(np.uint8)


def preview_png(path, x, title="", bar_sec=None, bars_per_mark=4, width=1400):
    from PIL import Image, ImageDraw
    x = np.asarray(x, dtype=float)
    mono = x.mean(axis=1) if x.ndim == 2 else x
    n = len(mono)
    # spectrogram on a log-frequency axis
    nper = 2048
    hop = max(256, n // width)
    f, t, Z = signal.stft(mono, FS, nperseg=nper, noverlap=nper - hop if nper > hop else 0, boundary=None)
    S = 20 * np.log10(np.abs(Z) + 1e-9)
    S -= S.max()
    H = 320
    fl = np.geomspace(30, 16000, H)
    idx = np.clip(np.searchsorted(f, fl), 0, len(f) - 1)
    S = S[idx][::-1]
    cols = np.linspace(0, S.shape[1] - 1, width).astype(int)
    S = S[:, cols]
    img_s = _cmap((S + 80.0) / 80.0)
    # waveform (peak + rms per column)
    WH = 120
    wf = np.zeros((WH, width, 3), dtype=np.uint8) + 18
    edges = np.linspace(0, n, width + 1).astype(int)
    for c in range(width):
        seg = mono[edges[c]:max(edges[c] + 1, edges[c + 1])]
        pk = np.max(np.abs(seg))
        rms = np.sqrt(np.mean(seg ** 2))
        hp_ = int(pk * (WH / 2 - 2))
        hr = int(rms * (WH / 2 - 2))
        wf[WH // 2 - hp_:WH // 2 + hp_ + 1, c] = (90, 140, 200)
        wf[WH // 2 - hr:WH // 2 + hr + 1, c] = (170, 220, 255)
    wf[WH // 2 - int(10 ** (-1 / 20) * (WH / 2 - 2)), :] = (200, 60, 60)  # -1 dBFS line
    img = np.concatenate([np.zeros((22, width, 3), dtype=np.uint8) + 10, img_s, wf], axis=0)
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    d.text((6, 5), title, fill=(230, 230, 230))
    if bar_sec:
        k = 0
        dur = n / FS
        while k * bar_sec < dur:
            xx = int(k * bar_sec / dur * width)
            major = (k % bars_per_mark == 0)
            d.line([(xx, 22), (xx, 22 + (H if major else 12))], fill=(255, 255, 255) if major else (150, 150, 150))
            if major:
                d.text((xx + 2, 24), str(k), fill=(255, 255, 255))
            k += 1
    for fr in (100, 1000, 10000):
        yy = 22 + int(H - 1 - np.searchsorted(fl, fr) * 1.0)
        d.text((width - 40, yy - 6), "%dk" % (fr // 1000) if fr >= 1000 else "%d" % fr, fill=(200, 200, 200))
    im.save(path)
