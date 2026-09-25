# Evil Cats

An original portrait 2D dark-fantasy defence game for Android, starring **Arc Light Cat**.
Enemies come from every direction. Your citadel's stations and Arc Light Cat fight automatically,
and you decide what to buy, which perks to take, where to strike with Arc Storm and when to raise
Nine-Lives Ward.

* 12 missions in 2 biomes, 3 bosses, 8 enemy types, 6 stations, 30 perks.
* Daily Challenge, Endless, 7-day login, daily objectives, offline Moon Gold and 22 achievements.
* Plays **fully offline**. Ads, purchases and sign-in are **not configured**, and the game says so honestly.
* Built with **Unity 6.3 LTS** (6000.3), URP 2D Renderer, uGUI + TextMeshPro and the Input System.

> **Honest status.** The whole game was written and checked **without opening Unity**; Unity could not run
> where it was built. The game rules were tested (89 automated tests) and every Unity script compiles.
> The project has **not yet been opened in Unity, built, or played on a phone.** Expect some first-run
> problems to fix. See `TEST_REPORT.md` and `KNOWN_ISSUES.md`.

---

## Part 1 — Play it in Unity on Windows (about 1 hour the first time)

### 1. Install Unity
1. Download **Unity Hub** from <https://unity.com/download> and install it. Sign in, or create a free Unity account. The free Personal licence is fine.
2. In Unity Hub, open **Installs → Install Editor**. Choose the newest **Unity 6.3 LTS (6000.3.x)**. The project was made for 6000.3.25f1, and any 6000.3 version works.
3. On the modules screen, tick **Android Build Support** together with its **OpenJDK** and **Android SDK & NDK Tools**. You need these for phone builds.
4. Wait for the install to finish. It is several GB.

### 2. Get the project
* **With Git:** `git clone` this repository.
* **Without Git:** on the GitHub page choose **Code → Download ZIP**, then unzip it to a short path such as `C:\Games\EvilCats-src`. Long Windows paths can cause import errors.

### 3. Open it
1. In Unity Hub choose **Add → Add project from disk** and pick the **`EvilCats`** folder inside the repository (the folder that contains `Assets` and `Packages`).
2. Open it. The first import downloads the packages and takes several minutes.
3. If Unity offers to upgrade the project to your exact 6000.3 version, accept.

### 4. One-click setup
In the Unity menu bar choose **Evil Cats → 1. Set Up Project**. It:
* applies pixel-perfect import settings;
* imports TextMeshPro resources and creates the pixel font assets;
* creates the URP 2D renderer and the scenes (Boot, Hub, Battle);
* fills in the player settings (portrait, Android 7.0+, 64-bit) and switches input to the Input System package.

If it says the input backend changed, click **Restart now**. Running it again is always safe.
The Console (`Window → General → Console`) shows a line for every step: `Done`, `AlreadyOk`, `Pending` or `Failed`.

### 5. Play
1. Open **Evil Cats → Open Boot Scene**.
2. In the **Game** tab, choose a phone-shaped resolution from the drop-down, for example add **1080×2400 Portrait**.
3. Press **Play** ▶. The mouse works as touch: click to tap, drag to aim Arc Storm, **Esc** acts as the Android back button.

### 6. Check everything is healthy
* **Evil Cats → 2. Validate Content, Art and Audio** should report no problems.
* **Window → General → Test Runner:** run **EditMode** and **PlayMode**. Please write the results into `TEST_REPORT.md`.

## Part 2 — Put it on your Android phone
1. On the phone, open **Settings → About phone** and tap **Build number** 7 times to enable Developer options. Then enable **Developer options → USB debugging**.
2. Connect the phone with a USB cable and allow the computer when the phone asks.
3. In Unity: **File → Build Profiles** (or Build Settings) → **Android → Switch Platform**. The first switch takes a while.
4. Choose **Evil Cats → Build → Android APK (development)**. The APK appears in `EvilCats/Builds/Android/`.
5. Install it in one of two ways:
   * use **Build And Run** in Build Profiles, or
   * copy the APK to the phone and open it (allow "install unknown apps").

A development build is signed with Unity's debug key. It is for your own testing only.

## Part 3 — Where things are

| Path | What |
|---|---|
| `EvilCats/` | the Unity project |
| `EvilCats/Assets/_EvilCats/Scripts/Core` | game rules: simulation, economy, saves (pure C#, tested) |
| `EvilCats/Assets/_EvilCats/Scripts/Game` | Unity layer: rendering, HUD, menus, audio, input |
| `EvilCats/Assets/_EvilCats/Editor` | setup, import, build and validation tools |
| `EvilCats/Assets/_EvilCats/Data/Resources/ECData` | **all game numbers and text** (JSON) |
| `EvilCats/Assets/_EvilCats/Art`, `Audio`, `UI` | generated art, music, sounds, font |
| `Tools/EvilCats.Core.Tests` | runs the 89 rule tests with plain .NET |
| `Tools/EvilCats.Sim` | balance simulator |
| `Tools/UnityCompileCheck` | compiles the Unity scripts without Unity |
| `Tools/art`, `Tools/audio` | regenerate the art and audio (Python) |
| `docs/` | plan, asset spec, reference notes, simulation outputs |
| `store/` | store graphics, listing draft, advertising budget plan |

### Change the game
* **Balance and text:** edit the JSON in `Data/Resources/ECData`, then run *Validate Content*. `BALANCE.md` explains every number.
* **Art:** `python Tools/art/build_all.py`. **Audio:** `python Tools/audio/build_audio.py`. Both need Python 3.11 with `numpy`, `pillow`, `scipy` and `soundfile`; audio also needs `oggenc`.
* **Rule tests** (needs the free .NET 8 SDK): `dotnet test Tools/EvilCats.Core.Tests`.

### Your save file
* **In the Editor:** **Evil Cats → Save Data → Show Save Folder** or **Delete Editor Save**.
* **On the phone:** in-game **Settings → Reset progress** (asks twice).

## Part 4 — What is not included (on purpose)
* **No real ads, purchases, sign-in, cloud save or online leaderboards.** They sit behind adapters that say "not configured" in the game.
* The Supporter Pack in the shop is visible but cannot be bought.
* The revive button explains that rewarded ads are not configured.
* Nothing is published and no money is spent.

`NEXT_STEPS.md` explains how to connect real services and what that costs. `RELEASE_CHECKLIST.md` lists what a commercial release needs.

## Documents

| File | Contents |
|---|---|
| `GAME_DESIGN.md` | the whole design: loop, hero, stations, perks, enemies, bosses, missions, screens |
| `BALANCE.md` | formulas, data tables, simulation results and known balance risks |
| `TEST_REPORT.md` | what was tested, what passed, what is blocked |
| `KNOWN_ISSUES.md` | limitations and risks |
| `RELEASE_CHECKLIST.md` | everything needed before a store release |
| `NEXT_STEPS.md` | what to do next, in order |
| `ASSET_MANIFEST.csv` | every asset, its origin and licence |
| `store/` | listing draft, graphics and a $2,000 advertising plan (not spent) |

## Licences
* **Code, art, music and sound effects** are original to this project. They are generated by the project's own tools; see `ASSET_MANIFEST.csv`.
* **Font:** Pixelify Sans, SIL Open Font License 1.1. The licence file sits next to the font.
* **Newtonsoft.Json:** MIT.
* **Unity and its packages:** Unity's terms.
