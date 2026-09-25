# Evil Cats — Game Design

**Genre:** portrait 2D dark-fantasy "central tower" defence with roguelite runs and permanent progression.
**Platform:** Android phones, portrait. The Unity Editor supports mouse for testing.
**Hero:** **Arc Light Cat**, a smug storm-wielding cat defending the Nine-Lives Citadel.
**Original work.** Evil Tower was used only as a genre reference. Nothing was copied from it, and its
video and store pages could not be opened in this environment (see `docs/REFERENCE_NOTES.md`).
Every number here lives in the JSON data files. `BALANCE.md` has the formulas and tables.

---

## 1. Pillars
1. **Watch, then decide.** Arc Light Cat and the stations fight automatically, so the player never has to tap to attack. The player's choices are what to buy, which perk, where to strike with Arc Storm, when to Ward, and what to target.
2. **Readable danger.** Every heavy boss attack is telegraphed: a red charge lane, a red barrage wedge or a golden volley glow, with a banner and a sound. Every counter uses a tool the player already has.
3. **Builds that feel different.**
   * Six stations, three slot bonuses and three adjacency synergies.
   * 30 perks, 5 per station family, including epic trade-offs.
4. **Short, honest sessions.**
   * The first mission lasts 3–4 minutes; later missions 8–10.
   * Progress is checkpointed after every wave.
   * Rewards are never granted twice, and nothing fake is shown.

## 2. Core loop
```
Start as guest → Home → Missions → Loadout (3 slots) → Battle:
   20 waves (each releases enemies over 18–25 s, next wave 3 s after it is cleared)
   Spark Coins from kills → 6 run upgrades (tap to buy)
   XP → level-up → choose 1 of 3 perks (battle pauses)
   waves 5 / 10 / 15 = elites, wave 20 = boss or finale
   new station slots can open mid-run (m01 wave 3, m02 wave 2)
→ Victory / defeat summary (main damage source + how to counter it, fast retry)
→ permanent rewards: Moon Gold, Storm Shards, station unlocks
→ spend on the permanent tree and station tiers → next mission
```

## 3. Battle controls and HUD
* **Top bar:**
  * pause, wave counter ("Wave 7/20") with enemies left or the next-wave countdown;
  * Spark Coins (tap for a hint) and the 1×/2× speed button;
  * a health bar with the **barrier shown as a separate pale strip**, and an XP bar with the level.
* **Boss bar:** name, portrait icon, health, phase, "Shielded" status and a **stagger meter** during the Golden Volley.
* **Bottom dock:**
  * **Arc Storm:** tap once to aim. The battle slows to 30 %, and the densest group is highlighted with a reticle and a count of enemies in range. Then:
    * tap or drag on the battlefield to strike there;
    * tap Arc Storm again to strike the highlighted spot;
    * or press **Cancel**.
    * Striking empty ground is refused and never uses the cooldown.
  * **Nine-Lives Ward:** tap to cast.
  * Hold either ability for its exact current numbers.
  * **Target priority:** cycles Nearest → Strongest → Ranged Threat.
  * **Synergy** button: lists active synergies, or explains which slots are adjacent.
  * **Six upgrades:** tap to buy; hold to see name, description, level and "now → next" computed from the real stats.
* **Battlefield:** tap an enemy to see its name, health and how to counter it.
* **Feedback:**
  * damage numbers (crits are gold with "!");
  * coins fly to the Spark counter and XP orbs to the hero;
  * hit flashes, screen shake (optional), and a danger vignette below 30 % health;
  * wave, elite and boss banners, and short remarks from Arc Light Cat.
* **Speed:** 2× runs twice as many simulation steps. The outcome is identical (verified).

## 4. Arc Light Cat and abilities

| | |
|---|---|
| Citadel health | 1000 |
| Arc Bolt | 12 damage every 1.0 s, range 7, 5 % crit at ×1.5 (automatic) |
| **Arc Storm** | up to 5 enemies in the chosen area, 3× Arc Bolt damage, 1.5 s stun (resisted by bosses); 25 s cooldown |
| **Nine-Lives Ward** | barrier worth 20 % of max health for 5 s; 35 s cooldown (not a revive) |

## 5. Stations, slots and synergies
Each station is run by a cat operator. Station art changes at permanent tiers 3 and 5, and again after 8 damage upgrades in a run.

| Station | Operator | Role |
|---|---|---|
| **Arc Coil** | silver tabby with goggles | chain lightning between clustered enemies |
| **Ember Maw** | soot-smudged orange cat | slow explosive shells; burning is capped at 3 stacks |
| **Frost Whisker** | fluffy white cat | ice-bell pulses slow groups (movement and attacks); repeated chills freeze |
| **Bone Ballista** | cheerful skeletal cat | piercing bolts, armour penetration; weak against swarms |
| **Ward Lantern** | hooded black cat | barriers, slow repair, weakens nearby attackers; costs an offensive slot |
| **Gravity Paw** | purple-eyed cat | pulls ordinary enemies together and interrupts them; golems and bosses take ×2 crush damage instead |

**Slots:**
* Crown: +15 % range or aura.
* Middle: +10 % power.
* Base: +10 % rate.

**Adjacent pairs** are Crown–Middle and Middle–Base.
* Conductive Frost (Arc Coil + Frost Whisker): Arc Coil chains to +1 target.
* Collapsing Fire (Ember Maw + Gravity Paw): explosion radius +20 %.
* Guarded Volley (Ward Lantern + Bone Ballista): the ballista attacks 15 % faster while a barrier is up.

**Unlocks:**
* Arc Coil and Ember Maw are available from the start.
* Frost Whisker comes after m01 (free).
* Bone Ballista after m03 (2 Storm Shards).
* Ward Lantern after m05 (2 shards).
* Gravity Paw after m07 (3 shards).

## 6. Run upgrades, levels and perks
* **Upgrades** bought with Spark Coins, cost `ceil(base × 1.16^level)`: Damage, Attack Speed, Max Health, Regeneration, Critical, Collection.
* **Levels:** XP needed is `30 + 20L + 5L²`. Each level offers 3 perks weighted by rarity, and only offers perks whose requirements are met.
* **30 perks:**

**Arc**

| Perk | Rarity | Stacks | Effect |
|---|---|---|---|
| Forked Bolt | common | 3 | Arc Bolt chains to +1 more enemy per stack. Each hop deals less damage; a chain never hits the same enemy twice. |
| Static Mark | common | 2 | Arc Bolt marks enemies for 4 s. Marked enemies take +15 % Arc damage per stack. |
| Thunderclap | rare | 2 | The last hop of every chain bursts for 35 % of that hop's damage per stack within 1.3 m (needs a chain source). |
| Conductive Chill | rare | 1 | Chains reach slowed enemies from 1.5× farther and deal +25 % damage to them (needs a slow source). |
| Overcharged Crown | epic | 1 | Trade-off: maximum health −15 %, all Arc damage +30 %. |

**Ember**

| Perk | Rarity | Stacks | Effect |
|---|---|---|---|
| Lingering Embers | common | 2 | Burning lasts +50 % longer per stack. |
| Cinder Spread | rare | 1 | When a burning enemy dies, up to 2 enemies within 2 m catch fire at 50 % strength. |
| Molten Shell | common | 2 | Explosion radius +15 % and splash +10 % per stack. |
| Furnace Heart | rare | 1 | Every 8 shell hits on burning enemies, Ember Maw fires 40 % faster for 5 s. |
| Wildfire Pact | epic | 1 | Trade-off: Ember Maw range −25 %, all fire damage +45 %. |

**Frost**

| Perk | Rarity | Stacks | Effect |
|---|---|---|---|
| Deep Chill | common | 2 | Frost Whisker slows +10 % more per stack (the caps still apply). |
| Brittle Armour | rare | 1 | Chilled enemies take +20 % physical damage (needs Bone Ballista). |
| Shatter | rare | 1 | Frozen enemies that die shatter for 30 frost damage within 1.5 m and chill what they hit. |
| Winter Ring | common | 2 | Every 6 s a frost ring pulses 3.2 m around the citadel for 8 damage and a chill. |
| Frozen Oath | epic | 1 | Trade-off: Frost Whisker damage −50 %, freeze duration +60 %, one fewer chill to freeze. |

**Bone**

| Perk | Rarity | Stacks | Effect |
|---|---|---|---|
| Barbed Bolts | common | 2 | Ballista hits bleed for 4 damage/s per stack for 3 s (up to 3 bleeds). |
| Double Nock | rare | 1 | Every 3rd ballista shot fires an extra bolt at a second target. |
| Armour Break | common | 1 | Ballista hits remove 20 armour for 4 s. |
| Executioner | rare | 2 | +40 % ballista damage per stack to enemies below 35 % health. |
| Heavy Quarrels | epic | 1 | Trade-off: ballista rate −30 %, damage +70 %, pierces +2 more. |

**Ward**

| Perk | Rarity | Stacks | Effect |
|---|---|---|---|
| Reinforced Barrier | common | 2 | All barriers +20 % per stack. |
| Mending Purr | common | 2 | Ward Lantern repairs +1 health/s and regeneration +10 % per stack. |
| Last Thread | rare | 1 | Once per run, just before health would drop below 20 %, gain a 30 % barrier for 6 s. |
| Reflective Fur | rare | 1 | 40 % of damage absorbed by barriers returns to the attacker (max 30 per hit). |
| Guardian Pact | epic | 1 | Trade-off: all damage −15 %, barriers +50 %, Ward Lantern activates 33 % faster. |

**Gravity**

| Perk | Rarity | Stacks | Effect |
|---|---|---|---|
| Wider Orbit | common | 2 | Pull radius +20 % per stack. |
| Crushing Centre | rare | 2 | When a pull ends, enemies within 0.9 m of the centre take 25 damage per stack. |
| Event Horizon | common | 1 | Enemies released from a pull are slowed 35 % for 2 s. |
| Falling Star | rare | 2 | Enemies pulled in the last 3 s take +15 % damage from everything per stack. |
| Unstable Singularity | epic | 1 | Trade-off: Gravity Paw cooldown +35 %, pulls last +70 % longer and reach +15 % wider. |

When no eligible perk remains, the offer uses fallback rewards: **Spark Cache**, **Stormheart Mend** (heal) or **Stormheart Shield** (barrier).

## 7. Enemies (the Golden Collar Order)

| Enemy | What it does | Counter |
|---|---|---|
| Rat Raider | basic melee in packs | chains and splash |
| Hound Runner | fast flanker on side paths | Nearest targeting, frost slows |
| Shield Guard | slow, 50 armour | Bone Ballista penetration, elements |
| Crow Archer | stops at range and shoots | Ranged Threat targeting |
| Bat Swarm | 5 fragile flyers ignoring paths | chains, splash, frost pulses |
| Bell Priest | heals nearby enemies | Ranged Threat targeting |
| Powder Rat | lights a keg near the citadel, then charges (70 damage) | stun (Arc Storm), freeze or pull during the fuse |
| Iron Golem | huge health, cannot be pulled | Ballista, damage upgrades, Gravity crush |

Elites appear on waves 5, 10 and 15. They have a gold aura, are larger and have more health, and they pay 3× rewards.

## 8. Bosses and counterplay

| Boss | Mission | Counterplay (also shown in the boss introduction) |
|---|---|---|
| **Sir Barkhelm**, the Iron Hound | 6 | He raises his shield and calls guards: clear the guards. When he steps back and growls, a red lane shows his **charge**: save Nine-Lives Ward for it. |
| **Mother Carrion**, the Bell Crow | 9 | She summons swarms and priests. A red **sector** means a feather barrage: kill the archers inside it to shrink the barrage, and ward the rest. |
| **King Goldenfang**, Commander of the Golden Collar | 12 | **Golden Volley:** deal heavy damage during the glow to stagger it (a meter shows progress), or absorb it with Ward. His decree empowers his troops, and his last phase combines charges and barrages. |

Bosses resist control:
* slows are capped at 15 %;
* stun and freeze last only ×0.3 as long;
* they cannot be pulled.

## 9. World, missions and story
* **Story:** four skippable panels at first launch, about 18 s.
  1. "Exiled for his lightning, Arc Light Cat found a relic in the ruins: the Stormheart."
  2. "Around it he raised the Nine-Lives Citadel, a refuge for every cursed cat."
  3. "The Golden Collar Order called his clan the 'Evil Cats', and marched."
  4. "Evil? Wonderful. Let them come."
* **Gravewood Outskirts** (missions 1–6, ending with Sir Barkhelm) and **Moonfall Ruins** (missions 7–12, ending with King Goldenfang). Each biome has its own ground, paths and props.
* A one-time chapter ending plays after each boss.

| # | Mission | Theme |
|---|---|---|
| 1 | The Crooked Gate | tutorial (10 waves); the Crown slot opens with Ember Maw at wave 3 |
| 2 | Moonlit Hedgerows | archers and bats; the Base slot opens at wave 2 |
| 3 | Graveyard Toll | Bell Priests |
| 4 | Broken Wall Run | Shield Guards and Powder Rats (modifier: Powder Night) |
| 5 | The Lantern Path | Iron Golems |
| 6 | Barkhelm's Siege | boss: Sir Barkhelm |
| 7 | Moonfall Steps | faster enemies (Moon Haste) |
| 8 | Statue Garden | a choir of priests (Sanctified) |
| 9 | The Bell Tower Fall | boss: Mother Carrion |
| 10 | Courtyard of Cinders | armour and golems (Iron Tide) |
| 11 | Violet Vigil | wings and arrows (Night Swarm) |
| 12 | Throne of Goldenfang | boss: King Goldenfang |

**Modifiers:**
* Powder Night (more powder rats), Moon Haste (+10 % speed), Sanctified (more priests), Iron Tide (+15 armour, more guards and golems), Night Swarm (more bats and archers), Gilded Wrath (+20 % enemy damage).
* Endless only: Frenzy, Bulwark, Horde.

**Battlefield paths.** The default is five routes. A setting switches to three routes, which is easier to read. A resumed run keeps its layout.

## 10. Modes
* **Campaign:** 12 missions. Replays pay 60 % of the Moon Gold. Defeats pay a share based on waves cleared.
* **Daily Challenge** (after mission 3):
  * the same seed, stations, modifier and boss for everyone that day;
  * permanent upgrades are ignored and there is no revive;
  * 15 waves;
  * the first finished attempt pays up to 80 Moon Gold;
  * the best score is stored **on this device only**, and there is no fake online ranking.
* **Endless** (after mission 12): scaling waves, a modifier added every 5 waves (4 at most), a boss every 10 waves, and 6 Moon Gold per wave.

## 11. Progression and retention
**Currencies:**
* **Spark Coins** exist only within a run.
* **Moon Gold** is permanent and comes from missions, daily rewards, offline time and achievements.
* **Storm Shards** are rare. They come from first clears, day 7 of the login track and achievements, and they unlock stations and some cosmetics.

**Spending and earning:**
* **Permanent tree** (Moon Gold): 15 nodes in Arc Mastery, Citadel Durability, Station Efficiency and Earnings, with prerequisites.
* **Station tiers** 1–5 (Moon Gold). The art changes at tiers 3 and 5.
* **Offline Moon Gold:**
  * starts after the first clear;
  * the rate grows with campaign progress, capped at 8 h;
  * a device clock moved backwards restarts accrual instead of paying.
* **7-day login:** missing a day never resets the track.
* **Three daily objectives** per local day.
* **22 achievements.**
* **Cosmetics** never affect power:
  * 4 hero outfits: Classic (free), Ember (600 Moon Gold), Frost (achievement), Gilded (8 shards);
  * banner colours, shown as flags on the home citadel.
  * The Supporter banners are tied to an unconfigured store and are shown as unavailable.
* **Every reward goes through an idempotent ledger.** Double taps, restarts and replays never pay twice.

## 12. Screens
* **Boot:** real loading steps (no fake percentage), save-recovery notices, **Continue as Guest**, and a sign-in button that clearly says it is not configured.
* **Home:** the citadel diorama with Arc Light Cat, equipped stations and banners; the next mission with Play; the resume card; Daily Challenge and Endless entries.
* **Missions** (per biome) → **Loadout:**
  * 3 slots, each with its bonus and lock reason;
  * a station picker showing the stats that station would have in that slot and any synergy it creates;
  * default target priority and Start.
* **Stations:** unlock with shards, and tier up with before → after stats.
* **Upgrades:** the permanent tree with costs and requirement reasons.
* **Daily:** login track, objectives, Daily Challenge and offline Moon Gold.
* **More:** Achievements, Records, Shop, Profile, Settings, Credits.
* **Battle pop-ups:**
  * perk choice (select, then confirm);
  * new-slot station choice;
  * boss introduction (first encounter);
  * pause with quick settings;
  * revive (explains that ads are not configured);
  * confirm dialogs;
  * victory/defeat summary with the main damage source, a counter tip and fast retry.
* **Results:** rewards, a new station, achievements ready to claim, a chapter ending, and Retry or Continue.
* **Android back button:**
  * closes dialogs, cancels aiming and pauses the battle;
  * on Home it asks before leaving.

## 13. Accessibility and comfort
* Portrait layout for phones:
  * 360-dp reference width and a 48-dp minimum touch target;
  * the safe area is respected (notches, gesture bars);
  * tablets scale by height.
* Settings:
  * music and effects volume;
  * vibration (short, only for heavy impacts and purchases);
  * screen shake;
  * **bright flashes** (off removes screen flashes and dims lightning);
  * damage numbers;
  * start at 2×;
  * **three or five paths**.
* Barrier and health are visually distinct. Status icons are shown for burn, bleed, chill, freeze, stun, mark and armour break.
* Every locked or unavailable action says why ("Not enough Spark Coins", "Unlocks during The Crooked Gate", "Rewarded ads are not configured in this build").

## 14. Art and audio
* **Art:**
  * original pixel art made by reproducible Python generators (`Tools/art`);
  * 11 atlases and 979 sprites;
  * world art at 16 pixels per unit;
  * hero, stations (3 visual tiers each), 8 enemies with elite variants, 3 bosses, 2 biomes, effects, UI, icons, portraits and store graphics.
* **Font:** Pixelify Sans (SIL Open Font Licence).
* **Audio:** original music and effects synthesised by `Tools/audio`.
  * 7 music tracks: menu, Gravewood, Moonfall, boss, victory, defeat, story.
  * 47 sound effects, played with voice limits, cooldowns and pitch variation.
  * **No person has listened to them yet.** See `KNOWN_ISSUES.md`.

## 15. Services and monetisation
* The game is **fully playable offline**. Ads, purchases, analytics, sign-in, cloud save and leaderboards sit behind adapters.
* The shipped default adapters say "not configured" and never pretend.
* Development builds can switch on a clearly labelled "DEV MOCK" rewarded ad to test the revive flow. It is compiled out of release builds.
* See `NEXT_STEPS.md` for integrating real services.

## 16. Saves and lifecycle
* **Save format:**
  * versioned JSON with a checksum;
  * atomic write plus a backup copy;
  * migrations from older versions;
  * unreadable files are kept aside, never silently deleted.
* **Checkpoints:** after every cleared wave the run is saved. Closing the app resumes at the start of the next wave, and the resume prompt explains this.
* **Background:** leaving the app pauses the battle and saves. Coming back shows the pause menu.
