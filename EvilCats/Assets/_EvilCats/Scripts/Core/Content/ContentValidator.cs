using System;
using System.Collections.Generic;
using EvilCats.Core;

namespace EvilCats.Content
{
    /// <summary>
    /// Validates all game content: duplicate ids, missing references, broken unlock chains,
    /// impossible perk requirements, unreachable enemies, invalid stat keys, bad route
    /// geometry and missing strings. Runs in unit tests, in the Unity editor menu and at boot.
    /// </summary>
    public static class ContentValidator
    {
        public sealed class Report
        {
            public readonly List<string> Errors = new List<string>();
            public readonly List<string> Warnings = new List<string>();
            public bool Ok => Errors.Count == 0;

            public override string ToString() =>
                $"{Errors.Count} error(s), {Warnings.Count} warning(s)" +
                (Errors.Count > 0 ? "\n  E: " + string.Join("\n  E: ", Errors) : "") +
                (Warnings.Count > 0 ? "\n  W: " + string.Join("\n  W: ", Warnings) : "");
        }

        private static readonly HashSet<string> Families = new HashSet<string> { "arc", "ember", "frost", "bone", "ward", "gravity" };
        private static readonly HashSet<string> Behaviors = new HashSet<string> { "chain", "shell", "frost_pulse", "piercing", "ward", "gravity" };
        private static readonly HashSet<string> Rarities = new HashSet<string> { "common", "rare", "epic" };
        private static readonly HashSet<string> Conditions = new HashSet<string> { "chain", "slow" };
        private static readonly HashSet<string> Ops = new HashSet<string> { "add", "pct", "mul", "rate", "ratemul" };
        private static readonly HashSet<string> BossAbilityTypes = new HashSet<string> { "shield_stance", "charge", "summon", "sector_barrage", "decree", "volley" };
        private static readonly HashSet<string> SlotModifiers = new HashSet<string> { "range", "power", "rate" };
        private static readonly HashSet<string> Specials = new HashSet<string> { "barrierHaste" };

        public static readonly HashSet<string> GlobalStats = new HashSet<string>
        {
            "hero.damage", "hero.interval", "hero.range", "hero.critChance", "hero.critMultiplier",
            "hero.chainTargets", "hero.chainRange", "hero.chainFalloff",
            "citadel.maxHealth", "citadel.regen", "barrier.all", "heal.all", "synergy.all",
            "arcStorm.cooldown", "arcStorm.damageMultiplier", "arcStorm.targets", "arcStorm.radius", "arcStorm.stun",
            "ward.cooldown", "ward.barrierFraction", "ward.duration",
            "dmg.all", "dmg.arc", "dmg.fire", "dmg.frost", "dmg.physical", "dmg.gravity",
            "rate.all", "rate.stations", "station.damage",
            "econ.sparkGain", "econ.xpGain", "econ.startSparks", "econ.moonGold", "econ.offline",
        };

        public static readonly HashSet<string> LifetimeStats = new HashSet<string>
        {
            "missions_cleared", "kills", "elite_kills", "max_chain", "freezes", "burns", "pulls", "barrier_absorbed",
            "powder_interrupts", "max_level", "modules_unlocked", "permanent_levels", "high_health_victories",
            "daily_completed", "endless_best", "offline_collected", "attendance_claims", "storm_uses", "ward_uses",
            "upgrades_bought", "perks_taken", "waves_cleared", "victories", "defeats", "runs_played",
            "boss_sir_barkhelm", "boss_mother_carrion", "boss_king_goldenfang",
        };

        public static Report Validate(GameContent c)
        {
            var r = new Report();
            foreach (var e in c.LoadErrors) r.Errors.Add("load: " + e);
            ValidateTuning(c, r);
            ValidateModules(c, r);
            ValidateEnemies(c, r);
            ValidateBosses(c, r);
            ValidatePerks(c, r);
            ValidateUpgrades(c, r);
            ValidateProgression(c, r);
            ValidateRoutes(c, r);
            ValidateMissions(c, r);
            ValidateStrings(c, r);
            return r;
        }

        private static void Need(GameContent c, Report r, string key)
        {
            if (!c.Strings.Has(key)) r.Errors.Add("missing string '" + key + "'");
        }

        private static bool ValidStat(GameContent c, string stat, out string reason)
        {
            reason = null;
            if (string.IsNullOrEmpty(stat)) { reason = "empty stat"; return false; }
            if (GlobalStats.Contains(stat)) return true;
            if (stat.StartsWith("module.", StringComparison.Ordinal))
            {
                var parts = stat.Split('.');
                if (parts.Length != 3) { reason = "bad module stat format"; return false; }
                var m = c.Module(parts[1]);
                if (m == null) { reason = "unknown module " + parts[1]; return false; }
                if (Array.IndexOf(Sim.StatsBuilder.ModuleStatNames, parts[2]) >= 0) return true;
                if (m.p != null && m.p.ContainsKey(parts[2])) return true;
                reason = "module " + parts[1] + " has no stat '" + parts[2] + "'";
                return false;
            }
            reason = "unknown stat";
            return false;
        }

        private static void CheckMods(GameContent c, Report r, string owner, List<StatModDef> mods)
        {
            if (mods == null) return;
            foreach (var m in mods)
            {
                if (!ValidStat(c, m.stat, out var why)) r.Errors.Add($"{owner}: invalid stat '{m.stat}' ({why})");
                if (!Ops.Contains(m.op)) r.Errors.Add($"{owner}: invalid op '{m.op}'");
                if ((m.op == "mul" || m.op == "ratemul") && m.value <= 0f) r.Errors.Add($"{owner}: multiplier must be > 0");
            }
        }

        private static void ValidateTuning(GameContent c, Report r)
        {
            var t = c.Tuning;
            if (t.tickRate < 10f || t.tickRate > 120f) r.Errors.Add("game: tickRate out of range");
            if (t.hero.damage <= 0f || t.hero.interval <= 0f || t.hero.range <= 0f) r.Errors.Add("game: hero stats must be positive");
            if (t.slots.Count != 3) r.Errors.Add("game: exactly three station slots are required");
            var ids = new HashSet<string>();
            foreach (var s in t.slots)
            {
                ids.Add(s.id);
                if (!SlotModifiers.Contains(s.modifier)) r.Errors.Add($"slot {s.id}: unknown modifier {s.modifier}");
                Need(c, r, "slot." + s.id + ".name");
            }
            foreach (var s in t.slots)
                foreach (var a in s.adjacent)
                {
                    if (!c.SlotById.TryGetValue(a, out var other)) { r.Errors.Add($"slot {s.id}: unknown adjacent slot {a}"); continue; }
                    if (!other.adjacent.Contains(s.id)) r.Errors.Add($"slot adjacency {s.id}-{a} is not symmetric");
                }
            foreach (var tip in t.defeatTips) Need(c, r, tip.tipKey);
            if (t.arena.meleeRing <= t.arena.citadelRadius) r.Errors.Add("game: melee ring must be outside the citadel");
        }

        private static void ValidateModules(GameContent c, Report r)
        {
            if (c.Modules.Count != 6) r.Errors.Add($"expected 6 modules, found {c.Modules.Count}");
            foreach (var m in c.Modules)
            {
                string o = "module " + m.id;
                if (!Families.Contains(m.family)) r.Errors.Add(o + ": unknown family");
                if (!Behaviors.Contains(m.behavior)) r.Errors.Add(o + ": unknown behavior");
                if (m.interval <= 0f) r.Errors.Add(o + ": interval must be > 0");
                if (m.damage < 0f || m.range < 0f || m.radius < 0f || m.duration < 0f) r.Errors.Add(o + ": negative stat");
                if (m.behavior != "ward" && m.range <= 0f) r.Errors.Add(o + ": range must be > 0");
                if (m.slotStats == null || m.slotStats.Count != 3) r.Errors.Add(o + ": slotStats must define range, power and rate");
                else
                    foreach (var kv in m.slotStats)
                    {
                        if (!SlotModifiers.Contains(kv.Key)) r.Errors.Add(o + ": unknown slotStats key " + kv.Key);
                        foreach (var s in kv.Value)
                            if (!ValidStat(c, "module." + m.id + "." + s, out var why)) r.Errors.Add(o + ": slotStats " + why);
                    }
                int prev = 1;
                foreach (var tier in m.tiers)
                {
                    if (tier.tier != prev + 1) r.Errors.Add(o + ": tiers must be consecutive from 2");
                    prev = tier.tier;
                    if (tier.moonGold <= 0) r.Errors.Add(o + ": tier cost must be > 0");
                    CheckMods(c, r, o + " tier " + tier.tier, tier.mods);
                }
                if (!m.starter)
                {
                    if (string.IsNullOrEmpty(m.unlockMission) || c.Mission(m.unlockMission) == null)
                        r.Errors.Add(o + ": non-starter module needs a valid unlockMission");
                    else
                    {
                        bool granted = false;
                        foreach (var mi in c.Missions) if (mi.unlocksModule == m.id) granted = true;
                        if (!granted) r.Errors.Add(o + ": no mission unlocks this module (unreachable)");
                    }
                    if (m.unlockShards < 0) r.Errors.Add(o + ": negative unlock cost");
                }
                Need(c, r, "module." + m.id + ".name");
                Need(c, r, "module." + m.id + ".desc");
            }
            foreach (var s in c.Synergies)
            {
                string o = "synergy " + s.id;
                if (c.Module(s.a) == null || c.Module(s.b) == null) r.Errors.Add(o + ": unknown module");
                if (s.a == s.b) r.Errors.Add(o + ": a module cannot synergise with itself");
                if (!string.IsNullOrEmpty(s.beneficiary) && s.beneficiary != s.a && s.beneficiary != s.b) r.Errors.Add(o + ": beneficiary must be a or b");
                if (!string.IsNullOrEmpty(s.special) && !Specials.Contains(s.special)) r.Errors.Add(o + ": unknown special " + s.special);
                if ((s.mods == null || s.mods.Count == 0) && string.IsNullOrEmpty(s.special)) r.Errors.Add(o + ": has no effect");
                CheckMods(c, r, o, s.mods);
                Need(c, r, "synergy." + s.id + ".name");
                Need(c, r, "synergy." + s.id + ".desc");
            }
        }

        private static void ValidateEnemies(GameContent c, Report r)
        {
            int archetypes = 0;
            float heroRange = c.Tuning.hero.range;
            foreach (var e in c.Enemies)
            {
                string o = "enemy " + e.id;
                if (!e.isUnitOnly) archetypes++;
                if (e.health <= 0f || e.speed <= 0f || e.radius <= 0f) r.Errors.Add(o + ": health/speed/radius must be > 0");
                if (!e.isUnitOnly && e.cost <= 0f) r.Errors.Add(o + ": cost must be > 0");
                if (e.groupMin < 1 || e.groupMax < e.groupMin) r.Errors.Add(o + ": invalid group size");
                if (e.swarmCount < 1) r.Errors.Add(o + ": swarmCount must be >= 1");
                if (!string.IsNullOrEmpty(e.unitId) && c.Enemy(e.unitId) == null) r.Errors.Add(o + ": unknown unitId");
                bool ranged = e.role == EnemyRole.Ranged || e.role == EnemyRole.Support;
                if (ranged && e.attackRange <= 0f) r.Errors.Add(o + ": ranged enemies need attackRange");
                // Reachability: every enemy must stop inside Arc Light Cat's base range.
                if (e.attackRange > heroRange - 0.3f) r.Errors.Add(o + $": stops at {e.attackRange}m, outside hero range {heroRange}m (unreachable)");
                if (e.flying && e.p != null && e.p.TryGetValue("hoverRadius", out var hov) && hov > heroRange - 0.3f) r.Errors.Add(o + ": hovers out of range");
                if (e.armor < 0f || e.armor > 90f || e.resist < 0f || e.resist > 90f) r.Errors.Add(o + ": armor/resist must be 0-90");
                Need(c, r, "enemy." + e.id + ".name");
            }
            if (archetypes != 8) r.Errors.Add($"expected 8 ordinary enemy archetypes, found {archetypes}");
        }

        private static void ValidateBosses(GameContent c, Report r)
        {
            if (c.Bosses.Count != 3) r.Errors.Add($"expected 3 bosses, found {c.Bosses.Count}");
            foreach (var b in c.Bosses)
            {
                string o = "boss " + b.id;
                if (b.health <= 0f) r.Errors.Add(o + ": health must be > 0");
                if (b.stopDistance > c.Tuning.hero.range - 0.3f) r.Errors.Add(o + ": stops outside hero range (unreachable)");
                if (b.phases.Count == 0 || b.phases[0].phase != 1) r.Errors.Add(o + ": phase 1 must be defined first");
                for (int i = 1; i < b.phases.Count; i++)
                    if (b.phases[i].healthBelow >= b.phases[i - 1].healthBelow) r.Errors.Add(o + ": phase thresholds must decrease");
                foreach (var a in b.abilities)
                {
                    if (!BossAbilityTypes.Contains(a.type)) r.Errors.Add(o + ": unknown ability type " + a.type);
                    if (a.cooldown <= 0f) r.Errors.Add(o + ": ability " + a.id + " needs a cooldown");
                    if ((a.type == "charge" || a.type == "volley" || a.type == "sector_barrage") && a.windup < 1.5f)
                        r.Errors.Add(o + ": heavy attack " + a.id + " needs a readable windup (>= 1.5s)");
                    foreach (var s in a.summons)
                        if (c.Enemy(s.enemy) == null) r.Errors.Add(o + ": summons unknown enemy " + s.enemy);
                }
                Need(c, r, "boss." + b.id + ".name");
                Need(c, r, "boss." + b.id + ".intro");
                Need(c, r, "boss." + b.id + ".hint");
            }
        }

        private static void ValidatePerks(GameContent c, Report r)
        {
            if (c.Perks.Count != 30) r.Errors.Add($"expected 30 perks, found {c.Perks.Count}");
            var perFamily = new Dictionary<string, int>();
            foreach (var p in c.Perks)
            {
                string o = "perk " + p.id;
                if (!Families.Contains(p.family)) r.Errors.Add(o + ": unknown family");
                else { perFamily.TryGetValue(p.family, out int n); perFamily[p.family] = n + 1; }
                if (!Rarities.Contains(p.rarity)) r.Errors.Add(o + ": unknown rarity");
                if (p.maxStacks < 1) r.Errors.Add(o + ": maxStacks must be >= 1");
                if (p.tradeoff && p.rarity != "epic") r.Warnings.Add(o + ": trade-off perks are expected to be epic");
                foreach (var m in p.requiresModules)
                    if (c.Module(m) == null) r.Errors.Add(o + ": requires unknown module " + m);
                foreach (var m in p.requiresAnyModule)
                    if (c.Module(m) == null) r.Errors.Add(o + ": requires unknown module " + m);
                foreach (var q in p.requiresAnyPerk)
                {
                    if (c.Perk(q) == null) r.Errors.Add(o + ": requires unknown perk " + q);
                    else if (q == p.id) r.Errors.Add(o + ": requires itself (impossible)");
                }
                if (!string.IsNullOrEmpty(p.requiresCondition) && !Conditions.Contains(p.requiresCondition))
                    r.Errors.Add(o + ": unknown condition " + p.requiresCondition);
                CheckMods(c, r, o, p.mods);
                // Every perk must be obtainable with at least one legal loadout (3 distinct modules).
                if (!PossibleWithSomeLoadout(c, p)) r.Errors.Add(o + ": requirements can never be satisfied (impossible perk)");
                Need(c, r, "perk." + p.id + ".name");
                Need(c, r, "perk." + p.id + ".desc");
                if (c.Strings.Has("perk." + p.id + ".desc"))
                {
                    string text = TextFormat.Perk(c, p);
                    if (text.IndexOf('{') >= 0) r.Errors.Add(o + ": description has unresolved tokens: " + text);
                }
            }
            foreach (var f in Families)
            {
                perFamily.TryGetValue(f, out int n);
                if (n != 5) r.Errors.Add($"family {f} must have exactly 5 perks (has {n})");
            }
            if (c.Fallbacks.Count < c.Tuning.perkOffer.choices) r.Errors.Add("need at least as many fallback rewards as offer choices");
        }

        private static bool PossibleWithSomeLoadout(GameContent c, PerkDef p)
        {
            var ids = new List<string>();
            foreach (var m in c.Modules) ids.Add(m.id);
            for (int a = 0; a < ids.Count; a++)
                for (int b = a + 1; b < ids.Count; b++)
                    for (int d = b + 1; d < ids.Count; d++)
                    {
                        var ctx = new Sim.PerkContext { heroChainTargets = 0 };
                        ctx.equippedModules.Add(ids[a]);
                        ctx.equippedModules.Add(ids[b]);
                        ctx.equippedModules.Add(ids[d]);
                        foreach (var q in p.requiresAnyPerk) ctx.stacks[q] = 1;
                        if (Sim.PerkSystem.IsEligible(p, ctx, out _)) return true;
                        ctx.heroChainTargets = 1;
                        if (Sim.PerkSystem.IsEligible(p, ctx, out _)) return true;
                    }
            return false;
        }

        private static void ValidateUpgrades(GameContent c, Report r)
        {
            if (c.Upgrades.Count != 6) r.Errors.Add($"expected 6 run upgrade tracks, found {c.Upgrades.Count}");
            foreach (var u in c.Upgrades)
            {
                if (u.baseCost <= 0 || u.maxLevel <= 0) r.Errors.Add("upgrade " + u.id + ": cost/max must be > 0");
                CheckMods(c, r, "upgrade " + u.id, u.mods);
                Need(c, r, "upgrade." + u.id + ".name");
                Need(c, r, "upgrade." + u.id + ".desc");
            }
        }

        private static void ValidateProgression(GameContent c, Report r)
        {
            var pg = c.Progression;
            foreach (var n in pg.nodes)
            {
                string o = "node " + n.id;
                if (n.maxLevel < 1 || n.baseCost <= 0) r.Errors.Add(o + ": maxLevel/cost must be > 0");
                if (!string.IsNullOrEmpty(n.requiresNode))
                {
                    if (!c.NodeById.TryGetValue(n.requiresNode, out var req)) r.Errors.Add(o + ": requires unknown node");
                    else if (n.requiresLevel > req.maxLevel) r.Errors.Add(o + ": requires a level that does not exist (impossible)");
                }
                if (!string.IsNullOrEmpty(n.requiresMission) && c.Mission(n.requiresMission) == null) r.Errors.Add(o + ": requires unknown mission");
                CheckMods(c, r, o, n.mods);
                Need(c, r, "node." + n.id + ".name");
                Need(c, r, "node." + n.id + ".desc");
            }
            // cycle detection in node prerequisites
            foreach (var n in pg.nodes)
            {
                var seen = new HashSet<string>();
                var cur = n;
                while (cur != null && !string.IsNullOrEmpty(cur.requiresNode))
                {
                    if (!seen.Add(cur.id)) { r.Errors.Add("node prerequisite cycle at " + n.id); break; }
                    c.NodeById.TryGetValue(cur.requiresNode, out cur);
                }
            }
            foreach (var cos in pg.cosmetics)
            {
                if (!string.IsNullOrEmpty(cos.achievement) && !c.AchievementById.ContainsKey(cos.achievement))
                    r.Errors.Add("cosmetic " + cos.id + ": unknown achievement");
                Need(c, r, "cosmetic." + cos.id + ".name");
            }
            if (pg.achievements.Count < 18) r.Warnings.Add("fewer than ~20 achievements");
            foreach (var a in pg.achievements)
            {
                if (!LifetimeStats.Contains(a.stat)) r.Errors.Add("achievement " + a.id + ": unknown stat " + a.stat);
                if (a.target < 1) r.Errors.Add("achievement " + a.id + ": target must be >= 1");
                if (!string.IsNullOrEmpty(a.reward?.cosmetic) && !c.CosmeticById.ContainsKey(a.reward.cosmetic))
                    r.Errors.Add("achievement " + a.id + ": unknown reward cosmetic");
                Need(c, r, "achievement." + a.id + ".name");
                Need(c, r, "achievement." + a.id + ".desc");
            }
            foreach (var d in pg.dailyObjectives)
            {
                if (!LifetimeStats.Contains(d.stat)) r.Errors.Add("objective " + d.id + ": unknown stat " + d.stat);
                if (!string.IsNullOrEmpty(d.requiresMission) && c.Mission(d.requiresMission) == null) r.Errors.Add("objective " + d.id + ": unknown mission");
                Need(c, r, "objective." + d.id + ".desc");
            }
            if (pg.dailyObjectives.Count < 3) r.Errors.Add("need at least 3 daily objectives");
            if (pg.attendance.Count != 7) r.Errors.Add("attendance must have 7 days");
        }

        private static void ValidateRoutes(GameContent c, Report r)
        {
            var a = c.Tuning.arena;
            foreach (var layout in c.RouteLayouts)
            {
                if (layout.routes.Count < 3) r.Errors.Add("layout " + layout.id + ": needs at least 3 routes");
                foreach (var route in layout.routes)
                {
                    string o = "route " + layout.id + "/" + route.id;
                    if (route.points.Count < 2) { r.Errors.Add(o + ": needs 2+ points"); continue; }
                    foreach (var p in route.points)
                    {
                        if (p.Length != 2) { r.Errors.Add(o + ": point must be [x,y]"); continue; }
                        if (Math.Abs(p[0]) > a.width * 0.5f || Math.Abs(p[1]) > a.height * 0.5f) r.Errors.Add(o + ": point outside arena");
                    }
                    var start = route.points[0];
                    var end = route.points[route.points.Count - 1];
                    float endR = (float)Math.Sqrt(end[0] * end[0] + end[1] * end[1]);
                    float startR = (float)Math.Sqrt(start[0] * start[0] + start[1] * start[1]);
                    if (endR < a.citadelRadius + 0.3f) r.Errors.Add(o + ": ends inside the citadel");
                    if (endR > a.approachRadius + 0.6f) r.Warnings.Add(o + ": ends far from the citadel");
                    if (startR < 6f) r.Errors.Add(o + ": must start near the arena edge (spawns never appear on the tower)");
                }
            }
        }

        private static void ValidateMissions(GameContent c, Report r)
        {
            if (c.Missions.Count != 12) r.Errors.Add($"expected 12 missions, found {c.Missions.Count}");
            var indexes = new HashSet<int>();
            foreach (var m in c.Missions)
            {
                string o = "mission " + m.id;
                if (!indexes.Add(m.index)) r.Errors.Add(o + ": duplicate index");
                if (m.waves < 1) r.Errors.Add(o + ": needs waves");
                if (m.budget <= 0f || m.budgetGrowth < 1f) r.Errors.Add(o + ": invalid budget");
                if (!c.LayoutById.ContainsKey(m.routeLayout ?? "")) r.Errors.Add(o + ": unknown route layout");
                if (m.biome != "gravewood" && m.biome != "moonfall") r.Errors.Add(o + ": unknown biome");
                if (m.index > 1)
                {
                    var req = c.Mission(m.requiresMission);
                    if (req == null) r.Errors.Add(o + ": must require a previous mission (unreachable)");
                    else if (req.index >= m.index) r.Errors.Add(o + ": requires a later mission (broken unlock chain)");
                }
                if (m.pool.Count == 0) r.Errors.Add(o + ": empty enemy pool");
                foreach (var pe in m.pool)
                {
                    var e = c.Enemy(pe.enemy);
                    if (e == null) r.Errors.Add(o + ": pool has unknown enemy " + pe.enemy);
                    else if (e.isUnitOnly) r.Errors.Add(o + ": pool uses unit-only enemy " + pe.enemy);
                    if (pe.fromWave > m.waves) r.Warnings.Add(o + ": " + pe.enemy + " never appears");
                }
                foreach (var s in m.scripted)
                {
                    if (s.wave < 1 || s.wave > m.waves) r.Errors.Add(o + ": scripted wave out of range");
                    foreach (var en in s.entries) if (c.Enemy(en.enemy) == null) r.Errors.Add(o + ": scripted unknown enemy " + en.enemy);
                    if (!string.IsNullOrEmpty(s.announceKey)) Need(c, r, s.announceKey);
                }
                if (!string.IsNullOrEmpty(m.boss) && c.Boss(m.boss) == null) r.Errors.Add(o + ": unknown boss");
                foreach (var mod in m.modifiers) if (!c.ModifierById.ContainsKey(mod)) r.Errors.Add(o + ": unknown modifier " + mod);
                foreach (var su in m.slotUnlocks)
                {
                    if (!c.SlotById.ContainsKey(su.slot)) r.Errors.Add(o + ": unknown slot " + su.slot);
                    if (su.wave < 1 || su.wave > m.waves) r.Errors.Add(o + ": slot unlock wave out of range");
                    if (!string.IsNullOrEmpty(su.grantModule) && c.Module(su.grantModule) == null) r.Errors.Add(o + ": grants unknown module");
                }
                if (!string.IsNullOrEmpty(m.unlocksModule) && c.Module(m.unlocksModule) == null) r.Errors.Add(o + ": unlocks unknown module");
                bool elite5 = false, elite10 = false, elite15 = false;
                foreach (var s in m.scripted)
                    foreach (var en in s.entries)
                        if (en.elite) { if (s.wave == 5) elite5 = true; if (s.wave == 10) elite10 = true; if (s.wave == 15) elite15 = true; }
                if (m.waves >= 20 && !(elite5 && elite10 && elite15)) r.Warnings.Add(o + ": missing elite encounter at wave 5/10/15");
                Need(c, r, "mission." + m.id + ".name");
                Need(c, r, "mission." + m.id + ".desc");
            }
            if (c.Mission("m01") == null) r.Errors.Add("missing first mission m01");
            foreach (var mod in c.Modifiers) Need(c, r, "modifier." + mod.id + ".name");
            foreach (var pe in c.Endless.pool) if (c.Enemy(pe.enemy) == null) r.Errors.Add("endless: unknown enemy " + pe.enemy);
            foreach (var id in c.Endless.modifierCycle) if (!c.ModifierById.ContainsKey(id)) r.Errors.Add("endless: unknown modifier " + id);
            foreach (var id in c.Endless.bossCycle) if (c.Boss(id) == null) r.Errors.Add("endless: unknown boss " + id);
            foreach (var pe in c.Daily.pool) if (c.Enemy(pe.enemy) == null) r.Errors.Add("daily: unknown enemy " + pe.enemy);
            foreach (var id in c.Daily.modifierChoices) if (!c.ModifierById.ContainsKey(id)) r.Errors.Add("daily: unknown modifier " + id);
            foreach (var id in c.Daily.bossChoices) if (c.Boss(id) == null) r.Errors.Add("daily: unknown boss " + id);
            if (c.Mission(c.Endless.requiresMission) == null) r.Errors.Add("endless: unknown unlock mission");
            if (c.Mission(c.Daily.requiresMission) == null) r.Errors.Add("daily: unknown unlock mission");
        }

        private static void ValidateStrings(GameContent c, Report r)
        {
            string[] required =
            {
                "game.title", "hero.name", "ui.continue_guest", "ui.play", "ui.victory", "ui.defeat", "ui.perk_title",
                "ui.resume_title", "ui.resume_body", "tip.default", "story.1", "story.2", "story.3", "story.4",
                "ability.arc_storm.name", "ability.ward.name", "priority.nearest", "priority.strongest", "priority.rangedThreat",
            };
            foreach (var k in required) Need(c, r, k);
            foreach (var f in c.Fallbacks) { Need(c, r, "fallback." + f.id + ".name"); Need(c, r, "fallback." + f.id + ".desc"); }
        }
    }
}
