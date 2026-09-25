"""
Build every Evil Cats sprite atlas.

    python Tools/art/build_all.py                 # everything
    python Tools/art/build_all.py --only hero,fx  # just some atlases (faster iteration)

Each generator module exposes build(reg: eclib.Registry). Output goes to
EvilCats/Assets/_EvilCats/Art/Resources/ECArt (atlases + JSON) and Tools/art/previews
(contact sheets for review). Provenance is written to Tools/art/provenance.csv.
"""
import argparse
import importlib
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eclib  # noqa: E402

GENERATORS = [
    "gen_hero", "gen_stations",          # Arc Light Cat, station modules, operator portraits
    "gen_enemies", "gen_bosses",         # Golden Collar Order
    "gen_citadel", "gen_env", "gen_fx",  # world + effects
    "gen_ui", "gen_icons",               # interface kit, icons, perk icons, emblem
]
POST = ["gen_marketing"]  # runs after atlases are written (launcher icons, store art)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma separated atlas names to write")
    ap.add_argument("--skip-post", action="store_true")
    args = ap.parse_args()
    only = [s.strip() for s in args.only.split(",") if s.strip()] or None

    reg = eclib.Registry()
    failures = []
    for name in GENERATORS:
        path = os.path.join(HERE, name + ".py")
        if not os.path.exists(path):
            print(f"[skip] {name}.py not present yet")
            continue
        t = time.time()
        try:
            mod = importlib.import_module(name)
            mod.build(reg)
            print(f"[ok] {name} ({time.time() - t:.1f}s)")
        except Exception:
            failures.append(name)
            print(f"[FAIL] {name}")
            traceback.print_exc()
    reg.write(only=only)
    if not only:
        reg.write_provenance(os.path.join(HERE, "provenance.csv"))
    if not args.skip_post and (not only or "marketing" in only):
        for name in POST:
            if os.path.exists(os.path.join(HERE, name + ".py")):
                try:
                    importlib.import_module(name).export()
                    print(f"[ok] {name}")
                except Exception:
                    failures.append(name)
                    traceback.print_exc()
    if failures:
        print("FAILED:", ", ".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    main()
