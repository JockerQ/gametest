# Evil Cats — Balance

All numbers below come from the game data in `EvilCats/Assets/_EvilCats/Data/Resources/ECData/*.json`.
Change the JSON, not the code. `Evil Cats > 2. Validate Content, Art and Audio` (Unity) and the
Core tests check that the data is consistent.

**Important:** every result on this page comes from a **headless simulation with rule-based bots**
(`Tools/EvilCats.Sim`). No person has played the game yet. Simulation shows that the rules are
consistent and the numbers are in a sensible range. It does **not** show that the game is fun or
that a human finds the difficulty right. Playtesting on a phone is the next step (see `NEXT_STEPS.md`).

---

## 1. Core rules and formulas

### Time
* Fixed simulation step: **30 steps per second** (`game.json › tickRate`).
* **2× speed** runs two steps per displayed step. Outcomes, spawns, rewards and cooldown ratios are
  identical at 1× and 2× (verified, see §6).

### Stat stacking (one rule for everything)
For any stat with base value `B`:

```
value    = (B + Σ add) × (1 + Σ pct) × Π mul
interval = B / ((1 + Σ rate) × Π rateMul) × Π mul      (attack/activation intervals)
```

* `pct` bonuses of the same kind **add** (two +10 % bonuses give +20 %, not +21 %).
* Trade-offs (`mul`) **multiply**.
* Stats are always **rebuilt from their sources** (upgrades, perks, permanent tree, station tier,
  slot, synergies). They never compound on repeated rebuilds.
* When **maximum health rises, current health rises by the same amount**. When it falls, current health
  is clamped to the new maximum.

### Arc Light Cat (the hero)

| Stat | Base | Source |
|---|---|---|
| Citadel health | 1000 | `hero.maxHealth` |
| Arc Bolt damage | 12 | `hero.damage` |
| Attack interval | 1.0 s | `hero.interval` |
| Range | 7.0 | `hero.range` |
| Critical chance / multiplier | 5 % / ×1.5 (chance capped at 60 %) | `hero.critChance`, `critMultiplier`, `critChanceCap` |
| Chain targets | 0 (perks and the permanent tree add them) | `hero.chainTargets`, falloff ×0.75 per hop, range 2.4 |

* **Arc Storm:** strikes up to **5** enemies inside radius 2.5 for **3×** Arc Bolt damage and stuns them for 1.5 s.
  The cooldown is **25 s**. Casting on empty ground is refused and **does not use the cooldown**.
  Bosses resist the stun (see control rules).
* **Nine-Lives Ward:** a barrier worth **20 % of maximum health** for **5 s**. The cooldown is **35 s**.
  It is a barrier, not a revive.

### Damage order
1. Attacker damage, which already includes upgrades, perks, the permanent tree, station tier and slot.
2. × (1 + Σ conditional bonuses). The bonuses are Static Mark, Falling Star, Brittle Armour and Executioner.
3. × the critical multiplier. Only direct hits can crit, with one roll per hit.
4. × mitigation:
   * **Physical** damage uses armour. Armour Break and penetration reduce the armour first.
   * **Elemental** damage uses resist.
   * **True** damage ignores both.
   * Armour and resist are each capped at 90 %.
5. × the boss shield-stance reduction (70 %).
6. The result is applied to health. Death pays out rewards and triggers on-death effects (Shatter, Cinder Spread, powder blast).

### Citadel damage order
1. The Ward Lantern aura reduces hits from attackers within its radius (−12 %).
2. **Last Thread** is checked once per run. It adds an emergency barrier before health would fall below 20 %.
3. **Barriers** absorb the hit next, the soonest-expiring pool first. Reflective Fur returns part of what they absorb.
4. Whatever is left reduces **health**.
5. The total of all barriers is **capped at 60 % of maximum health**.

### Control (no permanent lock-down)
* Slow cap: **60 %** normal, **40 %** elite, **15 %** boss. Slows also slow attacks.
* Every hard control adds **fatigue** of +35 %, up to 70 %. Fatigue decays by 10 % per second.
  The next control's duration is multiplied by `(1 − fatigue) × (1 − controlResist)`.
* Resistance: bosses take ×0.3 control and elites ×0.6. Bosses also have 70 % control resist.
* Freeze gives **3 s of freeze immunity** afterwards.
* Golems and bosses cannot be pulled. Gravity Paw deals **×2 crush damage** to them instead.

### Run upgrades (Spark Coins)
The cost of the next level is **`ceil(baseCost × 1.16^level)`**.

| Upgrade | Per level | Base cost | Max level | Costs of levels 1–5 | Total to max |
|---|---|---|---|---|---|
| Damage | +8 % all damage | 25 | 15 | 25, 29, 34, 40, 46 | 1298 |
| Attack Speed | +6 % attack rate | 30 | 12 | 30, 35, 41, 47, 55 | 932 |
| Max Health | +100 max health | 22 | 15 | 22, 26, 30, 35, 40 | 1144 |
| Regeneration | +1.2 health/s | 26 | 12 | 26, 31, 35, 41, 48 | 808 |
| Critical | +3 % crit chance | 32 | 10 | 32, 38, 44, 50, 58 | 686 |
| Collection | +12 % Spark Coins | 18 | 10 | 18, 21, 25, 29, 33 | 388 |

Spark Coins come from:
* enemies (see the enemy table);
* a wave-clear bonus of `(8 + 1.5 × wave) × spark gain`;
* the permanent "Pocket Sparks" node, which adds starting coins.

### Levels and perks
* XP needed for the next level: **`30 + 20·L + 5·L²`**, where L is the current run level (starting at 0).
* Each level offers **3 perk choices** weighted by rarity: common 60, rare 30, epic 10.
* Offers only include perks whose requirements are met, for example a module being equipped.
* When no eligible perk remains, the offer uses fallback rewards: Spark Cache, Stormheart Mend or Stormheart Shield.
* **30 perks**: 5 per family (Arc, Ember, Frost, Bone, Ward, Gravity). 12 are common, 12 rare and 6 epic trade-offs.

### Station slots

| Slot | Bonus |
|---|---|
| Crown | +15 % range or aura radius |
| Middle | +10 % power (damage, healing or barrier) |
| Base | +10 % attack/activation rate |

**Adjacency synergies.** Adjacent pairs are Crown–Middle and Middle–Base.

| Synergy | Stations | Effect |
|---|---|---|
| Conductive Frost | Arc Coil + Frost Whisker | Arc Coil chains to +1 target |
| Collapsing Fire | Ember Maw + Gravity Paw | Explosion radius +20 % |
| Guarded Volley | Ward Lantern + Bone Ballista | Ballista attacks 15 % faster while a barrier is up |

### Stations (tier 1, before the slot bonus)

| Station | Behaviour | Damage | Every (s) | Range | Other |
|---|---|---|---|---|---|
| Arc Coil | chain lightning | 11 | 1.6 | 6.0 | 3 targets, chain range 2.8, ×0.92 per hop |
| Ember Maw | lobbed shell | 18 | 2.4 | 7.2 | radius 1.3, 70 % splash, burn 5/s for 3 s (max 3 stacks) |
| Frost Whisker | frost pulse | 7 | 2.2 | 6.5 | radius 1.8, 30 % slow for 2.5 s, 3 chills → 1 s freeze |
| Bone Ballista | piercing bolt | 20 | 2.2 | 8.5 | pierces 2, 50 % armour penetration |
| Ward Lantern | barrier and repair | — | 9.0 | aura 3.4 | barrier 4.5 % max health for 6 s, repair 1/s, aura −12 % damage taken |
| Gravity Paw | pull well | 18 | 6.0 | 6.5 | radius 2.2, pull for 1.6 s, ×2 damage to targets that cannot be pulled |

**Permanent tiers.** Tiers 2–5 cost 80 / 180 / 360 / 650 Moon Gold. They add power and rate, and at tiers 3 and 5 the station's art changes.

### Enemies (before wave scaling)
Every wave multiplies health by `mission.healthScale × (1 + 0.06 × (wave − 1))` and damage by `(1 + 0.02 × (wave − 1))`. Mission modifiers apply on top.

Elites (waves 5, 10 and 15) have ×2.2 health and ×1.4 damage. They pay ×3 rewards, get +35 % control resist and are drawn ×1.25 larger.

| Enemy | Role | Health | Speed | Damage / interval | Armour / Resist | XP / Sparks | Notes |
|---|---|---|---|---|---|---|---|
| Rat Raider | melee | 28 | 1.05 | 5 / 1.1 s | 0 / 0 | 3 / 2 | |
| Hound Runner | fast | 18 | 2.1 | 4 / 0.8 s | 0 / 0 | 3 / 2 | |
| Shield Guard | armoured | 80 | 0.65 | 11 / 1.4 s | 50 / 15 | 7 / 5 | answer: Ballista penetration, elements |
| Crow Archer | ranged (5.2) | 26 | 1.1 | 6 / 1.7 s | 0 / 0 | 5 / 4 | answer: Ranged Threat priority |
| Bat Swarm | 5 flying bats | 8 each | 1.7 | 2 / 0.75 s | 0 / 0 | 1 / 1 each | answer: chains, frost |
| Bell Priest | support (heals) | 50 | 0.75 | 4 / 2.5 s | 0 / 0 | 8 / 6 | heals 12 % in 2.8 radius every 3.5 s |
| Powder Rat | suicide | 24 | 1.25 | 70 blast | 0 / 0 | 4 / 3 | 1.4 s fuse at 4.2 m; any stun or pull defuses it |
| Iron Golem | siege | 320 | 0.42 | 26 / 3.2 s | 35 / 20 | 18 / 15 | cannot be pulled |

### Bosses (before mission scaling)

| Boss | Health | Hit | Abilities and counterplay |
|---|---|---|---|
| **Sir Barkhelm** (mission 6) | 900 | 20 | **Shield stance:** −70 % damage taken, calls guards; kill the guards. **Charge:** steps back, red lane telegraph, 150 damage; ward it. **Howl:** summons. |
| **Mother Carrion** (mission 9) | 1000 | 10 | Summons bats, crows and a priest. **Feather barrage** into a marked sector: 8 feathers + 3 per ranged minion alive in the sector, so kill archers in the red zone. |
| **King Goldenfang** (mission 12) | 1150 | 26 | Command, decree (+20 % enemy damage for 6 s), priest and golem summons. **Golden Volley** (240): deal 6 % of his health during the 4 s glow to stagger it to half damage, or ward it. Charge and barrage as above. |

Bosses have 2–3 health phases; later phases shorten cooldowns. Every windup is shown with a telegraph and a banner.

### Waves and missions
* Each wave releases its enemies over **18–25 s**. The next wave starts **3 s after the wave is cleared**, not on a timer.
* Every standard mission has **20 waves**. Elite waves are 5, 10 and 15; wave 20 is the boss or finale. The tutorial mission has 10 waves.
* **Stall recovery.** If stragglers survive 75 s after the last spawn, they rush the citadel. A hard safety removes them at 180 s without paying rewards; it should never trigger in play.
* Enemy budget per wave is `budget × growth^(wave−1)`. The numbers are in the table below.

| Mission | Biome | Waves | Budget / growth | Health scale | Boss | Modifier | Moon Gold (first clear) | Shards | Unlocks |
|---|---|---|---|---|---|---|---|---|---|
| m01 | Gravewood | 10 | 4.0 / 1.15 | 3.2 | — | — | 60 | 1 | Frost Whisker |
| m02 | Gravewood | 20 | 6.5 / 1.11 | 2.01 | — | — | 80 | — | — |
| m03 | Gravewood | 20 | 7.15 / 1.11 | 2.13 | — | — | 100 | 2 | Bone Ballista |
| m04 | Gravewood | 20 | 7.15 / 1.115 | 2.2 | — | Powder Night | 120 | — | — |
| m05 | Gravewood | 20 | 7.8 / 1.115 | 2.03 | — | — | 140 | 2 | Ward Lantern |
| m06 | Gravewood | 20 | 7.8 / 1.115 | 1.45 | Sir Barkhelm | — | 200 | 3 | — |
| m07 | Moonfall | 20 | 8.45 / 1.115 | 2.03 | — | Moon Haste | 220 | 3 | Gravity Paw |
| m08 | Moonfall | 20 | 8.45 / 1.12 | 1.76 | — | Sanctified | 240 | — | — |
| m09 | Moonfall | 20 | 9.1 / 1.12 | 2.04 | Mother Carrion | — | 300 | 3 | — |
| m10 | Moonfall | 20 | 9.1 / 1.12 | 1.8 | — | Iron Tide | 280 | — | — |
| m11 | Moonfall | 20 | 9.75 / 1.12 | 2.73 | — | Night Swarm | 300 | — | — |
| m12 | Moonfall | 20 | 9.75 / 1.12 | 1.5 | King Goldenfang | — | 400 | 5 | — |

* **Replays** pay 60 % of the mission's Moon Gold.
* **Defeats** pay `40 % × (waves cleared / waves)`, at least 5 once one wave is cleared.
* **Daily Challenge** (unlocks after m03):
  * 15 waves, the same seed and stations for everyone that day.
  * Permanent upgrades are ignored and there is no revive.
  * Up to 80 Moon Gold for the first finished attempt each day, scaled by progress.
* **Endless** (unlocks after m12):
  * budget 12 ×1.06 per wave, capped at 200;
  * health grows linearly and quadratically, capped at ×40;
  * a new modifier every 5 waves, up to 4 at a time;
  * a boss every 10 waves;
  * 6 Moon Gold per wave cleared.

### Permanent progression (Moon Gold)
* 15 nodes in 4 branches: Arc Mastery, Citadel Durability, Station Efficiency and Earnings.
* Node cost is `ceil(baseCost × growth^level)`. Some nodes need an earlier node or a cleared mission.
* **Offline Moon Gold:** `(4 + 2 × highest cleared mission) × offline bonus` per hour.
  * It is capped at **8 hours** and starts after the first mission is cleared.
  * The minimum collection interval is 5 minutes.
  * If the device clock moves backwards, accrual restarts instead of paying out.
* **7-day login:** 40, 50, 60, 70, 80, 100, and 120 Moon Gold + 1 shard on day 7. Missing days never resets the track.
* **Three daily objectives** are drawn from 13 kinds, each paying 30–50 Moon Gold.
* **22 achievements** pay Moon Gold, shards or cosmetics.
* **Every claim is idempotent.** A transaction ledger means repeated taps, restarts and replays never pay twice.

---

## 2. How the numbers were tuned

1. **Headless simulator** (`Tools/EvilCats.Sim`, .NET 8). It runs the exact same `EvilCats.Core` code that Unity runs.
2. **Bots** (`AutoPilot`) only use the actions a player has:
   * buy upgrades, choose perks, cast abilities and switch target priority;
   * four build personalities: `default` (Arc Coil / Ember Maw / Frost Whisker), `chain_control` (Arc Coil / Frost / Gravity), `fire_gravity` (Ember / Gravity / Arc) and `ballista_ward` (Ballista / Ward / Arc).
3. **Progression profiles.** The sweep uses the "mid" profile, a typical permanent progression for each mission index. The campaign simulation instead plays all 12 missions in order, spending real rewards between runs.
4. **Calibration.** Mission `healthScale` values were searched until every build wins at least 2 of 3 runs, with the average lowest-health point on a descending difficulty curve. Rounding used a safety margin.

**Known bot limitation.** The bots save Nine-Lives Ward for telegraphed boss attacks and emergencies, so they cast it only 1–4 times per run. A player who casts it more often has an easier time than these tables show. The simulated difficulty is therefore a pessimistic estimate.

---

## 3. Results (simulation, 25 September 2026)

### Sweep: every mission × every build, "mid" progression, 4 seeds each
Each cell shows win % | average waves | average time | perks taken | average lowest health.

```
mission  default                           chain_control                     fire_gravity                      ballista_ward
m01      100%  10.0w  3:50  3.0p 64 %      100%  10.0w  3:49  3.0p 67 %      100%  10.0w  3:36  3.0p 87 %      100%  10.0w  3:32  3.0p 65 %
m02      100%  20.0w  8:19  7.0p 79 %      100%  20.0w  8:14  7.0p 89 %      100%  20.0w  8:22  7.0p 74 %      100%  20.0w  8:11  7.0p 78 %
m03      100%  20.0w  9:02  7.0p 64 %      100%  20.0w  8:50  7.0p 74 %      100%  20.0w  9:04  7.0p 54 %      100%  20.0w  8:42  7.0p 49 %
m04       75%  19.5w  9:13  6.8p 33 %       75%  19.8w  9:07  7.0p 48 %       75%  19.5w  9:09  6.8p 22 %       50%  18.8w  8:08  6.5p 25 %
m05      100%  20.0w 10:28  7.0p 51 %      100%  20.0w 10:25  7.0p 55 %      100%  20.0w 10:21  7.0p 42 %       75%  19.5w  9:12  7.0p 20 %
m06      100%  20.0w  9:12  7.0p 50 %       75%  19.8w  9:16  7.0p 47 %       75%  19.8w  9:08  7.0p 39 %      100%  20.0w  8:34  7.0p 77 %
m07      100%  20.0w 10:06  7.0p 63 %      100%  20.0w 10:12  7.0p 62 %      100%  20.0w 10:01  7.0p 65 %      100%  20.0w  9:19  7.3p 49 %
m08      100%  20.0w  9:48  8.0p 81 %      100%  20.0w 11:08  8.0p 64 %      100%  20.0w  9:50  8.0p 62 %      100%  20.0w  9:09  8.0p 74 %
m09       75%  19.8w 10:06  8.0p 42 %       75%  19.8w 11:35  8.0p 33 %      100%  20.0w 10:13  8.0p 46 %      100%  20.0w  9:28  8.0p 79 %
m10      100%  20.0w 10:32  8.0p 77 %      100%  20.0w 12:28  8.0p 48 %      100%  20.0w 10:34  8.0p 58 %      100%  20.0w  9:44  8.0p 55 %
m11      100%  20.0w 10:24  8.0p 74 %      100%  20.0w 11:49  8.0p 55 %      100%  20.0w 10:19  8.0p 59 %      100%  20.0w  9:46  8.0p 61 %
m12       75%  19.8w  9:50  8.5p 32 %        0%  19.0w 11:15  8.0p  0 %      100%  20.0w  9:58  8.3p 55 %      100%  20.0w  9:12  8.8p 88 %
```
Raw output: `docs/sim/sweep_mid.txt`.

**Reading it:**
* Mission length is **3.5–3.9 minutes** for the tutorial and **8–12.5 minutes** for 20-wave missions. The brief's 6–10 minutes is met for most builds. Chain/control runs later in Moonfall reach 11–12.5 minutes because that build kills more slowly.
* **Mission 4 (Powder Night)** is the first real wall at mid progression: 50–75 % wins. That is intended as the "learn to interrupt powder rats" mission, but it is the most likely place for players to feel stuck.
* **Weak spot: chain/control against King Goldenfang (m12).** The four sweep seeds all lost at the boss wave. Over 21 seeds the build wins **12 of 21 (≈57 %)**. The other builds win 75–100 %. Using Ward more often did not change the result. The losses come from Goldenfang plus his summoned golems, where a control build has the least burst.
  * If playtests confirm it, the smallest levers are: lower `king_goldenfang.health` by about 8 %, or raise Gravity Paw's `anchoredDamageMult` from 2.0 to 2.3. Both are in the JSON.
  * Players can also switch to a different loadout for the finale, and the defeat screen suggests it.

### Campaign: a simulated player plays missions 1–12 in order, spending real rewards

| Build | Seed | Runs to finish the campaign | Total play time | Notes |
|---|---|---|---|---|
| default | 1 | 12 | 114 min | no retries needed |
| default | 2 | 14 | 133 min | mission 5 needed 3 attempts |
| fire_gravity | 1 | 13 | 124 min | mission 11 needed 2 attempts |
| fire_gravity | 2 | 14 | 132 min | mission 5 needed 3 attempts |

The lowest-health points on missions 9–12 were 9–36 %. The finale is tight by design.

### Paths: three versus five (the "Battlefield paths" setting)

```
== routes_3 (easier to read)                       == routes_5 (default)
m02: win 100%  minHP 92 %  coverage 50 %           m02: win 100%  minHP 87 %  coverage 75 %
m05: win 100%  minHP 80 %  coverage 46 %           m05: win 75%   minHP 25 %  coverage 77 %
m08: win 100%  minHP 84 %  coverage 44 %           m08: win 100%  minHP 82 %  coverage 69 %
```
* "Coverage" is the share of 12 directions that attackers came from.
* Five paths surround the citadel more and are harder. Three paths are easier and less crowded (0.31–0.35 neighbours within 0.6 m, against 0.34–0.40).
* Five paths is the default. Three paths is offered as a readability/accessibility option.

---

## 4. Retention and economy pacing (simulated)
* The first mission clear unlocks offline Moon Gold, the Daily Challenge (after m03) and new stations every 2 missions.
* Station unlocks cost Storm Shards: 0 for Frost Whisker, 2 for Bone Ballista, 2 for Ward Lantern and 3 for Gravity Paw. First clears pay 1–5 shards, so each unlock is affordable within about one mission of its milestone.
* A simulated player finishes the 12-mission campaign in **12–14 runs (about 2 hours of play)**, retrying at most 2–3 times on a single mission (usually mission 5).

---

## 5. Performance of the simulation (not the whole game)

From `docs/sim/stress.txt`:
* The arena was held at the 140-enemy cap with every enemy type, 3 stations firing, a chaining hero and 25 projectiles.
* Per step: **mean 0.032 ms, p99 0.18 ms, max 0.45 ms** on a desktop CPU with the .NET JIT.
* At 2× speed that is about **0.2 % of one desktop core**.

The expensive part on a phone will be **drawing** 140 animated enemies with health bars, effects and numbers. That has **not been measured** because no device was available. Use the Unity Profiler on a real phone (`NEXT_STEPS.md`).

## 6. Determinism
* **Speed:** the same mission and seed played at 1× and 2× gives the same result: 20 waves, 370 kills, 82.53 % health, score 27675 (`docs/sim/speed_invariance.txt`).
* **Resume:** checkpoints resume at the start of the next wave with identical state. This is covered by unit tests.
