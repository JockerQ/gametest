# Evil Cats — Execution Plan

## Environment facts (session of 2026-09-25)

* Work happens in a **Linux cloud container**, not on the owner's Windows PC.
* **No Unity Editor** is installed, and the network policy blocks Unity's download,
  package-registry and licensing servers. The Editor can't be opened, Play Mode tests
  can't run, and **no APK can be built in this session**. Building happens on the
  owner's PC (see README) or in CI once a Unity licence secret is configured.
* Available here: .NET 8 SDK, Python 3.11 (numpy, Pillow, scipy, soundfile), ffmpeg,
  NuGet, PyPI and GitHub (including Unity's official `UnityCsReference` source, the
  `Unity-Technologies/Graphics` repo and package mirrors used to verify APIs).
* Versions verified against real Unity 6.3 sources/manifests: **Unity 6000.3 LTS**
  (latest tag 6000.3.25f1), URP **17.3.0**, Input System **1.20.0**, uGUI **2.0.0**
  (includes TextMeshPro), Test Framework **1.6.0**, Newtonsoft JSON **3.2.2**.

## Architecture

```
EvilCats/                    Unity project (open this folder in Unity Hub)
  Assets/_EvilCats/
    Scripts/Core/            EvilCats.Core — pure C#, no UnityEngine (noEngineReferences)
                             simulation, rules, economy, progression, saving logic
    Scripts/Game/            EvilCats.Game — Unity layer: scenes, presentation, UI, audio,
                             input, file storage, lifecycle, service adapters
    Editor/                  EvilCats.Editor — idempotent project setup, validators, builds
    Data/Resources/ECData/   JSON content (modules, enemies, bosses, perks, missions, …)
    Art/Resources/ECArt/     generated sprite atlases + JSON metadata
    Audio/Resources/ECAudio/ generated music/SFX + manifest
    UI/Resources/ECUI/       fonts, UI strings (localisation-ready)
    Tests/EditMode|PlayMode  Unity Test Framework tests
Tools/
  EvilCats.Core.Tests/       dotnet NUnit tests compiling the same Core sources
  EvilCats.Sim/              headless mission simulator + balance reports
  art/  audio/               reproducible asset generators (Python)
  UnityCompileCheck/         compiles Unity-layer code against reference assemblies
docs/                        design, balance, asset contract, reports
```

Key decisions:

1. **Deterministic fixed-step simulation** (30 ticks/s) in `EvilCats.Core`. 2× speed runs
   two ticks per frame-step, so outcomes, spawns, rewards and cooldown ratios are
   identical at 1× and 2×. The Unity layer only renders events and state.
2. **Data-driven content** in JSON with a validator (duplicate IDs, missing references,
   broken unlock chains, impossible perk requirements, value ranges). Stable string IDs
   are used everywhere, including save files.
3. **Runtime-built UI** (uGUI + TextMeshPro) from code, with a shared theme and a string
   table, so no hand-made prefabs or manual Editor clicks are required.
4. **One input path:** everything goes through the EventSystem pointer events, backed by
   the Input System package (with a guarded fallback while the backend switch awaits an
   Editor restart). Mouse works in the Editor and touch works on Android.
5. **Services behind adapters** (ads, purchases, analytics, auth, cloud save,
   leaderboards). The defaults are honest "not configured" implementations. Development
   mocks are labelled and compiled out of release builds.
6. **Saves:** versioned JSON with checksum, atomic replace plus a backup copy, migrations,
   and an idempotent reward ledger. Run checkpoints are taken at completed waves.

## Milestones (mapped to the brief)

| # | Goal | Status (25 Sep 2026; details in TEST_REPORT.md) |
|---|---|---|
| M1 | End-to-end slice: hero, arena, 3 modules, 3 enemies, 10 perks, 2 abilities, short mission, boss, audio, win/lose, saving | Built. Rules tested (87 tests); Unity code compiles. **Not yet run in Unity.** |
| M2 | Validate combat: routes 3 vs 5, target priority, all slots, synergies, upgrades, boss counterplay, HUD, pacing, retry | Validated in simulation: 3 vs 5 paths, priorities, slots, synergies, upgrades, boss counterplay, pacing. HUD and retry built, not yet seen running. |
| M3 | Full content: 2 biomes, 12 missions, 6 modules, 8 enemies, 3 bosses, 30 perks, progression, daily, endless, rewards, achievements | All content present and validated (2 biomes, 12 missions, 6 stations, 8 enemies, 3 bosses, 30 perks, daily, endless, 22 achievements). |
| M4 | Presentation: final art, animation, audio, accessibility, tutorials, recovery states | Art (979 sprites), audio (7 tracks, 47 effects), accessibility settings, tutorial hints and recovery states built. Not yet viewed or heard in the game. |
| M5 | Android quality: automated tests, save/resume stress, performance, build verification | Automated tests and compile check pass here; Unity tests, device, performance and build verification are **blocked** (no Unity or phone). |
| M6 | Private-release prep: docs, licences, store materials, known limitations | Docs, licences, store drafts, release checklist and ad plan (unspent) done. |

Because the core logic has no Unity dependency, M1–M3 logic is built and tested here
first. The Unity layer, art and audio are built alongside it. The parts that need the
Unity Editor or a phone are listed with exact steps in NEXT_STEPS.md.
