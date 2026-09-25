# Evil Cats — Next Steps (in order)

The game's rules, content, art, audio, Unity scripts and tools are complete. What is left needs
**Unity on your PC**, **real phones** and **people**. The steps are ordered so that each one finds
problems before the next step depends on it.

## 1. First open in Unity (you, about 1 hour)
1. Follow `README.md` Parts 1–4: install Unity 6.3 LTS with Android Build Support, open `EvilCats/`, run **Evil Cats → 1. Set Up Project**, restart if asked, and press Play in the Boot scene.
2. Fix any Console errors. The code compiles against reference assemblies, but it has never run inside Unity, so a few first-run fixes are likely (see `KNOWN_ISSUES.md`).
3. **Commit** what Unity and the setup created: the `.meta` files, `Assets/_EvilCats/Scenes`, `Assets/_EvilCats/Settings`, the fonts and materials, and `ProjectSettings/*.asset`. After that, other machines and CI start from a ready project.

## 2. Automated tests inside Unity (about 15 min)
* `Window → General → Test Runner` → run **EditMode** (Core rules and asset checks) and **PlayMode** (boot, battle, hub screens, saves).
* Write the results into `TEST_REPORT.md`.

## 3. Play-through in the Editor (about 2 hours)
Use the Game view at several shapes: 1080×2400, 1080×1920, 1440×3200 and a 4:3 tablet. Check:

* **First launch:**
  * loading steps, then Continue as Guest, the story (skippable) and Home;
  * the sign-in button says it is not configured.
* **Mission 1:**
  * tutorial hints appear once;
  * the Crown slot opens with Ember Maw on wave 3;
  * levelling up offers perks;
  * victory unlocks Frost Whisker.
* **HUD:**
  * nothing overlaps;
  * the barrier strip shows on the health bar;
  * the 2× button and target button work;
  * hold an upgrade to see details;
  * Arc Storm aim, strike and cancel;
  * tapping an enemy shows its info.
* **Mission 2:** the Base slot opens and the station choice appears.
* **Bosses** (use a save with missions cleared, or play through):
  * red charge lane, barrage wedge and volley glow with the stagger meter;
  * boss intro on first meeting.
* **Pause, background and quit:**
  * Esc (back) pauses;
  * minimise the Editor while playing, and it returns paused;
  * quit a run in the middle, reopen, and the resume prompt restarts at the next wave.
* **Hub:**
  * buy tree nodes and station tiers;
  * claim the login reward and objectives;
  * collect offline gold (change your PC clock forward to test, then back);
  * reset progress.

## 4. On real phones (about half a day)
1. Build with **Evil Cats → Build → Android APK (development)**. Install on 2–3 phones: one low-end with 2–3 GB of RAM, one mid-range and one recent.
2. Test:
   * touch feel, safe areas and notches, the Android back button;
   * incoming calls and backgrounding;
   * rotation, which should stay portrait;
   * text readability at arm's length.
3. **Profile** with Unity Profiler over USB on a crowded late wave at 2×. Look at:
   * CPU and GPU frame time (the target is a steady 60 fps, and 30 fps as the floor on low-end devices);
   * garbage-collection spikes;
   * memory.

   The simulation itself is cheap (`BALANCE.md` §5). If drawing is slow, the first levers are: lower `arena.maxAlive`, fewer damage numbers, and fewer status icons.
4. Check battery and heat over a 10-minute mission.

## 5. Listen and look (you or a friend, about 1 hour)
* Nobody has listened to the music and sound effects yet. Adjust volumes in `Audio/Resources/ECAudio/audio_manifest.json`, or change and re-render them in `Tools/audio`.
* Look at every screen in the running game and note anything ugly or unclear.

## 6. Human playtests (5–10 people, 1 week)
* Watch first-time players without helping. Watch for: do they understand Arc Storm aiming, the target button and perk choices?
* Difficulty spots to watch (`BALANCE.md` §3): **mission 4 (Powder Night)** and **the final boss with a chain/control loadout**.
* Tune the JSON numbers, then re-run the simulator (`Tools/EvilCats.Sim`) and the tests.

## 7. Decide what the commercial version includes (you)
Every item below is **optional**. The game is complete without them. Each needs accounts, legal texts and updates to the store's Data safety form. **None of these was set up, and nothing was bought.**

| Service | Suggested option | Cost to you | Where in the code |
|---|---|---|---|
| Rewarded ads (revive) | Google AdMob or Unity LevelPlay, with Google's consent SDK (UMP) | free SDK; revenue share | `Scripts/Game/Services/Services.cs` → implement `IAdsService` |
| Purchases (Supporter Pack, cosmetics) | Unity IAP (Google Play Billing) | Google's fee on sales | implement `IPurchaseService`; the product id is `supporter_pack` |
| Analytics | Unity Analytics, GameAnalytics or Firebase | free tiers | implement `IAnalyticsService` (events `battle_start` and `battle_end` already exist) |
| Sign-in and cloud save | Google Play Games Services | free | `IAuthService`, `ICloudSaveService` |
| Online leaderboards | Play Games leaderboards | free | `ILeaderboardService` |

**Rules to keep** (they are also in the code comments):
* grant a revive **only** when the ad reports `Completed`;
* never show a price that did not come from the store;
* never show a purchase as successful until the store confirms it.

## 8. CI with Unity (optional)
* `.github/workflows/ci.yml` already runs the rule tests, the determinism check and the compile check on every push. It needs no Unity licence.
* `.github/workflows/unity.yml` (manual) can run the Unity tests and build an APK with GameCI. It needs `UNITY_LICENSE`, `UNITY_EMAIL` and `UNITY_PASSWORD` as **repository secrets** (GitHub → Settings → Secrets and variables → Actions). Never put them in files or chats.

## 9. Release
Follow `RELEASE_CHECKLIST.md`. The advertising plan is in `store/AD_BUDGET_PLAN.md`. It stays unspent until you approve it.

## Costs you will meet (outside the $2,000 advertising budget; please confirm current prices)

| Item | Typical cost | Needed for |
|---|---|---|
| Google Play developer account | one-time registration fee (US$25 when last checked) | publishing on Google Play |
| Unity | Personal plan is free below Unity's revenue/funding threshold; check the current terms | building the game |
| Privacy-policy hosting | free (e.g. GitHub Pages) | the store listing |
| Test phones | whatever you have | step 4 |
| GitHub Actions minutes | free on public repos; limited free minutes on private ones | CI |

## For a future cloud session (if you want me to continue)
* In the environment's **network settings**, allow Unity's download and licence hosts. Then a session could install Unity, run the tests and build an APK.
* Allowing `youtube.com` and `play.google.com` would let a session read the reference pages. Watching video frames would need a video-analysis service, which may cost credits and would need your approval first.
