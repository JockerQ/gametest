# Evil Cats — Release Checklist

Two different things can be shipped. Keep them apart:

| | **Playable offline build** (exists now) | **Commercially configured release** (not done) |
|---|---|---|
| What | the complete game, offline, guest profile, no services | the same game published on Google Play, optionally with ads, purchases and sign-in |
| Signing | Unity debug key (development APK) | **your** upload keystore plus Google Play App Signing |
| Services | adapters show "not configured" | real SDKs behind the adapters, with consent and legal texts |
| Status | code complete; **not yet opened in Unity, built or played on a phone** | needs every item below |

Tick each item. Anything marked **(you)** needs your accounts, money or legal decisions, and was intentionally not done for you.

## A. Before any public build
- [ ] Every step in `NEXT_STEPS.md` 1–6 is done, and `TEST_REPORT.md` has no BLOCKED or NOT RUN rows left for Unity, device, audio or playtest.
- [ ] Unity Test Runner: EditMode and PlayMode all green.
- [ ] Played on at least 3 phones, including a low-end one. Steady frame rate, no crashes, no overheating in a 10-minute mission.
- [ ] Every screen checked on 16:9, 19.5:9 and 20:9 phones and on a tablet. No clipped text, and nothing hidden under notches.
- [ ] Back button, backgrounding, incoming call and low-battery mode behave as expected. Progress survives killing the app mid-wave.

## B. Identity (you)
- [ ] Final **app name** (Google Play title: 30 characters maximum). Check trademarks for "Evil Cats" in your markets.
- [ ] **Application id** you own, such as `com.yourname.evilcats`. Set it in Project Settings → Player → Android → Package Name. **It can never change after publishing.** The build script refuses to make a release with the placeholder `com.evilcats.arclightcat`.
- [ ] Company name, version name (`GameApp.Version` and PlayerSettings) and version code (increase by 1 for every upload).

## C. Signing (you)
- [ ] Create an **upload keystore**: Unity → Project Settings → Player → Android → Publishing Settings → Keystore Manager, or `keytool`. Pick strong passwords.
- [ ] **Back up** the keystore and its passwords offline, in two places. Losing it blocks updates unless Google resets the upload key.
- [ ] Enable **Play App Signing** in Play Console.
- [ ] Build the release bundle with the environment variables `EC_ANDROID_KEYSTORE`, `EC_ANDROID_KEYSTORE_PASS`, `EC_ANDROID_KEY_ALIAS` and `EC_ANDROID_KEY_PASS`, then run `Evil Cats → Build → Android App Bundle`. Never commit the keystore or the passwords; `.gitignore` excludes `*.keystore` and `*.jks`.

## D. Technical requirements
- [ ] **Target API level** meets Google Play's current requirement. Unity's "Automatic (highest installed)" setting is used; make sure the installed Android SDK is recent enough.
- [ ] 64-bit (ARM64, IL2CPP) is already set by the setup script. Minimum Android 7.0 (API 24).
- [ ] App size is well under Google Play's limits. Check the `.aab` size in `Builds/Android/last-build-report.txt`.
- [ ] Permissions: the game needs **no internet permission** (disabled). Vibration is the only extra permission.
- [ ] Android vitals after internal testing: crash rate and ANR rate below Google's bad-behaviour thresholds.

## E. Google Play Console (you)
- [ ] Developer account; see the fee in `NEXT_STEPS.md`.
- [ ] **New personal accounts** may have to run a **closed test** (a minimum number of testers for a minimum number of days) before production access. Check the current rule in Play Console.
- [ ] **Store listing**:
  * title, short description and full description (the draft is in `store/STORE_LISTING.md`);
  * 512×512 icon (`Art/Icons/launcher_512.png`) and 1024×500 feature graphic (`store/feature_graphic_1024x500.png`);
  * **at least 2 real phone screenshots captured from the game**. Do not use mock-ups. None exist yet because the game has not run.
- [ ] **Category:** Games → Strategy (tower defence). Add a contact email.
- [ ] **Privacy policy URL.** The draft is in `store/PRIVACY_POLICY_DRAFT.md`. Host it, for example on GitHub Pages, and update it if you add any SDK.
- [ ] **Content rating** questionnaire (IARC): cartoon fantasy violence, no blood, no gambling, no user-generated content.
- [ ] **Target audience.** If you target children under 13, the Families policy applies and restricts ads and SDKs. The game's tone suits "13+" or "everyone".
- [ ] **Ads declaration:** "No ads" while no ad SDK is integrated.
- [ ] **Data safety form:** "No data collected or shared" is accurate for this build. **Update it before adding ads, analytics, sign-in or cloud save.**
- [ ] Rollout order: internal testing → closed testing → production (consider a staged rollout).

## F. If you add commercial services (optional, you)
- [ ] **Ads:**
  * consent (Google UMP) for EEA, UK and Switzerland users;
  * test ad units during development;
  * grant the revive **only on a completed ad**;
  * frequency: one revive per run (already enforced by the rules).
- [ ] **Purchases:**
  * create products in Play Console;
  * restore purchases works;
  * prices come **only** from the store;
  * no success message until the store confirms.
  * Purchases never sell combat power (cosmetics and supporter only), as designed.
- [ ] **Analytics:** consent where required; list it in the Data safety form and the privacy policy.
- [ ] **Sign-in and cloud save:**
  * the guest profile stays available;
  * merge rules for an existing local save;
  * a working account deletion path if accounts exist.

## G. Legal and credits
- [ ] Third-party notices are in Credits and `ASSET_MANIFEST.csv`: Pixelify Sans (OFL; keep the licence file), Newtonsoft.Json (MIT) and Unity.
- [ ] All art, music and sound effects are original, generated by this project's tools.
- [ ] Support contact added to `ui.credits.support` in `strings_en.json`.

## H. Launch operations
- [ ] Soft launch in a few countries first. Watch retention (D1/D7), crashes and reviews.
- [ ] Advertising: follow `store/AD_BUDGET_PLAN.md` **only after your approval**. It needs analytics to measure anything.
- [ ] Plan the first update from playtest and review feedback.
