using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    public struct SpawnOrder
    {
        public float time;
        public string enemyId;
        public bool elite;
        public bool boss;
        public int route;
        public float lateral;
    }

    public sealed class WavePlan
    {
        public int wave;
        public float release;
        public float healthMult = 1f, damageMult = 1f, speedMult = 1f, armorAdd;
        public string bossId;
        public readonly List<SpawnOrder> orders = new List<SpawnOrder>();
        public readonly List<string> announce = new List<string>();
        public readonly List<string> activeModifiers = new List<string>();
        public float budgetUsed;
    }

    /// <summary>Normalised description of what a run spawns (campaign mission, daily challenge or endless).</summary>
    public sealed class EncounterSpec
    {
        public BattleMode mode;
        public string missionId;
        public string biome = "gravewood";
        public int totalWaves;               // 0 = endless
        public float budget, budgetGrowth, budgetCap = 9999f;
        public float healthScale = 1f, damageScale = 1f;
        public List<PoolEntryDef> pool = new List<PoolEntryDef>();
        public List<ScriptedWaveDef> scripted = new List<ScriptedWaveDef>();
        public string boss;
        public List<string> modifiers = new List<string>();
        public string routeLayout = "routes_5";
        public List<SlotUnlockDef> slotUnlocks = new List<SlotUnlockDef>();
        public bool tutorial;
        public EndlessDef endless;

        public static EncounterSpec ForMission(MissionDef m)
        {
            return new EncounterSpec
            {
                mode = BattleMode.Campaign, missionId = m.id, biome = m.biome, totalWaves = m.waves,
                budget = m.budget, budgetGrowth = m.budgetGrowth, healthScale = m.healthScale, damageScale = m.damageScale,
                pool = m.pool, scripted = m.scripted, boss = m.boss, modifiers = new List<string>(m.modifiers ?? new List<string>()),
                routeLayout = m.routeLayout, slotUnlocks = m.slotUnlocks ?? new List<SlotUnlockDef>(), tutorial = m.tutorial,
            };
        }

        public static EncounterSpec ForDaily(DailyChallengeDef d, List<string> modifiers, string boss, string biome)
        {
            return new EncounterSpec
            {
                mode = BattleMode.Daily, missionId = "daily", biome = biome, totalWaves = d.waves,
                budget = d.budget, budgetGrowth = d.budgetGrowth, healthScale = d.healthScale, damageScale = 1f,
                pool = d.pool, boss = boss, modifiers = modifiers ?? new List<string>(), routeLayout = "routes_5",
            };
        }

        public static EncounterSpec ForEndless(EndlessDef e)
        {
            return new EncounterSpec
            {
                mode = BattleMode.Endless, missionId = "endless", biome = "moonfall", totalWaves = 0,
                budget = e.budget, budgetGrowth = e.budgetGrowth, budgetCap = e.budgetCap, healthScale = e.healthScale,
                pool = e.pool, routeLayout = e.routeLayout, endless = e,
            };
        }
    }

    /// <summary>
    /// Deterministic wave composition: the same (seed, spec, wave) always gives the same plan,
    /// independent of how the previous waves went. That makes checkpoints and the daily
    /// challenge reproducible.
    /// </summary>
    public static class WavePlanner
    {
        private static readonly HashSet<string> Notable = new HashSet<string>
        {
            "hound_runner", "shield_guard", "crow_archer", "bat_swarm", "bell_priest", "powder_rat", "iron_golem"
        };

        public static List<string> ActiveModifiers(EncounterSpec spec, int wave)
        {
            var list = new List<string>(spec.modifiers);
            if (spec.mode == BattleMode.Endless && spec.endless != null && spec.endless.modifierCycle.Count > 0)
            {
                int count = wave / Math.Max(1, spec.endless.modifierEvery);
                var endlessMods = new List<string>();
                for (int i = 0; i < count; i++)
                    endlessMods.Add(spec.endless.modifierCycle[i % spec.endless.modifierCycle.Count]);
                // keep only the newest maxModifiers
                int start = Math.Max(0, endlessMods.Count - spec.endless.maxModifiers);
                for (int i = start; i < endlessMods.Count; i++) if (!list.Contains(endlessMods[i])) list.Add(endlessMods[i]);
            }
            return list;
        }

        public static string BossForWave(EncounterSpec spec, int wave)
        {
            if (spec.mode == BattleMode.Endless)
            {
                var e = spec.endless;
                if (e == null || e.bossEvery <= 0 || e.bossCycle.Count == 0 || wave % e.bossEvery != 0) return null;
                return e.bossCycle[(wave / e.bossEvery - 1) % e.bossCycle.Count];
            }
            return (spec.totalWaves > 0 && wave == spec.totalWaves) ? spec.boss : null;
        }

        public static float HealthMultiplier(GameContent c, EncounterSpec spec, int wave, List<ModifierDef> mods)
        {
            float m;
            if (spec.mode == BattleMode.Endless && spec.endless != null)
            {
                var e = spec.endless;
                float growth = 1f + e.healthGrowthLinear * (wave - 1) + e.healthGrowthQuadratic * (wave - 1) * (wave - 1);
                m = spec.healthScale * Math.Min(e.healthCap, growth);
            }
            else m = spec.healthScale * (1f + c.Tuning.waves.hpGrowthPerWave * (wave - 1));
            foreach (var mod in mods) m *= mod.healthMult;
            return m;
        }

        /// <summary>Insertion-order-stable sort (List.Sort is not stable and may differ between runtimes).</summary>
        private static void StableSortByTime(List<SpawnOrder> orders)
        {
            for (int i = 1; i < orders.Count; i++)
            {
                var cur = orders[i];
                int j = i - 1;
                while (j >= 0 && orders[j].time > cur.time)
                {
                    orders[j + 1] = orders[j];
                    j--;
                }
                orders[j + 1] = cur;
            }
        }

        public static WavePlan Plan(GameContent c, EncounterSpec spec, RouteSet routes, int wave, ulong seed)
        {
            var rng = new Rng(Rng.Mix(seed, (ulong)wave * 7919UL + 17UL), 11u);
            var t = c.Tuning.waves;
            var plan = new WavePlan { wave = wave };

            var mods = new List<ModifierDef>();
            foreach (var id in ActiveModifiers(spec, wave))
                if (c.ModifierById.TryGetValue(id, out var md)) { mods.Add(md); plan.activeModifiers.Add(id); }

            plan.healthMult = HealthMultiplier(c, spec, wave, mods);
            plan.damageMult = spec.damageScale * (1f + t.dmgGrowthPerWave * (wave - 1));
            foreach (var md in mods)
            {
                plan.damageMult *= md.damageMult;
                plan.speedMult *= md.speedMult;
                plan.armorAdd += md.armorAdd;
            }

            float budget = spec.budget * (float)Math.Pow(spec.budgetGrowth, wave - 1);
            budget = Math.Min(budget, spec.budgetCap);
            foreach (var md in mods) budget *= md.budgetMult;

            // Groups: (enemyId, count, elite, time offset hint)
            var groups = new List<(string id, int count, bool elite, bool scripted)>();
            ScriptedWaveDef scripted = null;
            if (spec.scripted != null)
                foreach (var s in spec.scripted) if (s.wave == wave) { scripted = s; break; }
            if (scripted != null)
            {
                foreach (var e in scripted.entries)
                {
                    var ed = c.Enemy(e.enemy);
                    if (ed == null) continue;
                    groups.Add((e.enemy, Math.Max(1, e.count), e.elite, true));
                    float cost = ed.cost * e.count * (e.elite ? 3f : 1f);
                    budget -= cost;
                    if (e.elite) plan.announce.Add("elite:" + e.enemy);
                }
                if (!string.IsNullOrEmpty(scripted.announceKey)) plan.announce.Add("key:" + scripted.announceKey);
                if (scripted.replaceBudget) budget = 0f;
                else budget = Math.Max(budget, spec.budget * (float)Math.Pow(spec.budgetGrowth, wave - 1) * 0.3f);
            }

            string bossId = BossForWave(spec, wave);
            if (spec.mode == BattleMode.Daily && wave == spec.totalWaves) bossId = spec.boss;
            if (!string.IsNullOrEmpty(bossId) && c.Boss(bossId) != null)
            {
                plan.bossId = bossId;
                plan.announce.Add("boss:" + bossId);
                budget *= 0.55f;
            }

            // Random fill from the pool by weight.
            var candidates = new List<PoolEntryDef>();
            var weights = new List<float>();
            foreach (var pe in spec.pool)
            {
                if (wave < pe.fromWave || wave > pe.toWave) continue;
                var ed = c.Enemy(pe.enemy);
                if (ed == null || ed.isUnitOnly) continue;
                float w = pe.weight;
                foreach (var md in mods)
                    if (md.weightMult != null && md.weightMult.TryGetValue(pe.enemy, out var wm)) w *= wm;
                if (w <= 0f) continue;
                candidates.Add(pe);
                weights.Add(w);
                if (pe.fromWave == wave && wave > 1 && Notable.Contains(pe.enemy)) plan.announce.Add("new:" + pe.enemy);
            }
            int guard = 0;
            int unitCount = 0;
            while (budget > 0f && candidates.Count > 0 && guard++ < 400)
            {
                // drop candidates that are no longer affordable
                for (int i = candidates.Count - 1; i >= 0; i--)
                {
                    if (c.Enemy(candidates[i].enemy).cost > budget + 1e-4f)
                    {
                        candidates.RemoveAt(i);
                        weights.RemoveAt(i);
                    }
                }
                if (candidates.Count == 0) break;
                int idx = rng.WeightedIndex(weights);
                if (idx < 0) break;
                var def = c.Enemy(candidates[idx].enemy);
                int size = rng.Range(Math.Max(1, def.groupMin), Math.Max(def.groupMin, def.groupMax) + 1);
                int affordable = (int)Math.Floor((budget + 1e-4f) / def.cost);
                size = Math.Max(1, Math.Min(size, affordable));
                groups.Add((def.id, size, false, false));
                budget -= size * def.cost;
                unitCount += size * Math.Max(1, def.swarmCount);
                if (unitCount > c.Tuning.arena.maxAlive * 2) break;
            }
            plan.budgetUsed = spec.budget * (float)Math.Pow(spec.budgetGrowth, wave - 1) - budget;

            // Timing: small waves release faster; normal waves over ~18-25 s.
            int groupCount = Math.Max(1, groups.Count);
            float release = rng.Range(t.releaseMin, t.releaseMax);
            release = Math.Min(release, Math.Max(10f, groupCount * 3.6f));
            plan.release = release;
            // shuffle non-scripted order but keep scripted groups spread evenly
            var order = new List<int>();
            for (int i = 0; i < groups.Count; i++) order.Add(i);
            rng.Shuffle(order);

            int lastRoute = -1;
            for (int gi = 0; gi < order.Count; gi++)
            {
                var g = groups[order[gi]];
                var def = c.Enemy(g.id);
                float start = 0.5f + release * gi / groupCount + rng.Range(0f, 0.4f * release / groupCount);
                var routeChoices = routes.IndicesWithTag(def.routeTag);
                int route = routeChoices[rng.Range(0, routeChoices.Count)];
                if (route == lastRoute && routeChoices.Count > 1) route = routeChoices[(routeChoices.IndexOf(route) + 1) % routeChoices.Count];
                lastRoute = route;
                for (int k = 0; k < g.count; k++)
                {
                    float lateral = (k % 3 == 0) ? 0f : (k % 3 == 1 ? 0.38f : -0.38f);
                    plan.orders.Add(new SpawnOrder
                    {
                        time = start + k * t.groupSpacing,
                        enemyId = g.id,
                        elite = g.elite,
                        route = route,
                        lateral = lateral + rng.Range(-0.08f, 0.08f),
                    });
                }
            }
            if (plan.bossId != null)
            {
                var routeChoices = routes.IndicesWithTag("any");
                plan.orders.Add(new SpawnOrder
                {
                    time = Math.Min(6f, release * 0.3f),
                    enemyId = plan.bossId,
                    boss = true,
                    route = routeChoices[rng.Range(0, routeChoices.Count)],
                    lateral = 0f,
                });
            }
            StableSortByTime(plan.orders);
            return plan;
        }
    }
}
