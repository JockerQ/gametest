using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;
using EvilCats.Meta;
using EvilCats.Sim;
using NUnit.Framework;

namespace EvilCats.Tests
{
    internal static class Sandbox
    {
        public static Battle New(Dictionary<string, string> loadout = null, bool emit = true, GameContent content = null)
        {
            var setup = new BattleSetup
            {
                mode = BattleMode.Campaign,
                missionId = "m02",
                seed = 42,
                sandbox = true,
                emitEvents = emit,
                loadout = loadout ?? new Dictionary<string, string>(),
            };
            foreach (var kv in setup.loadout) setup.unlockedSlots.Add(kv.Key);
            return new Battle(content ?? TestContent.Load(), setup);
        }

        public static void Ticks(Battle b, int n) { for (int i = 0; i < n; i++) b.Tick(); }
    }

    public class StatsTests
    {
        [Test]
        public void BaseStatsComeFromData()
        {
            var b = Sandbox.New();
            Assert.That(b.MaxHp, Is.EqualTo(1000f).Within(0.01f));
            Assert.That(b.Stats.hero.damage, Is.EqualTo(12f).Within(0.01f));
            Assert.That(b.Stats.hero.interval, Is.EqualTo(1.0f).Within(0.001f));
            Assert.That(b.Stats.hero.critChance, Is.EqualTo(0.05f).Within(1e-4f));
            Assert.That(b.Stats.hero.critMultiplier, Is.EqualTo(1.5f).Within(1e-4f));
            Assert.That(b.StormCooldownTotal, Is.EqualTo(25f).Within(0.01f));
            Assert.That(b.WardCooldownTotal, Is.EqualTo(35f).Within(0.01f));
        }

        [Test]
        public void PercentBonusesAddAndTradeoffsMultiply()
        {
            var c = TestContent.Load();
            var src = new StatSources();
            src.upgradeLevels["damage"] = 2;                  // +8% x2 = +16%
            src.nodeLevels["pm_arc_power"] = 1;               // hero.damage +6% (separate stat bucket)
            src.perkStacks["arc_overcharged_crown"] = 1;      // dmg.arc x1.3 and max health x0.85
            var d = StatsBuilder.Build(c, src);
            // hero damage = 12 * (1 + 0.06) [hero.damage] * (1 + 0.16) [dmg.all] * 1.3 [dmg.arc]
            Assert.That(d.hero.damage, Is.EqualTo(12f * 1.06f * 1.16f * 1.3f).Within(0.001f));
            Assert.That(d.citadel.maxHealth, Is.EqualTo(1000f * 0.85f).Within(0.01f));
        }

        [Test]
        public void RebuildingStatsNeverCompounds()
        {
            var b = Sandbox.New();
            b.DebugAddSparks(10000);
            b.BuyUpgrade("damage");
            float once = b.Stats.hero.damage;
            b.RebuildStats();
            b.RebuildStats();
            Assert.That(b.Stats.hero.damage, Is.EqualTo(once).Within(1e-4f));
        }

        [Test]
        public void AttackSpeedShortensIntervalByRate()
        {
            var c = TestContent.Load();
            var src = new StatSources();
            src.upgradeLevels["attack_speed"] = 5;           // +30% rate
            var d = StatsBuilder.Build(c, src);
            Assert.That(d.hero.interval, Is.EqualTo(1.0f / 1.3f).Within(1e-4f));
        }

        [Test]
        public void MaxHealthIncreaseHealsTheGainedAmount()
        {
            var b = Sandbox.New();
            b.DebugSetHp(500f);
            b.DebugAddSparks(1000);
            Assert.That(b.BuyUpgrade("max_health"), Is.EqualTo(PurchaseResult.Bought));
            Assert.That(b.MaxHp, Is.EqualTo(1100f).Within(0.01f));
            Assert.That(b.Hp, Is.EqualTo(600f).Within(0.01f), "healing rule: current health rises by the max-health gain");
        }

        [Test]
        public void MaxHealthDecreaseClampsCurrentHealth()
        {
            var b = Sandbox.New();
            Assert.That(b.Hp, Is.EqualTo(1000f).Within(0.01f));
            b.DebugAddPerk("arc_overcharged_crown");
            Assert.That(b.MaxHp, Is.EqualTo(850f).Within(0.01f));
            Assert.That(b.Hp, Is.EqualTo(850f).Within(0.01f));
        }

        [Test]
        public void SlotModifiersApplyToTheRightStats()
        {
            var c = TestContent.Load();
            var coil = c.Module("arc_coil");
            var crown = StatsBuilder.Build(c, new StatSources { loadout = { ["crown"] = "arc_coil" } }).Module("arc_coil");
            var middle = StatsBuilder.Build(c, new StatSources { loadout = { ["middle"] = "arc_coil" } }).Module("arc_coil");
            var bottom = StatsBuilder.Build(c, new StatSources { loadout = { ["base"] = "arc_coil" } }).Module("arc_coil");
            Assert.That(crown.range, Is.EqualTo(coil.range * 1.15f).Within(1e-3f), "Crown: +15% range");
            Assert.That(middle.damage, Is.EqualTo(coil.damage * 1.10f).Within(1e-3f), "Middle: +10% damage");
            Assert.That(bottom.interval, Is.EqualTo(coil.interval / 1.10f).Within(1e-3f), "Base: +10% rate");
            Assert.That(crown.damage, Is.EqualTo(coil.damage).Within(1e-3f));
        }

        [Test]
        public void WardLanternUsesAuraRadiusForCrownAndBarrierForMiddle()
        {
            var c = TestContent.Load();
            var def = c.Module("ward_lantern");
            var crown = StatsBuilder.Build(c, new StatSources { loadout = { ["crown"] = "ward_lantern" } }).Module("ward_lantern");
            var middle = StatsBuilder.Build(c, new StatSources { loadout = { ["middle"] = "ward_lantern" } }).Module("ward_lantern");
            Assert.That(crown.P("auraRadius"), Is.EqualTo(def.p["auraRadius"] * 1.15f).Within(1e-3f));
            Assert.That(middle.P("barrierFraction"), Is.EqualTo(def.p["barrierFraction"] * 1.10f).Within(1e-4f));
            Assert.That(middle.P("repair"), Is.EqualTo(def.p["repair"] * 1.10f).Within(1e-4f));
        }

        [Test]
        public void SynergiesRequireAdjacentSlots()
        {
            var c = TestContent.Load();
            // Crown and Base are NOT adjacent; Middle touches both.
            var apart = StatsBuilder.ActiveSynergies(c, new Dictionary<string, string> { ["crown"] = "arc_coil", ["base"] = "frost_whisker" });
            var adjacent = StatsBuilder.ActiveSynergies(c, new Dictionary<string, string> { ["crown"] = "arc_coil", ["middle"] = "frost_whisker" });
            Assert.That(apart, Is.Empty);
            Assert.That(adjacent.Count, Is.EqualTo(1));
            var d = StatsBuilder.Build(c, new StatSources { loadout = { ["crown"] = "arc_coil", ["middle"] = "frost_whisker" } });
            Assert.That(d.Module("arc_coil").targets, Is.EqualTo(c.Module("arc_coil").targets + 1), "Arc Coil beside Frost Whisker: +1 chain target");
            Assert.That(d.Module("frost_whisker").activeSynergies, Contains.Item("syn_storm_frost"), "synergy shown on both modules");
        }

        [Test]
        public void EmberGravitySynergyWidensExplosions()
        {
            var c = TestContent.Load();
            var d = StatsBuilder.Build(c, new StatSources { loadout = { ["middle"] = "ember_maw", ["base"] = "gravity_paw" } });
            Assert.That(d.Module("ember_maw").radius, Is.EqualTo(c.Module("ember_maw").radius * 1.2f).Within(1e-3f));
        }

        [Test]
        public void WardBallistaSynergyOnlyHastesTheBallista()
        {
            var c = TestContent.Load();
            var d = StatsBuilder.Build(c, new StatSources { loadout = { ["crown"] = "ward_lantern", ["middle"] = "bone_ballista" } });
            Assert.That(d.Module("bone_ballista").synergyValues.ContainsKey("barrierHaste"), Is.True);
            Assert.That(d.Module("ward_lantern").synergyValues.ContainsKey("barrierHaste"), Is.False);
            Assert.That(d.Module("ward_lantern").activeSynergies, Contains.Item("syn_ward_bone"));
        }
    }

    public class EconomyFormulaTests
    {
        [Test]
        public void UpgradeCostFollowsSpecFormula()
        {
            var def = new RunUpgradeDef { baseCost = 20, maxLevel = 10 };
            for (int level = 0; level < 10; level++)
                Assert.That(Battle.UpgradeCostAt(def, level, 1.16f), Is.EqualTo((int)Math.Ceiling(20 * Math.Pow(1.16, level) - 1e-9)), "level " + level);
            Assert.That(Battle.UpgradeCostAt(def, 0, 1.16f), Is.EqualTo(20));
            Assert.That(Battle.UpgradeCostAt(def, 1, 1.16f), Is.EqualTo(24));   // ceil(23.2)
            Assert.That(Battle.UpgradeCostAt(def, 5, 1.16f), Is.EqualTo(43));   // ceil(42.0068)
        }

        [Test]
        public void BuyingRespectsMaxLevelAndSparks()
        {
            var b = Sandbox.New();
            Assert.That(b.BuyUpgrade("crit"), Is.EqualTo(PurchaseResult.NotEnoughSparks));
            b.DebugAddSparks(100000);
            var def = b.C.UpgradeById["crit"];
            for (int i = 0; i < def.maxLevel; i++) Assert.That(b.BuyUpgrade("crit"), Is.EqualTo(PurchaseResult.Bought));
            Assert.That(b.BuyUpgrade("crit"), Is.EqualTo(PurchaseResult.MaxLevel));
            Assert.That(b.BuyUpgrade("not_a_track"), Is.EqualTo(PurchaseResult.Unknown));
        }

        [Test]
        public void CritChanceIsCapped()
        {
            var c = TestContent.Load();
            var src = new StatSources();
            src.upgradeLevels["crit"] = 50;
            Assert.That(StatsBuilder.Build(c, src).hero.critChance, Is.EqualTo(c.Tuning.hero.critChanceCap).Within(1e-4f));
        }

        [Test]
        public void XpRequirementMatchesFormula()
        {
            var c = TestContent.Load();
            for (int L = 0; L < 12; L++)
                Assert.That(Battle.XpRequirement(c, L), Is.EqualTo(30 + 20 * L + 5 * L * L).Within(1e-3f));
        }
    }

    public class TargetingTests
    {
        private static Battle WithThree(out Enemy near, out Enemy strong, out Enemy archer)
        {
            var b = Sandbox.New();
            near = b.DebugSpawn("rat_raider", new Vec2(3.2f, 0f));
            strong = b.DebugSpawn("shield_guard", new Vec2(0f, 5f));
            archer = b.DebugSpawn("crow_archer", new Vec2(-5f, 0f));
            return b;
        }

        [Test]
        public void NearestPicksClosestToCitadel()
        {
            var b = WithThree(out var near, out _, out _);
            Assert.That(Targeting.Select(b.Enemies, Vec2.Zero, 7f, TargetPriority.Nearest), Is.SameAs(near));
        }

        [Test]
        public void StrongestPicksHighestHealth()
        {
            var b = WithThree(out _, out var strong, out _);
            Assert.That(Targeting.Select(b.Enemies, Vec2.Zero, 7f, TargetPriority.Strongest), Is.SameAs(strong));
        }

        [Test]
        public void RangedThreatPrefersArchersAndPriests()
        {
            var b = WithThree(out _, out _, out var archer);
            Assert.That(Targeting.Select(b.Enemies, Vec2.Zero, 7f, TargetPriority.RangedThreat), Is.SameAs(archer));
        }

        [Test]
        public void TargetsOutsideRangeAreIgnored()
        {
            var b = Sandbox.New();
            b.DebugSpawn("rat_raider", new Vec2(7.5f, 0f));
            Assert.That(Targeting.Select(b.Enemies, Vec2.Zero, 7f, TargetPriority.Nearest), Is.Null);
        }

        [Test]
        public void ClusterPicksTheDensestGroup()
        {
            var b = Sandbox.New();
            b.DebugSpawn("rat_raider", new Vec2(-4f, 0f));
            var c1 = b.DebugSpawn("rat_raider", new Vec2(4f, 1f));
            b.DebugSpawn("rat_raider", new Vec2(4.5f, 1.2f));
            b.DebugSpawn("rat_raider", new Vec2(4.2f, 0.6f));
            Assert.That(Targeting.BestCluster(b.Enemies, Vec2.Zero, 7f, 1.5f, false, false, out var p, out int n), Is.True);
            Assert.That(n, Is.EqualTo(3));
            Assert.That(Vec2.Distance(p, c1.pos), Is.LessThan(1f));
        }
    }

    public class CombatTests
    {
        [Test]
        public void ArcBoltFiresAutomaticallyWithoutInput()
        {
            var b = Sandbox.New();
            var rat = b.DebugSpawn("rat_raider", new Vec2(4f, 0f));
            float before = rat.hp;
            Sandbox.Ticks(b, 3);
            Assert.That(rat.hp, Is.LessThan(before));
        }

        [Test]
        public void ChainNeverHitsTheSameEnemyTwice()
        {
            var b = Sandbox.New();
            // three enemies in a line, 5 chain targets available: each is hit exactly once per bolt
            b.DebugAddPerk("arc_forked_bolt");
            b.DebugAddPerk("arc_forked_bolt");
            b.DebugAddPerk("arc_forked_bolt");
            var a = b.DebugSpawn("iron_golem", new Vec2(3f, 0f));
            var c = b.DebugSpawn("iron_golem", new Vec2(4.5f, 0f));
            var d = b.DebugSpawn("iron_golem", new Vec2(6f, 0f));
            var hits = new Dictionary<int, int>();
            b.Tick();
            var ev = new List<SimEvent>();
            b.DrainEvents(ev);
            foreach (var e in ev)
                if (e.type == SimEventType.EnemyHit && e.id == "hero") { hits.TryGetValue(e.uid, out int n); hits[e.uid] = n + 1; }
            Assert.That(hits.Count, Is.EqualTo(3), "all three struck");
            foreach (var kv in hits) Assert.That(kv.Value, Is.EqualTo(1), "enemy " + kv.Key + " hit once");
            Assert.That(b.RunStats.maxChain, Is.EqualTo(3));
        }

        [Test]
        public void ChainDamageFallsOffPerHop()
        {
            var content = TestContent.Fresh();
            content.Tuning.hero.critChance = 0f;
            var b = Sandbox.New(null, true, content);
            b.DebugAddPerk("arc_forked_bolt");
            b.DebugSpawn("iron_golem", new Vec2(3f, 0f));
            b.DebugSpawn("iron_golem", new Vec2(4.5f, 0f));
            b.Tick();
            var ev = new List<SimEvent>();
            b.DrainEvents(ev);
            var dmg = new List<float>();
            foreach (var e in ev) if (e.type == SimEventType.EnemyHit && e.id == "hero") dmg.Add(e.value);
            Assert.That(dmg.Count, Is.EqualTo(2));
            // golems resist 20% of elemental damage; the hop keeps chainFalloff of the previous damage
            Assert.That(dmg[1] / dmg[0], Is.EqualTo(content.Tuning.hero.chainFalloff).Within(1e-3f));
        }

        [Test]
        public void SlowNeverExceedsTheCap()
        {
            var b = Sandbox.New();
            var rat = b.DebugSpawn("rat_raider", new Vec2(4f, 0f));
            rat.slowFrost = 0.95f; rat.slowFrostTime = 5f;
            rat.slowOther = 0.9f; rat.slowOtherTime = 5f;
            Assert.That(b.SlowFactor(rat), Is.EqualTo(b.C.Tuning.control.slowCap).Within(1e-5f));
            var boss = b.DebugSpawn("sir_barkhelm", new Vec2(0f, 5f));
            boss.slowFrost = 0.95f; boss.slowFrostTime = 5f;
            Assert.That(b.SlowFactor(boss), Is.EqualTo(b.C.Tuning.control.bossSlowCap).Within(1e-5f));
        }

        [Test]
        public void RepeatedStunsHaveDiminishingReturns()
        {
            var b = Sandbox.New();
            var rat = b.DebugSpawn("rat_raider", new Vec2(4f, 0f));
            var durations = new List<float>();
            for (int i = 0; i < 4; i++)
            {
                rat.stunTime = 0f;
                b.ApplyStun(rat, 2f);
                durations.Add(rat.stunTime);
            }
            Assert.That(durations[1], Is.LessThan(durations[0]));
            Assert.That(durations[3], Is.LessThanOrEqualTo(2f * (1f - b.C.Tuning.control.fatigueMax) + 1e-4f), "fatigue floor prevents infinite stun");
        }

        [Test]
        public void BossesResistControlDuration()
        {
            var b = Sandbox.New();
            var boss = b.DebugSpawn("sir_barkhelm", new Vec2(0f, 4f));
            b.ApplyStun(boss, 1.5f);
            Assert.That(boss.stunTime, Is.EqualTo(1.5f * (1f - b.C.Boss("sir_barkhelm").controlResist)).Within(1e-4f));
        }

        [Test]
        public void BurningIsCappedAtTheStackLimit()
        {
            var b = Sandbox.New(new Dictionary<string, string> { ["middle"] = "ember_maw" });
            var golem = b.DebugSpawn("iron_golem", new Vec2(4f, 0f));
            int cap = (int)b.Stats.Module("ember_maw").P("burnStacks");
            Sandbox.Ticks(b, 30 * 30);
            Assert.That(golem.burnCount, Is.LessThanOrEqualTo(cap));
        }

        [Test]
        public void FrozenEnemiesGetFreezeImmunityAfterwards()
        {
            var b = Sandbox.New(new Dictionary<string, string> { ["middle"] = "frost_whisker" });
            var rat = b.DebugSpawn("rat_raider", new Vec2(4f, 0f));
            rat.speed = 0f;
            bool froze = false, immuneAfter = false;
            for (int i = 0; i < 30 * 20 && rat.alive; i++)
            {
                b.Tick();
                if (rat.frozenTime > 0f) froze = true;
                if (froze && rat.frozenTime <= 0f && rat.freezeImmuneTime > 0f) { immuneAfter = true; break; }
                rat.hp = rat.maxHp;
            }
            Assert.That(froze, Is.True);
            Assert.That(immuneAfter, Is.True);
        }

        [Test]
        public void BarrierAbsorbsBeforeHealth()
        {
            var b = Sandbox.New();
            Assert.That(b.CastWard(), Is.EqualTo(AbilityResult.Cast));
            float barrier = b.BarrierTotal;
            Assert.That(barrier, Is.EqualTo(b.MaxHp * 0.2f).Within(0.5f));
            var rat = b.DebugSpawn("rat_raider", new Vec2(2.7f, 0f));
            rat.state = MoveState.Holding;
            rat.attackTimer = 0f;
            b.Tick();
            Assert.That(b.Hp, Is.EqualTo(b.MaxHp).Within(0.01f), "health untouched while the barrier holds");
            Assert.That(b.BarrierTotal, Is.LessThan(barrier));
        }

        [Test]
        public void WardDurationAndCooldownComeFromData()
        {
            var b = Sandbox.New();
            b.CastWard();
            Assert.That(b.CastWard(), Is.EqualTo(AbilityResult.OnCooldown));
            Sandbox.Ticks(b, (int)(5.2f * 30));
            Assert.That(b.BarrierTotal, Is.EqualTo(0f).Within(0.01f), "barrier lasts 5 seconds");
            Assert.That(b.WardCooldown, Is.GreaterThan(0f));
        }

        [Test]
        public void ArcStormOnEmptyAreaDoesNotUseTheCooldown()
        {
            var b = Sandbox.New();
            b.DebugSpawn("rat_raider", new Vec2(4f, 0f));
            Assert.That(b.CastArcStorm(new Vec2(-5f, -5f)), Is.EqualTo(AbilityResult.NoTargets));
            Assert.That(b.StormCooldown, Is.EqualTo(0f));
            Assert.That(b.CastArcStorm(new Vec2(4f, 0f)), Is.EqualTo(AbilityResult.Cast));
            Assert.That(b.StormCooldown, Is.EqualTo(b.StormCooldownTotal).Within(0.01f));
        }

        [Test]
        public void ArcStormStrikesAtMostFiveForTripleDamage()
        {
            var content = TestContent.Fresh();
            content.Tuning.hero.critChance = 0f;
            var b = Sandbox.New(null, true, content);
            for (int i = 0; i < 8; i++) b.DebugSpawn("iron_golem", new Vec2(4f + 0.1f * i, 0.1f * i));
            b.CastArcStorm(new Vec2(4.3f, 0.3f));
            var ev = new List<SimEvent>();
            b.DrainEvents(ev);
            int strikes = 0;
            foreach (var e in ev) if (e.type == SimEventType.ArcStormStrike) { strikes++; Assert.That(e.value, Is.EqualTo(b.Stats.hero.damage * 3f).Within(1e-3f)); }
            Assert.That(strikes, Is.EqualTo(5));
        }

        [Test]
        public void PowderRatFuseCanBeInterrupted()
        {
            var b = Sandbox.New();
            var rat = b.DebugSpawn("powder_rat", new Vec2(0f, 4.0f));
            b.Tick();
            Assert.That(rat.powder, Is.EqualTo(PowderState.Fuse));
            b.ApplyStun(rat, 1.5f);
            Assert.That(rat.powder, Is.EqualTo(PowderState.Dazed));
            Assert.That(b.RunStats.powderInterrupts, Is.EqualTo(1));
        }

        [Test]
        public void LastThreadTriggersOncePerRun()
        {
            var b = Sandbox.New(new Dictionary<string, string> { ["middle"] = "ward_lantern" });
            b.DebugAddPerk("ward_last_thread");
            b.DebugSetHp(250f);
            var golem = b.DebugSpawn("iron_golem", new Vec2(2.9f, 0f));
            golem.damage = 100f; golem.state = MoveState.Holding; golem.attackTimer = 0f;
            b.Tick();
            Assert.That(b.LastThreadUsed, Is.True);
            Assert.That(b.Hp, Is.EqualTo(250f).Within(1f), "the emergency barrier absorbed the hit");
        }

        [Test]
        public void GravityPawDoesNotMoveGolemsOrBosses()
        {
            var b = Sandbox.New(new Dictionary<string, string> { ["middle"] = "gravity_paw" });
            var golem = b.DebugSpawn("iron_golem", new Vec2(4f, 0f));
            var rat = b.DebugSpawn("rat_raider", new Vec2(5f, 0.5f));
            golem.speed = 0f; rat.speed = 0f;
            Vec2 g0 = golem.pos;
            Sandbox.Ticks(b, 30 * 3);
            Assert.That(Vec2.Distance(golem.pos, g0), Is.LessThan(0.01f));
            Assert.That(b.RunStats.pulls, Is.GreaterThan(0));
        }
    }

    public class PerkTests
    {
        private static PerkContext Ctx(params string[] modules)
        {
            var ctx = new PerkContext();
            foreach (var m in modules) ctx.equippedModules.Add(m);
            return ctx;
        }

        [Test]
        public void ModulePerksNeedTheirModule()
        {
            var c = TestContent.Load();
            Assert.That(PerkSystem.IsEligible(c.Perk("ember_molten_shell"), Ctx("arc_coil"), out _), Is.False);
            Assert.That(PerkSystem.IsEligible(c.Perk("ember_molten_shell"), Ctx("ember_maw"), out _), Is.True);
            Assert.That(PerkSystem.IsEligible(c.Perk("arc_static_mark"), Ctx(), out _), Is.True, "Arc perks are always relevant");
        }

        [Test]
        public void ConditionalPerksAreNotOfferedAsDeadChoices()
        {
            var c = TestContent.Load();
            Assert.That(PerkSystem.IsEligible(c.Perk("arc_thunderclap"), Ctx("ember_maw"), out _), Is.False, "no chain source");
            Assert.That(PerkSystem.IsEligible(c.Perk("arc_thunderclap"), Ctx("arc_coil"), out _), Is.True);
            Assert.That(PerkSystem.IsEligible(c.Perk("arc_conductive_chill"), Ctx("arc_coil"), out _), Is.False, "no slow source");
            Assert.That(PerkSystem.IsEligible(c.Perk("frost_brittle_armour"), Ctx("frost_whisker"), out _), Is.False, "needs physical damage");
            Assert.That(PerkSystem.IsEligible(c.Perk("frost_brittle_armour"), Ctx("frost_whisker", "bone_ballista"), out _), Is.True);
        }

        [Test]
        public void StackCapsAreRespected()
        {
            var c = TestContent.Load();
            var ctx = Ctx();
            ctx.stacks["arc_forked_bolt"] = c.Perk("arc_forked_bolt").maxStacks;
            Assert.That(PerkSystem.IsEligible(c.Perk("arc_forked_bolt"), ctx, out var why), Is.False);
            Assert.That(why, Is.EqualTo("max_stacks"));
        }

        [Test]
        public void OffersHaveThreeDistinctChoicesAndNeverDuplicates()
        {
            var c = TestContent.Load();
            var rng = new Rng(7);
            for (int i = 0; i < 300; i++)
            {
                var offer = PerkSystem.Generate(c, Ctx("arc_coil", "ember_maw", "frost_whisker"), rng, i);
                Assert.That(offer.choices.Count, Is.EqualTo(3));
                var ids = new HashSet<string>();
                foreach (var ch in offer.choices) Assert.That(ids.Add(ch.perkId ?? ch.fallbackId), Is.True, "duplicate in offer");
                foreach (var ch in offer.choices)
                    if (ch.perkId != null)
                        Assert.That(PerkSystem.IsEligible(c.Perk(ch.perkId), Ctx("arc_coil", "ember_maw", "frost_whisker"), out _), Is.True);
            }
        }

        [Test]
        public void FallbacksFillOffersWhenPerksRunOut()
        {
            var c = TestContent.Load();
            var ctx = Ctx();
            foreach (var p in c.Perks) ctx.stacks[p.id] = p.maxStacks;   // everything maxed
            var offer = PerkSystem.Generate(c, ctx, new Rng(1), 20);
            Assert.That(offer.choices.Count, Is.EqualTo(3));
            foreach (var ch in offer.choices) Assert.That(ch.fallbackId, Is.Not.Null);
        }

        [Test]
        public void LevelUpPausesTheBattleUntilAPerkIsChosen()
        {
            var b = Sandbox.New();
            // defeat enough enemies to level up
            for (int i = 0; i < 12 && b.Phase == BattlePhase.Running; i++)
            {
                var rat = b.DebugSpawn("rat_raider", new Vec2(3f, 0f));
                b.DealDamage(rat, 9999f, DamageType.True, "test", HitKind.Effect);
            }
            Assert.That(b.Phase, Is.EqualTo(BattlePhase.AwaitingPerk));
            float t = b.Time;
            Sandbox.Ticks(b, 60);
            Assert.That(b.Time, Is.EqualTo(t), "simulation does not advance during the choice");
            Assert.That(b.ChoosePerk(0), Is.True);
            Assert.That(b.Phase, Is.EqualTo(BattlePhase.Running));
        }
    }

    public class BattleFlowTests
    {
        private static Battle Mission(string id, ulong seed, GameContent content = null)
        {
            content = content ?? TestContent.Load();
            var save = SaveManager.NewProfile(new DateTime(2026, 1, 1));
            save.modulesUnlocked.AddRange(new[] { "frost_whisker", "bone_ballista" });
            save.slotsUnlocked = new List<string> { "crown", "middle", "base" };
            save.loadout = new Dictionary<string, string> { ["middle"] = "arc_coil", ["crown"] = "frost_whisker", ["base"] = "ember_maw" };
            var meta = new GameMeta(content, save);
            var setup = meta.CreateCampaignSetup(id, seed, false);
            setup.emitEvents = false;
            return new Battle(content, setup);
        }

        [Test]
        public void SameSeedSameInputsGiveIdenticalRuns()
        {
            var r1 = AutoPilot.Play(Mission("m03", 5), AutoPilot.Build("default", 5));
            var r2 = AutoPilot.Play(Mission("m03", 5), AutoPilot.Build("default", 5));
            Assert.That(r2.score, Is.EqualTo(r1.score));
            Assert.That(r2.stats.kills, Is.EqualTo(r1.stats.kills));
            Assert.That(r2.healthFraction, Is.EqualTo(r1.healthFraction));
        }

        [Test]
        public void SpeedDoesNotChangeOutcomes()
        {
            // 2x speed = two fixed ticks per rendered frame; the result must be bit-identical.
            RunResult Run(int perFrame)
            {
                var b = Mission("m02", 9);
                var pilot = AutoPilot.Build("default", 9);
                while (!b.IsOver && b.TickCount < 30 * 60 * 20)
                    for (int k = 0; k < perFrame && !b.IsOver; k++)
                    {
                        pilot.Step(b);
                        if (b.Phase == BattlePhase.Running) b.Tick();
                        if (b.CheckpointPending) b.TakeCheckpoint();
                    }
                return b.BuildResult();
            }
            var x1 = Run(1);
            var x2 = Run(2);
            Assert.That(x2.score, Is.EqualTo(x1.score));
            Assert.That(x2.stats.kills, Is.EqualTo(x1.stats.kills));
            Assert.That(x2.stats.timeSec, Is.EqualTo(x1.stats.timeSec).Within(1e-3f));
        }

        [Test]
        public void TutorialMissionIsShortAndGrantsSecondSlot()
        {
            var content = TestContent.Load();
            var save = SaveManager.NewProfile(new DateTime(2026, 1, 1));
            var meta = new GameMeta(content, save);
            var setup = meta.CreateCampaignSetup("m01", 3, false);
            setup.emitEvents = true;
            var b = new Battle(content, setup);
            var pilot = AutoPilot.Build("default", 3);
            bool slot = false;
            var ev = new List<SimEvent>();
            while (!b.IsOver && b.TickCount < 30 * 60 * 10)
            {
                pilot.Step(b);
                if (b.Phase == BattlePhase.Running) b.Tick();
                if (b.CheckpointPending) b.TakeCheckpoint();
                b.DrainEvents(ev);
                foreach (var e in ev) if (e.type == SimEventType.SlotUnlocked && e.id == "crown" && e.id2 == "ember_maw") slot = true;
                ev.Clear();
            }
            var r = b.BuildResult();
            Assert.That(slot, Is.True, "second slot unlocked during the tutorial with Ember Maw");
            Assert.That(r.victory, Is.True);
            Assert.That(r.stats.timeSec, Is.InRange(150f, 300f), "introductory mission ~3-4 minutes");
            Assert.That(r.unlockedSlots, Contains.Item("crown"));
        }

        [Test]
        public void WaveAdvancesOnlyWhenEnemiesAreDefeated()
        {
            var b = Mission("m02", 11);
            // no pilot: nobody buys anything, but the hero still fights automatically
            int waveAtStart = 0;
            while (b.Wave == 0) b.Tick();
            waveAtStart = b.Wave;
            // advance until all spawns are out
            while (b.PendingSpawns > 0 && !b.IsOver) b.Tick();
            if (b.AliveCount > 0) Assert.That(b.Wave, Is.EqualTo(waveAtStart), "a wave never ends while enemies remain");
        }

        [Test]
        public void EnemiesNeverSpawnOnTheCitadel()
        {
            var b = Mission("m05", 13);
            var pilot = AutoPilot.Build("default", 13);
            float minSpawnDist = float.MaxValue;
            var seen = new HashSet<int>();
            while (!b.IsOver && b.TickCount < 30 * 60 * 6)
            {
                pilot.Step(b);
                if (b.Phase == BattlePhase.Running) b.Tick();
                foreach (var e in b.Enemies)
                    if (e.alive && seen.Add(e.uid)) minSpawnDist = Math.Min(minSpawnDist, e.pos.Length);
            }
            Assert.That(minSpawnDist, Is.GreaterThan(b.C.Tuning.arena.minSummonDistance - 0.01f));
        }

        [Test]
        public void CheckpointResumeRestoresRunState()
        {
            var b = Mission("m03", 21);
            var pilot = AutoPilot.Build("default", 21);
            RunCheckpoint cp = null;
            while (!b.IsOver && cp == null)
            {
                pilot.Step(b);
                if (b.Phase == BattlePhase.Running) b.Tick();
                if (b.CheckpointPending && b.Wave >= 4) cp = b.TakeCheckpoint();
                else if (b.CheckpointPending) b.TakeCheckpoint();
            }
            Assert.That(cp, Is.Not.Null);
            string json = Json.Serialize(cp);
            var restored = Json.Deserialize<RunCheckpoint>(json);
            var content = TestContent.Load();
            var setup = new BattleSetup { mode = BattleMode.Campaign, missionId = "m03", seed = 21, resume = restored, emitEvents = false };
            var b2 = new Battle(content, setup);
            Assert.That(b2.NextWave, Is.EqualTo(cp.nextWave));
            Assert.That(b2.Hp, Is.EqualTo(cp.citadelHp).Within(0.01f));
            Assert.That(b2.Sparks, Is.EqualTo((int)Math.Floor(cp.sparks + 1e-4f)));
            Assert.That(b2.Level, Is.EqualTo(cp.level));
            Assert.That(b2.RunId, Is.EqualTo(cp.runId));
            foreach (var kv in cp.perks) Assert.That(b2.PerkStack(kv.Key), Is.EqualTo(kv.Value));
            foreach (var kv in cp.upgrades) Assert.That(b2.UpgradeLevel(kv.Key), Is.EqualTo(kv.Value));
            Assert.That(b2.RunStats.kills, Is.EqualTo(cp.stats.kills));
        }

        [Test]
        public void ResumedRunReplaysTheSameWaveComposition()
        {
            var content = TestContent.Load();
            var spec = EncounterSpec.ForMission(content.Mission("m04"));
            var routes = new RouteSet(content.LayoutById[spec.routeLayout]);
            var a = WavePlanner.Plan(content, spec, routes, 7, 1234);
            var c = WavePlanner.Plan(content, spec, routes, 7, 1234);
            Assert.That(c.orders.Count, Is.EqualTo(a.orders.Count));
            for (int i = 0; i < a.orders.Count; i++)
            {
                Assert.That(c.orders[i].enemyId, Is.EqualTo(a.orders[i].enemyId));
                Assert.That(c.orders[i].time, Is.EqualTo(a.orders[i].time));
                Assert.That(c.orders[i].route, Is.EqualTo(a.orders[i].route));
            }
        }

        [Test]
        public void EliteWavesAndBossAreAnnounced()
        {
            var content = TestContent.Load();
            var spec = EncounterSpec.ForMission(content.Mission("m06"));
            var routes = new RouteSet(content.LayoutById[spec.routeLayout]);
            Assert.That(WavePlanner.Plan(content, spec, routes, 5, 1).announce.Exists(a => a.StartsWith("elite:")), Is.True);
            var last = WavePlanner.Plan(content, spec, routes, 20, 1);
            Assert.That(last.bossId, Is.EqualTo("sir_barkhelm"));
            Assert.That(last.announce, Contains.Item("boss:sir_barkhelm"));
        }

        [Test]
        public void ReleaseWindowsStayWithinTheSpec()
        {
            var content = TestContent.Load();
            foreach (var m in content.Missions)
            {
                var spec = EncounterSpec.ForMission(m);
                var routes = new RouteSet(content.LayoutById[spec.routeLayout]);
                for (int w = 1; w <= m.waves; w++)
                {
                    var plan = WavePlanner.Plan(content, spec, routes, w, 99);
                    Assert.That(plan.release, Is.LessThanOrEqualTo(content.Tuning.waves.releaseMax + 1e-3f));
                    Assert.That(plan.orders.Count, Is.GreaterThan(0), m.id + " wave " + w);
                }
            }
        }

        [Test]
        public void EndlessHealthScalingIsBounded()
        {
            var content = TestContent.Load();
            var spec = EncounterSpec.ForEndless(content.Endless);
            float h500 = WavePlanner.HealthMultiplier(content, spec, 500, new List<ModifierDef>());
            float h5000 = WavePlanner.HealthMultiplier(content, spec, 5000, new List<ModifierDef>());
            Assert.That(h500, Is.EqualTo(h5000), "health multiplier is capped: no unbounded growth");
            Assert.That(float.IsFinite(h5000), Is.True);
        }
    }
}
