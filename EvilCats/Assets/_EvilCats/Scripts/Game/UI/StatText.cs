using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Sim;

namespace EvilCats.Game
{
    /// <summary>Player-facing stat lines computed from the same StatsBuilder the simulation uses.</summary>
    public static class StatText
    {
        private static readonly Dictionary<string, string[]> Shown = new Dictionary<string, string[]>
        {
            { "chain", new[] { "damage", "interval", "range", "targets", "chainRange" } },
            { "shell", new[] { "damage", "interval", "range", "radius", "burnDps", "burnDuration" } },
            { "frost_pulse", new[] { "damage", "interval", "range", "radius", "slow", "freezeDuration" } },
            { "piercing", new[] { "damage", "interval", "range", "targets", "armorPen" } },
            { "ward", new[] { "interval", "barrierFraction", "barrierDuration", "repair", "auraRadius", "auraReduction" } },
            { "gravity", new[] { "damage", "interval", "range", "radius", "duration", "anchoredDamageMult" } },
        };

        private static readonly HashSet<string> Percent = new HashSet<string> { "slow", "armorPen", "barrierFraction", "auraReduction", "splash", "falloff" };

        public static List<(string key, string label, string value)> Module(ModuleStats m)
        {
            var result = new List<(string, string, string)>();
            if (m == null || m.def == null) return result;
            if (!Shown.TryGetValue(m.def.behavior ?? "", out var keys)) keys = new[] { "damage", "interval", "range" };
            foreach (var k in keys) result.Add((k, L.T("stat." + k), Value(m, k)));
            return result;
        }

        public static string Value(ModuleStats m, string key)
        {
            float v;
            switch (key)
            {
                case "damage": v = m.damage; break;
                case "interval": return TextFormat.Number(Round(m.interval, 100f)) + "s";
                case "range": v = m.range; break;
                case "targets": return m.targets.ToString();
                case "radius": v = m.radius; break;
                case "duration": return TextFormat.Number(Round(m.duration, 10f)) + "s";
                case "projectileSpeed": v = m.projectileSpeed; break;
                default: v = m.P(key); break;
            }
            if (Percent.Contains(key)) return TextFormat.Percent(v);
            if (key == "anchoredDamageMult") return "x" + TextFormat.Number(Round(v, 10f));
            if (key.EndsWith("Duration")) return TextFormat.Number(Round(v, 10f)) + "s";
            return TextFormat.Number(Round(v, 10f));
        }

        private static float Round(float v, float step) => (float)System.Math.Round(v * step) / step;

        /// <summary>Stats of `moduleId` if it were placed in `slot` with the rest of `loadout` unchanged.</summary>
        public static ModuleStats Preview(GameContent c, Dictionary<string, string> loadout, string slot, string moduleId,
            IReadOnlyDictionary<string, int> upgrades, IReadOnlyDictionary<string, int> perks,
            Dictionary<string, int> nodes, Dictionary<string, int> tiers, bool ignorePermanent)
        {
            var d = BuildWith(c, loadout, slot, moduleId, upgrades, perks, nodes, tiers, ignorePermanent);
            return d.Module(moduleId);
        }

        public static DerivedStats BuildWith(GameContent c, Dictionary<string, string> loadout, string slot, string moduleId,
            IReadOnlyDictionary<string, int> upgrades, IReadOnlyDictionary<string, int> perks,
            Dictionary<string, int> nodes, Dictionary<string, int> tiers, bool ignorePermanent)
        {
            var lo = new Dictionary<string, string>();
            foreach (var kv in loadout) if (kv.Value != moduleId) lo[kv.Key] = kv.Value;
            if (!string.IsNullOrEmpty(slot)) lo[slot] = moduleId;
            var up = new Dictionary<string, int>();
            if (upgrades != null) foreach (var kv in upgrades) up[kv.Key] = kv.Value;
            var pk = new Dictionary<string, int>();
            if (perks != null) foreach (var kv in perks) pk[kv.Key] = kv.Value;
            return StatsBuilder.Build(c, new StatSources
            {
                loadout = lo,
                upgradeLevels = up,
                perkStacks = pk,
                nodeLevels = nodes ?? new Dictionary<string, int>(),
                moduleTiers = tiers ?? new Dictionary<string, int>(),
                ignorePermanent = ignorePermanent,
            });
        }

        /// <summary>Synergies that placing moduleId in slot would newly create.</summary>
        public static List<SynergyDef> NewSynergies(GameContent c, Dictionary<string, string> loadout, string slot, string moduleId)
        {
            var before = StatsBuilder.ActiveSynergies(c, new Dictionary<string, string>(loadout));
            var lo = new Dictionary<string, string>();
            foreach (var kv in loadout) if (kv.Value != moduleId) lo[kv.Key] = kv.Value;
            lo[slot] = moduleId;
            var after = StatsBuilder.ActiveSynergies(c, lo);
            after.RemoveAll(s => before.Contains(s));
            return after;
        }

        /// <summary>Display name for a damage source id (enemy, boss, boss ability).</summary>
        public static string SourceName(GameContent c, string id)
        {
            if (string.IsNullOrEmpty(id)) return "?";
            if (L.Has("source." + id)) return L.T("source." + id);
            if (c.Enemy(id) != null) return L.T("enemy." + (id == "bat" ? "bat_swarm" : id) + ".name");
            if (c.Boss(id) != null) return L.T("boss." + id + ".name");
            return id;
        }

        /// <summary>String key of the counter tip for the enemy/attack that did the most damage.</summary>
        public static string TipKey(GameContent c, string source)
        {
            if (!string.IsNullOrEmpty(source))
                foreach (var t in c.Tuning.defeatTips)
                    if (t.source == source && L.Has(t.tipKey)) return t.tipKey;
            return "tip.default";
        }
    }
}
