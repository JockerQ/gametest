using System;
using System.Collections.Generic;
using EvilCats.Content;

namespace EvilCats.Sim
{
    /// <summary>
    /// Collects stat modifiers from every source and resolves final values.
    ///
    /// STACKING RULE (documented in BALANCE.md):
    ///   value    = (base + Σadd) × (1 + Σpct) × Πmul
    ///   interval = base / ((1 + Σrate) × Πratemul) × Πmul
    /// "pct" bonuses from different sources ADD together (e.g. +8% upgrade and +6% permanent
    /// = +14%). "mul" factors (trade-off perks, pacts) MULTIPLY. Derived stats are always
    /// rebuilt from scratch from the source list, never modified incrementally, so bonuses
    /// cannot compound by accident.
    /// </summary>
    public sealed class ModifierSet
    {
        private sealed class Acc
        {
            public float add;
            public float pct;
            public float mul = 1f;
            public float rate;
            public float rateMul = 1f;
        }

        private readonly Dictionary<string, Acc> _acc = new Dictionary<string, Acc>();

        public void Clear() => _acc.Clear();

        public ModifierSet Clone()
        {
            var copy = new ModifierSet();
            foreach (var kv in _acc)
                copy._acc[kv.Key] = new Acc { add = kv.Value.add, pct = kv.Value.pct, mul = kv.Value.mul, rate = kv.Value.rate, rateMul = kv.Value.rateMul };
            return copy;
        }

        public void Apply(StatModDef mod, float times = 1f)
        {
            if (mod == null || string.IsNullOrEmpty(mod.stat) || times == 0f) return;
            Add(mod.stat, mod.op, mod.value, times);
        }

        public void Apply(IEnumerable<StatModDef> mods, float times = 1f)
        {
            if (mods == null) return;
            foreach (var m in mods) Apply(m, times);
        }

        public void Add(string stat, string op, float value, float times = 1f)
        {
            if (!_acc.TryGetValue(stat, out var a))
            {
                a = new Acc();
                _acc[stat] = a;
            }
            switch (op)
            {
                case "add": a.add += value * times; break;
                case "pct": a.pct += value * times; break;
                case "mul": a.mul *= (float)Math.Pow(value, times); break;
                case "rate": a.rate += value * times; break;
                case "ratemul": a.rateMul *= (float)Math.Pow(value, times); break;
                default: throw new ArgumentException($"Unknown stat op '{op}' for {stat}");
            }
        }

        public bool Has(string stat) => _acc.ContainsKey(stat);

        public float Value(string stat, float baseValue)
        {
            if (!_acc.TryGetValue(stat, out var a)) return baseValue;
            return (baseValue + a.add) * (1f + a.pct) * a.mul;
        }

        /// <summary>Multiplier-style stat with an implicit base of 1 (dmg.all, rate.all ...).</summary>
        public float Factor(string stat) => Value(stat, 1f);

        public float Interval(string stat, float baseInterval, float externalRateFactor = 1f)
        {
            float rate = externalRateFactor;
            float mul = 1f;
            float add = 0f;
            if (_acc.TryGetValue(stat, out var a))
            {
                rate *= (1f + a.rate) * a.rateMul;
                mul = a.mul;
                add = a.add;
            }
            rate = Math.Max(0.05f, rate);
            return Math.Max(0.05f, (baseInterval + add) / rate * mul);
        }

        public float RateFactor(string stat)
        {
            if (!_acc.TryGetValue(stat, out var a)) return 1f;
            return (1f + a.rate) * a.rateMul * (1f + a.pct) * a.mul;
        }
    }

    public sealed class HeroStats
    {
        public float damage, interval, range, critChance, critMultiplier, chainRange, chainFalloff;
        public int chainTargets;
    }

    public sealed class CitadelStats
    {
        public float maxHealth, regen, barrierMult, healMult;
    }

    public sealed class AbilityStats
    {
        public float stormCooldown, stormDamageMult, stormRadius, stormStun;
        public int stormTargets;
        public float wardCooldown, wardFraction, wardDuration;
    }

    public sealed class EconStats
    {
        public float sparkGain = 1f, xpGain = 1f, startSparks;
    }

    /// <summary>Final stats of one equipped station module.</summary>
    public sealed class ModuleStats
    {
        public string moduleId;
        public string slotId;
        public ModuleDef def;
        public float damage, interval, range, projectileSpeed, radius, duration;
        public int targets;
        public readonly Dictionary<string, float> p = new Dictionary<string, float>();
        public readonly List<string> activeSynergies = new List<string>();
        public readonly List<string> synergySpecials = new List<string>();
        public readonly Dictionary<string, float> synergyValues = new Dictionary<string, float>();

        public float P(string key, float fallback = 0f) => p.TryGetValue(key, out var v) ? v : fallback;
    }

    public sealed class DerivedStats
    {
        public readonly HeroStats hero = new HeroStats();
        public readonly CitadelStats citadel = new CitadelStats();
        public readonly AbilityStats abilities = new AbilityStats();
        public readonly EconStats econ = new EconStats();
        public readonly List<ModuleStats> modules = new List<ModuleStats>();
        public float dmgAll = 1f, dmgArc = 1f, dmgFire = 1f, dmgFrost = 1f, dmgPhysical = 1f, dmgGravity = 1f;
        public float stationDamage = 1f;

        public float TypeFactor(DamageType t)
        {
            switch (t)
            {
                case DamageType.Arc: return dmgArc;
                case DamageType.Fire: return dmgFire;
                case DamageType.Frost: return dmgFrost;
                case DamageType.Physical: return dmgPhysical;
                case DamageType.Gravity: return dmgGravity;
                default: return 1f;
            }
        }

        public ModuleStats Module(string id)
        {
            for (int i = 0; i < modules.Count; i++) if (modules[i].moduleId == id) return modules[i];
            return null;
        }
    }

    /// <summary>Everything that changes stats, as plain data (so previews and tests can build it).</summary>
    public sealed class StatSources
    {
        public Dictionary<string, string> loadout = new Dictionary<string, string>();   // slotId -> moduleId
        public Dictionary<string, int> upgradeLevels = new Dictionary<string, int>();    // run upgrades
        public Dictionary<string, int> perkStacks = new Dictionary<string, int>();       // run perks
        public Dictionary<string, int> nodeLevels = new Dictionary<string, int>();       // permanent tree
        public Dictionary<string, int> moduleTiers = new Dictionary<string, int>();      // permanent module tiers (1-5)
        public List<string> modifiers = new List<string>();                              // mission modifiers affecting the player
        public bool ignorePermanent;                                                     // daily challenge standardisation
    }

    public static class StatsBuilder
    {
        public static readonly string[] ModuleStatNames = { "damage", "interval", "range", "targets", "projectileSpeed", "radius", "duration" };

        /// <summary>Which pairs of equipped modules currently form an adjacency synergy.</summary>
        public static List<SynergyDef> ActiveSynergies(GameContent c, Dictionary<string, string> loadout)
        {
            var result = new List<SynergyDef>();
            foreach (var syn in c.Synergies)
            {
                string slotA = SlotOf(loadout, syn.a);
                string slotB = SlotOf(loadout, syn.b);
                if (slotA == null || slotB == null) continue;
                if (AreAdjacent(c, slotA, slotB)) result.Add(syn);
            }
            return result;
        }

        public static string SlotOf(Dictionary<string, string> loadout, string moduleId)
        {
            foreach (var kv in loadout) if (kv.Value == moduleId) return kv.Key;
            return null;
        }

        public static bool AreAdjacent(GameContent c, string slotA, string slotB)
        {
            if (slotA == slotB) return false;
            return c.SlotById.TryGetValue(slotA, out var a) && a.adjacent != null && a.adjacent.Contains(slotB);
        }

        public static DerivedStats Build(GameContent c, StatSources src)
        {
            var mods = new ModifierSet();
            var t = c.Tuning;

            // 1) run upgrades
            foreach (var kv in src.upgradeLevels)
                if (kv.Value > 0 && c.UpgradeById.TryGetValue(kv.Key, out var up))
                    mods.Apply(up.mods, kv.Value);
            // 2) perks
            foreach (var kv in src.perkStacks)
                if (kv.Value > 0 && c.PerkById.TryGetValue(kv.Key, out var perk))
                    mods.Apply(perk.mods, kv.Value);
            // 3) permanent tree
            if (!src.ignorePermanent)
                foreach (var kv in src.nodeLevels)
                    if (kv.Value > 0 && c.NodeById.TryGetValue(kv.Key, out var node))
                        mods.Apply(node.mods, Math.Min(kv.Value, node.maxLevel));
            // 4) synergies (static parts). "pct" synergy bonuses scale with synergy.all (permanent tree).
            var synergies = ActiveSynergies(c, src.loadout);
            float synergyFactor = mods.Factor("synergy.all");
            foreach (var syn in synergies)
                foreach (var sm in syn.mods)
                    mods.Add(sm.stat, sm.op, sm.op == "pct" ? sm.value * synergyFactor : sm.value);

            var d = new DerivedStats();
            d.dmgAll = mods.Factor("dmg.all");
            d.dmgArc = mods.Factor("dmg.arc");
            d.dmgFire = mods.Factor("dmg.fire");
            d.dmgFrost = mods.Factor("dmg.frost");
            d.dmgPhysical = mods.Factor("dmg.physical");
            d.dmgGravity = mods.Factor("dmg.gravity");
            d.stationDamage = mods.Factor("station.damage");
            float rateAll = mods.RateFactor("rate.all");
            float rateStations = mods.RateFactor("rate.stations");

            var h = d.hero;
            h.damage = mods.Value("hero.damage", t.hero.damage) * d.dmgAll * d.dmgArc;
            h.interval = mods.Interval("hero.interval", t.hero.interval, rateAll);
            h.range = mods.Value("hero.range", t.hero.range);
            h.critChance = Math.Min(t.hero.critChanceCap, mods.Value("hero.critChance", t.hero.critChance));
            h.critMultiplier = mods.Value("hero.critMultiplier", t.hero.critMultiplier);
            h.chainTargets = (int)Math.Round(mods.Value("hero.chainTargets", t.hero.chainTargets));
            h.chainRange = mods.Value("hero.chainRange", t.hero.chainRange);
            h.chainFalloff = MathXClamp(mods.Value("hero.chainFalloff", t.hero.chainFalloff), 0.1f, 1f);

            var cs = d.citadel;
            cs.maxHealth = Math.Max(1f, mods.Value("citadel.maxHealth", t.hero.maxHealth));
            cs.healMult = mods.Factor("heal.all");
            cs.regen = mods.Value("citadel.regen", t.hero.regen) * cs.healMult;
            cs.barrierMult = mods.Factor("barrier.all");

            var ab = d.abilities;
            ab.stormCooldown = Math.Max(5f, mods.Value("arcStorm.cooldown", t.arcStorm.cooldown));
            ab.stormDamageMult = mods.Value("arcStorm.damageMultiplier", t.arcStorm.damageMultiplier);
            ab.stormTargets = (int)Math.Round(mods.Value("arcStorm.targets", t.arcStorm.maxTargets));
            ab.stormRadius = mods.Value("arcStorm.radius", t.arcStorm.radius);
            ab.stormStun = mods.Value("arcStorm.stun", t.arcStorm.stun);
            ab.wardCooldown = Math.Max(5f, mods.Value("ward.cooldown", t.ward.cooldown));
            ab.wardFraction = mods.Value("ward.barrierFraction", t.ward.barrierFraction);
            ab.wardDuration = mods.Value("ward.duration", t.ward.duration);

            d.econ.sparkGain = mods.Factor("econ.sparkGain");
            d.econ.xpGain = mods.Factor("econ.xpGain");
            d.econ.startSparks = mods.Value("econ.startSparks", 0f);

            // 5) modules (slot modifier + tier + all of the above)
            foreach (var slot in t.slots)
            {
                if (!src.loadout.TryGetValue(slot.id, out var moduleId) || string.IsNullOrEmpty(moduleId)) continue;
                if (!c.ModuleById.TryGetValue(moduleId, out var def)) continue;
                d.modules.Add(BuildModule(c, def, slot, src, mods, d, rateAll * rateStations, synergies));
            }
            return d;
        }

        private static ModuleStats BuildModule(GameContent c, ModuleDef def, SlotDef slot, StatSources src,
            ModifierSet shared, DerivedStats d, float rateFactor, List<SynergyDef> synergies)
        {
            // Module-local set = every shared source + this module's slot and tier bonuses,
            // resolved with the same stacking rule as everything else.
            var local = shared.Clone();
            string prefix = "module." + def.id + ".";
            List<string> powerStats = null;
            if (def.slotStats != null) def.slotStats.TryGetValue("power", out powerStats);

            // Slot modifier: Crown +range/aura, Middle +power (damage/heal/barrier), Base +rate.
            if (slot != null && def.slotStats != null && def.slotStats.TryGetValue(slot.modifier, out var stats))
                foreach (var s in stats)
                    local.Add(prefix + s, slot.modifier == "rate" ? "rate" : "pct", slot.value);

            // Permanent module tier (tier 1 = base, tiers 2..5 add bonuses cumulatively).
            int tier = 1;
            if (!src.ignorePermanent && src.moduleTiers != null && src.moduleTiers.TryGetValue(def.id, out var tv)) tier = Math.Max(1, tv);
            foreach (var td in def.tiers)
            {
                if (td.tier > tier) continue;
                if (td.damagePct != 0f && powerStats != null)
                    foreach (var s in powerStats) local.Add(prefix + s, "pct", td.damagePct);
                if (td.ratePct != 0f) local.Add(prefix + "interval", "rate", td.ratePct);
                local.Apply(td.mods);
            }

            var m = new ModuleStats { moduleId = def.id, slotId = slot?.id, def = def };
            m.damage = local.Value(prefix + "damage", def.damage) * d.dmgAll * d.TypeFactor(def.damageType) * d.stationDamage;
            m.interval = local.Interval(prefix + "interval", def.interval, rateFactor);
            m.range = local.Value(prefix + "range", def.range);
            m.targets = Math.Max(1, (int)Math.Round(local.Value(prefix + "targets", def.targets)));
            m.projectileSpeed = local.Value(prefix + "projectileSpeed", def.projectileSpeed);
            m.radius = local.Value(prefix + "radius", def.radius);
            m.duration = local.Value(prefix + "duration", def.duration);
            foreach (var kv in def.p) m.p[kv.Key] = local.Value(prefix + kv.Key, kv.Value);

            foreach (var syn in synergies)
            {
                if (syn.a != def.id && syn.b != def.id) continue;
                m.activeSynergies.Add(syn.id);
                if (!string.IsNullOrEmpty(syn.special) && (string.IsNullOrEmpty(syn.beneficiary) || syn.beneficiary == def.id))
                {
                    m.synergySpecials.Add(syn.special);
                    m.synergyValues[syn.special] = syn.value * shared.Factor("synergy.all");
                }
            }
            return m;
        }

        private static float MathXClamp(float v, float min, float max) => v < min ? min : (v > max ? max : v);
    }
}
