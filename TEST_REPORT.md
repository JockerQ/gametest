# Evil Cats — Test Report

Date: 25 September 2026. Environment: a Linux cloud container **without the Unity Editor**. Unity's
download and licence servers are blocked there, so no Unity build or Unity test has run. This report
separates what actually ran from what could not run.

| Status | Meaning |
|---|---|
| **PASSED** | ran here, and the result is recorded below |
| **FAILED** | ran here and failed (none currently) |
| **BLOCKED** | cannot run in this environment; needs Unity and/or a phone |
| **NOT RUN** | could run elsewhere but has not been done yet |

## Summary

| Area | What | Status | Evidence |
|---|---|---|---|
| Game rules (Core) | 89 unit tests covering stats, costs, targeting, combat caps, perks, battle flow, bosses, checkpoints, saves, meta progression and the idempotent ledger | **PASSED** (89/89) | `cd Tools/EvilCats.Core.Tests && dotnet test` |
| Determinism | same seed at 1× and 2× gives an identical result | **PASSED** | `docs/sim/speed_invariance.txt` |
| Balance | 12 missions × 4 bot builds × 4 seeds | **PASSED with one finding** (below) | `docs/sim/sweep_mid.txt`, `BALANCE.md` |
| Campaign pacing | a simulated player finishes all 12 missions in 12–14 runs (2 builds, 2 seeds each) | **PASSED** | `docs/sim/campaign_*.txt` |
| Paths setting | three versus five paths | **PASSED** (3 paths is easier and less crowded) | `docs/sim/routes.txt` |
| Simulation load | 140 enemies held at the cap for 110 s | **PASSED** (mean 0.032 ms per step on a desktop CPU) | `docs/sim/stress.txt` |
| Unity scripts compile | Game code as Editor, Android release player and legacy-input variants; Editor tools; Unity-only tests | **PASSED** (with the limits described below) | `Tools/UnityCompileCheck/check.sh` |
| Asset completeness | every sprite, animation, sound and text key the code and data ask for exists | **PASSED** (Python replica of the Unity asset tests) | see "Asset checks" |
| Audio files | decode, peak, loudness, clipping and loop seams of all 70 files | **PASSED** (0 problems) | `docs/sim/audio_checks.txt` |
| Font coverage | every non-ASCII character in the game code and strings exists in both Pixelify Sans fonts | **PASSED** (after replacing ★ and ✓, see "Code review") | fontTools check |
| Code review | an independent review of the Unity layer and tools | **21 findings, all fixed** (below); the fixes compile and the rule fixes have tests, but none has been seen running | see "Code review" |
| Unity EditMode tests | `Tests/EditMode` (Core tests again, plus asset/import checks) | **BLOCKED** (no Unity Editor) | — |
| Unity PlayMode tests | boot, battle with pause and 2×, exactly-once result, every hub screen, save round trip | **BLOCKED** | — |
| Project setup script | `Evil Cats > 1. Set Up Project` | **BLOCKED** (never executed) | — |
| Android build | APK or AAB | **BLOCKED** | — |
| Play on a phone | gameplay, touch, safe area, back button, pause on background, performance | **NOT RUN** (no device) | — |
| Frame rate / memory / battery | Unity Profiler on a device | **NOT RUN** | — |
| Listening test | music and sound effects heard by a person | **NOT RUN** | — |
| Visual check in the engine | how the scene and UI look in Unity | **NOT RUN** (only atlases and a script-made layout check were viewed) | — |
| Fun and difficulty | human playtest | **NOT RUN** | — |

## Details

### Core unit tests: 89 passed
Command: `dotnet test Tools/EvilCats.Core.Tests -c Release`. The tests compile the same source files that
Unity compiles (`Assets/_EvilCats/Scripts/Core`) as C# 9 against .NET Standard 2.1, like Unity 6.

The areas covered include:
* **Stats and economy:**
  * stat stacking;
  * max-health healing rule;
  * slot modifiers;
  * synergies requiring adjacency;
  * upgrade cost formula `ceil(base × 1.16^level)`;
  * XP formula `30 + 20L + 5L²`;
  * crit cap.
* **Targeting:** Nearest, Strongest, Ranged Threat.
* **Control and chains:**
  * a chain never hits the same enemy twice;
  * chain falloff;
  * slow caps;
  * stun diminishing returns;
  * boss control resistance;
  * burn stack cap;
  * freeze immunity.
* **Barriers:** absorb before health, and the 60 % cap.
* **Perks:** perk eligibility and fallback rewards.
* **Waves:**
  * wave timing inside 18–25 s;
  * elites at 5/10/15 and the boss at 20;
  * stall recovery;
  * summon safety distance.
* **Checkpoints and settings:**
  * checkpoint resume restores the exact state;
  * the route-layout setting is applied and survives resume;
  * a Daily Challenge resumed or finished after midnight UTC still counts for its own day.
* **Slots:** a newly unlocked slot never receives a module that is already equipped elsewhere.
* **Saves:**
  * round trip;
  * corrupt primary recovers from the backup;
  * checksum tamper detection;
  * v1 → v2 migration;
  * newer-version protection;
  * atomic write with backup.
* **Meta progression:**
  * rewards applied exactly once;
  * first clears;
  * defeat rewards;
  * mission unlock order;
  * permanent-tree prerequisites;
  * module unlocks;
  * loadout swaps.
* **Daily and time-based rewards:**
  * attendance never punishes missed days;
  * offline gold is capped at 8 h, and a clock moved back grants nothing;
  * daily objectives and the daily challenge are reproducible and pay once per day.
* **Profile:**
  * cosmetics never change stats;
  * display-name validation;
  * checkpoint replay cannot duplicate rewards.

### Balance finding
**Chain/control against King Goldenfang (mission 12).** At mid progression this build wins about 57 % of runs (12 of 21 seeds). The other builds win 75–100 %. `BALANCE.md` §3 lists the data levers. This is left for human playtesting to confirm.

### Unity compile check: what it proves and what it doesn't
`Tools/UnityCompileCheck/check.sh` compiles the game scripts with the normal .NET compiler against:
* the UnityEngine 2021.3 reference assemblies from NuGet;
* the **real source** of uGUI (1.0.0) and TextMeshPro (3.2.0-pre.9) from public package mirrors;
* hand-written declarations for the few Input System, UnityEditor and test-runner members used.

Each of those declarations was checked against Unity's 6000.3 C# reference source or the package source.

* **It proves:** no syntax or type errors; every API the scripts call exists with the right shape; and the Android-only and editor-only code paths compile.
* **It does not prove:**
  * behaviour at runtime;
  * exact Unity 6 differences in uGUI 2.0 or TextMeshPro, where the parts used have been stable for years;
  * shader, material or import behaviour;
  * that `Set Up Project` succeeds.

### Asset checks (run with Python against the real files)
These are the same checks the Unity EditMode tests perform:
* Every sprite and animation named by the content data (stations × 3 tiers, perks, enemies and elite variants, bosses, hero outfits, avatars, biomes, citadel anchors) exists. The fixed effect and UI names also exist: 0 missing.
* Every sprite name written in the game code exists: 0 missing. Names completed at runtime, such as `"citadel/cracks" + level`, are excluded.
* Every text key used in the code exists in `strings_en.json` (616 strings): 0 missing.
* Every sound and music id used in the code exists in the audio manifest: 0 missing.

### Code review (second pass over the Unity layer)
A separate review read the Unity-side code looking for bugs that a compiler cannot find. Every
finding was checked against the code (and, where it concerned Unity or TextMeshPro behaviour, against
their published source) before fixing. All 21 are fixed:

| # | Problem | Fix |
|---|---|---|
| 1 | No AudioListener anywhere: the game would be silent | one listener on the persistent app object; stray camera listeners are disabled |
| 2 | `GetComponent() ?? AddComponent()` fails in the Editor (Unity's "fake null"), breaking UI layout and the camera rig | `TryGetComponent` |
| 3 | Settings sliders: fill and handle sized wrongly | fill stretched with zero size offset; handle 20 wide, full height |
| 4 | A tutorial hint could cover the Arc Storm aim bar and block taps | hints hide while aiming and return afterwards; hint and aim-bar backgrounds let taps through |
| 5 | Hints were marked "seen" before they appeared, could be lost, and ran out their timer behind dialogs | marked seen when shown; queue kept; timer waits while a dialog is open |
| 6 | Enemies killed by Arc Storm vanished without their death animation | events from player actions are shown immediately; views of just-killed enemies are kept |
| 7 | A Powder Rat's warning ring stayed after the rat was stunned | one ring per enemy, removed on interrupt or explosion |
| 8 | Music crossfades dropped the old track too fast | linear fade-out from its starting volume |
| 9 | ★ and ✓ are not in the pixel font (would show as boxes) | "Elite {name}" text and a check icon |
| 10 | Name field had no text cursor | input field configured before it is enabled (TextMeshPro creates the cursor then) |
| 11 | After "Reset progress" the old "save recovered" notice could reappear | reset records a new-profile load result |
| 12 | A Daily Challenge resumed after midnight rebuilt the wrong day's challenge | the checkpoint stores the challenge date; results count for that day |
| 13 | A slot unlock could equip a module already used in another slot | the player chooses another module instead (test added) |
| 14 | Command-line setup reported success while still waiting for TextMeshPro | exits with an error unless finished; in command-line mode the TextMeshPro resources are now unpacked synchronously |
| 15 | Setup overwrote your own version, icons, target API, architectures and internet setting on every build, and a build could close an unsaved scene | only fills in defaults; builds ask to save the open scene first and never discard unsaved changes |
| 16 | Home screen citadel was cut off at the bottom | moved up; panel 20 units taller |
| 17 | Long player names overlapped the Moon Gold counter | narrower name field with auto-size |
| 18 | Citadel crack overlay had the same draw order as the crown station | unique draw orders |
| 19 | Powder Rat never showed its charge animation; the boss shield pose was not held; a boss without an idle animation walked in place | clips follow the fuse state; shield pose held; standing bosses stop their walk cycle |
| 20 | Tiny drag threshold on high-resolution phones turned shaky taps into drags | about 2.5 mm, based on screen DPI |
| 21 | The PlayMode battle test could fail if the Editor window lost focus | explicit Pause/Resume and a switch that tests use to turn off auto-pause |

The command-line TextMeshPro unpacking (finding 14) was tested outside Unity against the real
"TMP Essential Resources" package: it wrote the same 85 files, byte for byte, as a standard tar
extraction, and a second run wrote nothing. The Unity import that follows it has not been run.

### Layout check
A script composed the real atlases at the scale the camera code computes for a 1080×2400 phone, with the HUD areas blocked out. The arena fills the width between the top bar and the dock. The citadel, hero and stations sit on their anchors, and enemy sizes read well.

This is a proportion check only. It is **not** a screenshot of the game and was not published as one.

## How to run the blocked tests (on your PC)
1. Open the project in Unity 6000.3 LTS and run `Evil Cats > 1. Set Up Project` (see README.md).
2. Open `Window > General > Test Runner`, then run **EditMode** and **PlayMode**.
3. Build a development APK (`Evil Cats > Build > Android APK (development)`) and play it on a phone.
4. Record the results in this file: replace BLOCKED or NOT RUN with PASSED or FAILED, and add notes.
