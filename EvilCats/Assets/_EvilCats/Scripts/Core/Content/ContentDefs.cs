using System;
using System.Collections.Generic;

// Data classes mapped 1:1 from the JSON files in Data/Resources/ECData.
// Field names are the JSON keys. Keep them stable: save files and content refer to
// stable string ids ("arc_coil", "m03", "arc_forked_bolt"), never to display names.
namespace EvilCats.Content
{
    public enum DamageType { Arc, Fire, Frost, Physical, Gravity, True }

    public enum TargetPriority { Nearest, Strongest, RangedThreat }

    public enum EnemyRole { Melee, Fast, Armored, Ranged, Flyer, Support, Suicide, Siege, Boss }

    public enum BattleMode { Campaign, Daily, Endless }

    // ----------------------------------------------------------------------------------
    // game.json
    // ----------------------------------------------------------------------------------
    [Serializable]
    public sealed class GameTuning
    {
        public float tickRate = 30f;
        public ArenaTuning arena = new ArenaTuning();
        public HeroTuning hero = new HeroTuning();
        public ArcStormTuning arcStorm = new ArcStormTuning();
        public WardTuning ward = new WardTuning();
        public XpTuning xp = new XpTuning();
        public ControlTuning control = new ControlTuning();
        public WaveTuning waves = new WaveTuning();
        public EliteTuning elite = new EliteTuning();
        public EconomyTuning economy = new EconomyTuning();
        public PerkOfferTuning perkOffer = new PerkOfferTuning();
        public List<SlotDef> slots = new List<SlotDef>();
        public OfflineTuning offline = new OfflineTuning();
        public List<DamageTipDef> defeatTips = new List<DamageTipDef>();
    }

    [Serializable]
    public sealed class ArenaTuning
    {
        public float width = 16f;
        public float height = 20f;
        public float citadelRadius = 2.2f;
        public float meleeRing = 2.65f;
        public int ringSlots = 24;
        public float outerRingStep = 0.55f;
        public float approachRadius = 4.2f;
        public float minSummonDistance = 3.4f;
        public float spawnInset = 0.4f;
        public int maxAlive = 140;
        public float stuckSeconds = 6f;
    }

    [Serializable]
    public sealed class HeroTuning
    {
        public float maxHealth = 1000f;
        public float regen = 0f;
        public float damage = 12f;
        public float interval = 1.0f;
        public float range = 7.0f;
        public float critChance = 0.05f;
        public float critMultiplier = 1.5f;
        public int chainTargets = 0;
        public float chainRange = 2.4f;
        public float chainFalloff = 0.75f;
        public float critChanceCap = 0.6f;
    }

    [Serializable]
    public sealed class ArcStormTuning
    {
        public float cooldown = 25f;
        public float damageMultiplier = 3f;
        public int maxTargets = 5;
        public float radius = 2.5f;
        public float stun = 1.5f;
        public float strikeDelay = 0.35f;
    }

    [Serializable]
    public sealed class WardTuning
    {
        public float cooldown = 35f;
        public float barrierFraction = 0.2f;
        public float duration = 5f;
    }

    [Serializable]
    public sealed class XpTuning
    {
        // next level requirement = a + b*L + c*L^2 where L is the current run level (starts at 0)
        public float a = 30f;
        public float b = 20f;
        public float c = 5f;
    }

    [Serializable]
    public sealed class ControlTuning
    {
        public float slowCap = 0.6f;
        public float bossSlowCap = 0.15f;
        public float eliteSlowCap = 0.4f;
        public float fatiguePerControl = 0.35f;
        public float fatigueMax = 0.7f;
        public float fatigueDecayPerSec = 0.1f;
        public float bossControlMultiplier = 0.3f;
        public float eliteControlMultiplier = 0.6f;
        public float freezeImmunity = 3f;
        public float barrierCapFraction = 0.6f;
        public float bellHealBossFraction = 0.01f;
    }

    [Serializable]
    public sealed class WaveTuning
    {
        public float firstWaveDelay = 2.0f;
        public float releaseMin = 18f;
        public float releaseMax = 25f;
        public float intermission = 3.0f;
        public float groupSpacing = 0.55f;
        public float stallSeconds = 75f;
        public float hardStallSeconds = 180f;
        public float hpGrowthPerWave = 0.035f;
        public float dmgGrowthPerWave = 0.02f;
    }

    [Serializable]
    public sealed class EliteTuning
    {
        public float healthMult = 3.0f;
        public float damageMult = 1.4f;
        public float rewardMult = 3.0f;
        public float controlResistAdd = 0.35f;
        public float scale = 1.25f;
    }

    [Serializable]
    public sealed class EconomyTuning
    {
        public float upgradeCostGrowth = 1.16f;
        public float waveClearSparksBase = 10f;
        public float waveClearSparksPerWave = 2f;
        public float defeatMoonGoldFraction = 0.4f;
        public float replayMoonGoldFraction = 0.6f;
        public int reviveHealthPercent = 40;
    }

    [Serializable]
    public sealed class PerkOfferTuning
    {
        public int choices = 3;
        public float commonWeight = 60f;
        public float rareWeight = 30f;
        public float epicWeight = 10f;
    }

    [Serializable]
    public sealed class SlotDef
    {
        public string id;           // crown | middle | base
        public string modifier;     // range | power | rate
        public float value;         // e.g. 0.15 = +15%
        public float x;             // projectile origin offset (world units)
        public float y;
        public List<string> adjacent = new List<string>();
        public int order;
    }

    [Serializable]
    public sealed class OfflineTuning
    {
        public float baseRatePerHour = 4f;
        public float ratePerMissionCleared = 2f;
        public float capHours = 8f;
        public float minCollectMinutes = 5f;
    }

    [Serializable]
    public sealed class DamageTipDef
    {
        public string source;   // enemy id, boss ability id, or "melee"/"ranged"
        public string tipKey;   // string table key explaining the counter
    }

    // ----------------------------------------------------------------------------------
    // modules.json
    // ----------------------------------------------------------------------------------
    [Serializable]
    public sealed class ModulesFile
    {
        public List<ModuleDef> modules = new List<ModuleDef>();
        public List<SynergyDef> synergies = new List<SynergyDef>();
    }

    [Serializable]
    public sealed class ModuleDef
    {
        public string id;
        public string family;          // arc | ember | frost | bone | ward | gravity
        public string behavior;        // chain | shell | frost_pulse | piercing | ward | gravity
        public DamageType damageType = DamageType.Arc;
        public float damage;
        public float interval = 1f;
        public float range = 6f;
        public int targets = 1;
        public float projectileSpeed;
        public float radius;
        public float duration;
        public Dictionary<string, float> p = new Dictionary<string, float>();
        // which stats each slot modifier improves ("range" -> ["range"] etc.)
        public Dictionary<string, List<string>> slotStats = new Dictionary<string, List<string>>();
        public List<ModuleTierDef> tiers = new List<ModuleTierDef>();
        public string unlockMission;   // mission id that must be cleared (null = starter)
        public int unlockShards;
        public bool starter;
        public int order;
    }

    [Serializable]
    public sealed class ModuleTierDef
    {
        public int tier;                 // 2..5 (tier 1 is the base)
        public int moonGold;
        public float damagePct;          // additive % for this module's power stats
        public float ratePct;            // additive % attack/activation rate
        public List<StatModDef> mods = new List<StatModDef>();
    }

    [Serializable]
    public sealed class SynergyDef
    {
        public string id;
        public string a;                 // module id
        public string b;                 // module id
        public List<StatModDef> mods = new List<StatModDef>();
        public string special;           // behaviour flag interpreted by the simulation
        public float value;
        public string beneficiary;       // module that receives the special effect (null = both)
    }

    // ----------------------------------------------------------------------------------
    // enemies.json / bosses.json
    // ----------------------------------------------------------------------------------
    [Serializable]
    public sealed class EnemiesFile
    {
        public List<EnemyDef> enemies = new List<EnemyDef>();
    }

    [Serializable]
    public sealed class EnemyDef
    {
        public string id;
        public EnemyRole role = EnemyRole.Melee;
        public float health = 30f;
        public float speed = 1f;
        public float radius = 0.35f;
        public float damage = 5f;
        public float attackInterval = 1f;
        public float attackRange;           // ranged: firing distance from the citadel centre
        public float projectileSpeed = 9f;
        public float armor;                 // % physical reduction (0-90)
        public float resist;                // % reduction of elemental damage (0-90)
        public bool flying;
        public bool displacementImmune;
        public float controlResist;         // 0..1 extra reduction of stun/freeze duration
        public int xp = 2;
        public int sparks = 3;
        public float cost = 1f;             // encounter budget points (for the whole group entry)
        public int groupMin = 1;
        public int groupMax = 3;
        public int swarmCount = 1;          // units spawned per entry (bats)
        public string unitId;               // unit spawned per swarm member (defaults to id)
        public string routeTag = "any";     // any | flank
        public Dictionary<string, float> p = new Dictionary<string, float>();
        public bool isUnitOnly;             // not spawnable by budget directly (e.g. single bat)
    }

    [Serializable]
    public sealed class BossesFile
    {
        public List<BossDef> bosses = new List<BossDef>();
    }

    [Serializable]
    public sealed class BossDef
    {
        public string id;
        public float health = 2000f;
        public float speed = 0.8f;
        public float radius = 0.8f;
        public float damage = 20f;
        public float attackInterval = 1.6f;
        public float armor;
        public float resist;
        public bool flying;
        public float stopDistance = 2.9f;
        public float controlResist = 0.7f;
        public int xp = 150;
        public int sparks = 150;
        public List<BossPhaseDef> phases = new List<BossPhaseDef>();
        public List<BossAbilityDef> abilities = new List<BossAbilityDef>();
    }

    [Serializable]
    public sealed class BossPhaseDef
    {
        public int phase;                 // 1-based
        public float healthBelow = 1f;    // phase starts when hp fraction <= this
        public float cooldownMult = 1f;
        public float attackSpeedMult = 1f;
    }

    [Serializable]
    public sealed class BossAbilityDef
    {
        public string id;                 // stable id, also used for defeat tips
        public string type;               // shield_stance | charge | summon | sector_barrage | decree | volley | bell_heal
        public float firstDelay = 8f;
        public float cooldown = 15f;
        public float windup = 1f;
        public float duration;
        public int minPhase = 1;
        public int maxPhase = 99;
        public Dictionary<string, float> p = new Dictionary<string, float>();
        public List<SummonDef> summons = new List<SummonDef>();
    }

    [Serializable]
    public sealed class SummonDef
    {
        public string enemy;
        public int count = 1;
        public bool elite;
        public string at = "boss";        // boss | edge
    }

    // ----------------------------------------------------------------------------------
    // perks.json
    // ----------------------------------------------------------------------------------
    [Serializable]
    public sealed class PerksFile
    {
        public List<PerkDef> perks = new List<PerkDef>();
        public List<FallbackRewardDef> fallbacks = new List<FallbackRewardDef>();
    }

    [Serializable]
    public sealed class PerkDef
    {
        public string id;
        public string family;              // arc | ember | frost | bone | ward | gravity
        public string rarity = "common";   // common | rare | epic
        public int maxStacks = 1;
        public bool tradeoff;
        public List<string> requiresModules = new List<string>();   // all must be equipped
        public List<string> requiresAnyModule = new List<string>(); // at least one equipped
        public List<string> requiresAnyPerk = new List<string>();   // at least one taken
        public string requiresCondition;   // e.g. "chain" (any Arc chain source), "slow" (any slow source)
        public List<StatModDef> mods = new List<StatModDef>();      // applied per stack
        public Dictionary<string, float> p = new Dictionary<string, float>();
        public int order;
    }

    [Serializable]
    public sealed class FallbackRewardDef
    {
        public string id;                  // spark_cache | stormheart_mend
        public string kind;                // sparks | heal
        public float value;
    }

    [Serializable]
    public sealed class StatModDef
    {
        public string stat;                // e.g. "hero.damage", "module.ember_maw.radius", "dmg.all"
        public string op = "pct";          // add | pct | mul | rate
        public float value;
    }

    // ----------------------------------------------------------------------------------
    // upgrades.json (run upgrades bought with Spark Coins)
    // ----------------------------------------------------------------------------------
    [Serializable]
    public sealed class UpgradesFile
    {
        public List<RunUpgradeDef> upgrades = new List<RunUpgradeDef>();
    }

    [Serializable]
    public sealed class RunUpgradeDef
    {
        public string id;                  // damage | attack_speed | max_health | regen | crit | collection
        public int baseCost = 20;
        public int maxLevel = 10;
        public List<StatModDef> mods = new List<StatModDef>();  // applied per level
        public int order;
        public string icon;
    }

    // ----------------------------------------------------------------------------------
    // progression.json (permanent tree, cosmetics, achievements, daily objectives)
    // ----------------------------------------------------------------------------------
    [Serializable]
    public sealed class ProgressionFile
    {
        public List<PermanentNodeDef> nodes = new List<PermanentNodeDef>();
        public List<CosmeticDef> cosmetics = new List<CosmeticDef>();
        public List<AchievementDef> achievements = new List<AchievementDef>();
        public List<DailyObjectiveDef> dailyObjectives = new List<DailyObjectiveDef>();
        public List<RewardDef> attendance = new List<RewardDef>();
        public List<string> avatars = new List<string>();
    }

    [Serializable]
    public sealed class PermanentNodeDef
    {
        public string id;
        public string branch;              // arc | citadel | stations | earnings
        public int maxLevel = 1;
        public int baseCost = 50;
        public float costGrowth = 1.6f;
        public List<StatModDef> mods = new List<StatModDef>();  // per level
        public string requiresNode;
        public int requiresLevel;
        public string requiresMission;     // optional campaign gate
        public int order;
    }

    [Serializable]
    public sealed class CosmeticDef
    {
        public string id;
        public string kind;                // hero_skin | banner | avatar_frame
        public string sprite;              // art key (e.g. hero skin id)
        public int moonGold;
        public int stormShards;
        public string achievement;         // unlocked by achievement instead of purchase
        public bool supporterOnly;         // requires the (unconfigured) supporter pack
        public int order;
    }

    [Serializable]
    public sealed class AchievementDef
    {
        public string id;
        public string stat;                // lifetime stat key
        public long target = 1;
        public RewardDef reward = new RewardDef();
        public int order;
    }

    [Serializable]
    public sealed class DailyObjectiveDef
    {
        public string id;
        public string stat;                // run stat key accumulated during the day
        public long target = 1;
        public RewardDef reward = new RewardDef();
        public string requiresMission;     // only offered after this mission is cleared
    }

    [Serializable]
    public sealed class RewardDef
    {
        public int moonGold;
        public int stormShards;
        public string cosmetic;
    }

    // ----------------------------------------------------------------------------------
    // routes.json
    // ----------------------------------------------------------------------------------
    [Serializable]
    public sealed class RoutesFile
    {
        public List<RouteLayoutDef> layouts = new List<RouteLayoutDef>();
    }

    [Serializable]
    public sealed class RouteLayoutDef
    {
        public string id;
        public List<RouteDef> routes = new List<RouteDef>();
    }

    [Serializable]
    public sealed class RouteDef
    {
        public string id;
        public string tag = "any";         // any | flank
        public List<float[]> points = new List<float[]>();  // control points [x,y] from edge to citadel
    }

    // ----------------------------------------------------------------------------------
    // missions.json
    // ----------------------------------------------------------------------------------
    [Serializable]
    public sealed class MissionsFile
    {
        public List<MissionDef> missions = new List<MissionDef>();
        public List<ModifierDef> modifiers = new List<ModifierDef>();
        public EndlessDef endless = new EndlessDef();
        public DailyChallengeDef daily = new DailyChallengeDef();
    }

    [Serializable]
    public sealed class MissionDef
    {
        public string id;
        public int index;                  // 1..12
        public string biome;               // gravewood | moonfall
        public string routeLayout = "routes_5";
        public int waves = 20;
        public float budget = 8f;          // wave 1 budget
        public float budgetGrowth = 1.12f; // multiplicative per wave
        public float healthScale = 1f;
        public float damageScale = 1f;
        public List<PoolEntryDef> pool = new List<PoolEntryDef>();
        public List<ScriptedWaveDef> scripted = new List<ScriptedWaveDef>();
        public string boss;                // boss id on the final wave (optional)
        public List<string> modifiers = new List<string>();
        public List<SlotUnlockDef> slotUnlocks = new List<SlotUnlockDef>();
        public string requiresMission;
        public int moonGold = 60;
        public int firstClearShards;
        public string unlocksModule;       // module made available on first clear
        public bool tutorial;
        public int startSlots = 3;         // max slots usable in this mission before events
    }

    [Serializable]
    public sealed class PoolEntryDef
    {
        public string enemy;
        public float weight = 1f;
        public int fromWave = 1;
        public int toWave = 999;
    }

    [Serializable]
    public sealed class ScriptedWaveDef
    {
        public int wave;
        public bool replaceBudget;         // true = only these entries this wave
        public string announceKey;
        public List<SummonDef> entries = new List<SummonDef>();
    }

    [Serializable]
    public sealed class SlotUnlockDef
    {
        public int wave;                   // unlock happens when this wave starts
        public string slot;
        public string grantModule;         // optional module granted immediately (tutorial)
    }

    [Serializable]
    public sealed class ModifierDef
    {
        public string id;
        public float healthMult = 1f;
        public float speedMult = 1f;
        public float damageMult = 1f;
        public float armorAdd;
        public float budgetMult = 1f;
        public Dictionary<string, float> weightMult = new Dictionary<string, float>();
        public Dictionary<string, float> p = new Dictionary<string, float>();
    }

    [Serializable]
    public sealed class EndlessDef
    {
        public string requiresMission = "m12";
        public float budget = 14f;
        public float budgetGrowth = 1.06f;
        public float budgetCap = 220f;
        public float healthScale = 3.0f;
        public float healthGrowthLinear = 0.10f;
        public float healthGrowthQuadratic = 0.002f;
        public float healthCap = 60f;
        public int modifierEvery = 5;
        public int maxModifiers = 4;
        public List<string> modifierCycle = new List<string>();
        public int bossEvery = 10;
        public List<string> bossCycle = new List<string>();
        public List<PoolEntryDef> pool = new List<PoolEntryDef>();
        public string routeLayout = "routes_5";
        public int moonGoldPerWave = 6;
    }

    [Serializable]
    public sealed class DailyChallengeDef
    {
        public string requiresMission = "m03";
        public int waves = 15;
        public float budget = 10f;
        public float budgetGrowth = 1.13f;
        public float healthScale = 1.6f;
        public List<PoolEntryDef> pool = new List<PoolEntryDef>();
        public List<string> modifierChoices = new List<string>();
        public List<string> bossChoices = new List<string>();
        public int moonGold = 80;
    }
}
