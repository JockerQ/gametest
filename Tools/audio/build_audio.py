"""
Build every Evil Cats music track and sound effect + audio_manifest.json.

    python3 Tools/audio/build_audio.py                          # everything
    python3 Tools/audio/build_audio.py --only menu,arc_bolt     # a subset (manifest is merged)
    python3 Tools/audio/build_audio.py --preview-dir /tmp/claude-0/audio_iter   # + spectrogram PNGs

Everything is synthesized here (numpy/scipy) from fixed seeds; OGG Vorbis is written with
oggenc and a fixed stream serial, so re-running reproduces identical files.
Output: EvilCats/Assets/_EvilCats/Audio/Resources/ECAudio/{music,sfx}/*.ogg + audio_manifest.json
After encoding, every file is decoded again and checked (peak <= -1 dBFS, no NaN/DC, loop seams,
leading silence); a table of the measured numbers is printed at the end.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zlib
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "EvilCats", "Assets", "_EvilCats", "Audio", "Resources", "ECAudio")

from synth import FS, undb, todb, hp, fade, rng_for, lufs_momentary_max, circular  # noqa: E402
import checks  # noqa: E402

PEAK_MAX_DB = -1.0          # contract: decoded peak must not exceed this
MUSIC_Q = 4                 # oggenc quality (music, stereo)
SFX_Q = 5                   # oggenc quality (sfx, mono)


# ----------------------------------------------------------------------------- encoding
def encode_ogg(x, path, quality, serial, tmpdir):
    wav = os.path.join(tmpdir, os.path.basename(path) + ".wav")
    sf.write(wav, np.clip(x, -1.0, 1.0), FS, subtype="PCM_24")
    subprocess.run(["oggenc", "-Q", "-q", str(quality), "--serial", str(serial), "-o", path, wav], check=True)
    os.remove(wav)
    y, fs = sf.read(path, always_2d=False)
    assert fs == FS
    return y


def encode_checked(x, path, quality, key, tmpdir):
    """Encode, decode, and if the lossy codec pushed the peak above the contract, pull the gain
    down and re-encode. Returns (decoded audio, applied gain dB)."""
    serial = zlib.crc32(key.encode()) & 0x7FFFFFFF
    gain_db = 0.0
    for _ in range(4):
        y = encode_ogg(x * undb(gain_db), path, quality, serial, tmpdir)
        pk = float(todb(np.max(np.abs(y))))
        if pk <= PEAK_MAX_DB - 0.05:
            return y, gain_db
        gain_db -= (pk - (PEAK_MAX_DB - 0.25))
    raise RuntimeError("could not bring %s under %.1f dBFS" % (path, PEAK_MAX_DB))


# ----------------------------------------------------------------------------- music job
def job_music(sid, preview_dir):
    import music
    t0 = time.time()
    S = music.SONGS[sid]()
    x, info = music.render_song(S, verbose=False)
    tmp = tempfile.mkdtemp(prefix="ecaudio_")
    try:
        path = os.path.join(OUT, "music", sid + ".ogg")
        y, g = encode_checked(x, path, MUSIC_Q, "music/" + sid, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    m = checks.metrics(y)
    row = dict(kind="music", id=sid, file="music/" + sid, dur=m["dur"], peak=m["peak_db"], rms=m["rms_db"],
               lufs=m["lufs"], centroid=m["centroid"], dc=m["dc_db"], nan=m["nan"], size=os.path.getsize(path),
               loop=S.loop, bpm=S.bpm, volume=S.volume, gain_fix=g, limiter=info["limiter_db"], secs=time.time() - t0,
               clip=int(np.sum(np.abs(y) >= 0.999)))
    if S.loop:
        sm = checks.seam(y)
        row.update(seam_ratio=sm["ratio"], seam_rms_step=sm["rms_step_db"],
                   exact_len=abs(len(y) - S.loop_len) == 0)
        row["length"] = S.loop_len / FS
    else:
        row["length"] = len(y) / FS
    # stereo width: side/mid energy ratio
    mid = y.mean(axis=1)
    side = (y[:, 0] - y[:, 1]) * 0.5
    row["width_db"] = float(10 * np.log10(np.sum(side ** 2) / max(np.sum(mid ** 2), 1e-20)))
    if preview_dir:
        checks.preview_png(os.path.join(preview_dir, sid + ".png"), y, "%s  %.1fs  %.1f LUFS" % (sid, m["dur"], m["lufs"]),
                           bar_sec=S.bpb * 60.0 / S.bpm)
    return row


# ----------------------------------------------------------------------------- sfx job
def finalize_sfx(y, loop=False, maxlen=None):
    """DC/rumble filter, trim leading silence (<= 0.5 ms pre-roll), cap the length with a smooth
    fade over the last 30 %, trim the inaudible tail (< -60 dB re peak), tiny fade in/out."""
    y = np.asarray(y, dtype=float)
    if loop:
        y = circular(lambda s: hp(s, 25.0, 2), y, min(0.5, len(y) / FS))
        return y - y.mean()
    y = hp(y, 25.0, 2)
    a = np.abs(y)
    pk = a.max()
    on = int(np.argmax(a > pk * 10 ** (-50 / 20)))
    on = max(0, on - int(0.0005 * FS))
    y = y[on:]
    if maxlen is not None and len(y) > int(maxlen * FS):
        n = int(maxlen * FS)
        y = y[:n]
        k = int(0.3 * n)
        y[n - k:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(1, k + 1) / k)
    a = np.abs(y)
    idx = np.nonzero(a > pk * 10 ** (-60 / 20))[0]
    end = min(len(y), (idx[-1] if len(idx) else len(y) - 1) + int(0.005 * FS))
    y = y[:end]
    y = fade(y, 0.0004, min(0.02, 0.15 * len(y) / FS))
    return y


def job_sfx(sid):
    import sfx
    t0 = time.time()
    fn, nvar, target, pvar, maxv, cool, cat = sfx.SFX_TABLE[sid]
    loop = sid in sfx.LOOPING
    raw = [finalize_sfx(fn(rng_for("sfx", sid, v), v), loop, sfx.MAXLEN.get(sid)) for v in range(nvar)]
    # match variations by loudness, then peak-normalise the group to -1.5 dBFS
    L = [lufs_momentary_max(r) for r in raw]
    ref = float(np.mean(L))
    raw = [r * undb(ref - l) for r, l in zip(raw, L)]
    pk = max(np.max(np.abs(r)) for r in raw)
    raw = [r * (undb(-1.5) / pk) for r in raw]
    tmp = tempfile.mkdtemp(prefix="ecaudio_")
    rows, files = [], []
    try:
        for v, r in enumerate(raw):
            name = sid if nvar == 1 else "%s_%d" % (sid, v)
            path = os.path.join(OUT, "sfx", name + ".ogg")
            y, g = encode_checked(r, path, SFX_Q, "sfx/" + name, tmp)
            m = checks.metrics(y)
            row = dict(kind="sfx", id=name, file="sfx/" + name, dur=m["dur"], peak=m["peak_db"], rms=m["rms_db"],
                       lufs=m["mom_max"], centroid=m["centroid"], dc=m["dc_db"], nan=m["nan"], lead_ms=m["lead_ms"],
                       size=os.path.getsize(path), gain_fix=g, clip=int(np.sum(np.abs(y) >= 0.999)))
            if loop:
                sm = checks.seam(y)
                row.update(seam_ratio=sm["ratio"])
            rows.append(row)
            files.append("sfx/" + name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    measured = float(np.mean([r["lufs"] for r in rows]))
    vol = float(np.clip(undb(target - measured), 0.05, 1.0))
    entry = {"files": files, "volume": round(vol, 2), "pitchVar": pvar, "maxVoices": maxv, "cooldownMs": cool,
             "category": cat}
    if loop:
        entry["loop"] = True
    return dict(id=sid, entry=entry, rows=rows, secs=time.time() - t0, target=target, measured=measured)


# ----------------------------------------------------------------------------- main
def main():
    import music
    import sfx
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma separated ids (music and/or sfx)")
    ap.add_argument("--preview-dir", default="", help="write spectrogram/waveform PNGs of the music here")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    music_ids = [m for m in music.SONGS if not only or m in only]
    sfx_ids = [s for s in sfx.SFX_TABLE if not only or s in only]
    unknown = only - set(music.SONGS) - set(sfx.SFX_TABLE)
    if unknown:
        sys.exit("unknown ids: %s" % ", ".join(sorted(unknown)))
    os.makedirs(os.path.join(OUT, "music"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "sfx"), exist_ok=True)
    if args.preview_dir:
        os.makedirs(args.preview_dir, exist_ok=True)

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        mf = {sid: ex.submit(job_music, sid, args.preview_dir) for sid in music_ids}
        sfut = {sid: ex.submit(job_sfx, sid) for sid in sfx_ids}
        mres = {sid: f.result() for sid, f in mf.items()}
        sres = {sid: f.result() for sid, f in sfut.items()}

    # ------------------------------------------------------------------ manifest (merge for --only)
    man_path = os.path.join(OUT, "audio_manifest.json")
    manifest = {"music": {}, "sfx": {}}
    if only and os.path.exists(man_path):
        with open(man_path) as fh:
            manifest = json.load(fh)
    for sid in music.SONGS:
        if sid in mres:
            r = mres[sid]
            manifest["music"][sid] = {"file": r["file"], "loop": bool(r["loop"]), "bpm": int(round(r["bpm"])),
                                      "volume": r["volume"], "lengthSec": round(r["length"], 3)}
    for sid in sfx.SFX_TABLE:
        if sid in sres:
            manifest["sfx"][sid] = sres[sid]["entry"]
    manifest["music"] = {k: manifest["music"][k] for k in music.SONGS if k in manifest["music"]}
    manifest["sfx"] = {k: manifest["sfx"][k] for k in sfx.SFX_TABLE if k in manifest["sfx"]}
    with open(man_path, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    # ------------------------------------------------------------------ stale files (full builds only)
    if not only:
        want = {f + ".ogg" for f in [e["file"] for e in manifest["music"].values()]}
        want |= {f + ".ogg" for e in manifest["sfx"].values() for f in e["files"]}
        for sub in ("music", "sfx"):
            for fn in os.listdir(os.path.join(OUT, sub)):
                rel = sub + "/" + fn
                if fn.endswith(".ogg") and rel not in want:
                    os.remove(os.path.join(OUT, sub, fn))
                    meta = os.path.join(OUT, sub, fn + ".meta")
                    if os.path.exists(meta):
                        os.remove(meta)
                    print("removed stale", rel)

    # ------------------------------------------------------------------ report
    problems = []
    print("\nMUSIC (decoded OGG)                     loudness = integrated LUFS (BS.1770)")
    print("%-10s %7s %7s %7s %7s %8s %6s %6s %6s %7s" % ("id", "dur s", "peak", "RMS", "LUFS", "centroid", "width", "seam", "limGR", "KB"))
    for sid in music_ids:
        r = mres[sid]
        seam = "%.2f" % r["seam_ratio"] if r["loop"] else "-"
        print("%-10s %7.2f %7.2f %7.2f %7.2f %8.0f %6.1f %6s %6.2f %7.0f" % (sid, r["dur"], r["peak"], r["rms"], r["lufs"], r["centroid"],
              r["width_db"], seam, r["limiter"], r["size"] / 1024))
        if r["peak"] > PEAK_MAX_DB or r["nan"] or r["clip"] or r["dc"] > -60:
            problems.append(sid)
        if r["loop"] and (r["seam_ratio"] > 1.0 or not r["exact_len"]):
            problems.append(sid + " (seam)")
    print("\nSFX (decoded OGG)                       loudness = max momentary LUFS; vol = manifest volume")
    print("%-22s %6s %7s %7s %7s %8s %5s %5s %6s" % ("id", "dur s", "peak", "RMS", "LUFSm", "centroid", "lead", "vol", "KB"))
    for sid in sfx_ids:
        s = sres[sid]
        for r in s["rows"]:
            extra = " seam %.2f" % r["seam_ratio"] if "seam_ratio" in r else ""
            print("%-22s %6.2f %7.2f %7.2f %7.2f %8.0f %5.1f %5.2f %6.1f%s" % (r["id"], r["dur"], r["peak"], r["rms"], r["lufs"],
                  r["centroid"], r["lead_ms"], s["entry"]["volume"], r["size"] / 1024, extra))
            if r["peak"] > PEAK_MAX_DB or r["nan"] or r["clip"] or r["dc"] > -50 or r["lead_ms"] > 5.0:
                problems.append(r["id"])
    msize = sum(r["size"] for r in mres.values())
    ssize = sum(rr["size"] for s in sres.values() for rr in s["rows"])
    mdur = sum(r["dur"] for r in mres.values())
    print("\nmusic: %d files, %.2f MB (%.2f MB/min)   sfx: %d files, %.2f MB   total %.2f MB   build %.0f s" % (
        len(mres), msize / 2 ** 20, (msize / 2 ** 20) / max(mdur / 60, 1e-9), sum(len(s["rows"]) for s in sres.values()),
        ssize / 2 ** 20, (msize + ssize) / 2 ** 20, time.time() - t0))
    all_rows = list(mres.values()) + [rr for s in sres.values() for rr in s["rows"]]
    if all_rows:
        print("worst DC offset %.1f dBFS | clipped samples (|x|>=0.999): %d | NaN/Inf files: %d | max leading silence %.1f ms" % (
            max(r["dc"] for r in all_rows), sum(r["clip"] for r in all_rows), sum(bool(r["nan"]) for r in all_rows),
            max([r.get("lead_ms", 0.0) for r in all_rows])))
    print("manifest:", os.path.relpath(man_path, ROOT))
    if problems:
        print("CHECK FAILURES:", ", ".join(problems))
        sys.exit(1)
    print("all checks passed (peak <= %.1f dBFS, no NaN/clipping/DC, seams, lead-in <= 5 ms)" % PEAK_MAX_DB)


if __name__ == "__main__":
    main()
