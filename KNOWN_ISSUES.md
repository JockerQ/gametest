# Evil Cats — Known Issues and Limitations

Honest list, most important first. "Unverified" means it might work fine, but nobody has seen it run.

## Not yet verified at all
1. **The project has never been opened in Unity, built, or run on a phone.** Everything Unity-related was written and compile-checked without the Unity Editor (`TEST_REPORT.md`). Expect first-run fixes: Console errors, layout details, import settings.
2. **Nobody has played it.** Balance comes from bot simulations, which prove consistency, not fun (`BALANCE.md`).
3. **Nobody has listened to the audio.** It passes objective checks (no clipping, consistent loudness, smooth loops), but the mix and taste are untested.
4. **The art has only been viewed as sprite sheets** and in a script-made layout check, never in the running game.
5. **Performance on phones is unknown.** The simulation is cheap (0.03 ms per step with 140 enemies). Drawing 140 animated enemies with health bars, status icons and up to 40 damage numbers on a low-end phone has not been measured.

## Setup-related risks
6. **URP 2D Renderer creation** calls URP's own internal "create asset" code by reflection (checked against URP 17.3.0 source).
   * If a future URP version changes it, the setup reports it and the game falls back to Unity's built-in renderer, which still draws everything correctly.
   * Manual fix: `Assets → Create → Rendering → URP Asset (with 2D Renderer)`, then assign it in Project Settings → Graphics.
7. **TextMeshPro resources** are imported automatically. Right after the import, setup re-runs itself to create the pixel font assets. If fonts ever look wrong, run `Window → TextMeshPro → Import TMP Essential Resources` and run setup again. At runtime the game can also build the font from the TTF by itself.
8. **The input backend switch** (to the Input System package) needs an Editor restart. The setup offers "Restart now". Builds refuse to run until the restart has happened.
9. **Scenes, settings and `.meta` files are generated on first open**, not stored in the repository. Commit them after the first setup (`NEXT_STEPS.md` step 1).

## Game limitations (by design, for now)
10. **No real ads, purchases, sign-in, cloud save or online leaderboards.**
    * The revive button explains that ads are not configured. It works only with the labelled DEV MOCK in development builds.
    * The Supporter Pack cannot be bought.
    * Records and Daily Challenge scores are **local only**.
11. **English only.** All text is in one string table (`strings_en.json`) ready for translation, but there is no language picker yet.
12. **Banner cosmetics** are shown as a tinted flag icon on the home screen and in the shop. There is no unique banner art, and banners do not appear in battle.
13. **Offline Moon Gold and daily rewards trust the device clock.** Moving the clock backwards never pays extra (accrual restarts), but this is not server-grade anti-cheat.
14. **The Daily Challenge** is "the same for everyone" because the seed comes from the UTC date. Nothing is verified online.
15. **Resuming a run** restarts at the beginning of the wave after the last cleared wave. Progress inside an unfinished wave is not saved, and the resume prompt says so.
16. The **Evil Tower reference video and store pages were never viewed** (blocked in this environment). The design comes from the brief (`docs/REFERENCE_NOTES.md`).

## Balance risks (from simulation)
17. **Chain/control loadout against King Goldenfang (mission 12)** wins about 57 % of bot runs at mid progression. Other loadouts win 75–100 %. The data levers are in `BALANCE.md` §3.
18. **Mission 4 (Powder Night)** is the first difficulty spike (50–75 % bot wins at mid progression).
19. Bots cast Nine-Lives Ward sparingly (1–4 times per run), so simulated difficulty is probably harder than for an active player.
20. Later chain/control missions last up to about 12.5 minutes, above the 6–10 minute target.

## Presentation details to check on a device
21. The smallest text uses 10-unit pixel-font sizes (about 10 dp). Check readability on small phones.
22. Tapping an enemy selects the nearest enemy within about one unit. In dense crowds it may pick a neighbour.
23. Hub screens rebuild completely after a purchase or claim; the scroll position is kept. It is simple and robust, but may cost a frame on slow phones.
24. While aiming Arc Storm, the battle runs at 30 % speed rather than pausing. Adjust `AimSlowdown` in `BattleController` if testers prefer a full pause.
