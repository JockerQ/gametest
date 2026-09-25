using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Converters;
using Newtonsoft.Json.Serialization;

namespace EvilCats.Content
{
    /// <summary>Supplies the raw JSON text of a content file ("modules" -> modules.json).</summary>
    public interface IContentSource
    {
        /// <returns>The file text, or null when the file does not exist.</returns>
        string Read(string name);
    }

    public static class Json
    {
        /// <summary>Shared serializer settings: enums as camelCase strings, strict members.</summary>
        public static JsonSerializerSettings Settings(bool strict, List<string> errors = null)
        {
            var s = new JsonSerializerSettings
            {
                MissingMemberHandling = strict ? MissingMemberHandling.Error : MissingMemberHandling.Ignore,
                NullValueHandling = NullValueHandling.Include,
                ObjectCreationHandling = ObjectCreationHandling.Replace,
                Culture = CultureInfo.InvariantCulture,
                FloatParseHandling = FloatParseHandling.Double,
                Formatting = Formatting.None,
            };
            s.Converters.Add(new StringEnumConverter(new CamelCaseNamingStrategy()));
            if (errors != null)
            {
                s.Error = (sender, args) =>
                {
                    errors.Add(args.ErrorContext.Path + ": " + args.ErrorContext.Error.Message);
                    args.ErrorContext.Handled = true;
                };
            }
            return s;
        }

        public static T Parse<T>(string text, bool strict, List<string> errors, string fileName) where T : class, new()
        {
            if (string.IsNullOrEmpty(text))
            {
                errors?.Add(fileName + ": missing or empty");
                return new T();
            }
            var local = new List<string>();
            T result;
            try
            {
                result = JsonConvert.DeserializeObject<T>(text, Settings(strict, local)) ?? new T();
            }
            catch (Exception e)
            {
                errors?.Add(fileName + ": " + e.Message);
                return new T();
            }
            if (errors != null)
                foreach (var e in local) errors.Add(fileName + ": " + e);
            return result;
        }

        public static string Serialize(object o, bool indented = false)
        {
            var s = Settings(false);
            s.Formatting = indented ? Formatting.Indented : Formatting.None;
            return JsonConvert.SerializeObject(o, s);
        }

        public static T Deserialize<T>(string text) => JsonConvert.DeserializeObject<T>(text, Settings(false));
    }

    /// <summary>Flat key -> text table with {named} placeholders. English is the initial language.</summary>
    public sealed class StringTable
    {
        private readonly Dictionary<string, string> _map;
        public string Language { get; }

        public StringTable(Dictionary<string, string> map, string language = "en")
        {
            _map = map ?? new Dictionary<string, string>();
            Language = language;
        }

        public bool Has(string key) => key != null && _map.ContainsKey(key);
        public IEnumerable<string> Keys => _map.Keys;

        /// <summary>Returns the text, or "[key]" when missing (visible, never crashes).</summary>
        public string Get(string key)
        {
            if (key != null && _map.TryGetValue(key, out var v)) return v;
            return "[" + key + "]";
        }

        public string Format(string key, IDictionary<string, string> args) => Fill(Get(key), args);

        public static string Fill(string template, IDictionary<string, string> args)
        {
            if (args == null || args.Count == 0 || template.IndexOf('{') < 0) return template;
            var sb = new StringBuilder(template.Length + 16);
            int i = 0;
            while (i < template.Length)
            {
                char c = template[i];
                if (c == '{')
                {
                    int end = template.IndexOf('}', i + 1);
                    if (end > i)
                    {
                        string name = template.Substring(i + 1, end - i - 1);
                        if (args.TryGetValue(name, out var val))
                        {
                            sb.Append(val);
                            i = end + 1;
                            continue;
                        }
                    }
                }
                sb.Append(c);
                i++;
            }
            return sb.ToString();
        }
    }

    /// <summary>All game content, loaded once at boot and treated as read-only afterwards.</summary>
    public sealed class GameContent
    {
        public static readonly string[] FileNames =
        {
            "game", "modules", "enemies", "bosses", "perks", "upgrades", "progression", "routes", "missions", "strings_en"
        };

        public GameTuning Tuning = new GameTuning();
        public List<ModuleDef> Modules = new List<ModuleDef>();
        public List<SynergyDef> Synergies = new List<SynergyDef>();
        public List<EnemyDef> Enemies = new List<EnemyDef>();
        public List<BossDef> Bosses = new List<BossDef>();
        public List<PerkDef> Perks = new List<PerkDef>();
        public List<FallbackRewardDef> Fallbacks = new List<FallbackRewardDef>();
        public List<RunUpgradeDef> Upgrades = new List<RunUpgradeDef>();
        public ProgressionFile Progression = new ProgressionFile();
        public List<RouteLayoutDef> RouteLayouts = new List<RouteLayoutDef>();
        public List<MissionDef> Missions = new List<MissionDef>();
        public List<ModifierDef> Modifiers = new List<ModifierDef>();
        public EndlessDef Endless = new EndlessDef();
        public DailyChallengeDef Daily = new DailyChallengeDef();
        public StringTable Strings = new StringTable(new Dictionary<string, string>());

        public readonly Dictionary<string, ModuleDef> ModuleById = new Dictionary<string, ModuleDef>();
        public readonly Dictionary<string, EnemyDef> EnemyById = new Dictionary<string, EnemyDef>();
        public readonly Dictionary<string, BossDef> BossById = new Dictionary<string, BossDef>();
        public readonly Dictionary<string, PerkDef> PerkById = new Dictionary<string, PerkDef>();
        public readonly Dictionary<string, RunUpgradeDef> UpgradeById = new Dictionary<string, RunUpgradeDef>();
        public readonly Dictionary<string, PermanentNodeDef> NodeById = new Dictionary<string, PermanentNodeDef>();
        public readonly Dictionary<string, CosmeticDef> CosmeticById = new Dictionary<string, CosmeticDef>();
        public readonly Dictionary<string, AchievementDef> AchievementById = new Dictionary<string, AchievementDef>();
        public readonly Dictionary<string, DailyObjectiveDef> ObjectiveById = new Dictionary<string, DailyObjectiveDef>();
        public readonly Dictionary<string, RouteLayoutDef> LayoutById = new Dictionary<string, RouteLayoutDef>();
        public readonly Dictionary<string, MissionDef> MissionById = new Dictionary<string, MissionDef>();
        public readonly Dictionary<string, ModifierDef> ModifierById = new Dictionary<string, ModifierDef>();
        public readonly Dictionary<string, SlotDef> SlotById = new Dictionary<string, SlotDef>();

        /// <summary>Problems found while parsing (unknown fields, bad values, duplicates).</summary>
        public readonly List<string> LoadErrors = new List<string>();

        public static GameContent Load(IContentSource source, bool strict = true)
        {
            var c = new GameContent();
            var e = c.LoadErrors;
            c.Tuning = Json.Parse<GameTuning>(source.Read("game"), strict, e, "game.json");
            var modules = Json.Parse<ModulesFile>(source.Read("modules"), strict, e, "modules.json");
            c.Modules = modules.modules;
            c.Synergies = modules.synergies;
            c.Enemies = Json.Parse<EnemiesFile>(source.Read("enemies"), strict, e, "enemies.json").enemies;
            c.Bosses = Json.Parse<BossesFile>(source.Read("bosses"), strict, e, "bosses.json").bosses;
            var perks = Json.Parse<PerksFile>(source.Read("perks"), strict, e, "perks.json");
            c.Perks = perks.perks;
            c.Fallbacks = perks.fallbacks;
            c.Upgrades = Json.Parse<UpgradesFile>(source.Read("upgrades"), strict, e, "upgrades.json").upgrades;
            c.Progression = Json.Parse<ProgressionFile>(source.Read("progression"), strict, e, "progression.json");
            c.RouteLayouts = Json.Parse<RoutesFile>(source.Read("routes"), strict, e, "routes.json").layouts;
            var missions = Json.Parse<MissionsFile>(source.Read("missions"), strict, e, "missions.json");
            c.Missions = missions.missions;
            c.Modifiers = missions.modifiers;
            c.Endless = missions.endless ?? new EndlessDef();
            c.Daily = missions.daily ?? new DailyChallengeDef();

            string stringsText = source.Read("strings_en");
            Dictionary<string, string> map = null;
            if (string.IsNullOrEmpty(stringsText)) e.Add("strings_en.json: missing or empty");
            else
            {
                try { map = JsonConvert.DeserializeObject<Dictionary<string, string>>(stringsText); }
                catch (Exception ex) { e.Add("strings_en.json: " + ex.Message); }
            }
            c.Strings = new StringTable(map ?? new Dictionary<string, string>(), "en");
            c.BuildIndexes();
            return c;
        }

        public void BuildIndexes()
        {
            Index(Modules, m => m.id, ModuleById, "module");
            Index(Enemies, x => x.id, EnemyById, "enemy");
            Index(Bosses, x => x.id, BossById, "boss");
            Index(Perks, x => x.id, PerkById, "perk");
            Index(Upgrades, x => x.id, UpgradeById, "upgrade");
            Index(Progression.nodes, x => x.id, NodeById, "permanent node");
            Index(Progression.cosmetics, x => x.id, CosmeticById, "cosmetic");
            Index(Progression.achievements, x => x.id, AchievementById, "achievement");
            Index(Progression.dailyObjectives, x => x.id, ObjectiveById, "daily objective");
            Index(RouteLayouts, x => x.id, LayoutById, "route layout");
            Index(Missions, x => x.id, MissionById, "mission");
            Index(Modifiers, x => x.id, ModifierById, "modifier");
            Index(Tuning.slots, x => x.id, SlotById, "slot");
            Modules.Sort((a, b) => a.order.CompareTo(b.order));
            Missions.Sort((a, b) => a.index.CompareTo(b.index));
            Upgrades.Sort((a, b) => a.order.CompareTo(b.order));
            Tuning.slots.Sort((a, b) => a.order.CompareTo(b.order));
        }

        private void Index<T>(List<T> list, Func<T, string> key, Dictionary<string, T> dict, string kind)
        {
            dict.Clear();
            if (list == null) return;
            foreach (var item in list)
            {
                string k = key(item);
                if (string.IsNullOrEmpty(k))
                {
                    LoadErrors.Add($"{kind} with empty id");
                    continue;
                }
                if (dict.ContainsKey(k))
                {
                    LoadErrors.Add($"duplicate {kind} id '{k}'");
                    continue;
                }
                dict[k] = item;
            }
        }

        // ---- convenience lookups --------------------------------------------------------
        public MissionDef Mission(string id) => id != null && MissionById.TryGetValue(id, out var m) ? m : null;
        public ModuleDef Module(string id) => id != null && ModuleById.TryGetValue(id, out var m) ? m : null;
        public EnemyDef Enemy(string id) => id != null && EnemyById.TryGetValue(id, out var m) ? m : null;
        public BossDef Boss(string id) => id != null && BossById.TryGetValue(id, out var m) ? m : null;
        public PerkDef Perk(string id) => id != null && PerkById.TryGetValue(id, out var m) ? m : null;

        public MissionDef NextMission(MissionDef m)
        {
            if (m == null) return null;
            foreach (var x in Missions) if (x.index == m.index + 1) return x;
            return null;
        }

        /// <summary>Text for UI, falling back to the id so missing strings are visible but harmless.</summary>
        public string T(string key) => Strings.Get(key);
    }
}
